import os, glob, time, platform
import re
import pandas as pd
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
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": DOWNLOAD_DIR})
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
        raise Exception("엑셀 다운로드 실패")
    finally:
        driver.quit()

def get_filtered_els():
    file_path = automate_download()
    raw_df = pd.read_excel(file_path, engine="xlrd")
    raw_df.columns = raw_df.columns.astype(str)
    
    result_list = []
    index_keywords = ["INDEX", "지수", "KOSPI", "S&P", "EURO", "HSCEI", "NIKKEI", "STOXX", "NIFTY", "CSI", "KRX", "코스피", "다우", "나스닥", "DOW", "NASDAQ", "NDX", "항셍"]

    for i, row in raw_df.iterrows():
        row_text = " ".join(str(x) for x in row.values)
        
        asset_val = ""
        for col in raw_df.columns:
            if "기초자산" in str(col):
                asset_val = str(row[col])
                break
        
        if "기초자산" in asset_val or asset_val.lower() == "nan" or asset_val.strip() == "":
            continue
            
        clean_asset = asset_val.upper().replace(chr(60) + "BR/" + chr(62), ",").replace("\n", ",").replace("/", ",")
        assets = [a.strip() for a in clean_asset.split(",") if a.strip()]
        
        is_index_only = True
        for asset in assets:
            if not any(k in asset for k in index_keywords):
                is_index_only = False
                break
                
        if not is_index_only:
            continue

        ki_val = "노낙인"
        m1 = re.search(r"(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)\s*[:\-_]?\s*(\d{2,3})", row_text, re.IGNORECASE)
        m2 = re.search(r"(\d{2,3})\s*(?:%|)\s*(?:KI|Knock[\s\-]*in|낙인|녹인|K/I)", row_text, re.IGNORECASE)
        m3 = re.search(r"-\s*\d{2,3}\s*/\s*(\d{2,3})", row_text)
        no_ki_match = re.search(r"(?:No\s*KI|노낙인|노녹인|No\s*Knock[\s\-]*in|KI\s*없음)", row_text, re.IGNORECASE)
        
        if m1: ki_val = m1.group(1)
        elif m2: ki_val = m2.group(1)
        elif m3: ki_val = m3.group(1)
        elif no_ki_match: ki_val = "노낙인"

        yield_str = "0"
        for col in raw_df.columns:
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
        for col in raw_df.columns:
            if "청약" in str(col) and "시작" in str(col):
                start_date = str(row[col]).split(' ')[0]
            elif "청약" in str(col) and "종료" in str(col):
                end_date = str(row[col]).split(' ')[0]
        sub_period = f"{start_date}~{end_date}" if start_date and end_date else "-"

        # 💡 [추가] 만기, 조기상환주기, 조기상환배리어 추출
        clean_text_for_barrier = re.sub(r"\([A-Za-z0-9]+\)", "", row_text)
        m_barrier = re.search(r"(\d{2,3}(?:[-\/,]\s*\d{2,3}){2,})", clean_text_for_barrier)
        barrier_val = m_barrier.group(1).replace("/", "-").replace(",", "-").replace(" ", "") if m_barrier else "-"

        m_maturity = re.search(r"(\d+(?:\.\d+)?)\s*(년|y)", row_text, re.IGNORECASE)
        maturity_val = m_maturity.group(1) + "년" if m_maturity else "-"

        m_cycle = re.search(r"(?:^|[^0-9\.])(\d+)\s*(개월|m)", row_text, re.IGNORECASE)
        cycle_val = m_cycle.group(1) + "개월" if m_cycle else "-"

        result_list.append({
            "상품명": str(row.get("상품명", "-")),
            "기초자산": clean_asset,
            "낙인(KI)": ki_val,
            "수익률": yield_num,
            "수익률_텍스트": f"{yield_num}%",
            "청약기간": sub_period,
            "발행회사": str(row.get("발행회사", "-")),
            "만기": maturity_val,          # 💡 추가됨
            "조기상환주기": cycle_val,      # 💡 추가됨
            "조기상환배리어": barrier_val   # 💡 추가됨
        })

    final_df = pd.DataFrame(result_list)
    if not final_df.empty:
        final_df = final_df.sort_values(by="수익률", ascending=False).reset_index(drop=True)
        
    return final_df
