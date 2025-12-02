import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import datetime
import os
import thread as crawler_thread  # 匯入您的爬蟲模組

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="台股策略分析儀表板",
    page_icon="📈",
    layout="wide"
)

# --- 2. 資料庫連線設定 ---
# 優先嘗試從 Streamlit secrets 讀取，其次是環境變數，最後是預設值
# 在 Streamlit Cloud 上，請在 Secrets 區域設定 NEON_DB_URL
DB_CONNECTION_STR = os.environ.get(
    "NEON_DB_URL", 
    "postgresql://neondb_owner:npg_4iLDkK9UWIgr@ep-cold-king-a4w2omct-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

# --- 3. 載入資料函式 (含快取) ---
@st.cache_data(ttl=300) # 設定 5 分鐘快取，避免頻繁查詢 DB
def load_data(date_input):
    """
    從 Neon 資料庫讀取指定日期的分析資料
    """
    try:
        engine = create_engine(DB_CONNECTION_STR)
        query = f"""
        SELECT * FROM stock_daily_analysis 
        WHERE record_date = '{date_input}'
        ORDER BY code ASC
        """
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        # 若資料表尚未建立或連線失敗，回傳空 DataFrame 並顯示錯誤
        st.error(f"無法讀取資料庫: {e}")
        return pd.DataFrame()

# --- 4. 側邊欄：控制與篩選 ---
st.sidebar.title("🛠️ 控制台")

st.sidebar.subheader("1. 資料更新")
# 按鈕：觸發爬蟲
if st.sidebar.button("🚀 執行爬蟲更新今日資料"):
    with st.spinner('正在執行爬蟲並上傳資料庫，請稍候... (約需 1-3 分鐘)'):
        try:
            # 呼叫 thread.py 的接口
            result_message = crawler_thread.run_crawler_pipeline()
            
            if "成功" in result_message:
                st.success(result_message)
                st.cache_data.clear() # 清除快取以顯示最新資料
            else:
                st.warning(result_message)
        except Exception as e:
            st.error(f"執行失敗: {e}")

st.sidebar.markdown("---")
st.sidebar.subheader("2. 日期選擇")
# 預設顯示今天，若無資料使用者可往前選
select_date = st.sidebar.date_input("選擇查看日期", datetime.date.today())

# --- 5. 主頁面內容 ---
st.title("📈 台股策略選股分析")
st.markdown(f"目前檢視日期：**{select_date}**")

# 載入資料
df = load_data(select_date)

if df.empty:
    st.info(f"📅 {select_date} 尚無資料。請點擊側邊欄的「執行爬蟲」按鈕，或選擇其他日期。")
else:
    # --- 策略篩選區塊 ---
    with st.expander("🔍 策略篩選條件 (點擊展開/收合)", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            min_trend = st.number_input("MA5 > MA20 最少天數", min_value=0, value=2, step=1)
        with col2:
            max_bbw = st.number_input("布林帶寬最大值 ((上-下)/中)", value=0.15, step=0.01)
        with col3:
            only_vol_break = st.checkbox("只顯示成交量放大 (大於5日均量)", value=True)

    # 進行篩選
    # 1. 趨勢天數
    filtered_df = df[df['trend_days'] >= min_trend]
    # 2. 布林帶寬 (根據您的邏輯，這裡是 (UB-LB)/MA20)
    filtered_df = filtered_df[filtered_df['bbw_ratio'] <= max_bbw]
    # 3. 成交量
    if only_vol_break:
        # 資料庫存的是 boolean
        filtered_df = filtered_df[filtered_df['volume_break'] == True]

    # --- 顯示結果統計 ---
    st.markdown("### 📊 篩選結果")
    st.write(f"在 {len(df)} 檔股票中，共有 **{len(filtered_df)}** 檔符合上述條件。")

    if not filtered_df.empty:
        # --- 圖表分析 (散佈圖) ---
        # X軸: 趨勢天數, Y軸: 帶寬, 泡泡大小: 成交量
        st.subheader("分佈圖：趨勢天數 vs 帶寬壓縮率")
        st.scatter_chart(
            filtered_df,
            x='trend_days',
            y='bbw_ratio',
            color='code',
            size='volume',
            use_container_width=True
        )

        # --- 詳細資料表格 ---
        st.subheader("詳細清單")
        
        # 整理要顯示的欄位與格式
        display_df = filtered_df[[
            'code', 'close_price', 'trend_days', 'bbw_ratio', 
            'volume', 'volume_break', 'ma5', 'ma20'
        ]].copy()

        # 顯示 Dataframe
        st.dataframe(
            display_df,
            column_config={
                "code": "股票代碼",
                "close_price": st.column_config.NumberColumn("收盤價", format="$%.2f"),
                "trend_days": "多頭天數",
                "bbw_ratio": st.column_config.NumberColumn("帶寬比率", format="%.4f"),
                "volume": "成交量",
                "volume_break": "爆量",
                "ma5": "MA5",
                "ma20": "MA20"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("在此篩選條件下，沒有符合的股票。請嘗試放寬條件。")