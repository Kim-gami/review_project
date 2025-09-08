# DB_craw.py

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama.llms import OllamaLLM
import os, re, hashlib, json
from typing import Optional, Tuple, Dict, Any, List
import math
import textwrap
import dotenv
dotenv.load_dotenv()
# ---- 외부 모듈 ----
import f_multi_main_tool
import latlontest
from concurrent.futures import ThreadPoolExecutor, as_completed
# ---- sqlite3 폴백(일부 윈도우 환경용) ----
try:
    import sqlite3  # 표준
except Exception:
    import sys, pysqlite3  # pip install pysqlite3-binary
    sys.modules['sqlite3'] = pysqlite3
    sys.modules['_sqlite3'] = pysqlite3
    import sqlite3

# =========================
# 설정
# =========================
DB_PATH = "reviews.db"
TOP_N_STORES = 5
STALE_DAYS = 30
PER_SOURCE_LIMIT = None   # 출처별 최신 N개 제한(없으면 전체)
CRAWL_MAX_REVIEWS = 10
CRAWL_HEADLESS = True
CRAWL_MAX_WORKERS = 5

PROMPT = """너는 리뷰 요약 및 평가 전문가야.
아래 매장 리뷰들(여러 출처, 최신/과거 혼재)을 읽고, 반드시 아래 JSON만 출력해.

출력 스키마(이 키/형식 그대로):
{{
  "one_liner": "30~40자 핵심 한 줄 평",
  "rating": 4.3,
  "complain": ["불만사항1", "불만사항2"]
}}

작성 규칙:
- 출력은 **JSON 한 덩어리만** 내고, 그 외 텍스트/설명/코드블록(``` 등)은 절대 포함하지 말 것.
- 언어는 한국어. 간결하고 사실 기반으로. 과장 금지, 이모지/해시태그 금지.
- "rating"은 **1.0~5.0** 사이 **소수점 한 자리**의 숫자(float)로. 근거 부족/리뷰 적으면 **3.0**에 가깝게 보수적.
- "complain"은 **리뷰에 실제로 나타난 반복/빈번한 불만**만 추출(1~2개). 사소한/단발성은 제외.
- 상반된 평이 있으면 **빈도/최근성**을 가볍게 반영해 평균적 체감 품질로 판단.
- 중복/동의어는 합치고, 각 항목은 **25자 내외**로 짧게.
- 매장명/출처/별점 숫자 등 메타는 본문에 넣지 말 것(오직 JSON 키만).

[매장명]
{store}

[리뷰들]
{reviews}
"""
# =========================
# DB & 스키마 (+마이그레이션)
# =========================
DDL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS stores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_name  TEXT,
  address     TEXT,
  lat         REAL,
  lng         REAL,
  img1        TEXT,
  img2        TEXT,
  img3        TEXT,
  store_key   TEXT UNIQUE,
  created_at  TEXT DEFAULT (datetime('now')),
  updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id    INTEGER NOT NULL,
  source      TEXT,
  review      TEXT,
  review_hash TEXT UNIQUE,
  first_seen  TEXT DEFAULT (datetime('now')),
  last_seen   TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_stores_name ON stores(store_name);
