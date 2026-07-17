import streamlit as st
import pandas as pd
import io
import time
import os
import glob
import re
import pandas as pd

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

    # 💡 [해결책] /tmp 가상 폴더 대신, 스트림릿 앱이 실행 중인 진짜 폴더의 절대경로를 씁니다.
    DOWNLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "downloads"))
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # 💡 [충돌 방지] 기존에 다운로드 폴더에 남아있던 찌꺼기 파일들 싹 청소하기
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.*")):
        try: os.remove(f)
        except: pass

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
        # 💡 [강제 권한] 컨테이너 환경에서 지정된 절대경로로 다운로드를 뚫어버립니다.
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": DOWNLOAD_DIR
        })
        
        driver.get("https://dis.kofia.or.kr/websquare/index.jsp?w2xPath=/wq/etcann/DISDLSSubscribing.xml&divisionId=MDIS04007001000000&serviceId=SDIS04007001000")
        wait = WebDriverWait(driver, 30)
        
        # 표의 뼈대가 나타날 때까지 대기
        wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@id, 'body_table')]")))
        time.sleep(10)
        
        # 엑셀 버튼 찾기
        target_xpath = "/html/body/div[1]/div[2]/div/div[2]/div[3]/div/div[1]/div[2]/a[1]"
        btn = wait.until(EC.presence_of_element_located((By.XPATH, target_xpath)))
        
        # 최초 1회 클릭
        driver.execute_script("arguments[0].click();", btn)
        
        for i in range(60):
            time.sleep(2)
            
            # 💡 [안전장치] 클릭이 무시되었을 경우를 대비해 10초마다 끈질기게 엑셀 버튼을 다시 찌릅니다.
            if i % 5 == 0:
                try: driver.execute_script("arguments[0].click();", btn)
                except: pass
            
            files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.*"))
            
            # 엑셀 파일이 정상적으로 생겼다면 즉시 성공 반환!
            excel_files = [f for f in files if f.endswith('.xls') or f.endswith('.xlsx')]
            if excel_files:
                time.sleep(2)
                return excel_files[0]
                
        # 실패할 경우 폴더 안에 임시 파일이라도 생겼는지 추적합니다.
        folder_contents = os.listdir(DOWNLOAD_DIR)
        raise Exception(f"엑셀 다운로드 실패. 폴더 내부 상태: {folder_contents}")
        
    finally:
        driver.quit()

# ==========================================
# ⬇️ 해독기 함수만 이걸로 덮어쓰기 하세요 ⬇️
# ==========================================

import re
import pandas as pd

def parse_kofia_file(file_path):
    raw_df = pd.read_excel(file_path, engine='xlrd')
    raw_df.columns = raw_df.columns.astype(str)
    
    asset_col_idx = None
    prod_col_idx = None
    for j in range(len(raw_df.columns)):
        if '기초자산' in str(raw_df.columns[j]):
            asset_col_idx = j
        if '상품명' in str(raw_df.columns[j]):
            prod_col_idx = j

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
    barrier_list = []  
    cycle_list = []    
    maturity_list = [] 
    
    index_keywords = ['INDEX', '지수', 'KOSPI', 'S&P', 'EURO', 'HSCEI', 'NIKKEI', 'STOXX', 'NIFTY', 'CSI', 'KRX', '코스피', '다우', '나스닥', 'DOW', 'NASDAQ', 'NDX', '항셍']
    
    for i, row in raw_df.iterrows():
        row_text = " ".join(str(x) for x in row.values)
        
        # --- 1) 낙인(KI) ---
        if row_text is None:
            m1 = None
        else:
            m1 = re.search(r'(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)\s*[:\-_]?\s*(\d{2,3})', str(row_text), re.IGNORECASE)
        m2 = re.search(r'(\d{2,3})\s*(?:%|)\s*(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)', str(row_text), re.IGNORECASE)
        m3 = re.search(r'-\s*\d{2,3}\s*/\s*(\d{2,3})', str(row_text))
        m4 = re.search(r'(\d{2,3})%-\(', str(row_text))
        m5 = re.search(r'월지급\s*(?:배리어|베리어)?\s*(\d{2,3})', str(row_text))
        no_ki_match = re.search(r'(?:No\s*KI|노낙인|노녹인|No\s*Knock[\s\-]*in|KI\s*없음|낙인\s*없음|녹인\s*없음|K/I\s*없음)', str(row_text), re.IGNORECASE)
        
        if m1: ki_list.append(m1.group(1))
        elif m2: ki_list.append(m2.group(1))
        elif m3: ki_list.append(m3.group(1))
        elif m4: ki_list.append(m4.group(1))
        elif m5: ki_list.append(m5.group(1))
        elif no_ki_match: ki_list.append("노낙인")
        else: ki_list.append("-")
        
        # --- 2) 기초자산 유형 ---
        if asset_col_idx is not None:
            asset_val = str(row.iloc[asset_col_idx])
            if '기초자산' in asset_val or asset_val.strip() == 'nan' or asset_val.strip() == '':
                type_list.append("-")
            else:
                clean_asset = asset_val.upper().replace('
', ',').replace('\n', ',').replace('/', ',')
                assets = [a.strip() for a in clean_asset.split(',') if a.strip()]
                has_index = False
                has_stock = False
                for asset in assets:
                    if any(k in asset for k in index_keywords):
                        has_index = True
                    else:
                        has_stock = True
                if has_index and has_stock: type_list.append("혼합형")
                elif has_index: type_list.append("지수형")
                elif has_stock: type_list.append("종목형")
                else: type_list.append("-")
        else:
            type_list.append("-")
            
        # --- 💡 3) 배리어, 만기, 주기 추출 (정밀 타격) ---
        
        # 배리어 찾기: 괄호(예: L50) 무시하고 연결
        clean_text = re.sub(r'\([A-Za-z0-9]+\)', '', str(row_text))
        m_barrier = re.search(r'(\d{2,3}(?:[-\/]\d{2,3}){2,})', clean_text)
        if m_barrier: 
            barrier_list.append(m_barrier.group(1).replace('/', '-'))
        else: 
            barrier_list.append("-")
            
        # 만기 찾기: 년, y 모두 감지
        m_maturity = re.search(r'(\d+(?:\.\d+)?)\s*(년|y)', str(row_text), re.IGNORECASE)
        if m_maturity: 
            maturity_list.append(m_maturity.group(1) + "년")
        else: 
            maturity_list.append("-")

        # 주기 찾기: 개월, m 모두 감지
        m_cycle = re.search(r'(?

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
