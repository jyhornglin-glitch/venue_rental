#!/bin/sh
set -e

echo "=== [1/3] 執行資料庫遷移 (migrate) ==="
python manage.py migrate --noinput

echo "=== [2/3] 收集靜態檔案 (collectstatic) ==="
python manage.py collectstatic --noinput

echo "=== [3/3] 啟動 Gunicorn WSGI 伺服器 ==="
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
