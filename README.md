# 🎮 주식왕 - 카카오톡 가상 주식 투자 게임

카카오톡에서 즐기는 가상 주식 투자 게임입니다.
실제 주식 시세를 기반으로 가상 머니로 투자하며 주식 투자를 배울 수 있습니다.

## 🎯 주요 기능

- **실시간 시세**: 실제 한국 주식 시세 연동 (pykrx)
- **가상 투자**: 1,000만원 시작 자금으로 매수/매도
- **출석 보상**: 매일 출석하면 50만원 지급
- **광고 보상**: 광고 시청으로 10만원 (1일 3회)
- **랭킹 시스템**: 수익률 기준 경쟁

## 📋 명령어

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /시작 | - | 게임 시작 (1,000만원 지급) |
| /출석 | /ㅊㅅ | 일일 출석 보상 |
| /광고 | /ㄱㄱ | 광고 시청 보상 |
| /시세 [종목명] | /ㅅㅅ | 주식 시세 조회 |
| /매수 [종목명] [수량] | /ㅁㅅ | 주식 매수 |
| /매도 [종목명] [수량] | /ㅁㄷ | 주식 매도 |
| /전량매수 [종목명] | - | 보유 현금으로 최대 매수 |
| /전량매도 [종목명] | - | 보유 주식 전량 매도 |
| /잔고 | /ㅈㄱ | 보유 현금 확인 |
| /포트폴리오 | /ㅍㅍ | 전체 자산 현황 |
| /랭킹 | /ㄹㅋ | 수익률 TOP 10 |
| /내순위 | - | 내 현재 순위 |
| /검색 [키워드] | - | 종목 검색 |
| /인기 | - | 거래량 TOP 10 |
| /도움말 | /ㄷㅇㅁ | 명령어 안내 |

## 🛠️ 기술 스택

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL / SQLite
- **Stock Data**: pykrx (한국 주식 데이터)
- **Deploy**: Railway

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

### 2. Railway 배포

1. GitHub에 코드 푸시
2. Railway에서 GitHub 연결
3. 자동 배포 완료!

## 📁 프로젝트 구조

```
stock-king-bot/
├── main.py              # FastAPI 메인 서버
├── config.py            # 설정 파일
├── database.py          # DB 연결
├── models.py            # DB 모델
├── requirements.txt     # 패키지 목록
├── Procfile             # Railway 배포용
├── services/            # 비즈니스 로직
│   ├── user_service.py
│   ├── stock_service.py
│   ├── trade_service.py
│   └── ranking_service.py
├── handlers/            # 명령어 처리
│   └── command_handler.py
└── utils/               # 유틸리티
    └── kakao_response.py
```

## 📄 라이선스

MIT License

## 👨‍💻 개발자

Made with ❤️ by [Your Name]
