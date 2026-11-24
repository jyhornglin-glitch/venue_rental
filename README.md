# 場地租借預約系統 (Venue Rental System)

慈濟基金會 松山聯絡處 - 場地預約與道場管理系統。
基於 Python Django 架構開發，提供具備響應式設計（RWD Mobile-First）的場地預約、借用管理、狀態審核及道場資源排程系統。

## 🌟 系統特色

- **響應式設計 (RWD)**：支援手機、平板與桌機無縫瀏覽，支援手機掃描 QR Code 快速開啟。
- **權限角色控管 (RBAC)**：支援超級管理員、管理員與一般使用者分級審核與預約管理。
- **靈活資料庫支援**：
  - 本機開發與測試預設使用 SQLite。
  - 生產環境（如 Synology NAS / MariaDB）可透過 `.env` 無縫切換。
- **RESTful API 架構**：前後端分離設計，前端採用原生 Fetch API 與非同步 JSON 交互。
- **時段防呆與衝突檢核**：後端嚴謹驗證同一空間重複預約與時段重疊。

## 🛠 技術棧

- **後端**：Python 3.9+ / Django
- **前端**：HTML5, CSS3, JavaScript (Mobile-First Vanilla JS)
- **資料庫**：SQLite (本機開發) / MariaDB (生產環境)
- **伺服器/部署**：WSGI / Synology NAS Web Station / uWSGI

## 🚀 快速開始

### 1. 複製專案

```bash
git clone https://github.com/jyhornglin-glitch/venue_rental.git
cd venue_rental
```

### 2. 建立並啟動虛擬環境

```bash
python3 -m venv venv
source venv/bin/activate  # macOS / Linux
# 或 venv\Scripts\activate  # Windows
```

### 3. 安裝依賴

```bash
pip install -r requirements.txt
```

### 4. 設定環境變數

複製 `.env.example` 為 `.env` 並配置相關參數：

```bash
cp .env.example .env
```

### 5. 資料庫遷移與建立超級管理員

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. 啟動開發伺服器

```bash
python manage.py runserver
```

開啟瀏覽器前往 [http://127.0.0.1:8000](http://127.0.0.1:8000) 即可開始使用。

## 🌐 Synology NAS 生產環境部署

本專案提供完整的 Synology NAS 部署設定與自動化腳本：
- **Container Manager (Docker Compose)**：推薦方式，環境隔離、開箱即用。
- **一鍵部署腳本**：提供 `deploy_nas.sh` 快速自動配置。
- **詳細圖文與設定說明**：請參閱完整指引文件 [SYNOLOGY_DEPLOYMENT.md](file:///Users/franklin/Documents/場地租借/SYNOLOGY_DEPLOYMENT.md)。

快速啟動（SSH 連線至 NAS 後）：
```bash
git clone https://github.com/jyhornglin-glitch/venue_rental.git
cd venue_rental
bash deploy_nas.sh
```

## 📁 專案結構

```
venue_rental/
├── config/                  # Django 專案全域設定與 URL 路由
├── reservations/            # 場地預約核心應用 (Models, Views, URLs)
├── static/                  # 靜態資源 (CSS, JS, 圖片)
├── templates/               # 前端 HTML 視圖模板
├── .env.example             # 環境變數範例檔
├── requirements.txt         # Python 依賴清單
├── Dockerfile               # 容器化建置設定
├── docker-compose.yml       # Docker Compose 服務編排設定
├── entrypoint.sh            # 容器初始化啟動入口腳本
├── deploy_nas.sh            # Synology NAS 一鍵部署腳本
├── SYNOLOGY_DEPLOYMENT.md   # NAS 完整部署與反向代理操作指引
└── manage.py                # Django CLI 工具
```

## 📄 授權條款

MIT License
