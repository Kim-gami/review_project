import os, dotenv, ast, html, folium, sqlite3
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
from datetime import datetime

import DB_craw
import latlontest

dotenv.load_dotenv()

# =========================
# 0) 기본 설정 / 상수
# =========================
st.set_page_config(page_title="PickPlace", page_icon="📍", layout="wide", initial_sidebar_state="collapsed")

# Python에서 플래그 읽어 세션에 저장
is_mobile = (st.query_params.get("m") == "1")
st.session_state["is_mobile"] = is_mobile

PRIMARY   = "#FF6B35"
# SECONDARY = "#FFB366"
# ACCENT    = "#FFF3E0"
# WARM      = "#FFF8F0"

JEONGJA_LAT, JEONGJA_LON = 37.3670, 127.1080
map_height = 320 if st.session_state.get("is_mobile") else 600
TAGS = [
    "#삼겹살","#치킨","#족발","#국밥","#파스타","#피자","#햄버거","#초밥",
    "#돈카츠","#라멘","#덮밥","#중식","#마라탕","#쌀국수","#카페","#디저트"
]

GOOD_SHOPS = [
    '토속정','이남장 분당점','시계토끼','더진국 분당정자역점','맛찬들왕소금구이 분당정자점','만족오향족발 정자점','샬라타이',
    '이경진우렁쌈밥정식','불고기미식관','천지한우전문점','서울감자탕 정자1지점','이한진 푸른참치','늘봄웰봄',
    '김명자낙지마당 정자점','카리 분당정자카페점','선한레시피 정자본점','홍차이나','미카도','춘향골남원추어탕 정자점','푸른바다볼테기','고향집삼계탕','두향'
]

st.session_state.setdefault("search_kw", "")
st.session_state.setdefault("kw_input", "")
st.session_state.setdefault("do_search", False)
st.session_state.setdefault("search_in_progress", False)
st.session_state.setdefault("search_token", 0)

#함수
#백엔드/데이터 및 추론
@st.cache_data(show_spinner=False, ttl=3600)
def fetch_results_and_summaries(keyword: str, lat:float, lon:float, query:str):
    if not keyword:
        return {}, {}, {}
    results, real_distance = DB_craw.run_keyword_flow(keyword, lat, lon, query, stale_days=30, per_source_limit=None)
    base_url = os.getenv('OLLAMA_REMOTE_HOST', 'http://jappscompany.duckdns.org:11434/')
    summaries = DB_craw.summarize_store_with_rating(
        results=results,
        model_name="llama3.1",
        max_reviews_per_store=60,
        max_workers=6,
        temperature=0.2,
        base_url=base_url
    )
    return results, summaries, real_distance

#약식카드
def render_compact_store_card(row: dict):
    name  = str(row.get("name", ""))
    results, summaries, real_distance = fetch_results_and_summaries(name, lat=BASE_LAT, lon=BASE_LON, query=search_kw)
    for store_name, info in results.items():
        one_liner = summaries.get(store_name, {}).get("one_liner", "")
        rating = summaries.get(store_name, {}).get("rating", 4.2)
        complain = summaries.get(store_name, {}).get("complain", [])

    img   = first_image(row.get("store_image")) or row.get("img1") or "https://placehold.co/680x380?text=No+Image"
    star_html, rating_str = make_star_html(rating)
    one_liner = html.escape(str(one_liner))
    complain = html.escape(str(complain))
    html_block = f"""
    <div class="card compact" style="
         overflow:hidden; border:1px solid #eee; border-radius:16px; background:#fff;
         box-shadow:0 4px 14px rgba(17,24,39,.06);">
      <img src="{img}" alt="대표이미지"
           style="width:100%; height:180px; object-fit:cover;">
      <div class="card-body" style="padding:14px;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:10px;">
          <h4 style="margin:0; font-size:18px; font-weight:800; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            {html.escape(name)}
          </h4>
          <div class="stars" style="white-space:nowrap;">{star_html}</div>
        </div>
        <div class="meta" style="margin-top:4px; color:#6b7280; font-size:12px;">
          평점 {rating_str}
        </div>
        <div style="font-size:13px; color:#333; background:#f9f9f9; padding:10px;
                    border-radius:10px; margin-top:10px;">
           “{one_liner}”
        </div>
                <div style="font-size:13px; color:#333; background:#f9f9f9; padding:10px;
                    border-radius:10px; margin-top:10px;">
           “{complain}”
        </div>
      </div>
    </div>
    """
    components.html(html_block, height=360, scrolling=False)

#이미지 1장 갖고오기
def first_image(x):
    if isinstance(x, list) and x:
        return x[0]
    if isinstance(x, str):
        try:
            v = ast.literal_eval(x)
            if isinstance(v, list) and v:
                return v[0]
        except Exception:
            pass
        if x.strip().startswith("http"):
            return x.strip()
    return None

#이미지 3장 갖고오기
def take_three_images(x):
    if isinstance(x, list):
        imgs = x[:3]
    elif isinstance(x, str):
        try:
            v = ast.literal_eval(x)
            imgs = v[:3] if isinstance(v, list) else ([x] if x.strip().startswith("http") else [])
        except Exception:
            imgs = [x] if x.strip().startswith("http") else []
    else:
        imgs = []
    while len(imgs) < 3:
        imgs.append("https://img.freepik.com/premium-vector/no-photo-available-vector-icon-default-image-symbol-picture-coming-soon-web-site-mobile-app_87543-18055.jpg")
    return imgs[:3]

