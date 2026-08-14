# CLAUDE.md - 만렙개미 (Stock King Bot)

## Project Overview

카카오톡 기반 가상 주식 투자 게임 챗봇. 한국투자증권 KIS OpenAPI로 실시간 시세를 연동하며, 유저는 가상 골드로 주식을 매수/매도하고 각성/배틀/미션 등 게임 요소를 즐길 수 있다.

- **Language**: Python 3.11
- **Framework**: FastAPI + Uvicorn (ASGI)
- **Database**: PostgreSQL (production) / SQLite (local dev, tests)
- **ORM**: SQLAlchemy 2.x
- **Deploy**: Docker (multi-stage) → Render (PaaS)

## Quick Commands

```bash
# Run server locally
uvicorn main:app --reload --port 8000

# Apply DB migrations (safe on both fresh and existing databases)
alembic upgrade head

# Run tests
pytest

# Run linter
ruff check .

# Run formatter check
ruff format --check .
```

## Project Structure

```
stock-king-bot/
├── main.py              # FastAPI app, endpoints, rate limiter, lifespan
├── database.py          # DB engine, session, migration, cleanup
├── models.py            # SQLAlchemy models (11 tables)
│   # ── Configuration & shared contracts (formerly one config.py) ──
├── settings.py          # DB URL, KIS/공공데이터 API, cache TTL, validate_config()
├── security.py          # Admin token, CORS origins, request size & rate limits
├── game_config.py       # GameConfig (balance) + GameProbability (odds, EV checks)
├── quiz_history.py      # 시장예측 quiz dataset (pure data)
├── enhance_config.py    # EnhanceConfig: 각성 cost/odds/multipliers, title lookup
├── enhance_titles.py    # 레벨별 칭호·문구 (pure data)
├── enhance_classes.py   # 계열·직군·종·성장 + 각성 문구 조립 (게임 쪽 데이터)
├── market_calendar.py   # KST, holidays, market hours → 장 상태 판정
├── messages.py          # Kakao response message templates
├── errors.py            # ErrorCode constants
├── responses.py         # success_response() / error_response() builders
├── constants.py         # BattleStatus, TradeType
├── handlers/            # Command routing & response formatting
│   ├── command_handler.py   # Main router (COMMAND_ROUTES dict → method dispatch)
│   ├── base_handler.py      # Common utilities mixin
│   ├── trading_handler.py   # 매수/매도/포트폴리오
│   ├── game_handler.py      # 보물상자/시장예측/업다운/각성
│   ├── market_handler.py    # 시세/급등/급락/뉴스/검색
│   └── social_handler.py    # 랭킹/배틀/챌린지/마일스톤
├── services/            # Business logic (one service per domain)
│   ├── common.py            # safe_commit, safe_add/subtract, validation helpers
│   ├── user_service.py      # User CRUD, attendance, chatroom membership
│   ├── stock_service.py     # KIS API client, price cache (TTLCache 60s)
│   ├── trade_service.py     # Buy/sell execution, fee calculation
│   ├── game_service.py      # Prediction games logic
│   ├── enhance_service.py   # 각성 (enhancement/awakening) system
│   ├── ranking_service.py   # Leaderboard queries (TTLCache 5min)
│   ├── battle_service.py    # PvP stock prediction battles
│   ├── news_service.py      # Google News RSS integration
│   ├── mission_service.py   # Daily missions
│   ├── challenge_service.py # Weekly challenges
│   ├── milestone_service.py # Asset milestones
│   ├── collection_service.py # 도감 기록·직군/종 추첨
│   ├── asset_service.py     # Asset history tracking
│   └── quiz_data_service.py # Stock quiz data from public API
├── .github/workflows/   # CI (ruff + pytest, PostgreSQL 동시성/마이그레이션 job 포함)
├── alembic.ini          # Alembic 설정 (DB URL은 env.py가 환경변수에서 읽음)
├── migrations/          # Alembic 리비전 (env.py, versions/)
├── enhance_art.py       # 도감 이미지 프롬프트 데이터 (40직군 × 5종 × 3성장)
├── art/web/             # 생성된 도감 이미지 600장 (webp, 앱이 /art로 서빙)
├── scripts/             # 이미지 생성·변환·검사 (운영 코드 아님)
├── utils/
│   ├── kakao_response.py    # Kakao chatbot response format builder (spec limits)
│   ├── budget.py            # Per-request time budget for the 5s Kakao skill SLA
│   ├── visual_helpers.py    # Text-based charts, progress bars
│   ├── resilience.py        # CircuitBreaker, CallThrottle, BoundedConcurrency
│   ├── logger.py            # Logging configuration
│   └── audit_logger.py      # Audit log for sensitive operations
├── tests/               # pytest tests (SQLite in-memory)
│   ├── conftest.py          # Fixtures: db, test_user, rich_user, poor_user
│   └── test_*.py            # Service-level unit tests
├── docs/                # Documentation
├── Dockerfile           # Multi-stage build, non-root user
├── Procfile             # PaaS start command (uvicorn on $PORT)
├── requirements.txt     # Dependencies
└── pytest.ini           # pytest config: -v --tb=short
```

