import streamlit as st
import pandas as pd
from kofia_els import automate_download, parse_kofia_file

st.set_page_config(page_title="나만의 ELS 검색기", page_icon="🎯", layout="wide")
st.title("🎯 나만의 맞춤형 ELS/DLS 검색기")

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

    # --- 필터 3: 증권사 ---
    company_col = next((col for col in raw_df.columns if '발행' in col or '회사' in col or '증권' in col), None)
    if company_col:
        company_options = sorted(raw_df[company_col].astype(str).unique().tolist())
        selected_companies = st.sidebar.multiselect("🏢 발행 증권사", company_options)
        if selected_companies:
            filtered_df = filtered_df[filtered_df[company_col].astype(str).isin(selected_companies)]

    # --- 💡 필터 4: 조기상환배리어 ---
    barrier_col = next((col for col in raw_df.columns if '상환' in col and '조건' in col), None)
    if barrier_col:
        search_barrier = st.sidebar.text_input("📉 조기상환배리어 (예: 95-95)")
        if search_barrier:
            filtered_df = filtered_df[filtered_df[barrier_col].astype(str).str.contains(search_barrier, na=False, case=False)]
    else:
        # 💡 [핵심] 컬럼을 못 찾으면 화면에 원본 컬럼 리스트를 강제로 띄웁니다!
        st.sidebar.warning("🚨 '상환조건' 열을 찾지 못했습니다. 아래 리스트에서 실제 이름을 확인해주세요:")
        st.sidebar.write(raw_df.columns.tolist())

    # --- 💡 필터 5: 조기상환주기 ---
    cycle_col = next((col for col in raw_df.columns if '주기' in col), None)
    if cycle_col:
        cycle_options = raw_df[cycle_col].dropna().astype(str).unique().tolist()
        cycle_options = [c for c in cycle_options if c.lower() != 'nan' and c.strip() != '']
        selected_cycle = st.sidebar.multiselect("⏳ 조기상환주기", sorted(cycle_options))
        if selected_cycle:
            filtered_df = filtered_df[filtered_df[cycle_col].astype(str).isin(selected_cycle)]
    else:
        if not barrier_col: pass
        else:
            st.sidebar.warning("🚨 '주기' 열을 찾지 못했습니다.")

    st.subheader(f"총 {len(filtered_df)}개의 ELS 상품이 검색되었습니다.")
    st.dataframe(filtered_df, use_container_width=True)

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
