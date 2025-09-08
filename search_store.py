# f_multi_kakao_tool.py
import re, time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

KAKAO_URL_TEMPLATE = "https://map.kakao.com/?q={}"

# 상세 페이지(가게 페이지)에서 매장명 파싱용
XPATH_STORE_NAME = "//*[@id='mainContent']/div[1]/div[1]/div[1]/h3"

# 검색 결과 li 요소
XPATH_RESULTS_LI = "//*[@id='info.search.place.list']/li[not(contains(@class,'hide'))]"
# li 내부 리뷰 버튼과 주소 후보
REL_XPATH_REVIEW_BTN = ".//div[4]/span[1]/a"
REL_XPATH_ADDR_CANDIDATES = [
    # 개별 li 고정 후보
    "//*[@id='info.search.place.list']/li[1]/div[5]/div[2]/p[1]",
    "//*[@id='info.search.place.list']/li[2]/div[5]/div[2]/p[1]",
    "//*[@id='info.search.place.list']/li[3]/div[5]/div[2]/p[1]",
    "//*[@id='info.search.place.list']/li[4]/div[5]/div[2]/p[1]",
    "//*[@id='info.search.place.list']/li[5]/div[5]/div[2]/p[1]"
]

REL_XPATH_ADDR_FALLBACK = "//*[@id='info.search.place.list']/li/div[5]/div[2]/p[1]"

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

def get_result_cards(driver, timeout=10):
    """검색결과의 각 매장 li 요소들을 반환"""
    try:
        wwait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.XPATH, XPATH_RESULTS_LI))
        )
    except TimeoutException:
        return []
    return driver.find_elements(By.XPATH, XPATH_RESULTS_LI)

def extract_review_href_from_li(li):
    """단일 매장 li 내부에서 리뷰 버튼의 href 추출"""
    try:
        a = li.find_element(By.XPATH, REL_XPATH_REVIEW_BTN)
        href = a.get_attribute("href")
        return href
    except Exception:
        return None

def extract_address_from_li(li, idx=None):
    """
    단일 매장 li 내부에서 주소 텍스트 추출
    1) li별 고정 XPath (REL_XPATH_ADDR_CANDIDATES) 시도
    2) 실패 시 fallback XPath (REL_XPATH_ADDR_FALLBACK)
    """
    # 1) li별 고정 후보 (idx 기반으로 선택)
    if idx is not None and idx - 1 < len(REL_XPATH_ADDR_CANDIDATES):
        try:
            xp = REL_XPATH_ADDR_CANDIDATES[idx - 1]
            el = li.find_element(By.XPATH, xp)
            txt = el.text.strip()
            if txt:
                return txt
        except Exception:
            pass

    # 2) fallback
    try:
        el = li.find_element(By.XPATH, REL_XPATH_ADDR_FALLBACK)
        txt = el.text.strip()
        if txt:
            return txt
    except Exception:
        pass

    return None

def get_top_place_review_urls_and_addresses(driver, top_n=5, timeout=10):
    cards = get_result_cards(driver, timeout=timeout)
    pairs = []
    for idx, li in enumerate(cards[:top_n], start=1):
        href = extract_review_href_from_li(li)
        addr = extract_address_from_li(li, idx=idx)
        if href:
            pairs.append((href, addr))
    return pairs

def parse_store_name(driver, timeout=6):
    try:
        el = wwait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, XPATH_STORE_NAME))
        )
        store_name = el.text.strip()
        return store_name
    except TimeoutException:
        return None

def parse_latlng_from_kakao_html(html: str):
    """카카오맵 상세페이지 HTML에서 위도(lat), 경도(lng) 추출"""
    try:
        soup = BeautifulSoup(html, "html.parser")
        meta = soup.find("meta", {"property": "og:image"})
        if not meta:
            return None, None
        url = meta.get("content", "")
        m = re.search(r"m=(-?\d+\.\d+),(-?\d+\.\d+)", url)
        if m:
            lng, lat = float(m.group(1)), float(m.group(2))
            return lat, lng
    except Exception:
        pass
    return None, None

def run_multi(keyword: str, top_n=5, max_reviews=None, headless=True):
    url = KAKAO_URL_TEMPLATE.format(keyword)
    driver = make_driver(headless=headless)
    driver.get(url)

    try:
        url_addr_pairs = get_top_place_review_urls_and_addresses(driver, top_n=top_n, timeout=25)
        if not url_addr_pairs:
            return {}

        results = {}
        for idx, (rurl, addr) in enumerate(url_addr_pairs, start=1):
            driver.get(rurl)

            store_name = parse_store_name(driver) or f"{keyword}_{idx}"
            html = driver.page_source
            lat, lng = parse_latlng_from_kakao_html(html)

            results[store_name] = (addr, (lat, lng))
            time.sleep(0.5)

        return results

    except TimeoutException:
        return {}
    finally:
        driver.quit()

if __name__ == "__main__":
    kw = "근처 삼겹살"
    out = run_multi(kw, top_n=5, max_reviews=5, headless=True)
    # print(out.keys())
