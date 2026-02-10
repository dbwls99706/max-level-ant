"""
주식왕 봇 설정 파일
"""
import os
import secrets
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple, List
import pytz
from dotenv import load_dotenv

load_dotenv()

# 설정 모듈용 로거
_config_logger = logging.getLogger(__name__)


# ===========================================
# 에러 코드 상수
# ===========================================
class ErrorCode:
    """표준화된 에러 코드"""
    USER_NOT_FOUND = "USER_NOT_FOUND"
    MARKET_CLOSED = "MARKET_CLOSED"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    STOCK_NOT_FOUND = "STOCK_NOT_FOUND"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_BET = "INVALID_BET"
    INVALID_CHOICE = "INVALID_CHOICE"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    INVALID_STATE = "INVALID_STATE"
    DAILY_LIMIT_REACHED = "DAILY_LIMIT_REACHED"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNAUTHORIZED = "UNAUTHORIZED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DB_ERROR = "DB_ERROR"
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"


class ApiResponse:
    """표준화된 API 응답 형식"""

    @staticmethod
    def success(data: Optional[Dict] = None, message: str = "성공") -> Dict[str, Any]:
        """성공 응답"""
        return {
            "success": True,
            "message": message,
            "data": data or {}
        }

    @staticmethod
    def error(
        error_code: str,
        message: str,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """에러 응답"""
        return {
            "success": False,
            "error_code": error_code,
            "message": message,
            "data": data or {}
        }


# ===========================================
# 배틀 상태 상수
# ===========================================
class BattleStatus:
    """배틀 상태"""
    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


# ===========================================
# 거래 타입 상수
# ===========================================
class TradeType:
    """거래 타입"""
    BUY = "BUY"
    SELL = "SELL"


# ===========================================
# 보안 설정
# ===========================================
class SecurityConfig:
    """보안 관련 설정"""
    # 관리자 토큰 (환경변수 필수 - 없으면 랜덤 생성 후 경고)
    _admin_token = os.getenv("ADMIN_TOKEN")
    if not _admin_token:
        _admin_token = secrets.token_urlsafe(32)
        _config_logger.warning(
            f"ADMIN_TOKEN 환경변수가 설정되지 않았습니다. "
            f"임시 토큰 생성됨 (재시작 시 변경됨): {_admin_token[:8]}..."
        )
    ADMIN_TOKEN = _admin_token

    # CORS 허용 도메인
    ALLOWED_ORIGINS = [
        "https://talk.kakao.com",
        "https://pf.kakao.com",
        "https://kapi.kakao.com",
    ]

    # 개발 모드에서는 모든 origin 허용
    DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

    # Rate Limiter 설정
    RATE_LIMIT_MAX_REQUESTS = 30  # 윈도우당 최대 요청 수
    RATE_LIMIT_WINDOW_SECONDS = 60  # 윈도우 크기 (초)
    RATE_LIMIT_CLEANUP_INTERVAL = 300  # 클린업 간격 (초)

    @classmethod
    def get_allowed_origins(cls) -> list:
        """허용된 origin 목록 반환"""
        if cls.DEV_MODE:
            return ["*"]
        return cls.ALLOWED_ORIGINS

# 한국 시간대
KST = pytz.timezone('Asia/Seoul')


# ===========================================
# 공휴일 목록 (2024-2026)
# ===========================================
HOLIDAYS = {
    # 2024년
    date(2024, 1, 1),    # 신정
    date(2024, 2, 9),    # 설날 연휴
    date(2024, 2, 10),   # 설날
    date(2024, 2, 11),   # 설날 연휴
    date(2024, 2, 12),   # 대체공휴일
    date(2024, 3, 1),    # 삼일절
    date(2024, 4, 10),   # 국회의원선거일
    date(2024, 5, 5),    # 어린이날
    date(2024, 5, 6),    # 대체공휴일
    date(2024, 5, 15),   # 부처님오신날
    date(2024, 6, 6),    # 현충일
    date(2024, 8, 15),   # 광복절
    date(2024, 9, 16),   # 추석 연휴
    date(2024, 9, 17),   # 추석
    date(2024, 9, 18),   # 추석 연휴
    date(2024, 10, 3),   # 개천절
    date(2024, 10, 9),   # 한글날
    date(2024, 12, 25),  # 성탄절
    date(2024, 12, 31),  # 연말 휴장
    # 2025년
    date(2025, 1, 1),    # 신정
    date(2025, 1, 28),   # 설날 연휴
    date(2025, 1, 29),   # 설날
    date(2025, 1, 30),   # 설날 연휴
    date(2025, 3, 1),    # 삼일절
    date(2025, 3, 3),    # 대체공휴일
    date(2025, 5, 5),    # 어린이날
    date(2025, 5, 6),    # 부처님오신날
    date(2025, 6, 6),    # 현충일
    date(2025, 8, 15),   # 광복절
    date(2025, 10, 3),   # 개천절
    date(2025, 10, 5),   # 추석 연휴
    date(2025, 10, 6),   # 추석
    date(2025, 10, 7),   # 추석 연휴
    date(2025, 10, 8),   # 대체공휴일
    date(2025, 10, 9),   # 한글날
    date(2025, 12, 25),  # 성탄절
    # 2026년
    date(2026, 1, 1),    # 신정
    date(2026, 2, 16),   # 설날 연휴
    date(2026, 2, 17),   # 설날
    date(2026, 2, 18),   # 설날 연휴
    date(2026, 3, 1),    # 삼일절
    date(2026, 3, 2),    # 대체공휴일
    date(2026, 5, 5),    # 어린이날
    date(2026, 5, 24),   # 부처님오신날
    date(2026, 5, 25),   # 대체공휴일
    date(2026, 6, 6),    # 현충일
    date(2026, 8, 15),   # 광복절
    date(2026, 8, 17),   # 대체공휴일
    date(2026, 9, 24),   # 추석 연휴
    date(2026, 9, 25),   # 추석
    date(2026, 9, 26),   # 추석 연휴
    date(2026, 10, 3),   # 개천절
    date(2026, 10, 5),   # 대체공휴일
    date(2026, 10, 9),   # 한글날
    date(2026, 12, 25),  # 성탄절
}


def is_holiday(check_date: date = None) -> bool:
    """공휴일 여부 확인"""
    if check_date is None:
        check_date = datetime.now(KST).date()
    return check_date in HOLIDAYS


# 공휴일 목록 연도 커버리지 확인
_holiday_years = {d.year for d in HOLIDAYS}
_current_year = datetime.now(KST).year
if _current_year not in _holiday_years:
    _config_logger.warning(
        f"공휴일 목록에 {_current_year}년 데이터가 없습니다. "
        f"공휴일 체크가 정상 작동하지 않을 수 있습니다. "
        f"config.py의 HOLIDAYS를 업데이트해주세요."
    )


def get_market_status() -> str:
    """
    현재 장 상태 반환
    - CLOSED: 완전 휴장 (주말, 공휴일, 18:00~08:30)
    - PRE_MARKET: 동시호가 (08:30~09:00)
    - REGULAR: 정규장 (09:00~15:30)
    - AFTER_HOURS: 시간외 거래 (15:40~18:00)
    """
    # UTC에서 명시적으로 KST로 변환 (서버 타임존 무관하게 동작)
    from datetime import timezone
    now = datetime.now(timezone.utc).astimezone(KST)
    today = now.date()

    # 주말 체크
    if now.weekday() >= 5:
        return "CLOSED"

    # 공휴일 체크
    if is_holiday(today):
        return "CLOSED"

    hour = now.hour
    minute = now.minute
    time_val = hour * 60 + minute  # 분 단위로 변환

    # 시간대별 상태
    if time_val < 8 * 60 + 30:  # ~08:30
        return "CLOSED"
    elif time_val < 9 * 60:  # 08:30~09:00
        return "PRE_MARKET"
    elif time_val < 15 * 60 + 30:  # 09:00~15:30
        return "REGULAR"
    elif time_val < 15 * 60 + 40:  # 15:30~15:40 (휴식)
        return "CLOSED"
    elif time_val < 18 * 60:  # 15:40~18:00
        return "AFTER_HOURS"
    else:  # 18:00~
        return "CLOSED"


def is_market_closed() -> bool:
    """장이 완전히 닫혀있는지 (거래 불가)"""
    return get_market_status() == "CLOSED"


def is_market_open() -> bool:
    """정규장이 열려있는지"""
    return get_market_status() == "REGULAR"


def is_trading_available() -> bool:
    """거래 가능 시간인지 (정규장 + 시간외)"""
    status = get_market_status()
    return status in ["REGULAR", "AFTER_HOURS", "PRE_MARKET"]


def get_market_status_message() -> str:
    """현재 장 상태 메시지"""
    status = get_market_status()
    from datetime import timezone
    now = datetime.now(timezone.utc).astimezone(KST)
    today = now.date()

    if status == "CLOSED":
        if now.weekday() >= 5:
            return "🔴 휴장 (주말)"
        elif is_holiday(today):
            return "🔴 휴장 (공휴일)"
        elif now.hour < 8 or (now.hour == 8 and now.minute < 30):
            return "🔴 휴장 (장 시작 전)"
        else:
            return "🔴 휴장 (장 마감)"
    elif status == "PRE_MARKET":
        return "🟡 동시호가 (08:30~09:00)"
    elif status == "REGULAR":
        return "🟢 정규장 (09:00~15:30)"
    elif status == "AFTER_HOURS":
        return "🟠 시간외 거래 (15:40~18:00)"
    return "알 수 없음"

# ===========================================
# 데이터베이스 설정
# ===========================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./stock_king.db"  # 로컬 개발용 SQLite
)

