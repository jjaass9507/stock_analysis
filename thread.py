import threading
import time
import crawler_ajax as cr
import concurrent.futures
from concurrent.futures import as_completed
import re
local_time = int(time.mktime(time.localtime()))
print(local_time)
def result():
    result = cr.loadlist()  #讀取抓下來的公司股價資料
    for i in range(len(result)):    #後續分析公司股價並存入txt
        cr.print_result(result,i)    
    end_time = time.time()
    print(end_time-start_time)
def crawler():
    global local_time
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=5")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")
    cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2")
    # print(cr.companycode)
    # companycode = cr.getdata('https://www.tej.com.tw/webtej/doc/uid.htm')   #抓取公司代碼
    with concurrent.futures.ThreadPoolExecutor() as executor: #建立多執行緒運行爬蟲
        count = 0
        counts = 1
        tasks = []
        all_task = None
        for i in cr.companycode:
            # count += 1
            # if count>100:
            #     break
            url = "https://histock.tw/Stock/tv/udf.asmx/history?symbol="+str(i)+"&resolution=D&from=1609430400&to="+str(local_time)
            try:
                task = executor.submit(cr.getajaxdata,url,i)
                # cr.getajaxdata(url,i)
                # print(i+"success")
            except Exception as exc:
                print(exc)
            tasks.append(task)              
        for task in as_completed(tasks):
            print(counts)
            counts += 1
            try:
                print(task.result)
            except Exception as exc:
                print(exc)
start_time = time.time()    #紀錄開始時間
# cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=5")
# cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")
# cr.getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2")

# result = cr.loadlist()
# print(len(result))

crawler()
print(len(cr.companycode))
print(len(cr.MA5))
for i in range(len(cr.MA5)):
    cr.savecode(cr.codes[i],cr.MA5[i],cr.MA20[i],cr.LB[i],cr.UB[i],cr.cprice[i],cr.volume[i],cr.VMA5[i])
result()
end_time = time.time()    #紀錄結束時間
print("花費"+str(end_time-start_time)+"秒")    #印出花費時間


