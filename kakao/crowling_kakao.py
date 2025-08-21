import os
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== 설정 =====
HEADLESS = True            # 화면 없이 실행하려면 True
RENDER_WAIT = 3.0          # 페이지/iframe 로딩 대기 (초)
RETRY = 2                  # 실패 시 재시도 횟수
OUTDIR = Path("saved_pages")
OUTDIR.mkdir(parents=True, exist_ok=True)

ID_FILE = "kakao_review_address.txt"          # 한 줄에 하나의 place id (예: 2112992111)
URL_FILE = "review_urls.txt"       # 한 줄에 하나의 리뷰 URL (예: https://place.map.kakao.com/2112992111#review)

ID_URL_PATTERN = re.compile(r"https?://place\.map\.kakao\.com/(\d+)(?:#.*)?")

def build_driver(headless: bool = True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,2000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(30)
    return driver

def read_ids_or_urls(id_file: str, url_file: str):
    ids = []
    urls = []

    if Path(id_file).exists():
        with open(id_file, "r", encoding="utf-8") as f:
            ids = [line.strip() for line in f if line.strip()]
    if Path(url_file).exists():
        with open(url_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

    # URL에서 ID 뽑아서 합치기
    for u in urls:
        m = ID_URL_PATTERN.match(u)
        if m:
            ids.append(m.group(1))

    # 중복 제거 & 정렬(optional)
    ids = sorted(set(ids))
    return ids

def dump_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8", errors="ignore")

def save_page_and_iframes(driver, place_id: str):
    """place 페이지 열고 메인 HTML + 모든 iframe HTML 저장"""
    target_dir = OUTDIR / place_id
    target_dir.mkdir(parents=True, exist_ok=True)

    url = f"https://place.map.kakao.com/{place_id}#review"
    driver.get(url)

    # 메인 페이지 렌더 대기
    time.sleep(RENDER_WAIT)

    # 메인 HTML 저장
    page_html = driver.page_source
    dump_text(target_dir / "page.html", page_html)

    # 가능한 경우, 리뷰 탭으로 자동 스크롤(로딩 유도)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1.0)

    # iframe 모두 저장
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for idx, iframe in enumerate(iframes):
        try:
            # 프레임 전환
            WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_frame(iframe))
            time.sleep(RENDER_WAIT)

            iframe_html = driver.page_source
            dump_text(target_dir / f"iframe_{idx}.html", iframe_html)

            # 프레임 내부에서 더 스크롤(추가 로딩 유도)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.0)

            # 되돌아오기
            driver.switch_to.default_content()
        except Exception:
            # 문제가 생겨도 다음 프레임으로 진행
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            continue

def run_batch(ids):
    driver = build_driver(HEADLESS)
    try:
        for i, pid in enumerate(ids, 1):
            print(f"[{i}/{len(ids)}] {pid} 처리 중...")
            success = False
            for attempt in range(1, RETRY + 2):
                try:
                    save_page_and_iframes(driver, pid)
                    success = True
                    break
                except Exception as e:
                    print(f"  - 시도 {attempt} 실패: {e}")
                    time.sleep(2.0)
            if not success:
                print(f"  >> 실패: {pid}")
            # 사이트 부하/차단 방지 딜레이
            time.sleep(1.5)
    finally:
        driver.quit()

if __name__ == "__main__":
    ids = read_ids_or_urls(ID_FILE, URL_FILE)
    if not ids:
        print("수집할 ID/URL이 없습니다. place_ids.txt 또는 review_urls.txt 를 확인하세요.")
    else:
        print(f"총 {len(ids)}개 ID 처리 예정.")
        run_batch(ids)
        print("완료!")