## Architecture & Key Patterns

### Request Flow
1. Kakao sends POST to `/skill` with user message
2. `main.py` extracts `kakao_id`, `utterance`, `group_key` from Kakao payload
3. Rate limiter checks (30 req/60s per user)
4. `CommandHandler.handle()` routes command via `COMMAND_ROUTES` dict
5. Handler calls service layer → DB operations → returns response dict
6. Response formatted via `KakaoResponse` utility for Kakao chatbot protocol

### Handler Architecture
`CommandHandler` uses **mixin inheritance**: `TradingHandlerMixin`, `GameHandlerMixin`, `MarketHandlerMixin`, `SocialHandlerMixin`, `BaseHandlerMixin`. Each mixin handles a domain of commands.

### Trading Lock Discipline
거래(`trade_service`)는 외부 API 호출을 **락 밖에서** 끝낸 뒤 락을 잡는다.

```
종목 resolve + KIS 시세 조회   ← 락 없음 (느릴 수 있는 구간)
        ↓
User FOR UPDATE
        ↓
잔고·보유량 재조회 + 재검증
        ↓
mutation + commit
```

- 락 밖에서 읽은 값 중 신뢰하는 것은 **주가뿐**이다. 돈·보유량은 락 이후 다시 읽는다
- 수량이 상태에 의존하는 `buy_max`/`sell_all`은 **락 안에서** 수량을 계산한다
- 락 보유 상태 전용 primitive: `_buy_stock_locked()` / `_sell_stock_locked()` (외부 호출 금지)
- 락 이후 재조회는 `populate_existing()`이 필수다. 없으면 ORM identity map이
  락 이전의 낡은 객체를 그대로 돌려줘 재검증이 무의미해진다

### Service Layer Conventions
- All services take `db: Session` as first parameter
- Use `safe_commit()` for DB writes (auto-rollback on failure)
- Use `safe_add()` / `safe_subtract()` for money operations (overflow protection)
- Return `success_response()` / `error_response()` dicts (from `responses.py`, re-exported by `services.common`)
- Error codes defined in `errors.ErrorCode`

### Database
- Models in `models.py`, 12 tables: `users`, `holdings`, `transactions`, `battles`, `weekly_challenges`, `user_challenges`, `milestones`, `asset_history`, `chatroom_members`, `stock_cache`, `api_tokens`, `class_collections`
- `api_tokens`는 KIS 접근 토큰을 영속 저장한다. 토큰이 프로세스 메모리에만 있으면
  재배포·콜드스타트마다 재발급을 시도하는데, KIS는 토큰 발급 자체에 유량 제한이 있어
  재기동이 잦으면 시세 조회가 통째로 멈춘다
