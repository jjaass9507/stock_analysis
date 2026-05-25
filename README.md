# 台股布林策略選股儀表板

以布林帶（Bollinger Bands）為核心的台股技術分析平台，提供每日選股訊號與互動式儀表板。

---

## 功能

- **布林收口篩選**：自動掃描全市場 ~2,270 檔股票，找出帶寬壓縮中的標的
- **多重確認條件**：MA5 > MA20 多頭趨勢 + 量能突破 + 帶寬擴張確認
- **%B 指標**：顯示收盤價在布林帶中的相對位置（0 = 下軌 / 1 = 上軌）
- **互動式儀表板**：即時篩選、排序、Plotly 散佈圖，無需重新載入頁面
- **官方資料來源**：接 TWSE / TPEX 官方 API，穩定可靠

---

## 技術架構

```
FastAPI (後端)
├── GET  /                    → 儀表板 HTML
├── GET  /api/stocks          → 取得指定日期的分析資料（JSON）
├── GET  /api/available-dates → 有資料的日期清單
├── POST /api/crawl           → 背景執行爬蟲
└── GET  /api/crawl/status    → 查詢爬蟲進度

Alpine.js (前端反應)  ← 篩選 / 排序 / Tab 切換全在瀏覽器端即時運算
Plotly.js (圖表)      ← 互動散佈圖，hover 顯示完整資訊
Neon PostgreSQL       ← 每日分析結果儲存
```

---

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入 NEON_DB_URL
```

### 3. 啟動伺服器

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

開啟瀏覽器：`http://localhost:8000`

---

## 部署（Render）

1. 推送至 GitHub
2. 在 Render 建立 **Web Service**
3. 設定：
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variable**：`NEON_DB_URL` = 你的 Neon 連線字串

---

## 策略邏輯

| 條件 | 說明 |
|---|---|
| 多頭趨勢 | MA5 > MA20 連續 N 天（預設 2 天） |
| 布林收口 | 帶寬比率 `(UB-LB)/MA20` 低於閾值（預設 0.15） |
| 量能突破 | 當日成交量 > 5 日均量 |
| 帶寬擴張 | 今日帶寬 > 昨日帶寬（壓縮結束確認） |

**最強訊號組合**：四個條件同時成立

---

## 專案結構

```
stock_analysis/
├── main.py              # FastAPI 伺服器（路由、API）
├── thread.py            # 爬蟲排程、DB 上傳
├── crawler_ajax.py      # TWSE/TPEX 資料抓取、技術指標計算
├── templates/
│   └── index.html       # 單頁儀表板（Alpine.js + Plotly.js）
├── requirements.txt
├── Procfile             # Render 部署設定
├── .env                 # 本地環境變數（不提交）
└── .env.example         # 環境變數範本
```

---

## 免責聲明

本平台僅提供技術面篩選結果，不構成任何投資建議。股票投資涉及風險，請自行評估並負擔投資決策責任。
