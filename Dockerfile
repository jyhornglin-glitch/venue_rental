FROM python:3.11-slim

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# 安裝基礎相依工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先複製 requirements.txt 以利用 Docker 快取層
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . /app/

# 建立資料保存與靜態檔案目錄並賦予執行權限
RUN mkdir -p /app/data /app/staticfiles && \
    chmod +x /app/entrypoint.sh

EXPOSE 8000

# 健康檢查 (Healthcheck)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
