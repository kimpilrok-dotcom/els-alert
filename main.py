import os
import sys
import json
import logging
from pathlib import Path
import pandas as pd
from solapi import SolapiMessageService
from solapi.model import RequestMessage

# 💡 1단계에서 만든 파일을 불러옵니다! (파일 이름이 다르면 kofia_els 부분을 수정하세요)
from kofia_els import get_filtered_els

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "sent_ids.json"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "els_alert.log"

MAX_MESSAGE_LENGTH = 1500

# 우리가 만든 해독기 표의 열 이름에 완벽하게 맞춘 기둥(Column) 후보군
COLUMN_CANDIDATES = {
    "id": ["상품번호", "상품명"], 
    "issuer": ["발행사", "회사명", "발행회사", "발행인"],
    "name": ["상품명", "종목명"],
    "underlying": ["기초자산", "기초자산명"],
    "knock_in": ["낙인(KI)", "낙인"],
    "coupon": ["수익률", "쿠폰", "제시"] # '수익률' 글자가 들어가면 무조건 잡도록 단순화!
}

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

def get_row_value(row, logical_name, default="-"):
    candidates = COLUMN_CANDIDATES.get(logical_name, [])
    
    # 표의 열 이름들을 하나씩 확인합니다.
    for col_name in row.index:
        # 엑셀 특유의 줄바꿈(\n)이나 띄어쓰기를 무시하도록 깔끔하게 정리
        clean_col = str(col_name).replace("\n", "").replace(" ", "")
        
        for candidate in candidates:
            # 열 이름에 '수익률' 같은 단어가 포함되어 있다면!
            if candidate in clean_col: 
                text = str(row[col_name]).strip()
                if text and text != "nan":
                    # 만약 엑셀 데이터 자체에 %가 붙어있다면 떼어냅니다 (메시지에서 %를 붙여주므로)
                    return text.replace("%", "")
                    
    return default

def load_sent_ids():
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()

def save_sent_ids(sent_ids):
    STATE_FILE.write_text(json.dumps(list(sent_ids), ensure_ascii=False, indent=2), encoding="utf-8")

def format_product(row, number):
    issuer = get_row_value(row, "issuer")
    name = get_row_value(row, "name")
    underlying = get_row_value(row, "underlying")
    knock_in = get_row_value(row, "knock_in")
    coupon = get_row_value(row, "coupon")

    return (
        f"{number}. {issuer} {name}\n"
        f"기초: {underlying}\n"
        f"낙인: {knock_in} / 수익률: {coupon}%\n"
        f"----------------------"
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

    # 💡 쉼표(,)를 기준으로 여러 개의 전화번호를 쪼개서 명단(리스트)으로 만듭니다.
    to_numbers = [num.strip() for num in to_numbers_str.split(",")]

    # 명단에 있는 번호들을 하나씩 꺼내면서 문자를 모두 발송합니다.
    for to_num in to_numbers:
        if not to_num: # 빈칸이면 패스
            continue
            
        try:
            message = RequestMessage(from_=from_num, to=to_num, text=text)
            service.send(message)
            logging.info(f"🎉 {to_num} 번호로 문자 발송 완료!")
        except Exception as e:
            logging.error(f"❌ {to_num} 번호 발송 실패: {e}")

def run():
    logging.info("ELS 신규 상품 확인 시작")
    
    # 우리가 만든 해독기로 알짜배기 상품만 가져오기
    products = get_filtered_els()

    if products.empty:
        logging.info("조건(지수형 & 낙인25이하)에 맞는 신규 상품이 없습니다.")
        return

    # 식별번호(상품명) 문자열로 확실히 정리
    products["_product_id"] = products["상품명"].astype(str).str.strip()
    
    sent_ids = load_sent_ids()

    # 아직 발송된 적 없는 새로운 상품만 걸러내기
    new_products = products[~products["_product_id"].isin(sent_ids)].copy()

    if new_products.empty:
        logging.info("이미 모두 알림을 받은 상품입니다. (신규 없음)")
        return

    logging.info(f"신규 조건충족 상품: {len(new_products)}건 발견!")

    # 💡 [핵심 추가] 문자 발송 전, 수익률 기준으로 내림차순(높은 순) 정렬하기
    def get_numeric_yield(row):
        val_str = get_row_value(row, "coupon", default="0")
        try:
            # 6.5% 나 세전6.5 처럼 문자가 섞여 있어도 순수 숫자(소수점 포함)만 추출합니다.
            import re
            numbers = re.findall(r"[-+]?\d*\.?\d+", val_str)
            if numbers:
                return float(numbers[0])
            return 0.0
        except:
            return 0.0

    # 임시 열(_sort_yield)을 만들어 숫자를 넣고, 그 숫자를 기준으로 정렬합니다.
    new_products["_sort_yield"] = new_products.apply(get_numeric_yield, axis=1)
    new_products = new_products.sort_values(by="_sort_yield", ascending=False)

    # 문자 메시지 내용 만들기
    message_lines = [f"[신규 알짜 ELS 발견: {len(new_products)}건]\n"]
    for idx, (_, row) in enumerate(new_products.iterrows(), 1):
        message_lines.append(format_product(row, idx))
    
    final_text = "\n".join(message_lines)
    
    # 문자 쏘기!
    send_sms(final_text[:MAX_MESSAGE_LENGTH])

    # 보낸 기록 업데이트
    sent_ids.update(new_products["_product_id"])
    
    # 💡 [핵심 안전장치] 아래 코드를 추가/수정하여 강제로 파일을 갱신합니다.
    import json
    import os
    
    # 현재 실행 폴더(깃허브 저장소 루트)에 확실하게 저장
    with open('sent_ids.json', 'w', encoding='utf-8') as f:
        json.dump(list(sent_ids), f, ensure_ascii=False, indent=2)
        
    logging.info(f"🎉 문자 발송 완료! 기록된 상품 수: {len(sent_ids)}건")
    # 💡 이 로그를 보고 장부가 제대로 업데이트되는지 확인합니다.

if __name__ == "__main__":
    configure_logging()
    run()
