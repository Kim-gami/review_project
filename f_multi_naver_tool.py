# naver_tool.py
import re, os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service

NAVER_URL_TEMPLATE = "https://map.naver.com/p/search/{}"
XPATH_FIRST_PLACE = ["//*[@id='_pcmap_list_scroll_container']/ul/li[1]/div[1]/div[1]/a/span[1]",
                     "//*[@id='_pcmap_list_scroll_container']/ul/li[1]/div[1]/div[1]/a/span[1]"]
XPATH_REVIEW_TABS = [
    "//*[@id='app-root']//span[normalize-space()='리뷰']",
    "//*[@id='app-root']/div/div/div[5]/div/div/div/div/a[3]/span",
    "//*[@id='app-root']/div/div/div[5]/div/div/div/div/a[5]/span",
    "//*[@id='app-root']//a[contains(@href,'review')]",
]
XPATH_SORT_LATESTS = [
    "//*[@id='app-root']//a[normalize-space()='최신순']",
    "//*[@id='app-root']/div/div/div[7]/div[2]/div[3]/div[1]/div[2]/div[1]/a[2]",
    "//*[@id='app-root']/div/div/div[7]/div[3]/div[3]/div[1]/div[2]/div[1]/a[2]"
]
XPATH_STORE_NAME = "//*[@id='_title']/div/span[1]"
XPATH_REVIEW_BLOCKS = [
    "//*[@id='_review_list']/li[1]/div[5]/a",
    "//*[@id='_review_list']/li[2]/div[5]/a",
    "//*[@id='_review_list']/li[3]/div[5]/a",
    "//*[@id='_review_list']/li[4]/div[5]/a",
    "//*[@id='_review_list']/li[5]/div[5]/a",
    "//*[@id='_review_list']/li[1]/div[5]/a[1]",
    "//*[@id='_review_list']/li[2]/div[5]/a[1]",
    "//*[@id='_review_list']/li[3]/div[5]/a[1]",
    "//*[@id='_review_list']/li[4]/div[5]/a[1]",
    "//*[@id='_review_list']/li[5]/div[5]/a[1]"
]

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
    driver.implicitly_wait(implicit_wait)
    return driver

def wwait(drv, timeout=5, poll=0.2):
    return WebDriverWait(drv, timeout, poll_frequency=poll)

def switch_to_iframe(drv, iframe_id, timeout=20):
    drv.switch_to.default_content()
    el = wwait(drv, timeout).until(
        EC.presence_of_element_located((By.ID, iframe_id))
    )
    drv.switch_to.frame(el)

def get_first_place(driver, timeout=20):
    switch_to_iframe(driver, "searchIframe", timeout)
    last_err = None
    for xp in XPATH_FIRST_PLACE:
        try:
            el = wwait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            el.click()
            # print("[OK] 첫 번째 장소 클릭 성공 (XPath)")
            return True
        except Exception as e:
            last_err = e
            continue

def click_review_tab(driver, timeout=20):
    switch_to_iframe(driver, "entryIframe", timeout)
    last_err = None
    for xp in XPATH_REVIEW_TABS:
        try:
            el = wwait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            el.click()
            # print(f"[OK] 리뷰 탭 클릭: {xp}")
            return True
        except Exception as e:
            last_err = e
            continue
    raise TimeoutException(f"리뷰 탭 클릭 실패: {last_err}")

def click_sort_latest(driver, timeout=20):
    switch_to_iframe(driver, "entryIframe", timeout)
    last_err = None
    for xp in XPATH_SORT_LATESTS:
        try:
            el = wwait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            el.click()
            # print(f"[OK] 최신순 버튼 클릭: {xp}")
            return True
        except Exception as e:
            last_err = e
            continue
    raise TimeoutException(f"최신순 버튼 클릭 실패: {last_err}")

def parse_reviews(driver, timeout=5, max_reviews=None):
    switch_to_iframe(driver, "entryIframe", timeout)
    try:
        wwait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.XPATH, "//*[@id='_review_list']"))
        )
    except TimeoutException:
        return []

    reviews, seen = [], set()
    for xp in XPATH_REVIEW_BLOCKS:
        elems = driver.find_elements(By.XPATH, xp)
        for e in elems:
            try:
                html = e.get_attribute("innerHTML") or e.text
                txt = re.sub(r"<[^>]+>", "", html).strip()
                if not txt:
                    continue
                if any(bad in txt for bad in ["리뷰 ", "팔로워", "팔로우"]):
                    continue
                txt = re.sub(r"(일상|연인|배우자|아이|가족|친구|혼밥|회식|모임|더보기|펼쳐보기).*", "", txt).strip()
                key = txt.replace(" ", "")
                if len(txt) < 2 or key in seen:
                    continue
                seen.add(key)
                reviews.append(txt)
                if max_reviews and len(reviews) >= max_reviews:
                    print(f"[NAVER] 리뷰 {len(reviews)}개 추출")
                    return reviews
            except Exception:
                continue
    print(f"[NAVER] 리뷰 {len(reviews)}개 추출")
    return reviews

def run(keyword: str, max_reviews=None):
    url = NAVER_URL_TEMPLATE.format(keyword)
    driver = make_driver(headless=True)
    driver.get(url)
    try:
        get_first_place(driver, timeout=7)
        click_review_tab(driver, timeout=7)
        click_sort_latest(driver, timeout=7)
        reviews = parse_reviews(driver, max_reviews=max_reviews)
        return {"keyword": keyword, "reviews": reviews}
    except TimeoutException:
        return {"keyword": keyword, "reviews": []}
    finally:
        driver.quit()

if __name__ == "__main__":
    kw = "정자역 미방"
    result = run(kw, max_reviews=20)
    print(result)
