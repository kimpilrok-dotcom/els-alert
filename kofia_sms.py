import pandas as pd
import numpy as np
import re
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
        
    if df.empty:
        return pd.DataFrame()

    # 💡 최적화 1: 이중 루프 제거 (매 행마다 컬럼을 찾지 않고 단 1번만 미리 탐색)
    yield_cols = [c for c in df.columns if "수익" in str(c)]
    start_cols = [c for c in df.columns if "청약" in str(c) and "시작" in str(c)]
    end_cols = [c for c in df.columns if "청약" in str(c) and "종료" in str(c)]
    period_cols = [c for c in df.columns if "청약" in str(c) and "기간" in str(c)]

    # --- 1. 수익률 추출 (Vectorized) ---
    yield_series = pd.Series("0", index=df.index)
    
    # 미리 찾은 수익 컬럼들을 순회하며 가장 처음 나오는 유효한 값을 한 번에 덮어씌움
    for col in yield_cols:
        col_str = df[col].astype(str).str.strip()
        valid_mask = ~col_str.str.lower().isin(['nan', 'none', ''])
        update_mask = (yield_series == "0") & valid_mask
        yield_series = np.where(update_mask, col_str, yield_series)
    
    yield_series = pd.Series(yield_series, index=df.index)
    
    # 수익률이 여전히 0인 경우, 상품명에서 정규식으로 한 번에(Batch) 추출
    if "상품명" in df.columns:
        zero_mask = (yield_series == "0")
        extracted = df.loc[zero_mask, "상품명"].astype(str).str.extract(r"(?:연\s*|)([\d\.]+)%")[0]
        yield_series.loc[zero_mask] = extracted.fillna("0")
        
    # 문자열 정제 및 float 변환
    yield_num = yield_series.astype(str).str.replace(r"[^\d\.]", "", regex=True)
    yield_num = pd.to_numeric(yield_num, errors='coerce').fillna(0.0)

    # --- 2. 청약기간 조립 (Vectorized) ---
    def get_safe_col(cols):
        if cols:
            return df[cols[0]].astype(str).str.split(' ').str[0].replace({r"(?i)nan": "", "None": "", "<NA>": ""}, regex=True)
        return pd.Series("", index=df.index)

    start_series = get_safe_col(start_cols)
    end_series = get_safe_col(end_cols)
    
    # "시작일 ~ 종료일" 조립
    combined_period = np.where((start_series != "") & (end_series != ""), start_series + " ~ " + end_series, "")
    
    if period_cols:
        p_col = df[period_cols[0]].astype(str).replace({r"(?i)nan": "", "None": "", "<NA>": ""}, regex=True)
        final_period = np.where(combined_period != "", combined_period, p_col)
    else:
        final_period = combined_period
        
    final_period = np.where(final_period == "", "-", final_period)
    period_series = pd.Series(final_period, index=df.index)

    # --- 3. 문자열 클리닝 함수 (💡 행 반복문 대신 Pandas C엔진 활용) ---
    def clean_vectorized(col_name, default_val="-"):
        if col_name not in df.columns and not isinstance(col_name, pd.Series):
            return pd.Series(default_val, index=df.index)
            
        series = col_name if isinstance(col_name, pd.Series) else df[col_name]
        
        # 강제 형변환 및 결측치 치환
        s = series.astype(str).replace({r"(?i)^nan$": default_val, "^None$": default_val, "^$": default_val}, regex=True)
        # HTML 태그 제거
        s = s.str.replace(r'<br\s*/?>', ' ', case=False, regex=True)
        # Index 단어 제거
        s = s.str.replace(r'\bIndex\b', '', case=False, regex=True)
        # 띄어쓰기 정리
        s = s.str.replace(r'\s+', ' ', regex=True).str.strip()
        
        return s.replace("nan", default_val)

    # --- 4. 결과 DataFrame 생성 (고속 매핑) ---
    result_df = pd.DataFrame({
        "상품명": clean_vectorized("상품명"),
        "기초자산": clean_vectorized("기초자산"),
        "낙인(KI)": clean_vectorized("낙인(KI)", "노낙인"),
        "수익률": yield_num,
        "수익률_텍스트": yield_num.astype(str) + "%",
        "청약기간": clean_vectorized(period_series),
        "발행회사": clean_vectorized("발행회사"),
        "만기": clean_vectorized("만기"),
        "조기상환주기": clean_vectorized("조기상환주기"),
        "조기상환배리어": clean_vectorized("조기상환배리어")
    })
    
    # 수익률 기준 정렬 및 인덱스 리셋
    if not result_df.empty:
        result_df = result_df.sort_values(by="수익률", ascending=False).reset_index(drop=True)
        
    return result_df
