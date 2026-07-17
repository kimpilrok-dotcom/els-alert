# --- 💡 3) 배리어, 만기, 주기 추출 (정밀 타격 업그레이드) ---
        
        # 1. 배리어 찾기: 75-75-75(L50)-70 처럼 중간에 괄호가 껴서 끊기는 문제 해결
        # 괄호 안의 내용(예: L50)을 임시로 지워서 숫자 패턴이 끝까지 이어지게 만듭니다.
        clean_text = re.sub(r'\([A-Za-z0-9]+\)', '', str(row_text))
        m_barrier = re.search(r'(\d{2,3}(?:[-\/]\d{2,3}){2,})', clean_text)
        
        if m_barrier: 
            # 슬래시(/)로 적힌 것도 하이픈(-)으로 예쁘게 통일합니다.
            barrier_list.append(m_barrier.group(1).replace('/', '-'))
        else: 
            barrier_list.append("-")
            
        # 2. 만기 찾기: 3년뿐만 아니라 영어 3y, 3Y도 '3년'으로 번역해서 가져옵니다.
        m_maturity = re.search(r'(\d+(?:\.\d+)?)\s*(년|y)', str(row_text), re.IGNORECASE)
        
        if m_maturity: 
            maturity_list.append(m_maturity.group(1) + "년")
        else: 
            maturity_list.append("-")

        # 3. 주기 찾기: 6개월뿐만 아니라 영어 6m, 6M도 '6개월'로 번역해서 가져옵니다.
        m_cycle = re.search(r'(?<!\d\.)(\d+)\s*(개월|m)(?!\w)', str(row_text), re.IGNORECASE)
        
        if m_cycle: 
            cycle_list.append(m_cycle.group(1) + "개월")
        else: 
            cycle_list.append("-")
