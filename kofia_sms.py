import pandas as pd
import numpy as np
from kofia_els import automate_download, parse_kofia_file

def get_filtered_els():
    file_path = automate_download()
    if not file_path:
        return None
        
    df = parse_kofia_file(file_path)
    if df is None or df.empty:
        return None
    
    if "유형" in df.columns:
        df = df[df["유형"] == "지수형"].copy()

    # 💡 최적화 1: 이중 루프를 막기 위해, 필요한 컬럼명들을 먼저 단 1번만 찾아둡니다.
    yield_cols = [c for c in df.columns if "수익" in str(c)]
    start_cols = [c for c in df.columns if "청약" in str(c) and "시작" in str(c)]
    end_cols = [c for c in df.columns if "청약" in str(c) and "종료" in str(c)]
    period_cols = [c for c in df.columns if "청약" in str(c) and "기간" in str(c)]

    # --- 1. 수익률 추출 (Vectorized) ---
    yield_series = pd.Series(np.nan, index=df.index)
    
    # 찾은 수익 컬럼들에서 유효한 값을 한 번에 덮어씌움
    for col in yield_cols:
        valid_mask = df[col].astype(str).str.lower().replace(['nan', 'none', ''], np.nan).notna()
        yield_series = np.where(yield_series.isna() & valid_mask, df[col], yield_series)
        
    yield_series = pd.Series(yield_series, index=df.index).fillna("0")

    # 값이 0인 경우 상품명에서 정규식으로 한 번에 추출
    if "상품명" in df.columns:
        mask = yield_series == "0"
        extracted = df.loc[mask, "상품명"].astype(str).str.extract(r"(?:연\s*|)([\d\.]+)%")[0]
        yield_series.loc[mask] = extracted.fillna("0")
        
    # 숫자 이외의 문자 한 번에 제거 후 float 형변환
    yield_num = yield_series.astype(str).str.replace(r"[^\d\.]", "", regex=True)
    yield_num = pd.to_numeric(yield_num, errors='coerce').fillna(0.0)

    # --- 2. 청약기간 조립 (Vectorized) ---
    start_series = df[start_cols[0]].astype(str).str.split(' ').str[0] if start_cols else pd.Series("", index=df.index)
    end_series = df[end_cols[0]].astype(str).str.split(' ').str[0] if end_cols else pd.Series("", index=df.index)
    
    # 결측치 텍스트("") 처리
    start_series = start_series.replace({r"(?i)nan": "", "None": "", "<NA>": ""}, regex=True)
    end_series = end_series.replace({r"(?i)nan": "", "None": "", "<NA>": ""}, regex=True)
    
    # 두 시리즈를 합쳐 "시작일 ~ 종료일" 구성
    combined_period = np.where((start_series != "") & (end_series != ""), start_series + " ~ " + end_series, "")
    
    if period_cols:
        p_col = df[period_cols[0]].astype(str).replace({r"(?i)nan": "", "None": "", "<NA>": ""}, regex=True)
        final_period = np.where(combined_period != "", combined_period, p_col)
    else:
        final_period = combined_period
        
    final_period = np.where(final_period == "", "-", final_period)
    period_series = pd.Series(final_period, index=df.index)

    # --- 3. 문자열 클리닝 함수 (💡 루프 대신 Pandas C엔진 활용) ---
    def clean_vectorized(series, default_val="-"):
        if series is None or (isinstance(series, pd.Series) and series.empty):
            return pd.Series(default_val, index=df.index)
        
        # 결측치를 먼저 기본값으로 치환
        s = series.astype(str).replace({r"(?i)nan": default_val, "None": default_val, "": default_val}, regex=True)
        # HTML 태그 제거
        s = s.str.replace(r'<br\s*/?>', ' ', case=False, regex=True)
        # Index 단어 제거
        s = s.str.replace(r'\bIndex\b', '', case=False, regex=True)
        # 띄어쓰기 정리
        s = s.str.replace(r'\s+', ' ', regex=True).str.strip()
        return s

    # --- 4. 결과 DataFrame 생성 (빠른 할당) ---
    result_df = pd.DataFrame({
        "상품명": clean_vectorized(df.get("상품명")),
        "기초자산": clean_vectorized(df.get("기초자산")),
        "낙인(KI)": clean_vectorized(df.get("낙인(KI)"), "노낙인"),
        "수익률": yield_num,
        "수익률_텍스트": yield_num.astype(str) + "%",
        "청약기간": clean_vectorized(period_series),
        "발행회사": clean_vectorized(df.get("발행회사")),
        "만기": clean_vectorized(df.get("만기")),
        "조기상환주기": clean_vectorized(df.get("조기상환주기")),
        "조기상환배리어": clean_vectorized(df.get("조기상환배리어"))
    })
    
    # 수익률 기준 정렬 및 인덱스 리셋
    if not result_df.empty:
        result_df = result_df.sort_values(by="수익률", ascending=False).reset_index(drop=True)
        
    return result_df
