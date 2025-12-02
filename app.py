# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import datetime

# 設定頁面資訊
st.set_page_config(page_title="台股策略分析儀表板", layout="wide")

# 資料庫連線
# 實務上建議使用 st.secrets 來管理密碼，不要直接貼在程式碼中
DB_CONNECTION_STR = "postgresql://neondb_owner:npg_4iLDkK9UWIgr@ep-cold-king-a4w2omct-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

@st.cache_data(ttl=3600) # 快取資料 1 小時，避免頻繁查詢資料庫
def load_data(date_input):
    engine = create_engine(DB_CONNECTION_STR)
    query = f"""
    SELECT * FROM stock_daily_analysis 
    WHERE record_date = '{date_input}'
    ORDER BY code ASC
    """
    try:
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"讀取資料庫失敗: {e}")
        return pd.DataFrame()

# --- 網站介面 ---
st.title("📈 台股策略選股分析")

# 1. 側邊欄：篩選條件
st.sidebar.header("篩選條件")
select_date = st.sidebar.date_input("選擇日期", datetime.date.today())

# 讀取資料
df = load_data(select_date)

if df.empty:
    st.warning(f"找不到 {select_date} 的資料。請確認爬蟲是否已執行並上傳。")
else:
    st.success(f"已載入 {len(df)} 筆資料")

    # 2. 策略篩選
    st.subheader("🎯 策略篩選器")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        min_trend = st.number_input("MA5 > MA20 最少天數", min_value=0, value=2)
    with col2:
        max_bbw = st.number_input("布林帶寬最大值 (壓縮中)", value=0.15)
    with col3:
        only_vol_break = st.checkbox("只顯示成交量放大", value=True)

    # 套用篩選
    filtered_df = df[
        (df['trend_days'] >= min_trend) & 
        (df['bbw_ratio'] < max_bbw)
    ]
    
    if only_vol_break:
        filtered_df = filtered_df[filtered_df['volume_break'] == True]

    # 3. 顯示結果
    st.write(f"共有 **{len(filtered_df)}** 檔股票符合條件：")
    
    # 格式化顯示
    st.dataframe(
        filtered_df[['code', 'close_price', 'trend_days', 'bbw_ratio', 'volume', 'volume_break']],
        use_container_width=True,
        column_config={
            "code": "代碼",
            "close_price": "收盤價",
            "trend_days": "多頭天數",
            "bbw_ratio": "帶寬比",
            "volume": "成交量",
            "volume_break": "爆量"
        }
    )

    # 4. 簡單圖表分析
    if not filtered_df.empty:
        st.subheader("📊 符合策略個股 - 帶寬 vs 趨勢天數")
        st.scatter_chart(
            filtered_df,
            x='trend_days',
            y='bbw_ratio',
            color='code',
            size='volume'
        )