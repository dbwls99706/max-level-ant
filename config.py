"""
주식왕 봇 설정 파일
"""
import os
from datetime import datetime, date
import pytz
from dotenv import load_dotenv

load_dotenv()

# 한국 시간대
KST = pytz.timezone('Asia/Seoul')


# ===========================================
# 공휴일 목록 (2024-2025)
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


def get_market_status() -> str:
    """
    현재 장 상태 반환
    - CLOSED: 완전 휴장 (주말, 공휴일, 18:00~08:30)
    - PRE_MARKET: 동시호가 (08:30~09:00)
    - REGULAR: 정규장 (09:00~15:30)
    - AFTER_HOURS: 시간외 거래 (15:40~18:00)
    """
    now = datetime.now(KST)
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
    now = datetime.now(KST)

    if status == "CLOSED":
        if now.weekday() >= 5:
            return "🔴 휴장 (주말)"
        elif is_holiday():
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


# ===========================================
# 캐시 설정
# ===========================================
class CacheConfig:
    # 주식 시세 캐시 시간 (초)
    STOCK_PRICE_TTL = 60  # 1분
    
    # 랭킹 캐시 시간 (초)
    RANKING_TTL = 300  # 5분


# ===========================================
# 응답 메시지
# ===========================================
class Messages:
    WELCOME = """🎮 주식왕 시작!

💰 {initial_cash:,}원 지급 완료!

버튼 눌러서 바로 투자 시작하세요 👇"""

    HELP = """📖 주식왕 명령어

📊 주식
/급등 - 급등주 TOP 10
/급락 - 급락주 TOP 10
/시세 [종목] - 시세 조회
/검색 [키워드] - 종목 검색
/뉴스 [종목] - 관련 뉴스
/포트폴리오 - 내 자산
/차트 - 자산 변동 차트

💵 보상
/출석 - +30만원 (연속보너스)
/복권 - 1만원 복권 (1일5회)

🎰 미니게임 (장 마감 후)
/게임 - 게임 목록
/슬롯머신 - 슬롯머신
/동전 - 동전던지기
/하이로우 - 숫자게임

⚔️ 배틀 (PvP)
/배틀설명 - 배틀 시스템 설명
/배틀 [종목] [상승/하락] - 대결 생성
/배틀참가 [ID] - 대결 참가
/배틀결과 [ID] - 결과 확인
/배틀목록 - 대기 중인 배틀

🎯 챌린지
/챌린지 - 주간 챌린지
/마일스톤 - 목표 달성 보상

🏆 경쟁
/랭킹 - TOP 10
/내순위 - 내 순위
/닉네임 [이름] - 닉네임 설정"""

    ALREADY_REGISTERED = "이미 주식왕에 가입되어 있습니다!"

    ATTENDANCE_SUCCESS = """✅ 출석 완료!

💰 +{reward:,}원 지급!
🔥 연속 출석: {streak}일

현재 잔고: {cash:,}원"""

    ATTENDANCE_ALREADY = """⚠️ 오늘은 이미 출석했습니다!

내일 다시 출석해주세요.
🔥 현재 연속 출석: {streak}일"""

    AD_SUCCESS = """📺 광고 시청 완료!

💰 +{reward:,}원 지급!
📍 오늘 남은 횟수: {remaining}회

현재 잔고: {cash:,}원"""

    AD_LIMIT = """⚠️ 오늘 광고 시청 횟수를 모두 사용했습니다!

내일 다시 시청해주세요.
(1일 최대 {max_ads}회)"""

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
📍 수수료: {fee:,}원

잔여 현금: {cash:,}원"""

    SELL_SUCCESS = """✅ 매도 완료!

📉 {name} {quantity:,}주
💵 체결가: {price:,}원
💰 총 금액: {total:,}원
📍 수수료: {fee:,}원
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