CREATE INDEX IF NOT EXISTS idx_reviews_store ON reviews(store_id);
CREATE INDEX IF NOT EXISTS idx_reviews_source ON reviews(source);
CREATE INDEX IF NOT EXISTS idx_reviews_lastseen ON reviews(last_seen);
"""
def checkpoint(db_path=DB_PATH, mode="TRUNCATE"):
    with sqlite3.connect(db_path) as con:
        con.execute(f"PRAGMA wal_checkpoint({mode});")

def _connect(db_path: str = DB_PATH):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con

def _ensure_column(table: str, col: str, col_def: str):
    with _connect() as con:
        cols = [r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def};")

def _init_db():
    with _connect() as con:
        con.executescript(DDL)

# =========================
# 유틸: 정규화/파싱/해시
# =========================
def _as_float_or_none(x):
    try:
        return float(x)
    except Exception:
        return None

def _split_address_latlng(addr_field, lat=None, lng=None):
    """
    addr_field: "성남시 분당구 ..."  또는  ("성남시 분당구 ...", (37.39, 127.12))
    반환: (address_str, lat, lng)
    """
    # 케이스 1) 문자열 주소
    if isinstance(addr_field, str):
        return addr_field, lat, lng

    # 케이스 2) (주소, (lat,lng)) or [주소, [lat,lng]]
    if isinstance(addr_field, (tuple, list)) and len(addr_field) >= 1:
        address_str = addr_field[0] if isinstance(addr_field[0], str) else str(addr_field[0])

        if len(addr_field) >= 2:
            latlng = addr_field[1]
            if isinstance(latlng, (tuple, list)) and len(latlng) >= 2:
                if lat is None:
                    lat = _as_float_or_none(latlng[0])
                if lng is None:
                    lng = _as_float_or_none(latlng[1])

        return address_str, lat, lng

    # 기타: 문자열로 강제
    return (str(addr_field) if addr_field is not None else None), lat, lng
_LATLNG_RE = re.compile(r"\(([-+]?\d+(?:\.\d+)?)[,\s]+([-+]?\d+(?:\.\d+)?)\)")

def _norm_text(s: Optional[str]) -> str:
    s = "" if s is None else str(s)
    return re.sub(r"\s+", " ", s).strip().lower()

def _parse_lat_lng_from_address(addr: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(addr, str): return None, None
    m = _LATLNG_RE.search(addr)
    if not m: return None, None
    try: return float(m.group(1)), float(m.group(2))
    except Exception: return None, None

def _make_store_key(name: str, address: Optional[str]) -> str:
    base = f"{_norm_text(name)}|{_norm_text(address)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def _make_review_hash(store_id: int, source: Optional[str], review: Optional[str]) -> str:
    base = f"{store_id}|{_norm_text(source)}|{_norm_text(review)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

# =========================
# Top5 후보 (카카오 리스트)
# =========================
def get_top5_store_pairs(keyword: str, lat: float, lon: float, query: str) -> List[Tuple[str, Optional[str], Optional[Tuple[Optional[float], Optional[float]]]]]:
    """
    반환: [(store_name, address, (lat,lng)), ...] 최대 5개
    f_multi_kakao_tool.run_multi() → {"매장명": (주소, (lat,lng))}
    """
    # ✅ 분기: '근처 ' 접두어 → GPS 반경 검색 / 아니면 키워드만 검색
    kw = (keyword or "").strip()
    if kw.startswith("근처 "):
        q = kw.replace("근처", "", 1).strip()  # '근처 ' 제거 → 실제 카테고리/태그
        ret, distance = latlontest.kakao_keyword_nearby(
            lat=lat, lon=lon, query=q, TOP_N_STORES=TOP_N_STORES
        )
    else:
        # 예: "정자동 삼겹살" → 좌표 없이 전국 검색(정확도 우선, 카카오가 지역어를 해석)
        ret, distance = latlontest.kakao_keyword_nearby(
            query=kw, TOP_N_STORES=TOP_N_STORES
        )

    pairs: List[Tuple[str, Optional[str], Optional[Tuple[Optional[float], Optional[float]]]]] = []
    if isinstance(ret, dict):
        for name, val in list(ret.items())[:TOP_N_STORES]:
            addr, latlng = None, None
            if isinstance(val, tuple):
                if len(val) >= 1: addr = val[0]
                if len(val) >= 2 and isinstance(val[1], tuple): latlng = val[1]
            elif isinstance(val, str):
                addr = val
            pairs.append((str(name).strip(), addr, latlng))
    return pairs[:TOP_N_STORES], distance

# =========================
# 신선도/조회
# =========================
def latest_age_days(store_name: str) -> Optional[float]:
    q = """
    SELECT julianday('now') - julianday(MAX(r.last_seen)) AS age_days
    FROM reviews r
    JOIN stores s ON r.store_id = s.id
    WHERE s.store_name = ?
    """
    with _connect() as con:
        row = con.execute(q, (store_name,)).fetchone()
    if not row or row["age_days"] is None: return None
    try: return float(row["age_days"])
    except Exception: return None

# =========================
# 업서트(메모리 → DB)  ★ store_image도 반영
# =========================
UPSERT_STORE_SQL = """
INSERT INTO stores (store_name, address, lat, lng, img1, img2, img3, store_key)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(store_key) DO UPDATE SET
  store_name  = excluded.store_name,
  address     = excluded.address,
  lat         = COALESCE(excluded.lat, stores.lat),
  lng         = COALESCE(excluded.lng, stores.lng),
  img1        = COALESCE(excluded.img1, stores.img1),
  img2        = COALESCE(excluded.img2, stores.img2),
  img3        = COALESCE(excluded.img3, stores.img3),
  updated_at  = datetime('now');
"""
UPSERT_REVIEW_SQL = """
INSERT INTO reviews (store_id, source, review, review_hash)
VALUES (?, ?, ?, ?)
ON CONFLICT(review_hash) DO UPDATE SET
  source    = excluded.source,
  review    = excluded.review,
  last_seen = datetime('now');
