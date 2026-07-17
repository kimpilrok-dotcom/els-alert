import streamlit as st
import pandas as pd
from kofia_els import automate_download, parse_kofia_file

# 1. 웹사이트 기본 설정
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
    with st.spinner("로봇이 최신 데이터를 수집하고 있습니다..."):
        raw_df = get_data()
    
    st.sidebar.header("🔍 검색 조건 설정")
    filtered_df = raw_df.copy()

    # --- 필터 1: 기초자산 유형 ---
    if '유형' in raw_df.columns:
        type_options = raw_df['유형'].unique().tolist()
        selected_types = st.sidebar.multiselect("✅ 기초자산 유형", type_options, default=type_options)
        if selected_types:
            filtered_df = filtered_df[filtered_df['유형'].isin(selected_types)]

    # --- 필터 2: 낙인(KI) ---
    if '낙인(KI)' in raw_df.columns:
        ki_options = raw_df['낙인(KI)'].unique().tolist()
        selected_ki = st.sidebar.multiselect("🛡️ 낙인(KI) 조건", ki_options, default=ki_options)
        if selected_ki:
            filtered_df = filtered_df[filtered_df['낙인(KI)'].isin(selected_ki)]

    # --- 필터 3: 증권사 (정확한 열 이름 반영) ---
    if '발행회사' in raw_df.columns:
        company_options = sorted(raw_df['발행회사'].astype(str).unique().tolist())
        selected_companies = st.sidebar.multiselect("🏢 발행 증권사", company_options)
        if selected_companies:
            filtered_df = filtered_df[filtered_df['발행회사'].isin(selected_companies)]
            
    # --- 필터 4: 기초자산 검색 ---
    if '기초자산' in raw_df.columns:
        search_asset = st.sidebar.text_input("🔎 기초자산 검색 (예: 삼성전자, S&P)")
        if search_asset:
            filtered_df = filtered_df[filtered_df['기초자산'].astype(str).str.contains(search_asset, na=False, case=False)]

    # --- 💡 필터 5: 조기상환배리어 (상품명에서 똑똑하게 찾기) ---
    if '상품명' in raw_df.columns:
        search_barrier = st.sidebar.text_input("📉 조기상환배리어 (예: 95-95, 85-80)")
        if search_barrier:
            # 상품명 안에 해당 숫자가 포함되어 있는지 검사합니다.
            filtered_df = filtered_df[filtered_df['상품명'].astype(str).str.contains(search_barrier, na=False, case=False)]

    # --- 💡 필터 6: 조기상환주기 (자주 쓰는 주기 버튼화) ---
    if '상품명' in raw_df.columns:
        cycle_options = ["3개월", "4개월", "6개월", "1년"]
        selected_cycle = st.sidebar.multiselect("⏳ 조기상환주기", cycle_options)
        if selected_cycle:
            # 선택한 주기(예: 3개월, 6개월) 중 하나라도 상품명에 포함된 것을 걸러냅니다.
            pattern = '|'.join(selected_cycle)
            filtered_df = filtered_df[filtered_df['상품명'].astype(str).str.contains(pattern, na=False)]

    # 3. 화면 오른쪽에 결과 표 보여주기
    st.subheader(f"총 {len(filtered_df)}개의 ELS 상품이 검색되었습니다.")
    st.dataframe(filtered_df, use_container_width=True)

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
