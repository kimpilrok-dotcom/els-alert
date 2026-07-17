import streamlit as st
import pandas as pd
from kofia_els import automate_download, parse_kofia_file

st.set_page_config(page_title="나만의 ELS 검색기", page_icon="🎯", layout="wide")
st.title("🎯 나만의 맞춤형 ELS/DLS 검색기")
st.markdown("금투협 최신 데이터를 바탕으로 **원하는 조건의 상품만 쏙쏙** 골라보세요!")

@st.cache_data(ttl=3600)
def get_data():
    path = automate_download()
    df = parse_kofia_file(path)
    df.columns = df.columns.astype(str)
    return df

try:
    with st.spinner("로봇이 최신 데이터를 수집하고 있습니다... (최초 1회 약 15초)"):
        raw_df = get_data()
    
    st.sidebar.header("🔍 검색 조건 설정")
    filtered_df = raw_df.copy()

    if '유형' in raw_df.columns:
        type_options = raw_df['유형'].unique().tolist()
        selected_types = st.sidebar.multiselect("✅ 기초자산 유형", type_options, default=type_options)
        if selected_types:
            filtered_df = filtered_df[filtered_df['유형'].isin(selected_types)]

    if '낙인(KI)' in raw_df.columns:
        ki_options = sorted([k for k in raw_df['낙인(KI)'].unique() if k != "-"])
        selected_ki = st.sidebar.multiselect("🛡️ 낙인(KI) 조건", ki_options)
        if selected_ki:
            filtered_df = filtered_df[filtered_df['낙인(KI)'].isin(selected_ki)]
            
    if '조기상환배리어' in raw_df.columns:
        search_barrier = st.sidebar.text_input("📉 조기상환배리어 검색 (예: 85-80)")
        if search_barrier:
            filtered_df = filtered_df[filtered_df['조기상환배리어'].astype(str).str.contains(search_barrier, na=False, case=False)]

    if '만기' in raw_df.columns:
        maturity_options = sorted([m for m in raw_df['만기'].unique() if m != "-"])
        selected_maturity = st.sidebar.multiselect("🗓️ 만기", maturity_options)
        if selected_maturity:
            filtered_df = filtered_df[filtered_df['만기'].isin(selected_maturity)]

    if '조기상환주기' in raw_df.columns:
        cycle_options = sorted([c for c in raw_df['조기상환주기'].unique() if c != "-"])
        selected_cycle = st.sidebar.multiselect("⏳ 조기상환주기", cycle_options)
        if selected_cycle:
            filtered_df = filtered_df[filtered_df['조기상환주기'].isin(selected_cycle)]

    if '발행회사' in raw_df.columns:
        company_options = sorted(raw_df['발행회사'].astype(str).unique().tolist())
        selected_companies = st.sidebar.multiselect("🏢 발행 증권사", company_options)
        if selected_companies:
            filtered_df = filtered_df[filtered_df['발행회사'].isin(selected_companies)]
            
    if '기초자산' in raw_df.columns:
        search_asset = st.sidebar.text_input("🔎 기초자산 검색 (예: 삼성전자, S&P)")
        if search_asset:
            filtered_df = filtered_df[filtered_df['기초자산'].astype(str).str.contains(search_asset, na=False, case=False)]

    st.subheader(f"총 {len(filtered_df)}개의 ELS 상품이 검색되었습니다.")
    filtered_df = filtered_df.drop(columns=["신용등급", "선택"], errors="ignore")
    st.dataframe(filtered_df, use_container_width=True)

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
