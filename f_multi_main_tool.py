import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import f_multi_kakao_tool
import f_multi_google_tool
import f_multi_naver_tool
import kakaoapi

#전역 변수
MAX_WORKERS = 10

def _extract_reviews_from_tool_output(obj):
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        revs = obj.get("reviews")
        if isinstance(revs, list):
            return revs
    return []

def get_store_list_from_kakao(keyword: str, top_n: int = 5, headless: bool = True):
    try:
        out,_ = kakaoapi.kakao_keyword_nearby(None, None,query=keyword,radius=1200,TOP_N_STORES=5,)
        if isinstance(out, dict):
            return list(out.items())[:top_n]
    except Exception as e:
        print(f"[SEARCH_STORE][ERR] {e}")
    return []

def fetch_kakao_reviews(store_name: str, max_reviews: int):
    try:
        out = f_multi_kakao_tool.run_multi(store_name, max_reviews=max_reviews)
        if isinstance(out, dict):
            return {
                "reviews": out.get("reviews", []),
                "store_image": out.get("store_image")
            }
        return {"reviews": [], "store_image": None}
    except Exception as e:
        print(f"[KAKAO][ERR] {store_name}: {e}")
        return {"reviews": [], "store_image": None}

def fetch_google(store_name: str, max_reviews: int):
    try:
        out = f_multi_google_tool.run(store_name, max_reviews=max_reviews)
        return _extract_reviews_from_tool_output(out)
    except Exception:
        return []

def fetch_naver(store_keyword: str, max_reviews: int):
    try:
        out = f_multi_naver_tool.run(store_keyword, max_reviews=max_reviews)
        return _extract_reviews_from_tool_output(out)
    except Exception as e:
        print(f"[NAVER][ERR] {store_keyword}: {e}")
        return []

# -------------------------
# 메인 파이프라인 (병렬)
# -------------------------
def collect_all_reviews_parallel(keyword: str, top_n: int = 5, max_reviews: int = 20, headless: bool = True):

    print(f"[SEARCH_STORE] 검색: {keyword}")
    store_pairs = get_store_list_from_kakao(keyword, top_n=top_n, headless=headless)
    if not store_pairs:
        print("[WARN] search_store에서 상위 매장명을 가져오지 못했습니다.")
        return {}

    results = {
        name: {
            "address": addr,
            "store_image": None,
            "kakao": {"reviews": []},
            "google": {"reviews": []},
            "naver": {"reviews": []}
        }
        for (name, addr) in store_pairs
    }

    futures = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for store_name, _addr in store_pairs:
            futures[ex.submit(fetch_kakao_reviews, store_name, max_reviews)] = ("kakao", store_name)
            futures[ex.submit(fetch_google, store_name, max_reviews)] = ("google", store_name)
            futures[ex.submit(fetch_naver, store_name.strip(), max_reviews)] = ("naver", store_name)

        for fut in as_completed(futures):
            src, name = futures[fut]
            try:
                revs = fut.result()
            except Exception as e:
                print(f"[{src.upper()}][ERR] {name}: {e}")
                revs = {"reviews": [], "store_image": None} if src == "kakao" else []

            if src == "kakao":
                results[name]["kakao"]["reviews"] = revs.get("reviews", [])
                results[name]["store_image"] = revs.get("store_image")  # ✅ 최상위에 저장
            else:
                results[name][src]["reviews"] = revs if isinstance(revs, list) else []

    print(f"[INFO] 병렬 수집 완료: {len(store_pairs)}개 매장, 경과 {time.time()-t0:.1f}s")
    return results

if __name__ == "__main__":
    kw = "정자동 삼겹살"
    out = collect_all_reviews_parallel(kw, top_n=1, max_reviews=10, headless=True)
    print(out)
