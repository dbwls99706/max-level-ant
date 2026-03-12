# 만렙개미 - 카카오톡 가상 주식 투자 게임

카카오톡에서 즐기는 가상 주식 투자 게임 챗봇입니다.
실제 한국 주식 시세(한국투자증권 KIS OpenAPI)를 기반으로 가상 골드로 투자하며,
쪼렙 개미에서 만렙 개미로 성장하세요!

## 주요 기능

- **실시간 시세**: 한국투자증권 KIS OpenAPI 연동 (60초 TTL 캐시)
- **가상 투자**: 1,000만원 시작 자금으로 매수/매도 (수수료 0.1%)
- **출석 보상**: 매일 출석 시 30만원 지급 (연속 출석 보너스 + 각성 레벨 배율)
- **예측게임**: 보물상자(하루 5회 무료), 시장예측(과거 주가 퀴즈), 업다운(숫자 연속 맞추기)
- **각성 시스템**: 골드를 써서 레벨업 도전 (Lv.0~20, 실패 시 Lv.0 초기화)
- **PvP 배틀**: 다른 유저와 주가 예측 대결 (배틀 생성/참가/결과 확인)
- **랭킹 시스템**: 수익률 랭킹, 각성 레벨 랭킹
- **성장 시스템**: 일간 미션(3회 거래 → 20만원), 주간 챌린지, 마일스톤(자산 목표)
- **뉴스**: Google News RSS 기반 종목별 뉴스
- **자산 차트**: 텍스트 기반 자산 변동 히스토리

## 명령어 목록

### 기본

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /시작 | /start | 게임 시작 (1,000만원 지급) |
| /출석 | /ㅊㅅ | 일일 출석 보상 (+30만원, 연속 보너스) |
| /도움말 | /help, /ㄷㅇㅁ | 전체 명령어 안내 |

### 주식 투자

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /시세 [종목명] | /ㅅㅅ | 실시간 시세 조회 |
| /매수 [종목명] [수량] | /ㅁㅅ | 주식 매수 |
| /매도 [종목명] [수량] | /ㅁㄷ | 주식 매도 |
| /전량매수 [종목명] | /ㅈㅁㅅ | 보유 현금으로 최대 매수 |
| /전량매도 [종목명] | /ㅈㅁㄷ | 보유 주식 전량 매도 |

### 시장 정보

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /급등 | /상승, /ㄱㄷ | 급등주 TOP 10 |
| /급락 | /하락 | 급락주 TOP 10 |
| /인기 | /ㅇㄱ | 거래대금 TOP 10 |
| /거래량 | - | 거래량 TOP 10 |
| /검색 [키워드] | /ㄱㅅ | 종목 검색 |
| /시장 | /지수 | 코스피/코스닥 지수 현황 |
| /뉴스 [종목명] | /ㄴㅅ | 종목 관련 최신 뉴스 |

### 내 자산

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /잔고 | /ㅈㄱ | 보유 현금 확인 |
| /포트폴리오 | /포폴, /ㅍㅍ | 전체 자산 현황 + 수익률 |
| /거래내역 | /ㄱㄹ | 체결된 거래 기록 |
| /차트 | /자산차트 | 자산 변동 차트 |
| /닉네임 [이름] | /ㄴㄴ | 닉네임 변경 |

### 게임/보상

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /예측 | /예측게임 | 예측게임 메뉴 |
| /복권 | /보물상자, /ㅂㄱ | 하루 최대 5회 무료 복권 |
| /시장예측 [금액] | /ㅅㅈ | 과거 주가 예측 (장 마감 후) |
| /업다운 [금액] | /ㅇㄷ | 숫자 연속 맞추기 (장 마감 후) |
| /업다운정산 | - | 업다운 게임 중간 정산 |
| /각성 | /ㄱㅎ, /강화, /능력 | 골드를 써서 레벨업 도전 |

### 랭킹/소셜

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /랭킹 | /ㄹㅋ | 수익률 TOP 10 |
| /내순위 | /ㄴㅅㅇ | 내 현재 순위 + 경쟁자 비교 |
| /각성랭킹 | /ㄱㅅㄹㅋ | 각성 레벨 TOP 10 |
| /미션 | - | 오늘의 거래 미션 + 보상 |
| /업적 | - | 달성한 업적 모아보기 |

### 배틀

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /배틀생성 | /배틀 | PvP 주가 예측 배틀 생성 |
| /배틀참가 | - | 대기 중인 배틀에 참가 |
| /배틀결과 | - | 배틀 결과 확인 |
| /배틀목록 | /대기배틀 | 대기 중인 배틀 목록 |
| /배틀설명 | - | 배틀 시스템 설명 |

### 챌린지/마일스톤

| 명령어 | 단축키 | 설명 |
|--------|--------|------|
| /챌린지 | /주간 | 주간 수익률 챌린지 |
| /챌린지보상 | - | 챌린지 보상 수령 |
| /마일스톤 | /목표 | 자산 목표 달성 현황 |
| /마일스톤보상 | - | 마일스톤 보상 수령 |

## 기술 스택

- **Backend**: Python 3.11 + FastAPI 0.109.0
- **ASGI Server**: Uvicorn 0.27.0
- **Database**: PostgreSQL (프로덕션) / SQLite (로컬 개발)
- **ORM**: SQLAlchemy 2.x
- **Stock Data**: 한국투자증권 KIS OpenAPI (서킷 브레이커 적용)
- **News**: Google News RSS
- **Cache**: cachetools TTLCache (시세 60초, 랭킹 5분)
- **Container**: Docker (멀티스테이지 빌드, non-root 실행)
- **Deploy**: Railway (PaaS)

