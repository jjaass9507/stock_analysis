from fastapi import FastAPI, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
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


# ─── 個股 K 線圖 ──────────────────────────────────────────────────────────
@app.get("/api/stock/{code}/kline")
async def stock_kline(code: str):
    import crawler_ajax as cr
    data = cr.fetch_kline_data(code.upper())
    if data is None:
        return JSONResponse({"error": f"無法取得 {code} 的K線資料"}, status_code=404)
    return data


# ─── 歷史回測 ────────────────────────────────────────────────────────────
class BacktestParams(BaseModel):
    min_trend: int = 2
    max_bbw: float = 0.15
    only_vol: bool = True
    only_exp: bool = False
    stop_loss: float = 0.07
    take_profit: float = 0.15
    max_hold_days: int = 20
    start_date: str
    end_date: str


@app.post("/api/backtest")
async def run_backtest(params: BacktestParams):
    try:
        query = text("""
            SELECT record_date::text, code,
                   close_price::float, ma5::float, ma20::float,
                   bbw_ratio::float, trend_days::int,
                   volume_break::boolean, bbw_expanding::boolean
            FROM stock_daily_analysis
            WHERE record_date BETWEEN :start_date AND :end_date
            ORDER BY record_date, code
        """)
        df = pd.read_sql(query, get_engine(), params={
            'start_date': params.start_date,
            'end_date':   params.end_date,
        })
        if df.empty:
            return {"trades": [], "equity_curve": [], "stats": {
                "total": 0, "win_rate": 0.0, "avg_pnl": 0.0,
                "max_drawdown": 0.0, "final_equity": 10000.0
            }}

        df['volume_break']  = df['volume_break'].fillna(False).astype(bool)
        df['bbw_expanding'] = df['bbw_expanding'].fillna(False).astype(bool)
        df['bbw_ratio']     = df['bbw_ratio'].fillna(999.0)
        df['trend_days']    = df['trend_days'].fillna(0).astype(int)

        positions  = {}   # code → {entry_date, entry_price, days}
        trades     = []
        equity     = 10000.0
        equity_curve = []

        for date in sorted(df['record_date'].unique()):
            day      = df[df['record_date'] == date]
            day_dict = {r['code']: r for _, r in day.iterrows()}

            # 持倉天數 +1（含今天）
            for pos in positions.values():
                pos['days'] += 1

            # 檢查出場
            for code in list(positions.keys()):
                if code not in day_dict:
                    continue
                row   = day_dict[code]
                pos   = positions[code]
                price = float(row['close_price'])
                entry = pos['entry_price']
                if entry == 0:
                    del positions[code]; continue
                pnl = (price - entry) / entry

                reason = None
                if   pnl <= -params.stop_loss:          reason = '停損'
                elif pnl >= params.take_profit:          reason = '停利'
                elif float(row['ma5']) < float(row['ma20']): reason = 'MA死叉'
                elif pos['days'] >= params.max_hold_days:    reason = '到期'

                if reason:
                    trades.append({
                        'code':        code,
                        'entry_date':  pos['entry_date'],
                        'exit_date':   date,
                        'entry_price': round(entry, 2),
                        'exit_price':  round(price, 2),
                        'pnl_pct':     round(pnl * 100, 2),
                        'hold_days':   pos['days'],
                        'exit_reason': reason,
                    })
                    equity += 100 * pnl   # 每筆固定投入 $100
                    del positions[code]

            equity_curve.append({'date': date, 'equity': round(equity, 2)})

            # 掃新訊號（下一個交易日開始檢查出場）
            for code, row in day_dict.items():
                if code in positions:
                    continue
                if int(row['trend_days']) < params.min_trend:
                    continue
                if float(row['bbw_ratio']) > params.max_bbw:
                    continue
                if params.only_vol and not bool(row['volume_break']):
                    continue
                if params.only_exp and not bool(row['bbw_expanding']):
                    continue
                positions[code] = {
                    'entry_date':  date,
                    'entry_price': float(row['close_price']),
                    'days': 0,
                }

        if not trades:
            return {"trades": [], "equity_curve": equity_curve, "stats": {
                "total": 0, "win_rate": 0.0, "avg_pnl": 0.0,
                "max_drawdown": 0.0, "final_equity": round(equity, 2)
            }}

        pnls = [t['pnl_pct'] for t in trades]
        wins = sum(1 for p in pnls if p > 0)

        eq_vals  = [e['equity'] for e in equity_curve]
        peak     = eq_vals[0]
        max_dd   = 0.0
        for v in eq_vals:
            if v > peak: peak = v
            dd = (peak - v) / peak * 100
            if dd > max_dd: max_dd = dd

        return {
            'trades':       sorted(trades, key=lambda t: t['entry_date'], reverse=True),
            'equity_curve': equity_curve,
            'stats': {
                'total':        len(trades),
                'win_rate':     round(wins / len(trades) * 100, 1),
                'avg_pnl':      round(sum(pnls) / len(pnls), 2),
                'max_drawdown': round(max_dd, 2),
                'final_equity': round(equity, 2),
            },
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
