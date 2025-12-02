import threading
import time
import crawler_ajax as cr
import concurrent.futures
from concurrent.futures import as_completed
import pandas as pd
import datetime
import requests
import os
from sqlalchemy import create_engine

# --- 設定資料庫連線 ---
# 建議將真實的連線字串設定在環境變數中，或者 Streamlit 的 secrets 裡
# 格式範例: "postgresql://neondb_owner:password@ep-something.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
DB_CONNECTION_STR = os.environ.get(
    "NEON_DB_URL", 
    "postgresql://neondb_owner:npg_4iLDkK9UWIgr@ep-cold-king-a4w2omct-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

def upload_to_neon(all_stock_data):
    """
    將爬蟲抓到的原始資料轉換為平整的格式，並上傳到 Neon PostgreSQL 資料庫。
    """
    if not all_stock_data:
        return "沒有資料可上傳"

    print("正在準備上傳資料至 Neon 資料庫...")
    
    flat_data = []
    # 設定時區為台灣時間 (UTC+8)，避免雲端主機時間造成日期錯誤
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz_tw).date()
    
    for stock in all_stock_data:
        try:
            # 取得該股票最後一天(最新)的索引
            # crawler_ajax 回傳的 cprice, MA5 等欄位都是長度為 5 的 list，取 -1 代表最新
            last_idx = -1 
            
            # 取得數值
            ub = stock['UB'][last_idx]
            lb = stock['LB'][last_idx]
            ma20 = stock['MA20'][last_idx]
            cprice = stock['cprice'][last_idx]
            vol = stock['volume'][last_idx]
            vma5 = stock['VMA5'][last_idx]
            
            # 計算布林帶寬指標
            # 避免除以 0 的錯誤
            bbw1 = round((ub - lb) / ma20, 2) if ma20 and ma20 != 0 else 0
            
            # 計算趨勢天數 (重用 crawler_ajax 的邏輯)
            day = 0
            for j in reversed(range(5)):
                if stock["MA5"][j] > stock["MA20"][j]:
                    day += 1
                else:
                    break
            
            # 整理成資料庫的一列 (Row)
            row = {
                'record_date': today,
                'code': stock['code'],
                'close_price': float(cprice),
                'volume': int(vol),
                'ma5': float(stock['MA5'][last_idx]),
                'ma20': float(ma20),
                'ub': float(ub),
                'lb': float(lb),
                'bbw_ratio': float(bbw1),
                'trend_days': int(day),
                'volume_break': bool(vol > vma5)
            }
            flat_data.append(row)
            
        except Exception as e:
            # 若單一股票資料有缺漏，印出錯誤但不中斷整個流程
            # print(f"處理股票 {stock.get('code', 'Unknown')} 時發生錯誤: {e}")
            continue

    if not flat_data:
        return "資料處理後為空，未上傳任何資料。"

    # 轉為 Pandas DataFrame
    df_db = pd.DataFrame(flat_data)
    
    try:
        # 建立資料庫連線引擎
        engine = create_engine(DB_CONNECTION_STR)
        
        # 使用 pandas 的 to_sql 寫入
        # if_exists='append': 若表存在則新增資料
        # index=False: 不將 pandas 的 index 寫入
        # method='multi': 批量插入，效能較好
        df_db.to_sql('stock_daily_analysis', engine, if_exists='append', index=False, method='multi', chunksize=1000)
        
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
    (保留原功能) 爬取所有公司代碼，並使用多執行緒及 requests.Session 抓取每支股票的詳細資料。
    """
    print("正在抓取所有上市櫃公司代碼...")
    # 呼叫 crawler_ajax.py 的函式抓取代碼
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=5")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2")
    
    company_codes = cr.companycode
    total_companies = len(company_codes)
    print(f"代碼抓取完成，共 {total_companies} 家公司。")
    print("開始使用多執行緒爬取個股資料 (已啟用 Session)...")
    
    local_time = int(time.mktime(time.localtime()))
    crawled_results = []
    
    # 建立 Session 以重複利用 TCP 連線，提升爬蟲速度
    with requests.Session() as session:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor: 
            tasks = {}
            for code in company_codes:
                url = f"https://histock.tw/Stock/tv/udf.asmx/history?symbol={code}&resolution=D&from=1609430400&to={local_time}"
                # 提交任務，傳入 session
                task = executor.submit(cr.getajaxdata, url, code, session)
                tasks[task] = code
                
            count = 0
            for future in as_completed(tasks):
                count += 1
                stock_result = future.result()
                if stock_result:
                    crawled_results.append(stock_result)
                
                # 簡單進度條
                if count % 50 == 0:
                    print(f"進度: {count}/{total_companies}", end='\r')

    print(f"\n所有個股資料爬取完成，共成功 {len(crawled_results)} 筆。")
    return crawled_results

def run_crawler_pipeline():
    """
    [新功能] 專門給 Streamlit 或外部程式呼叫的接口。
    執行完整流程：爬蟲 -> 資料庫上傳。
    回傳一個字串訊息，說明執行結果。
    """
    status_log = []
    try:
        # 1. 執行爬蟲
        all_data = crawler()
        
        if not all_data:
            return "❌ 爬蟲執行完畢，但未抓取到任何資料。"
        
        status_log.append(f"✅ 爬蟲成功，共抓取 {len(all_data)} 檔股票。")
        
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
    all_data = crawler()
    
    if not all_data:
        print("沒有成功抓取到任何資料，程式結束。")
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