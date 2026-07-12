import streamlit as st
import pandas as pd
import io
import time
import os
import glob
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ==========================================
# ⬇️ 클라우드(GitHub) 호환을 위한 다운로드 함수 수정 ⬇️
# ==========================================

def automate_download():
    # 💡 클라우드(리눅스) 환경에서도 오류가 안 나도록, 현재 실행 폴더 안에 다운로드 폴더를 만듭니다.
    DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    options = Options()
    
    # 💡 [핵심] 클라우드의 '모니터 없는 환경'에서 실행하기 위한 투명 망토 옵션들!
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True
    }
    options.add_experimental_option("prefs", prefs)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        existing_files = set(glob.glob(os.path.join(DOWNLOAD_DIR, "*.*")))
        
        driver.get("https://dis.kofia.or.kr/websquare/index.jsp?w2xPath=/wq/etcann/DISDLSSubscribing.xml&divisionId=MDIS04007001000000&serviceId=SDIS04007001000")
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@id, 'body_table')]")))
        
        target_xpath = "/html/body/div[1]/div[2]/div/div[2]/div[3]/div/div[1]/div[2]/a[1]/img"
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, target_xpath)))
        
        time.sleep(1)
        driver.execute_script("arguments[0].click();", btn)
        
        # 버튼 클릭 후 새 파일이 떨어질 때까지 대기
        for _ in range(40):
            time.sleep(0.5)
            current_files = set(glob.glob(os.path.join(DOWNLOAD_DIR, "*.*")))
            new_files = current_files - existing_files
            
            valid_new_files = [f for f in new_files if not f.endswith('.tmp') and not f.endswith('.crdownload')]
            
            if valid_new_files:
                excel_files = [f for f in valid_new_files if f.endswith('.xls') or f.endswith('.xlsx')]
                if excel_files:
                    time.sleep(1)
                    return excel_files[0]
        
        raise Exception("다운로드된 새 엑셀 파일을 찾을 수 없습니다.")
        
    finally:
        driver.quit()

import re
import pandas as pd

# ==========================================
# ⬇️ 해독기 함수만 이걸로 덮어쓰기 하세요 ⬇️
# ==========================================

def parse_kofia_file(file_path):
    # 1. 원본 엑셀 읽어오기
    raw_df = pd.read_excel(file_path, engine='xlrd')
    raw_df.columns = raw_df.columns.astype(str)
    
    # 💡 [핵심] '기초자산' 데이터가 도대체 몇 번째 칸에 있는지 로봇이 스스로 찾아냅니다.
    asset_col_idx = None
    for j in range(len(raw_df.columns)):
        if '기초자산' in str(raw_df.columns[j]):
            asset_col_idx = j
            break
    if asset_col_idx is None:
        for i in range(min(15, len(raw_df))):
            for j in range(len(raw_df.columns)):
                if '기초자산' in str(raw_df.iloc[i, j]):
                    asset_col_idx = j
                    break
            if asset_col_idx is not None:
                break

    ki_list = []
    type_list = []
    
    # 지수(Index)를 판별하는 핵심 키워드 사전
    index_keywords = ['INDEX', '지수', 'KOSPI', 'S&P', 'EURO', 'HSCEI', 'NIKKEI', 'STOXX', 'NIFTY', 'CSI', 'KRX', '코스피', '다우', '나스닥', 'DOW', 'NASDAQ', 'NDX', '항셍']
    
    # 2. 줄마다 스캔하며 데이터 추출
    for i, row in raw_df.iterrows():
        row_text = " ".join(str(x) for x in row.values)
        
        # --- 1) 낙인(KI) 추출 ---
        m1 = re.search(r'(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)\s*[:\-_]?\s*(\d{2,3})', row_text, re.IGNORECASE)
        m2 = re.search(r'(\d{2,3})\s*(?:%|)\s*(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)', row_text, re.IGNORECASE)
        m3 = re.search(r'-\s*\d{2,3}\s*/\s*(\d{2,3})', row_text)
        m4 = re.search(r'(\d{2,3})%-\(', row_text)
        m5 = re.search(r'월지급\s*(?:배리어|베리어)?\s*(\d{2,3})', row_text)
        no_ki_match = re.search(r'(?:No\s*KI|노낙인|노녹인|No\s*Knock[\s\-]*in|KI\s*없음|낙인\s*없음|녹인\s*없음|K/I\s*없음)', row_text, re.IGNORECASE)
        
        if m1: ki_list.append(m1.group(1))
        elif m2: ki_list.append(m2.group(1))
        elif m3: ki_list.append(m3.group(1))
        elif m4: ki_list.append(m4.group(1))
        elif m5: ki_list.append(m5.group(1))
        elif no_ki_match: ki_list.append("노낙인")
        else: ki_list.append("-")
        
        # --- 2) 기초자산 유형 분류 ---
        if asset_col_idx is not None:
            asset_val = str(row.iloc[asset_col_idx])
            # 머리글(헤더) 줄이거나 빈칸이면 건너뜀
            if '기초자산' in asset_val or asset_val.strip() == 'nan' or asset_val.strip() == '':
                type_list.append("-")
            else:
                # 기호들을 쉼표로 통일하여 각각의 자산으로 분리 (예: 삼성전자, KOSPI200)
                clean_asset = asset_val.upper().replace('<BR/>', ',').replace('\n', ',').replace('/', ',')
                assets = [a.strip() for a in clean_asset.split(',') if a.strip()]
                
                has_index = False
                has_stock = False
                
                for asset in assets:
                    # 지수 키워드가 포함되어 있으면 지수, 없으면 종목(주식)으로 간주
                    if any(k in asset for k in index_keywords):
                        has_index = True
                    else:
                        has_stock = True
                        
                # 판독 결과 저장
                if has_index and has_stock:
                    type_list.append("혼합형")
                elif has_index:
                    type_list.append("지수형")
                elif has_stock:
                    type_list.append("종목형")
                else:
                    type_list.append("-")
        else:
            type_list.append("-")
            
    # 3. 맨 앞에 열 2개 추가 (순서대로 꽂기 위해 유형을 먼저, 그다음 낙인을 맨 앞에 넣습니다)
    raw_df.insert(0, '유형', type_list)
    raw_df.insert(0, '낙인(KI)', ki_list)
    
    return raw_df

