# [完整替換 thread.py 的內容]

import threading
import time
import crawler_ajax as cr
import concurrent.futures
from concurrent.futures import as_completed
import pandas as pd
import datetime

def result(all_stock_data):
    """
    接收包含所有股票資料的列表，進行分析並將符合條件的結果寫入 txt 檔案。
    """
    print("開始分析篩選結果...")
    # 直接遍歷傳入的資料列表
    for stock_data in all_stock_data:
        # 將單一股票的字典傳遞給 print_result 函式
        cr.print_result(stock_data)
    print(f"分析完成，結果已存入 company-{datetime.date.today()}.txt")

def crawler():
    """
    爬取所有公司代碼，並使用多執行緒抓取每支股票的詳細資料。
    最終回傳一個包含所有成功抓取結果的列表。
    """
    # 步驟 1: 抓取所有公司代碼
    print("正在抓取所有上市櫃公司代碼...")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=5")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2")
    
    company_codes = cr.companycode
    total_companies = len(company_codes)
    print(f"代碼抓取完成，共 {total_companies} 家公司。")
    print("開始使用多執行緒爬取個股資料...")
    
    # 步驟 2: 使用多執行緒爬取資料
    local_time = int(time.mktime(time.localtime()))
    crawled_results = [] # 建立一個空列表，用來收集所有成功的回傳結果
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        # 建立任務字典 {future: code} 以便追蹤
        tasks = {}
        for code in company_codes:
            url = f"https://histock.tw/Stock/tv/udf.asmx/history?symbol={code}&resolution=D&from=1609430400&to={local_time}"
            task = executor.submit(cr.getajaxdata, url, code)
            tasks[task] = code
            
        # 步驟 3: 處理完成的任務並顯示進度
        count = 0
        for future in as_completed(tasks):
            count += 1
            stock_result = future.result() # 獲取 getajaxdata 的回傳值 (一個字典或 None)
            if stock_result: # 如果回傳的不是 None，就表示成功
                crawled_results.append(stock_result)
            
            # 打印進度
            print(f"進度: {count}/{total_companies}", end='\r')

    print("\n所有個股資料爬取完成。")
    return crawled_results # 回傳收集到的結果列表

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
    
    end_time = time.time()
    print(f"程式執行完畢，總花費 {end_time - start_time:.2f} 秒")

if __name__ == "__main__":
    main()