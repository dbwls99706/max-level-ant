# 만렙개미 - 카카오톡 가상 주식 투자 게임

카카오톡에서 즐기는 가상 주식 투자 게임입니다.
실제 한국 주식 시세(KIS API)를 기반으로 가상 골드로 투자하며,
쪼렙 개미에서 만렙 개미로 성장하세요!

## 주요 기능

- **실시간 시세**: 한국투자증권 KIS OpenAPI 연동
- **가상 투자**: 1,000만원 시작 자금으로 매수/매도 (수수료 0.1%)
- **출석 보상**: 매일 출석하면 30만원 지급 (연속 보너스 + 각성 레벨 배율)
- **예측게임**: 보물상자, 시장예측, 업다운
- **각성 시스템**: 골드를 써서 레벨업 도전! Lv.10 이후 직군(트레이더/투자가/퀀트) 배정 및 전용 칭호 트리
- **PvP 배틀**: 다른 유저와 주가 예측 대결
- **랭킹 시스템**: 수익률 랭킹, 각성 랭킹
- **성장 시스템**: 일간 미션, 주간 챌린지, 업적, 마일스톤
- **뉴스**: Google News RSS 기반 종목별 뉴스
- **자산 차트**: 자산 변동 히스토리

## 주요 명령어

### 주식 투자

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /시세 [종목명] | /ㅅㅅ | 실시간 시세 조회 |
| /매수 [종목명] [수량] | /ㅁㅅ | 주식 매수 |
| /매도 [종목명] [수량] | /ㅁㄷ | 주식 매도 |
| /전량매수 [종목명] | /ㅈㅁㅅ | 보유 현금으로 최대 매수 |
| /전량매도 [종목명] | /ㅈㅁㄷ | 보유 주식 전량 매도 |
| /급등 | /ㄱㄷ | 급등주 TOP 10 |
| /급락 | - | 급락주 TOP 10 |
| /인기 | /ㅇㄱ | 거래대금 TOP 10 |
| /거래량 | - | 거래량 TOP 10 |
| /검색 [키워드] | /ㄱㅅ | 종목 검색 |
| /시장 | - | 코스피/코스닥 지수 현황 |
| /뉴스 [종목명] | /ㄴㅅ | 종목 관련 최신 뉴스 |

### 내 자산

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /잔고 | /ㅈㄱ | 보유 현금 확인 |
| /포트폴리오 | /포폴, /ㅍㅍ | 전체 자산 현황 + 수익률 |
| /거래내역 | /ㄱㄹ | 체결된 거래 기록 |
| /차트 | - | 자산 변동 차트 |
| /닉네임 [이름] | /ㄴㄴ | 닉네임 변경 |

### 랭킹/소셜

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /랭킹 | /ㄹㅋ | 수익률 TOP 10 |
| /내순위 | /ㄴㅅㅇ | 내 현재 순위 + 경쟁자 비교 |
| /각성랭킹 | /ㄱㅅㄹㅋ | 각성 레벨 TOP 10 |
| /배틀 [종목] [상승/하락] [금액] | - | PvP 주가 예측 대결 |
| /배틀목록 | - | 대기 중인 배틀 목록 |
| /미션 | - | 오늘의 거래 미션 + 보상 |
| /업적 | - | 달성한 업적 모아보기 |
| /챌린지 | - | 주간 수익률 챌린지 |
| /마일스톤 | - | 자산 목표 달성 현황 |

### 보상/게임

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /시작 | - | 게임 시작 (1,000만원 지급) |
| /출석 | /ㅊㅅ | 일일 출석 보상 (+30만원) |
| /보물상자 | /ㅂㄱ | 하루 최대 5회 무료 |
| /각성 | /ㄱㅎ | 골드를 써서 레벨업 도전 |
| /능력 | - | 각성 레벨/직군/칭호/보너스 확인 |
| /시장예측 [금액] | /ㅅㅈ | 과거 주가 예측 (장 마감 후) |
| /업다운 [금액] | /ㅇㄷ | 숫자 연속 맞추기 (장 마감 후) |
| /도움말 | /ㄷㅇㅁ | 전체 명령어 안내 |

## 기술 스택

- **Backend**: Python 3.11 + FastAPI
- **WSGI**: Uvicorn (ASGI)
- **Database**: PostgreSQL (프로덕션) / SQLite (로컬 개발)
- **ORM**: SQLAlchemy 2.x
- **Stock Data**: 한국투자증권 KIS OpenAPI
- **News**: Google News RSS
- **Cache**: cachetools (TTLCache) - 시세 60초, 랭킹 5분
- **Container**: Docker (멀티스테이지 빌드, non-root 실행)
- **Deploy**: Railway (PaaS)

## 배포 방법

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

## 프로젝트 구조

```
stock-king-bot/
├── main.py                  # FastAPI 메인 서버
├── config.py                # 설정 (게임 밸런스, 각성, 메시지 등)
├── database.py              # DB 연결 + 마이그레이션
├── models.py                # DB 모델 (10개 테이블)
├── requirements.txt         # 패키지 목록
├── Dockerfile               # Docker 빌드
├── Procfile                 # Railway 배포용
├── runtime.txt              # Python 버전 명시
├── handlers/                # 명령어 처리
│   ├── command_handler.py   # 명령어 라우팅 + 기본 핸들러
│   ├── base_handler.py      # 공통 유틸리티 믹스인
│   ├── trading_handler.py   # 매수/매도/포트폴리오
│   ├── game_handler.py      # 보물상자/시장예측/업다운/각성
│   ├── market_handler.py    # 시세/급등/급락/뉴스/검색
│   └── social_handler.py    # 랭킹/배틀/챌린지/마일스톤
├── services/                # 비즈니스 로직
│   ├── common.py            # safe_add/subtract, 공통 유틸
│   ├── user_service.py      # 유저 관리 + 출석
│   ├── stock_service.py     # KIS API 연동 + 시세 조회
│   ├── trade_service.py     # 거래 처리
│   ├── game_service.py      # 예측게임 로직
│   ├── enhance_service.py   # 각성(강화) 시스템
│   ├── ranking_service.py   # 랭킹 조회
│   ├── battle_service.py    # PvP 배틀
│   ├── news_service.py      # 뉴스 서비스
│   ├── mission_service.py   # 일간 미션
│   ├── challenge_service.py # 주간 챌린지
│   ├── milestone_service.py # 마일스톤
│   └── asset_service.py     # 자산 히스토리
├── utils/                   # 유틸리티
│   ├── kakao_response.py    # 카카오 응답 포맷
│   ├── visual_helpers.py    # 시각적 표현 헬퍼
│   ├── logger.py            # 로깅 설정
│   └── audit_logger.py      # 감사 로그
├── tests/                   # 테스트
│   ├── conftest.py          # 테스트 설정 (SQLite in-memory)
│   ├── test_trade_service.py
│   ├── test_game_service.py
│   ├── test_user_service.py
│   ├── test_mission_service.py
│   ├── test_enhance_service.py
│   ├── test_common.py
│   └── test_circuit_breaker.py
└── docs/                    # 문서
    ├── GUIDE.md             # 개발 가이드
    └── GROUP_CHATBOT_GUIDE.md # 그룹 챗봇 가이드
```

## 라이선스

MIT License
