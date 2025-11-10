#抓取 kkday的網頁原始碼(HTML)
import urllib.request as req
import bs4
import json
import pandas as pd
import time
import ssl
import datetime
import concurrent.futures
import openpyxl
import threading
from openpyxl import Workbook
from concurrent.futures import as_completed
import requests

lock = threading.RLock()
ssl._create_default_https_context = ssl._create_unverified_context
companylist = []    #建立空列表 方便跨程式存取
VMA5 = []
MA5 = []
MA20 = []
companycode = []            
LB = []
UB = []
codes = [] 
cprice = []
volume = [] 
dateList= []


code_list = pd.DataFrame({  #建立DataFrame 個別以公司代碼、5日均線、20日均線、上軌、下軌儲存、收盤價、交易量
    "code":[],  #公司代碼  
    "MA5":[],   #5日均線
    "MA20":[],  #20日均線
    "UB":[],    #上軌
    "LB":[],    #下軌
    "cprice":[], #收盤
    "volume":[],  #交易量
    "VMA5":[]
})
def getdate():  #徒法煉鋼 還能再改
    tonow = datetime.date.today() #抓取今天時間
    for i in reversed(range(5)):
        dateList.append(str(tonow - datetime.timedelta(days=i)))
    for i in range(5):
        dateList[i].lstrip('2021-') 
def getdata(url):   #傳統模式(抓取上市上櫃公司代碼)
    #url = "https://www.tej.com.tw/webtej/doc/uid.htm"
    #建立Request物件，附加 Request Headers 的資訊
    global companylist,companycode     #從副程式外存取變數列表
    request = req.Request(url,headers={     #模擬使用者開啟網頁時的header
        "cookie":"",
        "User-agent":"Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Mobile Safari/537.36"
    })
    with req.urlopen(request) as response:
        data = response.read().decode("Big5","ignore")  #以big5解碼 並忽略其餘編碼
    #解析原始碼，取得每篇的標題
    root = bs4.BeautifulSoup(data,"lxml")    #讓beautifulsoup 協助我們以lxml解析 HTML 格式文件
    titles = root.find_all("tr")    #抓出所有 的 tr 標籤
    for i in titles:        
        c = i.td.text   #存取td標籤內的文字
        # print(i.td.text)
        c=c.split()
        if len(c)>1:
            companylist = companylist+[c]   #將文字存入列表內
    for i in companylist:
        if len(i[0])==4:                    #篩選出公司代碼來存入
            companycode = companycode + [i[0]]
    companycode = pd.unique(companycode).tolist()   #刪除列表內重複的欄位資料
    companycode.sort()  #列表按照大小排列
    # print(companycode)
    #     c=i.text.replace("\xa0","") #把空格取代為空
    #     c=c.replace("\r","")        #把\r取代為空
    #     c=c.replace("\n","")        #把\n取代為空
    #     c=c.split()                 #將剩餘資料切開
    #     if c != "" or c != None :       #如果資料為空或沒資料則不存入
    #         companylist = companylist+[c]
    # for i in companylist:
    #     if len(i) > 1:              #如果列表大於2表示為公司資料
    #         companycode = companycode+[i[0]]
    # print(companycode)
    #return companycode  #回傳代碼列表
        # if i.text.isdigit():
        #     print(i.text) 
    # for title in titles("span"):
    #     title.extract()
        # if title.span != None: #如果標題包含 a 標籤(沒有被刪除)
        #     title.decompose()
        #     print(title)
    # return root.find("a",string="‹ 上頁")["href"]
    #print(titles)

def loadlist(): #讀取公司股價資料列表
    global code_list    #從外部抓取建立的DataFrame
    with open('list-'+str(datetime.date.today())+'.json','r') as clist:    #打開資料夾內的list.json檔，r為讀取
        code_list = json.load(clist)        #將json檔放入變數
        code_list = json.loads(code_list)   #解析json格式
    return code_list    #回傳DataFrame
def savecode(code,MA5,MA20,LB,UB,cprice,volume,VMA5):    #儲存公司股價資料放入json檔
    global code_list
    code_list = code_list.append({
        'code' : code,
        'MA5' : MA5,
        'MA20' : MA20,
        'UB' : UB,
        'LB' : LB,
        'cprice' : cprice,
        "volume" : volume,
        "VMA5":VMA5
    }, ignore_index=True)
    code_json = code_list.to_json(orient="records") #將DataFrame轉換為json
    # print(code_list)
    # print(code_json)
    # output = json.loads(code_json)
    # print(output[0]['code'])
    # print(output[1])
    with open('list-'+str(datetime.date.today())+'.json','w') as load: #把資料寫入json檔
        json.dump(code_json,load)

