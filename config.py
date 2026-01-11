"""
주식왕 봇 설정 파일
"""
import os
from dotenv import load_dotenv

load_dotenv()

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
# 게임 설정
# ===========================================
class GameConfig:
    # 초기 자금
    INITIAL_CASH = 10_000_000  # 1,000만원

    # 출석 보상
    ATTENDANCE_REWARD = 2_000_000  # 200만원
    ATTENDANCE_STREAK_BONUS = {
        3: 1.3,    # 3일 연속: 30% 보너스
        5: 1.5,    # 5일 연속: 50% 보너스
        7: 2.0,    # 7일 연속: 100% 보너스 (최대)
    }

    # 광고 보상
    AD_REWARD = 1_500_000  # 150만원
    MAX_ADS_PER_DAY = 3  # 하루 최대 3회

    # 거래 수수료
    TRADE_FEE_RATE = 0.001  # 0.1%

    # 최소 거래 단위
    MIN_TRADE_AMOUNT = 1  # 최소 1주

    # 일간 미션
    DAILY_MISSION_TRADE_COUNT = 3  # 3번 거래 미션
    DAILY_MISSION_REWARD = 1_000_000  # 100만원

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
    WELCOME = """🎮 주식왕에 오신 것을 환영합니다!

💰 초기 자금 {initial_cash:,}원이 지급되었습니다.

📌 기본 명령어
/출석 - 매일 {attendance:,}원 받기
/광고 - 광고 보고 {ad:,}원 받기 (1일 {max_ads}회)
/급등 - 오늘의 급등주 확인
/시세 [종목명] - 주식 시세 조회
/매수 [종목명] [수량] - 주식 매수
/매도 [종목명] [수량] - 주식 매도
/미션 - 일간 미션 확인
/도움말 - 전체 명령어"""

    HELP = """📖 주식왕 명령어 안내

💵 재화 획득
/출석 - 일일 출석 보상 (200만원)
/광고 - 광고 시청 보상 (150만원, 1일 3회)

📊 주식 거래
/시세 [종목명] - 시세 조회
/매수 [종목명] [수량] - 주식 매수
/매도 [종목명] [수량] - 주식 매도
/전량매수 [종목명] - 최대 매수
/전량매도 [종목명] - 전량 매도

📈 시장 정보
/시장 - KOSPI/KOSDAQ 지수
/급등 - 급등주 TOP 10
/급락 - 급락주 TOP 10
/인기 - 거래량 TOP 10
/검색 [키워드] - 종목 검색

💼 내 정보
/잔고 - 보유 현금
/포트폴리오 - 전체 자산
/거래내역 - 최근 거래

🎯 미션 & 업적
/미션 - 일간 미션 현황
/업적 - 업적 달성 현황

🏆 경쟁
/랭킹 - 수익률 TOP 10
/내순위 - 내 현재 순위"""

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
