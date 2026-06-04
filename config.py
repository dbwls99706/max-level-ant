"""
만렙개미 봇 설정 파일
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
    # 운영 환경에서는 반드시 ADMIN_TOKEN 환경변수를 설정해야 합니다.
    _admin_token = os.getenv("ADMIN_TOKEN")
    _dev_mode_check = os.getenv("DEV_MODE", "false").lower() == "true"
    if not _admin_token:
        _admin_token = secrets.token_urlsafe(32)
        if not _dev_mode_check:
            _config_logger.error(
                "⚠️  ADMIN_TOKEN 환경변수가 설정되지 않았습니다! "
                "운영 환경에서는 반드시 ADMIN_TOKEN을 설정하세요. "
                "임시 토큰이 생성되었으나 서버 재시작 시 변경됩니다."
            )
        else:
            _config_logger.warning(
                "ADMIN_TOKEN 미설정 (DEV_MODE): 임시 토큰 사용 중"
            )
    ADMIN_TOKEN = _admin_token

    # 요청 본문 최대 크기 (10KB) - DoS 방지
    MAX_REQUEST_SIZE = 10 * 1024  # 10KB

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

    # 급등/급락 순위에서 제외할 종목 키워드 (레버리지/인버스 ETF 등)
    # 이름에 아래 키워드가 포함된 종목은 개별 종목 급등/급락 순위에 노출하지 않는다.
    # 레버리지/인버스 상품은 지수의 2배로 움직여 등락률 상·하위를 독식하므로 제외한다.
    RANKING_EXCLUDE_KEYWORDS = ("레버리지", "인버스", "2X", "2x", "곱버스")

    # ETF/ETN 식별용 브랜드 접두사
    # 종목명이 아래 브랜드로 시작하면 ETF로 분류한다 (예: "KODEX 200", "TIGER 미국S&P500").
    # 개별 종목 급등/급락에서는 제외하고, ETF 전용 급등/급락(/ETF급등 등)에서만 노출한다.
    # ETN은 종목명에 "ETN"이 포함되는 특성으로 별도 판별한다.
    ETF_BRAND_PREFIXES = (
        "KODEX", "TIGER", "RISE", "KBSTAR", "SOL", "ACE", "KINDEX",
        "PLUS", "ARIRANG", "HANARO", "KOSEF", "TIMEFOLIO", "FOCUS",
        "TREX", "KIWOOM", "히어로즈", "WOORI", "BNK", "1Q", "VITA",
        "마이다스", "파워", "마이티", "KCGI", "WON",
    )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.APP_KEY and cls.APP_SECRET)


# ===========================================
# 게임 설정
# ===========================================
class GameConfig:
    # 초기 자금
    INITIAL_CASH = 10_000_000  # 1000만원

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

    # 예측게임/투자 설정
    MIN_BET = 10_000  # 최소 투자금 1만원
    MAX_BET = 999_999_999_999  # 최대 투자금 9999억 9999만 9999원
    DEFAULT_BET = 50_000  # 기본 투자금 5만원
    BIG_BET = 500_000  # 큰 투자금 50만원 (게임 메뉴용)
    DEFAULT_BATTLE_BET = 100_000  # 배틀 기본 투자금 10만원
    LOTTERY_COST = 0  # 복권 가격 (무료)
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

    # 보물상자 희귀도 확률 (전설→빈상자 순, 기대값 ~100%)
    # 확률 조정: 전설 최소 인상, 영웅·희귀·고급 순차 인상, 일반·빈상자 소폭 감소
    LOTTERY = {
        "전설":   {"prob": 0.003, "min_reward": 500_000, "max_reward": 1_000_000},  # 0.3%
        "영웅":   {"prob": 0.025, "min_reward": 50_000,  "max_reward": 100_000},    # 2.5%
        "희귀":   {"prob": 0.070, "min_reward": 15_000,  "max_reward": 30_000},     # 7.0%
        "고급":   {"prob": 0.120, "min_reward": 12_000,  "max_reward": 20_000},     # 12.0%
        "일반":   {"prob": 0.470, "min_reward": 3_000,   "max_reward": 8_000},      # 47.0%
        "빈 상자":{"prob": 0.312, "min_reward": 0,       "max_reward": 0},          # 31.2%
    }

    # 시장예측 (역사 퀴즈) — 상승/하락 맞추면 x2 (기대값: 지식 의존)
    STOCK_QUIZ_MULTIPLIER = 2.0

    # 역사 퀴즈 데이터 — 실제 한국 주식 역사 기반
    # answer: "상승" 또는 "하락"
    HISTORICAL_STOCK_DATA = [
        # === 삼성전자 (005930) ===
        {"stock_name": "삼성전자", "period": "2017년 1월 ~ 2018년 1월", "answer": "상승",
         "description": "반도체 슈퍼사이클로 메모리 수요 폭발"},
        {"stock_name": "삼성전자", "period": "2018년 1월 ~ 2019년 1월", "answer": "하락",
         "description": "메모리 반도체 가격 하락 사이클 진입"},
        {"stock_name": "삼성전자", "period": "2020년 3월 ~ 2021년 1월", "answer": "상승",
         "description": "코로나 이후 반도체 수요 급증, 언택트 호황"},
        {"stock_name": "삼성전자", "period": "2021년 1월 ~ 2022년 1월", "answer": "하락",
         "description": "글로벌 공급망 혼란과 금리 인상 우려"},
        {"stock_name": "삼성전자", "period": "2022년 1월 ~ 2023년 1월", "answer": "하락",
         "description": "메모리 다운사이클, 글로벌 IT 투자 위축"},
        {"stock_name": "삼성전자", "period": "2023년 1월 ~ 2024년 1월", "answer": "상승",
         "description": "AI 반도체 기대감, HBM 수요 증가"},

        # === SK하이닉스 (000660) ===
        {"stock_name": "SK하이닉스", "period": "2017년 1월 ~ 2018년 1월", "answer": "상승",
         "description": "메모리 호황, DRAM 가격 급등"},
        {"stock_name": "SK하이닉스", "period": "2018년 6월 ~ 2019년 6월", "answer": "하락",
         "description": "반도체 다운사이클, 재고 증가"},
        {"stock_name": "SK하이닉스", "period": "2020년 3월 ~ 2021년 3월", "answer": "상승",
         "description": "코로나 저점 반등, 서버 메모리 수요 증가"},
        {"stock_name": "SK하이닉스", "period": "2021년 6월 ~ 2022년 6월", "answer": "하락",
         "description": "메모리 업황 둔화, 금리 인상 공포"},
        {"stock_name": "SK하이닉스", "period": "2023년 1월 ~ 2024년 1월", "answer": "상승",
         "description": "AI 열풍, HBM3 독점 공급 기대"},

        # === 네이버 (035420) ===
        {"stock_name": "네이버", "period": "2020년 3월 ~ 2021년 3월", "answer": "상승",
         "description": "코로나로 온라인 커머스/광고 폭발 성장"},
        {"stock_name": "네이버", "period": "2021년 7월 ~ 2022년 7월", "answer": "하락",
         "description": "기술주 밸류에이션 조정, 금리 인상"},
        {"stock_name": "네이버", "period": "2019년 1월 ~ 2020년 1월", "answer": "상승",
         "description": "커머스 사업 확대, 라인 실적 개선"},

        # === 카카오 (035720) ===
        {"stock_name": "카카오", "period": "2020년 3월 ~ 2021년 6월", "answer": "상승",
         "description": "언택트 수혜, 카카오뱅크/카카오페이 상장 기대"},
        {"stock_name": "카카오", "period": "2021년 6월 ~ 2022년 6월", "answer": "하락",
         "description": "사업 다각화 관련 규제 이슈, 기술주 약세"},
        {"stock_name": "카카오", "period": "2022년 10월 ~ 2023년 3월", "answer": "하락",
         "description": "카카오 데이터센터 화재, SM엔터 인수전 혼란"},

        # === 현대자동차 (005380) ===
        {"stock_name": "현대자동차", "period": "2018년 1월 ~ 2019년 1월", "answer": "하락",
         "description": "중국 시장 부진, SUV 트렌드 늦은 대응"},
        {"stock_name": "현대자동차", "period": "2020년 3월 ~ 2021년 1월", "answer": "상승",
         "description": "전기차 전환 기대, 애플카 협력 루머"},
        {"stock_name": "현대자동차", "period": "2022년 1월 ~ 2023년 1월", "answer": "상승",
         "description": "미국 IRA법 수혜, 전기차 판매 호조"},

        # === 셀트리온 (068270) ===
        {"stock_name": "셀트리온", "period": "2017년 1월 ~ 2018년 1월", "answer": "상승",
         "description": "바이오시밀러 유럽 진출 성공, 개인 투자자 열풍"},
        {"stock_name": "셀트리온", "period": "2021년 1월 ~ 2022년 1월", "answer": "하락",
         "description": "바이오 업종 밸류에이션 조정, 합병 불확실성"},

        # === LG에너지솔루션 (373220) ===
        {"stock_name": "LG에너지솔루션", "period": "2022년 1월 ~ 2022년 12월", "answer": "하락",
         "description": "IPO 후 밸류에이션 부담, 원자재 가격 상승"},
        {"stock_name": "LG에너지솔루션", "period": "2023년 1월 ~ 2023년 7월", "answer": "상승",
         "description": "IRA 보조금 수혜, 북미 배터리 공장 수주"},

        # === LG화학 (051910) ===
        {"stock_name": "LG화학", "period": "2020년 1월 ~ 2021년 1월", "answer": "상승",
         "description": "전기차 배터리 분사 기대, 테슬라 공급"},
        {"stock_name": "LG화학", "period": "2021년 1월 ~ 2022년 6월", "answer": "하락",
         "description": "배터리 부문 분사 후 밸류에이션 재평가"},

        # === POSCO홀딩스 (005490) ===
        {"stock_name": "POSCO홀딩스", "period": "2020년 3월 ~ 2021년 5월", "answer": "상승",
         "description": "철강 가격 급등, 2차전지 소재 사업 부각"},
        {"stock_name": "POSCO홀딩스", "period": "2021년 5월 ~ 2022년 7월", "answer": "하락",
         "description": "철강 가격 하락, 글로벌 경기 둔화 우려"},
        {"stock_name": "POSCO홀딩스", "period": "2023년 1월 ~ 2023년 7월", "answer": "상승",
         "description": "리튬·니켈 등 2차전지 소재 밸류체인 기대"},

        # === 삼성SDI (006400) ===
        {"stock_name": "삼성SDI", "period": "2020년 3월 ~ 2021년 1월", "answer": "상승",
         "description": "전기차 배터리 수주 확대, ESS 시장 성장"},
        {"stock_name": "삼성SDI", "period": "2021년 11월 ~ 2022년 11월", "answer": "하락",
         "description": "2차전지주 밸류에이션 조정"},

        # === 기아 (000270) ===
        {"stock_name": "기아", "period": "2020년 6월 ~ 2021년 6월", "answer": "상승",
         "description": "EV6 출시 기대, 디자인 혁신 호평"},
        {"stock_name": "기아", "period": "2022년 1월 ~ 2023년 1월", "answer": "상승",
         "description": "미국 시장 판매 호조, 수익성 개선"},

        # === 삼성바이오로직스 (207940) ===
        {"stock_name": "삼성바이오로직스", "period": "2020년 1월 ~ 2020년 12월", "answer": "상승",
         "description": "코로나 백신·치료제 위탁생산(CMO) 수주"},
        {"stock_name": "삼성바이오로직스", "period": "2022년 1월 ~ 2022년 10월", "answer": "하락",
         "description": "바이오주 전반 약세, 금리 인상 부담"},

        # === 한화에어로스페이스 (012450) ===
        {"stock_name": "한화에어로스페이스", "period": "2022년 2월 ~ 2023년 2월", "answer": "상승",
         "description": "우크라이나 전쟁 이후 방산 수출 급증"},
        {"stock_name": "한화에어로스페이스", "period": "2020년 1월 ~ 2020년 12월", "answer": "하락",
         "description": "코로나 영향으로 항공 엔진 수요 급감"},

        # === 크래프톤 (259960) ===
        {"stock_name": "크래프톤", "period": "2021년 8월 ~ 2022년 8월", "answer": "하락",
         "description": "IPO 후 게임주 약세, 신작 부진 우려"},
        {"stock_name": "크래프톤", "period": "2023년 1월 ~ 2024년 1월", "answer": "상승",
         "description": "배틀그라운드 인도 재출시, 실적 개선"},
    ]

    # 업다운 멀티라운드 — 배율은 확률 기반으로 동적 계산
    # (EV 100%: 매 라운드 배율 = 1/확률)
    # 라운드 진행 수수료: 정보 우위를 상쇄하기 위한 배율 감소
    UPDOWN_ROUND_FEE = {
        # (시작 라운드, 끝 라운드): 배율 유지율
        (1, 3): 1.0,     # 1~3라운드: 수수료 없음 (신규 유저 체험)
        (4, 6): 0.95,    # 4~6라운드: 배율 5% 차감
        (7, 9): 0.90,    # 7~9라운드: 배율 10% 차감
        (10, 99): 0.85,  # 10라운드+: 배율 15% 차감
    }

    @classmethod
    def validate_probabilities(cls) -> bool:
        """모든 확률이 유효한지 검증"""
        errors = []

        # 복권 확률 합계 검증
        lottery_sum = sum(tier["prob"] for tier in cls.LOTTERY.values())
        if not (0.999 <= lottery_sum <= 1.001):
            errors.append(f"복권 확률 합계 오류: {lottery_sum}")

        # 역사 퀴즈 데이터 검증
        if len(cls.HISTORICAL_STOCK_DATA) < 10:
            errors.append(f"역사 퀴즈 데이터 부족: {len(cls.HISTORICAL_STOCK_DATA)}개")

        up_count = sum(1 for q in cls.HISTORICAL_STOCK_DATA if q["answer"] == "상승")
        down_count = len(cls.HISTORICAL_STOCK_DATA) - up_count
        if up_count == 0 or down_count == 0:
            errors.append("역사 퀴즈 데이터에 상승/하락이 균형적이지 않음")

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
            if GameConfig.LOTTERY_COST == 0:
                return 100.0
            cost = GameConfig.LOTTERY_COST
            ev = 0
            for tier in cls.LOTTERY.values():
                avg_reward = (tier["min_reward"] + tier["max_reward"]) / 2
                ev += tier["prob"] * avg_reward
            return (ev / cost) * 100

        elif game == "stock_quiz":
            # 역사 퀴즈 기대값 (지식 의존, 50% 기준)
            return 0.5 * cls.STOCK_QUIZ_MULTIPLIER * 100

        elif game == "updown":
            # 업다운 멀티라운드 - 매 라운드 EV = 100% (배율 = 1/확률)
            return 100.0

        return 0


# ===========================================
# 각성 시스템 설정 (던전 캐릭터 각성)
# ===========================================
class EnhanceConfig:
    """
    각성 시스템 — 던전 캐릭터 각성

    레벨이 오를수록 캐릭터가 진화하여
    출석/복권 보상이 증가합니다.
    실패 시 레벨이 0으로 초기화되어 긴장감이 극대화됩니다.
    장 마감 후에만 각성 시도가 가능합니다.
    """
    MAX_LEVEL = 20

    # 각성 비용: (현재 레벨 + 1) * BASE_COST
    BASE_COST = 100_000  # 10만원

    # 레벨별 성공 확률 (%) — 레벨 0→1 부터 19→20
    SUCCESS_RATES = [
        95, 90, 85, 80, 75,   # 0→1 ~ 4→5
        65, 60, 55, 50, 45,   # 5→6 ~ 9→10
        38, 32, 26, 22, 18,   # 10→11 ~ 14→15
        14, 11, 8, 6, 4,      # 15→16 ~ 19→20
    ]

    # 실패 시 레벨 0으로 초기화 (하드코어 모드)
    FAIL_RESET_TO_ZERO = True

    # 레벨별 성공 시 문구 (new_level 기준, 0→1 ~ 19→20)
    SUCCESS_FLAVORS = [
        "",                                                        # 미사용 (인덱스 0)
        "투자의 세계에 첫 발을 내딛었어요.",                               # → Lv.1
        "기초를 다졌어요. 투자 감각이 살아나고 있어요.",                      # → Lv.2
        "차트가 보이기 시작했어요. 모험가의 눈이 트이고 있어요.",              # → Lv.3
        "초보 딱지를 뗐어요. 진짜 투자자로 인정받았습니다.",                  # → Lv.4
        "여기까지 온 것만으로 이미 상위권 개미예요.",                       # → Lv.5
        "경고: 이제부터 실패 시 원점으로 초기화! 각오하세요.",               # → Lv.6
        "Lv.7의 험로를 통과했어요. 배짱이 두둑하시네요.",                   # → Lv.7
        "Lv.8 도달! 여기까지 오는 개미는 8명 중 1명뿐이에요.",             # → Lv.8
        "Lv.9 — 상위 10% 개미!",                                     # → Lv.9
        "두 자릿수 돌파! 진짜 투자 고수의 탄생입니다.",                     # → Lv.10
        "성공률 38% 관문 통과. 이건 근성으로만 됩니다.",                   # → Lv.11
        "Lv.12. 전설의 시작점에 서 있어요.",                            # → Lv.12
        "성공률 26% 돌파. 당신은 희귀한 개미예요.",                        # → Lv.13
        "Lv.14... 그랜드마스터 직전입니다.",                             # → Lv.14
        "성공률 18%를 뚫었습니다. 심장이 강한 개미예요.",                  # → Lv.15
        "14%를 뚫는 개미는 인간이 아니에요. 슈퍼개미 등극!",               # → Lv.16
        "11%... 역대급 개미가 나타났습니다!",                             # → Lv.17
        "성공률 8%를 뚫었어요. 전설의 개미로 기록됩니다.",                  # → Lv.18
        "6%의 기적. 당신은 이미 투자 레전드예요.",                        # → Lv.19
        "4%를 뚫고 만렙 달성! 당신을 넘을 개미는 없습니다.",               # → Lv.20
    ]

    # 레벨별 실패 시 문구 (시도 레벨 기준, 0→1 ~ 19→20)
    FAIL_FLAVORS = [
        "95%에서 넘어졌어요... 용사도 처음엔 슬라임에게 집니다.",            # Lv.0→1 실패
        "90% 확률의 벽... 주식 시장은 호락호락하지 않군요.",               # Lv.1→2 실패
        "85%에서 미끄러졌어요. 차트가 당신을 비웃고 있어요.",               # Lv.2→3 실패
        "80%도 됩니다... 오늘은 확률이 심술을 부렸네요.",                  # Lv.3→4 실패
        "75%에서 탈락. 조금만 더 버텨봐요.",                              # Lv.4→5 실패
        "65%... 중간 보스한테 막혔어요. 다시 돌격!",                      # Lv.5→6 실패
        "60%에서 패배. 검은 다음에도 예리할 거예요.",                      # Lv.6→7 실패
        "55%, 거의 반반의 싸움에서 졌어요. 재도전!",                      # Lv.7→8 실패
        "50%... 동전의 뒷면이 나왔어요. 짓궂네요.",                        # Lv.8→9 실패
        "45%... 두 자릿수 문 앞에서 주저앉았어요.",                       # Lv.9→10 실패
        "38% 관문에서 쓰러졌어요. 이 구간은 원래 어렵습니다.",              # Lv.10→11 실패
        "32%의 벽은 높았어요. 그래도 Lv.11까지 온 건 대단해요.",           # Lv.11→12 실패
        "26%... 포기가 정답인 개미가 더 많아요. 당신은 달라요.",            # Lv.12→13 실패
        "22%... 그랜드마스터 직전에서 쓰러졌어요. 아직 기회 있어요.",        # Lv.13→14 실패
        "18%... 실패가 당연한 확률이에요. 용사는 다시 일어납니다.",          # Lv.14→15 실패
        "14%의 도전에 쓰러졌어요. 이 배짱 자체가 전설입니다.",              # Lv.15→16 실패
        "11%에 도전한 것 자체를 존경합니다. 다시!",                       # Lv.16→17 실패
        "8%에 배팅한 용기에 박수! 전설은 실패를 먹고 자랍니다.",            # Lv.17→18 실패
        "6%... 레전드 직전에서 쓰러졌어요. 다시 달리세요!",                # Lv.18→19 실패
        "4%의 마지막 문 앞에서 쓰러졌어요. 여기까지 온 것 자체가 전설입니다.",          # Lv.19→20 실패
    ]

    # 보너스 비율 (레벨당)
    ATTENDANCE_BONUS_PER_LEVEL = 0.05   # 출석: 레벨당 +5% (레벨 20 = +100%)
    LOTTERY_BONUS_PER_LEVEL = 0.08      # 복권: 레벨당 +8% (레벨 20 = +160%)

    # 각성 단계 칭호 (레벨별 개별 후보군) — 개미 성장 RPG 테마
    # 각 레벨마다 후보 칭호 5개, 게임 중 랜덤 표시
    # 쪼렙 개미 → 동학개미 → 서학개미 → 슈퍼개미 → 만렙 개미 성장 루트
    TITLE_NAMES = {
        0:  [("쪼렙 개미", "🐜"), ("주린이 개미", "🔰"), ("새내기 개미", "🌱"), ("광장 구경 개미", "🐜"), ("알바비 개미", "💸")],
        1:  [("입문 개미", "📋"), ("호기심 개미", "🔍"), ("첫날 개미", "🌅"), ("스타트 개미", "🚀"), ("도전 개미", "💪")],
        2:  [("차트 입문 개미", "📊"), ("캔들 개미", "🕯️"), ("이평선 개미", "📈"), ("기초 분석 개미", "📖"), ("볼린저 개미", "🔢")],
        3:  [("국장 개미", "🇰🇷"), ("코스피 개미", "📉"), ("삼성전자 개미", "📱"), ("현대차 개미", "🚗"), ("네이버 개미", "🌐")],
        4:  [("동학개미 지망생", "⚔️"), ("국장 전사 개미", "🛡️"), ("코스닥 개미", "📊"), ("SK하이닉스 개미", "💾"), ("국내주 개미", "🏠")],
        5:  [("동학 개미", "🇰🇷"), ("왕십리 개미", "🗺️"), ("코스피 정예 개미", "⚔️"), ("코스닥 전사 개미", "🔥"), ("개인 투자 개미", "💼")],
        6:  [("서학개미 지망생", "✈️"), ("달러 환전 개미", "💵"), ("나스닥 입문 개미", "🌎"), ("해외주 개미", "🗺️"), ("테슬라 개미", "🚗")],
        7:  [("서학 개미", "🌎"), ("엔비디아 개미", "🖥️"), ("S&P500 개미", "📈"), ("애플 개미", "🍎"), ("나스닥 전사 개미", "⚔️")],
        8:  [("글로벌 개미", "🌐"), ("메타 개미", "📘"), ("아마존 개미", "📦"), ("구글 개미", "🔍"), ("해외 고수 개미", "🏆")],
        9:  [("포트폴리오 개미", "💼"), ("분산투자 개미", "⚖️"), ("리밸런싱 개미", "🔄"), ("전략 개미", "🧩"), ("글로벌 정예 개미", "🌟")],
        10: [("슈퍼개미 지망생", "🦸"), ("큰손 개미", "💰"), ("수익률 달인 개미", "📊"), ("주식 고수 개미", "🏅"), ("고수익 개미", "🔥")],
        11: [("알파 개미", "🦅"), ("팩터 개미", "⚗️"), ("퀀트 개미 견습", "🧮"), ("차트 마스터 개미", "📐"), ("수익 마법 개미", "🪄")],
        12: [("헤지 개미", "🛡️"), ("리스크 관리 개미", "⚖️"), ("손절 장인 개미", "✂️"), ("변동성 사냥 개미", "🌪️"), ("방어형 개미", "🏰")],
        13: [("퀀트 개미", "🤖"), ("알고리즘 개미", "💻"), ("시스템 매매 개미", "⚙️"), ("데이터 개미", "🧮"), ("모델 개미", "🔬")],
        14: [("전문가 개미", "🎓"), ("마켓 마스터 개미", "🌐"), ("차트 고수 개미", "📐"), ("수익률 챔피언 개미", "🏅"), ("기술 고수 개미", "🔧")],
        15: [("고인물 개미", "🌊"), ("전업 지망 개미", "💎"), ("본좌 개미", "👊"), ("마스터 개미", "🧪"), ("리딩 개미", "📡")],
        16: [("슈퍼개미", "⚡"), ("대주주 개미", "🏛️"), ("기관 사냥 개미", "🦅"), ("외인급 개미", "🌍"), ("전업 개미", "💼")],
        17: [("레전드 개미", "🌟"), ("시장 정복 개미", "🏹"), ("시장 파괴 개미", "⚔️"), ("그랜드마스터 개미", "💎"), ("전설의 개미", "🏆")],
        18: [("신화급 개미", "🏛️"), ("월드클래스 개미", "🌏"), ("버핏급 개미", "🎩"), ("피터린치급 개미", "📚"), ("투자의 神 개미", "⚡")],
        19: [("만렙 직전 개미", "✨"), ("4% 도전 개미", "🎯"), ("마지막 관문 개미", "🔮"), ("투자 레전드 개미", "💫"), ("초월 개미", "🌈")],
        20: [("만렙 개미", "👑"), ("진짜 슈퍼개미", "👑"), ("개미계의 왕", "👑"), ("개미들의 신", "👑"), ("동학·서학 초월 개미", "👑")],
    }

    @classmethod
    def get_cost(cls, current_level: int) -> int:
        """각성 비용 계산"""
        return (current_level + 1) * cls.BASE_COST

    @classmethod
    def get_success_rate(cls, current_level: int) -> int:
        """현재 레벨에서 각성 성공률 (%)"""
        if current_level >= cls.MAX_LEVEL:
            return 0
        if current_level < 0:
            return 95
        return cls.SUCCESS_RATES[current_level]

    @classmethod
    def get_fail_penalty(cls, current_level: int) -> tuple:
        """실패 시 페널티 — 항상 레벨 0으로 초기화"""
        if current_level <= 0:
            return 0, 0
        return 100, current_level  # 100% 확률로 현재 레벨만큼 하락 = 0으로

    # ===========================================
    # 직군 시스템 (레벨 10 이상 랜덤 배정)
    # - 레벨 9 → 10 각성 성공 시 3개 직군 중 하나가 자동 랜덤 배정됨
    # - 이후 직군에 해당하는 칭호 트리만 사용
    # - 각 직군은 레벨 10~19에서 레벨당 3개 고유 칭호 (직군 간 중복 없음)
    # - 레벨 20은 직군 무관 공통 만렙 칭호
    # ===========================================
    CLASS_LEVEL_THRESHOLD = 10  # 직군 배정 레벨

    CLASS_INFO = {
        1: {"name": "트레이더",  "emoji": "⚡",  "desc": "단타·스윙·기술분석의 달인 — 시장 흐름을 읽고 빠르게 치고 빠진다"},
        2: {"name": "투자가",   "emoji": "📜",  "desc": "가치투자·장기보유·펀더멘털 분석 — 기업의 본질 가치를 본다"},
        3: {"name": "퀀트",     "emoji": "🤖",  "desc": "알고리즘·데이터·시스템 매매 — 숫자와 논리로 알파를 창출한다"},
    }

    # 직군별 칭호: {직군_id: {레벨: [(칭호, 이모지), ...]}}
    # 규칙: 각 레벨당 3개, 직군 간 칭호 이름 중복 없음
    CLASS_TITLES = {
        1: {  # 트레이더 ──────────────────────────────
            10: [("주니어 딜러",        "📊"),  ("차트 분석사",       "📈"),  ("어시스턴트 트레이더","⚡")],
            11: [("딜러",               "💹"),  ("스캘핑 전문가",     "🔍"),  ("시니어 트레이더",   "🏹")],
            12: [("헤드 트레이더",      "🎯"),  ("스윙 마스터",       "📐"),  ("모멘텀 사냥꾼",     "🏆")],
            13: [("트레이딩 스페셜리스트","💎"),("시장 분석관",       "🧩"),  ("포지션 장인",       "🛡️")],
            14: [("프리미엄 트레이더",  "🌟"),  ("마켓 메이커",       "⚙️"),  ("알파 헌터",         "🦅")],
            15: [("트레이딩 마스터",    "🔥"),  ("딜링 전문가",       "💼"),  ("시장 예언자",       "🔮")],
            16: [("엘리트 트레이더",    "💫"),  ("마켓 위저드",       "🧙"),  ("트레이딩 레전드",   "✨")],
            17: [("그랜드 트레이더",    "🌠"),  ("시장의 지배자",     "👊"),  ("전설적 딜러",       "🌈")],
            18: [("트레이딩 신화",      "🏛️"), ("월가급 트레이더",   "💫"),  ("최강 트레이더",     "🌌")],
            19: [("트레이더의 왕",      "🎯"),  ("시장 초월 트레이더","⭐"),  ("트레이딩 신의 경지","🌸")],
        },
        2: {  # 투자가 ──────────────────────────────
            10: [("주니어 애널리스트",  "🔍"),  ("기업 분석사",       "📋"),  ("가치 평가사",       "⚖️")],
            11: [("애널리스트",         "📚"),  ("펀더멘털 탐색가",   "🧭"),  ("기업 가치 발굴사",  "🌱")],
            12: [("시니어 애널리스트",  "💡"),  ("가치 투자 전문가",  "🎓"),  ("기업 분석 전문가",  "📜")],
            13: [("리서치 헤드",        "🔬"),  ("투자 전략가",       "🧩"),  ("장기 투자 마스터",  "📖")],
            14: [("포트폴리오 매니저",  "💼"),  ("헤지펀드 PM",       "💎"),  ("투자 디렉터",       "🌟")],
            15: [("CIO 지망생",         "🏆"),  ("마스터 투자가",     "🎩"),  ("가치 투자의 대가",  "🏅")],
            16: [("투자 레전드",        "✨"),  ("그랜드 투자가",     "💫"),  ("투자 마에스트로",   "🌠")],
            17: [("시장의 현자",        "🧙"),  ("투자 신화",         "🏛️"), ("버핏 계열",          "🦁")],
            18: [("투자 그랜드마스터",  "🔮"),  ("역대급 투자가",     "🌌"),  ("투자의 전설",       "🌈")],
            19: [("투자가의 왕",        "🎯"),  ("시장 초월 투자가",  "⭐"),  ("투자 신의 경지",    "🌺")],
        },
        3: {  # 퀀트 ──────────────────────────────
            10: [("퀀트 견습생",        "🤖"),  ("데이터 마이너",     "🧮"),  ("알고리즘 탐험가",   "🧭")],
            11: [("팩터 분석가",        "⚗️"),  ("코드 투자자",       "💻"),  ("시스템 지망생",     "⚙️")],
            12: [("퀀트 전문가",        "🎓"),  ("알파 탐색자",       "🧩"),  ("리스크 모델러",     "⚖️")],
            13: [("퀀트 전략가",        "🔬"),  ("시스템 트레이더",   "⚙️"),  ("AI 투자자",         "🤖")],
            14: [("퀀트 디렉터",        "🌟"),  ("알파 엔지니어",     "⚡"),  ("모델 마스터",       "🔢")],
            15: [("퀀트 마스터",        "💎"),  ("알파 생성자",       "✨"),  ("시스템 신화",       "🏛️")],
            16: [("퀀트 그랜드마스터",  "💫"),  ("알고리즘 레전드",   "🌠"),  ("퀀트 초고수",       "🌈")],
            17: [("퀀트 신화",          "🔮"),  ("데이터의 지배자",   "📊"),  ("퀀트개미 신",       "🌌")],
            18: [("퀀트 역사를 쓰다",   "📜"),  ("알파 최강자",       "🏅"),  ("퀀트 초월자",       "💫")],
            19: [("퀀트의 왕",          "🎯"),  ("알고리즘 신의 경지","⭐"),  ("퀀트 초월 존재",    "🌻")],
        },
    }

    @classmethod
    def get_class_candidates(cls, level: int, enhance_class: int):
        """직군 칭호 후보 반환. 해당 레벨·직군 없으면 None."""
        class_data = cls.CLASS_TITLES.get(enhance_class)
        if class_data is None:
            return None
        return class_data.get(level)  # {레벨: 목록} 구조

    @classmethod
    def get_title(cls, level: int, seed: int = None, enhance_class: int = 0) -> tuple:
        """레벨에 해당하는 칭호와 이모지.
        - level >= CLASS_LEVEL_THRESHOLD && enhance_class 배정 시 직군 칭호 사용
        - seed 있으면 해당 인덱스(0~2)로 고정, 없으면 랜덤
        - level 20은 직군 무관 공통 만렙 칭호
        """
        import random
        level = max(0, min(level, cls.MAX_LEVEL))

        candidates = None
        # 레벨 20은 항상 공통 만렙 칭호
        if level < cls.MAX_LEVEL and level >= cls.CLASS_LEVEL_THRESHOLD and enhance_class:
            candidates = cls.get_class_candidates(level, enhance_class)

        if candidates is None:
            candidates = cls.TITLE_NAMES.get(level, [("투자자", "📊")])

        if seed is not None:
            return candidates[seed % len(candidates)]
        return random.choice(candidates)

    @classmethod
    def get_attendance_multiplier(cls, level: int) -> float:
        """출석 보상 배율"""
        return 1.0 + (level * cls.ATTENDANCE_BONUS_PER_LEVEL)

    @classmethod
    def get_lottery_multiplier(cls, level: int) -> float:
        """복권 보상 배율"""
        return 1.0 + (level * cls.LOTTERY_BONUS_PER_LEVEL)


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
    for game in ["lottery", "stock_quiz", "updown"]:
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
    WELCOME = """🐜 만렙개미에 오신 것을 환영합니다!

