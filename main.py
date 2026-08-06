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

    # 💡 보기 좋게 문자로 조립 + 수익률 강조 괄호 【 】 추가!
    return (
        f"{number}. {issuer} {name}\n"
        f"기초: {underlying}\n"
        f"낙인: {knock_in} / 수익률: 【 {coupon} 】\n"
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
    # 빈 공백 번호 등 방어 코드 적용
    to_numbers = [num.strip() for num in to_numbers_str.split(",") if num.strip()]

    # 💡 최적화: 문자열이 최대 길이를 넘어가면 안전하게 자르고 '...' 추가
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH - 3] + "..."

    for to_num in to_numbers:
        try:
            message = RequestMessage(from_=from_num, to=to_num, text=text)
            service.send(message)
            logging.info(f"🎉 {to_num} 번호로 문자 발송 완료!")
        except Exception as e:
            logging.error(f"❌ {to_num} 번호 발송 실패: {e}")

def run():
    logging.info("ELS 리포트 발송 준비 시작")
    
    products = get_filtered_els()
    if products.empty:
        logging.info("조건에 맞는 상품이 없습니다.")
        return

    # 💡 최적화: SettingWithCopyWarning 방지를 위해 명시적으로 복사본 생성
    products = products.copy()
    products["_product_id"] = products["상품명"].astype(str).str.strip()
    sent_ids = load_sent_ids()

    # 💡 최적화: 정규식을 통한 apply 연산을 Pandas 벡터화(Vectorized) 연산으로 변경하여 속도 극대화
    ki_series = products["낙인(KI)"].astype(str).str.strip()
    mask_invalid = ki_series.str.contains("노낙인|없음", na=False) | ki_series.isin(["-", ""])
    
    # 모든 행의 숫자를 한 번에 추출
    extracted_ki = ki_series.str.extract(r'([-+]?\d*\.?\d+)')[0].astype(float)
    extracted_ki = extracted_ki.fillna(0.0)
    extracted_ki[mask_invalid] = 0.0 # 노낙인 등의 텍스트가 포함된 경우 0으로 처리
    
    products["_sort_ki"] = extracted_ki
    products["_sort_yield"] = products["수익률"]

    # 노낙인 제외 (정상적인 데이터만 추려냄)
    valid_products = products[products["_sort_ki"] > 0]
    
    if valid_products.empty:
        logging.info("유효한 낙인(KI) 데이터가 없습니다.")
        return

    # 최저 낙인 / 차최저 낙인 찾기
    ki_levels = sorted(valid_products["_sort_ki"].unique())
    lowest_ki = ki_levels[0]
    second_lowest_ki = ki_levels[1] if len(ki_levels) > 1 else None

    group1 = valid_products[valid_products["_sort_ki"] == lowest_ki].sort_values(by="_sort_yield", ascending=False).head(5)
    
    if second_lowest_ki is not None:
        group2 = valid_products[valid_products["_sort_ki"] == second_lowest_ki].sort_values(by="_sort_yield", ascending=False).head(5)
    else:
        group2 = pd.DataFrame()

    message_lines = ["[오늘의 알짜 ELS 리포트]\n"]
    newly_sent_product_ids = []
    
    def append_to_message(group, ki_val):
        message_lines.append(f"  ■ 낙인 {ki_val} (상위수익률 TOP 5)")
        message_lines.append("") # 띄어쓰기
        
        for idx, (_, row) in enumerate(group.iterrows(), 1):
            pid = row["_product_id"]
            newly_sent_product_ids.append(pid)
            
            formatted_product = format_product(row, idx)
            
            # 💡 최적화: 청약기간 포맷팅 로직 간결화
            period_str = str(row.get("청약기간", "-")).strip()
            if "~" in period_str:
                s_date, e_date = [d.strip() for d in period_str.split("~", 1)]
                s_date = f"{s_date[4:6]}.{s_date[6:8]}" if len(s_date) >= 8 else s_date
                e_date = f"{e_date[4:6]}.{e_date[6:8]}" if len(e_date) >= 8 else e_date
                period_str = f"청약: {s_date} ~ {e_date}"
            else:
                period_str = f"청약: {period_str}"
            
            # 💡 최적화: USD(달러) 상품 조건 검사 간결화
            search_text = f"{row.get('상품명', '')}{row.get('비고', '')}{row.get('상품유형', '')}".upper()
            is_usd = "USD" in search_text or "달러" in search_text
            usd_tag = "💵[USD] " if is_usd else ""
            
            # 신규 / 기존 태그 부착
            status_tag = "✨[신규]" if pid not in sent_ids else "  [기존]"
            message_lines.append(f"{status_tag} {usd_tag}{formatted_product}\n{period_str}\n")
    
    if not group1.empty:
        append_to_message(group1, lowest_ki)
    if not group2.empty:
        append_to_message(group2, second_lowest_ki)

    final_text = "\n".join(message_lines)
    
    # 발송
    send_sms(final_text)

    # 💡 치명적 버그 수정: 상대경로('sent_ids.json') 대신 절대경로(STATE_FILE) 사용
    sent_ids.update(newly_sent_product_ids)
    STATE_FILE.write_text(json.dumps(list(sent_ids), ensure_ascii=False, indent=2), encoding='utf-8')
        
    logging.info(f"🎉 리포트 발송 완료! (보고된 상품 수: {len(newly_sent_product_ids)}건, 누적 장부: {len(sent_ids)}건)")

if __name__ == "__main__":
    configure_logging()
    run()
