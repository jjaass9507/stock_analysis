# Changelog

## [未發布]

### 新增
- `main.py`：以 FastAPI 取代 Streamlit，提供 REST API 與單頁儀表板
- `templates/index.html`：全新前端，採用 Alpine.js + Plotly.js + 純 CSS 深色主題
- `Procfile`：Render 部署設定（uvicorn 啟動命令）
- `/api/available-dates` 端點：回傳 DB 中最近 30 天有資料的日期清單
- 表格欄位全部支援點擊排序
- 新增「指標說明」Tab，包含 %B 參考區間說明

### 優化
- 篩選 / 排序在瀏覽器端即時運算（Alpine.js computed），無需呼叫後端
- DB engine 改為單例（Lazy init），避免重複建立連線
- 爬蟲以獨立 daemon thread 執行，前端輪詢 `/api/crawl/status` 顯示進度

---

## [2026-05-25] 短期優化

### 新增
- `%B` 指標：(Close - LB) / (UB - LB)，反映收盤在布林帶中的相對位置
- `bbw_expanding`：今日帶寬 > 昨日帶寬，壓縮結束確認訊號
- 每日增量快取：已分析的股票當日不重複抓取 API
- DB schema 自動遷移（`ALTER TABLE ADD COLUMN IF NOT EXISTS`）

---

## [2026-05-25] 資料來源優化

### 變更
- 資料來源從 Histock 第三方 API 改接 **TWSE / TPEX 官方 API**
  - 上市股票：`twse.com.tw/exchangeReport/STOCK_DAY`
  - 上櫃/興櫃：`tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php`
- 月初資料不足 20 筆時自動補抓上個月
- 執行緒數從 10 降為 5，每次請求內建 0.2s 間隔，配合官方速率限制
- 成交量單位明確換算為張（÷1000）

---

## [2026-05-25] 安全性修正

### 修正
- 資料庫密碼從程式碼移至 `.env`，改用 `python-dotenv` 讀取
- 新增 `.gitignore`（防止 `.env`、資料檔被提交）
- 新增 `.env.example` 作為設定範本
- SQL 查詢改用 SQLAlchemy 參數化語法，修正 SQL injection 風險

### 重構
- `crawler_ajax.py`：移除死掉的全域變數，`getdata()` 改為回傳值
- `thread.py`：`crawler()` 改用 `getdata()` 回傳值，不再依賴共享全域狀態
- `requirements.txt`：修正 UTF-16 編碼問題，新增 `python-dotenv`
