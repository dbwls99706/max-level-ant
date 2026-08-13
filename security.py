"""
보안 설정
- 관리자 토큰
- CORS 허용 도메인
- 요청 크기 제한 / Rate limit 파라미터
"""

import logging
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class SecurityConfig:
    """보안 관련 설정"""

    # 개발 모드 (CORS 전체 허용, 디버그 엔드포인트 활성화)
    DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

    # 관리자 토큰 (환경변수 필수 - 없으면 랜덤 생성 후 경고)
    # 운영 환경에서는 반드시 ADMIN_TOKEN 환경변수를 설정해야 합니다.
    _admin_token = os.getenv("ADMIN_TOKEN")
    if not _admin_token:
        _admin_token = secrets.token_urlsafe(32)
        if not DEV_MODE:
            logger.error(
                "⚠️  ADMIN_TOKEN 환경변수가 설정되지 않았습니다! "
                "운영 환경에서는 반드시 ADMIN_TOKEN을 설정하세요. "
                "임시 토큰이 생성되었으나 서버 재시작 시 변경됩니다."
            )
        else:
            logger.warning("ADMIN_TOKEN 미설정 (DEV_MODE): 임시 토큰 사용 중")
    ADMIN_TOKEN = _admin_token
    del _admin_token

    # 요청 본문 최대 크기 (10KB) - DoS 방지
    MAX_REQUEST_SIZE = 10 * 1024

    # CORS 허용 도메인
    ALLOWED_ORIGINS = [
        "https://talk.kakao.com",
        "https://pf.kakao.com",
        "https://kapi.kakao.com",
    ]

    # Rate Limiter 설정
    RATE_LIMIT_MAX_REQUESTS = 30  # 윈도우당 최대 요청 수
    RATE_LIMIT_WINDOW_SECONDS = 60  # 윈도우 크기 (초)
    RATE_LIMIT_CLEANUP_INTERVAL = 300  # 클린업 간격 (초)
    RATE_LIMIT_MAX_TRACKED_USERS = 10_000  # 추적 유저 수 상한 (메모리 폭증 방지)

    @classmethod
    def get_allowed_origins(cls) -> list:
        """허용된 origin 목록 반환"""
        if cls.DEV_MODE:
            return ["*"]
        return cls.ALLOWED_ORIGINS
