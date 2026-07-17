import streamlit as st
import pandas as pd
from kofia_els import automate_download, parse_kofia_file

# 1. 웹사이트 기본 설정
st.set_page_config(page_title="나만의 ELS 검색기", page_icon="🎯", layout="wide")
st.title("🎯 나만의 맞춤형 ELS/DLS 검색기")
st.markdown("금투협 최신 데이터를 바탕으로 **원하는 조건의 상품만 쏙쏙** 골라보세요!")

# 💡 [핵심 기술] 필터를 클릭할 때마다 엑셀을 다시 다운받지 않도록 '데이터를 기억(캐싱)' 해둡니다.
@st.cache_data(ttl=3600) # 1시간 동안 메모리에 저장
def get_data():
    path = automate_download()
    df = parse_kofia_file(path)
    df.columns = df.columns.astype(str)
    return df

try:
    # 데이터 불러오기
    with st.spinner("로봇이 최신 데이터를 수집하고 있습니다... (최초 1회만 대기)"):
        raw_df = get_data()
    
    # 2. 화면 왼쪽에 검색 조건(사이드바) 만들기
    st.sidebar.header("🔍 검색 조건 설정")
    
    # 필터링을 위해 원본 데이터를 복사합니다.
    filtered_df = raw_df.copy()

    # --- 필터 1: 기초자산 유형 ---
    if '유형' in raw_df.columns:
        type_options = raw_df['유형'].unique().tolist()
        selected_types = st.sidebar.multiselect("✅ 기초자산 유형", type_options, default=type_options)
        if selected_types:
            filtered_df = filtered_df[filtered_df['유형'].isin(selected_types)]

    # --- 필터 2: 낙인(KI) 조건 ---
    if '낙인(KI)' in raw_df.columns:
        ki_options = raw_df['낙인(KI)'].unique().tolist()
        selected_ki = st.sidebar.multiselect("🛡️ 낙인(KI) 조건", ki_options, default=ki_options)
        if selected_ki:
            filtered_df = filtered_df[filtered_df['낙인(KI)'].isin(selected_ki)]

    # --- 필터 3: 기초자산 이름 검색 ---
    asset_col = next((col for col in raw_df.columns if '기초자산' in col), None)
    if asset_col:
        search_asset = st.sidebar.text_input("🔎 기초자산 검색 (예: 삼성전자, S&P)")
        if search_asset:
            filtered_df = filtered_df[filtered_df[asset_col].astype(str).str.contains(search_asset, na=False, case=False)]
            
    # --- 필터 4: 발행 증권사 ---
    company_col = next((col for col in raw_df.columns if '발행' in col or '회사' in col or '증권' in col), None)
    if company_col:
        # 가나다순으로 깔끔하게 정렬해서 보여줍니다.
        company_options = sorted(raw_df[company_col].astype(str).unique().tolist())
        selected_companies = st.sidebar.multiselect("🏢 발행 증권사", company_options)
        if selected_companies:
            filtered_df = filtered_df[filtered_df[company_col].astype(str).isin(selected_companies)]

    # --- 💡 필터 5: 조기상환배리어 (새로 추가됨!) ---
    barrier_col = next((col for col in raw_df.columns if '상환' in col and '조건' in col), None)
    if barrier_col:
        # 배리어는 "95-95..." 처럼 다양하므로 직접 입력해서 찾도록 텍스트 검색을 씁니다.
        search_barrier = st.sidebar.text_input("📉 조기상환배리어 (예: 95-95, 85-80)")
        if search_barrier:
            filtered_df = filtered_df[filtered_df[barrier_col].astype(str).str.contains(search_barrier, na=False, case=False)]

    # --- 💡 필터 6: 조기상환주기 (새로 추가됨!) ---
    cycle_col = next((col for col in raw_df.columns if '주기' in col), None)
    if cycle_col:
        # 숫자나 글자(3, 6, 6개월 등)를 찾아 선택지로 깔끔하게 만듭니다.
        cycle_options = raw_df[cycle_col].dropna().astype(str).unique().tolist()
        cycle_options = [c for c in cycle_options if c.lower() != 'nan' and c.strip() != '']
        selected_cycle = st.sidebar.multiselect("⏳ 조기상환주기", sorted(cycle_options))
        if selected_cycle:
            filtered_df = filtered_df[filtered_df[cycle_col].astype(str).isin(selected_cycle)]

    # 3. 화면 오른쪽에 결과 표 보여주기
    st.subheader(f"총 {len(filtered_df)}개의 ELS 상품이 검색되었습니다. (전체 {len(raw_df)}개 중)")
    st.dataframe(filtered_df, use_container_width=True)

except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
