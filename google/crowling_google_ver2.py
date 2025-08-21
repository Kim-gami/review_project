from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException, StaleElementReferenceException
)
import os, re
from datetime import datetime

# 🔗 정자동 식당 검색 URL
SEARCH_URL = "https://www.google.co.kr/maps/search/%EC%A0%95%EC%9E%90%EB%8F%99+%EC%8B%9D%EB%8B%B9/data=!3m1!4b1?entry=ttu&g_ep=EgoyMDI1MDgxOS4wIKXMDSoASAFQAw%3D%3D"

# ⛳ 결과 리스트의 각 가게 카드 anchor
CSS_RESULT_LINKS = "a.hfpxzc[aria-label][href]"

# ⭐ 상세에서 리뷰 탭 버튼(‘리뷰’ div를 감싸는 button)
XPATH_REVIEW_BUTTON = "//button[.//div[normalize-space()='리뷰']]"

SAVE_DIR = "saved_pages"

def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_experimental_option("detach", True)   # 스크립트 끝나도 창 유지
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1300, 950)
    return driver

def wwait(driver, timeout=20, poll=0.2):
    return WebDriverWait(driver, timeout, poll_frequency=poll)

def safe_click(driver, locator, timeout=20):
    wait = wwait(driver, timeout)
    el = wait.until(EC.presence_of_element_located(locator))
    el = wait.until(EC.visibility_of_element_located(locator))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    wait.until(EC.element_to_be_clickable(locator))
    try:
        ActionChains(driver).move_to_element(el).click(el).perform()
    except (ElementClickInterceptedException, StaleElementReferenceException):
        el = driver.find_element(*locator)
        driver.execute_script("arguments[0].click();", el)
    return True

def get_results_container(driver):
    """
    구글맵 좌측 결과 패널의 스크롤 컨테이너를 찾는다.
    우선순위:
      1) role='feed' (요즘 지도 DOM에서 결과 리스트)
      2) 스크롤 가능한 m6QErb... 컨테이너 (백업)
    """
    wait = wwait(driver, 20)
    try:
        feed = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed']")))
        return feed
    except TimeoutException:
        pass
    # 백업 셀렉터 (클래스는 자주 변해서 contains 활용)
    backup = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR,
        "div.m6QErb.DxyBCb.kA9KIf.dS8AEf"  # 결과 리스트 패널의 공통 조합
    )))
    return backup

def scroll_results_to_load_more(driver, max_scrolls=40, min_increment=3, timeout_each=10):
    """
    결과 패널을 아래로 스크롤하며 더 많은 가게 카드를 로딩한다.
    - max_scrolls: 최대 스크롤 시도 횟수
    - min_increment: 새로 로드되었다고 인정할 최소 결과 증가 수
    - timeout_each: 각 스크롤 이후 증가 감지 대기 최대 초(Wait 기반)
    """
    container = get_results_container(driver)
    wait = wwait(driver, timeout_each, poll=0.2)

    def current_count():
        return len(driver.find_elements(By.CSS_SELECTOR, CSS_RESULT_LINKS))

    seen_count = current_count()
    stagnant = 0

    for i in range(1, max_scrolls + 1):
        # 컨테이너 최하단으로 스크롤
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)

        try:
            # 결과 개수가 늘어날 때까지 대기
            wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, CSS_RESULT_LINKS)) >= seen_count + min_increment)
            new_count = current_count()
            print(f"[SCROLL {i}] 결과 {seen_count} → {new_count}")
            if new_count == seen_count:
                stagnant += 1
            else:
                stagnant = 0
            seen_count = new_count
        except TimeoutException:
            # 증가 없으면 정체 카운트 증가
            stagnant += 1
            print(f"[SCROLL {i}] 증가 없음 (누적 정체 {stagnant})")

        # 몇 번 연속으로 증가가 없으면 종료
        if stagnant >= 3:
            print("[INFO] 추가 로딩 정체: 스크롤 중단")
            break

def collect_result_links(driver, max_items=None):
    """
    화면에 로드된 a.hfpxzc 링크들을 수집해 (href, label) 리스트로 반환.
    """
    wwait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, CSS_RESULT_LINKS)))
    anchors = driver.find_elements(By.CSS_SELECTOR, CSS_RESULT_LINKS)
    seen = set()
    items = []
    for a in anchors:
        try:
            href = a.get_attribute("href")
            label = (a.get_attribute("aria-label") or "").split("·", 1)[0].strip()
            if not href or href in seen:
                continue
            seen.add(href)
            items.append((href, label))
            if max_items and len(items) >= max_items:
                break
        except Exception:
            continue
    return items

def save_current_html(driver, label="page"):
    os.makedirs(SAVE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_label = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", label)[:80] or "page"
    html_path = os.path.join(SAVE_DIR, f"{ts}_{safe_label}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"[SAVE] HTML → {html_path}")
    return html_path

def click_reviews(driver, timeout=20):
    return safe_click(driver, (By.XPATH, XPATH_REVIEW_BUTTON), timeout=timeout)

def run(max_items=None, do_scroll=True, scroll_batches=40):
    """
    1) 검색 페이지 접속
    2) (옵션) 결과 패널 스크롤로 추가 로딩
    3) 결과 링크 수집
    4) 각 링크로 이동 → '리뷰' 클릭 → HTML 저장
    """
    driver = make_driver()
    driver.get(SEARCH_URL)

    # 2) 스크롤로 더 로딩
    if do_scroll:
        try:
            scroll_results_to_load_more(driver, max_scrolls=scroll_batches, min_increment=3, timeout_each=8)
        except Exception as e:
            print("[WARN] 스크롤 중 예외 발생:", e)

    # 3) 링크 수집
    links = collect_result_links(driver, max_items=max_items)
    print(f"[INFO] 수집된 링크 수: {len(links)}")

    # 4) 각 장소 처리
    for idx, (href, label) in enumerate(links, start=1):
        print(f"\n[{idx}/{len(links)}] 이동: {label} → {href}")
        try:
            driver.get(href)
            try:
                click_reviews(driver, timeout=25)
                print("[OK] 리뷰 버튼 클릭")
            except TimeoutException:
                print("[WARN] 리뷰 버튼을 못 찾음 (페이지 HTML만 저장)")
            save_current_html(driver, label=f"{idx:02d}_{label}_review")
        except Exception as e:
            print(f"[ERROR] 처리 실패({label}): {e}")

    print("\n[DONE] 모든 항목 처리 완료")
    input("브라우저는 열린 상태로 유지됩니다. 종료하려면 Enter...")

if __name__ == "__main__":
    # 예) 테스트로 30개만 수집하려면 max_items=30
    run(max_items=None, do_scroll=True, scroll_batches=50)