🪙 시작 골드: {initial_cash:,}원 지급!

쪼렙 개미에서 만렙 개미로 성장하세요 👇"""

    HELP = """🐜 만렙개미 도움말
실제 한국 주식 시세로 투자하며 골드를 모아
쪼렙 개미에서 만렙 개미로 성장하는 게임이에요!

아래에서 분야를 골라보세요 👇"""

    HELP_STOCK = """📊 주식 투자

/급등 · /급락 — 오늘의 급등·급락주
/인기 · /거래량 — 거래 상위 종목
/시세 [종목] — 실시간 시세·등락률
/뉴스 [종목] — 종목 최신 뉴스
/검색 [키워드] — 종목명·코드 검색
/시장 — 코스피·코스닥 현황

💵 매매
/매수 · /매도 [종목] [수량]
/전량매수 · /전량매도 [종목]

💡 단축: ㅅㅅ시세 ㅁㅅ매수 ㅁㄷ매도 ㄱㄷ급등"""

    HELP_ASSET = """💼 내 자산

/잔고 — 보유 현금·총자산 확인
/포트폴리오 — 보유 주식 현황·수익률
/차트 — 최근 매매 내역 차트
/거래내역 — 체결된 전체 거래 기록
/랭킹 — 수익률 순위 TOP 10
/내순위 — 내 순위 + 경쟁자 비교
/각성랭킹 — 각성 레벨 TOP 10
/닉네임 [이름] — 닉네임 변경"""

    HELP_GAME = """🧬 각성 · 게임 ⚠️ 장 마감 후만 가능

