# f_multi_kakao_tool.py
import re, time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

KAKAO_URL_TEMPLATE = "https://map.kakao.com/?q={}"

# 상세 페이지(가게 페이지)에서 매장명 파싱용
XPATH_STORE_NAME = "//*[@id='mainContent']/div[1]/div[1]/div[1]/h3"
XPATH_STORE_ADD = [
    "//*[@id='info.search.place.list']/li[1]/div[5]/div[2]/p[1]",
    "//*[@id='info.search.place.list']/li[2]/div[5]/div[2]/p[1]",
    "//*[@id='info.search.place.list']/li[3]/div[5]/div[2]/p[1]",
    "//*[@id='info.search.place.list']/li/div[5]/div[2]/p[1]"
]
XPATH_STORE_IMG = [
    "//*[@id='mainContent']/div[1]/div[3]/div/div[1]/a/img",
    "//*[@id='mainContent']/div[1]/div[3]/div/div[2]/div[1]/div[1]/a/img",
    "//*[@id='mainContent']/div[1]/div[3]/div/div[2]/div[2]/div[1]/a/img",
    "//*[@id='mainContent']/div[1]/div[3]/div/div[2]/div[1]/a/img",
    "//*[@id='mainContent']/div[1]/div[3]/div/div[2]/div[2]/a/img"
]
# 검색 결과 리스트에서 각 매장의 "리뷰" 버튼 (리스트 페이지)
# 기존 단일 매장용 XPATH를 그대로 사용하되, find_elements로 여러 개를 수집
XPATH_PLACE_REVIEW_BTNS = "//*[@id='info.search.place.list']/li/div[4]/span[1]/a"

# 상세 페이지의 리뷰 블록(페이지 구조에 맞게 유지)
CSS_REVIEW_BLOCKS = "ul li div div:nth-child(2) div div:nth-child(1) div:nth-child(2) a p"
XPATH_REVIEW_LI_ALL = "//*[@id='mainContent']/div[2]/div[2]/div[2]/div[3]/ul/li"
XPATH_REVIEW_MORE_TPL = "//*[@id='mainContent']/div[2]/div[2]/div[2]/div[3]/ul/li[{num}]/div/div[2]/div/div[1]/div[2]/a/p"

def make_driver(headless=True, width=1300, height=950):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--window-size={width},{height}")
    drv = webdriver.Chrome(options=opts)
    drv.implicitly_wait(0)
    return drv

def wwait(driver, timeout=5, poll=0.2):
    return WebDriverWait(driver, timeout, poll_frequency=poll)

def get_top_place_review_url(driver, timeout=8):

    try:
        wwait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.XPATH, XPATH_PLACE_REVIEW_BTNS))
        )
    except TimeoutException:
        # print("[WARN] 리뷰 버튼을 찾지 못했습니다.")
        return None

    try:
        btn = driver.find_element(By.XPATH, XPATH_PLACE_REVIEW_BTNS)
        href = btn.get_attribute("href")
        if href:
            # print("[INFO] 최상단 리뷰 URL 수집 완료")
            return href
    except Exception:
        pass

    return None

def click_expand_all_reviews(driver, timeout=10, max_clicks=None, pause=0.2):
    """
    리뷰 목록의 각 아이템에 대해 '더보기'를 1회씩 클릭.
    - num은 1부터 li 개수까지 증가
    - 더보기가 없는 항목은 건너뜀
    - 클릭은 JS로 수행하여 인터셉트/가림 문제 회피
    반환: 실제 클릭된 개수
    """
    wait = wwait(driver, timeout)
    clicked = 0
    try:
        wait.until(EC.presence_of_all_elements_located((By.XPATH, XPATH_REVIEW_LI_ALL)))
    except TimeoutException:
        # print("[WARN] 리뷰 리스트(li)를 찾지 못했습니다.")
        return 0

    li_elems = driver.find_elements(By.XPATH, XPATH_REVIEW_LI_ALL)
    total = len(li_elems)
    if max_clicks:
        total = min(total, max_clicks)

    for idx in range(1, total + 1):
        xp = XPATH_REVIEW_MORE_TPL.format(num=idx)
        try:
            el = driver.find_element(By.XPATH, xp)
            # 뷰로 스크롤 후 JS 클릭(겹침/가림 방지)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.1)
            driver.execute_script("arguments[0].click();", el)
            clicked += 1
            time.sleep(pause)
        except Exception:
            # 더보기가 없거나 이미 펼쳐진 경우 등은 패스
            continue

    # print(f"[CLICK] 리뷰 더보기 {clicked}/{total}건 클릭 완료")
    return clicked

