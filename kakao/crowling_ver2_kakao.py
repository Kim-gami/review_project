import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

HEADLESS = False           # 먼저 눈으로 확인 추천
RENDER_WAIT = 2.0
CLICK_WAIT = 0.8
MAX_ROUNDS = 8
SCROLL_STEP = 900
OUTDIR = Path("saved_pages")
ID_FILE = "kakao_review_address.txt"

TEXT_INCLUDE = ["더보기", "리뷰 더보기", "후기 더보기", "자세히 보기", "More", "Read more"]
TEXT_EXCLUDE = ["메뉴", "사진", "영업", "지도", "길찾기", "예약", "전화", "영업시간", "정보"]

def build_driver():
    opts = webdriver.ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1440,2400")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    drv.set_page_load_timeout(40)
    return drv

def dump_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="ignore")

def read_place_ids(file=ID_FILE):
    if not Path(file).exists():
        return []
    with open(file, "r", encoding="utf-8") as f:
        return sorted({line.strip() for line in f if line.strip()})

def safe_click(driver, el):
    for fn in (
        lambda: el.click(),
        lambda: driver.execute_script("arguments[0].click();", el),
        lambda: ActionChains(driver).move_to_element(el).pause(0.1).click().perform(),
    ):
        try:
            fn(); return True
        except Exception:
            continue
    return False

def unclamp_texts(driver):
    """line-clamp/ellipsis 등으로 접힌 텍스트 강제 해제 + 오버레이 제거"""
    js = r"""
    (function(){
      const sels = [
        '[style*="-webkit-line-clamp"]','.ellipsis','.clamp','.line-clamp',
        '.txt_comment','.txt_review','.review','.desc_comment'
      ];
      const nodes = sels.flatMap(s => Array.from(document.querySelectorAll(s)));
      for (const el of nodes) {
        el.style.webkitLineClamp = 'unset';
        el.style.display = 'block';
        el.style.maxHeight = 'none';
        el.style.overflow = 'visible';
        el.style.whiteSpace = 'normal';
      }
      const masks = document.querySelectorAll('.DimmedLayer, .mask, .overlay, .layer_dimmed');
      masks.forEach(m => m.remove());
      return nodes.length;
    })();
    """
    try:
        driver.execute_script(js)
    except Exception:
        pass

def scroll_through(driver, steps=30, step_px=SCROLL_STEP):
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.2)
    last_h = 0
    for _ in range(steps):
        driver.execute_script(f"window.scrollBy(0, {step_px});")
        time.sleep(0.2)
        h = driver.execute_script("return document.body.scrollHeight;")
        if h == last_h:
            break
        last_h = h

def find_review_root(driver):
    """
    '리뷰' 포함 헤딩/탭 기준으로 가장 가까운 컨테이너 반환.
    못 찾으면 review 라벨/ID/클래스 추정, 최후에는 body.
    """
    X = (
        "//*[self::h1 or self::h2 or self::h3 or self::h4 or self::strong or self::span or self::a or self::button]"
        "[contains(normalize-space(.),'리뷰')]"
    )
    heads = driver.find_elements(By.XPATH, X)
    for h in heads:
        try:
            root = h.find_element(By.XPATH, "ancestor::*[self::section or self::article or self::div][1]")
            if root and root.is_displayed():
                return root
        except Exception:
            continue
    # class/id에 review 들어간 컨테이너 후보
    try:
        return driver.find_element(By.XPATH, "//*[contains(translate(@class,'REVIEW','review'),'review') or contains(translate(@id,'REVIEW','review'),'review')]")
    except Exception:
        pass
    # fallback
    return driver.find_element(By.XPATH, "/html/body")

def list_more_candidates_in(root):
    """
    루트 내부의 '더보기' 계열만 수집. 텍스트 포함 + 크기·가시성 필터.
    """
    elems = root.find_elements(By.XPATH, ".//*[self::button or self::a or self::span or self::div]")
    out = []
    seen = set()
    for e in elems:
        try:
            if not e.is_displayed():
                continue
            txt = (e.text or "").strip()
            if not txt:
                continue
            if any(p in txt for p in TEXT_INCLUDE) and not any(x in txt for x in TEXT_EXCLUDE):
                # 너무 큰 버튼(전환/탭류) 배제: 작은 버튼 위주
                rect = e.rect
                if rect.get("width", 200) > 500 or rect.get("height", 60) > 120:
                    continue
                key = (e.tag_name, e.get_attribute("class"), txt)
                if key in seen:
                    continue
                seen.add(key)
                out.append(e)
        except Exception:
            continue
    return out

