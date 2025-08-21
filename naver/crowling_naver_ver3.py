# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException,
    StaleElementReferenceException
)
import os, re, time
from datetime import datetime

# 🔗 정자동 식당 검색 URL
SEARCH_URL = "https://map.naver.com/p/search/%EC%A0%95%EC%9E%90%EB%8F%99%20%EC%8B%9D%EB%8B%B9?c=14.00,0,0,0,dh"
SAVE_DIR = "saved_pages"

WAIT_LONG = 10
WAIT_SHORT = 8

def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_experimental_option("detach", True)   # 스크립트 끝나도 창 유지
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1300, 950)
    return driver

def wwait(drv, t=WAIT_LONG, poll=0.2):
    return WebDriverWait(drv, t, poll_frequency=poll)

def click_with_retry(drv, by, sel, tries=4, pre_sleep=0.2, post_sleep=0.35, timeout=WAIT_SHORT):
    last_err = None
    for attempt in range(1, tries+1):
        try:
            if pre_sleep: time.sleep(pre_sleep)
            w = wwait(drv, timeout)
            el = w.until(EC.presence_of_element_located((by, sel)))
            el = w.until(EC.visibility_of_element_located((by, sel)))
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            w.until(EC.element_to_be_clickable((by, sel)))
            try:
                ActionChains(drv).move_to_element(el).pause(0.05).click(el).perform()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                drv.execute_script("arguments[0].click();", el)
            if post_sleep: time.sleep(post_sleep)
            return el
        except Exception as e:
            last_err = e
            time.sleep(0.5 + 0.25*attempt)
    raise TimeoutException(f"click_with_retry 실패: {sel} // {last_err}")

def to_search_iframe(drv):
    drv.switch_to.default_content()
    wwait(drv).until(EC.presence_of_element_located((By.ID, "searchIframe")))
    drv.switch_to.frame(drv.find_element(By.ID, "searchIframe"))

def to_entry_iframe(drv):
    drv.switch_to.default_content()
    wwait(drv).until(EC.presence_of_element_located((By.ID, "entryIframe")))
    drv.switch_to.frame(drv.find_element(By.ID, "entryIframe"))
    time.sleep(0.5)

def wait_entry_loaded(drv, timeout=WAIT_LONG):
    w = wwait(drv, timeout)
    try:
        w.until(EC.presence_of_element_located((By.XPATH, "//section[contains(@class,'place_section')]")))
    except TimeoutException:
        time.sleep(0.8)

def wait_reviews_ready(drv, timeout=WAIT_SHORT):
    w = wwait(drv, timeout)
    try:
        w.until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:
        pass
    time.sleep(0.6)

