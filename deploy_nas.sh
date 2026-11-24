#!/bin/bash
# ==============================================================================
# Synology NAS 場地租借預約系統一鍵部署腳本
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=================================================="
echo "  慈濟松山聯絡處 場地租借預約系統 - NAS 部署作業"
echo "=================================================="

# 1. 檢查 .env 環境變數檔
if [ ! -f ".env" ]; then
    echo "⚠️ 尚未偵測到 .env 檔案，正在從 .env.example 建立預設範本..."
    cp .env.example .env
    # 自動產生隨機 SECRET_KEY
    RANDOM_KEY=$(openssl rand -base64 32 2>/dev/null || cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 50 | head -n 1)
    sed -i.bak "s/your-secret-key-here-please-change-in-production/${RANDOM_KEY}/" .env 2>/dev/null || true
    rm -f .env.bak
    echo "✅ 已建立 .env 檔案。請記得確認 ALLOWED_HOSTS 與 CSRF_TRUSTED_ORIGINS 是否符合您的 NAS 網址或 IP。"
fi

# 2. 建立必要資料夾
mkdir -p data staticfiles

# 3. 部署模式選擇：Docker Compose 或 原生 Python venv
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    echo "🐳 偵測到 Docker & Docker Compose 環境！"
    read -p "是否使用 Docker Compose 進行容器化部署？ (Y/n): " USE_DOCKER
    USE_DOCKER=${USE_DOCKER:-Y}
    if [[ "$USE_DOCKER" =~ ^[Yy]$ ]]; then
        echo "🚀 正在使用 Docker Compose 建置並啟動服務..."
        docker compose down --remove-orphans 2>/dev/null || true
        docker compose build
        docker compose up -d
        echo ""
        echo "🎉 Docker 容器部署完成！服務已在 Port 8000 運行。"
        echo "💡 您可以使用以下指令查看執行日誌："
        echo "   docker compose logs -f"
        echo "💡 建立超級管理員指令："
        echo "   docker compose exec venue_web python manage.py createsuperuser"
        exit 0
    fi
fi

# 原生 Python 部署流程
echo "🐍 執行原生 Python 虛擬環境部署..."

PYTHON_BIN="python3"
if ! command -v $PYTHON_BIN &> /dev/null; then
    echo "❌ 找不到 python3，請先於 Synology 套件中心安裝 Python 3。"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "📦 正在建立 Python 虛擬環境 (venv)..."
    $PYTHON_BIN -m venv venv
fi

echo "🔄 啟用虛擬環境並升級 pip..."
source venv/bin/activate
pip install --upgrade pip

echo "📥 安裝相依套件..."
pip install -r requirements.txt

echo "🗄️ 執行資料庫結構遷移..."
python manage.py migrate

echo "🎨 收集靜態資源 (WhiteNoise)..."
python manage.py collectstatic --noinput

echo ""
echo "=================================================="
echo "🎉 專案初始化與建置完成！"
echo "=================================================="
echo "您可以透過 Gunicorn 啟動服務："
echo "   nohup venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --daemon &"
echo ""
echo "若要建立超級管理員，請執行："
echo "   venv/bin/python manage.py createsuperuser"
echo "=================================================="
