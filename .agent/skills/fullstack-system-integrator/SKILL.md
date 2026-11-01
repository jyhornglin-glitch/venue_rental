---
name: fullstack-system-integrator
description: 全端系統開發與服務整合。當使用者提到「全端開發」、「資料庫整合」、「RWD 網頁」、「Django API」、「本機測試到 NAS 部署」、「場地預約或管理系統」時自動觸發。
---

# Full-Stack System Integrator

## Summary
用於自動化生成包含 Python (Django) 後端、關聯式資料庫（SQLite/MariaDB）以及跨裝置 RWD Web UI 的資訊系統，並支援從本機測試至 Synology Web Station 的部署流程。

## Workflow Steps
1. 階段一：專案骨架與環境變數 (.env) 配置
2. 階段二：資料模型 (models.py) 與業務約束 (clean 驗證)
3. 階段三：RESTful API (views.py) 與權限控管 (RBAC)
4. 階段四：原生 RWD 前端頁面 (templates/index.html) 串接 Fetch API
5. 階段五：Synology MariaDB 與 WSGI 部署設定

## Development Rules
- 每次實作必須分階段進行，完成一階段測試後再進行下一階段。
- 前端一律採 Mobile-First 設計，不得使用固定寬度，支援手機掃描 QR Code 使用。
- 資料庫連線一律使用環境變數隔離，禁止寫死密碼。

## Architecture & Technical Standards
- **後端框架**：Python 生態系（如 Django / Django REST Framework），具備明確關聯模型、權限控管與資料驗證。
- **資料庫策略**：本機開發與自動化測試使用 SQLite；線上環境使用 MariaDB。
- **前端介面**：原生 HTML5 + CSS3 + JavaScript，採 Mobile-First RWD 設計（Flexbox / Grid），無需安裝 App，掃描 QR Code 即可使用。
- **API 設計**：遵循 RESTful 風格，使用 JSON 格式交互，具備明確 HTTP 狀態碼與錯誤處理機制。
- **部署流程**：本機驗證通過後提交版本控制 (GitHub)，再部署至 Synology Web Station (WSGI/uWSGI)。

## Critical Gotchas
- **Viewport 與縮放**：前端頁面必須包含 `<meta name="viewport" content="width=device-width, initial-scale=1.0">`，確保行動裝置版面正常呈現。
- **機敏資訊管理**：嚴禁寫死資料庫密碼或 SECRET_KEY，一律透過 `.env` 讀取。
- **CORS 與 ALLOWED_HOSTS**：須針對本機測試與 NAS 反向代理或網域名稱正確設定，避免請求受阻。
- **靜態檔案路徑**：確保靜態資源使用框架 static 標籤或相對路徑，以支援 Synology Web Station 子路徑或反向代理配置。
