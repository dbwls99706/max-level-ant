"""
시장예측(역사 퀴즈) 문제 데이터

실제 한국 주식 역사 기반 - 특정 구간의 등락 방향을 맞히는 퀴즈.
answer: "상승" 또는 "하락"
"""

HISTORICAL_STOCK_DATA = [
    # === 삼성전자 (005930) ===
    {
        "stock_name": "삼성전자",
        "period": "2017년 1월 ~ 2018년 1월",
        "answer": "상승",
        "description": "반도체 슈퍼사이클로 메모리 수요 폭발",
    },
    {
        "stock_name": "삼성전자",
        "period": "2018년 1월 ~ 2019년 1월",
        "answer": "하락",
        "description": "메모리 반도체 가격 하락 사이클 진입",
    },
    {
        "stock_name": "삼성전자",
        "period": "2020년 3월 ~ 2021년 1월",
        "answer": "상승",
        "description": "코로나 이후 반도체 수요 급증, 언택트 호황",
    },
    {
        "stock_name": "삼성전자",
        "period": "2021년 1월 ~ 2022년 1월",
        "answer": "하락",
        "description": "글로벌 공급망 혼란과 금리 인상 우려",
    },
    {
        "stock_name": "삼성전자",
        "period": "2022년 1월 ~ 2023년 1월",
        "answer": "하락",
        "description": "메모리 다운사이클, 글로벌 IT 투자 위축",
    },
    {
        "stock_name": "삼성전자",
        "period": "2023년 1월 ~ 2024년 1월",
        "answer": "상승",
        "description": "AI 반도체 기대감, HBM 수요 증가",
    },
    # === SK하이닉스 (000660) ===
    {
        "stock_name": "SK하이닉스",
        "period": "2017년 1월 ~ 2018년 1월",
        "answer": "상승",
        "description": "메모리 호황, DRAM 가격 급등",
    },
    {
        "stock_name": "SK하이닉스",
        "period": "2018년 6월 ~ 2019년 6월",
        "answer": "하락",
        "description": "반도체 다운사이클, 재고 증가",
    },
    {
        "stock_name": "SK하이닉스",
        "period": "2020년 3월 ~ 2021년 3월",
        "answer": "상승",
        "description": "코로나 저점 반등, 서버 메모리 수요 증가",
    },
    {
        "stock_name": "SK하이닉스",
        "period": "2021년 6월 ~ 2022년 6월",
        "answer": "하락",
        "description": "메모리 업황 둔화, 금리 인상 공포",
    },
    {
        "stock_name": "SK하이닉스",
        "period": "2023년 1월 ~ 2024년 1월",
        "answer": "상승",
        "description": "AI 열풍, HBM3 독점 공급 기대",
    },
    # === 네이버 (035420) ===
    {
        "stock_name": "네이버",
        "period": "2020년 3월 ~ 2021년 3월",
        "answer": "상승",
        "description": "코로나로 온라인 커머스/광고 폭발 성장",
    },
    {
        "stock_name": "네이버",
        "period": "2021년 7월 ~ 2022년 7월",
        "answer": "하락",
        "description": "기술주 밸류에이션 조정, 금리 인상",
    },
    {
        "stock_name": "네이버",
        "period": "2019년 1월 ~ 2020년 1월",
        "answer": "상승",
        "description": "커머스 사업 확대, 라인 실적 개선",
    },
    # === 카카오 (035720) ===
    {
        "stock_name": "카카오",
        "period": "2020년 3월 ~ 2021년 6월",
        "answer": "상승",
        "description": "언택트 수혜, 카카오뱅크/카카오페이 상장 기대",
    },
    {
        "stock_name": "카카오",
        "period": "2021년 6월 ~ 2022년 6월",
        "answer": "하락",
        "description": "사업 다각화 관련 규제 이슈, 기술주 약세",
    },
    {
        "stock_name": "카카오",
        "period": "2022년 10월 ~ 2023년 3월",
        "answer": "하락",
        "description": "카카오 데이터센터 화재, SM엔터 인수전 혼란",
    },
    # === 현대자동차 (005380) ===
    {
        "stock_name": "현대자동차",
        "period": "2018년 1월 ~ 2019년 1월",
        "answer": "하락",
        "description": "중국 시장 부진, SUV 트렌드 늦은 대응",
    },
    {
        "stock_name": "현대자동차",
        "period": "2020년 3월 ~ 2021년 1월",
        "answer": "상승",
        "description": "전기차 전환 기대, 애플카 협력 루머",
    },
    {
        "stock_name": "현대자동차",
        "period": "2022년 1월 ~ 2023년 1월",
        "answer": "상승",
        "description": "미국 IRA법 수혜, 전기차 판매 호조",
    },
    # === 셀트리온 (068270) ===
    {
        "stock_name": "셀트리온",
        "period": "2017년 1월 ~ 2018년 1월",
        "answer": "상승",
        "description": "바이오시밀러 유럽 진출 성공, 개인 투자자 열풍",
    },
    {
        "stock_name": "셀트리온",
        "period": "2021년 1월 ~ 2022년 1월",
        "answer": "하락",
        "description": "바이오 업종 밸류에이션 조정, 합병 불확실성",
    },
    # === LG에너지솔루션 (373220) ===
    {
        "stock_name": "LG에너지솔루션",
        "period": "2022년 1월 ~ 2022년 12월",
        "answer": "하락",
        "description": "IPO 후 밸류에이션 부담, 원자재 가격 상승",
    },
    {
        "stock_name": "LG에너지솔루션",
        "period": "2023년 1월 ~ 2023년 7월",
        "answer": "상승",
        "description": "IRA 보조금 수혜, 북미 배터리 공장 수주",
    },
    # === LG화학 (051910) ===
    {
        "stock_name": "LG화학",
        "period": "2020년 1월 ~ 2021년 1월",
        "answer": "상승",
        "description": "전기차 배터리 분사 기대, 테슬라 공급",
    },
    {
        "stock_name": "LG화학",
        "period": "2021년 1월 ~ 2022년 6월",
        "answer": "하락",
        "description": "배터리 부문 분사 후 밸류에이션 재평가",
    },
    # === POSCO홀딩스 (005490) ===
    {
        "stock_name": "POSCO홀딩스",
        "period": "2020년 3월 ~ 2021년 5월",
        "answer": "상승",
        "description": "철강 가격 급등, 2차전지 소재 사업 부각",
    },
    {
        "stock_name": "POSCO홀딩스",
        "period": "2021년 5월 ~ 2022년 7월",
        "answer": "하락",
        "description": "철강 가격 하락, 글로벌 경기 둔화 우려",
    },
    {
        "stock_name": "POSCO홀딩스",
        "period": "2023년 1월 ~ 2023년 7월",
        "answer": "상승",
        "description": "리튬·니켈 등 2차전지 소재 밸류체인 기대",
    },
    # === 삼성SDI (006400) ===
    {
        "stock_name": "삼성SDI",
        "period": "2020년 3월 ~ 2021년 1월",
        "answer": "상승",
        "description": "전기차 배터리 수주 확대, ESS 시장 성장",
    },
    {
        "stock_name": "삼성SDI",
        "period": "2021년 11월 ~ 2022년 11월",
        "answer": "하락",
        "description": "2차전지주 밸류에이션 조정",
    },
    # === 기아 (000270) ===
    {
        "stock_name": "기아",
        "period": "2020년 6월 ~ 2021년 6월",
        "answer": "상승",
        "description": "EV6 출시 기대, 디자인 혁신 호평",
    },
    {
        "stock_name": "기아",
        "period": "2022년 1월 ~ 2023년 1월",
        "answer": "상승",
        "description": "미국 시장 판매 호조, 수익성 개선",
    },
    # === 삼성바이오로직스 (207940) ===
    {
        "stock_name": "삼성바이오로직스",
        "period": "2020년 1월 ~ 2020년 12월",
        "answer": "상승",
        "description": "코로나 백신·치료제 위탁생산(CMO) 수주",
    },
    {
        "stock_name": "삼성바이오로직스",
        "period": "2022년 1월 ~ 2022년 10월",
        "answer": "하락",
        "description": "바이오주 전반 약세, 금리 인상 부담",
    },
    # === 한화에어로스페이스 (012450) ===
    {
        "stock_name": "한화에어로스페이스",
        "period": "2022년 2월 ~ 2023년 2월",
        "answer": "상승",
        "description": "우크라이나 전쟁 이후 방산 수출 급증",
    },
    {
        "stock_name": "한화에어로스페이스",
        "period": "2020년 1월 ~ 2020년 12월",
        "answer": "하락",
        "description": "코로나 영향으로 항공 엔진 수요 급감",
    },
    # === 크래프톤 (259960) ===
    {
        "stock_name": "크래프톤",
        "period": "2021년 8월 ~ 2022년 8월",
        "answer": "하락",
        "description": "IPO 후 게임주 약세, 신작 부진 우려",
    },
    {
        "stock_name": "크래프톤",
        "period": "2023년 1월 ~ 2024년 1월",
        "answer": "상승",
        "description": "배틀그라운드 인도 재출시, 실적 개선",
    },
]
