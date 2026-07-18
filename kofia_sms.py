import pandas as pd
import re
# 💡 [핵심] 앱(검색기)을 구동하는 최신 분석 엔진을 그대로 끌어와서 사용합니다!
from kofia_els import automate_download, parse_kofia_file

def get_filtered_els():
    # 앱과 100% 동일한 로직으로 데이터를 다운받고 분석합니다.
    file_path = automate_download()
    df = parse_kofia_file(file_path)
    
    # 앱과 완벽하게 동일한 기준으로 '지수형'만 필터링합니다.
    if "유형" in df.columns:
        df = df[df["유형"] == "지수형"]
        
    result_list = []
    for i, row in df.iterrows():
        # 수익률 파싱
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
        
        # 청약기간 파싱
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
        
        # 문자 발송(main.py)을 위한 포맷팅
        result_list.append({
            "상품명": str(row.get("상품명", "-")),
            "기초자산": str(row.get("기초자산", "-")),
            "낙인(KI)": str(row.get("낙인(KI)", "노낙인")),
            "수익률": yield_num,
            "수익률_텍스트": f"{yield_num}%",
            "청약기간": sub_period,
            "발행회사": str(row.get("발행회사", "-")),
            "만기": str(row.get("만기", "-")),
            "조기상환주기": str(row.get("조기상환주기", "-")),
            "조기상환배리어": str(row.get("조기상환배리어", "-"))
        })
        
    final_df = pd.DataFrame(result_list)
    if not final_df.empty:
        final_df = final_df.sort_values(by="수익률", ascending=False).reset_index(drop=True)
        
    return final_df