# Railway PostgreSQL은 postgres:// 로 시작하는데, 
# SQLAlchemy는 postgresql:// 필요
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# ===========================================
# 한국투자증권 KIS API 설정
# ===========================================
class KISConfig:
    APP_KEY = os.getenv("KIS_APP_KEY", "")
    APP_SECRET = os.getenv("KIS_APP_SECRET", "")
    BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
    API_TIMEOUT = 10  # API 요청 타임아웃 (초)

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.APP_KEY and cls.APP_SECRET)


# ===========================================
# 게임 설정
# ===========================================
class GameConfig:
    # 초기 자금
    INITIAL_CASH = 5_000_000  # 500만원

    # 출석 보상
    ATTENDANCE_REWARD = 300_000  # 30만원
    ATTENDANCE_STREAK_BONUS = {
        3: 1.2,    # 3일 연속: 20% 보너스
        5: 1.5,    # 5일 연속: 50% 보너스
        7: 2.0,    # 7일 연속: 100% 보너스 (최대 60만원)
    }

    # 광고 보상 (비활성화 - 수익 발생 방지)
    # AD_REWARD = 500_000  # 50만원
    # MAX_ADS_PER_DAY = 3  # 하루 최대 3회
    AD_DISABLED = True  # 광고 기능 비활성화

    # 거래 수수료
    TRADE_FEE_RATE = 0.001  # 0.1%

    # 최소 거래 단위
    MIN_TRADE_AMOUNT = 1  # 최소 1주

    # 일간 미션
    DAILY_MISSION_TRADE_COUNT = 3  # 3번 거래 미션
    DAILY_MISSION_REWARD = 200_000  # 20만원

    # 주간 보너스 (특정 요일)
    WEEKLY_BONUS_DAY = 0  # 월요일 (0=월, 6=일)
    WEEKLY_BONUS_MULTIPLIER = 2.0  # 2배 보너스

    # 미니게임/배팅 설정
    MIN_BET = 10_000  # 최소 배팅금 1만원
    MAX_BET = 999_999_999_999  # 최대 배팅금 9999억 9999만 9999원
    DEFAULT_BET = 50_000  # 기본 배팅금 5만원
    BIG_BET = 500_000  # 큰 배팅금 50만원 (게임 메뉴용)
    DEFAULT_BATTLE_BET = 100_000  # 배틀 기본 배팅금 10만원
    LOTTERY_COST = 10_000  # 복권 가격
    MAX_LOTTERY_PER_DAY = 5  # 복권 1일 최대 횟수

    # 거래 설정
    MAX_QUANTITY = 1_000_000  # 1회 최대 거래 수량
    MAX_CASH = 10_000_000_000_000  # 최대 현금 10조 (오버플로우 방지)

    # 검색 제한 (카카오톡 메시지 1000자 제한 고려, KIS API 최대 10개 반환)
    MAX_SEARCH_LIMIT = 20  # 검색 결과 최대 개수


