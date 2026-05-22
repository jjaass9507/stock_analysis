import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import datetime
import os
from dotenv import load_dotenv
import thread as crawler_thread

load_dotenv()

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="台股策略分析儀表板",
    page_icon="📈",
    layout="wide"
)

# --- 2. 資料庫連線設定 ---
DB_CONNECTION_STR = os.environ.get("NEON_DB_URL")
if not DB_CONNECTION_STR:
    st.error("請在 .env 或環境變數中設定 NEON_DB_URL")
    st.stop()

# --- 3. 載入資料函式 (含快取) ---
@st.cache_data(ttl=300)
def load_data(date_input):
    """從 Neon 資料庫讀取指定日期的分析資料。"""
    try:
        engine = create_engine(DB_CONNECTION_STR)
        query = text(
            "SELECT * FROM stock_daily_analysis "
            "WHERE record_date = :date ORDER BY code ASC"
        )
        df = pd.read_sql(query, engine, params={"date": date_input})
        return df
    except Exception as e:
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
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            min_trend = st.number_input("MA5 > MA20 最少天數", min_value=0, value=2, step=1)
        with col2:
            max_bbw = st.number_input("布林帶寬上限 ((上-下)/中)", value=0.15, step=0.01)
        with col3:
            only_vol_break = st.checkbox("只顯示爆量 (量 > 5日均量)", value=True)
        with col4:
            only_expanding = st.checkbox("只顯示帶寬擴張中", value=False,
                                         help="%B > 0 且今日帶寬 > 昨日帶寬，確認壓縮結束")

    # 篩選
    filtered_df = df[df['trend_days'] >= min_trend]
    filtered_df = filtered_df[filtered_df['bbw_ratio'] <= max_bbw]
    if only_vol_break:
        filtered_df = filtered_df[filtered_df['volume_break'] == True]
    if only_expanding and 'bbw_expanding' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['bbw_expanding'] == True]

    st.markdown("### 📊 篩選結果")
    st.write(f"在 {len(df)} 檔股票中，共有 **{len(filtered_df)}** 檔符合上述條件。")

    if not filtered_df.empty:
        # 散佈圖：X = 趨勢天數, Y = %B，帶寬越小泡泡越小
        st.subheader("分佈圖：多頭天數 vs %B 位置")
        has_percent_b = 'percent_b' in filtered_df.columns and filtered_df['percent_b'].notna().any()
        if has_percent_b:
            st.scatter_chart(
                filtered_df,
                x='trend_days',
                y='percent_b',
                color='code',
                size='bbw_ratio',
                use_container_width=True
            )
        else:
            st.scatter_chart(
                filtered_df,
                x='trend_days',
                y='bbw_ratio',
                color='code',
                size='volume',
                use_container_width=True
            )

        # 詳細清單
        st.subheader("詳細清單")

        base_cols   = ['code', 'close_price', 'trend_days', 'bbw_ratio', 'volume', 'volume_break', 'ma5', 'ma20']
        extra_cols  = [c for c in ['percent_b', 'bbw_expanding'] if c in filtered_df.columns]
        display_df  = filtered_df[base_cols + extra_cols].copy()

        col_cfg = {
            "code":          "股票代碼",
            "close_price":   st.column_config.NumberColumn("收盤價",   format="$%.2f"),
            "trend_days":    "多頭天數",
            "bbw_ratio":     st.column_config.NumberColumn("帶寬比率", format="%.4f"),
            "volume":        "成交量(張)",
            "volume_break":  "爆量",
            "ma5":           st.column_config.NumberColumn("MA5",  format="%.2f"),
            "ma20":          st.column_config.NumberColumn("MA20", format="%.2f"),
            "percent_b":     st.column_config.NumberColumn(
                                 "%B 位置", format="%.4f",
                                 help="0=下軌 / 0.5=中線 / 1=上軌，>1 突破上軌"),
            "bbw_expanding": st.column_config.CheckboxColumn(
                                 "帶寬擴張",
                                 help="True = 今日帶寬 > 昨日帶寬，壓縮結束訊號"),
        }

        st.dataframe(display_df, column_config=col_cfg, use_container_width=True, hide_index=True)
    else:
        st.warning("在此篩選條件下，沒有符合的股票。請嘗試放寬條件。")