#위치 받아오기
def ensure_browser_geolocation():
    """
    - 쿼리에 ulat/ulon이 없을 때만 브라우저에 위치 권한을 요청
    - 성공 시 쿼리에 ulat/ulon 추가 후 새로고침
    - 실패/거부 시 조용히 패스(기본 좌표로 폴백)
    """
    qp = st.query_params
    if "ulat" in qp and "ulon" in qp:
        return

    components.html("""
    <script>
    (function(){
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition(
        function(pos){
          const lat = pos.coords.latitude.toFixed(6);
          const lon = pos.coords.longitude.toFixed(6);
          const url = new URL(window.parent.location);
          url.searchParams.set('ulat', lat);
          url.searchParams.set('ulon', lon);
          window.parent.history.replaceState(null, '', url);
          window.parent.location.reload();
        },
        function(_err){},
        { enableHighAccuracy:true, timeout:8000, maximumAge:60000 }
      );
    })();
    </script>
    """, height=0)

#지도 중심 잡기
def _center_of_bounds(bounds: dict):
    try:
        sw = bounds.get("_southWest") or bounds.get("southWest")
        ne = bounds.get("_northEast") or bounds.get("northEast")
        clat = (float(sw["lat"]) + float(ne["lat"])) / 2.0
        clon = (float(sw["lng"]) + float(ne["lng"])) / 2.0
        return clat, clon
    except Exception:
        return None