- Auto-migration in `database._migrate_db()` adds missing columns on startup
- `User.cash` and financial fields use `BigInteger` to prevent overflow
- Timestamps stored as naive UTC (`_utcnow()` helper)

### Caching
- Stock prices: `cachetools.TTLCache` with 60s TTL
- Rankings: `cachetools.TTLCache` with 5min TTL
- Stock name→code lookups: DB-backed `StockCache` table

## Environment Variables

```
DATABASE_URL=sqlite:///./stock_king.db    # Local dev
# DATABASE_URL=postgresql://...           # Production
KIS_APP_KEY=<한국투자증권 API key>
KIS_APP_SECRET=<한국투자증권 API secret>
KIS_BASE_URL=https://openapi.koreainvestment.com:9443

# Optional
SKILL_API_KEY=<스킬 공유 비밀키>           # 운영 필수. 미설정 시 서버 기동 실패
SKILL_API_KEY_HEADER=X-Skill-Key          # 카카오 관리자센터에 등록할 헤더 이름
ADMIN_TOKEN=<관리자 API 토큰>              # 미설정 시 임시 토큰 생성 + 경고
DB_POOL_TIMEOUT=2.0                       # DB 커넥션 풀 대기 상한 (초)
DEV_MODE=false                            # true면 CORS 전체 허용 + 디버그 엔드포인트
KIS_MIN_CALL_INTERVAL=0.1                 # KIS 호출 간 최소 간격 (초). 모의투자면 1.0 이상
KIS_API_TIMEOUT=1.5                       # KIS 개별 시세 조회 타임아웃 (초)
KIS_RANK_TIMEOUT=3.0                      # 순위 조회 타임아웃 (초). 30여 종목이라 더 느리다
KIS_REFRESH_TIMEOUT=20.0                  # 배경 순위 갱신 타임아웃 (초). SLA가 없어 넉넉하다
KIS_REFRESH_INTERVAL=45                   # 배경 순위 갱신 주기 (초). 0이면 배경 갱신 끔
KIS_RANK_CACHE_TTL=180                    # 순위 캐시 TTL (초). 갱신 주기보다 길어야 한다
KIS_CONNECT_TIMEOUT=5.0                   # 연결 단계 타임아웃 (초). 나머지가 응답 대기 몫
KIS_TOKEN_TIMEOUT=5.0                     # KIS 토큰 발급 전용 타임아웃 (초)
KIS_MAX_CONCURRENT_CALLS=5                # 프로세스 전역 동시 KIS 호출 상한
KIS_SLOT_WAIT_CAP=1.0                     # 동시 호출 슬롯 대기 상한 (초)
SKILL_RESPONSE_BUDGET=3.5                 # 요청 전체 시간 예산 (카카오 5초 SLA 대비)
PUBLIC_DATA_API_TIMEOUT=2.0               # 공공데이터 API 타임아웃 (초)
KIS_CIRCUIT_FAILURE_THRESHOLD=5           # 서킷 차단 임계 실패 횟수
KIS_CIRCUIT_RECOVERY_TIMEOUT=60           # 차단 후 복구 프로브까지 대기 (초)
PUBLIC_DATA_SERVICE_KEY=<공공데이터포털 key>
PUBLIC_BASE_URL=https://stock-king-bot.onrender.com   # 각성 도감 이미지 절대 URL의 앞부분
ART_DIR=art/web                           # 이미지 디렉터리 (기본값)
ART_EXT=webp                              # 이미지 확장자. 카카오가 webp를 못 그리면 jpeg
```

## Testing

```bash
pytest                    # Run all tests (postgres 테스트는 자동 skip)
pytest -m "not postgres"  # Unit tests only (CI의 lint job과 동일)
pytest tests/test_trade_service.py  # Run specific test file
pytest -k "test_buy"      # Run tests matching pattern

# 동시성 통합 테스트 (실제 PostgreSQL 필요)
TEST_DATABASE_URL=postgresql://user:pw@localhost/dbname pytest -m postgres
```