def wait_content_changed_after_click(driver, before_len_selector_list):
    """
    클릭 후 '펼쳐진 텍스트 길이 증가' 또는 '버튼 사라짐' 같은 변화를 짧게 대기.
    """
    try:
        time.sleep(CLICK_WAIT)
        for sel in before_len_selector_list:
            js = "return Array.from(document.querySelectorAll(arguments[0])).map(x=>x.innerText.length).reduce((a,b)=>a+b,0);"
            before_len = driver.execute_script(js, sel[0])
            # 짧게 더 기다리며 변화 감지
            for _ in range(10):
                time.sleep(0.15)
                after_len = driver.execute_script(js, sel[0])
                if after_len > before_len:
                    return True
        return False
    except Exception:
        return False

def dump_candidates_snapshot(driver, root, outdir: Path, tag_prefix: str):
    """후보 버튼들의 외형/텍스트를 파일로 저장(디버깅용)"""
    cands = list_more_candidates_in(root)
    lines = []
    for i, e in enumerate(cands, 1):
        try:
            outer = driver.execute_script("return arguments[0].outerHTML;", e)
            txt = (e.text or "").strip()
            lines.append(f"[{i}] text='{txt}'\n{outer}\n")
        except Exception:
            continue
    if lines:
        dump_text(outdir / f"{tag_prefix}_more_candidates.txt", "\n\n".join(lines))

def expand_reviews_in_current_context(driver, tag_prefix: str, outdir: Path):
    """
    리뷰 컨텍스트에서 <span class="btn_more">더보기</span> 를 '한 번씩만' 눌러서 펼친 뒤 HTML 저장
    """
    # 화면에 노출되도록 한 번 스크롤만 수행
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.2)
    for _ in range(30):
        driver.execute_script("window.scrollBy(0, 900);")
        time.sleep(0.1)

    # 현재 시점의 btn_more들만 수집 → 한 번씩만 클릭
    btns = driver.find_elements(By.CSS_SELECTOR, "span.btn_more")
    clicked = 0
    for b in btns:
        try:
            if not b.is_displayed():
                continue
            # 보이게 스크롤
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
            time.sleep(0.1)
            # 한 번만 클릭
            if safe_click(driver, b):
                clicked += 1
                time.sleep(0.4)  # 짧게 로딩 대기
                # 다시 토글되는 걸 방지: DOM에서 제거(옵션) 또는 표시만 숨김
                try:
                    driver.execute_script("arguments[0].setAttribute('data-clicked','1');"
                                          "arguments[0].style.pointerEvents='none';"
                                          "arguments[0].style.display='none';", b)
                except Exception:
                    pass
        except Exception:
            continue

    print(f"    * 더보기 1회 클릭 완료: {clicked}개")

    # 펼친 상태로 저장
    html = driver.page_source
    dump_text(outdir / f"{tag_prefix}_expanded.html", html)
# === 아래는 사용 루틴(페이지 열기/iframe 순회) 예시 ===

def process_place(driver, place_id: str):
    url = f"https://place.map.kakao.com/{place_id}#review"
    target_dir = OUTDIR / place_id
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[OPEN] {url}")
    driver.get(url)
    time.sleep(RENDER_WAIT)

    # 메인 문서 (혹시라도 여기에 리뷰가 있으면 대비)
    try:
        expand_reviews_in_current_context(driver, "page", target_dir)
    except Exception as e:
        print("  - 메인 확장 중 예외:", e)
        dump_text(target_dir / "page_expanded.html", driver.page_source)

    # 모든 iframe 순회
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"  - iframe 개수: {len(iframes)}")
    for idx, iframe in enumerate(iframes):
        try:
            src = iframe.get_attribute("src")
            print(f"    [iframe {idx}] src={src}")
            WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_frame(iframe))
            time.sleep(RENDER_WAIT)
            expand_reviews_in_current_context(driver, f"iframe_{idx}", target_dir)
        except Exception as e:
            print(f"    - iframe {idx} 처리 중 예외:", e)
        finally:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

def main():
    ids = read_place_ids()
    if not ids:
        print("place_ids.txt 를 준비해 주세요. (한 줄당 하나의 ID)"); return
    OUTDIR.mkdir(parents=True, exist_ok=True)
    drv = build_driver()
    try:
        for i, pid in enumerate(ids, 1):
            print(f"\n[{i}/{len(ids)}] ID={pid}")
            try:
                process_place(drv, pid)
            except Exception as e:
                print(f"  - 실패: {pid} ({e})")
            time.sleep(1.0)
    finally:
        drv.quit()

if __name__ == "__main__":
    main()