#정확한 위치 설정용 지도
def render_center_picker_dialog(BASE_LAT: float, BASE_LON: float):
    """모달 안에서만 사용하는 위치 설정 전용 지도(m_loc)"""
    m_loc = folium.Map(location=[BASE_LAT, BASE_LON], zoom_start=16)

    folium.Marker(
        [BASE_LAT, BASE_LON],
        tooltip="현재 저장된 위치",
        icon=folium.Icon(color="red", icon="user")
    ).add_to(m_loc)

    # 십자선 오버레이
    st.markdown("""
    <div style="position:relative;">
      <div style="position:absolute; z-index:9999; left:50%; top:50%;
        width:24px; height:24px; margin-left:-12px; margin-top:-12px; pointer-events:none;">
        <svg viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="3" fill="none" stroke="#FF6B35" stroke-width="2"/>
          <line x1="12" y1="0"  x2="12" y2="6"  stroke="#FF6B35" stroke-width="2"/>
          <line x1="12" y1="18" x2="12" y2="24" stroke="#FF6B35" stroke-width="2"/>
          <line x1="0"  y1="12" x2="6"  y2="12" stroke="#FF6B35" stroke-width="2"/>
          <line x1="18" y1="12" x2="24" y2="12" stroke="#FF6B35" stroke-width="2"/>
        </svg>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st_map_loc = st_folium(m_loc, key="map_loc_picker", width=900, height=map_height)

    chosen = None
    if isinstance(st_map_loc, dict) and st_map_loc.get("bounds"):
        chosen = _center_of_bounds(st_map_loc["bounds"])

    col_a, col_b = st.columns([1,4])
    with col_a:
        if st.button("이 화면 중심으로 저장", type="primary"):
            if chosen:
                lat, lon = chosen
                st.session_state["user_lat"] = lat
                st.session_state["user_lon"] = lon
                st.query_params.update({"ulat": f"{lat:.6f}", "ulon": f"{lon:.6f}"})
                st.session_state["show_loc_dialog"] = False
                st.success(f"저장됨: {lat:.6f}, {lon:.6f}")
                st.rerun()
            else:
                st.warning("지도를 한 번 움직이거나 확대/축소해 주세요.")
    with col_b:
        if chosen:
            st.caption(f"화면 중심: {chosen[0]:.6f}, {chosen[1]:.6f}")
        else:
            st.caption("화면 중심 좌표를 읽는 중...")

#태그 버튼 클릭시
def _apply_tag(tag_text: str):
    st.session_state["kw_input"] = tag_text
    st.session_state["search_kw"] = tag_text
    st.session_state["do_search"] = True
    st.session_state["search_in_progress"] = True

#태그 버튼 UI용 청크 나누기
def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

#별점 표기
def make_star_html(value):
    if not isinstance(value, (int, float)):
        value = 4.2  # 기본값
    value = max(0.0, min(5.0, float(value)))
    full = int(value)
    half = 1 if value - full >= 0.5 else 0
    empty = 5 - full - half
    return "★"*full + ("☆" if half else "") + "☆"*empty, f"{value:.1f}"

#모범음식점 렌더링
def render_good_shop_carousel(good_shop: list[str]):
    """
    good_shop: ['돈멜', '미방 정자점', ...] 처럼 매장명 리스트
    DB에서 매장 정보 읽어와 가로 스크롤 카드로 노출
    """
    if not good_shop:
        return

    conn = sqlite3.connect("reviews.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # IN (...) 쿼리로 한 번에 가져오기
    ph = ",".join(["?"] * len(good_shop))
    cur.execute(f"""
        SELECT store_name, address, lat, lng, img1, img2, img3
        FROM stores
        WHERE store_name IN ({ph})
    """, good_shop)
    rows_info = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows_info:
        st.info("선정된 매장을 DB에서 찾지 못했습니다.")
        return

    # 입력 순서 유지
    order = {name: i for i, name in enumerate(good_shop)}
    rows_info.sort(key=lambda r: order.get(r["store_name"], 10**9))

    # 카드 데이터 만들기
    DEFAULT_IMG = "https://via.placeholder.com/320x200?text=No+Image"
    cards_html = []
    for r in rows_info:
        imgs = [r.get("img1"), r.get("img2"), r.get("img3")]
        imgs = [u for u in imgs if u]  # None/빈값 제거
        rep = imgs[0] if imgs else DEFAULT_IMG
        name = html.escape(str(r.get("store_name") or ""))
        addr = html.escape(str(r.get("address") or ""))

        card = f"""
        <div class="pp-card">
          <div class="pp-thumb">
            <img src="{rep}" alt="대표이미지"
                 onerror="this.onerror=null;this.src='{DEFAULT_IMG}';" />
          </div>
          <div class="pp-body">
            <div class="pp-title">{name}</div>
            <div class="pp-meta">{addr}</div>
          </div>
        </div>
        """
        cards_html.append(card)

    html_block = f"""
    <style>
      .pp-wrap {{
        position: relative; margin: 8px 0 18px 0;
      }}
      .pp-rail {{
        display: flex; gap: 12px; overflow-x: auto; scroll-behavior: smooth;
        padding: 6px 44px;  /* 양옆 화살표 공간 */
      }}
      .pp-rail::-webkit-scrollbar {{ height: 8px; }}
      .pp-rail::-webkit-scrollbar-thumb {{ background: #ddd; border-radius: 999px; }}
      .pp-card {{
        min-width: 300px; max-width: 300px;
        background: #fff; border:1px solid #eee; border-radius:14px;
        box-shadow:0 4px 14px rgba(17,24,39,.06); overflow:hidden; flex: 0 0 auto;
      }}
      .pp-thumb img {{
        width: 100%; height: 180px; object-fit: cover; display:block;
      }}
      .pp-body {{ padding: 12px; }}
      .pp-title {{ font-weight: 700; margin-bottom: 6px; }}
      .pp-meta  {{ font-size: 12px; color: #6b7280; }}
      .pp-nav {{
        position: absolute; top: 50%; transform: translateY(-50%);
        width: 36px; height: 36px; border-radius: 50%;
        border:1px solid #eee; background:#fff;
        box-shadow:0 2px 8px rgba(0,0,0,.08);
        display:flex; align-items:center; justify-content:center;
        cursor: pointer; user-select: none;
      }}
      .pp-nav:hover {{ filter: brightness(1.02); }}
      .pp-left  {{ left: 4px; }}
      .pp-right {{ right: 4px; }}
    </style>

    <div class="pp-wrap">
      <div id="pp-left"  class="pp-nav pp-left">◀</div>
      <div id="pp-rail"  class="pp-rail">
        {''.join(cards_html)}
      </div>
      <div id="pp-right" class="pp-nav pp-right">▶</div>
    </div>

    <script>
      const rail  = document.getElementById('pp-rail');
      const left  = document.getElementById('pp-left');
      const right = document.getElementById('pp-right');
      const step = Math.max(260, Math.floor(rail.clientWidth * 0.9));

      left.onclick  = () => rail.scrollBy({{ left: -step, behavior: 'smooth' }});
      right.onclick = () => rail.scrollBy({{ left:  step, behavior: 'smooth' }});
    </script>
    """
    st.markdown('<div class="row-title"><h3>✅ 모범음식점 리스트</h3></div>', unsafe_allow_html=True)
    components.html(html_block, height=300, scrolling=False)

#약식카드용 DF에서 행 찾기
def _get_row_by_name(name: str, df: pd.DataFrame):
    # 정확 매칭
    try:
        return df.loc[df["name"].astype(str).str.strip() == name].iloc[0].to_dict()
    except Exception:
        pass
    # 느슨한 매칭(괄호/공백 차이 등)
    m = df["name"].astype(str).str.contains(name, regex=False, na=False)
    if m.any():
        return df.loc[m].iloc[0].to_dict()
    # DF에 없으면 DB에서 보루 조회
    try:
        conn = sqlite3.connect("reviews.db"); conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT store_name AS name, address AS store_address, lat, lng,
                   img1 AS store_image
            FROM stores
            WHERE store_name = ?
            LIMIT 1
        """, (name,))
        r = cur.fetchone(); conn.close()
        if r: return dict(r)
    except Exception:
        pass
    return None

def render_mobile_tag_chips(primary_color: str, tags_src: list[str]):
    tags = [t.lstrip("#") for t in tags_src]
    pills = [f'<button class="pp-chip" data-kw="근처 {html.escape(kw)}">#{html.escape(kw)}</button>' for kw in tags]
    rows = (len(tags)+1)//2
    height_px = min(rows*46 + 14, 460)  # 적당히 늘어나는 높이

    components.html(f"""
    <style>
      .pp-chip-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0,1fr)); /* 모바일 2열 고정 */
        gap: 8px;
        width: 100%;
      }}
      .pp-chip {{
        width: 100%;
        height: 36px;                 /* 컴팩트 높이 */
        padding: 6px 8px;             /* 좌우 패딩 슬림 */
        border-radius: 999px;
        border: 1px solid rgba(255,107,53,.35);
        background: linear-gradient(180deg,#FFF8F2 0%, #FFF3EA 100%);
        color: {primary_color};
        font-weight: 700;
        font-size: 13px;
        line-height: 1;
        box-shadow: 0 2px 8px rgba(255,107,53,.10);
        transition: transform .08s ease, box-shadow .15s ease, filter .15s ease;
      }}
      .pp-chip:hover {{ filter: brightness(1.02); box-shadow: 0 4px 12px rgba(255,107,53,.12); }}
      .pp-chip:active {{ transform: translateY(1px); }}
    </style>

    <div class="pp-chip-grid" id="pp-chip-grid">
      {''.join(pills)}
    </div>

    <script>
      (function(){{
        var grid = document.getElementById('pp-chip-grid');
        if(!grid) return;
        grid.addEventListener('click', function(e){{
          var btn = e.target.closest('.pp-chip');
          if(!btn) return;
          var kw = btn.getAttribute('data-kw');
          const url = new URL(window.parent.location);
          url.searchParams.set('kw', kw);
          window.parent.history.replaceState(null,'',url);
          window.parent.location.reload();
        }});
      }})();
    </script>
    """, height=height_px, scrolling=True)
#메인
#위치 확보
ensure_browser_geolocation()
qp = st.query_params
if "ulat" in qp and "ulon" in qp:
    user_lat = float(qp["ulat"])
    user_lon = float(qp["ulon"])
else:
    user_lat = JEONGJA_LAT
    user_lon = JEONGJA_LON

# 사용자 좌표 우선 기준
st.session_state.setdefault("user_lat", user_lat)
st.session_state.setdefault("user_lon", user_lon)
BASE_LAT = st.session_state.get("user_lat", user_lat)
BASE_LON = st.session_state.get("user_lon", user_lon)
geo = latlontest.get_gu_dong(BASE_LAT, BASE_LON)


st.markdown(
    f"""
    <style>
    /* Streamlit 배경을 투명하게 만드는 대신, 기본 테마를 사용하도록 변경 */
    /* .stApp, .main, .block-container, [data-testid="stAppViewContainer"], [data-testid="stApp"] {{
        background: transparent !important;
        background-color: transparent !important;
    }} */

    /* 기존 코드에서 주황색 배경 설정 부분은 유지 */
    .hero {{ 
        background: linear-gradient(180deg, {PRIMARY} 0%, #ff9559 100%); 
        color:white; 
        padding:26px; 
        border-radius:14px; 
    }}

    /* ⭐⭐⭐ 다크/라이트 모드에 따른 텍스트 색상 규칙은 유지 ⭐⭐⭐ */
    [data-theme="dark"] p,
    [data-theme="dark"] ul,
    [data-theme="dark"] ol,
    [data-theme="dark"] li,
    [data-theme="dark"] div[class*="stMarkdownContainer"] *,
    [data-theme="dark"] [data-testid="stText"] {{
        color: white !important;
    }}

    [data-theme="light"] p,
    [data-theme="light"] ul,
    [data-theme="light"] ol,
    [data-theme="light"] li,
    [data-theme="light"] div[class*="stMarkdownContainer"] *,
    [data-theme="light"] [data-testid="stText"] {{
        color: #333 !important;
    }}

    /* 나머지 CSS 코드는 그대로 유지 */

    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown("""
<style>
/* 모바일 여백 줄이기 */
@media (max-width: 820px){
  .main [data-testid="block-container"]{
    padding-left: 12px !important;
    padding-right: 12px !important;
    max-width: 100% !important;
  }
  /* 히어로 폰트 축소 */
  .hero h3{ font-size: 22px !important; }
  .hero p { font-size: 16px !important; }

  /* 카드 내 텍스트/제목 축소 */
  .card-body{ font-size: 13px !important; }
  .card-body h4{ font-size: 16px !important; margin: 0 0 4px 0 !important; }

  /* 키워드 버튼(필) 더 촘촘하게 */
  .stButton > button[kind="secondary"]{
    height: 30px !important;
    line-height: 30px !important;
    font-size: 12px !important;
    min-width: 88px !important;
    width: 88px !important;
  }
}
</style>
""", unsafe_allow_html=True)
# JavaScript: 테마 감지 및 data-theme 설정 (이 코드는 그대로 유지)
st.markdown(
    """
    <script>
    document.addEventListener("DOMContentLoaded", function() {
        const isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');

        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        });
    });
    </script>
    """,
    unsafe_allow_html=True,
)

# ---------------------- 상단 네비 (250907 수정) -------------
left, right = st.columns([1, 1])

with left:
    st.markdown(
        """
        <a href="/" target="_self" style="text-decoration:none; color:inherit; font-weight:800; font-size:20px;">
          📍 PickPlace
        </a>
        """,
        unsafe_allow_html=True
    )

with right:
    st.markdown(
        f"""
        <div style="display:flex; justify-content:flex-end; gap:10px; align-items:center;">
          <button id="btn-open-loc" class="loc-btn" style="
            cursor:pointer; border:1px solid {PRIMARY}; padding:6px 10px; border-radius:10px;
            color:{PRIMARY}; background:#FDF6EC; font-weight:700;"
            onclick="(function(){{
              const url = new URL(window.location);
              url.searchParams.set('open_loc','dialog');
              window.history.replaceState(null,'',url);
              window.location.reload();
            }})()"
          >
            정확한 위치 설정
          </button>
          <span style="font-size:20px;">🔔</span>
          <span style="font-size:20px;">👤</span>
        </div>
        """,
        unsafe_allow_html=True
    )
if st.session_state.get("show_loc_dialog", False):
    @st.dialog("📍 정확한 위치 설정", width="large")
    def _dlg():
        render_center_picker_dialog(
            BASE_LAT=st.session_state.get("user_lat", BASE_LAT),
            BASE_LON=st.session_state.get("user_lon", BASE_LON),
        )
    _dlg()
# 모달 열기 플래그
if "show_loc_dialog" not in st.session_state:
    st.session_state["show_loc_dialog"] = False
if "open_loc" in st.query_params:
    st.session_state["show_loc_dialog"] = True
    q = dict(st.query_params)
    q.pop("open_loc", None)
    st.query_params.clear()
    st.query_params.update(q)

# ---------------------- 히어로 ----------------------
gu = geo['gu']
dong = geo['dong']
st.markdown(f'''
<div class="hero">
  <h3 style="margin:0 0 10px 0; font-size:32px;">현위치 : {gu} {dong}</h3>
  <p style="font-size:24px; opacity:0.9;">오늘은 어떤 맛집을 찾고 계신가요?</p>
</div>
''', unsafe_allow_html=True)

# ---------------------- 검색 폼 + 추천 키워드 ----------------------
# 쿼리파라미터 처리
qp = st.query_params
if "kw" in qp:
    v = qp["kw"]
    st.session_state["kw_input"] = v
    st.session_state["search_kw"] = v
    st.session_state["do_search"] = True

#키워드 입력칸 + 검색 버튼
with st.form("search_form", clear_on_submit=False):
    c1, c2 = st.columns([8.6, 1.4])

    with c1:
        kw_current = st.text_input(
            " ",
            key="kw_input",
            placeholder="지역, 음식 종류, 식당명으로 검색해보세요",
            label_visibility="collapsed",
        )

    in_progress = bool(st.session_state.get("search_in_progress"))
    btn_label   = "⏹ 정지" if in_progress else "🔎 검색"

    with c2:
        submit = st.form_submit_button(btn_label, type="primary", use_container_width=True)

    if submit:
        if in_progress:
            # 정지: 현재 검색 무효화 + 즉시 UI 갱신
            st.session_state["do_search"] = False
            st.session_state["search_in_progress"] = False
            st.session_state["search_token"] = st.session_state.get("search_token", 0) + 1
            st.rerun()  # ← 여기 중요
        else:
            kw = (kw_current or "").strip()
            if not kw:
                # 키워드 비었으면 액션 없음 (비활성화 대신 no-op)
                pass
            else:
                if len(kw) <= 3 and not kw.startswith("근처 "):
                    kw = f"근처 {kw}"
                st.session_state["search_kw"] = kw
                st.session_state["do_search"] = True
                st.session_state["search_in_progress"] = True
                st.session_state["search_token"] = st.session_state.get("search_token", 0) + 1
                st.rerun()

# 검색 버튼 CSS
st.markdown(f"""
<style>
.stButton > button[kind="primary"] {{
  background: #FDF6EC !important;
  color: {PRIMARY} !important;
  border: 1px solid {PRIMARY} !important;
  border-radius: 10px;
  padding: 10px 14px;
  font-weight: 700;
  letter-spacing: .2px;
  box-shadow: 0 4px 12px rgba(255,107,53,.18);
  transition: transform .05s ease, box-shadow .15s ease, filter .15s ease;
}}

