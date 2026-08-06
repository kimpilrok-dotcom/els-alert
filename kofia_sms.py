import pandas as pd
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
        df = df[df["유형"] == "지수형"]
        
    # 💡 HTML 태그(<br> 등) 제거 및 'Index' 글자 제거를 함께 수행하는 함수
    def clean_html(val):
        if val is None or pd.isna(val):
            return "-"
        # 1. HTML 태그 제거
        cleaned = re.sub(r'<br\s*/?>', ' ', str(val), flags=re.IGNORECASE)
        # 2. 'Index' 단어 제거 (대소문자 무시)
        cleaned = re.sub(r'\bIndex\b', '', cleaned, flags=re.IGNORECASE)
        # 3. 불필요한 여백 정리
        return re.sub(r'\s+', ' ', cleaned).strip()
        
    result_list = []
    for i, row in df.iterrows():
        yield_str = "0"
        for col in row.index:
            if "수익" in str(col):
                v = str(row[col])
                if v.lower() != "nan" and v != "":
                    yield_str = v
                    break
        if yield_str == "0":
            m = re.search(r"(?:연\s*|)([\d\.]+)%", str(row.get("상품명", "")))
            if m: yield_str = m.group(1)
        
        try: yield_num = float(re.sub(r"[^\d\.]", "", yield_str))
        except: yield_num = 0.0
        
        start_date, end_date = "", ""
        for col in row.index:
            if "청약" in str(col) and "시작" in str(col):
                v = str(row[col]).split(' ')[0]
                if v.lower() != "nan": start_date = v
            elif "청약" in str(col) and "종료" in str(col):
                v = str(row[col]).split(' ')[0]
                if v.lower() != "nan": end_date = v
        
        if start_date and end_date:
            sub_period = f"{start_date} ~ {end_date}"
        else:
            sub_period = "-"
            for col in row.index:
                if "청약" in str(col) and "기간" in str(col):
                    v = str(row[col])
                    if v.lower() != "nan" and v != "": sub_period = v
                    break
        
        result_list.append({
            "상품명": clean_html(row.get("상품명", "-")),
            "기초자산": clean_html(row.get("기초자산", "-")),
            "낙인(KI)": clean_html(row.get("낙인(KI)", "노낙인")),
            "수익률": yield_num,
            "수익률_텍스트": f"{yield_num}%",
            "청약기간": clean_html(sub_period),
            "발행회사": clean_html(row.get("발행회사", "-")),
            "만기": clean_html(row.get("만기", "-")),
            "조기상환주기": clean_html(row.get("조기상환주기", "-")),
            "조기상환배리어": clean_html(row.get("조기상환배리어", "-"))
        })
        
    final_df = pd.DataFrame(result_list)
    if not final_df.empty:
        final_df = final_df.sort_values(by="수익률", ascending=False).reset_index(drop=True)
        
    return final_df
