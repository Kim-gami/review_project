import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

def make_chrome(headless=True, width=1300, height=950):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--window-size={width},{height}")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-tools")
    opts.add_argument("--no-zygote")
    opts.add_argument("--remote-debugging-port=9222")

    # chromium 바이너리 경로 지정
    for bin_path in ["/usr/bin/chromium", "/usr/bin/chromium-browser"]:
        if shutil.which(bin_path):
            opts.binary_location = bin_path
            break

    # chromedriver 경로 탐색
    driver_path = None
    for path in ["/usr/bin/chromedriver",
                 "/usr/lib/chromium/chromedriver",
                 "/usr/lib/chromium-browser/chromedriver"]:
        if shutil.which(path):
            driver_path = path
            break
    if not driver_path:
        raise RuntimeError("chromedriver 경로를 찾을 수 없습니다. packages.txt 설정 확인 필요")

    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=opts)
    driver.implicitly_wait(0)
    return driver
