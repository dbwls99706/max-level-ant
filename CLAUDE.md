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
├── enhance_titles.py    # 각성 title trees & flavor text (pure data)
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
│   ├── asset_service.py     # Asset history tracking
│   └── quiz_data_service.py # Stock quiz data from public API
├── .github/workflows/   # CI (ruff + pytest, PostgreSQL 동시성/마이그레이션 job 포함)
├── alembic.ini          # Alembic 설정 (DB URL은 env.py가 환경변수에서 읽음)
├── migrations/          # Alembic 리비전 (env.py, versions/)
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
- Models in `models.py`, 11 tables: `users`, `holdings`, `transactions`, `battles`, `weekly_challenges`, `user_challenges`, `milestones`, `asset_history`, `chatroom_members`, `stock_cache`, `api_tokens`
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
KIS_API_TIMEOUT=1.5                       # KIS 개별 호출 타임아웃 (초)
KIS_TOKEN_TIMEOUT=5.0                     # KIS 토큰 발급 전용 타임아웃 (초)
KIS_MAX_CONCURRENT_CALLS=5                # 프로세스 전역 동시 KIS 호출 상한
KIS_SLOT_WAIT_CAP=1.0                     # 동시 호출 슬롯 대기 상한 (초)
SKILL_RESPONSE_BUDGET=3.5                 # 요청 전체 시간 예산 (카카오 5초 SLA 대비)
PUBLIC_DATA_API_TIMEOUT=2.0               # 공공데이터 API 타임아웃 (초)
KIS_CIRCUIT_FAILURE_THRESHOLD=5           # 서킷 차단 임계 실패 횟수
KIS_CIRCUIT_RECOVERY_TIMEOUT=60           # 차단 후 복구 프로브까지 대기 (초)
PUBLIC_DATA_SERVICE_KEY=<공공데이터포털 key>
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
- **Kakao response spec** (enforced in `utils/kakao_response.py`, verified by `tests/test_kakao_spec_compliance.py`): `outputs` ≤ 3; textCard title+description ≤ 400; basicCard description ≤ 230; listCard items ≤ 5; buttons ≤ 3 vertical / 2 horizontal. `KakaoResponse.BODY_LIMIT` (350) is a deliberately stricter UX limit — the group beta guide requires responses not to cover the whole chat screen
- `listLayout: "ranking"` is a **group-chatbot-only** bubble ('리스트(랭킹)', beta guide slide 32); it is not in the public 1:1 spec
