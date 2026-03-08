# CLAUDE.md - 만렙개미 (Stock King Bot)

## Project Overview

카카오톡 기반 가상 주식 투자 게임 챗봇. 한국투자증권 KIS OpenAPI로 실시간 시세를 연동하며, 유저는 가상 골드로 주식을 매수/매도하고 각성/배틀/미션 등 게임 요소를 즐길 수 있다.

- **Language**: Python 3.11
- **Framework**: FastAPI + Uvicorn (ASGI)
- **Database**: PostgreSQL (production) / SQLite (local dev, tests)
- **ORM**: SQLAlchemy 2.x
- **Deploy**: Docker (multi-stage) → Railway (PaaS)

## Quick Commands

```bash
# Run server locally
uvicorn main:app --reload --port 8000

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
├── config.py            # All game config, constants, error codes, messages
├── database.py          # DB engine, session, migration, cleanup
├── models.py            # SQLAlchemy models (10 tables)
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
├── utils/
│   ├── kakao_response.py    # Kakao chatbot response format builder
│   ├── visual_helpers.py    # Text-based charts, progress bars
│   ├── logger.py            # Logging configuration
│   └── audit_logger.py      # Audit log for sensitive operations
├── tests/               # pytest tests (SQLite in-memory)
│   ├── conftest.py          # Fixtures: db, test_user, rich_user, poor_user
│   └── test_*.py            # Service-level unit tests
├── docs/                # Documentation
├── Dockerfile           # Multi-stage build, non-root user
├── Procfile             # Railway deployment
├── requirements.txt     # Dependencies
└── pytest.ini           # pytest config: -v --tb=short
```

## Architecture & Key Patterns

### Request Flow
1. Kakao sends POST to `/api/chat` with user message
2. `main.py` extracts `kakao_id`, `utterance`, `group_key` from Kakao payload
3. Rate limiter checks (30 req/60s per user)
4. `CommandHandler.handle()` routes command via `COMMAND_ROUTES` dict
5. Handler calls service layer → DB operations → returns response dict
6. Response formatted via `KakaoResponse` utility for Kakao chatbot protocol

### Handler Architecture
`CommandHandler` uses **mixin inheritance**: `TradingHandlerMixin`, `GameHandlerMixin`, `MarketHandlerMixin`, `SocialHandlerMixin`, `BaseHandlerMixin`. Each mixin handles a domain of commands.

### Service Layer Conventions
- All services take `db: Session` as first parameter
- Use `safe_commit()` for DB writes (auto-rollback on failure)
- Use `safe_add()` / `safe_subtract()` for money operations (overflow protection)
- Return `ApiResponse.success()` or `ApiResponse.error()` dicts
- Error codes defined in `config.ErrorCode`

### Database
- Models in `models.py`, 10 tables: `users`, `holdings`, `transactions`, `battles`, `weekly_challenges`, `user_challenges`, `milestones`, `asset_history`, `chatroom_members`, `stock_cache`
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
```

## Testing

```bash
pytest                    # Run all tests
pytest tests/test_trade_service.py  # Run specific test file
pytest -k "test_buy"      # Run tests matching pattern
```

- Tests use **in-memory SQLite** (see `tests/conftest.py`)
- Each test gets a fresh DB via function-scoped `db` fixture
- Fixtures: `test_user` (10M cash), `rich_user` (100M cash), `poor_user` (1K cash)
- No external API calls in tests — mock `StockService` / `KISAPIClient` as needed

## Code Conventions

- **Language**: Code and comments in Korean; variable/function names in English
- **Config**: All game balance values, messages, and constants in `config.py` — never hardcode
- **Error handling**: Use `ErrorCode` constants and `ApiResponse` format
- **Logging**: Use module-specific loggers from `utils.logger` (`get_main_logger`, `get_handler_logger`, `get_service_logger`)
- **Money safety**: Always use `safe_add()` / `safe_subtract()` from `services.common` for financial calculations
- **No Alembic**: Schema migrations are manual via `_migrate_db()` in `database.py`
- **Imports**: Relative imports within packages (handlers, services, utils), absolute from root

## Linting

```bash
ruff check .              # Lint
ruff format --check .     # Format check
```

## Important Notes

- The app integrates with Kakao chatbot platform — responses must follow Kakao's JSON format (see `utils/kakao_response.py`)
- KIS API requires token refresh; handled in `stock_service.py`
- Group chat support: `chatroom_members` table tracks which users are in which chat rooms for per-room rankings
- Rate limiting is in-memory (not Redis) — resets on restart
- `config.py` is large (~50K) — contains all game balance, messages, enhancement tables, etc.
