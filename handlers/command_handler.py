"""
명령어 처리 핸들러 (리팩토링)
- 명령어 라우팅
- 각 기능별 핸들러 믹스인 사용
"""
from typing import Dict, Optional
from sqlalchemy.orm import Session

from services import UserService
from services.user_service import register_chatroom_member
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
    - GameHandlerMixin: 예측게임 (복권, 시장예측, 업다운)
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
        "/도움말주식": "handle_help_stock",
        "/도움말자산": "handle_help_asset",
        "/도움말게임": "handle_help_game",
        "/도움말소셜": "handle_help_social",

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
        "/ETF급등": "handle_top_etf_gainers",
        "/etf급등": "handle_top_etf_gainers",
        "/ETF상승": "handle_top_etf_gainers",
        "/ETF급락": "handle_top_etf_losers",
        "/etf급락": "handle_top_etf_losers",
        "/ETF하락": "handle_top_etf_losers",
        "/시장": "handle_market_overview",
        "/지수": "handle_market_overview",
        "/뉴스": "handle_news",
        "/ㄴㅅ": "handle_news",

        # 예측게임
        "/예측": "handle_game_menu",
        "/예측게임": "handle_game_menu",
        "/복권": "handle_lottery",
        "/보물상자": "handle_lottery",
        "/ㅂㄱ": "handle_lottery",
        "/시장예측": "handle_stock_quiz",
        "/ㅅㅈ": "handle_stock_quiz",
        "/업다운정산": "handle_updown_cashout",
        "/업다운": "handle_updown",
        "/ㅇㄷ": "handle_updown",
        "/각성": "handle_enhance",
        "/ㄱㅎ": "handle_enhance",
        "/능력": "handle_enhance",
        "/강화": "handle_enhance",

        # 소셜/경쟁
        "/랭킹": "handle_ranking",
        "/ㄹㅋ": "handle_ranking",
        "/내순위": "handle_my_rank",
        "/ㄴㅅㅇ": "handle_my_rank",
        "/미션": "handle_mission",
        "/업적": "handle_achievements",
        "/닉네임": "handle_nickname",
        "/ㄴㄴ": "handle_nickname",
        "/각성랭킹": "handle_enhance_ranking",
        "/ㄱㅅㄹㅋ": "handle_enhance_ranking",

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

    def __init__(self, db: Session, kakao_id: str, utterance: str, nickname: str = None, group_key: str = ""):
        self.db = db
        self.kakao_id = kakao_id
        self.utterance = utterance.strip()
        self.nickname = nickname
        self.group_key = group_key

    def handle(self) -> Dict:
        """
        명령어 처리 메인 함수
        라우팅 테이블을 사용하여 적절한 핸들러 호출
        """
        # 그룹 챗봇: 채팅방 멤버 등록
        if self.group_key:
            register_chatroom_member(self.db, self.group_key, self.kakao_id)

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
                {"label": "🎁 보물상자", "action": "message", "messageText": "/보물상자"},
                {"label": "🚀 급등주 정찰", "action": "message", "messageText": "/급등"},
            ]
            return KakaoResponse.quick_replies(welcome_msg, buttons)
        else:
            buttons = [
                {"label": "📅 출석", "action": "message", "messageText": "/출석"},
                {"label": "🎁 보물상자", "action": "message", "messageText": "/보물상자"},
                {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "🧬 각성", "action": "message", "messageText": "/각성"},
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"},
            ]
            name = self._display_name()
            return KakaoResponse.quick_replies(f"{name}, 다시 오셨군요! 바로 시작 👇", buttons)

    def handle_attendance(self) -> Dict:
        """출석 체크"""
        success, reward, streak, cash, enhance_level = UserService.check_attendance(self.db, self.kakao_id)

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
                    return "🎊🎊 7일 연속 출석! 최대 보너스 골드 획득! 🎊🎊"
                elif s == 14 and is_new:
                    return "👑 2주 연속! 진정한 장기 투자자! 👑"
                elif s == 30 and is_new:
                    return "🏆 한 달 연속!!! 전설의 개미로 등극! 🏆"
                return f"🔥 최대 보너스 유지 중! ({s}일 연속)"
            elif s >= 5:
                return f"🎯 내일 7일 달성하면 2배 골드! ({7-s}일 남음)"
            elif s >= 3:
                return f"📈 5일 달성하면 50% 보너스! ({5-s}일 남음)"
            elif s >= 1:
                return f"💪 3일 달성하면 20% 보너스! ({3-s}일 남음)"
            return "🌱 연속 입장 시작! 보너스 골드가 커져요!"

        if success:
            motivation = get_streak_motivation(streak, True)
            enhance_line = ""
            if enhance_level > 0:
                from config import EnhanceConfig
                title_name, title_emoji = EnhanceConfig.get_title(enhance_level)
                att_bonus = int((EnhanceConfig.get_attendance_multiplier(enhance_level) - 1) * 100)
                enhance_line = f"\n{title_emoji} {title_name} 보너스: +{att_bonus}% (Lv.{enhance_level})"

            name = self._display_name()
            msg = f"""📅 {name} 출석 완료!

🪙 +{reward:,}원 획득!{enhance_line}
{streak_emoji} 연속 입장: {streak}일

{motivation}

💰 현재 골드: {cash:,}원"""
        else:
            motivation = get_streak_motivation(streak, False)
            # 스트릭 유지 경고 - 잃을 보상 강조 (손실 회피 심리)
            if streak >= 7:
                bonus_losing = int(GameConfig.ATTENDANCE_REWARD * 2)  # 2배 보너스
                warning = f"🚨 내일 입장 안 하면 {streak}일 스트릭 리셋!\n💸 잃게 될 보너스: {bonus_losing:,}원/일 → 기본 30만원"
            elif streak >= 5:
                bonus_losing = int(GameConfig.ATTENDANCE_REWARD * 1.5)
                warning = f"⚠️ 내일 입장 안 하면 {streak}일 스트릭 리셋!\n💸 잃게 될 보너스: {bonus_losing:,}원/일"
            elif streak >= 3:
                bonus_losing = int(GameConfig.ATTENDANCE_REWARD * 1.2)
                warning = f"⚠️ 내일 입장 안 하면 {streak}일 스트릭 리셋!\n💸 잃게 될 보너스: {bonus_losing:,}원/일"
            else:
                warning = "📅 내일 다시 출석해주세요!"
            name = self._display_name()
            msg = f"""📅 {name}, 오늘 이미 출석했어요!

{warning}
{streak_emoji} 현재 연속 입장: {streak}일
{motivation}"""

        buttons = [
            {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
            {"label": "🎁 보물상자", "action": "message", "messageText": "/보물상자"},
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
        ]
        buttons.extend(self._get_game_buttons())
        return KakaoResponse.quick_replies(msg, buttons)

    def handle_help(self) -> Dict:
        """도움말 - 분야 선택(화면을 가득 채우지 않도록 카테고리로 분할)"""
        buttons = [
            {"label": "📊 주식", "action": "message", "messageText": "/도움말주식"},
            {"label": "💼 자산", "action": "message", "messageText": "/도움말자산"},
            {"label": "🧬 게임·각성", "action": "message", "messageText": "/도움말게임"},
            {"label": "⚔️ 소셜", "action": "message", "messageText": "/도움말소셜"},
        ]
        return KakaoResponse.quick_replies(Messages.HELP, buttons)

    def handle_help_stock(self) -> Dict:
        """도움말 - 주식 투자"""
        buttons = [
            {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
            {"label": "🔥 인기 종목", "action": "message", "messageText": "/인기"},
            {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
        ]
        return KakaoResponse.quick_replies(Messages.HELP_STOCK, buttons)

    def handle_help_asset(self) -> Dict:
        """도움말 - 내 자산"""
        buttons = [
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
            {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"},
            {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
        ]
        return KakaoResponse.quick_replies(Messages.HELP_ASSET, buttons)

    def handle_help_game(self) -> Dict:
        """도움말 - 각성·게임"""
        buttons = [
            {"label": "🎁 보물상자", "action": "message", "messageText": "/보물상자"},
            {"label": "🧬 각성", "action": "message", "messageText": "/각성"},
            {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
        ]
        return KakaoResponse.quick_replies(Messages.HELP_GAME, buttons)

    def handle_help_social(self) -> Dict:
        """도움말 - 소셜"""
        buttons = [
            {"label": "⚔️ 배틀", "action": "message", "messageText": "/배틀"},
            {"label": "🎯 미션", "action": "message", "messageText": "/미션"},
            {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
        ]
        return KakaoResponse.quick_replies(Messages.HELP_SOCIAL, buttons)

    def handle_welcome(self) -> Dict:
        """웰컴 블록 응답 - 채팅방 진입 시 빈 utterance로 트리거됨"""
        return KakaoResponse.quick_replies(
            "🐜 만렙개미에 오신 것을 환영합니다!\n쪼렙 개미에서 만렙 개미로 성장하세요!",
            [
                {"label": "🚀 시작하기", "action": "message", "messageText": "/시작"},
                {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
            ]
        )

    def handle_unknown(self) -> Dict:
        """알 수 없는 명령어 / 폴백 응답"""
        logger.debug(f"알 수 없는 명령어: {self.utterance}")
        return KakaoResponse.quick_replies(
            Messages.UNKNOWN_COMMAND,
            [
                {"label": "🚀 시작하기", "action": "message", "messageText": "/시작"},
                {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
                {"label": "📈 급등주", "action": "message", "messageText": "/급등"},
                {"label": "📅 출석", "action": "message", "messageText": "/출석"},
            ]
        )