의존성: `pip install -r requirements.txt -r requirements-dev.txt`

- Tests use **in-memory SQLite** (see `tests/conftest.py`)
- Each test gets a fresh DB via function-scoped `db` fixture
- Fixtures: `test_user` (10M cash), `rich_user` (100M cash), `poor_user` (1K cash)
- No external API calls in tests — mock `StockService` / `KISAPIClient` as needed
- **동시성 정합성은 SQLite로 검증되지 않는다.** `SELECT ... FOR UPDATE`에 의존하는
  매수/출석/보물상자 로직은 `tests/test_postgres_concurrency.py`가 실제 PostgreSQL에서
  검증한다 (`TEST_DATABASE_URL` 없으면 skip). CI는 postgres 서비스 컨테이너로 돌린다

## Code Conventions

- **Language**: Code and comments in Korean; variable/function names in English
- **Config**: Never hardcode game balance, messages, or limits in services/handlers. Balance → `game_config.py`, 각성 → `enhance_config.py`, messages → `messages.py`, infra/API → `settings.py`, security/limits → `security.py`
- **Error handling**: Use `ErrorCode` constants and the `error_response()` / `success_response()` format
- **Logging**: Use module-specific loggers from `utils.logger` (`get_main_logger`, `get_handler_logger`, `get_service_logger`)
- **Money safety**: Always use `safe_add()` / `safe_subtract()` from `services.common` for financial calculations
- **Alembic**: schema changes live in `migrations/versions/`. `0001_baseline` is deliberately
  **idempotent** (creates only missing tables/columns, widens int4 money columns) because the
  production DB predates Alembic — so `alembic upgrade head` works on both a fresh and an
  existing DB, with no `stamp` step. Never edit `0001_baseline` when models change; add a new
  revision. `init_db()`'s `create_all()` + `_migrate_db()` are still in place on purpose and
  are removed only after the Alembic path has run against production — see `docs/MIGRATIONS.md`
- **`0001_baseline` cannot be downgraded** and raises if you try. It doubles as an *adoption*
  step for the pre-Alembic production schema, so it cannot tell which tables it created —
  `downgrade base` would DROP `users`/`holdings`/`transactions` and destroy real user data.
  Downgrades between `0002`+ revisions are fine; write their `downgrade()` normally
- **Imports**: Relative imports within packages (handlers, services, utils), absolute from root

## Linting

```bash
ruff check .              # Lint
ruff format --check .     # Format check
```

## Important Notes

- **`/skill`은 공유 비밀키(`SKILL_API_KEY`) 헤더로 인증한다.** 없으면 누구나 임의의
  `user.id`로 게임 명령을 실행할 수 있으므로, 운영 환경에서는 키 미설정 시 기동을 막는다
  (`DEV_MODE=true`에서만 인증 없이 동작)
- **증시 휴장일 = 법정공휴일 + KRX 전용 휴장일**(근로자의 날 5/1, 연말 휴장).
  `market_calendar.py`의 데이터는 손으로 관리하므로 공휴일법 개정·임시공휴일·선거일이
  생기면 갱신해야 한다. 날짜 기준 판정은 `is_trading_day()` 사용
- The app integrates with Kakao chatbot platform — responses must follow Kakao's JSON format (see `utils/kakao_response.py`)
- KIS API requires token refresh; handled in `stock_service.py`
- Group chat support: `chatroom_members` table tracks which users are in which chat rooms for per-room rankings
- Rate limiting is in-memory (not Redis) — resets on restart
- Configuration is split by responsibility (see Project Structure). Large pure-data tables live in their own modules (`quiz_history.py`, `enhance_titles.py`) so the config modules stay readable
- **순위 조회(급등/급락/거래량/거래대금)는 캐시 + 실패 시 직전 성공값으로 물러선다.**
  순위는 유저마다 다르지 않은데 사람 수만큼 KIS에 다시 묻고 있었고, 장중에 KIS가 느려지면
  (실측 2.91초) 그대로 실패로 돌아왔다. 빈 화면보다 조금 지난 순위가 낫다.
  조회 실패 경로는 타임아웃뿐 아니라 HTTP 에러·`rt_cd` 에러·예산 소진까지 전부
  `fallback()`(직전 성공값)으로 모인다