# ===========================================
# 게임 확률 설정 (기대값 검증 포함)
# ===========================================
class GameProbability:
    """
    게임 확률 상수 (기대값 검증 포함)

    모든 확률은 합이 1.0이어야 하며,
    기대값(EV)은 합리적인 범위 내에 있어야 합니다.
    """

    # 복권 확률 (기대값 약 90%)
    # 각 티어: (확률, 최소보상, 최대보상)
    LOTTERY = {
        "1등": {"prob": 0.002, "min_reward": 500_000, "max_reward": 1_000_000},  # 0.2%
        "2등": {"prob": 0.018, "min_reward": 50_000, "max_reward": 100_000},     # 1.8%
        "3등": {"prob": 0.05, "min_reward": 15_000, "max_reward": 30_000},       # 5%
        "4등": {"prob": 0.10, "min_reward": 8_000, "max_reward": 12_000},        # 10%
        "5등": {"prob": 0.30, "min_reward": 10_000, "max_reward": 10_000},       # 30% (본전)
        "꽝": {"prob": 0.53, "min_reward": 0, "max_reward": 1_000},              # 53%
    }

    # 슬롯머신 확률
    SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "🚀"]

    # (심볼, 배수, 확률)
    SLOT_PAYOUTS = [
        ("7️⃣", 50, 0.0005),   # 0.05% - 잭팟 (희귀)
        ("💎", 20, 0.0015),    # 0.15% (희귀)
        ("🚀", 10, 0.003),     # 0.3% (희귀)
        ("🍇", 5, 0.012),      # 1.2%
        ("🍊", 3, 0.025),      # 2.5%
        ("🍋", 2, 0.0575),     # 5.75%
        ("🍒", 1.5, 0.10),     # 10%
        ("MATCH2", 1, 0.35),   # 35% - 2개 일치 (본전)
        ("LOSE", 0, 0.4505),   # 45.05% - 꽝
    ]

    # 룰렛 확률 (기대값 90%)
    ROULETTE = {
        "빨강": {"prob": 0.45, "multiplier": 2},
        "검정": {"prob": 0.45, "multiplier": 2},
        "초록": {"prob": 0.10, "multiplier": 9},
    }

    # 하이로우 (기대값 90%)
    HIGHLOW_MULTIPLIER = 1.8  # 맞추면 1.8배

    # 동전던지기 (기대값 100%)
    COINFLIP_MULTIPLIER = 2.0  # 맞추면 2배

    @classmethod
    def validate_probabilities(cls) -> bool:
        """모든 확률이 유효한지 검증"""
        errors = []

        # 복권 확률 합계 검증
        lottery_sum = sum(tier["prob"] for tier in cls.LOTTERY.values())
        if not (0.999 <= lottery_sum <= 1.001):
            errors.append(f"복권 확률 합계 오류: {lottery_sum}")

        # 슬롯 확률 합계 검증
        slot_sum = sum(prob for _, _, prob in cls.SLOT_PAYOUTS)
        if not (0.999 <= slot_sum <= 1.001):
            errors.append(f"슬롯 확률 합계 오류: {slot_sum}")

        # 룰렛 확률 합계 검증
        roulette_sum = sum(color["prob"] for color in cls.ROULETTE.values())
        if not (0.999 <= roulette_sum <= 1.001):
            errors.append(f"룰렛 확률 합계 오류: {roulette_sum}")

        if errors:
            for error in errors:
                _config_logger.warning(f"확률 검증 실패: {error}")
            return False

        _config_logger.debug("게임 확률 검증 완료")
        return True

    @classmethod
    def calculate_expected_value(cls, game: str) -> float:
        """게임별 기대값 계산"""
        if game == "lottery":
            # 복권 기대값 (10,000원 기준)
            cost = GameConfig.LOTTERY_COST
            ev = 0
            for tier in cls.LOTTERY.values():
                avg_reward = (tier["min_reward"] + tier["max_reward"]) / 2
                ev += tier["prob"] * avg_reward
            return (ev / cost) * 100  # % 반환

        elif game == "slot":
            # 슬롯 기대값
            ev = sum(mult * prob for _, mult, prob in cls.SLOT_PAYOUTS)
            return ev * 100  # % 반환

        elif game == "roulette":
            # 룰렛 기대값
            ev = sum(color["prob"] * color["multiplier"] for color in cls.ROULETTE.values())
            return ev * 100  # % 반환

        elif game == "highlow":
            # 하이로우 기대값 (50은 무승부)
            # P(win) = 49/99 (1-49 또는 51-100), P(draw) = 1/100
            p_win = 49 / 100
            return p_win * cls.HIGHLOW_MULTIPLIER * 100

        elif game == "coinflip":
            # 동전던지기 기대값
            return 0.5 * cls.COINFLIP_MULTIPLIER * 100

        return 0


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
        errors.append(f"MAX_BET({GameConfig.MAX_BET})는 MIN_BET({GameConfig.MIN_BET})보다 커야 합니다")
    if GameConfig.INITIAL_CASH <= 0:
        errors.append(f"INITIAL_CASH는 양수여야 합니다: {GameConfig.INITIAL_CASH}")
    if not (0 <= GameConfig.TRADE_FEE_RATE <= 0.1):
        errors.append(f"TRADE_FEE_RATE는 0~10% 범위여야 합니다: {GameConfig.TRADE_FEE_RATE}")

    # 4. 게임 확률 검증
    if not GameProbability.validate_probabilities():
        errors.append("게임 확률 설정 오류 - 확률 합계가 1이 아닙니다")

    # 5. 기대값 검증 (과도하게 높거나 낮은 경우 경고)
    for game in ["lottery", "slot", "roulette", "highlow", "coinflip"]:
        ev = GameProbability.calculate_expected_value(game)
        if ev > 150:
            warnings.append(f"{game} 기대값이 너무 높음: {ev:.1f}%")
        elif ev < 50:
            warnings.append(f"{game} 기대값이 너무 낮음: {ev:.1f}%")

    # 로그 출력
    for warning in warnings:
        _config_logger.warning(f"설정 경고: {warning}")
    for error in errors:
        _config_logger.error(f"설정 오류: {error}")

    is_valid = len(errors) == 0

    if is_valid:
        _config_logger.info("설정 검증 완료 - 모든 필수 설정 확인됨")

    return is_valid, errors


