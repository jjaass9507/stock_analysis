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

ssl._create_default_https_context = ssl._create_unverified_context


def getdate():
    tonow = datetime.date.today()
    return [str(tonow - datetime.timedelta(days=i)) for i in reversed(range(5))]


def getdata(url):
    """抓取上市/上櫃/興櫃公司代碼，回傳排序後的代碼列表。"""
    request = req.Request(url, headers={
        "cookie": "",
        "User-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Mobile Safari/537.36"
    })
    with req.urlopen(request) as response:
        data = response.read().decode("Big5", "ignore")

    root = bs4.BeautifulSoup(data, "lxml")
    titles = root.find_all("tr")

    codes = set()
    for i in titles:
        if i.td:
            c = i.td.text.split()
            if len(c) > 1 and len(c[0]) == 4:
                codes.add(c[0])

    return sorted(list(codes))


def analyze_stock_strategy(stock_data):
    """
    分析單一股票是否符合策略。
    符合條件回傳指標字典，否則回傳 None。
    """
    try:
        day = 0
        for j in reversed(range(5)):
            if stock_data["MA5"][j] > stock_data["MA20"][j]:
                day += 1
            else:
                break

        last_index = -1
        BBW1 = round((stock_data["UB"][last_index] - stock_data["LB"][last_index]) / stock_data["MA20"][last_index], 2)
        BBW2 = round((stock_data["UB"][last_index] / stock_data["LB"][last_index]) - 1, 2)
        volume_break = stock_data["volume"][last_index] > stock_data["VMA5"][last_index]

        if day >= 2 and BBW2 < 0.1 and volume_break:
            return {
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

    except (IndexError, ZeroDivisionError):
        return None

    return None


def print_result(stock_data):
    """將符合策略的股票資料寫入 txt 檔。"""
    day = 0
    for j in reversed(range(5)):
        if stock_data["MA5"][j] > stock_data["MA20"][j]:
            day += 1
        else:
            break

    last_index = -1
    BBW1 = round((stock_data["UB"][last_index] - stock_data["LB"][last_index]) / stock_data["MA20"][last_index], 2)
    BBW2 = round((stock_data["UB"][last_index] / stock_data["LB"][last_index]) - 1, 2)
    volume_break = stock_data["volume"][last_index] > stock_data["VMA5"][last_index]

    if day >= 2 and BBW2 < 0.1 and volume_break:
        date_list = getdate()
        with open(f'company-{datetime.date.today()}.txt', 'a', encoding='utf8') as f:
            f.write(f"公司代碼: {stock_data['code']}\n")
            f.write(f"今日收盤價: {stock_data['cprice'][last_index]}\n")
            f.write(f"當前帶寬(上軌-下軌)/中線: {BBW1}\n")
            f.write(f"當前帶寬(上軌/下軌)-1: {BBW2}\n")
            f.write(f"連續 {day} 天五日線高於中線\n")
            f.write(f"最近五日日期: {date_list}\n")
            f.write(f"最近五日交易量: {stock_data['volume']}\n")
            f.write(f"最近五日交易量均線: {stock_data['VMA5']}\n")
            f.write(f"MA5: {stock_data['MA5']}\n")
            f.write(f"MA20: {stock_data['MA20']}\n")
            f.write(f"UB: {stock_data['UB']}\n")
            f.write(f"LB: {stock_data['LB']}\n")
            f.write("=====================================\n")


def getajaxdata(url, code, session):
    """
    使用傳入的 requests.Session 抓取單一股票歷史資料，
    計算技術指標並回傳字典。失敗時回傳 None。
    """
    headers = {
        "referer": "https://histock.tw/stock/tv/tvchart.aspx?no=2330",
        "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
    }

    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if 'c' not in data or len(data['c']) < 20:
            return None

        c = data['c']
        v = data['v']

        return {
            'code':   code,
            'MA5':    ma5(c),
            'MA20':   ma20(c),
            'UB':     B_Band_UB(c),
            'LB':     B_Band_LB(c),
            'cprice': c[len(c)-5:len(c)],
            'volume': v[len(v)-5:len(v)],
            'VMA5':   vma5(v)
        }

    except requests.exceptions.RequestException:
        return None
    except Exception:
        return None


def vma5(v):
    result = []
    maxday = len(v)
    for i in range(5):
        result.append(round(sum(v[maxday-5:maxday]) / 5, 2))
        maxday -= 1
    result.reverse()
    return result


def ma5(c):
    result = []
    maxday = len(c)
    for i in range(5):
        result.append(round(sum(c[maxday-5:maxday]) / 5, 2))
        maxday -= 1
    result.reverse()
    return result


def ma20(c):
    result = []
    maxday = len(c)
    for i in range(5):
        result.append(round(sum(c[maxday-20:maxday]) / 20, 2))
        maxday -= 1
    result.reverse()
    return result


def B_Band_LB(c):
    result = []
    maxday = len(c)
    for i in range(5):
        slice_c = c[maxday-20:maxday]
        mean_val = sum(slice_c) / 20
        stdev = (sum((x - mean_val)**2 for x in slice_c) / 20) ** 0.5
        result.append(round(mean_val - stdev * 2, 2))
        maxday -= 1
    result.reverse()
    return result


def B_Band_UB(c):
    result = []
    maxday = len(c)
    for i in range(5):
        slice_c = c[maxday-20:maxday]
        mean_val = sum(slice_c) / 20
        stdev = (sum((x - mean_val)**2 for x in slice_c) / 20) ** 0.5
        result.append(round(mean_val + stdev * 2, 2))
        maxday -= 1
    result.reverse()
    return result
