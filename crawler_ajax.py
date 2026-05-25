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


def getdata(url, market):
    """
    抓取上市/上櫃/興櫃公司代碼。
    回傳 (code, market) 元組的排序列表。
    """
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

    return [(code, market) for code in sorted(codes)]


# ---------------------------------------------------------------------------
# FinMind API 逐支股票查詢（免費帳號可用；批量下載需付費方案）
# ---------------------------------------------------------------------------

def _probe_latest_trading_date(token, session):
    """
    以 2330 單一股票探測 FinMind 實際最新交易日。
    系統時鐘可能與市場日期不符（例如設為未來），
    此函式從當前系統年份往前逐年嘗試，找到有資料的最新日期。
    """
    sys_year = datetime.date.today().year
    last_error = "（未嘗試任何年份）"
    for start_year in range(sys_year, sys_year - 5, -1):
        try:
            resp = session.get(
                "https://api.finmindtrade.com/api/v4/data",
                params={
                    "dataset": "TaiwanStockPrice",
                    "data_id": "2330",
                    "start_date": f"{start_year}-01-01",
                    "token": token
                },
                timeout=30
            )
            if resp.status_code == 200:
                rows = resp.json().get("data", [])
                if rows:
                    return datetime.date.fromisoformat(max(r["date"] for r in rows))
                last_error = f"{start_year}: HTTP 200 但 data 為空"
            else:
                last_error = f"{start_year}: HTTP {resp.status_code} — {resp.text[:300]}"
        except Exception as e:
            last_error = f"{start_year}: {e}"
    raise Exception(f"無法從 FinMind 取得交易日期。最後錯誤：{last_error}")


def get_stock_list_finmind(token, session):
    """
    從 FinMind TaiwanStockInfo 取得所有台股代碼（4 位純數字）。
    失敗時回傳空清單，由 crawler 決定是否 fallback。
    """
    try:
        resp = session.get(
            "https://api.finmindtrade.com/api/v4/data",
            params={"dataset": "TaiwanStockInfo", "token": token},
            timeout=30
        )
        if resp.status_code != 200:
            return []
        rows = resp.json().get("data", [])
        codes = sorted({
            r["stock_id"] for r in rows
            if len(r.get("stock_id", "")) == 4 and r["stock_id"].isdigit()
        })
        return codes
    except Exception:
        return []


def fetch_stock_finmind(stock_id, token, session, start_date):
    """
    從 FinMind 逐支抓取單一股票歷史資料並計算技術指標。
    失敗或資料不足時回傳 None。
    """
    try:
        time.sleep(0.25)   # 避免觸發 FinMind 速率限制
        resp = session.get(
            "https://api.finmindtrade.com/api/v4/data",
            params={
                "dataset": "TaiwanStockPrice",
                "data_id": stock_id,
                "start_date": start_date.isoformat(),
                "token": token
            },
            timeout=30
        )
        if resp.status_code != 200:
            return None
        rows = resp.json().get("data", [])
        return process_finmind_stock(stock_id, rows) if rows else None
    except Exception:
        return None


def process_finmind_stock(stock_id, rows):
    """
    處理 FinMind 單一股票的資料列表，計算布林帶技術指標。
    資料不足 20 個交易日時回傳 None。
    """
    closes, vols = [], []
    for row in rows:
        try:
            c = float(row["close"])
            v = int(float(row["Trading_Volume"])) // 1000  # 股 → 張
            if c > 0:
                closes.append(c)
                vols.append(v)
        except (ValueError, KeyError, TypeError):
            continue

    if len(closes) < 20:
        return None

    ub_list   = B_Band_UB(closes)
    lb_list   = B_Band_LB(closes)
    ma20_list = ma20(closes)
    c_last5   = closes[-5:]

    pb_list = []
    for close, upper, lower in zip(c_last5, ub_list, lb_list):
        band = upper - lower
        pb_list.append(round((close - lower) / band, 4) if band > 0 else 0.5)

    bbw_curr = (ub_list[-1] - lb_list[-1]) / ma20_list[-1] if ma20_list[-1] != 0 else 0
    bbw_prev = (ub_list[-2] - lb_list[-2]) / ma20_list[-2] if ma20_list[-2] != 0 else 0

    return {
        'code':          stock_id,
        'MA5':           ma5(closes),
        'MA20':          ma20_list,
        'UB':            ub_list,
        'LB':            lb_list,
        'cprice':        c_last5,
        'volume':        vols[-5:],
        'VMA5':          vma5(vols),
        'percent_b':     pb_list,
        'bbw_expanding': bbw_curr > bbw_prev
    }


