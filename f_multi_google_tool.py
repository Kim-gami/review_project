from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException, StaleElementReferenceException
)
import re, os
from selenium.webdriver.chrome.service import Service

XPATH_STORE_NAMES = [
    "//*[@id='QA0Szd']/div/div/div[1]/div[3]/div/div[1]/div/div/div[1]/div/div/div[2]/div/div/span",
    "//*[@id='QA0Szd']/div/div/div[1]/div[2]/div/div[1]/div/div/div[2]/div/div[1]/div[1]/h1",
    "//*[@id='QA0Szd']/div/div/div[1]/div[3]/div/div[1]/div/div/div[2]/div[2]/div/div[1]/div[1]/h1",
    "//*[@id='QA0Szd']/div/div/div[1]/div[2]/div/div[1]/div/div/div[2]/div/div[1]/div[1]/h1",
    "//*[@id='QA0Szd']/div/div/div[1]/div[3]/div/div[1]/div/div/div[2]/div[2]/div/div[1]/div[1]/h1"
]
XPATH_REVIEW_BUTTONS = [
    "//button[.//div[normalize-space()='리뷰']]",
    "//button[.//div[contains(., 'Reviews')]]",
    "//*[@id='QA0Szd']//button[3]//div[contains(., '리뷰')]",
    "//*[@id='ChdDSUhNMG9nS0VMM3c5cm1CakpfLWtRRRAB']/span[2]/button"
]
XPATH_FIRST_RESULT_LINK = "//*[@id='QA0Szd']/div/div/div[1]/div[2]/div/div[1]/div/div/div[1]/div[1]/div[3]/div/a"

XPATH_MORE_BUTTONS = "//*[@id='ChdDSUhNMG9nS0VMM3c5cm1CakpfLWtRRRAB']/span[2]/button"


def make_driver(headless=True, width=1300, height=950, implicit_wait=0):
    opts = webdriver.ChromeOptions()

    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"--window-size={width},{height}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-infobars")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    #도커
    chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    driver_path = os.getenv("CHROMEDRIVER", "/usr/bin/chromedriver")
    opts.binary_location = chrome_bin

    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=opts)
    driver.implicitly_wait(implicit_wait)  # 암시적 대기(권장: 0 or 짧게)
    return driver

def wwait(driver, timeout=20, poll=0.2):
    return WebDriverWait(driver, timeout, poll_frequency=poll)

def safe_click(driver, locator, timeout=5):
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

def click_first_link(driver, timeout=5):
    return safe_click(driver, (By.XPATH, XPATH_FIRST_RESULT_LINK), timeout=timeout)

def click_reviews(driver, timeout=2):
    for xpath in XPATH_REVIEW_BUTTONS:
        try:
            return safe_click(driver, (By.XPATH, xpath), timeout=timeout)
        except TimeoutException:
            continue
    raise TimeoutException("리뷰 버튼을 찾지 못했습니다.")

def click_all_detail_buttons(driver, timeout=5):
    wait = wwait(driver, timeout)
    try:
        wait.until(EC.presence_of_all_elements_located((By.XPATH, XPATH_MORE_BUTTONS)))
        buttons = driver.find_elements(By.XPATH, XPATH_MORE_BUTTONS)
    except TimeoutException:
        return 0

    clicked_count = 0
    for btn in buttons:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            safe_click(driver, (By.XPATH, XPATH_MORE_BUTTONS), timeout=timeout)
            clicked_count += 1
        except Exception:
            continue

    # print(f"[OK] '자세히' 버튼 {clicked_count}개 클릭 완료")
    return clicked_count

def parse_reviews(driver, timeout=20, max_reviews=None):

    wait = wwait(driver, timeout)
    try:
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-review-id]")))
    except TimeoutException:
        # print("[WARN] 리뷰 영역을 찾지 못했습니다.")
        return []

    review_elems = driver.find_elements(By.CSS_SELECTOR, "div[data-review-id]")
    reviews = []
    seen = set()

    for elem in review_elems:
        try:
            text_elem = elem.find_element(By.CSS_SELECTOR, "span[class*='wiI7pd']")
            text = text_elem.text.strip()
            if not text:
                continue

            text = re.sub(r"\s+", " ", text)

            if text not in seen:
                reviews.append(text)
                seen.add(text)

            if max_reviews and len(reviews) >= max_reviews:
                break

        except Exception:
            continue

    print(f"[GOOGLE] 리뷰 {len(reviews)}개 추출")
    return reviews

def run(keyword: str, max_reviews=None):
    url = f"https://www.google.co.kr/maps/search/{keyword}"
    driver = make_driver(headless=True)
    driver.get(url)

    try:
        click_first_link(driver, timeout=5)
        click_reviews(driver, timeout=5)
        click_all_detail_buttons(driver, timeout=5)
        reviews = parse_reviews(driver, max_reviews=max_reviews)
        return {"keyword": keyword, "reviews": reviews}

    except TimeoutException:
        try:
            click_reviews(driver, timeout=5)
            click_all_detail_buttons(driver, timeout=5)
            reviews = parse_reviews(driver, max_reviews=max_reviews)
            return {"keyword": keyword, "reviews": reviews}
        except TimeoutException:
            return {"keyword": keyword, "reviews": None}

    except Exception as e:
        print(f"[ERROR] 알 수 없는 오류: {e}")
        return {"keyword": keyword, "reviews": [], "message": str(e)}

    finally:
        driver.quit()

# ---------------- 실행 예시 ----------------
if __name__ == "__main__":
    kw = "정자동 삼겹살"
    result = run(kw, max_reviews=5)
    print(result)