🎁 매일 무료
/출석 — +30만 골드 (각성 보너스)
/보물상자 — 하루 최대 5회

🧬 각성
/각성 — 레벨업 도전 (실패 시 Lv.0)
  └ Lv.10 달성 시 직군 배정
/능력 — 각성 레벨·직군 확인

🎮 예측
/시장예측 [금액] — 주가 예언 (2배!)
/업다운 [금액] — 연속 맞추기 (연승↑)

💡 단축: ㅊㅅ출석 ㅂㄱ보물상자 ㄱㅎ각성"""

    HELP_SOCIAL = """⚔️ 소셜

/배틀 [종목] [상승/하락] [금액]
  └ 다른 개미와 1:1 주가 예측 대결
/배틀목록 — 대기 중인 배틀 목록
/미션 — 오늘의 거래 미션·보상 확인
/업적 — 달성한 업적 모아보기
/챌린지 — 주간 수익률 챌린지
/마일스톤 — 자산 목표 달성 현황"""

    ALREADY_REGISTERED = "이미 참가 중입니다! 바로 시작 👇"

    ATTENDANCE_SUCCESS = """📅 출석 완료!

🪙 +{reward:,}원 획득!
🔥 연속 출석: {streak}일

현재 골드: {cash:,}원"""

    ATTENDANCE_ALREADY = """⚠️ 오늘 이미 출석했어요!

