# 데이터베이스 마이그레이션 (Alembic)

## 배경

Alembic 도입 전에는 서버 기동 시 `database.init_db()`가
`Base.metadata.create_all()` + `_migrate_db()`(users에 누락 컬럼 ALTER)로
스키마를 맞췄다. 컬럼 추가만 가능하고, 이름 변경·삭제·제약조건 변경은
할 수 없으며, 어떤 스키마가 적용됐는지 추적할 수단도 없었다.

지금은 Alembic이 스키마 변경의 단일 출처다.

## baseline 리비전이 멱등한 이유

운영 DB에는 이미 모든 테이블이 존재한다. 평범한 baseline이라면
`CREATE TABLE users`에서 바로 실패한다. 그래서 `0001_baseline`은
**있는 것은 건드리지 않고 없는 것만 채우도록** 되어 있다.

- 이미 있는 테이블은 만들지 않는다
- `users`에 빠진 컬럼만 추가한다 (구 `_migrate_db()`가 하던 일)
- PostgreSQL에서 `transactions.fee`, `holdings.avg_price`가 int4면 int8로 넓힌다

덕분에 **새 DB든 기존 운영 DB든 `alembic upgrade head` 한 명령으로 동일하게
처리된다.** `alembic stamp`를 먼저 칠 필요가 없다.

> `0001_baseline`의 테이블 정의는 그 시점에 **고정**된 것이다.
> 모델을 바꿀 때 baseline을 수정하면 안 된다 — 새 리비전을 만들어야 한다.
> (`tests/test_alembic_migrations.py`가 baseline의 `models`/`database` import를 막는다)

## 운영 DB 적용 절차 (최초 1회)

1. **백업.** Render 관리형 PostgreSQL이면 대시보드에서 백업/스냅샷을 먼저 만든다.
   이 단계를 건너뛰지 말 것.

2. **적용 전 상태 확인** (아직 `alembic_version`이 없어야 정상):

   ```bash
   psql "$DATABASE_URL" -c "\dt"
   ```

3. **마이그레이션 실행:**

   ```bash
   DATABASE_URL="<운영 DB URL>" alembic upgrade head
   ```

   기존 DB에서는 대부분 no-op이다. 실제로 바뀌는 것은
   `alembic_version` 테이블 생성과, 혹시 빠져 있던 테이블·컬럼뿐이다.

4. **결과 확인:**

   ```bash
   psql "$DATABASE_URL" -c "SELECT * FROM alembic_version;"   # 0001_baseline
   DATABASE_URL="<운영 DB URL>" alembic check                  # 차이 없음이어야 한다
   ```

`alembic check`이 차이를 보고하면 운영 DB가 모델과 어긋난 것이다.
그 차이로 새 리비전을 만들어(`alembic revision --autogenerate`) 적용한다.

## 자동 마이그레이션은 아직 남아 있다

`init_db()`의 `create_all()` + `_migrate_db()`는 **의도적으로 그대로 두었다.**
운영 DB에 Alembic 경로가 실제로 한 번 적용되기 전에 이것을 떼면,
문제가 생겼을 때 되돌릴 곳이 없어진다.

위 절차를 운영에서 완료하고 정상 동작을 확인한 뒤에 별도 변경으로 제거한다:

- `database.init_db()`에서 `create_all()` / `_migrate_db()` / `_widen_integer_columns()` 제거
- 배포 시작 명령 앞에 `alembic upgrade head` 추가
  (`Procfile` 또는 Render의 pre-deploy 명령)

그때까지는 두 경로가 같은 결과를 낸다. `create_all`은 이미 있는 테이블을
건드리지 않고, `_migrate_db`도 없는 컬럼만 추가하기 때문이다.

## 새 마이그레이션 만들기

```bash
# 1. models.py 수정
# 2. 리비전 생성 (로컬 DB가 현재 head 상태여야 한다)
DATABASE_URL="sqlite:///./stock_king.db" alembic revision --autogenerate -m "설명"
# 3. 생성된 파일을 반드시 눈으로 확인 (autogenerate는 완벽하지 않다)
# 4. 적용
DATABASE_URL="sqlite:///./stock_king.db" alembic upgrade head
```

CI(PostgreSQL job)가 새 DB에서 `alembic upgrade head` → `alembic check`을
돌리므로, 모델만 고치고 리비전을 빼먹으면 빌드가 실패한다.

## 자주 쓰는 명령

```bash
alembic current              # 현재 리비전
alembic history              # 리비전 이력
alembic upgrade head         # 최신까지 적용
alembic downgrade -1         # 한 단계 되돌리기
alembic check                # 모델과 DB 스키마 차이 확인
```

DB URL은 `alembic.ini`가 아니라 환경변수 `DATABASE_URL`에서 읽는다
(`migrations/env.py`). 앱과 마이그레이션이 서로 다른 DB를 보는 사고를 막기 위해서다.
일회성으로 다른 DB를 지정하려면 `-x db_url=...`을 쓴다.
