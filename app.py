import streamlit as st
import pandas as pd
import re
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

    # 💡 [수정된 정렬 기능] '노낙인', '낙인없음', '-' 기호는 무조건 밑으로 가도록 9999로 처리
    def get_sort_ki(ki_str):
        val = str(ki_str).strip()
        if "노낙인" in val or "없음" in val or val == "-": 
            return 9999.0
        m = re.search(r'(\d+)', val)
        if m: return float(m.group(1))
        return 9999.0

    def get_sort_yield(row):
        for c in row.index:
            if "수익" in str(c):
                v = str(row[c])
                if v.lower() != "nan" and v.strip() != "":
                    m = re.search(r'([\d\.]+)', v)
                    if m: return float(m.group(1))
        prod_name = str(row.get("상품명", ""))
        m = re.search(r"(?:연\s*|)([\d\.]+)%", prod_name)
        if m: return float(m.group(1))
        return 0.0

    filtered_df['sort_ki'] = filtered_df['낙인(KI)'].apply(get_sort_ki)
    filtered_df['sort_yield'] = filtered_df.apply(get_sort_yield, axis=1)
    
    # sort_ki(낙인)는 오름차순(낮은 것부터), sort_yield(수익률)는 내림차순(높은 것부터) 정렬
    filtered_df = filtered_df.sort_values(by=['sort_ki', 'sort_yield'], ascending=[True, False])
    filtered_df = filtered_df.drop(columns=['sort_ki', 'sort_yield'])

    st.subheader(f"총 {len(filtered_df)}개의 ELS 상품이 검색되었습니다.")
    
    tab1, tab2 = st.tabs(["📊 엑셀(표) 형태로 보기", "📝 리스트(카드) 형태로 보기"])
    
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
                        
                start_date = ""
                end_date = ""
                for c in row.index:
                    if "청약" in str(c) and "시작" in str(c):
                        v = str(row[c]).split(' ')[0]
                        if v.lower() != "nan": start_date = v
                    elif "청약" in str(c) and "종료" in str(c):
                        v = str(row[c]).split(' ')[0]
                        if v.lower() != "nan": end_date = v
                        
                if start_date and end_date:
                    sub_period = f"{start_date} ~ {end_date}"
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

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