- **순위는 요청 경로가 아니라 배경 루프가 받아온다.** `main._rank_refresh_loop()`이
  `KIS_REFRESH_INTERVAL`(기본 45초)마다 `StockService.refresh_rankings()`를 스레드풀에서
  돌려 `_WARM_RANK_KEYS`(거래량·거래대금)를 미리 채운다. 배경에는 카카오 5초 SLA가 없어
  `budget.timeout_for()`가 상한을 깎지 않으므로 `KIS_REFRESH_TIMEOUT`(기본 20초)을 그대로
  쓸 수 있다 - 요청 경로의 3.5초 예산에서는 KIS가 3초 걸리는 시간대에 통째로 실패했다.
  루프의 불변식 셋: 장 마감이면 건너뛴다(순위가 변하지 않는다), 어떤 예외로도 죽지 않는다
  (한 번 죽으면 그 뒤로 영영 낡은 값만 남는다), `CancelledError`는 반드시 다시 던진다.
  기동 시 한 번 먼저 채워 첫 유저가 느린 호출을 물지 않게 한다.
  `KIS_RANK_CACHE_TTL`(기본 180초)은 한 갱신 주기(최악 20초×2 + 45초)보다 길어야 한다.
  짧으면 유저 요청이 만료된 캐시를 만나 3.5초 예산으로 느린 KIS를 직접 부르다 실패한다 -
  배경 갱신을 만든 이유를 정면으로 되돌리는 일이다
- **서킷 브레이커는 시세용·순위용 둘이다.** 실측에서 순위(volume-rank)가 8초를 넘기는
  동안 종목별 현재가(inquire-price)는 멀쩡했다. 서킷이 하나면 느린 순위가 임계치를 채워
  서킷을 열고 그때부터 시세·매수·매도가 전부 막히며, 45초마다 도는 배경 갱신이
  HALF_OPEN 복구 프로브를 매번 가져가 실패시키므로 시세는 복구 기회조차 못 얻는다.
  한쪽 엔드포인트가 느린 것과 KIS 전체가 죽은 것은 다른 사건이다.
  로그는 `서킷 브레이커[시세]` / `서킷 브레이커[순위]`로 구분된다
- **`requests`의 타임아웃은 (연결, 응답 대기)에 각각 적용된다.** 스칼라로 8초를 주면
  최악 16초를 기다린다(실측: 상한 8초에 10.07초 대기). `_http_timeout()`이 연결 몫을
  `KIS_CONNECT_TIMEOUT`(기본 5초)으로 잘라내고 나머지를 응답 대기에 줘서 상한이
  실제 벽시계 시간을 뜻하게 만든다. KIS HTTP 호출은 전부 이 함수를 거친다.
  연결 몫을 2초로 뒀다가 상한 20초짜리 호출이 2.2초에 죽은 적이 있다 -
  타임아웃 로그가 `연결`/`응답` 중 어느 단계인지 함께 찍는 이유다
- **KIS 호출은 공용 `requests.Session`(`_http`)을 쓴다.** `requests.get()`은 호출마다
  새 Session을 만들어 매번 TCP 3-way + TLS 핸드셰이크를 한다. 서버(오리건)와
  KIS(서울) 사이에서는 그 비용이 커서 연결 단계에서만 타임아웃이 났다. keep-alive로
  재사용하면 두 번째 호출부터 핸드셰이크가 사라진다 - 상한이 1.5초뿐인 매매 경로에서
  특히 크다. 어댑터 재시도는 **0**이다. 재시도 판단은 서킷 브레이커와 폴백 캐시의
  몫이고, urllib3가 몰래 한 번 더 부르면 우리가 계산한 상한이 배가 된다.
  테스트는 `services.stock_service._http`를 patch한다(`requests`가 아니다)
