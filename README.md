# 만렙개미 - 카카오톡 가상 주식 투자 게임

카카오톡에서 즐기는 가상 주식 투자 게임 챗봇입니다.
실제 한국 주식 시세(한국투자증권 KIS OpenAPI)를 기반으로 가상 골드로 투자하며,
쪼렙 개미에서 만렙 개미로 성장하세요!

## 주요 기능

- **실시간 시세**: 한국투자증권 KIS OpenAPI 연동 (60초 TTL 캐시)
- **가상 투자**: 1,000만원 시작 자금으로 매수/매도 (수수료 0.1%)
- **출석 보상**: 매일 출석 시 30만원 지급 (연속 출석 보너스 + 각성 레벨 배율)
- **예측게임**: 보물상자(하루 5회 무료), 시장예측(과거 주가 퀴즈), 업다운(숫자 연속 맞추기)
- **각성 시스템**: 골드를 써서 레벨업 도전 (Lv.0~30, 실패 시 Lv.0 초기화)
- **직군 도감**: Lv.10에 40직군 중 하나가 배정되고, 종(5등급)과 성장 단계(6)에
  따라 전용 일러스트가 붙는다. 실패로 레벨이 초기화돼도 도감 기록은 남는다
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
| /각성 | /ㄱㅎ, /강화, /능력 | 골드를 써서 레벨업 도전 (시간 제한 없음) |
| /도감 [계열] | - | 직군 도감 진행도 (계열명 주면 상세) |

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
- **Cache**: cachetools TTLCache (시세 60초, 유저 랭킹 5분, 시세 순위 180초 + 배경 갱신)
- **Container**: Docker (멀티스테이지 빌드, non-root 실행)
- **Deploy**: Render (PaaS, Docker 배포)

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

# 스킬 서버 인증 (운영 필수 - 미설정 시 서버가 기동하지 않음)
SKILL_API_KEY=<긴 랜덤 문자열>    # 카카오 관리자센터 스킬 헤더에 등록할 값
SKILL_API_KEY_HEADER=X-Skill-Key # 헤더 이름 (기본값)

# 선택
ADMIN_TOKEN=your_secure_token    # /admin/* 엔드포인트 인증 (미설정 시 자동 생성)
DEV_MODE=false                   # true 시 /debug/skill 활성화 + 스킬 인증 생략 (로컬 전용)
DB_POOL_TIMEOUT=2.0              # DB 커넥션 풀 대기 상한 (초)
SKILL_RESPONSE_BUDGET=3.5        # 요청 시간 예산 (카카오 5초 SLA 대비)
KIS_API_TIMEOUT=1.5              # KIS 개별 조회 타임아웃 (초)
KIS_TOKEN_TIMEOUT=5.0            # KIS 토큰 발급 타임아웃 (초, 조회보다 넉넉하게)
KIS_MAX_CONCURRENT_CALLS=5       # 프로세스 전역 동시 KIS 호출 상한
KIS_SLOT_WAIT_CAP=1.0            # 동시 호출 슬롯 대기 상한 (초)
KIS_CONNECT_TIMEOUT=5.0          # 연결 단계 타임아웃 (초). 나머지가 응답 대기 몫
KIS_RANK_TIMEOUT=3.0             # 순위 조회 타임아웃 (초). 30여 종목이라 더 느리다
KIS_REFRESH_TIMEOUT=40.0         # 배경 순위 갱신 타임아웃 (초). SLA가 없어 넉넉하다
KIS_REFRESH_INTERVAL=45          # 배경 순위 갱신 주기 (초). 0이면 배경 갱신 끔
KIS_RANK_CACHE_TTL=180           # 순위 캐시 TTL (초). 갱신 주기보다 길어야 한다

# 각성 도감 이미지 (카카오 카드는 공개 HTTPS 절대 URL만 받는다)
PUBLIC_BASE_URL=https://your-app.onrender.com   # 미설정 시 텍스트로 물러섬
ART_DIR=art/web                  # 이미지 디렉터리
ART_EXT=webp                     # 카카오가 webp를 못 그리면 jpeg
```

> **순위는 요청 경로가 아니라 배경 루프가 받아온다.** KIS 순위 API는 실측 17초가
> 걸려서 카카오 5초 SLA 안에 못 들어온다. `KIS_REFRESH_INTERVAL`마다 배경에서
> 받아 캐시에 넣고, 유저 요청은 메모리만 읽는다. 조회가 실패하면 직전 성공값으로
> 물러선다 - 빈 화면보다 조금 지난 순위가 낫기 때문이다.

> **KIS 토큰은 DB(`api_tokens`)에 저장된다.** 토큰은 24시간 유효한데
> 프로세스 메모리에만 두면 재배포·콜드스타트마다 재발급을 시도하게 되고,
> KIS는 토큰 발급 자체에 유량 제한이 있어 재기동이 잦으면 시세 조회가 통째로 멈춘다.

전체 목록은 `.env.example` 참고.

### 데이터베이스 마이그레이션

스키마 변경은 Alembic으로 관리한다.

```bash
alembic upgrade head     # 최신 스키마 적용 (새 DB / 기존 DB 모두 안전)
alembic check            # models.py와 실제 스키마 차이 확인
```

`0001_baseline`은 이미 테이블이 있는 기존 운영 DB에서도 그대로 돌도록
멱등하게 작성돼 있다 (`stamp` 불필요). 운영 적용 절차와 자동 마이그레이션
제거 시점은 [docs/MIGRATIONS.md](docs/MIGRATIONS.md) 참고.

### ⚠️ 스킬 인증 적용 시 배포 순서

`/skill`은 공유 비밀키 헤더로 인증한다. **키를 설정하지 않으면 서버가 기동하지 않으므로**
아래 순서를 지켜야 무중단으로 넘어갈 수 있다.

1. **Render 등 운영 환경에 `SKILL_API_KEY` 먼저 설정** (아직 배포하지 않음)
2. **카카오 챗봇 관리자센터 > 스킬 설정에 같은 헤더/값 등록**
3. **스킬 설정 배포** - 관리자센터에서 배포해야 운영 봇에 반영된다
4. **서버 코드 배포**

3번을 먼저 하는 이유: 구버전 서버는 모르는 헤더를 그냥 무시하므로 카카오 쪽을 먼저
바꿔도 안전하다. 반대로 서버를 먼저 배포하면 헤더 없는 요청이 전부 403이 된다.

키 생성:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 테스트

```bash
pytest                              # 전체 테스트 (postgres 마커는 자동 skip)
pytest -m "not postgres"            # 단위 테스트만 (CI의 lint job과 동일)
pytest tests/test_trade_service.py  # 특정 파일
pytest -k "test_buy"                # 패턴 매칭

