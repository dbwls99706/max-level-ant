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
        "/인기": "handle_top_volume",
        "/거래량": "handle_top_volume",
        "/ㅇㄱ": "handle_top_volume",
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

        # 라우팅 테이블에서 핸들러 찾기
        handler_name = self._find_handler(cmd)

        if handler_name:
            handler_method = getattr(self, handler_name, None)
            if handler_method:
                logger.debug(f"명령어 '{cmd}' -> {handler_name}")
                return handler_method()

        # 알 수 없는 명령어
        return self.handle_unknown()

    def _find_handler(self, cmd: str) -> Optional[str]:
        """
        명령어에 맞는 핸들러 이름 찾기
        startswith를 사용하여 인자가 있는 명령어도 매칭
        """
        for command, handler_name in self.COMMAND_ROUTES.items():
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
            logger.info(f"새 유저 가입: {self.kakao_id}")
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

        if success:
            msg = f"""✅ 출석 완료!

💰 +{reward:,}원 지급!
{streak_emoji} 연속 출석: {streak}일

현재 잔고: {cash:,}원"""
        else:
            msg = f"""⚠️ 오늘은 이미 출석했습니다!

내일 다시 출석해주세요.
{streak_emoji} 현재 연속 출석: {streak}일"""

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

    def handle_unknown(self) -> Dict:
        """알 수 없는 명령어"""
        logger.debug(f"알 수 없는 명령어: {self.utterance}")
        return KakaoResponse.quick_replies(
            Messages.UNKNOWN_COMMAND,
            [
                {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
                {"label": "🎮 시작하기", "action": "message", "messageText": "/시작"}
            ]
        )