def analyze_stock_strategy(stock_data):
    """
    專門用來分析單一股票是否符合策略的函式。
    如果符合，回傳一個包含關鍵指標的字典。
    如果不符合，回傳 None。
    """
    try:
        # 1. 判斷趨勢: 連續幾天 MA5 > MA20
        day = 0
        for j in reversed(range(5)):
            if stock_data["MA5"][j] > stock_data["MA20"][j]:
                day += 1
            else:
                break

        # 2. 計算布林帶寬指標
        last_index = -1 # 使用 -1 更 pythonic，代表最後一個元素
        BBW1 = round((stock_data["UB"][last_index] - stock_data["LB"][last_index]) / stock_data["MA20"][last_index], 2)
        BBW2 = round((stock_data["UB"][last_index] / stock_data["LB"][last_index]) - 1, 2)
        
        # 3. 判斷成交量是否放大
        volume_break = stock_data["volume"][last_index] > stock_data["VMA5"][last_index]

        # 4. 策略條件判斷
        if day >= 2 and BBW2 < 0.1 and volume_break:
            # 整理成一個扁平化的字典，方便寫入 Excel
            result = {
                '公司代碼': stock_data['code'],
                '收盤價': stock_data['cprice'][last_index],
                '連續MA5>MA20天數': day,
                '成交量是否放大': '是' if volume_break else '否',
                '布林帶寬((上-下)/中)': BBW1,
                '布林帶寬((上/下)-1)': BBW2,
                '最新成交量': stock_data['volume'][last_index],
                '5日成交均量': stock_data['VMA5'][last_index],
                '5日均線': stock_data['MA5'][last_index],
                '20日均線': stock_data['MA20'][last_index]
            }
            return result
            
    except (IndexError, ZeroDivisionError):
        # 如果計算過程中發生錯誤 (例如除以零)，則視為不符合
        return None
        
    return None # 預設回傳 None
def print_result(stock_data):    # 將資料輸出為txt (已重構)
    """
    接收單一股票的資料字典，判斷是否符合策略，
    若符合則將結果寫入文字檔。
    """
    # 函式現在接收一個字典 (stock_data)，而不是列表和索引
    day = 0
    # 判斷趨勢: 連續幾天 MA5 > MA20
    for j in reversed(range(5)):
        if stock_data["MA5"][j] > stock_data["MA20"][j]:
            day += 1
        else:
            break

    # 計算布林帶寬指標
    last_index = len(stock_data["UB"]) - 1
    BBW1 = round((stock_data["UB"][last_index] - stock_data["LB"][last_index]) / stock_data["MA20"][last_index], 2)
    BBW2 = round((stock_data["UB"][last_index] / stock_data["LB"][last_index]) - 1, 2)
    
    # 判斷成交量是否放大
    volume_break = stock_data["volume"][last_index] > stock_data["VMA5"][last_index]

    # 策略條件判斷
    if day >= 2 and BBW2 < 0.1 and volume_break:
        # 使用 'a' 模式 (append) 來追加內容到檔案中
        with open(f'company-{datetime.date.today()}.txt', 'a', encoding='utf8') as f:
            f.write(f"公司代碼: {stock_data['code']}\n")
            f.write(f"今日收盤價: {stock_data['cprice'][last_index]}\n")
            f.write(f"當前帶寬(上軌-下軌)/中線: {BBW1}\n")
            f.write(f"當前帶寬(上軌/下軌)-1: {BBW2}\n")
            f.write(f"連續 {day} 天五日線高於中線\n")
            f.write(f"最近五日日期: {dateList}\n") # dateList 仍是全域變數
            f.write(f"最近五日交易量: {stock_data['volume']}\n")
            f.write(f"最近五日交易量均線: {stock_data['VMA5']}\n")
            f.write(f"MA5: {stock_data['MA5']}\n")
            f.write(f"MA20: {stock_data['MA20']}\n")
            f.write(f"UB: {stock_data['UB']}\n")
            f.write(f"LB: {stock_data['LB']}\n")
            f.write("=====================================\n")

    # 呼叫新的分析函式
    analysis_result = analyze_stock_strategy(stock_data)
    
    # 如果分析結果不是 None，代表符合條件
    if analysis_result:
        with open(f'company-{datetime.date.today()}.txt', 'a', encoding='utf8') as f:
            f.write(f"公司代碼: {analysis_result['公司代碼']}\n")
            f.write(f"今日收盤價: {analysis_result['收盤價']}\n")
            f.write(f"當前帶寬(上軌-下軌)/中線: {analysis_result['布林帶寬((上-下)/中)']}\n")
            f.write(f"當前帶寬(上軌/下軌)-1: {analysis_result['布林帶寬((上/下)-1)']}\n")
            f.write(f"連續 {analysis_result['連續MA5>MA20天數']} 天五日線高於中線\n")
            # 原始資料的寫入可以視需求保留或移除
            f.write(f"MA5: {stock_data['MA5']}\n")
            f.write(f"MA20: {stock_data['MA20']}\n")
            f.write("=====================================\n")
            
