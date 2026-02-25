"""
명령어 처리 핸들러 (리팩토링)
- 명령어 라우팅
- 각 기능별 핸들러 믹스인 사용
"""
from typing import Dict, Optional
from sqlalchemy.orm import Session

from services import UserService
from utils import KakaoResponse, get_streak_display, get_handler_logger
from config import GameConfig, Messages

from .base_handler import BaseHandlerMixin
from .trading_handler import TradingHandlerMixin
from .game_handler import GameHandlerMixin
from .market_handler import MarketHandlerMixin
from .social_handler import SocialHandlerMixin

logger = get_handler_logger()


# 명령어 라우팅 테이블 타입
CommandRoute = Dict[str, str]


class CommandHandler(
    TradingHandlerMixin,
    GameHandlerMixin,
    MarketHandlerMixin,
    SocialHandlerMixin,
    BaseHandlerMixin
):
    """
    명령어 처리 클래스

    각 기능별 핸들러 믹스인을 상속받아 사용합니다.
    - TradingHandlerMixin: 거래 관련 (매수, 매도, 포트폴리오)
    - GameHandlerMixin: 미니게임 (복권, 슬롯, 동전 등)
    - MarketHandlerMixin: 시장 정보 (급등주, 뉴스, 검색)
    - SocialHandlerMixin: 소셜/경쟁 (랭킹, 배틀, 챌린지)
    """

    # 명령어 -> 핸들러 메서드 이름 매핑
    COMMAND_ROUTES: CommandRoute = {
        # 기본 명령어
        "/시작": "handle_start",
        "/start": "handle_start",
        "/출석": "handle_attendance",
        "/ㅊㅅ": "handle_attendance",
        "/도움말": "handle_help",
        "/help": "handle_help",
        "/ㄷㅇㅁ": "handle_help",

        # 거래 관련
        "/시세": "handle_price",
        "/ㅅㅅ": "handle_price",
        "/매수": "handle_buy",
        "/ㅁㅅ": "handle_buy",
        "/매도": "handle_sell",
        "/ㅁㄷ": "handle_sell",
        "/전량매수": "handle_buy_max",
        "/ㅈㅁㅅ": "handle_buy_max",
        "/전량매도": "handle_sell_all",
        "/ㅈㅁㄷ": "handle_sell_all",
        "/잔고": "handle_balance",
        "/ㅈㄱ": "handle_balance",
        "/포트폴리오": "handle_portfolio",
        "/포폴": "handle_portfolio",
        "/ㅍㅍ": "handle_portfolio",
        "/거래내역": "handle_transactions",
        "/ㄱㄹ": "handle_transactions",

        # 시장 정보
        "/검색": "handle_search",
        "/ㄱㅅ": "handle_search",
        "/인기": "handle_top_trading_value",
        "/ㅇㄱ": "handle_top_trading_value",
        "/거래량": "handle_top_volume",
        "/급등": "handle_top_gainers",
        "/상승": "handle_top_gainers",
        "/ㄱㄷ": "handle_top_gainers",
        "/급락": "handle_top_losers",
        "/하락": "handle_top_losers",
        "/시장": "handle_market_overview",
        "/지수": "handle_market_overview",
        "/뉴스": "handle_news",
        "/ㄴㅅ": "handle_news",

        # 미니게임
        "/게임": "handle_game_menu",
        "/미니게임": "handle_game_menu",
        "/복권": "handle_lottery",
        "/ㅂㄱ": "handle_lottery",
        "/슬롯머신": "handle_slot",
        "/ㅅㄹㅁ": "handle_slot",
        "/동전": "handle_coin",
        "/코인": "handle_coin",
        "/ㄷㅈ": "handle_coin",
        "/하이로우": "handle_highlow",
        "/ㅎㅇㄹㅇ": "handle_highlow",
        "/룰렛": "handle_roulette",
        "/ㄹㄹ": "handle_roulette",

        # 소셜/경쟁
        "/랭킹": "handle_ranking",
        "/ㄹㅋ": "handle_ranking",
        "/내순위": "handle_my_rank",
        "/ㄴㅅㅇ": "handle_my_rank",
        "/미션": "handle_mission",
        "/업적": "handle_achievements",
        "/닉네임": "handle_nickname",
        "/ㄴㄴ": "handle_nickname",

        # 배틀
        "/배틀설명": "handle_battle_help",
        "/배틀생성": "handle_battle_create",
        "/배틀": "handle_battle_create",
        "/배틀참가": "handle_battle_join",
        "/배틀결과": "handle_battle_result",
        "/배틀목록": "handle_battle_list",
        "/대기배틀": "handle_battle_list",

        # 챌린지/마일스톤
        "/챌린지": "handle_challenge",
        "/주간": "handle_challenge",
        "/챌린지보상": "handle_challenge_reward",
        "/마일스톤": "handle_milestone",
        "/목표": "handle_milestone",
        "/마일스톤보상": "handle_milestone_reward",

        # 자산 차트
        "/차트": "handle_asset_chart",
        "/자산차트": "handle_asset_chart",
    }

    def __init__(self, db: Session, kakao_id: str, utterance: str, nickname: str = None):
        self.db = db
        self.kakao_id = kakao_id
        self.utterance = utterance.strip()
        self.nickname = nickname

    def handle(self) -> Dict:
        """
        명령어 처리 메인 함수
        라우팅 테이블을 사용하여 적절한 핸들러 호출
        """
        cmd = self.utterance.lower()

        # 빈 utterance = 웰컴 블록 트리거
        if not cmd:
            return self.handle_welcome()

        # 라우팅 테이블에서 핸들러 찾기
        handler_name = self._find_handler(cmd)

        if handler_name:
            handler_method = getattr(self, handler_name, None)
            if handler_method:
                logger.debug(f"명령어 '{cmd}' -> {handler_name}")
                return handler_method()

        # 알 수 없는 명령어
        return self.handle_unknown()

    # 명령어를 길이 내림차순으로 정렬 (긴 명령어 우선 매칭하여 prefix 충돌 방지)
    _SORTED_ROUTES = None

    @classmethod
    def _get_sorted_routes(cls):
        """정렬된 명령어 라우트 캐시"""
        if cls._SORTED_ROUTES is None:
            cls._SORTED_ROUTES = sorted(
                cls.COMMAND_ROUTES.items(),
                key=lambda x: len(x[0]),
                reverse=True
            )
        return cls._SORTED_ROUTES

    def _find_handler(self, cmd: str) -> Optional[str]:
        """
        명령어에 맞는 핸들러 이름 찾기
        긴 명령어부터 매칭하여 prefix 충돌 방지
        예: '/배틀생성'이 '/배틀'보다 먼저 매칭됨
        """
        for command, handler_name in self._get_sorted_routes():
            if cmd.startswith(command):
                return handler_name
        return None

    # ==========================================
    # 기본 핸들러 (분리하지 않은 것들)
    # ==========================================

    def handle_start(self) -> Dict:
        """게임 시작 / 회원가입"""
        user, is_new = UserService.create_user(self.db, self.kakao_id, self.nickname)

        if is_new:
            masked_id = f"{self.kakao_id[:4]}****" if len(self.kakao_id) > 4 else "****"
            logger.info(f"새 유저 가입: {masked_id}")
            welcome_msg = Messages.WELCOME.format(initial_cash=GameConfig.INITIAL_CASH)
            buttons = [
                {"label": "📅 출석 +30만", "action": "message", "messageText": "/출석"},
                {"label": "🎫 무료복권", "action": "message", "messageText": "/복권"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
            ]
            return KakaoResponse.quick_replies(welcome_msg, buttons)
        else:
            buttons = [
                {"label": "📅 출석", "action": "message", "messageText": "/출석"},
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "📰 뉴스", "action": "message", "messageText": "/뉴스"},
                {"label": "🔍 검색", "action": "message", "messageText": "/검색"},
            ]
            return KakaoResponse.quick_replies("이미 가입했어요! 바로 플레이 👇", buttons)

    def handle_attendance(self) -> Dict:
        """출석 체크"""
        success, reward, streak, cash = UserService.check_attendance(self.db, self.kakao_id)

        if not success and reward == 0 and streak == 0:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        streak_emoji = get_streak_display(streak)

        # 스트릭 기반 동기부여 메시지
        def get_streak_motivation(s: int, is_new: bool) -> str:
            if s >= 7:
                if s == 7 and is_new:
                    return "🎊🎊 7일 연속 달성! 최대 보너스 획득! 🎊🎊"
                elif s == 14 and is_new:
                    return "👑 2주 연속! 당신은 진정한 충성 플레이어! 👑"
                elif s == 30 and is_new:
                    return "🏆 한 달 연속!!! 전설의 투자자! 🏆"
                return f"🔥 최대 보너스 유지 중! ({s}일)"
            elif s >= 5:
                return f"🎯 내일 7일 달성하면 2배 보너스! ({7-s}일 남음)"
            elif s >= 3:
                return f"📈 5일 달성하면 50% 보너스! ({5-s}일 남음)"
            elif s >= 1:
                return f"💪 3일 달성하면 20% 보너스! ({3-s}일 남음)"
            return "🌱 연속 출석 시작! 보너스가 커져요!"

        if success:
            motivation = get_streak_motivation(streak, True)
            msg = f"""✅ 출석 완료!

💰 +{reward:,}원 지급!
{streak_emoji} 연속 출석: {streak}일

{motivation}

현재 잔고: {cash:,}원"""
        else:
            motivation = get_streak_motivation(streak, False)
            # 스트릭 유지 경고 - 잃을 보상 강조 (손실 회피 심리)
            if streak >= 7:
                bonus_losing = int(GameConfig.ATTENDANCE_REWARD * 2)  # 2배 보너스
                warning = f"🚨 내일 출석 안 하면 {streak}일 스트릭 리셋!\n💸 잃게 될 보너스: {bonus_losing:,}원/일 → 기본 30만원"
            elif streak >= 5:
                bonus_losing = int(GameConfig.ATTENDANCE_REWARD * 1.5)
                warning = f"⚠️ 내일 출석 안 하면 {streak}일 스트릭 리셋!\n💸 잃게 될 보너스: {bonus_losing:,}원/일"
            elif streak >= 3:
                bonus_losing = int(GameConfig.ATTENDANCE_REWARD * 1.2)
                warning = f"⚠️ 내일 출석 안 하면 {streak}일 스트릭 리셋!\n💸 잃게 될 보너스: {bonus_losing:,}원/일"
            else:
                warning = "📅 내일 다시 출석해주세요!"
            msg = f"""✅ 오늘 출석 완료!

{warning}
{streak_emoji} 현재 연속 출석: {streak}일
{motivation}"""

        buttons = [
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
            {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
        ]
        buttons.extend(self._get_game_buttons())
        return KakaoResponse.quick_replies(msg, buttons)

    def handle_help(self) -> Dict:
        """도움말"""
        return KakaoResponse.quick_replies(
            Messages.HELP,
            [
                {"label": "🎮 시작하기", "action": "message", "messageText": "/시작"},
                {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    def handle_welcome(self) -> Dict:
        """웰컴 블록 응답 - 채팅방 진입 시 빈 utterance로 트리거됨"""
        return KakaoResponse.quick_replies(
            "🎮 가상 주식 연습 봇에 오신 걸 환영해요!\n실제 주식 시세로 투자 연습을 시작해보세요.",
            [
                {"label": "🎮 시작하기", "action": "message", "messageText": "/시작"},
                {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
            ]
        )

    def handle_unknown(self) -> Dict:
        """알 수 없는 명령어 / 폴백 응답"""
        logger.debug(f"알 수 없는 명령어: {self.utterance}")
        return KakaoResponse.quick_replies(
            Messages.UNKNOWN_COMMAND,
            [
                {"label": "🎮 시작하기", "action": "message", "messageText": "/시작"},
                {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "📅 출석", "action": "message", "messageText": "/출석"},
            ]
        )
