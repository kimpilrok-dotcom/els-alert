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
    import pandas as pd
    import json
    import os
    import re
    
    logging.info("ELS 리포트 발송 준비 시작")
    
    # 1. 상품 데이터 가져오기
    products = get_filtered_els()
    if products.empty:
        logging.info("조건에 맞는 상품이 없습니다.")
        return

    # 상품명 정리 및 장부 불러오기
    products["_product_id"] = products["상품명"].astype(str).str.strip()
    sent_ids = load_sent_ids()

    # 2. 정확한 이름표로 숫자 추출 도구 만들기
    def get_numeric_yield(row):
        try:
            val_str = str(row.get("조건 충족시\n수익률(연, %)", "0"))
            numbers = re.findall(r"[-+]?\d*\.?\d+", val_str)
            return float(numbers[0]) if numbers else 0.0
        except:
            return 0.0

    def get_numeric_ki(row):
        try:
            val_str = str(row.get("낙인(KI)", "0")).strip()
            # [노낙인 차단]
            if "노낙인" in val_str or "없음" in val_str or val_str == "-" or val_str == "":
                return 0.0
            numbers = re.findall(r"[-+]?\d*\.?\d+", val_str)
            return float(numbers[0]) if numbers else 0.0
        except:
            return 0.0

    # 추출한 숫자를 새 열에 저장
    products["_sort_yield"] = products.apply(get_numeric_yield, axis=1)
    products["_sort_ki"] = products.apply(get_numeric_ki, axis=1)

    # 💡 [핵심] 낙인이 0보다 큰(노낙인이 아닌) 정상적인 데이터만 추려냅니다! (아까 지워졌던 부분)
    valid_products = products[products["_sort_ki"] > 0]
    
    if valid_products.empty:
        logging.info("유효한 낙인(KI) 데이터가 없습니다.")
        return

    # 3. 최저 낙인 / 차최저 낙인 찾기
    ki_levels = sorted(valid_products["_sort_ki"].unique())
    lowest_ki = ki_levels[0]
    second_lowest_ki = ki_levels[1] if len(ki_levels) > 1 else None

    # 최저 & 차최저 그룹 각각 상위 5개 추출
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
            
            # 기존 포맷 함수 사용
            formatted_product = format_product(row, idx)
            
            # 특수기호 및 점선 정리
            import re
            formatted_product = re.sub(r"-{3,}", "", formatted_product) 
            formatted_product = formatted_product.replace("<br/>", ", ").replace("<br>", ", ")
            formatted_product = formatted_product.strip()
            
            # 💡 [추가된 기능] 청약기간 데이터 가져오기 (예: "20260706")
            s_date = str(row.get("청약시작일", "")).split('.')[0]
            e_date = str(row.get("청약종료일", "")).split('.')[0]
            
            # "20260706"을 "07.06"으로 보기 좋게 자르는 함수
            def format_d(d):
                return f"{d[4:6]}.{d[6:8]}" if len(d) == 8 else d
            
            period_str = f"청약: {format_d(s_date)} ~ {format_d(e_date)}"
            
            # 기존 정보 맨 아랫줄에 청약기간 추가
            formatted_product = f"{formatted_product}\n{period_str}"
            
            # 신규 / 기존 태그 부착
            if pid not in sent_ids:
                message_lines.append(f"✨[신규] {formatted_product}\n")
            else:
                message_lines.append(f"  [기존] {formatted_product}\n")
        
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
