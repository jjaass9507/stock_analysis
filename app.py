import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import datetime
import os
from dotenv import load_dotenv
import thread as crawler_thread

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# 頁面設定
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="布林策略儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# 深色主題 CSS（仿 TradingView / Bloomberg 風格）
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── 全域背景 ── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: #0d1117;
}
[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #21262d;
}
[data-testid="stHeader"] { background-color: transparent; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* ── 全域文字 ── */
html, body, [class*="css"], .stMarkdown, p, span, label {
    color: #e6edf3;
}
.stSidebar p, .stSidebar label, .stSidebar span { color: #c9d1d9; }

/* ── 指標卡 ── */
[data-testid="metric-container"] {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
    transition: border-color 0.2s;
}
[data-testid="metric-container"]:hover { border-color: #1f6feb; }
[data-testid="stMetricLabel"] {
    color: #8b949e !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
}
[data-testid="stMetricValue"] {
    color: #e6edf3 !important;
    font-size: 1.75rem !important;
    font-weight: 700;
    line-height: 1.1;
}
[data-testid="stMetricDelta"] { font-size: 0.8rem !important; }

/* ── 按鈕 ── */
.stButton > button {
    background: #1f6feb !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    padding: 0.45rem 1.1rem !important;
    transition: background 0.15s ease, transform 0.1s ease;
}
.stButton > button:hover {
    background: #388bfd !important;
    transform: translateY(-1px);
}
.stButton > button:active { transform: translateY(0); }

/* ── 輸入框 ── */
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
input[type="number"], input[type="text"] {
    background: #21262d !important;
    color: #e6edf3 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
}
[data-testid="stNumberInput"] input:focus,
[data-testid="stDateInput"] input:focus {
    border-color: #1f6feb !important;
    box-shadow: 0 0 0 2px rgba(31,111,235,0.2) !important;
}

/* ── Checkbox ── */
[data-testid="stCheckbox"] label { color: #c9d1d9 !important; font-size: 0.88rem; }
[data-testid="stCheckbox"] span[data-baseweb="checkbox"] > div {
    background: #21262d !important;
    border-color: #30363d !important;
    border-radius: 4px !important;
}
[data-testid="stCheckbox"] input:checked + div {
    background: #1f6feb !important;
    border-color: #1f6feb !important;
}

/* ── Tabs ── */
[data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid #21262d;
    gap: 0;
}
[data-baseweb="tab"] {
    color: #8b949e !important;
    border-bottom: 2px solid transparent !important;
    padding: 0.55rem 1.2rem !important;
    font-weight: 500;
    font-size: 0.88rem;
    background: transparent !important;
    transition: color 0.15s;
}
[data-baseweb="tab"]:hover { color: #c9d1d9 !important; }
[aria-selected="true"][data-baseweb="tab"] {
    color: #e6edf3 !important;
    border-bottom-color: #1f6feb !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
}
[data-testid="stExpander"] summary {
    color: #8b949e;
    font-size: 0.85rem;
}

/* ── DataFrame ── */
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

/* ── Alert / Info ── */
[data-testid="stAlert"] {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 8px !important;
    color: #c9d1d9 !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] > div { color: #1f6feb !important; }

/* ── 分隔線 ── */
hr { border-color: #21262d !important; margin: 0.75rem 0; }

/* ── Caption ── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #6e7681 !important;
    font-size: 0.78rem;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# DB 連線（cache_resource = 整個 App 生命週期只建立一次引擎）
# ─────────────────────────────────────────────────────────────────────────────
DB_CONNECTION_STR = os.environ.get("NEON_DB_URL")
if not DB_CONNECTION_STR:
    st.error("請在 .env 或 Render 環境變數中設定 NEON_DB_URL")
    st.stop()


@st.cache_resource
def get_engine():
    return create_engine(DB_CONNECTION_STR, pool_pre_ping=True)


# ─────────────────────────────────────────────────────────────────────────────
# 資料載入（只抓需要的欄位，依帶寬由小到大排序）
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data(date_input: datetime.date) -> pd.DataFrame:
    try:
        query = text("""
            SELECT code, close_price, volume, ma5, ma20,
                   ub, lb, bbw_ratio, trend_days,
                   volume_break, percent_b, bbw_expanding
            FROM stock_daily_analysis
            WHERE record_date = :date
            ORDER BY bbw_ratio ASC
        """)
        return pd.read_sql(query, get_engine(), params={"date": date_input})
    except Exception as e:
        st.error(f"資料庫讀取失敗：{e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 側邊欄
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<h3 style='color:#e6edf3;margin-bottom:0.2rem'>⚙️ 控制台</h3>",
        unsafe_allow_html=True,
    )
    st.markdown("<hr>", unsafe_allow_html=True)

    select_date = st.date_input("📅 查看日期", datetime.date.today())

    st.markdown("<hr>", unsafe_allow_html=True)

    if st.button("🚀 執行爬蟲更新", use_container_width=True):
        with st.spinner("正在抓取 TWSE / TPEX 資料，約需 5–10 分鐘…"):
            try:
                msg = crawler_thread.run_crawler_pipeline()
                if "成功" in msg:
                    st.success(msg)
                    st.cache_data.clear()
                else:
                    st.warning(msg)
            except Exception as e:
                st.error(f"執行失敗：{e}")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6e7681;font-size:0.75rem;line-height:1.6'>"
        "資料來源：TWSE / TPEX 官方 API<br>"
        "策略：布林收口 + MA5>MA20 + 量能突破<br>"
        "快取：5 分鐘 TTL</p>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# 主標題
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    "<h2 style='color:#e6edf3;margin-bottom:2px;font-weight:700'>"
    "📈 台股布林策略選股</h2>"
    f"<p style='color:#8b949e;margin-top:0;font-size:0.88rem'>"
    f"{select_date.strftime('%Y 年 %m 月 %d 日')} 分析報告</p>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# 載入資料
# ─────────────────────────────────────────────────────────────────────────────
df = load_data(select_date)

if df.empty:
    st.info(
        f"📅 {select_date} 尚無資料。"
        "請點擊左側「執行爬蟲更新」，或選擇其他有資料的日期。"
    )
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# 篩選條件（內嵌，不佔用側邊欄）
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("🔍 篩選條件", expanded=True):
    fc1, fc2, fc3, fc4 = st.columns([1.2, 1.2, 1, 1])
    with fc1:
        min_trend = st.number_input("多頭天數 ≥", min_value=0, value=2, step=1)
    with fc2:
        max_bbw = st.number_input("帶寬比率 ≤", value=0.15, step=0.01, format="%.2f")
    with fc3:
        only_vol = st.checkbox("爆量篩選", value=True, help="成交量 > 5 日均量")
    with fc4:
        only_exp = st.checkbox(
            "帶寬擴張", value=False,
            help="今日帶寬 > 昨日帶寬，壓縮結束訊號"
        )

# 套用篩選
fdf = df.copy()
fdf = fdf[fdf["trend_days"] >= min_trend]
fdf = fdf[fdf["bbw_ratio"] <= max_bbw]
if only_vol:
    fdf = fdf[fdf["volume_break"] == True]
if only_exp and "bbw_expanding" in fdf.columns:
    fdf = fdf[fdf["bbw_expanding"] == True]

# ─────────────────────────────────────────────────────────────────────────────
# 指標卡（4格）
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
m1, m2, m3, m4 = st.columns(4)

total   = len(df)
matched = len(fdf)
hit_pct = f"{matched / total * 100:.1f}%" if total > 0 else "—"
avg_bbw = round(fdf["bbw_ratio"].mean(), 4) if not fdf.empty else 0

has_exp_col = "bbw_expanding" in fdf.columns
strong = int(fdf["bbw_expanding"].sum()) if has_exp_col and not fdf.empty else 0

with m1:
    st.metric("掃描股票數", f"{total:,}")
with m2:
    st.metric("符合條件", f"{matched:,}", delta=hit_pct)
with m3:
    st.metric("平均帶寬比率", f"{avg_bbw:.4f}")
with m4:
    st.metric("帶寬擴張訊號", f"{strong:,}", help="帶寬擴張 = True 的股票數")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 無結果提示
# ─────────────────────────────────────────────────────────────────────────────
if fdf.empty:
    st.warning("⚠️ 目前篩選條件下沒有符合的股票，請嘗試放寬條件。")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab_table, tab_chart, tab_guide = st.tabs(["📋 訊號列表", "📊 分佈圖", "💡 指標說明"])

# ── Tab 1：訊號列表 ────────────────────────────────────────────────────────
with tab_table:
    base_cols  = ["code", "close_price", "trend_days", "bbw_ratio",
                  "volume", "volume_break", "ma5", "ma20"]
    extra_cols = [c for c in ["percent_b", "bbw_expanding"] if c in fdf.columns]
    disp = fdf[base_cols + extra_cols].copy().reset_index(drop=True)

    # %B 超出 [0,1] 的做 clip，ProgressColumn 只顯示 0–1 範圍
    if "percent_b" in disp.columns:
        disp["percent_b"] = disp["percent_b"].clip(0, 1)

    col_cfg = {
        "code": st.column_config.TextColumn("代碼", width="small"),
        "close_price": st.column_config.NumberColumn(
            "收盤價", format="$%.2f", width="small"
        ),
        "trend_days": st.column_config.NumberColumn(
            "多頭天數", format="%d 天", width="small"
        ),
        "bbw_ratio": st.column_config.ProgressColumn(
            "帶寬比率",
            min_value=0, max_value=0.3,
            format="%.4f",
            help="越小代表布林帶壓縮越緊，突破潛力越大",
        ),
        "volume": st.column_config.NumberColumn("量(張)", format="%d", width="small"),
        "volume_break": st.column_config.CheckboxColumn("爆量", width="small"),
        "ma5":  st.column_config.NumberColumn("MA5",  format="%.2f", width="small"),
        "ma20": st.column_config.NumberColumn("MA20", format="%.2f", width="small"),
        "percent_b": st.column_config.ProgressColumn(
            "%B 位置",
            min_value=0, max_value=1,
            format="%.3f",
            help="0 = 下軌｜0.5 = 中線｜1 = 上軌",
        ),
        "bbw_expanding": st.column_config.CheckboxColumn(
            "帶寬擴張",
            help="True = 今日帶寬 > 昨日帶寬，壓縮結束訊號",
            width="small",
        ),
    }

    st.dataframe(
        disp, column_config=col_cfg,
        use_container_width=True, hide_index=True,
        height=420,
    )
    st.caption(
        f"顯示 {len(disp)} 筆｜依帶寬比率由小到大排列（帶寬越小 = 壓縮越緊）"
    )

# ── Tab 2：分佈圖 ─────────────────────────────────────────────────────────
with tab_chart:
    has_pb = "percent_b" in fdf.columns and fdf["percent_b"].notna().any()

    if has_pb:
        plot_df = fdf.copy()

        if has_exp_col:
            plot_df["_label"] = plot_df["bbw_expanding"].map(
                {True: "帶寬擴張", False: "持續收口"}
            ).fillna("持續收口")
        else:
            plot_df["_label"] = "股票"

        COLOR_MAP = {"帶寬擴張": "#39d353", "持續收口": "#4d5566", "股票": "#1f6feb"}

        fig = go.Figure()

        for label, color in COLOR_MAP.items():
            sub = plot_df[plot_df["_label"] == label]
            if sub.empty:
                continue
            custom = sub[["code", "bbw_ratio", "close_price", "volume"]].values
            fig.add_trace(go.Scatter(
                x=sub["trend_days"],
                y=sub["percent_b"],
                mode="markers",
                name=label,
                marker=dict(
                    color=color, size=9, opacity=0.85,
                    line=dict(width=1, color="rgba(255,255,255,0.08)"),
                ),
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%B：<b>%{y:.4f}</b><br>"
                    "多頭天數：%{x} 天<br>"
                    "帶寬比率：%{customdata[1]:.4f}<br>"
                    "收盤：$%{customdata[2]:.2f}<br>"
                    "量：%{customdata[3]:,} 張"
                    "<extra></extra>"
                ),
            ))

        # 參考線
        for y_val, label_text, color in [
            (1.0, "上軌", "#f85149"),
            (0.5, "中線", "#8b949e"),
            (0.0, "下軌", "#39d353"),
        ]:
            fig.add_hline(
                y=y_val, line_dash="dot", line_color=color, opacity=0.45,
                annotation_text=label_text,
                annotation_font_color=color,
                annotation_font_size=11,
                annotation_position="right",
            )

        fig.update_layout(
            paper_bgcolor="#0d1117",
            plot_bgcolor="#161b22",
            font=dict(color="#e6edf3", family="system-ui, -apple-system, sans-serif"),
            xaxis=dict(
                title="多頭天數",
                gridcolor="#1e2632", gridwidth=1,
                color="#8b949e", tickcolor="#30363d",
                showline=True, linecolor="#21262d",
            ),
            yaxis=dict(
                title="%B 位置",
                gridcolor="#1e2632", gridwidth=1,
                color="#8b949e", tickcolor="#30363d",
                showline=True, linecolor="#21262d",
                range=[-0.15, 1.25],
            ),
            legend=dict(
                bgcolor="#161b22", bordercolor="#21262d",
                borderwidth=1,
                font=dict(color="#c9d1d9", size=12),
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1,
            ),
            hovermode="closest",
            height=430,
            margin=dict(l=55, r=90, t=40, b=50),
        )

        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "💡 綠色 = 帶寬擴張中（壓縮剛結束）｜"
            "%B 越接近 1.0 代表收盤越靠近上軌｜點擊圖例可切換顯示"
        )
    else:
        st.info("資料中沒有 %B 欄位，請執行最新爬蟲後重新查看。")

# ── Tab 3：指標說明 ───────────────────────────────────────────────────────
with tab_guide:
    c_l, c_r = st.columns(2)

    with c_l:
        st.markdown(
            """
<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:1.2rem">
<h4 style="color:#e6edf3;margin-top:0">🔵 布林帶指標</h4>
<table style="width:100%;border-collapse:collapse;font-size:0.85rem">
<tr style="border-bottom:1px solid #21262d">
  <td style="padding:6px 8px;color:#8b949e;width:40%">帶寬比率</td>
  <td style="padding:6px 8px;color:#c9d1d9">(上軌 - 下軌) / MA20<br>越小代表壓縮越緊</td>
</tr>
<tr style="border-bottom:1px solid #21262d">
  <td style="padding:6px 8px;color:#8b949e">%B 位置</td>
  <td style="padding:6px 8px;color:#c9d1d9">(收盤 - 下軌) / (上軌 - 下軌)<br>0=下軌 / 0.5=中線 / 1=上軌</td>
</tr>
<tr>
  <td style="padding:6px 8px;color:#8b949e">帶寬擴張</td>
  <td style="padding:6px 8px;color:#c9d1d9">今日帶寬 > 昨日帶寬<br>壓縮結束、開始放大的確認訊號</td>
</tr>
</table>
</div>
            """,
            unsafe_allow_html=True,
        )

    with c_r:
        st.markdown(
            """
<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:1.2rem">
<h4 style="color:#e6edf3;margin-top:0">🟢 策略篩選邏輯</h4>
<table style="width:100%;border-collapse:collapse;font-size:0.85rem">
<tr style="border-bottom:1px solid #21262d">
  <td style="padding:6px 8px;color:#8b949e;width:40%">多頭趨勢</td>
  <td style="padding:6px 8px;color:#c9d1d9">MA5 &gt; MA20 連續 N 天<br>確認短期多頭格局</td>
</tr>
<tr style="border-bottom:1px solid #21262d">
  <td style="padding:6px 8px;color:#8b949e">量能突破</td>
  <td style="padding:6px 8px;color:#c9d1d9">成交量 &gt; 5 日均量<br>資金流入確認</td>
</tr>
<tr>
  <td style="padding:6px 8px;color:#8b949e">最強訊號組合</td>
  <td style="padding:6px 8px;color:#39d353;font-weight:600">
    布林收口 + 帶寬擴張<br>+ 多頭趨勢 + 爆量
  </td>
</tr>
</table>
</div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown(
        """
<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:1rem 1.2rem">
<p style="color:#8b949e;font-size:0.82rem;margin:0">
⚠️ <b style="color:#c9d1d9">免責聲明</b>：本平台僅提供技術面篩選結果，不構成投資建議。
投資有風險，請自行評估並負擔投資決策責任。
</p>
</div>
        """,
        unsafe_allow_html=True,
    )
