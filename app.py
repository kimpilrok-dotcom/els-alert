import streamlit as st
import pandas as pd
import re
import yfinance as yf
import plotly.graph_objects as go
from kofia_els import automate_download, parse_kofia_file

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
    
    tab1, tab2, tab3 = st.tabs(["📊 엑셀(표) 형태로 보기", "📝 리스트(카드) 형태로 보기", "📈 기초자산 낙인(KI) 시뮬레이터"])
    
    with tab1:
        st.dataframe(filtered_df, use_container_width=True)
        
    with tab2:
        if len(filtered_df) == 0:
            st.info("조건에 맞는 상품이 없습니다.")
        else:
            for idx, row in filtered_df.iterrows():
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
        st.markdown("오늘 ELS에 가입한다고 가정했을 때, 설정한 낙인(KI) 도달 위험이 과거 폭락장(코로나, 금융위기 등)과 비교해 어느 정도 수준인지 직관적으로 확인하세요.")
        
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
            selected_sim_asset = st.selectbox("분석할 대표 지수 선택", list(TICKER_MAP.keys()))
        with col2:
            ki_level = st.slider("가상 낙인(KI) 조건 설정 (%)", min_value=30, max_value=70, value=45, step=5)
            
        ticker_symbol = TICKER_MAP[selected_sim_asset]
        
        with st.spinner(f"{selected_sim_asset}의 과거 10년 금융 데이터를 불러오는 중입니다..."):
            try:
                ticker_data = yf.Ticker(ticker_symbol)
                hist = ticker_data.history(period="10y")
                
                # 💡 [핵심 수정] 야후 파이낸스의 KOSPI200 등 결측치(NaN) 버그 방지
                if 'Close' in hist.columns:
                    hist = hist.dropna(subset=['Close'])
                
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
                    ki_price = current_price * (ki_level / 100.0)
                    
                    fig = go.Figure()
                    
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', name=selected_sim_asset, line=dict(color='#1E3A8A', width=1.5)))
                    fig.add_trace(go.Scatter(x=[hist.index[0], hist.index[-1]], y=[ki_price, ki_price], mode='lines', name=f'위험선 (현재가의 {ki_level}%)', line=dict(color='#DC2626', width=2, dash='dash')))
                    
                    fig.update_layout(
                        title=f"{selected_sim_asset} (최근 10년)",
                        xaxis_title="연도",
                        yaxis_title="지수 포인트",
                        hovermode="x unified",
                        margin=dict(l=20, r=20, t=50, b=20)
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.info(f"💡 **현재 지수:** {current_price:,.2f} 포인트 ➔ **가상의 {ki_level}% 낙인선:** {ki_price:,.2f} 포인트\n\n위 그래프의 **빨간 점선**이 낙인선입니다. 과거 10년 동안 이 점선 밑으로 지수가 떨어진 적이 몇 번이나 있었는지 시각적으로 체크해 보세요.")
                else:
                    st.warning("데이터를 불러올 수 없습니다. 일시적인 야후 파이낸스 서버 오류일 수 있습니다.")
            except Exception as e:
                st.error(f"데이터를 불러오는 데 실패했습니다: {e}")

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
