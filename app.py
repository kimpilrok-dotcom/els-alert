import streamlit as st
import pandas as pd
import re

# 기존 main.py에서 크롤링 함수만 쏙 가져옵니다.
# (main.py 파일이 같은 폴더에 있어야 합니다)
try:
    from main import get_filtered_els
except ImportError:
    st.error("main.py 파일에서 get_filtered_els 함수를 불러올 수 없습니다.")

# =========================================================
# 1. 페이지 기본 설정
# =========================================================
st.set_page_config(page_title="나만의 ELS 검색기", page_icon="📈", layout="wide")
st.title("📈 ELS 맞춤형 검색 플랫폼")
st.markdown("금투협 데이터를 바탕으로 나만의 조건에 맞는 ELS를 찾아보세요.")

# =========================================================
# 2. 데이터 불러오기 및 전처리 (캐시 적용)
# =========================================================
# @st.cache_data를 붙이면, 슬라이더를 움직일 때마다 매번 크롤링하지 않고 데이터를 기억해둡니다!
@st.cache_data(ttl=3600) # 1시간 동안 데이터 기억
def load_and_prep_data():
    # 1. 원본 데이터 수집
    df = get_filtered_els()
    if df.empty:
        return pd.DataFrame()
        
    # 2. 숫자 추출 도구 (기존 코드 재사용)
    def get_numeric_yield(val):
        try:
            numbers = re.findall(r"[-+]?\d*\.?\d+", str(val))
            return float(numbers[0]) if numbers else 0.0
        except:
            return 0.0

    def get_numeric_ki(val):
        try:
            val_str = str(val).strip()
            if "노낙인" in val_str or "없음" in val_str or val_str == "-" or val_str == "":
                return 0.0
            numbers = re.findall(r"[-+]?\d*\.?\d+", val_str)
            return float(numbers[0]) if numbers else 0.0
        except:
            return 0.0

    # 3. 전처리 적용
    df["수익률(숫자)"] = df["조건 충족시\n수익률(연, %)"].apply(get_numeric_yield)
    df["낙인(숫자)"] = df["낙인(KI)"].apply(get_numeric_ki)
    
    # 달러(USD) 상품 여부 확인 열 추가
    df["USD여부"] = (df["상품명"].fillna("") + df["비고"].fillna("") + df["상품유형"].fillna("")).str.contains("USD|달러", case=False, regex=True)
    
    return df

# 데이터 로딩 실행
with st.spinner('금투협 데이터를 실시간으로 불러오는 중입니다...'):
    raw_df = load_and_prep_data()

# =========================================================
# 3. 사이드바 (왼쪽 필터 메뉴)
# =========================================================
st.sidebar.header("🔍 검색 조건 필터")

if not raw_df.empty:
    # 3-1. 수익률 필터 (슬라이더)
    max_yield_val = float(raw_df["수익률(숫자)"].max()) if not raw_df["수익률(숫자)"].empty else 20.0
    min_yield = st.sidebar.slider("💰 최소 수익률(%)", min_value=0.0, max_value=max_yield_val, value=10.0, step=0.5)

    # 3-2. 낙인 필터 (슬라이더)
    max_ki_val = float(raw_df["낙인(숫자)"].max()) if not raw_df["낙인(숫자)"].empty else 60.0
    max_ki = st.sidebar.slider("🛡️ 최대 낙인(%) (노낙인 제외)", min_value=10.0, max_value=max_ki_val, value=40.0, step=5.0)

    # 3-3. 부가 조건 (체크박스)
    st.sidebar.markdown("---")
    include_no_ki = st.sidebar.checkbox("✅ 노낙인(No KI) 상품 포함하기", value=False)
    only_usd = st.sidebar.checkbox("💵 USD(달러) 상품만 보기", value=False)

    # =========================================================
    # 4. 필터링 로직 및 결과 출력
    # =========================================================
    filtered_df = raw_df.copy()

    # 수익률 적용
    filtered_df = filtered_df[filtered_df["수익률(숫자)"] >= min_yield]

    # 낙인 적용 (노낙인 포함 여부에 따라 다르게 처리)
    if include_no_ki:
        # 지정된 낙인 이하이거나, 노낙인(0)인 경우
        filtered_df = filtered_df[(filtered_df["낙인(숫자)"] <= max_ki) | (filtered_df["낙인(숫자)"] == 0.0)]
    else:
        # 노낙인 제외하고 지정된 낙인 이하인 경우
        filtered_df = filtered_df[(filtered_df["낙인(숫자)"] <= max_ki) & (filtered_df["낙인(숫자)"] > 0.0)]

    # USD 적용
    if only_usd:
        filtered_df = filtered_df[filtered_df["USD여부"] == True]

    # 결과 요약 보여주기
    st.subheader(f"✅ 조건에 맞는 상품: 총 {len(filtered_df)}건")
    
    # 화면에 예쁜 표로 출력 (수익률 높은 순으로 정렬)
    if not filtered_df.empty:
        # 화면에 보여줄 주요 컬럼만 선택
        display_columns = ["발행회사", "상품명", "조건 충족시\n수익률(연, %)", "낙인(KI)", "기초자산", "청약종료일"]
        result_df = filtered_df.sort_values(by="수익률(숫자)", ascending=False)[display_columns]
        
        # Streamlit의 인터랙티브 데이터프레임 사용 (정렬, 확대 등 가능)
        st.dataframe(result_df, use_container_width=True, hide_index=True)
    else:
        st.warning("조건에 맞는 상품이 없습니다. 사이드바에서 조건을 조금 완화해 보세요.")
else:
    st.error("데이터를 불러오지 못했습니다.")