def getajaxdata(url, code, session):   # ajax模式 (已重構 for requests.Session)
    """
    使用傳入的 requests.Session 物件抓取單一股票的歷史資料，
    計算技術指標，並回傳一個包含所有結果的字典。
    如果失敗則回傳 None。
    """
    headers = {
        "referer":"https://histock.tw/stock/tv/tvchart.aspx?no=2330",   
        "User-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
    }
    
    try:
        # 使用傳入的 session 物件發送 GET 請求，並設定 10 秒超時
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status() # 如果請求失敗 (狀態碼非 2xx)，會拋出異常
        
        # 直接使用 .json() 方法將回應解析為 Python 字典，更簡潔
        data = response.json()

        # 檢查資料是否足夠
        if 'c' not in data or len(data['c']) < 20:
            return None

        # 取得 JSON 資料中的股價與成交量
        c = data['c']
        v = data['v']

        # 將所有計算結果打包成一個字典
        result_dict = {
            'code'   : code,
            'MA5'    : ma5(c),
            'MA20'   : ma20(c),
            'UB'     : B_Band_UB(c),
            'LB'     : B_Band_LB(c),
            'cprice' : c[len(c)-5:len(c)],
            'volume' : v[len(v)-5:len(v)],
            'VMA5'   : vma5(v)
        }
        
        return result_dict

    except requests.exceptions.RequestException as e:
        # 專門捕捉 requests 相關的錯誤 (如網路、超時)
        # print(f"處理代碼 {code} 時發生網路錯誤: {e}")
        return None
    except Exception as e:
        # 捕捉其他可能的錯誤 (如 JSON 解析失敗)
        # print(f"處理代碼 {code} 時發生未知錯誤: {e}")
        return None

def vma5(v):
    VMA5 = []
    maxday = len(v)
    for i in range(5):     
        MA = round(pd.Series(v[maxday-5:maxday]).sum()/5,2)
        VMA5 = VMA5 + [MA]
        maxday -= 1
    VMA5.reverse()
    return VMA5
def ma5(c):     #取得五日均線
    MA5 = []
    maxday = len(c)
    for i in range(5):     
        MA = round(pd.Series(c[maxday-5:maxday]).sum()/5,2)
        MA5 = MA5 + [MA]
        maxday -= 1
    MA5.reverse()
    return MA5
def ma20(c):    #取得20日均線
    MA20 = []
    maxday = len(c)
    for i in range(5):     
        MA = round(pd.Series(c[maxday-20:maxday]).sum()/20,2)
        MA20 = MA20 + [MA]
        maxday -= 1
    MA20.reverse()
    return MA20
def B_Band_LB(c):   #計算布林軌道上軌
    LB = []
    maxday = len(c)
    for i in range(5):     
        MA = round(pd.Series(c[maxday-20:maxday]).sum()/20-pd.Series(c[maxday-20:maxday]).std(ddof= 0)*2,2)
        LB = LB + [MA]
        maxday -= 1
    LB.reverse()
    return LB
def B_Band_UB(c):   #計算布林軌道下軌
    UB = []
    maxday = len(c)
    for i in range(5):     
        MA = round(pd.Series(c[maxday-20:maxday]).sum()/20+pd.Series(c[maxday-20:maxday]).std(ddof= 0)*2,2)
        UB = UB + [MA]
        maxday -= 1
    UB.reverse()    
    return UB
getdate()
# getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=5")
# getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")
# getdata("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2")
# # companycode.sort()
# print(len(companycode))
# print(companycode)

    


