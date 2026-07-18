import os
import sys
import json
import logging
from pathlib import Path
import pandas as pd
from solapi import SolapiMessageService
from solapi.model import RequestMessage

# 💡 알림용으로 특화된 파일을 불러옵니다!
from kofia_sms import get_filtered_els

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "sent_ids.json"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "els_alert.log"

MAX_MESSAGE_LENGTH = 1500

def configure_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

def load_sent_ids():
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()

def format_product(row, number):
    # 💡 kofia_sms.py에서 깨끗하게 다듬어준 데이터를 바로 가져다 씁니다.
    issuer = row.get("발행회사", "-")
    name = row.get("상품명", "-")
    underlying = row.get("기초자산", "-")
    knock_in = row.get("낙인(KI)", "-")
    coupon = row.get("수익률_텍스트", "-")
    
    # 💡 요청하신 3가지 항목 추가!
    maturity = row.get("만기", "-")
    cycle = row.get("조기상환주기", "-")
    barrier = row.get("조기상환배리어", "-")

    # 보기 좋게 문자로 조립합니다.
    return (
        f"{number}. {issuer} {name}\n"
        f"기초: {underlying}\n"
        f"낙인: {knock_in} / 수익률: {coupon}\n"
        f"만기: {maturity} / 주기: {cycle}\n"
        f"배리어: {barrier}"
    )

def send_sms(text):
    api_key = os.getenv("SOLAPI_API_KEY")
    api_secret = os.getenv("SOLAPI_API_SECRET")
    from_num = os.getenv("SOLAPI_FROM_NUMBER")
    to_numbers_str = os.getenv("ELS_ALERT_TO_NUMBER")

    if not all([api_key, api_secret, from_num, to_numbers_str]):
        logging.error("환경변수가 없어 문자를 보낼 수 없습니다.")
        return

    service = SolapiMessageService(api_key=api_key, api_secret=api_secret)
    to_numbers = [num.strip() for num in to_numbers_str.split(",")]

    for to_num in to_numbers:
        if not to_num: 
            continue
            
        try:
            message = RequestMessage(from_=from_num, to=to_num, text=text)
            service.send(message)
            logging.info(f"🎉 {to_num} 번호로 문자 발송 완료!")
        except Exception as e:
            logging.error(f"❌ {to_num} 번호 발송 실패: {e}")

def run():
    import re
    
    logging.info("ELS 리포트 발송 준비 시작")
    
    # 1. kofia_sms.py에서 지수형 필터링 & 수익률 정렬이 완료된 데이터 가져오기
    products = get_filtered_els()
    if products.empty:
        logging.info("조건에 맞는 상품이 없습니다.")
        return

    products["_product_id"] = products["상품명"].astype(str).str.strip()
    sent_ids = load_sent_ids()

    def get_numeric_ki(row):
        try:
            val_str = str(row.get("낙인(KI)", "0")).strip()
            if "노낙인" in val_str or "없음" in val_str or val_str == "-" or val_str == "":
                return 0.0
            numbers = re.findall(r"[-+]?\d*\.?\d+", val_str)
            return float(numbers[0]) if numbers else 0.0
        except:
            return 0.0

    # kofia_sms.py에서 수익률을 이미 숫자로 주므로 복잡한 추출 코드가 필요 없습니다.
    products["_sort_yield"] = products["수익률"]
    products["_sort_ki"] = products.apply(get_numeric_ki, axis=1)

    # 노낙인 제외 (정상적인 데이터만 추려냄)
    valid_products = products[products["_sort_ki"] > 0]
    
    if valid_products.empty:
        logging.info("유효한 낙인(KI) 데이터가 없습니다.")
        return

    # 3. 최저 낙인 / 차최저 낙인 찾기
    ki_levels = sorted(valid_products["_sort_ki"].unique())
    lowest_ki = ki_levels[0]
    second_lowest_ki = ki_levels[1] if len(ki_levels) > 1 else None

    group1 = valid_products[valid_products["_sort_ki"] == lowest_ki].sort_values(by="_sort_yield", ascending=False).head(5)
    
    if second_lowest_ki is not None:
        group2 = valid_products[valid_products["_sort_ki"] == second_lowest_ki].sort_values(by="_sort_yield", ascending=False).head(5)
    else:
        group2 = pd.DataFrame()

    # 4. 문자 메시지 조립하기
    message_lines = ["[오늘의 알짜 ELS 리포트]\n"]
    newly_sent_product_ids = []
    
    def append_to_message(group, ki_val):
        message_lines.append(f"■ 낙인 {ki_val} (상위수익률 TOP 5)")
        
        for idx, (_, row) in enumerate(group.iterrows(), 1):
            pid = row["_product_id"]
            newly_sent_product_ids.append(pid)
            
            formatted_product = format_product(row, idx)
            
            # 청약기간 포맷팅 (YYYYMMDD~YYYYMMDD 형태를 00.00 ~ 00.00으로 이쁘게 변경)
            period_str = str(row.get("청약기간", "-"))
            if "~" in period_str:
                s_date, e_date = period_str.split("~")
                def format_d(d):
                    d = d.strip()
                    return f"{d[4:6]}.{d[6:8]}" if len(d) >= 8 else d
                period_str = f"청약: {format_d(s_date)} ~ {format_d(e_date)}"
            else:
                period_str = f"청약: {period_str}"
            
            formatted_product = f"{formatted_product}\n{period_str}"
            
            # USD(달러) 상품인지 확인하기
            is_usd = False
            search_text = str(row.get("상품명", "")) + str(row.get("비고", "")) + str(row.get("상품유형", ""))
            if "USD" in search_text.upper() or "달러" in search_text:
                is_usd = True
                
            usd_tag = "💵[USD] " if is_usd else ""
            
            # 신규 / 기존 태그 부착
            if pid not in sent_ids:
                message_lines.append(f"✨[신규] {usd_tag}{formatted_product}\n")
            else:
                message_lines.append(f"  [기존] {usd_tag}{formatted_product}\n")
        
        message_lines.append("") # 그룹 간 띄어쓰기

    if not group1.empty:
        append_to_message(group1, lowest_ki)
    if not group2.empty:
        append_to_message(group2, second_lowest_ki)

    final_text = "\n".join(message_lines)
    
    # 5. 발송 및 장부 업데이트
    send_sms(final_text[:MAX_MESSAGE_LENGTH])

    sent_ids.update(newly_sent_product_ids)
    
    with open('sent_ids.json', 'w', encoding='utf-8') as f:
        json.dump(list(sent_ids), f, ensure_ascii=False, indent=2)
        
    logging.info(f"🎉 리포트 발송 완료! (보고된 상품 수: {len(newly_sent_product_ids)}건, 누적 장부: {len(sent_ids)}건)")

if __name__ == "__main__":
    configure_logging()
    run()
