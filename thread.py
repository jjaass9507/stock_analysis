import threading
import time
import crawler_ajax as cr
import concurrent.futures
from concurrent.futures import as_completed
import pandas as pd
import datetime
import requests
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION_STR = os.environ.get("NEON_DB_URL")
if not DB_CONNECTION_STR:
    raise RuntimeError("請在 .env 或環境變數中設定 NEON_DB_URL")

_ENSURE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_daily_analysis (
    record_date   DATE         NOT NULL,
    code          VARCHAR(10)  NOT NULL,
    close_price   FLOAT,
    volume        INT,
    ma5           FLOAT,
    ma20          FLOAT,
    ub            FLOAT,
    lb            FLOAT,
    bbw_ratio     FLOAT,
    trend_days    INT,
    volume_break  BOOLEAN,
    percent_b     FLOAT,
    bbw_expanding BOOLEAN,
    PRIMARY KEY (record_date, code)
);
ALTER TABLE stock_daily_analysis ADD COLUMN IF NOT EXISTS percent_b     FLOAT;
ALTER TABLE stock_daily_analysis ADD COLUMN IF NOT EXISTS bbw_expanding BOOLEAN;
"""


def _ensure_schema(engine):
    """建立資料表（若不存在）並補齊新增欄位。"""
    with engine.connect() as conn:
        for stmt in _ENSURE_SCHEMA_SQL.strip().split(';'):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()


def _get_analyzed_codes_today(engine):
    """回傳今日已存入 DB 的股票代碼集合，供增量更新跳過使用。"""
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz_tw).date()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT code FROM stock_daily_analysis WHERE record_date = :date"),
            {"date": today}
        )
        return {row[0] for row in result}


def upload_to_neon(all_stock_data):
    """將爬蟲資料轉換為平整格式並上傳至 Neon PostgreSQL。"""
    if not all_stock_data:
        return "沒有資料可上傳"

    print("正在準備上傳資料至 Neon 資料庫...")

    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz_tw).date()

    flat_data = []
    for stock in all_stock_data:
        try:
            last_idx = -1
            ub     = stock['UB'][last_idx]
            lb     = stock['LB'][last_idx]
            ma20   = stock['MA20'][last_idx]
            cprice = stock['cprice'][last_idx]
            vol    = stock['volume'][last_idx]
            vma5   = stock['VMA5'][last_idx]

            bbw1 = round((ub - lb) / ma20, 2) if ma20 and ma20 != 0 else 0

            day = 0
            for j in reversed(range(5)):
                if stock["MA5"][j] > stock["MA20"][j]:
                    day += 1
                else:
                    break

            flat_data.append({
                'record_date':   today,
                'code':          stock['code'],
                'close_price':   float(cprice),
                'volume':        int(vol),
                'ma5':           float(stock['MA5'][last_idx]),
                'ma20':          float(ma20),
                'ub':            float(ub),
                'lb':            float(lb),
                'bbw_ratio':     float(bbw1),
                'trend_days':    int(day),
                'volume_break':  bool(vol > vma5),
                'percent_b':     float(stock.get('percent_b', [0.5] * 5)[last_idx]),
                'bbw_expanding': bool(stock.get('bbw_expanding', False))
            })
        except Exception:
            continue

    if not flat_data:
        return "資料處理後為空，未上傳任何資料。"

    df_db = pd.DataFrame(flat_data)

    try:
        engine = create_engine(DB_CONNECTION_STR)
        _ensure_schema(engine)
        # 先寫入暫存表，再 upsert 至正式表，避免重複 PK 衝突
        df_db.to_sql(
            '_stock_upload_tmp', engine,
            if_exists='replace', index=False,
            method='multi', chunksize=1000
        )
        upsert_sql = text("""
            INSERT INTO stock_daily_analysis
                (record_date, code, close_price, volume, ma5, ma20,
                 ub, lb, bbw_ratio, trend_days, volume_break, percent_b, bbw_expanding)
            SELECT
                record_date::date, code, close_price, volume, ma5, ma20,
                ub, lb, bbw_ratio, trend_days, volume_break, percent_b, bbw_expanding
            FROM _stock_upload_tmp
            ON CONFLICT (record_date, code) DO UPDATE SET
                close_price   = EXCLUDED.close_price,
                volume        = EXCLUDED.volume,
                ma5           = EXCLUDED.ma5,
                ma20          = EXCLUDED.ma20,
                ub            = EXCLUDED.ub,
                lb            = EXCLUDED.lb,
                bbw_ratio     = EXCLUDED.bbw_ratio,
                trend_days    = EXCLUDED.trend_days,
                volume_break  = EXCLUDED.volume_break,
                percent_b     = EXCLUDED.percent_b,
                bbw_expanding = EXCLUDED.bbw_expanding
        """)
        with engine.connect() as conn:
            conn.execute(upsert_sql)
            conn.execute(text("DROP TABLE IF EXISTS _stock_upload_tmp"))
            conn.commit()
        return f"成功更新 {len(df_db)} 筆資料至資料庫！"
    except Exception as e:
        return f"資料庫上傳失敗: {e}"

def result(all_stock_data):
    """
    (保留原功能) 接收所有股票資料，進行分析，並將符合條件的結果寫入 txt 和 xlsx 檔案。
    """
    print("開始分析篩選結果並產生本地檔案...")
    
    filtered_stocks = [] 
    
    for stock_data in all_stock_data:
        # 1. 輸出到 txt 檔
        cr.print_result(stock_data)
        
        # 2. 收集結果準備寫入 Excel
        analysis_result = cr.analyze_stock_strategy(stock_data)
        if analysis_result:
            filtered_stocks.append(analysis_result)

    # 3. 寫入 Excel 檔案
    if filtered_stocks:
        df = pd.DataFrame(filtered_stocks)
        columns_order = [
            '公司代碼', '收盤價', '連續MA5>MA20天數', '成交量是否放大', 
            '布林帶寬((上/下)-1)', '布林帶寬((上-下)/中)', '最新成交量', 
            '5日成交均量', '5日均線', '20日均線'
        ]
        # 確保欄位存在才選取，避免報錯
        valid_columns = [c for c in columns_order if c in df.columns]
        df = df[valid_columns]
        
        excel_filename = f'filtered_stocks_{datetime.date.today()}.xlsx'
        df.to_excel(excel_filename, index=False, engine='openpyxl')
        print(f"Excel 報告已儲存至: {excel_filename}")
    else:
        print("未篩選出符合條件的股票，不生成 Excel 檔案。")

def crawler():
    """
    使用 FinMind API 批量抓取所有台股日交易資料。
    以 1~2 次大量下載取代 2000+ 次個別請求，
    不受 TWSE/TPEX 雲端 IP 封鎖影響。
    """
    finmind_token = os.environ.get("FINMIND_TOKEN", "")
    if not finmind_token:
        raise RuntimeError(
            "請在 .env（本地）或 Render 環境變數中設定 FINMIND_TOKEN。\n"
            "申請網址：https://finmindtrade.com/"
        )

    print("正在從 FinMind API 批量下載台股資料（約 30~90 秒）...")

    with requests.Session() as session:
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        session.mount('https://', adapter)
        stock_map = cr.fetch_all_finmind(finmind_token, session)

    total_stocks = len(stock_map)
    if total_stocks == 0:
        return [], 0

    print(f"收到 {total_stocks} 檔股票資料，計算技術指標中...")

    results = []
    for stock_id, rows in stock_map.items():
        r = cr.process_finmind_stock(stock_id, rows)
        if r:
            results.append(r)

    print(f"計算完成，共 {len(results)} 檔資料足夠。")
    return results, total_stocks

def run_crawler_pipeline():
    """
    [新功能] 專門給 Streamlit 或外部程式呼叫的接口。
    執行完整流程：爬蟲 -> 資料庫上傳。
    回傳一個字串訊息，說明執行結果。
    """
    status_log = []
    try:
        # 1. 執行爬蟲
        all_data, total_attempted = crawler()

        if total_attempted == 0:
            return "✅ 成功：今日資料已是最新，無需重新抓取。"

        if not all_data:
            return (
                f"❌ 爬蟲發出 {total_attempted} 筆請求，但全部回傳空資料。\n"
                "可能原因：① 今日為非交易日（週末/假日）② 交易所 API 封鎖此伺服器 IP"
            )

        status_log.append(f"✅ 爬蟲成功，共抓取 {len(all_data)} / {total_attempted} 檔股票。")

        # 2. 上傳資料庫
        upload_msg = upload_to_neon(all_data)
        status_log.append(f"📤 {upload_msg}")

        return "\n".join(status_log)

    except Exception as e:
        return f"❌ 執行過程中發生嚴重錯誤: {str(e)}"

def main():
    """
    主執行函式 (本地端執行用)
    """
    start_time = time.time()
    
    # 1. 執行爬蟲
    all_data, total_attempted = crawler()

    if not all_data:
        print(f"沒有成功抓取到任何資料（嘗試 {total_attempted} 檔），程式結束。")
        return

    # 2. (本地備份) 將所有資料存成 JSON
    print("正在將所有資料儲存至 JSON 檔案中...")
    df = pd.DataFrame(all_data) 
    code_json = df.to_json(orient="records") 
    file_name = f'list-{datetime.date.today()}.json'
    
    with open(file_name, 'w', encoding='utf-8') as f:
        f.write(code_json)
    print(f"資料已成功儲存至 {file_name}")

    # 3. (本地分析) 產出 Excel 和 Txt
    result(all_data)
    
    # 4. (雲端上傳) 上傳至 Neon 資料庫
    # 如果是在本地測試且有設定好資料庫，這裡也會執行上傳
    print("嘗試上傳至資料庫...")
    msg = upload_to_neon(all_data)
    print(msg)
    
    end_time = time.time()
    print(f"程式執行完畢，總花費 {end_time - start_time:.2f} 秒")

if __name__ == "__main__":
    main()