.stButton > button[kind="primary"]:hover {{
  filter: brightness(1.02);
  box-shadow: 0 6px 18px rgba(255,107,53,.25);
  transform: translateY(-1px);
}}

.stButton > button[kind="primary"]:active {{
  transform: translateY(0);
  filter: brightness(.98);
}}

.stButton > button[kind="primary"]:focus {{
  outline: none;
  box-shadow: 0 0 0 3px rgba(255,107,53,.25), 0 4px 12px rgba(255,107,53,.18);
}}

.stButton > button[kind="primary"]:disabled {{
  opacity: .6;
  cursor: not-allowed;
}}
</style>
""", unsafe_allow_html=True)

#검색 중
if st.session_state.get("search_in_progress") and st.session_state.get("search_kw"):
    interaction_html = f"""
    <div class="interaction-msg" style="height:20px;margin:10px 0;font-size:18px;color:{PRIMARY};position:relative;">
        <span>검색 결과를 AI가 평가 중입니다...</span>
        <span>리뷰를 분석하고 있어요...</span>
        <span>조금만 기다려 주세요 😊</span>
    </div>
    <style>
    .interaction-msg span {{
        position: absolute;
        left: 0;
        top: 0;
        opacity: 0;
        animation: rotate-msg 12s infinite;
    }}
    .interaction-msg span:nth-child(1) {{ animation-delay: 0s; }}
    .interaction-msg span:nth-child(2) {{ animation-delay: 4s; }}
    .interaction-msg span:nth-child(3) {{ animation-delay: 8s; }}
    @keyframes rotate-msg {{
        0%   {{ opacity: 1; }}
        33%  {{ opacity: 1; }}
        33.01% {{ opacity: 0; }}
        100% {{ opacity: 0; }}
    }}
    </style>
    """
    st.markdown(interaction_html, unsafe_allow_html=True)

#태그 버튼
st.markdown('<div class="row-title"><h3>📌 키워드 선택</h3></div>', unsafe_allow_html=True)
with st.expander("OPEN/CLOSE", expanded=False):
    if st.session_state.get("is_mobile"):
        # ✅ 모바일: 예쁜 칩 2열
        render_mobile_tag_chips(PRIMARY, TAGS)
    else:
        # ✅ 데스크톱: 지금 쓰던 8개씩 가로 → 2행
        for row in chunk(TAGS, 8):
            cols = st.columns(8, gap="small")
            for col, raw_kw in zip(cols, row):
                with col:
                    kw = raw_kw.lstrip("#")
                    st.button(
                        kw,
                        key=f"pill_{kw}",
                        type="secondary",
                        use_container_width=True,
                        on_click=_apply_tag,
                        args=(f"근처 {kw}",)
                    )

# 태그 버튼 CSS
st.markdown(f"""
<style>
:root {{ --primary: {PRIMARY}; }}

