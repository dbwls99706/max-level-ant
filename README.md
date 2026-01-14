# 🎮 주식왕 - 카카오톡 가상 주식 투자 게임

카카오톡에서 즐기는 가상 주식 투자 게임입니다.
실제 주식 시세를 기반으로 가상 머니로 투자하며 주식 투자를 배울 수 있습니다.

## 🎯 주요 기능

- **실시간 시세**: 한국투자증권 KIS API 연동
- **가상 투자**: 5,000만원 시작 자금으로 매수/매도
- **출석 보상**: 매일 출석하면 30만원 지급 (연속 보너스)
- **미니게임**: 복권, 슬롯머신, 동전던지기, 룰렛, 하이로우
- **PvP 배틀**: 다른 유저와 주가 예측 대결
- **랭킹 시스템**: 수익률 기준 경쟁

## 📋 주요 명령어

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /시작 | - | 게임 시작 (5,000만원 지급) |
| /출석 | /ㅊㅅ | 일일 출석 보상 (+30만원) |
| /시세 [종목명] | /ㅅㅅ | 주식 시세 조회 |
| /매수 [종목명] [수량] | /ㅁㅅ | 주식 매수 |
| /매도 [종목명] [수량] | /ㅁㄷ | 주식 매도 |
| /전량매수 [종목명] | /ㅈㅁㅅ | 보유 현금으로 최대 매수 |
| /전량매도 [종목명] | /ㅈㅁㄷ | 보유 주식 전량 매도 |
| /잔고 | /ㅈㄱ | 보유 현금 확인 |
| /포트폴리오 | /포폴 | 전체 자산 현황 |
| /급등 | /ㄱㄷ | 급등주 TOP 10 |
| /급락 | - | 급락주 TOP 10 |
| /인기 | /ㅇㄱ | 거래량 TOP 10 |
| /검색 [키워드] | /ㄱㅅ | 종목 검색 |
| /랭킹 | /ㄹㅋ | 수익률 TOP 10 |
| /내순위 | /ㄴㅅㅇ | 내 현재 순위 |
| /복권 | /ㅂㄱ | 복권 긁기 (1일 5회) |
| /게임 | - | 미니게임 목록 |
| /도움말 | /ㄷㅇㅁ | 전체 명령어 안내 |

## 🎰 미니게임 (장 마감 후)

| 게임 | 단축키 | 기대값 |
|------|--------|--------|
| /슬롯머신 [금액] | /ㅅㄹㅁ | ~83.5% |
| /동전 [금액] [앞/뒤] | /ㄷㅈ | 100% |
| /룰렛 [금액] [색상] | /ㄹㄹ | 90% |
| /하이로우 [금액] [높/낮] | /ㅎㅇㄹㅇ | 90% |
| /복권 | /ㅂㄱ | 90% |

## 🛠️ 기술 스택

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL / SQLite
- **Stock Data**: 한국투자증권 KIS API
- **Deploy**: Render / Railway

## 🚀 배포 방법

### 1. 로컬 실행

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --reload --port 8000
```

### 2. 환경 변수

```env
DATABASE_URL=postgresql://...
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
```

## 📁 프로젝트 구조

```
stock-king-bot/
├── main.py              # FastAPI 메인 서버
├── config.py            # 설정 파일
├── database.py          # DB 연결
├── models.py            # DB 모델
├── requirements.txt     # 패키지 목록
├── services/            # 비즈니스 로직
│   ├── user_service.py
│   ├── stock_service.py
│   ├── trade_service.py
│   ├── game_service.py
│   ├── battle_service.py
│   └── ranking_service.py
├── handlers/            # 명령어 처리
│   └── command_handler.py
└── utils/               # 유틸리티
    ├── kakao_response.py
    └── visual_helpers.py
```

## 📄 라이선스

MIT License
