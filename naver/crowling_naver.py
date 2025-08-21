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

WAIT_LONG = 20
WAIT_SHORT = 8

# ▶ 클릭할 버튼 시퀀스
BUTTON_SEQUENCE = [
    {
        "name": "가게 선택",
        "scope": "search",
        "xpath": "//span[contains(@class,'TYaxT') and normalize-space()='한돈곳간 분당정자점']",
        "pre": 0.2, "post": 0.6, "tries": 2, "timeout": WAIT_LONG,
    },
    {
        "name": "리뷰 탭",
        "scope": "entry",
        "xpath": "//span[contains(@class,'veBoZ') and normalize-space()='리뷰']",
        "pre": 0.5, "post": 0.8, "tries": 3, "timeout": WAIT_LONG,
    },
    {
        "name": "리뷰 정렬(최신순)",
        "scope": "entry",
        "xpath": "//a[@role='option' and contains(@class,'place_btn_option') and normalize-space()='최신순']",
        "pre": 0.3, "post": 0.6, "tries": 2, "timeout": WAIT_SHORT,
    },
]

# --- 유틸 함수들 ---
def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_experimental_option("detach", True)   # 스크립트 끝나도 창 유지
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1300, 950)
    return driver

def wwait(drv, t=WAIT_LONG, poll=0.2):
    return WebDriverWait(drv, t, poll_frequency=poll)

def click_with_retry(drv, by, sel, tries=3, pre_sleep=0.2, post_sleep=0.35, timeout=WAIT_SHORT):
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
            time.sleep(0.4 + 0.2*attempt)
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

# --- 메인 ---
def run_test():
    drv = make_driver()
    drv.get(SEARCH_URL)

    for step in BUTTON_SEQUENCE:
        name, scope, xp = step["name"], step["scope"], step["xpath"]
        pre, post = step.get("pre",0.2), step.get("post",0.4)
        tries, timeout = step.get("tries",2), step.get("timeout",WAIT_SHORT)

        if scope == "search":
            to_search_iframe(drv)
        elif scope == "entry":
            to_entry_iframe(drv)
            wait_entry_loaded(drv)

        print(f"[CLICK] {name}")
        click_with_retry(drv, By.XPATH, xp, tries=tries, pre_sleep=pre, post_sleep=post, timeout=timeout)
        if "리뷰 탭" in name:
            wait_reviews_ready(drv)

    # 전체 페이지 + 리뷰 섹션 저장
    drv.switch_to.default_content()
    save_html(drv, "after_3_clicks")
    save_review_section_html(drv, "reviews")

    print("[DONE] 버튼 3개 클릭 + 저장 완료")
    input("브라우저는 열린 상태로 유지됩니다. 종료하려면 Enter...")

if __name__ == "__main__":
    run_test()
