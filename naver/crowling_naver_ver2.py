# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException,
    StaleElementReferenceException, NoSuchElementException
)
import os, re, time
from datetime import datetime

# 🔗 정자동 식당 검색 URL
SEARCH_URL = "https://map.naver.com/p/search/%EC%A0%95%EC%9E%90%EB%8F%99%20%EC%8B%9D%EB%8B%B9?c=14.00,0,0,0,dh"
SAVE_DIR = "saved_pages"

WAIT_LONG = 20
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

# --------- 추가: 검색 리스트에서 다건 반복을 위한 헬퍼들 ---------
def list_search_items(drv, timeout=WAIT_LONG):
    """검색 iframe에서 가게명 span들을 리스트로 반환(텍스트, locator 튜플)."""
    to_search_iframe(drv)
    w = wwait(drv, timeout)
    # 가게명 스팬(리스트 영역). 클래스는 변경될 수 있어 가장 보편 패턴 사용
    w.until(EC.presence_of_all_elements_located((By.XPATH, "//span[contains(@class,'TYaxT')]")))
    spans = drv.find_elements(By.XPATH, "//span[contains(@class,'TYaxT')]")
    items = []
    for idx, el in enumerate(spans):
        try:
            name = el.text.strip()
            if not name:
                continue
            # 인덱스 기반 재탐색 가능한 XPATH
            xp = f"(//span[contains(@class,'TYaxT')])[{idx+1}]"
            items.append((name, (By.XPATH, xp)))
        except Exception:
            continue
    if not items:
        raise TimeoutException("검색 결과 아이템을 찾지 못했습니다.")
    return items

def open_reviews_tab_and_sort(drv, tries=4, sort_latest=True):
    """상세 iframe에서 리뷰 탭 클릭, (옵션) 최신순 선택."""
    to_entry_iframe(drv)
    wait_entry_loaded(drv)

    # 리뷰 탭
    print("[CLICK] 리뷰 탭")
    click_with_retry(
        drv, By.XPATH,
        "//span[contains(@class,'veBoZ') and normalize-space()='리뷰']",
        tries=max(tries, 3), pre_sleep=0.4, post_sleep=0.8, timeout=WAIT_LONG
    )
    wait_reviews_ready(drv)

    # 최신순 정렬(옵션)
    if sort_latest:
        # 드롭다운이 이미 열려있는 경우/아닌 경우 모두 커버: '최신순' 옵션 자체를 직접 클릭
        print("[CLICK] 리뷰 정렬(최신순)")
        try:
            click_with_retry(
                drv, By.XPATH,
                "//a[@role='option' and contains(@class,'place_btn_option') and normalize-space()='최신순']",
                tries=3, pre_sleep=0.3, post_sleep=0.6, timeout=WAIT_SHORT
            )
        except Exception:
            # 드롭다운 토글 누르고 다시 시도
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
                print("[WARN] 최신순 선택 실패 — 계속 진행합니다.")
    return True

def expand_all_reviews(drv, max_clicks=300, scroll_step=500, pause=0.25):
    """
    상세 iframe에서 리뷰 본문 '더보기(rvshowmore)'만 모두 펼침.
    클릭한 버튼은 즉시 DOM에서 제거해 재클릭을 방지한다.
    """
    to_entry_iframe(drv)
    total_clicked = 0
    idle_rounds = 0  # 새 버튼을 못 찾은 라운드 수(종료 조건)

    while total_clicked < max_clicks and idle_rounds < 10:
        clicked_this_round = 0

        # 리뷰 리스트 컨테이너 기준으로만 탐색(사진 더보기 등 오클릭 방지)
        containers = drv.find_elements(By.CSS_SELECTOR, "#_review_list, div[id$='_review_list']")
        scope = containers[0] if containers else drv

        # rvshowmore만 대상으로 (rvshowless/접기 제외)
        btns = scope.find_elements(By.CSS_SELECTOR, "a[data-pui-click-code='rvshowmore']")
        for b in btns:
            try:
                if not b.is_displayed():
                    continue
                # 혹시 텍스트가 '접기'로 바뀐 토글형이라면 패스
                txt = (b.text or "").strip()
                if "접기" in txt:
                    continue

                # 화면 중앙으로 스크롤
                drv.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                time.sleep(0.05)
                try:
                    ActionChains(drv).move_to_element(b).pause(0.02).click(b).perform()
                except (ElementClickInterceptedException, StaleElementReferenceException):
                    drv.execute_script("arguments[0].click();", b)

                # 클릭 직후 같은 버튼을 다시 못 누르게 DOM에서 제거(또는 플래그)
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
            # 더보기 버튼이 잘 안 잡히면 조금씩 내려가며 탐색
            drv.execute_script(f"window.scrollBy(0, {scroll_step});")
            time.sleep(pause)
        else:
            idle_rounds = 0  # 새로 펼친 게 있으면 카운터 초기화

    print(f"[INFO] 리뷰 더보기 펼침 완료: {total_clicked}회, idle_rounds={idle_rounds}")


def run_crawl(max_places=10, sort_latest=True, expand_more=True):
    drv = make_driver()
    drv.get(SEARCH_URL)

    # 검색 리스트 수집
    items = list_search_items(drv)
    print(f"[INFO] 검색 결과 {len(items)}개 발견. 상위 {min(max_places, len(items))}개 처리.")

    processed = 0
    for idx, (name, locator) in enumerate(items, start=1):
        if processed >= max_places:
            break

        # 동일 인덱스로 매번 재탐색(iframe 상태 초기화)
        to_search_iframe(drv)
        print(f"\n[CLICK] ({idx}) 가게 선택: {name}")
        try:
            # 클릭 시 상세 iframe이 갱신됨
            click_with_retry(drv, locator[0], locator[1], tries=4, pre_sleep=0.2, post_sleep=0.6, timeout=WAIT_LONG)
        except Exception as e:
            print(f"[WARN] 가게 선택 실패: {name} // {e}")
            continue

        # 상세에서 리뷰 탭 & 정렬
        try:
            open_reviews_tab_and_sort(drv, tries=4, sort_latest=sort_latest)
        except Exception as e:
            print(f"[WARN] 리뷰 탭/정렬 실패: {name} // {e} (다음 가게로 진행)")
            # 실패해도 다음 가게로 넘어가도록 continue
            # 그래도 이 가게의 전체 페이지/섹션 저장은 시도
        finally:
            # (옵션) 더보기 모두 펼치기
            if expand_more:
                try:
                    expand_all_reviews(drv, max_clicks=200)
                except Exception as e:
                    print(f"[WARN] 더보기 펼치기 실패: {name} // {e}")

        # 저장 (가게명 포함)
        safe_name = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", name)[:60] or f"place_{idx}"
        drv.switch_to.default_content()
        # save_html(drv, f"{idx:02d}_{safe_name}_fullpage")
        try:
            save_review_section_html(drv, f"{idx:02d}_{safe_name}_reviews")
        except Exception as e:
            print(f"[WARN] 리뷰 섹션 저장 실패: {name} // {e}")

        processed += 1

    print(f"\n[DONE] 총 {processed}개 가게 처리 완료.")
    input("브라우저는 열린 상태로 유지됩니다. 종료하려면 Enter...")

if __name__ == "__main__":
    # 예: 상위 8개 가게, 최신순 정렬, 더보기 펼치기 활성화
    run_crawl(max_places=8, sort_latest=True, expand_more=True)