"""

def _upsert_one_store(con, name, address, lat, lng, store_images):
    # store_images 는 list 또는 None
    img1 = img2 = img3 = None
    if isinstance(store_images, list):
        if len(store_images) > 0: img1 = store_images[0]
        if len(store_images) > 1: img2 = store_images[1]
        if len(store_images) > 2: img3 = store_images[2]

    store_key = _make_store_key(name, address)
    con.execute(UPSERT_STORE_SQL, (name, address, lat, lng, img1, img2, img3, store_key))
    sid = con.execute("SELECT id FROM stores WHERE store_key=?", (store_key,)).fetchone()[0]
    return int(sid)

def upsert_from_results(results: dict) -> dict:
    store_ids = {}
    with _connect() as con:
        with con:  # 트랜잭션
            for name, obj in results.items():
                address_raw = (obj or {}).get("address")      # <-- 지금은 튜플일 수 있음
                store_image = (obj or {}).get("store_image")

                # 주소 문자열 안의 "(lat,lng)" 패턴 파싱이 따로 있다면 먼저 적용 (옵션)
                lat0, lng0 = _parse_lat_lng_from_address(address_raw if isinstance(address_raw, str) else None)

                # ⭐ 최종적으로 주소/좌표를 정규화(문자열, float)
                address, lat, lng = _split_address_latlng(address_raw, lat0, lng0)

                # 이제부터 address는 str, lat/lng는 float/None 보장
                sid = _upsert_one_store(con, name, address, lat, lng, store_image)
                store_ids[name] = sid

                for source in ("kakao", "google", "naver"):
                    reviews = ((obj or {}).get(source) or {}).get("reviews") or []
                    for rv in reviews:
                        rv_text = str(rv or "").strip()
                        if not rv_text:
                            continue
                        rh = _make_review_hash(sid, source, rv_text)
                        con.execute(UPSERT_REVIEW_SQL, (sid, source, rv_text, rh))
    return store_ids

# =========================
# 크롤 호출(매장 단일)
# =========================
def crawl_one_store(store_name: str) -> Dict[str, Any]:
    return f_multi_main_tool.collect_all_reviews_parallel(
        keyword=store_name, top_n=1, max_reviews=CRAWL_MAX_REVIEWS, headless=CRAWL_HEADLESS
    )

# =========================
# 조회: 상위 5개만 DB→리스트 (store_image 포함)
# =========================
def fetch_reviews_for_store_list(store_names: List[str],
                                 per_source_limit: Optional[int] = PER_SOURCE_LIMIT) -> List[Dict[str, Any]]:
    if not store_names: return []
    placeholders = ",".join(["?"] * len(store_names))
    sql = f"""
    SELECT s.store_name, s.address, s.lat, s.lng,
       s.img1, s.img2, s.img3,
       r.source, r.review, r.last_seen
    FROM reviews r
    JOIN stores s ON r.store_id = s.id
    WHERE s.store_name IN ({placeholders})
    ORDER BY s.store_name, r.source, r.last_seen DESC
    """
    with _connect() as con:
        rows = con.execute(sql, store_names).fetchall()

    if per_source_limit and per_source_limit > 0:
        grouped = {}
        for row in rows:
            key = (row["store_name"], row["source"] or "UNKNOWN")
            grouped.setdefault(key, []).append(row)
        rows = [r for (_k, lst) in grouped.items() for r in lst[:per_source_limit]]

    out = []
    for r in rows:
        out.append({
            "store_name": r["store_name"],
            "address": r["address"],
            "lat": r["lat"],
            "lng": r["lng"],
            "img1": r["img1"],
            "img2": r["img2"],
            "img3": r["img3"],
            "source": r["source"],
            "review": r["review"],
            "last_seen": r["last_seen"],
        })
    return out

def _second_token_or_first(q: str) -> Optional[str]:
    toks = (q or "").split()
    if not toks:
        return None
    return toks[1] if len(toks) >= 2 else toks[0]

# =========================
# 메인 오케스트레이션(키워드 전용, LLM 없음)
# =========================
def run_keyword_flow(keyword: str, lat: float, lon:float, query:str,
                     stale_days: int = STALE_DAYS,
                     per_source_limit: Optional[int] = PER_SOURCE_LIMIT) -> Dict[str, Any]:
    def _extract_dong(text: str) -> Optional[str]:
        """문자열에서 '정자동', '야탑동' 같은 동 토큰을 추출"""
        if not text:
            return None
        m = re.search(r'([가-힣0-9]+동)\b', text)
        return m.group(1) if m else None
    _init_db()

    # 1) Top-N 후보
    top5_pairs, distance = get_top5_store_pairs(keyword, lat, lon, query)
    top5_names = [n for (n, _a, _ll) in top5_pairs]
    print(f"[INFO] Top-{len(top5_names)} stores:", ", ".join(top5_names))

    # 2) Freshness 체크 → 필요시 크롤링 & 업서트
    need_crawl: List[str] = []
    for name, addr, latlng in top5_pairs:
        age = latest_age_days(name)
        if age is None or age > stale_days:
            need_crawl.append(name)

    if need_crawl:
        all_results: Dict[str, Any] = {}

        # ✅ 페어 맵(주소/좌표를 나중에 upsert 직전에도 쓸 거라 루프 밖에서 만들어둠)
        pair_map = {n: (a, ll) for (n, a, ll) in top5_pairs}

        to_crawl: List[Tuple[str, str]] = []
        for name in need_crawl:
            try:
                addr, _latlng = pair_map.get(name, (None, None))

                # 1) 주소에서 동 추출 → 없으면 keyword에서 추출
                dong = _extract_dong(addr) or _extract_dong(keyword)

                # 2) 매장명의 첫 토큰 + 동을 조합 (동이 있으면 앞에 붙임)
                base_token = (name.split()[0] if name else "").strip()
                if dong:
                    n_keyword = f"{dong} {base_token}".strip()
                else:
                    n_keyword = base_token or name  # 둘 다 없으면 name 전체

                to_crawl.append((name, n_keyword))
            except Exception as e:
                print(f"[PREP_ERROR] {name}: {e}")

        # 2) 병렬 크롤 (I/O 바운드)
        with ThreadPoolExecutor(max_workers=CRAWL_MAX_WORKERS, thread_name_prefix="crawl") as ex:
            future_map = {ex.submit(crawl_one_store, nkw): name for (name, nkw) in to_crawl}

            for fut in as_completed(future_map):
                name = future_map[fut]
                try:
                    res = fut.result()  # 기대형태: { "매장명": {...} }
                    if isinstance(res, dict) and res:
                        all_results.update(res)
                except Exception as e:
                    print(f"[CRAWL_ERROR] {name}: {e}")

        if all_results:
            # ✅ 업서트 직전 좌표 주입 (기존 로직 유지)
            for n, obj in all_results.items():
                if n in pair_map:
                    a, ll = pair_map[n]
                    obj["address"] = (a, ll)

            upsert_from_results(all_results)
            checkpoint(db_path=DB_PATH)

    # 3) DB에서 최종 리뷰 불러오기
    rows = fetch_reviews_for_store_list(top5_names, per_source_limit=per_source_limit)

    # 4) 반환 딕셔너리 구성
    results: Dict[str, Any] = {}
    for r in rows:
        store = r["store_name"]
        if store not in results:
            images = [x for x in (r["img1"], r["img2"], r["img3"]) if x]
            results[store] = {
                "address": r["address"],
                "lat": r["lat"],
                "lng": r["lng"],
                "store_image": images,
                "kakao": {"reviews": []},
                "google": {"reviews": []},
                "naver": {"reviews": []}
            }
        src = (r["source"] or "").lower()
        if src in results[store]:
            results[store][src]["reviews"].append(r["review"])

    return results, distance

def _safe_parse_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}

def _sanitize_payload(parsed: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    one  = parsed.get("one_liner") or ""
    one  = one.strip() if isinstance(one, str) else ""

    rating = parsed.get("rating", 3.0)
    try:
        rating = float(rating)
    except Exception:
        rating = 3.0
    rating = max(1.0, min(5.0, rating))

    complains = [c for c in parsed.get("complain", []) if isinstance(c, str) and c.strip()][:6]

    return {
        "one_liner": one,
        "rating": round(rating, 1),
        "complain": complains,
        "raw_text_len": len(raw_text),
    }

def _interleave_and_dedupe(buckets: List[List[str]], limit: int) -> List[str]:
    """여러 소스 리뷰를 번갈아 섞어 limit까지 수집, 공백/중복 제거."""
    idx = [0] * len(buckets)
    out, seen = [], set()
    while len(out) < limit and any(i < len(b) for i, b in zip(idx, buckets)):
        for k, b in enumerate(buckets):
            i = idx[k]
            if i < len(b):
                rv = (b[i] or "").strip()
                idx[k] += 1
                if not rv or rv in seen:
                    continue
                seen.add(rv)
                out.append(rv)
                if len(out) >= limit:
                    break
    return out

def _gather_reviews_per_store(data: Dict[str, Any], limit: int) -> List[str]:
    """results[store]에서 리뷰만 추출. kakao/google/naver + 최상단 reviews 모두 지원."""
    # 표준 구조
    kakao  = list((((data.get("kakao")  or {}).get("reviews")) or []))
    google = list((((data.get("google") or {}).get("reviews")) or []))
    naver  = list((((data.get("naver")  or {}).get("reviews")) or []))
    # fallback: 최상단 reviews
    top    = list(((data.get("reviews")) or []))
    buckets = [kakao, google, naver, top] if top else [kakao, google, naver]
    return _interleave_and_dedupe(buckets, limit)

# -------------------- 메인 함수 --------------------
def summarize_store_with_rating(
    results: Dict[str, Any],
    model_name: str = "llama3.1",
    max_reviews_per_store: int = 60,
    max_workers: int = 6,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    dict(results)를 받아 LLM에 병렬 추론을 수행해 매장별 한 줄 평/장단점/별점을 생성.
    return: {store: {"one_liner": str, "pros":[...], "cons":[...], "rating":4.2, "raw_text_len":N}}
    """
    llm = OllamaLLM(
        model=model_name,
        temperature=temperature,
        # api_key=api_key or os.getenv('OLLAMA_LOCAL_HOST'),
        base_url=base_url
    )
    prompt = PromptTemplate.from_template(PROMPT)
    chain = prompt | llm | StrOutputParser()

    # 입력 준비
    inputs, order = [], []
    for store, data in results.items():
        reviews = _gather_reviews_per_store(data, max_reviews_per_store)
        text = "\n".join(reviews)
        inputs.append({"store": store, "reviews": text})
        order.append((store, text))

    if not inputs:
        return {}

    # 병렬 추론 (LCEL .batch)
    raw_outputs = chain.batch(inputs, config={"max_concurrency": max_workers})
    # 임시
    with open("result.txt", 'w', encoding='utf-8') as f:
        f.write(str(raw_outputs))
    # 후처리
    out: Dict[str, Any] = {}
    for (store, text), raw in zip(order, raw_outputs):
        parsed = _safe_parse_json(raw)
        # 리뷰가 비어있거나 JSON 파싱 실패 시 기본값
        if not text.strip():
            out[store] = {"one_liner": "", "rating": 3.0, "complain": [], "raw_text_len": 0}
            continue
        if not parsed or not isinstance(parsed, dict):
            parsed = {"one_liner": "", "rating": 3.0, "complain": [], "raw_text_len": 0}
        out[store] = _sanitize_payload(parsed, text)

    return out
