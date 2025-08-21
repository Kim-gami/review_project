from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException
import os
from datetime import datetime

SAVE_DIR = "saved_pages"

def save_current_html(driver, label="hyowon_review"):
    """
    현재 페이지의 DOM 스냅샷을 saved_pages 폴더에 UTF-8로 저장합니다.
    파일명 예: 2025-08-21_11-32-05_hyowon_review.html
    """
    os.makedirs(SAVE_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_label = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in label)
    filepath = os.path.join(SAVE_DIR, f"{ts}_{safe_label}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"[OK] HTML 저장 완료 -> {filepath}")
    return filepath
URL = "https://www.google.co.kr/maps/search/%EC%A0%95%EC%9E%90%EB%8F%99+%EC%8B%9D%EB%8B%B9/data=!3m1!4b1?entry=ttu&g_ep=EgoyMDI1MDgxOS4wIKXMDSoASAFQAw%3D%3D"

# 1) 효원식당 분당정자점 링크 <a>
XPATH_FIRST_LINK = "//a[@class='hfpxzc' and contains(@aria-label,'효원식당 분당정자점')]"

# 2) 리뷰 버튼 (리뷰 div를 감싸는 button)
XPATH_REVIEW_BUTTON = "//button[.//div[normalize-space()='리뷰']]"

def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_experimental_option("detach", True)   # 스크립트 끝나도 창 유지
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1280, 900)
    return driver

def wait_and_click(driver, locator, timeout=15):
    wait = WebDriverWait(driver, timeout)
    el = wait.until(EC.presence_of_element_located(locator))
    el = wait.until(EC.visibility_of_element_located(locator))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    wait.until(EC.element_to_be_clickable(locator))
    try:
        ActionChains(driver).move_to_element(el).click(el).perform()
    except (ElementClickInterceptedException, StaleElementReferenceException):
        el = driver.find_element(*locator)
        driver.execute_script("arguments[0].click();", el)

if __name__ == "__main__":
    driver = make_driver()
    driver.get(URL)

    # 1) 첫 번째 클릭 (효원식당 링크)
    try:
        wait_and_click(driver, (By.XPATH, XPATH_FIRST_LINK), timeout=20)
        print("[OK] 효원식당 링크 클릭 완료")
    except Exception as e:
        print("[FAIL] 첫 번째 클릭 실패:", e)

    # 2) 두 번째 클릭 (리뷰 버튼)
    try:
        wait_and_click(driver, (By.XPATH, XPATH_REVIEW_BUTTON), timeout=20)
        print("[OK] 리뷰 버튼 클릭 완료")
        save_current_html(driver, label="hyowon_review")

    except Exception as e:
        print("[FAIL] 두 번째 클릭 실패:", e)


    input("브라우저가 열린 상태입니다. 종료하려면 Enter를 누르세요...")
