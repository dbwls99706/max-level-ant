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
# 카카오 스킬 서버 SLA
# ===========================================
class SkillConfig:
    """
    카카오 스킬 응답 시간 제약.

    카카오는 스킬 요청을 5초 안에 응답받지 못하면 실패로 처리한다.
    (초과 시에는 useCallback/callbackUrl로 후속 응답을 보내야 한다.)

    RESPONSE_BUDGET은 그보다 짧게 잡아, 네트워크 왕복·DB·응답 직렬화에
    쓸 여유를 남긴다. 모든 외부 API 호출은 이 예산을 나눠 쓴다.
    """

    # 카카오가 보장하는 스킬 타임아웃 (초)
    KAKAO_TIMEOUT = 5.0

    # 요청 처리에 허용할 총 시간 (초) - 외부 호출 전체가 이 안에서 끝나야 한다
    RESPONSE_BUDGET = float(os.getenv("SKILL_RESPONSE_BUDGET", "3.5"))

    # 남은 예산이 이보다 적으면 새 외부 호출을 시작하지 않는다 (초)
    # 어차피 응답 전에 카카오 타임아웃이므로 캐시/폴백으로 넘어간다.
    MIN_CALL_BUDGET = 0.3

    # DB 커넥션 풀 대기 상한 (초).
    # 예산은 외부 HTTP 호출에만 전파되고 DB 대기에는 적용되지 않으므로,
    # 풀 고갈 시 SLA를 넘기지 않도록 풀 자체의 대기 시간을 짧게 잡는다.
    DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "2.0"))


# ===========================================
# 정적 이미지(각성 직군 도감) 서빙
# ===========================================
class AssetConfig:
    """
    각성 직군 이미지 서빙 설정.

    카카오 카드(basicCard 등)는 이미지를 **공개 HTTPS 절대 URL**로만 받는다.
    상대 경로나 http는 카드가 통째로 렌더되지 않는다. 그래서 서버가 자기
    바깥 주소를 알아야 하는데, 요청 헤더의 Host는 프록시에 따라 달라질 수
    있으므로 환경변수로 명시한다.

    이미지는 저장소에 함께 들어 있어(art/web, 600장 약 45MB) 앱과 같이
    배포된다. 별도 오브젝트 스토리지를 두지 않는 이유는, 이 크기에서는
    운영할 것이 하나 늘어나는 손해가 더 크기 때문이다. 훨씬 커지면
    그때 CDN으로 옮기고 BASE_URL만 바꾸면 된다.
    """

    # 예: https://stock-king-bot.onrender.com (뒤 슬래시 없이)
    BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    # 정적 마운트 경로와 실제 디렉터리
    URL_PREFIX = "/art"
    DIRECTORY = os.getenv("ART_DIR", "art/web")

    # 이미지는 한 번 만들면 바뀌지 않는다. 파일명이 곧 내용이므로
    # 길게 캐시해도 안전하고, 그만큼 카카오 쪽 재요청이 줄어든다.
    CACHE_MAX_AGE = 60 * 60 * 24 * 30  # 30일

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.BASE_URL)

    @classmethod
    def image_url(cls, stem: str) -> str:
        """이미지 절대 URL. BASE_URL 미설정이면 빈 문자열.

        빈 문자열을 돌려주는 이유는, 이미지 없이도 텍스트 카드로 물러설 수
        있어야 하기 때문이다. 여기서 예외를 던지면 도감 명령 전체가 죽는다.
        """
        if not cls.BASE_URL:
            return ""
        # 환경변수에 뒤 슬래시를 붙여 넣기 쉽다. 여기서도 한 번 더 잘라낸다.
        return f"{cls.BASE_URL.rstrip('/')}{cls.URL_PREFIX}/{stem}.webp"


# ===========================================
# 공공데이터포털 API 설정 (금융위원회 주식시세정보)
# ===========================================
class PublicDataConfig:
    SERVICE_KEY = os.getenv("PUBLIC_DATA_SERVICE_KEY", "")
    BASE_URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService"
    # 스킬 SLA(5초) 안에서 끝나야 하므로 개별 호출 상한도 짧게 잡는다
    API_TIMEOUT = float(os.getenv("PUBLIC_DATA_API_TIMEOUT", "2.0"))