# ===========================================
# 응답 메시지
# ===========================================
class Messages:
    WELCOME = """🎮 주식왕 시작!

💰 {initial_cash:,}원 지급 완료!

버튼 눌러서 바로 투자 시작하세요 👇"""

    HELP = """📖 주식왕 명령어

📊 주식 거래
/시세 [종목] - 시세 조회 (/ㅅㅅ)
/매수 [종목] [수량] - 매수 (/ㅁㅅ)
/매도 [종목] [수량] - 매도 (/ㅁㄷ)
/전량매수 [종목] - 올인 매수 (/ㅈㅁㅅ)
/전량매도 [종목] - 전량 매도 (/ㅈㅁㄷ)

🔍 종목 탐색
/급등 - 급등주 TOP 10 (/ㄱㄷ)
/급락 - 급락주 TOP 10
/인기 - 거래량 TOP 10 (/ㅇㄱ)
/검색 [키워드] - 종목 검색 (/ㄱㅅ)
/뉴스 [종목] - 관련 뉴스 (/ㄴㅅ)
/시장 - 시장 현황 (KOSPI/KOSDAQ)

💰 내 자산
/잔고 - 보유 현금 (/ㅈㄱ)
/포트폴리오 - 내 자산 현황 (/포폴)
/차트 - 자산 변동 그래프

💵 무료 보상
/출석 - 매일 +30만원 (/ㅊㅅ)
/복권 - 1만원 복권 1일5회 (/ㅂㄱ)

🎰 미니게임 (장 마감 후)
/게임 - 전체 게임 목록
/슬롯머신 [금액] (/ㅅㄹㅁ)
/동전 [금액] [앞/뒤] (/ㄷㅈ)
/룰렛 [금액] [빨강/검정] (/ㄹㄹ)
/하이로우 [금액] [높/낮] (/ㅎㅇㄹㅇ)

🏆 경쟁
/랭킹 - 수익률 TOP 10 (/ㄹㅋ)
/내순위 - 내 순위 확인 (/ㄴㅅㅇ)
/닉네임 [이름] - 닉네임 변경"""

    ALREADY_REGISTERED = "이미 주식왕에 가입되어 있습니다!"

    ATTENDANCE_SUCCESS = """✅ 출석 완료!

💰 +{reward:,}원 지급!
🔥 연속 출석: {streak}일

현재 잔고: {cash:,}원"""

    ATTENDANCE_ALREADY = """⚠️ 오늘은 이미 출석했습니다!

내일 다시 출석해주세요.
🔥 현재 연속 출석: {streak}일"""

    STOCK_PRICE = """📊 {name} ({code})

💵 현재가: {price:,}원
📈 전일대비: {change:+.2f}%
📉 저가: {low:,}원 / 고가: {high:,}원
📊 거래량: {volume:,}주"""

    STOCK_NOT_FOUND = "❌ '{query}' 종목을 찾을 수 없습니다."

    BUY_SUCCESS = """✅ 매수 완료!

📈 {name} {quantity:,}주
💵 체결가: {price:,}원
💰 총 금액: {total:,}원
📍 수수료: -{fee:,}원

잔여 현금: {cash:,}원"""

    SELL_SUCCESS = """✅ 매도 완료!

📉 {name} {quantity:,}주
💵 체결가: {price:,}원
💰 총 금액: {total:,}원
📍 수수료: -{fee:,}원
{profit_text}

잔여 현금: {cash:,}원"""

    NOT_ENOUGH_CASH = """❌ 잔고가 부족합니다!

필요 금액: {required:,}원
보유 현금: {cash:,}원
부족 금액: {shortage:,}원"""

    NOT_ENOUGH_STOCK = """❌ 보유 수량이 부족합니다!

매도 요청: {requested:,}주
보유 수량: {holding:,}주"""

    BALANCE = """💰 내 잔고

현금: {cash:,}원"""

    PORTFOLIO = """💼 내 포트폴리오

💰 보유 현금: {cash:,}원

📈 보유 주식
{holdings}

📊 총 자산: {total:,}원
📈 총 수익률: {profit_rate:+.2f}%"""

    RANKING = """🏆 수익률 랭킹 TOP 10

{ranking_list}"""

    MY_RANK = """📍 내 순위

🏆 {rank}위 / 전체 {total}명
📈 수익률: {profit_rate:+.2f}%
💰 총 자산: {total_asset:,}원"""

    ERROR = "❌ 오류가 발생했습니다. 다시 시도해주세요."
    UNKNOWN_COMMAND = """❓ 알 수 없는 명령어입니다.

/도움말 을 입력하여 명령어를 확인하세요."""

    # 공통 에러 메시지
    USER_NOT_FOUND = "먼저 /시작 으로 게임을 시작해주세요."

    MARKET_CLOSED_TRADING = """🚫 현재 거래 불가능한 시간입니다.

{status_msg}

⏰ 거래 가능 시간:
• 동시호가: 08:30~09:00
• 정규장: 09:00~15:30
• 시간외: 15:40~18:00"""

    MARKET_CLOSED_GAME = """미니게임은 장 마감 후에만 가능해요!

{status_msg}

🎮 게임 가능 시간:
• 평일 18:00 이후
• 평일 08:30 이전
• 주말/공휴일 종일"""

    INSUFFICIENT_BALANCE_GAME = "잔액 부족! (보유: {cash:,}원, 필요: {bet:,}원)"

    MIN_TRADE_AMOUNT_ERROR = "최소 {min_amount}주 이상 거래해야 합니다."

    STOCK_PRICE_FAIL = "'{name}' 시세 조회 실패. 잠시 후 다시 시도해주세요."
