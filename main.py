"""
만렙개미 카카오톡 챗봇 - 메인 서버
"""
import os
import uuid
import secrets
import time
import threading
from collections import defaultdict
from fastapi import FastAPI, Request, Depends, HTTPException, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import uvicorn
from contextlib import asynccontextmanager
from typing import Optional, Callable

from database import get_db, init_db, reset_db, check_db_health, SessionLocal
from handlers import CommandHandler
from utils import KakaoResponse, configure_root_logger, get_main_logger
from services.stock_service import KISAPIClient, StockService
from services.battle_service import BattleService
from config import SecurityConfig, validate_config

# 로깅 설정
configure_root_logger()
logger = get_main_logger()


# ===========================================
# 간단한 인메모리 Rate Limiter
# ===========================================
class RateLimiter:
    """
    간단한 인메모리 Rate Limiter (스레드 안전)
    - 유저별 요청 횟수 제한
    - 주기적으로 오래된 데이터 정리
    - 최대 유저 수 제한으로 메모리 폭증 방지
    """
    MAX_TRACKED_USERS = 10_000  # 메모리 폭증 방지

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict = defaultdict(list)
        self.last_cleanup = time.time()
        self._lock = threading.Lock()

    def is_allowed(self, user_id: str) -> bool:
        """요청 허용 여부 확인"""
        now = time.time()

        with self._lock:
            # 설정된 간격마다 오래된 데이터 정리
            if now - self.last_cleanup > SecurityConfig.RATE_LIMIT_CLEANUP_INTERVAL:
                self._cleanup()
                self.last_cleanup = now

            # 최대 추적 유저 수 초과 시 강제 정리
            if len(self.requests) > self.MAX_TRACKED_USERS:
                self._cleanup()

            # 해당 유저의 윈도우 내 요청 기록
            user_requests = self.requests[user_id]
            cutoff = now - self.window_seconds

            # 윈도우 밖의 오래된 요청 제거
            self.requests[user_id] = [ts for ts in user_requests if ts > cutoff]

            # 제한 확인
            if len(self.requests[user_id]) >= self.max_requests:
                return False

            # 현재 요청 기록
            self.requests[user_id].append(now)
            return True

    def _cleanup(self):
        """오래된 데이터 정리 (lock 보유 상태에서 호출됨)"""
        now = time.time()
        cutoff = now - self.window_seconds
        expired_users = []

        for user_id, timestamps in list(self.requests.items()):
            self.requests[user_id] = [ts for ts in timestamps if ts > cutoff]
            if not self.requests[user_id]:
                expired_users.append(user_id)

        for user_id in expired_users:
            del self.requests[user_id]


# Rate limiter 인스턴스 (설정값 사용)
rate_limiter = RateLimiter(
    max_requests=SecurityConfig.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=SecurityConfig.RATE_LIMIT_WINDOW_SECONDS
)


# ===========================================
# 앱 생명주기 관리
# ===========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    # 시작 시
    logger.info("만렙개미 봇 서버 시작!")

    # 설정 검증
    is_valid, errors = validate_config()
    if not is_valid:
        logger.error(f"설정 검증 실패: {errors}")
        # 중요: 설정 오류 시에도 서버는 시작 (경고만 출력)
        # 실제 프로덕션에서는 raise RuntimeError() 고려

    init_db()  # DB 테이블 생성

    # 종목 캐시 로드 (DB에서 메모리로)
    StockService.load_stock_cache()

    # 만료된 대기 배틀 정리 (서버 재시작 시)
    cleanup_db = None
    try:
        cleanup_db = SessionLocal()
        cleaned = BattleService.cleanup_stale_battles(cleanup_db)
        if cleaned > 0:
            logger.info(f"서버 시작 시 만료 배틀 {cleaned}건 정리")
    except Exception as e:
        logger.warning(f"만료 배틀 정리 실패: {e}")
    finally:
        if cleanup_db:
            cleanup_db.close()

    # KIS API 토큰 미리 발급 (타임아웃 방지)
    token = KISAPIClient.get_access_token()
    if token:
        logger.info("KIS API 토큰 준비 완료!")
    else:
        logger.warning("KIS API 토큰 발급 실패 - 환경변수 확인 필요")

    # 개발 모드 알림
    if SecurityConfig.DEV_MODE:
        logger.warning("개발 모드 활성화됨 - CORS 제한 해제")

    yield
    # 종료 시
    logger.info("만렙개미 봇 서버 종료!")


