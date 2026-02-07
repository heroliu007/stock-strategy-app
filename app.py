import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import time

# ==========================================
# 1. 網頁與側邊欄設定
# ==========================================
st.set_page_config(page_title="投信攻擊偵測儀 v2.0", layout="wide")
st.title("🕵️‍♂️ 投信攻擊 + 動態籌碼分析")

# 側邊欄：模式選擇
mode = st.sidebar.radio("選擇功能模式", ["🔎 單股深度分析", "🚀 多股批次快篩"])

st.sidebar.markdown("---")
st.sidebar.subheader("策略參數設定")
it_days = st.sidebar.number_input("投信連買天數", min_value=1, value=2)
vol_mul = st.sidebar.number_input("爆量倍數", value=1.5)
it_ratio = st.sidebar.number_input("投信佔比(%)", value=2.0)

# ==========================================
# 2. 核心數據函數
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(stock_id, days=120):
    dl = DataLoader()
    end_date = datetime.date.today().strftime("%Y-%m-%d")
    start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    
    # 修正：使用正確的函數名稱
    try:
        df_price = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
        df_chip = dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date, end_date=end_date)
    except Exception as e:
        return None

    if df_price.empty: return None
    
    # 資料整理
    df_price = df_price.rename(columns={"date": "Date", "open": "Open", "max": "High", "min": "Low", "close": "Close", "Trading_Volume": "Volume"})
    df_price['Date'] = pd.to_datetime(df_price['Date'])
    df_price.set_index('Date', inplace=True)
    
    # 整理投信
    if not df_chip.empty:
        df_it = df_chip[df_chip['name'] == 'Investment_Trust']
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

def analyze_strategy(df):
    if df is None or len(df) < 60: return None
    
    # 計算指標
    df['MA5_Vol'] = df['Volume'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 策略邏輯
    res = {}
    res['price'] = last['Close']
    res['pct_change'] = (last['Close'] - last['Open']) / last['Open'] * 100
    
    # 條件
    res['cond_it_buy'] = (last['IT_Net'] > 0) and (prev['IT_Net'] > 0)
    res['it_percent'] = (last['IT_Net'] / last['Volume'] * 100) if last['Volume'] > 0 else 0
    res['cond_it_ratio'] = res['it_percent'] >= it_ratio
    
    vol_ratio = last['Volume'] / last['MA5_Vol'] if last['MA5_Vol'] > 0 else 0
    res['cond_vol'] = vol_ratio >= vol_mul
    
    res['cond_trend'] = last['Close'] > last['MA60']
    res['is_buy'] = res['cond_it_buy'] and res['cond_it_ratio'] and res['cond_vol'] and res['cond_trend']
    
    return res, df

# ==========================================
# 3. 介面邏輯
# ==========================================

if mode == "🔎 單股深度分析":
    stock_id = st.text_input("輸入股票代號", value="2330")
    days_back = st.slider("K線回看天數", 60, 365, 120)
    
    if stock_id:
        df = get_stock_data(stock_id, days_back)
        if df is not None:
            analysis, df_calc = analyze_strategy(df)
            
            # 顯示分析結果
            st.subheader(f"📊 {stock_id} 分析報告")
            
            # 訊號燈
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("投信連買", "✅ 是" if analysis['cond_it_buy'] else "❌ 否", f"今日:{int(df_calc.iloc[-1]['IT_Net'])}張")
            c2.metric("投信佔比", f"{analysis['it_percent']:.1f}%", f"門檻:{it_ratio}%")
            c3.metric("爆量倍數", f"{df_calc.iloc[-1]['Volume']/df_calc.iloc[-1]['MA5_Vol']:.1f}倍", f"門檻:{vol_mul}倍")
            c4.metric("趨勢狀態", "多頭 ✅" if analysis['cond_trend'] else "空頭 🔻")

            if analysis['is_buy']:
                st.success(f"🔥 {stock_id} 符合所有買進條件！主力正在攻擊！")
            
            # 畫圖
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=df_calc.index, open=df_calc['Open'], high=df_calc['High'], low=df_calc['Low'], close=df_calc['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_calc.index, y=df_calc['MA10'], line=dict(color='orange'), name='10日線'), row=1, col=1)
            fig.add_trace(go.Bar(x=df_calc.index, y=df_calc['IT_Net'], marker_color=['red' if v>0 else 'green' for v in df_calc['IT_Net']], name='投信'), row=2, col=1)
            fig.update_layout(height=500, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

elif mode == "🚀 多股批次快篩":
    st.info("💡 輸入多個代號 (用逗號分隔)，系統將自動找出符合「投信連買」的標的。")
    default_list = "2330, 2317, 2603, 3231, 2382, 2376, 2303, 2454, 3037, 3034"
    stock_list_str = st.text_area("輸入觀察名單 (例如：0050成份股或您的自選股)", value=default_list, height=100)
    
    if st.button("開始掃描"):
        stock_list = [s.strip() for s in stock_list_str.split(',') if s.strip()]
        
        progress_bar = st.progress(0)
        results = []
        
        for i, code in enumerate(stock_list):
            # 抓取並分析
            df = get_stock_data(code, days=60)
            if df is not None:
                analysis, _ = analyze_strategy(df)
                if analysis:
                    # 只要符合「投信連買」就列出來
                    if analysis['cond_it_buy']:
                        status = "🔥 符合策略" if analysis['is_buy'] else "👀 投信佈局中"
                        results.append({
                            "代號": code,
                            "狀態": status,
                            "現價": analysis['price'],
                            "投信佔比(%)": f"{analysis['it_percent']:.1f}",
                            "漲跌幅(%)": f"{analysis['pct_change']:.1f}"
                        })
            
            # 更新進度條
            progress_bar.progress((i + 1) / len(stock_list))
            time.sleep(0.1) # 避免請求過快
            
        if results:
            st.success(f"掃描完成！發現 {len(results)} 檔投信關注股")
            st.table(pd.DataFrame(results))
        else:
            st.warning("掃描完成，清單中沒有發現投信連買的股票。")