def save_html(drv, label="page"):
    os.makedirs(SAVE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_label = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", label)[:80] or "page"
    path = os.path.join(SAVE_DIR, f"{ts}_{safe_label}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(drv.page_source)
    print(f"[SAVE] {path}")
    return path

def wait_review_container(drv, timeout=20):
    candidates = [
        (By.CSS_SELECTOR, "#_review_list"),
        (By.CSS_SELECTOR, "div[id$='_review_list']"),
        (By.CSS_SELECTOR, "section[class*='place_section'][data-tab='review']"),
        (By.CSS_SELECTOR, "div.place_section_content"),
    ]
    w = wwait(drv, timeout, poll=0.2)
    for by, sel in candidates:
        try:
            el = w.until(EC.presence_of_element_located((by, sel)))
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            return el
        except Exception:
            continue
    raise TimeoutException("리뷰 컨테이너를 찾지 못했습니다")

def save_review_section_html(drv, label="review_section"):
    os.makedirs(SAVE_DIR, exist_ok=True)
    to_entry_iframe(drv)
    el = wait_review_container(drv, timeout=20)
    html = el.get_attribute("outerHTML")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_label = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", label)[:80] or "review_section"
    path = os.path.join(SAVE_DIR, f"{ts}_{safe_label}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[SAVE] 리뷰 섹션 → {path}")
    return path

# --- 검색 리스트 처리 ---
def list_search_items(drv, timeout=WAIT_LONG):
    """검색 iframe에서 가게명 span 리스트를 (이름, locator) 배열로 반환."""
    to_search_iframe(drv)
    w = wwait(drv, timeout)
    w.until(EC.presence_of_all_elements_located((By.XPATH, "//span[contains(@class,'TYaxT')]")))
    spans = drv.find_elements(By.XPATH, "//span[contains(@class,'TYaxT')]")
    items = []
    for idx, el in enumerate(spans):
        try:
            name = el.text.strip()
            if not name:
                continue
            xp = f"(//span[contains(@class,'TYaxT')])[{idx+1}]"
            items.append((name, (By.XPATH, xp)))
        except Exception:
            continue
    if not items:
        raise TimeoutException("검색 결과 아이템을 찾지 못했습니다.")
    return items

def open_reviews_tab_and_sort(drv, tries=4, sort_latest=True):
    """상세에서 리뷰 탭 → (옵션) 최신순 정렬."""
    to_entry_iframe(drv)
    wait_entry_loaded(drv)

    print("[CLICK] 리뷰 탭")
    click_with_retry(
        drv, By.XPATH,
        "//span[contains(@class,'veBoZ') and normalize-space()='리뷰']",
        tries=max(tries, 3), pre_sleep=0.4, post_sleep=0.8, timeout=WAIT_LONG
    )
    wait_reviews_ready(drv)

    if sort_latest:
        print("[CLICK] 리뷰 정렬(최신순)")
        try:
            click_with_retry(
                drv, By.XPATH,
                "//a[@role='option' and contains(@class,'place_btn_option') and normalize-space()='최신순']",
                tries=3, pre_sleep=0.3, post_sleep=0.6, timeout=WAIT_SHORT
            )
        except Exception:
            try:
                click_with_retry(
                    drv, By.XPATH,
                    "//button[contains(@class,'place_section_content')]//span[contains(text(),'정렬')]",
                    tries=2, pre_sleep=0.2, post_sleep=0.4, timeout=WAIT_SHORT
                )
                click_with_retry(
                    drv, By.XPATH,
                    "//a[@role='option' and contains(@class,'place_btn_option') and normalize-space()='최신순']",
                    tries=3, pre_sleep=0.2, post_sleep=0.6, timeout=WAIT_SHORT
                )
            except Exception:
                print("[WARN] 최신순 선택 실패 — 계속 진행")
    return True

def expand_all_reviews(drv, max_clicks=300, scroll_step=500, pause=0.25):
    """
    상세 iframe에서 리뷰 본문 '더보기(rvshowmore)'만 모두 펼침.
    클릭한 버튼은 즉시 DOM에서 제거해 재클릭(접힘) 방지.
    """
    to_entry_iframe(drv)
    total_clicked = 0
    idle_rounds = 0

    while total_clicked < max_clicks and idle_rounds < 10:
        clicked_this_round = 0

        containers = drv.find_elements(By.CSS_SELECTOR, "#_review_list, div[id$='_review_list']")
        scope = containers[0] if containers else drv

        btns = scope.find_elements(By.CSS_SELECTOR, "a[data-pui-click-code='rvshowmore']")
        for b in btns:
            try:
                if not b.is_displayed():
                    continue
                txt = (b.text or "").strip()
                if "접기" in txt:
                    continue

                drv.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                time.sleep(0.05)
                try:
                    ActionChains(drv).move_to_element(b).pause(0.02).click(b).perform()
                except (ElementClickInterceptedException, StaleElementReferenceException):
                    drv.execute_script("arguments[0].click();", b)

                try:
                    drv.execute_script("""
                        if (arguments[0]) {
                            arguments[0].setAttribute('data-expanded-once','1');
                            arguments[0].parentNode && arguments[0].parentNode.removeChild(arguments[0]);
                        }
                    """, b)
                except Exception:
                    pass

                total_clicked += 1
                clicked_this_round += 1
                time.sleep(0.12)
                if total_clicked >= max_clicks:
                    break
            except Exception:
                continue

        if clicked_this_round == 0:
            idle_rounds += 1
            drv.execute_script(f"window.scrollBy(0, {scroll_step});")
            time.sleep(pause)
        else:
            idle_rounds = 0

    print(f"[INFO] 리뷰 더보기 펼침 완료: {total_clicked}회, idle_rounds={idle_rounds}")

# --- 페이지 네비게이션 ---
def goto_search_page(drv, page_no, tries=3):
    """
    검색 iframe에서 페이지 번호 버튼 클릭 (예: <a role="button" class="mBN2s ">2</a>)
    """
    to_search_iframe(drv)
    xp = f"//a[@role='button' and contains(@class,'mBN2s') and normalize-space()='{page_no}']"
    print(f"[PAGE] {page_no}페이지 이동 시도")
    for attempt in range(1, tries+1):
        try:
            click_with_retry(drv, By.XPATH, xp, tries=2, pre_sleep=0.2, post_sleep=0.6, timeout=WAIT_LONG)
            # 새 페이지 결과 로딩 대기
            wwait(drv, WAIT_LONG).until(
                EC.presence_of_all_elements_located((By.XPATH, "//span[contains(@class,'TYaxT')]"))
            )
            time.sleep(0.5)
            print(f"[PAGE] {page_no}페이지 이동 성공")
            return True
        except Exception as e:
            print(f"[WARN] {page_no}페이지 이동 실패 (시도 {attempt}) // {e}")
            time.sleep(1.0)
    return False

from selenium.webdriver.common.keys import Keys

def count_search_items(drv):
    """검색 iframe에서 리스트 항목 개수 반환."""
    to_search_iframe(drv)
    els = drv.find_elements(By.XPATH, "//span[contains(@class,'TYaxT')]")
    return len([e for e in els if (e.text or "").strip()])

def _find_search_list_container(drv):
    """
    검색 iframe 안에서 실제로 스크롤되는 리스트 컨테이너를 최대한 보편적으로 탐색.
    - overflowY가 'auto'/'scroll'이고, 아이템(span.TYaxT)을 포함하는 가장 큰 div를 선택
    """
    to_search_iframe(drv)
    divs = drv.find_elements(By.CSS_SELECTOR, "div")
    candidate = None
    max_area = 0
    for d in divs:
        try:
            has_item = len(d.find_elements(By.XPATH, ".//span[contains(@class,'TYaxT')]")) > 0
            if not has_item:
                continue
            overflow = drv.execute_script("return window.getComputedStyle(arguments[0]).overflowY;", d)
            if overflow not in ("auto", "scroll"):
                continue
            h = d.size.get("height", 0)
            w = d.size.get("width", 0)
            area = h * w
            if area > max_area:
                max_area = area
                candidate = d
        except Exception:
            continue
    return candidate  # 없으면 None 반환

def scroll_search_list_until_stable(
    drv,
    max_tries=80,         # ⬅ 더 깊게: 시도 횟수 증가
    pause=0.45,           # ⬅ 로딩 여유 증가
    stable_needed=4,      # ⬅ 변화 없음을 더 엄격히
    extra_push=True       # ⬅ 키보드/휠 이벤트로 추가 트리거
):
    """
    검색 iframe에서 실제 리스트 컨테이너에 스크롤을 가해
    매장 수가 더 이상 늘어나지 않을 때까지 내려감.
    """
    to_search_iframe(drv)
    container = _find_search_list_container(drv)
    prev_cnt = -1
    stable = 0

    for i in range(max_tries):
        # 현재 개수
        cur_cnt = count_search_items(drv)

        if cur_cnt == prev_cnt:
            stable += 1
        else:
            stable = 0

        if stable >= stable_needed:
            print(f"[SCROLL] 리스트 안정화: {cur_cnt}개 (시도 {i+1})")
            return cur_cnt

        # 마지막 아이템을 기준으로 scrollIntoView (로딩 트리거 가장 확실)
        try:
            items = drv.find_elements(By.XPATH, "//span[contains(@class,'TYaxT')]")
            if items:
                last_el = items[-1]
                drv.execute_script("arguments[0].scrollIntoView({block:'end'});", last_el)
        except Exception:
            pass

        # 리스트 컨테이너에 직접 스크롤 (창이 아니라 컨테이너!)
        try:
            if container:
                drv.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].clientHeight;", container)
        except Exception:
            pass

        # 추가 푸시(선택): 키보드/휠 이벤트로 lazy-load 더 자극
        if extra_push:
            try:
                if container:
                    # 휠 이벤트
                    drv.execute_script("""
                        const el = arguments[0];
                        el.dispatchEvent(new WheelEvent('wheel', {deltaY: el.clientHeight}));
                    """, container)
                else:
                    # 컨테이너를 못 찾은 경우에는 문서에 PageDown
                    body = drv.find_element(By.TAG_NAME, "body")
                    body.send_keys(Keys.PAGE_DOWN)
            except Exception:
                pass

        time.sleep(pause)
        prev_cnt = cur_cnt

    final_cnt = count_search_items(drv)
    print(f"[SCROLL] 최대 시도 도달: {final_cnt}개")
    return final_cnt



# --- 메인 루프 ---
def run_crawl(max_pages=5, per_page_limit=None, sort_latest=True, expand_more=True):
    drv = make_driver()
    drv.get(SEARCH_URL)

    total_processed = 0

    for page in range(1, max_pages + 1):
        ok = goto_search_page(drv, page)
        if not ok:
            print(f"[WARN] {page}페이지로 이동하지 못해 종료합니다.")
            break

        # ✅ 페이지 넘기기 전에 끝까지 스크롤해서 매장 최대 노출
        total_on_page = scroll_search_list_until_stable(drv)
        print(f"[INFO] {page}페이지: 스크롤 후 매장 {total_on_page}개 감지")

        # 이제 리스트를 수집해서 처리
        items = list_search_items(drv)
        print(f"[INFO] {page}페이지: 실제 수집 대상 {len(items)}개")

        processed_this_page = 0
        for idx, (name, locator) in enumerate(items, start=1):
            if per_page_limit and processed_this_page >= per_page_limit:
                break

            to_search_iframe(drv)
            print(f"\n[CLICK] [{page}페이지 #{idx}] 가게 선택: {name}")
            try:
                click_with_retry(drv, locator[0], locator[1], tries=4, pre_sleep=0.2, post_sleep=0.6, timeout=WAIT_LONG)
            except Exception as e:
                print(f"[WARN] 가게 선택 실패: {name} // {e}")
                continue

            try:
                open_reviews_tab_and_sort(drv, tries=4, sort_latest=sort_latest)
                if expand_more:
                    expand_all_reviews(drv, max_clicks=200)
            except Exception as e:
                print(f"[WARN] 리뷰 탭/정렬/더보기 처리 중 문제: {name} // {e}")

            safe_name = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", name)[:60] or f"place_{idx}"
            drv.switch_to.default_content()
            # save_html(drv, f"p{page:02d}_{idx:02d}_{safe_name}_fullpage")
            try:
                save_review_section_html(drv, f"p{page:02d}_{idx:02d}_{safe_name}_reviews")
            except Exception as e:
                print(f"[WARN] 리뷰 섹션 저장 실패: {name} // {e}")

            processed_this_page += 1
            total_processed += 1

        print(f"\n[PAGE DONE] {page}페이지 처리: {processed_this_page}개")

    print(f"\n[DONE] 총 처리 가게 수: {total_processed}개")
    input("브라우저는 열린 상태로 유지됩니다. 종료하려면 Enter...")

if __name__ == "__main__":
    # 1~5페이지, 페이지당 전부 처리, 최신순 정렬 + 더보기 펼치기
    run_crawl(max_pages=5, per_page_limit=None, sort_latest=True, expand_more=True)
