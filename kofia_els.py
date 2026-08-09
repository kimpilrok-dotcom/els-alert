import os, glob, time, platform
import re
import pandas as pd
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def automate_download():
    DOWNLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "downloads"))
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
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
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": DOWNLOAD_DIR
        })
        
        driver.get("https://dis.kofia.or.kr/websquare/index.jsp?w2xPath=/wq/etcann/DISDLSSubscribing.xml&divisionId=MDIS04007001000000&serviceId=SDIS04007001000")
        wait = WebDriverWait(driver, 30)
        
        wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@id, 'body_table')]")))
        time.sleep(10)
        
        target_xpath = "/html/body/div[1]/div[2]/div/div[2]/div[3]/div/div[1]/div[2]/a[1]"
        btn = wait.until(EC.presence_of_element_located((By.XPATH, target_xpath)))
        
        driver.execute_script("arguments[0].click();", btn)
        
        for i in range(60):
            time.sleep(2)
            if i % 5 == 0:
                try: driver.execute_script("arguments[0].click();", btn)
                except: pass
            files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.*"))
            excel_files = [f for f in files if f.endswith(".xls") or f.endswith(".xlsx")]
            if excel_files:
                time.sleep(2)
                return excel_files[0]
        folder_contents = os.listdir(DOWNLOAD_DIR)
        raise Exception(f"엑셀 다운로드 실패. 폴더 내부 상태: {folder_contents}")
    finally:
        driver.quit()

def parse_kofia_file(file_path):
    raw_df = pd.read_excel(file_path, engine="xlrd")
    raw_df.columns = raw_df.columns.astype(str)
    
    # 1. 기초자산 컬럼 인덱스 찾기
    asset_col_idx = None
    prod_col_idx = None
    for j in range(len(raw_df.columns)):
        if "기초자산" in str(raw_df.columns[j]): asset_col_idx = j
        if "상품명" in str(raw_df.columns[j]): prod_col_idx = j

    if asset_col_idx is None:
        for i in range(min(15, len(raw_df))):
            for j in range(len(raw_df.columns)):
                if "기초자산" in str(raw_df.iloc[i, j]):
                    asset_col_idx = j
                    break
            if asset_col_idx is not None: break

    row_text_series = raw_df.apply(lambda row: ' '.join(str(x) for x in row.values), axis=1)

    # 2. 통화(Currency) 추출
    currency_series = np.where(row_text_series.str.contains(r"USD|달러", case=False, regex=True), "USD", "KRW")

    # 3. 낙인(KI) 추출
    m1_ext = row_text_series.str.extract(r"(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)\s*[:\-_]?\s*(\d{2,3})", flags=re.IGNORECASE)[0]
    m2_ext = row_text_series.str.extract(r"(\d{2,3})\s*(?:%|)\s*(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)", flags=re.IGNORECASE)[0]
    m3_ext = row_text_series.str.extract(r"-\s*\d{2,3}\s*/\s*(\d{2,3})")[0]
    m4_ext = row_text_series.str.extract(r"(\d{2,3})%-\(")[0]
    m5_ext = row_text_series.str.extract(r"월지급\s*(?:배리어|베리어)?\s*(\d{2,3})")[0]
    no_ki_mask = row_text_series.str.contains(r"(?:No\s*KI|노낙인|노녹인|No\s*Knock[\s\-]*in|KI\s*없음|낙인\s*없음|녹인\s*없음|K/I\s*없음)", case=False, regex=True)
    
    ki_series = m1_ext.combine_first(m2_ext).combine_first(m3_ext).combine_first(m4_ext).combine_first(m5_ext)
    ki_series = np.where(ki_series.notna(), ki_series, np.where(no_ki_mask, "노낙인", "-"))

    # 4. 배리어(Barrier) 추출
    clean_text_series = row_text_series.str.replace(r"\([A-Za-z0-9]+\)", "", regex=True)
    barrier_ext = clean_text_series.str.extract(r"(\d{2,3}(?:[-\/,]\s*\d{2,3}){2,})")[0]
    barrier_series = barrier_ext.str.replace(r"[/,]", "-", regex=True).str.replace(" ", "", regex=False).fillna("-")

    # 5. 만기(Maturity) 추출
    maturity_ext = row_text_series.str.extract(r"(\d+(?:\.\d+)?)\s*(?:년|y)", flags=re.IGNORECASE)[0]
    maturity_series = np.where(maturity_ext.notna(), maturity_ext + "년", "-")

    # 6. 주기(Cycle) 추출
    cycle_ext = row_text_series.str.extract(r"(?:^|[^0-9\.])(\d{1,3})\s*(?:개월|m)", flags=re.IGNORECASE)[0]
    cycle_series = np.where(cycle_ext.notna(), cycle_ext + "개월", "-")

    # 7. 기초자산 유형(Type) 분류
    index_keywords = ["INDEX", "지수", "KOSPI", "S&P", "EURO", "HSCEI", "NIKKEI", "STOXX", "NIFTY", "CSI", "KRX", "코스피", "다우", "DOW", "NDX", "항셍", "NASDAQ100", "나스닥100", "NASDAQ 100", "나스닥 100"]
    
    def classify_asset(asset_val):
        asset_str = str(asset_val)
        if "기초자산" in asset_str or asset_str.strip() in ("nan", ""):
            return "-"
        
        tag_br = chr(60) + "BR/" + chr(62)
        clean_asset = asset_str.upper().replace(tag_br, ",").replace("\n", ",").replace("/", ",")
        assets = [a.strip() for a in clean_asset.split(",") if a.strip()]
        
        has_index = False
        has_stock = False
        
        for asset in assets:
            if re.search(r'\((NASDAQ|NYSE|나스닥|뉴욕|NY|AMEX)[^)]*\)', asset):
                has_stock = True
            elif any(k in asset for k in index_keywords):
                has_index = True
            else:
                has_stock = True
                
        if has_index and has_stock: return "혼합형"
        elif has_index: return "지수형"
        elif has_stock: return "종목형"
        return "-"

    if asset_col_idx is not None:
        type_series = raw_df.iloc[:, asset_col_idx].map(classify_asset)
    else:
        type_series = pd.Series("-", index=raw_df.index)

    # 8. 최종 결과 삽입
    raw_df.insert(0, "통화", currency_series)
    raw_df.insert(0, "조기상환주기", cycle_series)
    raw_df.insert(0, "만기", maturity_series)
    raw_df.insert(0, "조기상환배리어", barrier_series)
    raw_df.insert(0, "유형", type_series)
    raw_df.insert(0, "낙인(KI)", ki_series)
    
    return raw_df
