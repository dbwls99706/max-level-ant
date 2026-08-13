"""
외부 연동/인프라 설정
- 데이터베이스 URL
- 한국투자증권(KIS) OpenAPI
- 공공데이터포털 API
- 캐시 TTL
- 기동 시 설정 검증 (validate_config)
"""

import logging
import os
from typing import List, Tuple

from dotenv import load_dotenv

from game_config import GameConfig, GameProbability
from security import SecurityConfig

load_dotenv()

logger = logging.getLogger(__name__)


# ===========================================
# 데이터베이스 설정
# ===========================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./stock_king.db",  # 로컬 개발용 SQLite
)

# Railway PostgreSQL은 postgres:// 로 시작하는데,
# SQLAlchemy는 postgresql:// 필요
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# ===========================================
# 공공데이터포털 API 설정 (금융위원회 주식시세정보)
# ===========================================
class PublicDataConfig:
    SERVICE_KEY = os.getenv("PUBLIC_DATA_SERVICE_KEY", "")
    BASE_URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService"
    API_TIMEOUT = 10


# ===========================================
# 한국투자증권 KIS API 설정
# ===========================================
class KISConfig:
    APP_KEY = os.getenv("KIS_APP_KEY", "")
    APP_SECRET = os.getenv("KIS_APP_SECRET", "")
    BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
    API_TIMEOUT = 10  # API 요청 타임아웃 (초)

    # KIS 유량 제한(초당 거래건수) 회피용 호출 간 최소 간격(초).
    # 단일 프로세스 기준 모든 KIS 호출을 직렬화해 초당 호출 수를 제한한다.
    # 0.1 → 초당 최대 ~10건. 필요 시 환경변수로 조정 가능.
    MIN_CALL_INTERVAL = float(os.getenv("KIS_MIN_CALL_INTERVAL", "0.1"))

    # 급등/급락 순위에서 제외할 종목 키워드 (레버리지/인버스 ETF 등)
    # 이름에 아래 키워드가 포함된 종목은 개별 종목 급등/급락 순위에 노출하지 않는다.
    # 레버리지/인버스 상품은 지수의 2배로 움직여 등락률 상·하위를 독식하므로 제외한다.
    RANKING_EXCLUDE_KEYWORDS = ("레버리지", "인버스", "2X", "2x", "곱버스")

    # ETF/ETN 식별용 브랜드 접두사
    # 종목명이 아래 브랜드로 시작하면 ETF로 분류한다 (예: "KODEX 200", "TIGER 미국S&P500").
    # 개별 종목 급등/급락에서는 제외하고, ETF 전용 급등/급락(/ETF급등 등)에서만 노출한다.
    # ETN은 종목명에 "ETN"이 포함되는 특성으로 별도 판별한다.
    ETF_BRAND_PREFIXES = (
        "KODEX",
        "TIGER",
        "RISE",
        "KBSTAR",
        "SOL",
        "ACE",
        "KINDEX",
        "PLUS",
        "ARIRANG",
        "HANARO",
        "KOSEF",
        "TIMEFOLIO",
        "FOCUS",
        "TREX",
        "KIWOOM",
        "히어로즈",
        "WOORI",
        "BNK",
        "1Q",
        "VITA",
        "마이다스",
        "파워",
        "마이티",
        "KCGI",
        "WON",
    )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.APP_KEY and cls.APP_SECRET)


# ===========================================
# 캐시 설정
# ===========================================
class CacheConfig:
    # 주식 시세 캐시 시간 (초)
    STOCK_PRICE_TTL = 60  # 1분

    # 랭킹 캐시 시간 (초)
    RANKING_TTL = 300  # 5분


# ===========================================
# 설정 검증
# ===========================================
def validate_config() -> Tuple[bool, List[str]]:
    """
    모든 설정을 검증하고 결과 반환

    Returns:
        (is_valid, errors): 검증 통과 여부와 에러 목록
    """
    errors = []
    warnings = []

    # 1. 필수 환경변수 검증
    if not KISConfig.is_configured():
        warnings.append("KIS API 미설정 - 실시간 시세 조회 불가")

    # 2. 데이터베이스 URL 검증
    if not DATABASE_URL:
        errors.append("DATABASE_URL이 설정되지 않았습니다")
    elif "sqlite" in DATABASE_URL and not SecurityConfig.DEV_MODE:
        warnings.append("프로덕션에서 SQLite 사용 중 - PostgreSQL 권장")

    # 3. 게임 설정 값 범위 검증
    if GameConfig.MIN_BET <= 0:
        errors.append(f"MIN_BET는 양수여야 합니다: {GameConfig.MIN_BET}")
    if GameConfig.MAX_BET <= GameConfig.MIN_BET:
        errors.append(
            f"MAX_BET({GameConfig.MAX_BET})는 MIN_BET({GameConfig.MIN_BET})보다 커야 합니다"
        )
    if GameConfig.INITIAL_CASH <= 0:
        errors.append(f"INITIAL_CASH는 양수여야 합니다: {GameConfig.INITIAL_CASH}")
    if not (0 <= GameConfig.TRADE_FEE_RATE <= 0.1):
        errors.append(
            f"TRADE_FEE_RATE는 0~10% 범위여야 합니다: {GameConfig.TRADE_FEE_RATE}"
        )

    # 4. 게임 확률 검증
    if not GameProbability.validate_probabilities():
        errors.append("게임 확률 설정 오류 - 확률 합계가 1이 아닙니다")

    # 5. 기대값 검증 (과도하게 높거나 낮은 경우 경고)
    for game in ["lottery", "stock_quiz", "updown"]:
        ev = GameProbability.calculate_expected_value(game)
        if ev > 150:
            warnings.append(f"{game} 기대값이 너무 높음: {ev:.1f}%")
        elif ev < 50:
            warnings.append(f"{game} 기대값이 너무 낮음: {ev:.1f}%")

    # 로그 출력
    for warning in warnings:
        logger.warning(f"설정 경고: {warning}")
    for error in errors:
        logger.error(f"설정 오류: {error}")

    is_valid = len(errors) == 0

    if is_valid:
        logger.info("설정 검증 완료 - 모든 필수 설정 확인됨")

    return is_valid, errors
