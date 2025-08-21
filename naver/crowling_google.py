from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, JavascriptException
import os, re
from datetime import datetime

URL = "https://map.naver.com/p/search/%EC%A0%95%EC%9E%90%EB%8F%99%20%EC%8B%9D%EB%8B%B9?c=14.00,0,0,0,dh"

# 1,2,3번 버튼 (네가 준 그대로)
FIRST_BUTTON  = (By.XPATH, "//a[@role='button']//span[normalize-space()='정자장어타운']")
SECOND_BUTTON = (By.XPATH, "//a[@role='tab']//span[normalize-space()='리뷰']")
THIRD_BUTTON  = (By.XPATH, "//a[@role='option' and normalize-space()='최신순']")

SAVE_DIR = "saved_pages"

# 리뷰 컨테이너 후보 셀렉터들 (도메스트릭: DOM 변동 대비해서 넓게 잡음)
REVIEW_CONTAINER_SELECTORS = [
    # 섹션 루트
    "section:has(span:contains('리뷰'))",                # 최신 크롬 :has 지원
    "section:has(h2:contains('리뷰'))",
    # 네이버가 자주 쓰는 패턴들(리뷰 목록)
    "ul[class*='list'], div[class*='list'] div[class*='review']",
    "div[role='article']",                               # 카드형 아티클
    "[data-nclick*='rvw']",
]

# 크롬에서만 동작하는 :contains, :has 사용을 허용(폴백도 구현)
JS_WAIT_FOR_ANY_SELECTOR = r"""
const selectors = arguments[0];
const timeoutMs = arguments[1];
const cb = arguments[2];

function qsaAny(selectors) {
  for (const sel of selectors) {
    try {
      const nodes = document.querySelectorAll(sel);
      if (nodes && nodes.length > 0) return {sel, nodes};
    } catch (e) {/* CSS4 selector not supported yet; ignore */}
  }
  return null;
}

// 폴백: 텍스트로 '리뷰' 구간 추정
function fallbackFind() {
  const candidates = Array.from(document.querySelectorAll('section,div,ul,article'));
  for (const el of candidates) {
    const txt = (el.innerText || '').trim();
    if (txt.includes('리뷰')) {
      return {sel: 'FALLBACK', nodes: [el]};
    }
  }
  return null;
}

const found = qsaAny(selectors) || fallbackFind();
if (found) return cb(found);

const obs = new MutationObserver(() => {
  const f = qsaAny(selectors) || fallbackFind();
  if (f) {
    obs.disconnect();
    cb(f);
  }
});

obs.observe(document.documentElement, {subtree: true, childList: true});

setTimeout(() => {
  try { obs.disconnect(); } catch(e) {}
  cb(null);
}, timeoutMs);
"""

def make_driver():
    opts = webdriver.ChromeOptions()
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1300, 950)
    return driver

def save_text(text, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def timestamped(name):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", name)[:80] or "page"
    return f"{ts}_{safe}"

def switch_to_iframe_contains(driver, key, timeout=20):
    WebDriverWait(driver, timeout).until(
        EC.frame_to_be_available_and_switch_to_it(
            (By.XPATH, f"//iframe[contains(@id,'{key}') or contains(@name,'{key}')]")
        )
    )

def run():
    driver = make_driver()
    try:
        driver.get(URL)

        # --- 1) searchIframe 에서 가게 클릭 ---
        driver.switch_to.default_content()
        switch_to_iframe_contains(driver, "searchIframe", timeout=25)
        WebDriverWait(driver, 25).until(EC.element_to_be_clickable(FIRST_BUTTON)).click()
        print("[OK] 1번(가게) 클릭")

        # --- 2) entryIframe 으로 전환 ---
        driver.switch_to.default_content()
        switch_to_iframe_contains(driver, "entryIframe", timeout=25)

        # --- 3) 리뷰 탭 → 최신순 클릭 ---
        WebDriverWait(driver, 25).until(EC.element_to_be_clickable(SECOND_BUTTON)).click()
        print("[OK] 2번(리뷰 탭) 클릭")
        WebDriverWait(driver, 25).until(EC.element_to_be_clickable(THIRD_BUTTON)).click()
        print("[OK] 3번(최신순) 클릭")

        # --- 4) 리뷰 DOM이 실제로 붙을 때까지 MutationObserver로 대기 ---
        try:
            found = driver.execute_async_script(JS_WAIT_FOR_ANY_SELECTOR, REVIEW_CONTAINER_SELECTORS, 15000)
        except JavascriptException:
            # 일부 환경에서 :has/:contains 미지원 시 폴백만 수행하도록
            found = driver.execute_async_script(JS_WAIT_FOR_ANY_SELECTOR.replace(":has", "").replace(":contains", ""), REVIEW_CONTAINER_SELECTORS, 15000)

        # --- 5) 저장 ---
        base = os.path.join(SAVE_DIR, timestamped("naver_reviews"))
        if found:
            # 컨테이너의 outerHTML 저장 + 전체 HTML 백업
            sel = found.get("sel", "UNKNOWN")
            # 첫 노드만 저장
            outer_html = driver.execute_script("return arguments[0].outerHTML;", found["nodes"][0])
            save_text(outer_html, base + f"__container_{sel}.html")
            save_text(driver.page_source, base + "__full.html")
            print(f"[SAVE] 리뷰 컨테이너 + 전체 DOM 저장 완료 → {base}__*.html")
        else:
            # 컨테이너를 못 찾았으면 전체 DOM만 저장(디버그용)
            save_text(driver.page_source, base + "__full_only.html")
            print(f"[WARN] 리뷰 컨테이너를 못 찾음. 전체 DOM만 저장 → {base}__full_only.html")

    except Exception as e:
        print("[ERROR]", e)
        # 오류 발생 시에도 전체 DOM 백업
        try:
            base = os.path.join(SAVE_DIR, timestamped("naver_error_dump"))
            save_text(driver.page_source, base + "__full.html")
            print(f"[DUMP] 에러 시점 DOM 저장 → {base}__full.html")
        except Exception:
            pass
    finally:
        driver.quit()  # 요청하신 대로 작업 후 창 닫기

if __name__ == "__main__":
    run()
