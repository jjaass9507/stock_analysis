
from sqlalchemy import create_engine
import threading
import time
import crawler_ajax as cr
import concurrent.futures
from concurrent.futures import as_completed
import pandas as pd
import datetime
import requests

# 設定您的 Neon 資料庫連線字串 (建議設為環境變數，或暫時寫在這裡)
# 注意：若使用 sqlalchemy，連線字串開頭須為 postgresql:// 而非 postgres://
DB_CONNECTION_STR = "postgresql://neondb_owner:npg_4iLDkK9UWIgr@ep-cold-king-a4w2omct-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def upload_to_neon(all_stock_data):
    """
    將爬蟲抓到的原始資料轉換為平整的格式，並上傳到 Neon 資料庫
    """
    print("正在準備上傳資料至 Neon 資料庫...")
    
    flat_data = []
    today = datetime.date.today()
    
    for stock in all_stock_data:
        try:
            # 取得該股票最後一天的索引 (通常是 -1)
            # 注意：您的 crawler_ajax.py 回傳的 cprice 等欄位是 list，取最後一個值代表最新
            last_idx = -1 
            
            # 簡單計算帶寬供資料庫儲存
            ub = stock['UB'][last_idx]
            lb = stock['LB'][last_idx]
            ma20 = stock['MA20'][last_idx]
            bbw1 = round((ub - lb) / ma20, 2) if ma20 != 0 else 0
            
            # 計算趨勢天數 (重用您原本的邏輯)
            day = 0
            for j in reversed(range(5)):
                if stock["MA5"][j] > stock["MA20"][j]:
                    day += 1
                else:
                    break
            
            row = {
                'record_date': today,
                'code': stock['code'],
                'close_price': stock['cprice'][last_idx],
                'volume': stock['volume'][last_idx],
                'ma5': stock['MA5'][last_idx],
                'ma20': stock['MA20'][last_idx],
                'ub': ub,
                'lb': lb,
                'bbw_ratio': bbw1,
                'trend_days': day,
                'volume_break': stock['volume'][last_idx] > stock['VMA5'][last_idx]
            }
            flat_data.append(row)
        except Exception as e:
            # 略過資料不全的個股
            continue

    if not flat_data:
        print("沒有可上傳的資料。")
        return

    # 轉為 DataFrame
    df_db = pd.DataFrame(flat_data)
    
    # 建立資料庫連線引擎
    engine = create_engine(DB_CONNECTION_STR)
    
    try:
        # 使用 pandas 的 to_sql 快速寫入
        # if_exists='append' 表示若表存在則新增資料
        # index=False 表示不將 pandas 的 index 寫入
        df_db.to_sql('stock_daily_analysis', engine, if_exists='append', index=False, method='multi', chunksize=1000)
        print(f"成功上傳 {len(df_db)} 筆資料至 Neon！")
    except Exception as e:
        print(f"上傳失敗: {e}")
        # 這裡可以加入處理重複 Key 的邏輯，或者在 SQL 使用 ON CONFLICT (進階)

