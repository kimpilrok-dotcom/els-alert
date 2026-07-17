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
    import os, glob, time, platform
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # 💡 [핵심 수정 1] 클라우드(리눅스) 서버는 보안상 /tmp 폴더에만 파일 저장이 가능합니다.
    if platform.system() == "Linux":
        DOWNLOAD_DIR = "/tmp/els_downloads"
    else:
        DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
        
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0
    }
    options.add_experimental_option("prefs", prefs)
    
    if platform.system() == "Linux":
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())
        
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        # 💡 [핵심 수정 2] 최신 헤드리스 크롬에서도 무조건 다운로드를 허용하도록 권한 명령어를 2중으로 걸어줍니다.
        try:
            driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": DOWNLOAD_DIR,
                "eventsEnabled": True
            })
        except:
            pass
            
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": DOWNLOAD_DIR
        })
        
        existing_files = set(glob.glob(os.path.join(DOWNLOAD_DIR, "*.*")))
        
        driver.get("https://dis.kofia.or.kr/websquare/index.jsp?w2xPath=/wq/etcann/DISDLSSubscribing.xml&divisionId=MDIS04007001000000&serviceId=SDIS04007001000")
        wait = WebDriverWait(driver, 30)
        
        wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@id, 'body_table')]")))
        time.sleep(10)
        
        target_xpath = "/html/body/div[1]/div[2]/div/div[2]/div[3]/div/div[1]/div[2]/a[1]"
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, target_xpath)))
        
        driver.execute_script("arguments[0].click();", btn)
        
        for i in range(60):
            time.sleep(2)
            
            if i == 15:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                except:
                    pass
            
            current_files = set(glob.glob(os.path.join(DOWNLOAD_DIR, "*.*")))
            new_files = current_files - existing_files
            
            valid_new_files = [f for f in new_files if not f.endswith('.tmp') and not f.endswith('.crdownload')]
            
            if valid_new_files:
                excel_files = [f for f in valid_new_files if f.endswith('.xls') or f.endswith('.xlsx')]
                if excel_files:
                    time.sleep(2) 
                    return excel_files[0]
        
        raise Exception("다운로드된 새 엑셀 파일을 찾을 수 없습니다. (대기 시간 초과)")
        
    finally:
        driver.quit()

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
