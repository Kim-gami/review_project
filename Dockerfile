# ===== Base =====
FROM python:3.11-slim

# ===== System packages =====
# - chromium / chromium-driver: 크롬 & 드라이버
# - 필수 X/GTK/오디오/글꼴 라이브러리
# - tzdata: 타임존
# - fonts-noto-cjk & fonts-nanum: 한글 폰트 (크롤링/렌더링 시 깨짐 방지)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    libglib2.0-0 libnss3 libasound2 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 \
    libxdamage1 libxrandr2 libxi6 libxtst6 \
    libpangocairo-1.0-0 libgtk-3-0 libgbm1 libxshmfence1 libdrm2 \
    fonts-noto-cjk fonts-nanum \
    build-essential tzdata curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# ===== Workdir =====
WORKDIR /app

# ===== Python deps =====
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===== App source =====
COPY . .

# ===== Environment for Selenium =====
# 기본 경로 고정해두면 코드에서 경로 하드코딩 없이 env만 읽으면 됨
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER=/usr/bin/chromedriver

# ===== Logging / Buffering =====
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_RUN_ON_SAVE=true

# ===== Streamlit =====
ENV PORT=8501
EXPOSE 8501

# ===== Non-root user (권장) =====
RUN useradd -m appuser
USER appuser

# ===== Entrypoint =====
# front_DB4.py 기준으로 실행
CMD ["streamlit", "run", "mobile_lunch_hg.py", "--server.port=8501", "--server.address=0.0.0.0"]
