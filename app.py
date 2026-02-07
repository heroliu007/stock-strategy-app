import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# ==========================================
# 1. 網頁標題與側邊欄設定
# ==========================================
st.set_page_config(page_title="投信攻擊偵測儀", layout="wide")
st.title("🕵️‍♂️ 投信攻擊 + 動態籌碼分析")

# 側邊欄：使用者輸入區
st.sidebar.header("查詢設定")
stock_id = st.sidebar.text_input("輸入股票代號", value="2330")
days_back = st.sidebar.slider("回看天數", 30, 180, 90)

# 策略參數微調 (讓您可以隨時調整標準)
st.sidebar.markdown("---")
st.sidebar.subheader("策略參數")
it_days = st.sidebar.number_input("投信連買天數", min_value=1, value=2)
vol_mul = st.sidebar.number_input("爆量倍數", value=1.5)
it_ratio = st.sidebar.number_input("投信佔比(%)", value=2.0)

# ==========================================
# 2. 抓取數據函數 (FinMind)
# ==========================================
@st.cache_data(ttl=3600) # 設定快取，避免重複抓取
def load_data(stock_id, days):
    dl = DataLoader()
    end_date = datetime.date.today().strftime("%Y-%m-%d")
    start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    
    # 抓股價
    df_price = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
    if df_price.empty: return None
    
    # 抓籌碼
    df_chip = dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date, end_date=end_date)
    
    # 資料整理
    df_price = df_price.rename(columns={"date": "Date", "open": "Open", "max": "High", "min": "Low", "close": "Close", "Trading_Volume": "Volume"})
    df_price['Date'] = pd.to_datetime(df_price['Date'])
    df_price.set_index('Date', inplace=True)
    
    # 整理投信
    if not df_chip.empty:
        df_it = df_chip[df_chip['name'] == 'Investment_Trust']
        # 處理沒有投信數據的情況
        if df_it.empty:
            df_price['IT_Net'] = 0
        else:
            df_it = df_it[['date', 'buy', 'sell']]
            df_it['IT_Net'] = df_it['buy'] - df_it['sell']
            df_it['Date'] = pd.to_datetime(df_it['date'])
            df_it.set_index('Date', inplace=True)
            df_price = df_price.join(df_it['IT_Net']).fillna(0)
    else:
        df_price['IT_Net'] = 0
        
    return df_price

# ==========================================
# 3. 核心邏輯計算
# ==========================================
df = load_data(stock_id, days_back)

if df is not None:
    # 計算指標
    df['MA5_Vol'] = df['Volume'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    
    # 取得最新一筆資料
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    # 判斷策略條件
    # 1. 投信連買
    cond_it_buy = (last_row['IT_Net'] > 0) and (prev_row['IT_Net'] > 0)
    # 2. 投信佔比
    it_percent = (last_row['IT_Net'] / last_row['Volume'] * 100) if last_row['Volume'] > 0 else 0
    cond_it_ratio = it_percent >= it_ratio
    # 3. 爆量
    vol_ratio = last_row['Volume'] / last_row['MA5_Vol'] if last_row['MA5_Vol'] > 0 else 0
    cond_vol = vol_ratio >= vol_mul
    # 4. 長紅 (漲幅 > 3%)
    pct_change = (last_row['Close'] - last_row['Open']) / last_row['Open'] * 100
    cond_long_red = pct_change >= 3.0
    # 5. 季線之上
    cond_trend = last_row['Close'] > last_row['MA60']

    # ==========================================
    # 4. 畫面呈現
    # ==========================================
    
    # --- 狀態儀表板 ---
    st.subheader(f"📊 {stock_id} 分析結果 ({df.index[-1].strftime('%Y-%m-%d')})")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("收盤價", f"{last_row['Close']}", f"{pct_change:.2f}%")
    col2.metric("投信今日買賣", f"{int(last_row['IT_Net'])} 張", delta_color="normal")
    col3.metric("投信佔比", f"{it_percent:.2f}%", f"門檻: {it_ratio}%")
    col4.metric("量增倍數", f"{vol_ratio:.1f}倍", f"門檻: {vol_mul}倍")

    # --- 策略訊號燈 ---
    st.markdown("### 🚦 策略訊號檢測")
    c1, c2, c3, c4 = st.columns(4)
    c1.info("投信連買 ✅" if cond_it_buy else "投信未連買 ⬜")
    c2.info("投信佔比達標 ✅" if cond_it_ratio else "佔比不足 ⬜")
    c3.info("爆量攻擊 ✅" if cond_vol else "量能不足 ⬜")
    c4.info("多頭趨勢 ✅" if cond_trend else "股價弱勢 ⬜")

    if cond_it_buy and cond_it_ratio and cond_vol and cond_long_red and cond_trend:
        st.success("🔥🔥🔥 強力買進訊號出現！ 🔥🔥🔥")
    elif last_row['IT_Net'] < 0 and last_row['Close'] < last_row['MA10']:
        st.error("⚠️ 警戒：投信賣出且跌破10日線 (建議出場)")
    else:
        st.warning("觀察中 (未觸發特殊訊號)")

    # --- 互動式圖表 (K線 + 投信) ---
    st.markdown("---")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, row_heights=[0.7, 0.3])

    # K線圖
    fig.add_trace(go.Candlestick(x=df.index,
                    open=df['Open'], high=df['High'],
                    low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
    # 均線
    fig.add_trace(go.Scatter(x=df.index, y=df['MA10'], line=dict(color='orange', width=1), name='10日線'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='green', width=1), name='60日線'), row=1, col=1)

    # 投信買賣超 (柱狀圖)
    colors = ['red' if v > 0 else 'green' for v in df['IT_Net']]
    fig.add_trace(go.Bar(x=df.index, y=df['IT_Net'], marker_color=colors, name='投信買賣超'), row=2, col=1)

    fig.update_layout(height=600, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # 顯示數據表
    with st.expander("查看詳細歷史數據"):
        st.dataframe(df.sort_index(ascending=False).head(10))

else:
    st.error("找不到該股票數據，請確認代號是否正確。")