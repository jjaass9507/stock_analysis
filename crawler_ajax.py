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
def print_result(collect,i):    #將資料輸出為txt
    # print("公司代碼:"+str(collect[i]["code"]))
    # print("MA5:"+str(collect[i]["MA5"]))
    # print("MA20:"+str(collect[i]["MA20"]))
    day = 0
    for j in reversed(range(5)):      #
            if collect[i]["MA5"][j]>collect[i]["MA20"][j]:
                day += 1
                continue
            else:
                break 
    BBW1 = round((collect[i]["UB"][len(collect[i]["UB"])-1]-collect[i]["LB"][len(collect[i]["LB"])-1])/collect[i]["MA20"][len(collect[i]["MA20"])-1],2)
    BBW2 = round((collect[i]["UB"][len(collect[i]["UB"])-1]/collect[i]["LB"][len(collect[i]["LB"])-1])-1,2)
    if day>=2 and BBW2<0.1 and collect[i]["volume"][len(collect[i]["volume"])-1]>collect[i]["VMA5"][len(collect[i]["VMA5"])-1]:   #抓出符合選項的股票
        f = open('company-'+str(datetime.date.today())+'.txt','a',encoding='utf8')
        f.write("公司代碼:"+str(collect[i]["code"])+"\n")
        f.write("今日收盤價"+str(collect[i]["cprice"][len(collect[i]["cprice"])-1])+"\n")
        f.write("當前帶寬(上軌-下軌)/2:"+str(BBW1)+"\n")
        f.write("當前帶寬(上軌/下軌)-1:"+str(BBW2)+"\n")
        f.write("連續"+str(day)+"天五日線高於中線"+"\n")
        f.write("日期:"+str(dateList)+"\n")
        f.write("交易量"+str(collect[i]["volume"])+"\n")
        f.write("交易量五日均線"+str(collect[i]["VMA5"])+"\n")
        f.write("MA5:"+str(collect[i]["MA5"])+"\n")
        f.write("MA20:"+str(collect[i]["MA20"])+"\n")
        f.write("UB:"+str(collect[i]["UB"])+"\n")
        f.write("LB:"+str(collect[i]["LB"])+"\n")
        f.write("=====================================\n")
        # print("公司代碼:"+str(collect[i]["code"]))
        # print("連續"+str(day)+"天五日線高於中線")
        # print("MA5:"+str(collect[i]["MA5"]))
        # print("MA20:"+str(collect[i]["MA20"]))
def getajaxdata(url,code):   #ajax模式
    global MA5,MA20,UB,LB,codes,cprice,volume
    #url = "https://www.ptt.cc/bbs/Gossiping/index.html"
    #建立Request物件，附加 Request Headers 的資訊
    while True:
        try:
            request = req.Request(url,headers={     #取得某些header取得讀取權限
                "referer":"https://histock.tw/stock/tv/tvchart.aspx?no=2330",   
                "cookie":"ASP.NET_SessionId=jtcjw5s2sev13qed0vw5o0tg; _ga=GA1.2.2114789011.1629736882; _gcl_au=1.1.140816943.1629736882; __gads=ID=99eff656639bfa08-227edbfb17cb0077:T=1629736889:RT=1629736889:S=ALNI_MYNcPmDzFVTtl1vR7NyZrrDqqaR7A; _fbp=fb.1.1629736883018.779705980; _gid=GA1.2.902996350.1629961090; _gat=1",
                "User-agent":"Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Mobile Safari/537.36"
            })
            with req.urlopen(request) as response:
                data = response.read().decode("utf-8")  #根據觀察 此處資料為 JSON 格式

            #解析 JSON 格式資料,取得每則標題
            data = json.loads(data) #把原始 JSON 資料解析成字典/列表的表示形式
            #print(data)
            day = 0
            #取得 JSON 資料中的股價
            if len(data) <= 5:
                print(code)
            if len(data) > 5:   #判斷裡面有沒有資料
                h = data['h']   #股價每日高點
                c = data['c']   #股價每日收盤價
                l = data['l']   #股價每日低點
                o = data['o']   #股價每日開盤
                v = data['v']   #股市每日交易量
                c1 = c[len(c)-5:len(c)]
                v1 = v[len(v)-5:len(v)]
                lock.acquire()
                codes.append(code)
                VMA5.append(vma5(v))
                MA5.append(ma5(c))    #將五日均線回傳存入
                MA20.append(ma20(c))  #將二十日均線回傳存入
                UB.append(B_Band_UB(c))   #將布林軌道上軌回傳存入
                LB.append(B_Band_LB(c))   #將布林軌道下軌回傳存入
                cprice.append(c1)   #將收盤價回傳存入
                volume.append(v1)   #將交易量回傳存入
                lock.release()
                # print(LB)
                # for i in range(5):  #判斷當前五日均線是否高於二十日均線
                #     if MA5[i]>MA20[i]:
                #         day += 1
                #         continue    #當前日期符合繼續迴圈
                #     else:
                #         break       #不符合跳出迴圈
                # savecode(code,MA5,MA20,LB,UB) #把抓取的股價資料存入
                time.sleep(1)   #待機
                # return MA5[0]
        except Exception as e:
            print("錯誤原因:",e)
        else:
            break
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

    