def _parse_rows(data_rows, close_col=6, vol_col=1):
    """
    解析 TWSE / TPEX 的每日交易 rows，回傳 (收盤價列表, 成交量列表)。
    成交量單位換算：股 → 張 (÷1000)。
    """
    closes, vols = [], []
    for row in data_rows:
        try:
            close_str = row[close_col].replace(',', '').strip()
            vol_str   = row[vol_col].replace(',', '').strip()
            # 停牌或無成交日以 '--' 表示，跳過
            if not close_str or '--' in close_str or close_str == '0':
                continue
            closes.append(float(close_str))
            vols.append(int(vol_str) // 1000)   # 股 → 張
        except (ValueError, IndexError, AttributeError):
            continue
    return closes, vols


def _fetch_twse_month(code, year, month, session):
    """
    向 TWSE 官方 API 抓取指定月份的日交易資料。
    endpoint: /exchangeReport/STOCK_DAY
    """
    url = (
        f"https://www.twse.com.tw/exchangeReport/STOCK_DAY"
        f"?response=json&date={year}{month:02d}01&stockNo={code}"
    )
    try:
        time.sleep(0.2)     # 避免過快觸發 TWSE 速率限制
        resp = session.get(url, headers={"User-agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get('stat') != 'OK' or not data.get('data'):
            return [], []
        return _parse_rows(data['data'])
    except Exception:
        return [], []


def _fetch_tpex_month(code, year, month, session):
    """
    向 TPEX 官方 API 抓取指定月份的日交易資料。
    endpoint: /web/stock/aftertrading/daily_trading_info/st43_result.php
    """
    url = (
        f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/"
        f"st43_result.php?l=zh-tw&d={year}/{month:02d}/01&stkno={code}"
    )
    try:
        time.sleep(0.2)
        resp = session.get(url, headers={"User-agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get('aaData', [])
        if not rows:
            return [], []
        return _parse_rows(rows)
    except Exception:
        return [], []


def fetch_stock_history(code, market, session):
    """
    從 TWSE 或 TPEX 官方 API 抓取個股歷史資料，
    確保取得至少 20 個交易日的資料後計算技術指標，
    回傳與舊版 getajaxdata() 相容的字典格式。
    資料不足或發生錯誤時回傳 None。
    """
    today = datetime.date.today()
    year, month = today.year, today.month
    fetch_fn = _fetch_twse_month if market == 'TWSE' else _fetch_tpex_month

    c, v = fetch_fn(code, year, month, session)

    # 月初交易日不足 20 天時，補抓上個月資料
    if len(c) < 20:
        prev_year  = year if month > 1 else year - 1
        prev_month = month - 1 if month > 1 else 12
        c_prev, v_prev = fetch_fn(code, prev_year, prev_month, session)
        c = c_prev + c
        v = v_prev + v

    if len(c) < 20:
        return None

    ub_list  = B_Band_UB(c)
    lb_list  = B_Band_LB(c)
    ma20_list = ma20(c)
    c_last5  = c[-5:]

    # %B = (Close - LB) / (UB - LB)，反映收盤價在布林帶中的相對位置
    pb_list = []
    for close, upper, lower in zip(c_last5, ub_list, lb_list):
        band = upper - lower
        pb_list.append(round((close - lower) / band, 4) if band > 0 else 0.5)

    # 帶寬擴張確認：最新一天的帶寬比前一天大，表示壓縮結束、開始擴張
    bbw_curr = (ub_list[-1] - lb_list[-1]) / ma20_list[-1] if ma20_list[-1] != 0 else 0
    bbw_prev = (ub_list[-2] - lb_list[-2]) / ma20_list[-2] if ma20_list[-2] != 0 else 0
    is_expanding = bbw_curr > bbw_prev

    return {
        'code':         code,
        'MA5':          ma5(c),
        'MA20':         ma20_list,
        'UB':           ub_list,
        'LB':           lb_list,
        'cprice':       c_last5,
        'volume':       v[-5:],
        'VMA5':         vma5(v),
        'percent_b':    pb_list,
        'bbw_expanding': is_expanding
    }


# ---------------------------------------------------------------------------
# 策略分析
# ---------------------------------------------------------------------------

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

        percent_b_val  = stock_data.get('percent_b', [0.5] * 5)[last_index]
        bbw_expanding  = stock_data.get('bbw_expanding', False)

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
                '20日均線': stock_data['MA20'][last_index],
                '%B': round(percent_b_val, 4),
                '帶寬擴張': '是' if bbw_expanding else '否'
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
            f.write(f"最近五日交易量(張): {stock_data['volume']}\n")
            f.write(f"最近五日交易量均線: {stock_data['VMA5']}\n")
            f.write(f"MA5: {stock_data['MA5']}\n")
            f.write(f"MA20: {stock_data['MA20']}\n")
            f.write(f"UB: {stock_data['UB']}\n")
            f.write(f"LB: {stock_data['LB']}\n")
            f.write("=====================================\n")


# ---------------------------------------------------------------------------
# 技術指標計算
# ---------------------------------------------------------------------------

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
