# f_multi_main_tool.py
# -*- coding: utf-8 -*-
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 외부 도구 임포트 ===
import f_multi_kakao_tool
import f_multi_google_tool
import f_multi_naver_tool
import search_store  # ✅ 추가: 매장 이름/주소 뽑는 용도
import os
import csv
# -------------------------
# 설정
# -------------------------
MAX_WORKERS = 10  # 동시 크롤링 스레드 수
# print(data)
# -------------------------
# 유틸
# -------------------------
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

def save_results_to_csv_unique(results: dict, filename: str = "reviews.csv"):
    existing = set()
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # 헤더 건너뛰기
            for row in reader:
                if len(row) >= 5:  # ✅ store_image 포함
                    store, addr, img, src, review = row[:5]
                    existing.add((store.strip(), src.strip(), review.strip()))

    with open(filename, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)

        if os.path.getsize(filename) == 0:
            writer.writerow(["store_name", "store_address", "store_image", "source", "review"])

        new_count = 0
        for store, data in results.items():
            address = data.get("address", "-")
            image = data.get("store_image", "-")  # ✅ 카카오에서 들어온 이미지
            for src in ("kakao", "google", "naver"):
                reviews = data.get(src, {}).get("reviews", [])
                for review in reviews:
                    key = (store.strip(), src.strip(), review.strip())
                    if key not in existing:
                        writer.writerow([store, address, image, src, review])
                        existing.add(key)
                        new_count += 1

    print(f"[INFO] CSV 저장 완료: {filename}, 새로 추가된 행 {new_count}개")


# -------------------------
# search_store로 이름/주소만 빠르게 수집
# -------------------------
def get_store_list_from_search_store(keyword: str, top_n: int = 5, headless: bool = True):
    """
    search_store.run_multi(keyword) -> {"매장명": "주소"} 형태를 기대
    반환: [(매장명, 주소), ...]
    """
    try:
        out = search_store.run_multi(keyword, top_n=top_n, headless=headless)
        if isinstance(out, dict):
            return list(out.items())[:top_n]
    except Exception as e:
        print(f"[SEARCH_STORE][ERR] {e}")
    return []

# -------------------------
# 개별 소스 러너 (병렬 대상)
# -------------------------
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
    store_pairs = get_store_list_from_search_store(keyword, top_n=top_n, headless=headless)
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

            # kakao / google / naver 3원 병렬
            # parts_kw = keyword.split()
            # parts_nm = store_name.split()
            # n_keyword = (parts_kw[0] if parts_kw else "") + " " + (parts_nm[0] if parts_nm else store_name)

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

# -------------------------
# 보기 좋게 출력 (옵션)
# -------------------------
def pretty_print(results: dict):
    for store, data in results.items():
        addr = data.get("address") or "-"
        print(f"\n=== {store} ===")
        print(f"주소: {addr}")
        for src in ("kakao", "google", "naver"):
            reviews = data.get(src, {}).get("reviews", [])
            print(f"[{src}] {len(reviews)}개")
            for r in reviews[:3]:
                preview = r[:120].replace("\n", " ")
                ellipsis = "..." if len(r) > 120 else ""
                print(f" - {preview}{ellipsis}")

if __name__ == "__main__":
    kw = "미담 정자"
    out = collect_all_reviews_parallel(kw, top_n=1, max_reviews=10, headless=True)
    print(out)
    # save_results_to_csv_unique(all_res, "reviews.csv")
    # pretty_print(out)