def result(all_stock_data):
    """
    接收所有股票資料，進行分析，並將符合條件的結果寫入 txt 和 xlsx 檔案。
    """
    print("開始分析篩選結果...")
    
    filtered_stocks = [] # 建立一個空列表，用來收集符合條件的股票
    
    # 遍歷所有抓取到的股票資料
    for stock_data in all_stock_data:
        # 1. 保持原有功能，將結果輸出到 txt 檔
        cr.print_result(stock_data)
        
        # 2. 呼叫分析函式，以收集結果準備寫入 Excel
        analysis_result = cr.analyze_stock_strategy(stock_data)
        if analysis_result:
            filtered_stocks.append(analysis_result)

    print(f"分析完成！共篩選出 {len(filtered_stocks)} 支符合條件的股票。")

    # 3. 將收集到的結果寫入 Excel 檔案
    if filtered_stocks:
        print("正在生成 Excel 報告...")
        
        # 將字典列表轉換為 pandas DataFrame
        df = pd.DataFrame(filtered_stocks)
        
        # 設定欄位順序
        columns_order = [
            '公司代碼', '收盤價', '連續MA5>MA20天數', '成交量是否放大', 
            '布林帶寬((上/下)-1)', '布林帶寬((上-下)/中)', '最新成交量', 
            '5日成交均量', '5日均線', '20日均線'
        ]
        df = df[columns_order]
        
        # 產生 Excel 檔名
        excel_filename = f'filtered_stocks_{datetime.date.today()}.xlsx'
        
        # 將 DataFrame 寫入 Excel，index=False 表示不將 DataFrame 的索引寫入檔案
        df.to_excel(excel_filename, index=False, engine='openpyxl')
        
        print(f"Excel 報告已儲存至: {excel_filename}")
    else:
        print("未篩選出符合條件的股票，不生成 Excel 檔案。")

def crawler():
    """
    爬取所有公司代碼，並使用多執行緒及 requests.Session 抓取每支股票的詳細資料。
    最終回傳一個包含所有成功抓取結果的列表。
    """
    print("正在抓取所有上市櫃公司代碼...")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=5")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2")
    
    company_codes = cr.companycode
    total_companies = len(company_codes)
    print(f"代碼抓取完成，共 {total_companies} 家公司。")
    print("開始使用多執行緒爬取個股資料 (已啟用 Session)...")
    
    local_time = int(time.mktime(time.localtime()))
    crawled_results = []
    
    # 在 ThreadPoolExecutor 外層建立一個 Session 物件
    # 這樣所有執行緒就可以共享這個 Session 及其連線池
    with requests.Session() as session:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor: # 您可以調整 workers 數量
            tasks = {}
            for code in company_codes:
                url = f"https://histock.tw/Stock/tv/udf.asmx/history?symbol={code}&resolution=D&from=1609430400&to={local_time}"
                # 在提交任務時，將 session 物件作為參數傳遞進去
                task = executor.submit(cr.getajaxdata, url, code, session)
                tasks[task] = code
                
            count = 0
            for future in as_completed(tasks):
                count += 1
                stock_result = future.result()
                if stock_result:
                    crawled_results.append(stock_result)
                
                print(f"進度: {count}/{total_companies}", end='\r')

    print("\n所有個股資料爬取完成。")
    return crawled_results

def main():
    """
    主執行函式
    """
    start_time = time.time()
    
    # 1. 執行爬蟲並獲取所有資料
    all_data = crawler()
    
    if not all_data:
        print("沒有成功抓取到任何資料，程式結束。")
        return

    print(f"成功抓取 {len(all_data)} 家公司的有效資料。")
    
    # 2. 將所有資料一次性存成 JSON 檔 (備份用)
    print("正在將所有資料儲存至 JSON 檔案中...")
    # 將字典列表轉換為 pandas DataFrame
    df = pd.DataFrame(all_data) 
    # 將 DataFrame 轉為 JSON 字串
    code_json = df.to_json(orient="records") 
    
    file_name = f'list-{datetime.date.today()}.json'
    with open(file_name, 'w', encoding='utf-8') as f:
        # 這裡直接寫入 code_json 字串，因為 cr.loadlist() 預期讀取的是一個 JSON 字串
        # 如果 cr.loadlist() 要修改成讀取標準 JSON，這裡要用 json.dump(all_data, f)
        f.write(code_json)
    print(f"資料已成功儲存至 {file_name}")

    # 3. 直接使用記憶體中的資料進行分析
    result(all_data)
    
    # 4. 新增：上傳到資料庫
    upload_to_neon(all_data)

    end_time = time.time()
    print(f"程式執行完畢，總花費 {end_time - start_time:.2f} 秒")

if __name__ == "__main__":
    main()