# ===========================================
# 한국투자증권 KIS API 설정
# ===========================================
class KISConfig:
    APP_KEY = os.getenv("KIS_APP_KEY", "")
    APP_SECRET = os.getenv("KIS_APP_SECRET", "")
    BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")

    # 개별 호출 타임아웃 상한 (초).
    # 한 요청에서 토큰 발급 + 시세 조회가 연달아 일어나므로,
    # 2회 연속 호출해도 SkillConfig.RESPONSE_BUDGET을 넘지 않는 값이어야 한다.
    # (deadline이 한 번 더 줄여주지만, 타임아웃만으로도 SLA를 지키게 둔다.)
    # 실제 적용값은 min(이 값, 요청에 남은 예산)이다 (utils.budget 참고).
    API_TIMEOUT = float(os.getenv("KIS_API_TIMEOUT", "1.5"))

    # 토큰 발급(/oauth2/tokenP) 전용 타임아웃 상한 (초).
    # 시세 조회보다 느리고, 실패하면 그 뒤 모든 조회가 막히는 선행 호출이다.
    # 기동 시점에는 카카오 SLA가 없으므로 조회용보다 넉넉하게 준다.
    # 요청 처리 중에는 min(이 값, 남은 예산)으로 다시 잘린다 (utils.budget).
    TOKEN_TIMEOUT = float(os.getenv("KIS_TOKEN_TIMEOUT", "5.0"))

    # KIS 유량 제한(초당 거래건수) 회피용 호출 간 최소 간격(초).
    # 단일 프로세스 기준 모든 KIS 호출을 직렬화해 초당 호출 수를 제한한다.
    # 0.1 → 초당 최대 ~10건. 실전투자 한도(초당 18건) 안쪽이라 기본값으로 안전하다.
    #
    # ⚠️ 모의투자(openapivts...:29443)는 한도가 초당 1건이다.
    #    BASE_URL을 모의투자로 바꿀 때는 KIS_MIN_CALL_INTERVAL=1.0 이상으로
    #    같이 올리지 않으면 유량 초과로 조회가 계속 실패한다.
    MIN_CALL_INTERVAL = float(os.getenv("KIS_MIN_CALL_INTERVAL", "0.1"))

    # 프로세스 전체 동시 KIS 호출 상한.
    # 상류가 느려질 때 in-flight 호출이 무한정 쌓이는 것을 막는다.
    # (요청 예산이 끝나면 응답은 먼저 반환하지만 worker/소켓은 남기 때문)
    MAX_CONCURRENT_CALLS = int(os.getenv("KIS_MAX_CONCURRENT_CALLS", "5"))

    # 동시 호출 슬롯 대기 상한 (초). 실제 대기는 min(이 값, 남은 예산)
    SLOT_WAIT_CAP = float(os.getenv("KIS_SLOT_WAIT_CAP", "1.0"))

    # 서킷 브레이커 (연속 실패 시 일시 차단)
    CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("KIS_CIRCUIT_FAILURE_THRESHOLD", "5"))
    CIRCUIT_RECOVERY_TIMEOUT = float(os.getenv("KIS_CIRCUIT_RECOVERY_TIMEOUT", "60"))

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

    # 4-1. 카카오 스킬 SLA 검증
    # 예산이 카카오 타임아웃을 넘으면 응답해도 이미 실패로 처리된다.
    if SkillConfig.RESPONSE_BUDGET >= SkillConfig.KAKAO_TIMEOUT:
        errors.append(
            f"SKILL_RESPONSE_BUDGET({SkillConfig.RESPONSE_BUDGET}초)은 "
            f"카카오 스킬 타임아웃({SkillConfig.KAKAO_TIMEOUT}초)보다 작아야 합니다"
        )
    # 토큰 발급 + 실제 조회가 연달아 일어나므로 2회분이 예산에 들어가야 한다
    if KISConfig.API_TIMEOUT * 2 > SkillConfig.RESPONSE_BUDGET:
        warnings.append(
            f"KIS_API_TIMEOUT({KISConfig.API_TIMEOUT}초) 2회분이 "
            f"응답 예산({SkillConfig.RESPONSE_BUDGET}초)을 초과 - "
            f"느린 응답 시 deadline에 의해 강제로 잘립니다"
        )

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