# ===========================================
# FastAPI 앱 생성
# ===========================================
app = FastAPI(
    title="만렙개미 카카오톡 챗봇",
    description="주식 던전 RPG 챗봇 API — 쪼렙 개미에서 만렙 개미로",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정 (카카오톡 도메인만 허용, 개발 모드에서는 전체 허용)
# 참고: CORS는 브라우저에서만 적용됨. 서버-to-서버 요청(Render keep-alive 등)은 영향 없음
app.add_middleware(
    CORSMiddleware,
    allow_origins=SecurityConfig.get_allowed_origins(),
    allow_credentials=False,  # 카카오톡 요청에는 credentials 불필요
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# ===========================================
# 요청 ID 추적 미들웨어
# ===========================================
@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable) -> Response:
    """
    모든 요청에 고유 ID 부여 (로그 추적용)
    X-Request-ID 헤더가 있으면 재사용, 없으면 새로 생성
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ===========================================
# 요청 본문 크기 제한 미들웨어
# ===========================================
@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next: Callable) -> Response:
    """
    요청 본문 크기 제한 (DoS 방지)
    최대 10KB 허용
    """
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > SecurityConfig.MAX_REQUEST_SIZE:
        return JSONResponse(
            status_code=413,
            content={"error": "요청 크기가 너무 큽니다.", "max_size": SecurityConfig.MAX_REQUEST_SIZE}
        )
    return await call_next(request)


# ===========================================
# 헬스체크 엔드포인트
# ===========================================
@app.get("/")
async def root():
    """서버 상태 확인"""
    return {
        "status": "ok",
        "message": "만렙개미 봇 서버가 실행 중입니다!",
        "version": "1.0.0"
    }


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    """헬스체크 (UptimeRobot 등 모니터링 서비스용)"""
    db_healthy = check_db_health()
    if not db_healthy:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "db": "disconnected"}
        )
    return {"status": "healthy", "db": "connected"}


# ===========================================
# 카카오 스킬 엔드포인트
# ===========================================
@app.post("/skill")
async def kakao_skill(request: Request, db: Session = Depends(get_db)):
    """
    카카오톡 챗봇 스킬 엔드포인트

    카카오 챗봇 관리자센터에서 이 URL을 스킬 서버로 등록합니다.
    예: https://your-domain.com/skill
    """
    try:
        # 요청 파싱
        body = await request.json()

        # 유저 정보 추출
        user_request = body.get("userRequest", {})
        user_info = user_request.get("user", {})
        kakao_id = user_info.get("id", "")
        utterance = user_request.get("utterance", "")

        # 닉네임 추출 (카카오 OpenBuilder에서 제공)
        nickname = user_info.get("properties", {}).get("nickname", "")

        # 그룹 챗봇: 채팅방 식별키 추출
        chat_info = user_request.get("chat", {})
        group_key = chat_info.get("properties", {}).get("botGroupKey", "")

        # 디버그: 카카오에서 받은 유저 정보 로그 (민감 정보 마스킹)
        masked_id = f"{kakao_id[:4]}****" if len(kakao_id) > 4 else "****"
        request_id = getattr(request.state, "request_id", "unknown")
        logger.debug(f"[{request_id}] 카카오 유저: id={masked_id}, has_nickname={bool(nickname)}")

        # 유저 ID 검증 (빈값, 너무 긴 값 방지)
        if not kakao_id or len(kakao_id) > 100:
            return KakaoResponse.simple_text("유저 정보를 확인할 수 없습니다.")

        # 악의적인 ID 패턴 차단 (SQL-like, 특수문자)
        if not kakao_id.replace("-", "").replace("_", "").isalnum():
            logger.warning(f"의심스러운 kakao_id 감지: {repr(kakao_id[:20])}")
            return KakaoResponse.simple_text("유저 정보를 확인할 수 없습니다.")

        # utterance 입력 검증 및 정제
        utterance = utterance.strip()
        if len(utterance) > 500:  # 최대 길이 제한
            utterance = utterance[:500]
        # Null 바이트 및 제어 문자 제거
        utterance = "".join(c for c in utterance if c.isprintable() or c in "\n\t")

        # Rate limiting 체크
        if not rate_limiter.is_allowed(kakao_id):
            logger.warning(f"Rate limit exceeded: {masked_id}")
            return KakaoResponse.simple_text(
                "⚠️ 요청이 너무 많습니다.\n잠시 후 다시 시도해주세요."
            )

        # 명령어 처리
        handler = CommandHandler(db, kakao_id, utterance, nickname, group_key)
        response = handler.handle()

        return response

    except Exception as e:
        logger.error(f"스킬 처리 에러: {e}", exc_info=True)

        return KakaoResponse.simple_text(
            "죄송합니다. 오류가 발생했습니다.\n잠시 후 다시 시도해주세요."
        )


# ===========================================
# 디버그용 엔드포인트
# ===========================================
@app.post("/debug/skill")
async def debug_skill(request: Request, db: Session = Depends(get_db)):
    """
    디버그용 스킬 테스트 엔드포인트 (DEV_MODE에서만 활성화)

    curl로 테스트:
    curl -X POST http://localhost:8000/debug/skill \
         -H "Content-Type: application/json" \
         -d '{"kakao_id": "test123", "message": "/시작"}'
    """
    # 프로덕션에서는 디버그 엔드포인트 비활성화
    if not SecurityConfig.DEV_MODE:
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        body = await request.json()
        kakao_id = body.get("kakao_id", "test_user")
        message = body.get("message", "/도움말")

        handler = CommandHandler(db, kakao_id, message)
        response = handler.handle()

        return response

    except Exception as e:
        logger.error(f"디버그 엔드포인트 에러: {e}", exc_info=True)
        return {"error": "내부 오류가 발생했습니다."}


# ===========================================
# 관리자 엔드포인트
# ===========================================
@app.post("/admin/reset-db")
async def admin_reset_db(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """
    데이터베이스 초기화 (모든 데이터 삭제)
    인증 필요: Authorization 헤더에 Bearer 토큰 필요

    curl -X POST http://localhost:8000/admin/reset-db \
         -H "Content-Type: application/json" \
         -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
         -d '{"confirm": "DELETE_ALL_DATA"}'
    """
    try:
        # 인증 확인
        if not authorization:
            logger.warning("관리자 API 호출 - 인증 토큰 없음")
            raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

        # Bearer 토큰 파싱
        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                raise ValueError("Invalid scheme")
        except ValueError:
            logger.warning("관리자 API 호출 - 잘못된 토큰 형식")
            raise HTTPException(status_code=401, detail="잘못된 인증 형식입니다.")

        # 토큰 검증 (타이밍 공격 방지를 위해 secrets.compare_digest 사용)
        if not secrets.compare_digest(token, SecurityConfig.ADMIN_TOKEN):
            logger.warning("관리자 API 호출 - 잘못된 토큰")
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

        body = await request.json()
        confirm = body.get("confirm", "")

        if confirm != "DELETE_ALL_DATA":
            return {
                "success": False,
                "message": "초기화를 확인하려면 confirm 필드에 'DELETE_ALL_DATA'를 입력하세요."
            }

        # 데이터베이스 초기화
        reset_db()
        logger.info("관리자에 의해 데이터베이스가 초기화됨")

        return {
            "success": True,
            "message": "데이터베이스가 초기화되었습니다. 모든 유저 데이터가 삭제되었습니다."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"관리자 API 에러: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.post("/admin/reset-seed")
async def admin_reset_seed(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """
    기존 유저 시드머니 초기화 (보유주식/거래내역 정리 + 현금 리셋)

    curl -X POST http://localhost:8000/admin/reset-seed \
         -H "Content-Type: application/json" \
         -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
         -d '{"confirm": "RESET_SEED_MONEY"}'
    """
    try:
        if not authorization:
            raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                raise ValueError("Invalid scheme")
        except ValueError:
            raise HTTPException(status_code=401, detail="잘못된 인증 형식입니다.")

        if not secrets.compare_digest(token, SecurityConfig.ADMIN_TOKEN):
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

        body = await request.json()
        confirm = body.get("confirm", "")

        if confirm != "RESET_SEED_MONEY":
            return {
                "success": False,
                "message": "시드머니 초기화를 확인하려면 confirm 필드에 'RESET_SEED_MONEY'를 입력하세요."
            }

        from models import User, Holding, Transaction
        from config import GameConfig

        db = SessionLocal()
        try:
            # 보유 주식 전량 삭제
            deleted_holdings = db.query(Holding).delete()
            # 거래 내역 전량 삭제
            deleted_transactions = db.query(Transaction).delete()
            # 모든 유저 현금 + 초기자금 리셋
            new_cash = GameConfig.INITIAL_CASH
            updated_users = db.query(User).update({
                User.cash: new_cash,
                User.initial_cash: new_cash,
            })
            db.commit()
            logger.info(
                f"시드머니 초기화 완료: {updated_users}명 유저 → {new_cash:,}원, "
                f"보유주식 {deleted_holdings}건 삭제, 거래내역 {deleted_transactions}건 삭제"
            )
            return {
                "success": True,
                "message": f"시드머니 초기화 완료",
                "data": {
                    "updated_users": updated_users,
                    "new_seed_money": new_cash,
                    "deleted_holdings": deleted_holdings,
                    "deleted_transactions": deleted_transactions,
                }
            }
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"시드머니 초기화 에러: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ===========================================
# 메인 실행
# ===========================================
if __name__ == "__main__":
    # 개발 모드에서만 reload 활성화
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=SecurityConfig.DEV_MODE
    )