.stButton > button[kind="secondary"] {{
  display: inline-block;
  padding: 5px 10px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  color: {PRIMARY} !important;
  background: #FDF6EC;
  border: 1px solid #FF6B35;
  border-radius: 999px;
  box-shadow: none;
  min-height: 26px;
  cursor: pointer;
  text-align: center;
  transition: transform .06s ease, box-shadow .15s ease, border-color .15s ease, background .15s ease;
}}
.stButton > button[kind="secondary"]:hover {{
  background: #FFF6EF;
  border-color: {PRIMARY};
  box-shadow: 0 4px 14px rgba(0,0,0,0.06);
  transform: translateY(-1px);
}}
.stButton > button[kind="secondary"]:focus {{
  outline: none;
  box-shadow: 0 0 0 3px rgba(255,107,53,0.20);
}}
</style>
""", unsafe_allow_html=True)

search_kw = st.session_state.get("search_kw", "")
run_token = st.session_state.get("search_token", 0)

# ✅ 검색 실행 (명시적으로 do_search가 True일 때만)
if st.session_state.get("do_search") and search_kw:
    with st.spinner("Searching..."):
        results, summaries, real_distance = fetch_results_and_summaries(
            search_kw, lat=BASE_LAT, lon=BASE_LON, query=search_kw
        )

    # 사용자가 중간에 '정지'를 눌렀거나, 새로운 검색이 시작되었다면 토큰 불일치 → 결과 폐기
    if run_token != st.session_state.get("search_token", 0) or not st.session_state.get("do_search", False):
        results, summaries, real_distance = {}, {}, {}
        st.session_state["search_in_progress"] = False
        st.session_state["do_search"] = False
        st.info("검색이 취소되었습니다.")
    else:
        # 정상 종료
        st.session_state["search_in_progress"] = False
else:
    results, summaries, real_distance = {}, {}, {}

#데이터 프레임 생성
rows = []
for store_name, info in results.items():
    lat = float(info["lat"])
    lng = float(info["lng"])
    addr = info["address"]
    imgs = info["store_image"]
    kakao_cnt  = len(info["kakao"]["reviews"])
    google_cnt = len(info["google"]["reviews"])
    naver_cnt  = len(info["naver"]["reviews"])
    review_count = kakao_cnt + google_cnt + naver_cnt

    one_liner = summaries.get(store_name, {}).get("one_liner", "")
    rating = summaries.get(store_name, {}).get("rating", 4.2)
    complain = summaries.get(store_name, {}).get("complain", [])

    # 거리 딕셔너리에 키가 없을 수 있으므로 get 사용
    distance_m = (real_distance or {}).get(store_name)
    walk_min   = int(round(distance_m / 80)) if isinstance(distance_m, (int, float)) else None

    rows.append({
        "name": store_name,
        "lat": lat,
        "lon": lng,
        "store_address": addr,
        "store_image": imgs,
        "review_count": review_count,
        "oneliner": one_liner,
        "rating": rating,
        "complain": complain,
        "distance_m": distance_m,
        "walk_min": walk_min,
    })

columns = [
    "name", "lat", "lon", "store_address",
    "store_image", "review_count", "oneliner", "rating", "complain", "distance_m", "walk_min"
]
data = pd.DataFrame(rows, columns=columns)

# 결과 카드
if st.session_state.get("do_search", False):

    st.markdown('<div class="row-title"><h3>검색 결과</h3></div>', unsafe_allow_html=True)

    n_cols = 1 if st.session_state.get("is_mobile") else 2
    rows_n = (len(data) + n_cols - 1) // n_cols
    for i in range(rows_n):
        cols = st.columns(n_cols)
        for j in range(n_cols):
            idx = i * n_cols + j
            if idx >= len(data):
                continue

            # 상원님 코드 추가
            r = data.iloc[idx]
            name = r.get("name", "")
            rcnt = int(r.get("review_count") or 0)
            addr = r.get("store_address", "주소 정보 없음")
            one_liner = r.get("oneliner") or "요약이 아직 없어요."
            rating_value = r.get("rating") if pd.notnull(r.get("rating")) else 4.2
            complain_raw = r.get("complain")

            if isinstance(complain_raw, list):
                complain_list = complain_raw
            elif isinstance(complain_raw, str):
                try:
                    import ast

                    v = ast.literal_eval(complain_raw)
                    complain_list = v if isinstance(v, list) else [complain_raw]
                except Exception:
                    complain_list = [complain_raw]
            else:
                complain_list = []

            star_html, rating_str = make_star_html(rating_value)

            if complain_list:
                complain_html = "<ul style='margin:6px 0 0 18px; padding:0; font-size:12px;'>" + \
                                "".join(f"<li style='color:white !important;'>{html.escape(str(c))}</li>" for c in
                                        complain_list[:3]) + \
                                "</ul>"
            else:
                complain_html = "<div class='meta' style='margin-top:4px; color:white !important;'>AI 요약 불편한 점 없음</div>"

            # 거리/도보
            d, w = r.get("distance_m"), r.get("walk_min")
            if pd.notnull(d) and pd.notnull(w):
                try:
                    dist_text = f"직선 {int(d)}m · 도보 {int(w)}분"
                except Exception:
                    dist_text = "위치 정보 없음"
            else:
                dist_text = "위치 정보 없음"

            # 이미지 3장
            rep, sub1, sub2 = take_three_images(r.get("store_image"))

            with cols[j]:
                st.markdown('<div class="card">', unsafe_allow_html=True)

                # 대표 1 + 보조 2 (B 레이아웃)
                img_html_parts = ['<div style="display:flex; gap:6px; padding:8px;">']
                left = f'''
                        <div style="flex:2;">
                          {f'<img src="{rep}" alt="대표이미지" style="width:100%; height:200px; object-fit:cover; border-radius:6px;">' if rep else ''}
                        </div>'''
                right = f'''
                        <div style="flex:1; display:flex; flex-direction:column; gap:6px;">
                          {f'<img src="{sub1}" alt="보조1" style="width:100%; height:97px; object-fit:cover; border-radius:6px;">' if sub1 else '<div style="width:100%; height:97px;"></div>'}
                          {f'<img src="{sub2}" alt="보조2" style="width:100%; height:97px; object-fit:cover; border-radius:6px;">' if sub2 else '<div style="width:100%; height:97px;"></div>'}
                        </div>'''
                img_html_parts += [left, right, '</div>']
                st.markdown("".join(img_html_parts), unsafe_allow_html=True)

                # 라벨 + 버튼 같은 자리에 배치
                c1, c2 = st.columns(
                    [9, 1.4])  # Left column wider for body (8 parts), right narrower for button (2 parts)

                with c1:  # This is the left/wider column: place the card body here
                    st.markdown(f"""
                        <div class="card-body">
                          <h4>{name}</h4>
                          <div class="rating-info meta" style="margin-bottom:6px;">AI 분석 결과 {rating_str}</div>
                          <div class="stars" style="margin:4px 0;">{star_html}</div>

                          <div style="font-size:12px; color:#333; background:#f9f9f9; padding:8px;
                                      border-radius:6px; margin:6px 0;">
                             “{html.escape(one_liner)}”
                          </div>

                          <div class="meta" style="margin:8px 0 6px;">
                             <span>📍 {dist_text}</span>
                          </div>
                          <div class="meta" style="margin-top:2px;">📍 {addr}</div>

                          <div style="margin-top:8px;">
                            <div class="meta" style="margin-bottom:4px;">AI 분석 결과 불편한 점</div>
                            {complain_html}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                # 리뷰 버튼 스타일 정의
                st.markdown("""
                    <style>
                    .review-btn {
                        position: relative;
                        float: right;
                        background: rgba(255, 255, 255, 0.85); /* 더 밝고 선명한 반투명 흰색 */
                        box-shadow: 0 2px 8px rgba(80, 80, 80, 0.10); /* 잔잔한 그림자 */
                        backdrop-filter: blur(5px);
                        padding: 6px 14px; /* 버튼이 더 넓게, 글자와 여백 조정 */
                        border-radius: 16px; /* 더 둥글게 */
                        border: 1px solid rgba(120,120,120,0.13); /* 얇고 부드러운 테두리 */
                        font-weight: 500; /* 좀 더 진한 글씨 */
                        color: #333 !important; /* 검은색에 가깝게 */
                        transition: background 0.2s, box-shadow 0.2s;
                        cursor: pointer;
                        font-size: 15px;
                    }
                    .review-btn:hover {
                        background: rgba(230, 230, 230, 0.95);
                        box-shadow: 0 4px 16px rgba(80,80,80,0.12);
                    }
                    </style>
                    """, unsafe_allow_html=True)

                with c2:
                    st.markdown('<div style="display: flex; justify-content: flex-end;">', unsafe_allow_html=True)
                    clicked = st.button(f"리뷰 {rcnt}개", key=f"reviews_btn_{name}", help="리뷰 상세 보기")
                    st.markdown('</div>', unsafe_allow_html=True)

                    # 버튼 클릭 시 리뷰 열기
                    if clicked:
                        st.session_state[f"show_reviews_{name}"] = not st.session_state.get(f"show_reviews_{name}",
                                                                                            False)

                # 리뷰 출력
                if st.session_state.get(f"show_reviews_{name}", False):
                    st.markdown(f"#### 📝 {name} 리뷰 ({rcnt}개)")
                    conn = sqlite3.connect("reviews.db")
                    cur = conn.cursor()
                    cur.execute("""
                            SELECT r.review
                            FROM reviews r
                            JOIN stores s ON r.store_id = s.id
                            WHERE s.store_name = ?
                            ORDER BY r.last_seen DESC
                        """, (name,))
                    rows = cur.fetchall()
                    conn.close()

                    if rows:
                        for (rv,) in rows:
                            st.markdown(f"- {rv}")
                    else:
                        st.info("저장된 리뷰가 없습니다.")