def parse_store_name(driver, timeout=6):
    try:
        el = wwait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, XPATH_STORE_NAME))
        )
        store_name = el.text.strip()
        # print(f"[PARSE] 매장명 추출: {store_name}")
        return store_name
    except TimeoutException:
        # print("[WARN] 매장명을 찾지 못했습니다.")
        return None

def parse_images(driver, timeout=6, max_images=None):
    urls = []
    seen = set()

    for xp in XPATH_STORE_IMG:
        try:
            wwait(driver, timeout).until(
                EC.presence_of_all_elements_located((By.XPATH, xp))
            )
        except TimeoutException:
            continue  # 이 후보 XPATH는 패스

        elems = driver.find_elements(By.XPATH, xp)
        for el in elems:
            src = None

            # 요소가 <img>면 바로 src 계열 확인
            if el.tag_name.lower() == "img":
                src = el.get_attribute("src") or el.get_attribute("data-src") or el.get_attribute("srcset")
            else:
                # 아니면 내부의 <img> 찾기
                try:
                    img = el.find_element(By.TAG_NAME, "img")
                    src = img.get_attribute("src") or img.get_attribute("data-src") or img.get_attribute("srcset")
                except Exception:
                    src = None

            if not src:
                continue

            # srcset일 경우 첫 항목 하나만 취함 (공백/쉼표 기준)
            if "," in src:
                src = src.split(",")[0].strip()
            if " " in src:
                src = src.split(" ")[0].strip()

            if not src or src in seen:
                continue

            seen.add(src)
            urls.append(src)

            if max_images and len(urls) >= max_images:
                return urls

    return urls

def parse_reviews(driver, timeout=6, max_reviews=None):
    try:
        wwait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, CSS_REVIEW_BLOCKS))
        )
    except TimeoutException:
        # print("[WARN] 리뷰 블록을 찾지 못했습니다.")
        return []

    elems = driver.find_elements(By.CSS_SELECTOR, CSS_REVIEW_BLOCKS)
    reviews, seen = [], set()
    for e in elems:
        txt = e.text.strip()
        if not txt:
            continue
        txt = re.sub(r"\s+", " ", txt)

        # 중복 제거
        if txt in seen:
            continue
        seen.add(txt)

        reviews.append(txt)
        if max_reviews and len(reviews) >= max_reviews:
            break

    print(f"[KAKAO] 리뷰 {len(reviews)}개 추출")
    return reviews

def run_multi(keyword: str, max_reviews=None, headless=True):
    url = KAKAO_URL_TEMPLATE.format(keyword)
    driver = make_driver(headless=headless)
    driver.get(url)

    try:
        review_url = get_top_place_review_url(driver, timeout=7)
        if not review_url:
            return {}

        results = {}
        driver.get(review_url)
        store_image = parse_images(driver, timeout=7)
        click_expand_all_reviews(driver, timeout=7)
        store_name = parse_store_name(driver) or f"{keyword}"
        reviews = parse_reviews(driver, max_reviews=max_reviews)

        # results[store_name] = reviews  # ⭐ 바로 리스트만 저장
        results = {"keyword": store_name, "reviews" : reviews, "store_image": store_image}
        time.sleep(0.5)

        return results   # ⭐ {"매장명": 리뷰리스트}

    except TimeoutException:
        return {}

    finally:
        driver.quit()

if __name__ == "__main__":
    kw = "정자동 고기"
    out = run_multi(kw, max_reviews=5, headless=True)
    print(out)