# UI 출력 부분
if __name__ == "__main__":
    st.set_page_config(page_title="KOFIA ELS/DLS 통합 허브", layout="wide")
    st.title("🏆 금융투자협회 ELS/DLS 통합 조회 허브")

    if st.button("🚀 자동 수집 및 분석 시작", width="stretch"):
        with st.spinner("로봇이 금투협에서 최신 데이터를 가져오는 중입니다... (약 10초 소요)"):
            try:
                path = automate_download()
                df = parse_kofia_file(path)
                st.session_state['data'] = df
                st.success(f"✅ 성공! 금투협에서 {len(df)}개의 최신 상품을 가져왔습니다.")
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

    if 'data' in st.session_state:
        st.divider()
        st.dataframe(st.session_state['data'], use_container_width=True)

# ==========================================
# ⬇️ 수정된 필터링 함수 (기존 함수 덮어쓰기) ⬇️
# ==========================================

def get_filtered_els():
    """
    앞으로 만들 '자동 문자 발송 로봇(main.py)'이 호출해서 쓸 함수입니다.
    조건: 1) 지수형  2) 낙인 25 이하 (노낙인/낙인없음 제외)
    """
    # 1. 다운로드 및 파싱
    file_path = automate_download()
    df = parse_kofia_file(file_path)
    
    if df.empty:
        return df

    # 2. 깐깐해진 낙인 판독 미니 함수
    def check_ki_condition(ki_value):
        ki_str = str(ki_value).strip()
        
        # 💡 [변경됨] "노낙인" 이거나 정보가 없는 상품(-)은 무조건 탈락! (False)
        if "노낙인" in ki_str or ki_str == "-" or ki_str == "":
            return False
            
        # 숫자가 포함되어 있다면 추출해서 25 이하인지 확인
        import re
        numbers = re.findall(r'\d+', ki_str)
        if numbers:
            # 💡 [변경됨] 기준이 40 이하에서 25 이하로 대폭 강화되었습니다!
            if int(numbers[0]) <= 25:
                return True
                
        return False

    # 3. 조건 체에 거르기 (지수형 & 낙인조건 충족)
    mask_type = df['유형'] == '지수형'
    mask_ki = df['낙인(KI)'].apply(check_ki_condition)
    
    filtered_df = df[mask_type & mask_ki].copy()
    
    # 향후 문자 발송 시 중복 방지를 위해 '상품명'을 고유 ID인 '상품번호'로 복사해 둡니다.
    filtered_df['상품번호'] = filtered_df['상품명']
    
    return filtered_df