from fastapi import FastAPI, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, text
import pandas as pd
import datetime
import os
import threading
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="布林策略儀表板", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")

DB_CONNECTION_STR = os.environ.get("NEON_DB_URL")

# ─── DB engine（單例，延遲初始化）────────────────────────────────────────
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_CONNECTION_STR, pool_pre_ping=True, pool_size=5)
    return _engine


# ─── 爬蟲狀態（執行緒共享）──────────────────────────────────────────────
_crawler = {"running": False, "message": "尚未執行", "success": False}


def _run_crawler():
    import thread as crawler_thread
    global _crawler
    try:
        msg = crawler_thread.run_crawler_pipeline()
        _crawler.update(running=False, message=msg, success="成功" in msg)
    except Exception as e:
        _crawler.update(running=False, message=f"執行失敗：{e}", success=False)


# ─── 路由 ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/stocks")
async def get_stocks(date: str = Query(default=None)):
    if not date:
        tz_tw = datetime.timezone(datetime.timedelta(hours=8))
        date = datetime.datetime.now(tz_tw).date().isoformat()
    try:
        query = text("""
            SELECT code, close_price, volume, ma5, ma20,
                   ub, lb, bbw_ratio, trend_days,
                   volume_break, percent_b, bbw_expanding
            FROM stock_daily_analysis
            WHERE record_date = :date
            ORDER BY bbw_ratio ASC
        """)
        df = pd.read_sql(query, get_engine(), params={"date": date})
        df["volume_break"]  = df["volume_break"].fillna(False).astype(bool)
        df["bbw_expanding"] = df["bbw_expanding"].fillna(False).astype(bool)
        df["percent_b"]     = df["percent_b"].fillna(0.0).clip(0, 1)
        df = df.fillna(0)
        return df.to_dict(orient="records")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/available-dates")
async def available_dates():
    """回傳 DB 中有資料的日期清單（最近 30 天）。"""
    try:
        query = text("""
            SELECT DISTINCT record_date
            FROM stock_daily_analysis
            ORDER BY record_date DESC
            LIMIT 30
        """)
        with get_engine().connect() as conn:
            rows = conn.execute(query).fetchall()
        return [str(r[0]) for r in rows]
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/crawl")
async def start_crawl():
    if _crawler["running"]:
        return {"status": "running", "message": "爬蟲已在執行中，請稍候"}
    _crawler.update(running=True, message="正在爬取 TWSE / TPEX 資料，約需 5–10 分鐘…", success=False)
    threading.Thread(target=_run_crawler, daemon=True).start()
    return {"status": "started", "message": "爬蟲已啟動，請稍候…"}


@app.get("/api/crawl/status")
async def crawl_status():
    return _crawler
