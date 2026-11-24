# Synology NAS (DSM 7.x) 完整部署指南

本手冊說明如何將「慈濟松山聯絡處 場地租借預約系統」部署至 Synology NAS。
系統已支援 **Docker / Container Manager 容器化部署（強烈推薦）** 與 **Web Station / 原生 Python 環境** 兩種方式。

---

## 目錄
1. [前置準備與套件安裝](#1-前置準備與套件安裝)
2. [【推薦】方案一：使用 Container Manager (Docker Compose) 部署](#2-推薦方案一使用-container-manager-docker-compose-部署)
   - [方法 A：DSM 圖形介面操作](#方法-a透過-dsm-container-manager-圖形介面)
   - [方法 B：透過 SSH 終端機一鍵部署](#方法-b透過-ssh-終端機一鍵腳本)
3. [方案二：使用 Web Station / 原生 Python 部署](#3-方案二使用-web-station--原生-python-部署)
4. [Synology 反向代理伺服器 (Reverse Proxy) 與 SSL 憑證設定](#4-synology-反向代理伺服器-reverse-proxy-與-ssl-憑證設定)
5. [常見問題與避坑指南 (FAQ)](#5-常見問題與避坑指南-faq)

---

## 1. 前置準備與套件安裝

請登入 Synology DSM 控制台，開啟 **「套件中心」**，依據您選用的部署方案安裝相應套件：

- **若使用容器化部署（推薦）**：
  - 安裝 **Container Manager**（DSM 7.2+ 原 Docker 套件）。
  - （可選）若欲使用外部資料庫，安裝 **MariaDB 10** 與 **phpMyAdmin**。
- **若使用原生 Python 部署**：
  - 安裝 **Python 3**、**Web Station**、**MariaDB 10**、**phpMyAdmin**。

---

## 2. 【推薦】方案一：使用 Container Manager (Docker Compose) 部署

容器化部署具有環境隔離、升級不破壞 DSM 系統、重開機自動啟動等優點。

### 方法 A：透過 DSM Container Manager 圖形介面

1. **建立專案資料夾**：
   - 開啟 **File Station**。
   - 在 `docker` 共用資料夾下建立一個新目錄，例如 `/docker/venue_rental`。
   - 在 `/docker/venue_rental` 中建立 `data` 目錄（路徑為 `/docker/venue_rental/data`），用以保存資料庫。

2. **上傳專案檔案**：
   - 將專案原始碼上傳至 `/docker/venue_rental`（包含 `Dockerfile`、`docker-compose.yml`、`entrypoint.sh`、`requirements.txt`、`config/`、`reservations/`、`templates/`、`static/`）。

3. **配置 `.env` 環境變數**：
   - 複製 `.env.example` 為 `.env`。
   - 編輯 `.env`：
     ```ini
     SECRET_KEY=產生一組長度32以上的隨機字串
     DEBUG=False
     # 請填寫您的 NAS IP 或 Synology DDNS 網域名稱
     ALLOWED_HOSTS=127.0.0.1,localhost,your-nas.synology.me,192.168.1.100
     # 反向代理必備（必須帶 http:// 或 https://）
     CSRF_TRUSTED_ORIGINS=https://your-nas.synology.me,http://192.168.1.100:8000
     
     # 資料庫設定 (預設使用容器內持久化 SQLite，直接設 False 即可；若要切換 MariaDB 請設 True)
     USE_MARIADB=False
     ```

4. **在 Container Manager 建立專案**：
   - 開啟 **Container Manager** -> 點選左側 **「專案 (Project)」** -> 點擊 **「新增」**。
   - 專案名稱輸入：`venue-rental`。
   - 路徑選擇：`/docker/venue_rental`。
   - 來源：選擇 **「使用現有的 docker-compose.yml 建立專案」**。
   - 點擊「下一步」並完成建置，系統將自動建置 Image 並啟動容器。

---

### 方法 B：透過 SSH 終端機一鍵腳本

如果您習慣使用 SSH 終端機連入 NAS：

1. **SSH 登入 NAS**：
   ```bash
   ssh admin_user@192.168.1.100
   ```

2. **進入存放目錄並 Clone / 下載專案**：
   ```bash
   cd /volume1/docker
   git clone https://github.com/jyhornglin-glitch/venue_rental.git
   cd venue_rental
   ```

3. **執行一鍵部署腳本**：
   ```bash
   bash deploy_nas.sh
   ```
   腳本會自動檢查環境、產生 `.env`、透過 Docker Compose 建置並啟動服務！

4. **建立超級管理員帳號 (Superuser)**：
   ```bash
   docker compose exec venue_web python manage.py createsuperuser
   ```
   依提示輸入管理員帳號、電子郵件與密碼。

---

## 3. 方案二：使用 Web Station / 原生 Python 部署

若您的 NAS 機型不支援 Docker，可使用原生 Python 虛擬環境：

1. 透過 SSH 登入 NAS 並切換至專案路徑：
   ```bash
   cd /volume1/web/venue_rental
   ```

2. 建立 Python 虛擬環境並安裝相依套件：
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. 設定 `.env` 檔案（填入金鑰、`ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS` 及 MariaDB 參數）。

4. 執行資料庫遷移與靜態資源收集：
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py createsuperuser
   ```

5. 使用 Gunicorn 於背景常駐（可搭配 DSM「控制台」->「工作排程器」設定開機自動啟動）：
   ```bash
   nohup /volume1/web/venue_rental/venv/bin/gunicorn config.wsgi:application \
       --bind 127.0.0.1:8000 \
       --workers 3 \
       --timeout 120 \
       --daemon > /volume1/web/venue_rental/gunicorn.log 2>&1 &
   ```

---

## 4. Synology 反向代理伺服器 (Reverse Proxy) 與 SSL 憑證設定

為了讓使用者能透過標準 HTTPS (443) 埠號或自訂網域名稱（免記 `:8000` 連接埠）安全瀏覽，請在 DSM 設定反向代理：

1. 前往 **DSM 控制台** -> **登入入口 (Login Portal)** -> **進階 (Advanced)**。
2. 點選 **「反向代理伺服器 (Reverse Proxy)」** -> **「新增」**。
3. **一般設定**：
   - **反向代理名稱**：`場地預約系統`
   - **來源 (Source)**：
     - 通訊協定：`HTTPS`
     - 主機名稱：您的網域名稱（例如 `venue.your-domain.synology.me`）
     - 連接埠：`443`
     - 勾選「啟用 HSTS」
   - **目的地 (Destination)**：
     - 通訊協定：`HTTP`
     - 主機名稱：`localhost` 或 `127.0.0.1`
     - 連接埠：`8000`
4. **自訂標頭 (Custom Header)**：
   - 點擊「新增」-> 選擇 **「WebSocket」**（系統會自動帶入 `Upgrade` 與 `Connection` 標頭）。
5. 點擊 **「儲存」**。
6. 前往 **控制台** -> **安全性** -> **憑證**，確保將 Let's Encrypt SSL 憑證指派給該反向代理服務。

---

## 5. 常見問題與避坑指南 (FAQ)

### Q1: 送出登入或預約時出現 `403 Forbidden - CSRF verification failed`？
- **原因**：Django 4.2+ 要求跨網域或 HTTPS 反向代理必須明確聲明來源。
- **解法**：檢查 `.env` 中的 `CSRF_TRUSTED_ORIGINS`，必須包含前綴協定 `https://`，例如：
  `CSRF_TRUSTED_ORIGINS=https://venue.your-domain.synology.me,http://192.168.1.100:8000`

### Q2: 頁面樣式遺失或靜態檔案顯示 404？
- **解法**：本專案已全面整合 **WhiteNoise**。
  - Docker Compose 會在每次啟動時自動執行 `python manage.py collectstatic --noinput`。
  - 若為手動部署，請確認已執行上述收集指令，且 `staticfiles` 資料夾具有讀取權限。

### Q3: 如何切換為 Synology 的 MariaDB 10 套件？
1. 開啟 **phpMyAdmin**，建立資料庫（例如 `venue_db`，編碼選擇 `utf8mb4_unicode_ci`）。
2. 建立專用使用者（例如 `venue_user`）並給予該資料庫完整權限。
3. 修改 `.env`：
   ```ini
   USE_MARIADB=True
   DB_NAME=venue_db
   DB_USER=venue_user
   DB_PASSWORD=您的密碼
   DB_HOST=172.17.0.1   # 若從 Docker 容器連 NAS 本機，請填 Docker 閘道 IP 或 NAS 區網 IP；若本機原生部署請填 127.0.0.1
   DB_PORT=3307         # Synology MariaDB 10 預設連接埠為 3307
   ```
4. 重新啟動服務並執行 `python manage.py migrate`。

### Q4: 如何備份資料？
- **SQLite 模式**：直接備份 `/docker/venue_rental/data/db.sqlite3` 檔案即可。
- **MariaDB 模式**：使用 phpMyAdmin 匯出 `venue_db` 或使用 DSM Hyper Backup 套件備份 MariaDB 10。
