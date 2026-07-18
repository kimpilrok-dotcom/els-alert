import streamlit as st
import pandas as pd
import re
import yfinance as yf
import plotly.graph_objects as go
from kofia_els import automate_download, parse_kofia_file
import numpy as np

st.set_page_config(page_title="나만의 ELS 검색기", page_icon="🎯", layout="wide")
st.title("🎯 나만의 맞춤형 ELS/DLS 검색기")
st.markdown("금투협 최신 데이터를 바탕으로 **원하는 조건의 상품만 쏙쏙** 골라보세요!")

@st.cache_data(ttl=3600)
def get_data():
    path = automate_download()
    df = parse_kofia_file(path)
    df.columns = df.columns.astype(str)
    filtered_df = df.drop(columns=["신용등급", "선택"], errors="ignore")
    
    if "기초자산" in filtered_df.columns:
        br_pattern = chr(60) + r"(?i)br\s*/?" + chr(62)
        filtered_df["기초자산"] = filtered_df["기초자산"].astype(str).str.replace(br_pattern, ", ", regex=True)
        
    return filtered_df

try:
    with st.spinner("로봇이 최신 데이터를 수집하고 있습니다... (최초 1회 약 15초)"):
        raw_df = get_data()
    
    st.sidebar.header("🔍 검색 조건 설정")
    filtered_df = raw_df.copy()

    if "유형" in raw_df.columns:
        type_options = raw_df["유형"].unique().tolist()
        selected_types = st.sidebar.multiselect("✅ 기초자산 유형", type_options, default=type_options)
        if selected_types:
            filtered_df = filtered_df[filtered_df["유형"].isin(selected_types)]

    if "낙인(KI)" in raw_df.columns:
        ki_options = sorted([k for k in raw_df["낙인(KI)"].unique() if str(k) != "-"])
        selected_ki = st.sidebar.multiselect("🛡️ 낙인(KI) 조건", ki_options)
        if selected_ki:
            filtered_df = filtered_df[filtered_df["낙인(KI)"].isin(selected_ki)]

    if "통화" in raw_df.columns:
        currency_options = sorted(raw_df["통화"].unique().tolist())
        selected_currency = st.sidebar.multiselect("💵 통화 (KRW/USD)", currency_options, default=currency_options)
        if selected_currency:
            filtered_df = filtered_df[filtered_df["통화"].isin(selected_currency)]

    if "만기" in raw_df.columns:
        maturity_options = sorted([m for m in raw_df["만기"].unique() if str(m) != "-"])
        selected_maturity = st.sidebar.multiselect("🗓️ 만기", maturity_options)
        if selected_maturity:
            filtered_df = filtered_df[filtered_df["만기"].isin(selected_maturity)]

    if "조기상환주기" in raw_df.columns:
        cycle_options = sorted([c for c in raw_df["조기상환주기"].unique() if str(c) != "-"])
        selected_cycle = st.sidebar.multiselect("⏳ 조기상환주기", cycle_options)
        if selected_cycle:
            filtered_df = filtered_df[filtered_df["조기상환주기"].isin(selected_cycle)]

    if "조기상환배리어" in raw_df.columns:
        first_barriers = raw_df["조기상환배리어"].astype(str).str.split('-').str[0]
        valid_barriers = list(set([b for b in first_barriers if b != "-" and b.strip() != ""]))
        barrier_options = sorted(valid_barriers, key=lambda x: float(x) if x.replace('.', '', 1).isdigit() else 0, reverse=True)
        
        selected_first_barrier = st.sidebar.multiselect("📉 최초상환배리어", barrier_options)
        if selected_first_barrier:
            filtered_df = filtered_df[filtered_df["조기상환배리어"].astype(str).str.split('-').str[0].isin(selected_first_barrier)]

    if "발행회사" in raw_df.columns:
        company_options = sorted(raw_df["발행회사"].astype(str).unique().tolist())
        selected_companies = st.sidebar.multiselect("🏢 발행 증권사", company_options)
        if selected_companies:
            filtered_df = filtered_df[filtered_df["발행회사"].isin(selected_companies)]
            
    if "기초자산" in raw_df.columns:
        all_assets = []
        for asset_str in raw_df["기초자산"].dropna():
            if str(asset_str).lower() != "nan" and str(asset_str).strip() != "":
                parts = [p.strip() for p in str(asset_str).split(',')]
                all_assets.extend(parts)
        
        unique_assets = list(set([a for a in all_assets if a]))
        index_keywords = ["INDEX", "지수", "KOSPI", "S&P", "EURO", "HSCEI", "NIKKEI", "STOXX", "NIFTY", "CSI", "KRX", "코스피", "다우", "나스닥", "DOW", "NASDAQ", "NDX", "항셍"]
        
        indices = []
        stocks = []
        for a in unique_assets:
            if any(k.upper() in a.upper() for k in index_keywords): indices.append(a)
            else: stocks.append(a)
                
        asset_options = sorted(indices) + sorted(stocks)
        selected_assets = st.sidebar.multiselect("🔎 기초자산 (지수형 먼저 표시)", asset_options)
        if selected_assets:
            mask = filtered_df["기초자산"].astype(str).apply(lambda x: any(sel in x for sel in selected_assets))
            filtered_df = filtered_df[mask]

    st.subheader(f"총 {len(filtered_df)}개의 ELS 상품이 검색되었습니다.")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 엑셀(표)", "📝 리스트(카드)", "📈 낙인 시뮬레이터", "🧪 과거 10년 롤링 백테스트"])
    
    with tab1:
        st.dataframe(filtered_df, use_container_width=True)
        
    with tab2:
        if len(filtered_df) == 0:
            st.info("조건에 맞는 상품이 없습니다.")
        else:
            tab2_df = filtered_df.copy()
            
            def extract_ki(val):
                s = str(val).strip()
                if "노낙인" in s or "없음" in s or s in ("-", ""): return 999.0
                nums = re.findall(r"[-+]?\d*\.?\d+", s)
                return float(nums[0]) if nums else 999.0
            
            def extract_yield(row):
                p_name = str(row.get("상품명", "-"))
                for c in row.index:
                    if "수익" in str(c):
                        v = str(row[c])
                        if v.lower() != "nan" and v != "":
                            nums = re.findall(r"[-+]?\d*\.?\d+", v.replace(",", ""))
                            if nums: return float(nums[0])
                m = re.search(r"(?:연\s*|)([\d\.]+)%", p_name)
                if m: return float(m.group(1))
                return 0.0
            
            tab2_df["_sort_ki"] = tab2_df["낙인(KI)"].apply(extract_ki)
            tab2_df["_sort_yield"] = tab2_df.apply(extract_yield, axis=1)
            
            tab2_df = tab2_df.sort_values(by=["_sort_ki", "_sort_yield"], ascending=[True, False])

            for idx, row in tab2_df.iterrows():
                def get_val(col_name):
                    v = str(row.get(col_name, "-"))
                    return "-" if v.lower() == "nan" or v == "" else v
                
                prod_name = get_val("상품명")
                currency = get_val("통화")
                assets = get_val("기초자산")
                ki = get_val("낙인(KI)")
                maturity = get_val("만기")
                cycle = get_val("조기상환주기")
                barrier = get_val("조기상환배리어")
                
                yield_val = "-"
                for c in row.index:
                    if "수익" in str(c):
                        v = str(row[c])
                        if v.lower() != "nan" and v != "":
                            yield_val = f"{v}%" if v.replace('.','',1).isdigit() else v
                        break
                if yield_val == "-":
                    m = re.search(r"(?:연\s*|)([\d\.]+)%", prod_name)
                    if m: yield_val = f"연 {m.group(1)}%"
                        
                start_date, end_date = "", ""
                for c in row.index:
                    if "청약" in str(c) and "시작" in str(c):
                        v = str(row[c]).split(' ')[0]
                        if v.lower() != "nan": start_date = v
                    elif "청약" in str(c) and "종료" in str(c):
                        v = str(row[c]).split(' ')[0]
                        if v.lower() != "nan": end_date = v
                        
                if start_date and end_date: sub_period = f"{start_date} ~ {end_date}"
                else:
                    sub_period = "-"
                    for c in row.index:
                        if "청약" in str(c) and "기간" in str(c):
                            v = str(row[c])
                            if v.lower() != "nan" and v != "": sub_period = v
                            break

                st.markdown(f'''
                
                    {prod_name}
                    
                        통화: {currency} 
                        기초자산: {assets} 
                        낙인(KI): {ki} 
                        수익율: {yield_val} 
                        청약기간: {sub_period} 
                        만기: {maturity} 
                        조기상환주기: {cycle} 
                        조기상환배리어: {barrier}
                    
                
                ''', unsafe_allow_html=True)
                
    with tab3:
        st.markdown("#### 📉 기초자산 10년 추이 및 현재가 기준 낙인선 분석")
        
        TICKER_MAP = {
            "S&P500": "^GSPC",
            "EUROSTOXX50": "^STOXX50E",
            "KOSPI200": "^KS200",
            "NIKKEI225": "^N225",
            "HSCEI": "^HSCE",
            "NASDAQ100": "^NDX"
        }
        
        col1, col2 = st.columns(2)
        with col1:
            selected_sim_asset = st.selectbox("분석할 대표 지수 선택", list(TICKER_MAP.keys()), key="sim_asset")
        with col2:
            ki_level = st.slider("가상 낙인(KI) 조건 설정 (%)", min_value=15, max_value=70, value=45, step=5, key="sim_ki")
            
        ticker_symbol = TICKER_MAP[selected_sim_asset]
        
        with st.spinner(f"{selected_sim_asset}의 과거 10년 금융 데이터를 불러오는 중입니다..."):
            try:
                ticker_data = yf.Ticker(ticker_symbol)
                hist = ticker_data.history(period="10y")
                
                if 'Close' in hist.columns:
                    hist = hist.dropna(subset=['Close'])
                
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
                    ki_price = current_price * (ki_level / 100.0)
                    
                    touch_points = hist[hist['Close'] <= ki_price]
                    
                    # 💡 변수 초기화
                    last_touch_date_str = "이력 없음"
                    last_touch_idx = None
                    last_touch_val = None
                    
                    if not touch_points.empty:
                        last_touch_idx = touch_points.index[-1]
                        last_touch_val = touch_points['Close'].iloc[-1]
                        last_touch_date_str = last_touch_idx.strftime('%Y-%m-%d')
                    
                    metric_col1, metric_col2, metric_col3 = st.columns(3)
                    metric_col1.metric(label=f"📊 {selected_sim_asset} 현재 지수", value=f"{current_price:,.2f}")
                    metric_col2.metric(label=f"🚨 가상 낙인선 ({ki_level}%)", value=f"{ki_price:,.2f}")
                    metric_col3.metric(label="⏱️ 가장 최근 낙인 터치일", value=last_touch_date_str, help="과거 10년 기준, 마지막으로 빨간 선 아래로 떨어졌던 날짜입니다.")
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', name='현재가 흐름', line=dict(color='#1E3A8A', width=1.5)))
                    fig.add_trace(go.Scatter(x=[hist.index[0], hist.index[-1]], y=[ki_price, ki_price], mode='lines', name=f'위험선 ({ki_level}%)', line=dict(color='#DC2626', width=2, dash='dash')))
                    
                    # 💡 [핵심 추가] 최근 터치일에 눈에 띄는 주황색 마커와 말풍선 추가
                    if last_touch_idx is not None:
                        fig.add_trace(go.Scatter(
                            x=[last_touch_idx], 
                            y=[last_touch_val],
                            mode='markers',
                            name='터치 지점',
                            marker=dict(color='#EA580C', size=12, line=dict(color='white', width=2))
                        ))
                        fig.add_annotation(
                            x=last_touch_idx,
                            y=last_touch_val,
                            text=f"최근 터치: {last_touch_date_str}",
                            showarrow=True,
                            arrowhead=2,
                            ax=0,
                            ay=-40,
                            font=dict(color="#EA580C", size=12, family="Arial Black"),
                            bgcolor="white",
                            bordercolor="#EA580C",
                            borderwidth=1.5
                        )
                    
                    fig.add_annotation(x=hist.index[-1], y=current_price, text=f"{current_price:,.2f}", showarrow=True, arrowhead=2, ax=40, ay=0, font=dict(color="#1E3A8A", size=13), bgcolor="white", bordercolor="#1E3A8A")
                    fig.add_annotation(x=hist.index[-1], y=ki_price, text=f"{ki_price:,.2f}", showarrow=True, arrowhead=2, ax=40, ay=0, font=dict(color="#DC2626", size=13), bgcolor="white", bordercolor="#DC2626")
                    
                    fig.update_layout(xaxis_title="연도", yaxis_title="지수 포인트", hovermode="x unified", showlegend=False, margin=dict(l=20, r=80, t=30, b=20))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("데이터를 불러올 수 없습니다.")
            except Exception as e:
                st.error(f"오류: {e}")

    with tab4:
        st.markdown("#### 🧪 기초자산 낙인(KI) 확률 백테스트 (Rolling Window)")
        st.markdown("과거 매 거래일마다 ELS(만기 3년)에 가입했다고 가정할 때, 3년 내에 낙인을 터치했을 확률을 계산합니다.")
        
        TICKER_MAP = {
            "S&P500": "^GSPC",
            "EUROSTOXX50": "^STOXX50E",
            "KOSPI200": "^KS200",
            "NIKKEI225": "^N225",
            "HSCEI": "^HSCE",
            "NASDAQ100": "^NDX"
        }
        
        col1, col2 = st.columns(2)
        with col1:
            bt_asset = st.selectbox("기초자산 선택", list(TICKER_MAP.keys()), key="bt_asset_2")
        with col2:
            bt_ki_level = st.slider("가정할 낙인(KI) 배리어 (%)", min_value=15, max_value=70, value=45, step=1, key="bt_ki_2")
            
        bt_ticker = TICKER_MAP[bt_asset]
        
        with st.spinner("과거 13년 치 데이터를 받아와 롤링 시뮬레이션을 돌리는 중입니다..."):
            try:
                bt_hist = yf.Ticker(bt_ticker).history(period="13y")
                if 'Close' in bt_hist.columns:
                    bt_hist = bt_hist.dropna(subset=['Close'])
                    
                if not bt_hist.empty:
                    prices = bt_hist['Close'].values
                    dates = bt_hist.index
                    
                    window_size = 252 * 3
                    total_valid_days = len(prices) - window_size
                    
                    if total_valid_days <= 0:
                        st.error("데이터가 충분하지 않아 3년 만기 백테스트를 수행할 수 없습니다.")
                    else:
                        knock_in_count = 0
                        hit_dates = []
                        hit_prices = []
                        
                        for i in range(total_valid_days):
                            issue_price = prices[i]
                            ki_price = issue_price * (bt_ki_level / 100.0)
                            window_min_price = np.min(prices[i : i + window_size])
                            
                            if window_min_price <= ki_price:
                                knock_in_count += 1
                                hit_dates.append(dates[i])
                                hit_prices.append(issue_price)
                                
                        probability = (knock_in_count / total_valid_days) * 100
                        
                        st.markdown("---")
                        res_col1, res_col2, res_col3 = st.columns(3)
                        res_col1.metric("총 시뮬레이션 횟수", f"{total_valid_days:,}일", help="과거 10년간 매일 ELS에 가입했다고 가정한 횟수입니다.")
                        res_col2.metric(f"낙인(KI) 도달 횟수", f"{knock_in_count:,}회", help="가입 후 3년 내에 설정한 낙인 배리어를 터치한 횟수입니다.", delta_color="inverse")
                        res_col3.metric("🚨 역사적 낙인 확률", f"{probability:.2f}%", help="이 지수에 해당 낙인 조건으로 가입했을 때의 과거 위험도입니다.")
                        
                        st.markdown(f"**📉 {bt_asset} 지수 흐름 및 낙인 발생 가입 시점 (Danger Zone)**")
                        fig_bt = go.Figure()
                        
                        fig_bt.add_trace(go.Scatter(x=dates, y=prices, mode='lines', name='지수 종가', line=dict(color='#9CA3AF', width=1)))
                        
                        if hit_dates:
                            fig_bt.add_trace(go.Scatter(x=hit_dates, y=hit_prices, mode='markers', name='낙인 발생 가입일', marker=dict(color='#DC2626', size=4)))
                        
                        fig_bt.update_layout(xaxis_title="연도", yaxis_title="지수 포인트", hovermode="x unified", margin=dict(l=20, r=20, t=30, b=20), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                        st.plotly_chart(fig_bt, use_container_width=True)
                        
            except Exception as e:
                st.error(f"백테스트 중 오류가 발생했습니다: {e}")

except Exception as e:
    st.error(f"전체 앱 오류가 발생했습니다: {e}")