- **응답 실패 경로에서 새 외부 호출을 하지 말 것.** `_popular_stock_btn()`이 캐시가 비면
  KIS를 직접 불렀는데, 순위 조회가 실패한 화면에서 버튼을 만들려다 KIS를 한 번 더 부르는
  일이 생겼다. 첫 호출이 예산을 다 써서 두 번째는 0.6초만 받고 같이 죽었다.
  지금은 순위를 성공적으로 받아온 핸들러가 `remember_popular_stock()`으로 넣어준 값만 쓴다
- KIS API calls go through `services.stock_service._kis_call()`: a process-wide
  `BoundedConcurrency` slot **outside** the `CircuitBreaker.guard()`. The slot is outside
  so a HALF_OPEN probe never waits on a slot while holding the recovery slot, and so a
  `ConcurrencyLimitError` (a local resource limit, not an API failure) is never counted as
  a circuit failure. In `HALF_OPEN` only a single recovery probe is allowed through at a time
- KIS token issuance uses its own timeout (`KIS_TOKEN_TIMEOUT`), longer than the per-query
  one: it is slower, and if it fails every subsequent query is blocked. At startup there is no
  Kakao SLA so the full value applies; during a request `budget` caps it again
- **Kakao skill SLA is 5s.** `/skill` starts a **cooperative** time budget (`utils/budget.py`) at request entry and hands it to the worker thread; external calls use `min(call timeout, remaining budget)` and are skipped when the budget is spent. This is not a hard timeout — DB query time isn't covered (pool wait is bounded separately by `DB_POOL_TIMEOUT`), and `requests` timeouts are per-connect/read, not total wall clock. Handling runs in a threadpool so one slow request can't stall the event loop
- **No sync DB work on the event loop.** An `async def` endpoint body runs on the loop thread,
  so a slow DB call there freezes *every* request in that worker. `/skill`, `/debug/skill`,
  `/health`, `/admin/reset-db` and `/admin/reset-seed` all hand their DB work to
  `run_in_threadpool`. A `Session` must be created, used, committed and closed inside the same
  worker function (`_reset_seed_money` exists for exactly this reason)
- **Group chat membership.** `chatroom_members` has an FK to `users`, so registration only works
  once the user row exists. The first `/시작` in a room creates that row *during* the command,
  so `CommandHandler.handle()` retries registration after dispatch when the pre-check found no
  user. A unique-constraint violation there means a concurrent request already registered — it
  is treated as success, not failure
- **Kakao response spec** (enforced in `utils/kakao_response.py`, verified by `tests/test_kakao_spec_compliance.py`): `outputs` ≤ 3; textCard title+description ≤ 400; basicCard description ≤ 230; listCard items ≤ 5; button label ≤ 14; buttons ≤ 2 horizontal. **버튼은 기본이 가로 2개**다 - 세로로 쌓으면 버튼 하나가 한 줄씩 대화창을 가린다. 셋 이상이 꼭 필요한 화면만 `force_vertical=True`를 쓰고, 그때 세로 한도는 **1:1이 3개, 그룹방이 5개**(그룹 가이드 v1.10.0)라 핸들러가 `self.button_cap`으로 넓힌다. `KakaoResponse.BODY_LIMIT` (350) is a deliberately stricter UX limit — the group beta guide requires responses not to cover the whole chat screen
- **각성 정체성은 (계열 × 직군 × 종 × 성장) 네 축이다.** 직군·종은 `users.enhance_job`/
  `enhance_rarity`에 저장하고 성장은 레벨에서 파생한다(`enhance_classes.growth_stage`).
  이 좌표가 곧 이미지 파일명이고 각성 성공 문구도 같은 좌표로 조립되므로,
  한쪽만 바꾸면 유저가 A 그림을 받고 B 설명을 읽는다. 파일명 규칙은
  `enhance_art.image_stem()` 한곳에만 있다
