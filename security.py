"""
보안 설정
- 관리자 토큰
- CORS 허용 도메인
- 요청 크기 제한 / Rate limit 파라미터
"""

import logging
import os
import secrets
from typing import Optional

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

    # ===========================================
    # 스킬 서버 인증
    # ===========================================
    # /skill은 공개 POST 엔드포인트다. 인증이 없으면 누구나 임의의
    # userRequest.user.id를 만들어 게임 명령을 실행할 수 있고,
    # ID를 바꿔가며 유저별 rate limit도 우회할 수 있다.
    # (DB 레코드 대량 생성, KIS 호출 유발, 게임 상태 조작)
    #
    # 카카오 챗봇 관리자센터의 스킬 설정에서 커스텀 헤더를 지정할 수 있으므로,
    # 그 헤더에 공유 비밀키를 실어 보내게 하고 서버에서 검증한다.
    SKILL_API_KEY = os.getenv("SKILL_API_KEY", "")
    SKILL_API_KEY_HEADER = os.getenv("SKILL_API_KEY_HEADER", "X-Skill-Key")

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

    @classmethod
    def is_skill_key_configured(cls) -> bool:
        return bool(cls.SKILL_API_KEY)

    @classmethod
    def verify_skill_key(cls, provided: Optional[str]) -> bool:
        """
        스킬 요청의 공유 비밀키 검증.

        키가 설정돼 있지 않으면 DEV_MODE에서만 통과시킨다.
        운영 환경에서는 기동 시점에 키 미설정을 막으므로(validate_config)
        여기까지 오면 통과시키지 않는다.
        """
        if not cls.SKILL_API_KEY:
            return cls.DEV_MODE
        # 타이밍 공격 방지
        return secrets.compare_digest(provided or "", cls.SKILL_API_KEY)