def pretty_print_summaries(summary: dict, width: int = 80):
    """
    summary: { "가게명": {"one_liner": str, "rating": float, "complain": [str], "raw_text_len": int}, ... }
    width  : 한 줄 래핑 폭
    """
    if not summary:
        print("출력할 요약이 없습니다.")
        return

    name_w = max(len(str(name)) for name in summary.keys())

    for store, s in summary.items():
        one = (s.get("one_liner") or "").strip()
        rating = float(s.get("rating", 3.0))
        complains = [c for c in (s.get("complain") or []) if isinstance(c, str) and c.strip()]
        raw_len = int(s.get("raw_text_len", 0))

        # 별점 막대
        filled = int(round(rating))  # 정수 개수의 별
        stars = "★" * filled + "☆" * (5 - filled)
        stars += f"  ({rating:.1f})"

        # 헤더
        print("─" * width)
        print(f"🏪 {store}")
        print(f"   별점: {stars}   |   원문 길이: {raw_len}")

        # 한 줄 평
        if one:
            wrapped = textwrap.fill(one, width=width, subsequent_indent=" " * 6)
            print(f"   한줄평: {wrapped}")
        else:
            print(f"   한줄평: (없음)")

        # 불만사항
        if complains:
            print("   불만사항:")
            for i, c in enumerate(complains, 1):
                wrapped = textwrap.fill(c, width=width, subsequent_indent=" " * 8)
                print(f"      {i}. {wrapped}")
        else:
            print("   불만사항: (없음)")

    print("─" * width)
if __name__ == "__main__":
    out = run_keyword_flow("정자 두향", stale_days=7, per_source_limit=None)
    # print(out)
    # summary = summarize_store_with_rating(
    #     results=out,  # 앞 단계 산출물
    #     model_name="llama3.1",
    #     max_reviews_per_store=60,
    #     max_workers=6,
    #     temperature=0.2,  # 일관된 출력
    #     base_url= os.getenv("OLLAMA_REMOTE_HOST")
    # )
    # pretty_print_summaries(summary, width=90)
    from pprint import pprint
    pprint(out)