## 실행 방법

### 로컬 실행

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일에 KIS API 키 입력

# 서버 실행
uvicorn main:app --reload --port 8000
```

### 환경 변수

```env
# 데이터베이스
DATABASE_URL=sqlite:///./stock_king.db          # 로컬 개발
# DATABASE_URL=postgresql://user:pass@host/db   # 프로덕션

# 한국투자증권 KIS OpenAPI
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_BASE_URL=https://openapi.koreainvestment.com:9443

# 선택
ADMIN_TOKEN=your_secure_token    # /admin/* 엔드포인트 인증 (미설정 시 자동 생성)
DEV_MODE=false                   # true 시 /debug/skill 엔드포인트 활성화
```

### 테스트

```bash
pytest                              # 전체 테스트
pytest tests/test_trade_service.py  # 특정 파일
pytest -k "test_buy"                # 패턴 매칭
```

테스트는 인메모리 SQLite를 사용하며 외부 API 호출 없이 동작합니다.

### Docker

```bash
docker build -t stock-king-bot:latest .
docker run -p 8000:8000 --env-file .env stock-king-bot:latest
```

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/skill` | 카카오 챗봇 스킬 엔드포인트 (메인) |
| `GET` | `/` | 서버 상태 확인 |
| `GET/HEAD` | `/health` | 헬스 체크 (모니터링용) |
| `POST` | `/debug/skill` | 로컬 테스트용 (DEV_MODE=true 시) |
| `POST` | `/admin/reset-db` | DB 초기화 (Bearer 토큰 인증) |
| `POST` | `/admin/reset-seed` | 시드머니 초기화 (Bearer 토큰 인증) |

## 프로젝트 구조

```
stock-king-bot/
├── main.py                  # FastAPI 메인 서버 + 엔드포인트
├── config.py                # 설정 (게임 밸런스, 각성, 메시지 등)
├── database.py              # DB 연결 + 자동 마이그레이션
├── models.py                # DB 모델 (10개 테이블)
├── requirements.txt
├── Dockerfile               # 멀티스테이지 빌드
├── Procfile                 # Railway 배포용
├── runtime.txt              # Python 3.11.0
├── handlers/                # 명령어 처리 (믹스인 아키텍처)
│   ├── command_handler.py   # 명령어 라우팅 (COMMAND_ROUTES)
│   ├── base_handler.py      # 공통 유틸리티 믹스인
│   ├── trading_handler.py   # 매수/매도/포트폴리오
│   ├── game_handler.py      # 보물상자/시장예측/업다운/각성
│   ├── market_handler.py    # 시세/급등/급락/뉴스/검색
│   └── social_handler.py    # 랭킹/배틀/챌린지/마일스톤
├── services/                # 비즈니스 로직
│   ├── common.py            # safe_add/subtract, 공통 유틸
│   ├── user_service.py      # 유저 관리 + 출석
│   ├── stock_service.py     # KIS API 연동 + 시세 캐시
│   ├── trade_service.py     # 거래 처리 + 수수료
│   ├── game_service.py      # 예측게임 로직
│   ├── enhance_service.py   # 각성(강화) 시스템
│   ├── ranking_service.py   # 랭킹 조회 + 캐시
│   ├── battle_service.py    # PvP 배틀
│   ├── news_service.py      # Google News RSS
│   ├── mission_service.py   # 일간 미션
│   ├── challenge_service.py # 주간 챌린지
│   ├── milestone_service.py # 마일스톤
│   ├── asset_service.py     # 자산 히스토리
│   └── quiz_data_service.py # 주식 퀴즈 데이터 (공공 API)
├── utils/                   # 유틸리티
│   ├── kakao_response.py    # 카카오 응답 포맷 빌더
│   ├── visual_helpers.py    # 텍스트 차트, 수익률 바
│   ├── logger.py            # 로깅 설정
│   └── audit_logger.py      # 감사 로그
├── tests/                   # pytest (SQLite 인메모리)
│   ├── conftest.py          # 픽스처: db, test_user, rich_user, poor_user
│   ├── test_trade_service.py
│   ├── test_game_service.py
│   ├── test_user_service.py
│   ├── test_mission_service.py
│   ├── test_enhance_service.py
│   ├── test_common.py
│   └── test_circuit_breaker.py
└── docs/
    ├── GUIDE.md             # 개발 + 배포 가이드
    └── GROUP_CHATBOT_GUIDE.md # 그룹 챗봇(팀채팅) 가이드
```

## 게임 밸런스

| 항목 | 값 |
|------|-----|
| 시작 자금 | 10,000,000원 |
| 출석 보상 | 300,000원/일 |
| 연속 출석 배율 | 3일 1.2배, 5일 1.5배, 7일 2.0배 |
| 거래 수수료 | 0.1% |
| 일간 미션 | 3회 거래 → 200,000원 |
| 보물상자 | 하루 5회, 무료 |
| 각성 최대 레벨 | Lv.20 |
| 각성 비용 | (레벨+1) × 100,000원 |
| 각성 성공률 | Lv.1 95% ~ Lv.20 4% |
| 각성 실패 | Lv.0으로 초기화 |
| 배틀 기본 베팅 | 100,000원 |
| 최소 베팅 | 10,000원 |
| 최대 베팅 | 999,999,999,999원 |

## 라이선스

MIT License