render_good_shop_carousel(GOOD_SHOPS)

#홈페이지 지도
if not st.session_state.get("do_search", False):
    m_store = folium.Map(location=[BASE_LAT, BASE_LON], zoom_start=15)

    conn = sqlite3.connect("reviews.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT store_name, address, lat, lng, img1
        FROM stores
    """)
    rows_info = cur.fetchall()
    conn.close()

    marker_info = []
    for row in rows_info:
        marker_info.append({
            "name": row["store_name"],
            "store_address": row["address"],
            "lat": row["lat"],
            "lon": row["lng"],
            "store_image": row["img1"]
        })
    df = pd.DataFrame(marker_info)

    for c in ["lat", "lon"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    pts = df.dropna(subset=["lat", "lon"])

    m_store = folium.Map(location=[BASE_LAT, BASE_LON], zoom_start=15)

#검색시 지도
else:
    st.markdown('<div class="row-title"><h3>🗺 지도에서 보기</h3></div>', unsafe_allow_html=True)
    m_store = folium.Map(location=[BASE_LAT, BASE_LON], zoom_start=15)
    df = data if not data.empty else data

# 숫자형 변환 + 좌표 없는 행 제거
    for c in ["lat", "lon"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    pts = df.dropna(subset=["lat", "lon"])

# 지도 중심 재설정
    if not pts.empty:
        center_lat = float(pts["lat"].mean())
        center_lon = float(pts["lon"].mean())
        m_store = folium.Map(location=[center_lat, center_lon], zoom_start=15)
    else:
        m_store = folium.Map(location=[BASE_LAT, BASE_LON], zoom_start=15)

cluster = MarkerCluster(
    icon_create_function=f"""
        function(cluster) {{
            var count = cluster.getChildCount();
            return new L.DivIcon({{
                html: '<div style="background:{PRIMARY};border-radius:50%;width:40px;height:40px;display:flex;align-items:center;justify-content:center;color:white;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,0.25);border:2px solid rgba(255,255,255,0.9);">' + count + '</div>',
                className: 'custom-cluster',
                iconSize: [40, 40]
            }});
        }}
    """
).add_to(m_store)

# 3) 마커 + 팝업 HTML
for _, r in pts.iterrows():
    name = r.get("name", "")
    address = r.get("store_address", "")

    # 거리/도보 표기
    dist_txt = None
    d, w = r.get("distance_m"), r.get("walk_min")
    if pd.notnull(d) and pd.notnull(w):
        try:
            dist_txt = f"직선 {int(d)}m · 도보 {int(w)}분"
        except Exception:
            dist_txt = None

    # 이미지 1장 (있으면)
    img_url = first_image(r.get("store_image"))

    # 팝업 HTML 조합 (필드가 있으면만 렌더)
    parts = [
        f'<h4 style="margin:0; font-size:15px;">{html.escape(str(name))}</h4>',
        f'<div style="font-size:12px; color:#333; margin-bottom:4px;"> {html.escape(str(address))}</div>'
    ]
    if dist_txt:
        parts.append(f'<div style="font-size:12px; color:#333; margin-bottom:4px;">{dist_txt}</div>')
    if img_url:
        parts.append(
            f'<img src="{img_url}" style="width:100%; height:120px; object-fit:cover; border-radius:8px; margin-bottom:6px;" />')

    popup_html = f'<div style="width:260px; font-family:Arial, sans-serif;">' + "".join(parts) + "</div>"

    folium.Marker(
        location=[float(r["lat"]), float(r["lon"])],  # ✅ [위도, 경도] 순서
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=name,
        icon = folium.Icon(color = "blue", icon='flag')
    ).add_to(cluster)

# 범위 자동 맞춤
if st.session_state.get("do_search", False) and not pts.empty:
    m_store.fit_bounds(
        [[pts["lat"].min(), pts["lon"].min()], [pts["lat"].max(), pts["lon"].max()]],
        padding=(20, 20)
    )

map_col, card_col = st.columns([7, 5], gap="large")

with map_col:
    map_state = st_folium(m_store, key="map_store_view", height=map_height, use_container_width=True)

# === 마커 클릭 → 매장명 추출 ===
clicked_name = None
if isinstance(map_state, dict):
    # 1) 마커 tooltip이 곧 매장명
    tt = map_state.get("last_object_clicked_tooltip")
    if isinstance(tt, str) and tt.strip():
        clicked_name = tt.strip()

    # 2) (보험) 팝업 HTML에서 <h4>...</h4> 추출
    if not clicked_name:
        pop = map_state.get("last_object_clicked_popup")
        if isinstance(pop, str) and pop:
            import re, html as _html
            m = re.search(r"<h4[^>]*>(.*?)</h4>", pop, flags=re.S)
            if m:
                clicked_name = _html.unescape(m.group(1)).strip()

# 상태 업데이트 (선택이 잡혔을 때만)
if clicked_name:
    st.session_state["sel"] = clicked_name

with card_col:
    st.markdown("### 🔎 매장 요약")
    sel = (st.session_state.get("sel") or "").strip()

    if not sel:
        st.info("지도의 마커를 클릭하면 여기에서 약식 카드가 보여요.")
    else:
        row = _get_row_by_name(sel, df)
        if row:
            render_compact_store_card(row)
        else:
            st.warning(f"선택한 매장({sel})를 현재 목록에서 찾지 못했습니다.")

# ---------------------- 푸터 ----------------------
st.markdown("---")

st.markdown("### 📍 PickPlace")
st.caption("AI 기반 맛집 길라잡이 · 신뢰할 수 있는 정보로 찾아드려요")

st.markdown(f"""
<div class="footer">
  <p>© {datetime.now().year} PickPlace. All rights reserved.</p>
</div>
""", unsafe_allow_html=True)

# ======================= [MOD] CSS-only fixes injected =======================
st.markdown("""
<style>
/* [MOD] Centered layout with side gutters like ChatGPT */
.main [data-testid="block-container"]{
  max-width: 980px !important;          /* content width; adjust 880~1200px as you like */
  margin-left: auto !important;
  margin-right: auto !important;
  padding-left: 100px !important;       /* required: 100px left gutter */
  padding-right: 100px !important;      /* required: 100px right gutter */
}
@media (max-width: 1100px){
  .main [data-testid="block-container"]{
    padding-left: 24px !important;
    padding-right: 24px !important;
  }
}

@media (min-width: 821px){
  /* 데스크톱에서만 Streamlit 버튼 고정폭을 쓰고 싶다면 여기에 */
  .stButton > button[kind="secondary"]{
    display:inline-flex !important;
    align-items:center; justify-content:center;
    width:104px !important; min-width:104px !important;
    height:34px !important; line-height:34px !important;
    padding:0 10px !important; margin:2px 6px !important;
    white-space:nowrap !important;
  }
  .stButton{ display:inline-block !important; margin:0 !important; }
}

/* Ensure the wrapper itself doesn't force full width */
.stButton{ display: inline-block !important; margin: 0 !important; }
</style>
""", unsafe_allow_html=True)
# ===========================================================================
components.html("""
<script>
(function(){
  const btn = window.parent.document.getElementById('btn-open-loc');
  if (!btn) return;
  btn.addEventListener('click', function(e){
    e.preventDefault();
    const url = new URL(window.parent.location);
    url.searchParams.set('open_loc','dialog');
    window.parent.history.replaceState(null, '', url);
    window.parent.location.reload();
  });
})();
</script>
""", height=0)

components.html("""
<script>
(function(){
  try{
    var isMobile = window.innerWidth < 500;     // breakpoint
    var want = isMobile ? '1' : '0';
    var url = new URL(window.parent.location);
    var cur = url.searchParams.get('m');
    if (cur !== want){
      url.searchParams.set('m', want);
      window.parent.history.replaceState(null,'',url);
      window.parent.location.reload();
    }
  }catch(e){}
})();
</script>
""", height=0)