- **직군은 Lv.10 도달 시 배정되고, 실패해 Lv.0이 되면 직군·종이 함께 풀린다.**
  종은 Lv.10/20/30에서 재추첨되며 내려갈 수도 있다. **도감 기록(`class_collections`)만은
  실패해도 남는다** - 판을 넘어 남는 유일한 자산이라 여기가 무너지면 다시 시작할 이유가 없다
- **종 수익률 보정은 랭킹에만 적용한다** (상한 10%). 잔고·포트폴리오의 수익률은 보정 없는
  값이다. `RankingService._build_rankings`가 `profit_rate`(보정 후)와 `raw_profit_rate`를
  함께 돌려주므로 화면이 "실력 + 보정"을 나눠 보여줄 수 있다
- **도감 기록은 SAVEPOINT 안에서 쓴다.** 유니크 제약에 걸렸을 때 `db.rollback()`을 부르면
  같은 트랜잭션의 레벨업·비용 차감까지 사라진다. 도감은 부가 기록이지 각성의 조건이 아니다
- **각성 직군 도감 이미지는 저장소에 함께 들어 있다** (`art/web/*.webp`, 600장 약 45MB).
  앱이 `/art`로 정적 서빙하고 `AssetConfig.image_url()`이 절대 URL을 만든다. 카카오 카드는
  **공개 HTTPS 절대 URL만** 받으므로 `PUBLIC_BASE_URL`이 없으면 이미지 카드를 못 만든다
  (그때는 예외를 던지지 않고 빈 문자열을 돌려줘 텍스트로 물러선다). 원본 PNG(1.4GB)는
  `.gitignore`·`.dockerignore` 대상이고, 파일명 규칙은 `enhance_art.image_stem()` 한곳에만 있다
- `listLayout: "ranking"` is a **group-chatbot-only** bubble ('리스트(랭킹)'); the group skill guide
  v1.11.1 documents the field name and a JSON example, so it is confirmed - not in the public 1:1 spec
- **팀채팅 미지원 컴포넌트: `quickReplies` / `commerceCard` / `carousel`.** 셋 다 만들지 않는다
  (스펙 테스트가 막는다). 카드를 여러 장 넘겨 보여주는 연출은 carousel이 없어 불가능하므로
  목록은 `listCard`로 낸다. `BasicCard`/`ItemCard`는 지원된다
- **listCard 항목은 한 줄에 들어가야 한다.** 카카오는 글자 수를 막지 않고 폰에서 줄이
  접힐 뿐인데, 5줄짜리 랭킹이 10줄이 되면 그룹방 화면을 덮는다. `KakaoResponse.list_card()`가
  표시 폭(`utils.display_width`, 한글·이모지=2칸)으로 제목 20 / 설명 24에 맞춘다.
  **폭만 검사하면 잘라주니 항상 통과한다** - 테스트는 `…`로 끝나는지(정보 손실)를 본다
- **멘션은 `simpleText`에서만 동작한다.** `KakaoResponse.simple_text_with_mentions()`가
  `{{#mentions.key}}` 자리표시자와 `extra.mentions`를 함께 만든다(한 응답 15명 상한).
  카드에 자리표시자를 넣으면 치환되지 않고 문자 그대로 노출되고, simpleText에는 버튼을
  달 수 없다. 그래서 `/랭킹`처럼 버튼이 필요한 화면은 `listCard`를 유지한다
- **버튼 플러그인**(`guide`/`share`/`invite`/`inviteMember`/`mention`/`settings`/`webViewLink`)은
  `messageText`나 URL 없이 `action`만으로 동작한다. `KakaoResponse.PLUGIN_ACTIONS` 참고
- **SkillRequest에는 하위 호환 필드가 추가될 수 있다.** `main.py`는 전부 `.get()`으로 읽어
  알 수 없는 필드가 와도 터지지 않는다. 이 성질을 깨지 말 것