# 동시성 통합 테스트 (실제 PostgreSQL 필요)
TEST_DATABASE_URL=postgresql://user:pw@localhost/dbname pytest -m postgres
```

기본 테스트는 인메모리 SQLite를 쓰고 외부 API를 호출하지 않는다.
다만 **동시성 정합성은 SQLite로 검증되지 않는다.** `SELECT ... FOR UPDATE`에
의존하는 매수·출석·보물상자 로직은 실제 PostgreSQL에서만 의미가 있어
`tests/test_postgres_concurrency.py`가 따로 검증한다 (CI는 서비스 컨테이너로 돌린다).

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
├── settings.py              # DB/API/캐시 설정 + 기동 시 검증
├── security.py              # 관리자 토큰, CORS, 요청 크기·레이트 제한
├── game_config.py           # 게임 밸런스·확률
├── quiz_history.py          # 시장예측 퀴즈 데이터
├── enhance_config.py        # 각성 비용·확률·칭호 조회
├── enhance_titles.py        # 각성 칭호·문구 데이터
├── enhance_classes.py       # 계열·직군·종·성장 + 각성 문구 조립
├── enhance_art.py           # 도감 이미지 프롬프트 데이터 (파일명 규칙의 단일 출처)
├── market_calendar.py       # 공휴일·장 운영시간
├── messages.py              # 응답 메시지 템플릿
├── errors.py                # 에러 코드
├── responses.py             # 서비스 응답 빌더
├── constants.py             # 배틀/거래 상태 상수
├── database.py              # DB 연결 + 자동 마이그레이션
├── models.py                # DB 모델 (12개 테이블)
├── alembic.ini              # Alembic 설정
├── migrations/              # Alembic 리비전 (env.py, versions/)
├── art/web/                 # 도감 이미지 1203장 (webp, 앱이 /art로 서빙)
├── scripts/                 # 이미지 생성·변환·검사 (운영 코드 아님)
├── requirements.txt
├── Dockerfile               # 멀티스테이지 빌드
├── Procfile                 # PaaS 기동 명령 (uvicorn, $PORT 바인딩)
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
│   ├── collection_service.py # 도감 기록·직군/종 추첨
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
│   ├── budget.py            # 카카오 5초 SLA 대비 요청 시간 예산
│   ├── resilience.py        # CircuitBreaker, CallThrottle, BoundedConcurrency
│   ├── visual_helpers.py    # 텍스트 차트, 수익률 바, 표시 폭 계산
│   ├── logger.py            # 로깅 설정
│   └── audit_logger.py      # 감사 로그
├── tests/                   # pytest 27개 파일 (기본은 SQLite 인메모리)
│   ├── conftest.py          # 픽스처: db, test_user, rich_user, poor_user
│   └── test_*.py            # 서비스·핸들러·카카오 스펙·마이그레이션 검증
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
| 각성 최대 레벨 | Lv.30 |
| 각성 비용 | 10,000원 + 현재 레벨 × 3,000원 (Lv.29 → 97,000원) |
| 각성 성공률 | 0→1 99% ~ 29→30 68% |
| 각성 도달 확률 | Lv.10 66.4%, Lv.20 19.5%, Lv.30 1.2% |
| 각성 실패 | Lv.0으로 초기화 (직군·종도 함께 해제, 도감 기록은 유지) |
| 각성 보너스 | 출석 레벨당 +5%, 보물상자 레벨당 +8% |
| 직군 배정 | Lv.10 도달 시 40직군 중 랜덤 |
| 종 추첨 | Lv.10/20/30에서 재추첨 (노멀 50% ~ 신화 1%) |
| 종 랭킹 보정 | 수익률 +0% ~ +10% (랭킹에만 적용, 잔고는 보정 없음) |
| 도감 총량 | 40직군 × 5종 × 6성장 = 1,200칸 |
| 배틀 기본 베팅 | 100,000원 |
| 최소 베팅 | 10,000원 |
| 최대 베팅 | 999,999,999,999원 |

## 라이선스

MIT License