내일 다시 입장해주세요.
🔥 현재 연속 입장: {streak}일"""

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

남은 골드: {cash:,}원"""

    SELL_SUCCESS = """✅ 매도 완료!

📉 {name} {quantity:,}주
💵 체결가: {price:,}원
💰 총 금액: {total:,}원
📍 수수료: -{fee:,}원
{profit_text}

남은 골드: {cash:,}원"""

    NOT_ENOUGH_CASH = """❌ 골드가 부족합니다!

필요 골드: {required:,}원
보유 골드: {cash:,}원
부족 골드: {shortage:,}원"""

    NOT_ENOUGH_STOCK = """❌ 보유 수량이 부족합니다!

매도 요청: {requested:,}주
보유 수량: {holding:,}주"""

    BALANCE = """🪙 내 골드

현금: {cash:,}원"""

    PORTFOLIO = """💼 내 포트폴리오

🪙 보유 골드: {cash:,}원

📈 보유 종목
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
아래 버튼을 눌러 시작해보세요 👇"""

    # 공통 에러 메시지
    USER_NOT_FOUND = "먼저 /시작 으로 참가하세요."

    MARKET_CLOSED_TRADING = """🚫 주식 거래 시간이 아닙니다.

{status_msg}

⏰ 거래 가능 시간:
• 동시호가: 08:30~09:00
• 정규장: 09:00~15:30
• 시간외: 15:40~18:00"""

    MARKET_CLOSED_GAME = """예측 게임은 장 마감 후에만 가능합니다!

{status_msg}

⏰ 게임 가능 시간:
• 평일 18:00 이후
• 평일 08:30 이전
• 주말/공휴일 종일"""

    INSUFFICIENT_BALANCE_GAME = "골드 부족! (보유: {cash:,}원, 필요: {bet:,}원)"

    MIN_TRADE_AMOUNT_ERROR = "최소 {min_amount}주 이상 거래해야 합니다."

    STOCK_PRICE_FAIL = "'{name}' 시세 조회 실패. 잠시 후 다시 시도해주세요."
