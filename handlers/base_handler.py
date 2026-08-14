"""
기본 핸들러 믹스인 (개선)
- 공통 기능 제공
- 투자 동기부여 요소 (연속 보상, 스트릭, 레벨업)
"""

from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from cachetools import TTLCache

from game_config import GameConfig
from market_calendar import is_market_closed
from utils import get_handler_logger, KakaoResponse

logger = get_handler_logger()


class BaseHandlerMixin:
    """핸들러 공통 기능"""

    db: Session
    kakao_id: str
    utterance: str
    nickname: str
    group_key: str

    # ===========================================
    # 응답 한도
    # ===========================================

    @property
    def button_cap(self) -> int:
        """이 방에서 세로로 노출 가능한 버튼 수.

        그룹 챗봇 가이드는 세로 정렬 최대 5개를 허용하지만 1:1 기본 명세는
        3개다. 이 앱은 둘 다 받으므로 방을 아는 여기서만 판단한다.
        group_key가 없으면(1:1) 좁은 쪽을 쓴다.
        """
        if self.group_key:
            return KakaoResponse.MAX_VERTICAL_BUTTONS_GROUP
        return KakaoResponse.MAX_VERTICAL_BUTTONS

    # ===========================================
    # 유저 표시명
    # ===========================================

    def _display_name(self) -> str:
        """카카오톡 @멘션 형태 유저 표시명"""
        name = self.nickname
        if not name:
            from models import User

            user = self.db.query(User).filter(User.kakao_id == self.kakao_id).first()
            if user and user.nickname:
                name = user.nickname
        if name:
            return f"@{name} 님"
        return ""

    # ===========================================
    # 도파민 요소: 효과음/이펙트
    # ===========================================
    EFFECTS = {
        "jackpot": "🎆🎇🎆🎇🎆",
        "big_win": "✨🎉✨",
        "win": "🎊",
        "small_win": "💫",
        "profit": "📈💰",
        "loss": "📉",
        "streak": ["🔥", "🔥🔥", "🔥🔥🔥", "💎🔥", "⚡🔥⚡"],
        "rank_up": "⬆️🏆",
        "level_up": "🆙✨",
        "milestone": "🏅",
    }

    PROFIT_TIERS = [
        (1_000_000, "🤑 레전드 수익!", EFFECTS["jackpot"]),
        (500_000, "💎 압도적 수익!", EFFECTS["big_win"]),
        (100_000, "🎉 좋아요!", EFFECTS["win"]),
        (10_000, "👍 괜찮네요!", EFFECTS["small_win"]),
        (0, "📈 수익!", ""),
        (-50_000, "😅 아쉽네요", ""),
        (-100_000, "😢 조금 많이...", ""),
        (float("-inf"), "💸 크게 잃었네요", ""),
    ]

    def _get_profit_message(self, profit: int) -> Tuple[str, str]:
        """수익에 따른 도파민 메시지 반환 (메시지, 이펙트)"""
        for threshold, msg, effect in self.PROFIT_TIERS:
            if profit >= threshold:
                return msg, effect
        return "", ""

    def _get_streak_effect(self, streak: int) -> str:
        """연속 횟수에 따른 이펙트"""
        effects = self.EFFECTS["streak"]
        if streak <= 0:
            return ""
        if streak <= len(effects):
            return effects[streak - 1]
        return effects[-1] + f" x{streak}"

    # ===========================================
    # 인기 종목 동적 버튼 (하드코딩 제거)
    # ===========================================

    _popular_stock_cache = TTLCache(maxsize=1, ttl=300)  # 5분 캐시

    @classmethod
    def remember_popular_stock(cls, name: str) -> None:
        """순위 조회가 성공했을 때 1등 종목명을 기억해 둔다.

        버튼을 만들려고 따로 조회하지 않기 위해서다. 이미 순위를 받아온
        핸들러가 그 값을 여기 넣어주면 다음 화면들이 공짜로 쓴다.
        """
        if name:
            cls._popular_stock_cache["top"] = name

    @classmethod
    def _get_top_popular_stock(cls) -> Optional[str]:
        """기억해 둔 인기 1등 종목명. **외부 호출은 하지 않는다.**

        예전에는 캐시가 비면 여기서 KIS를 직접 불렀다. 그 결과 순위 조회가
        실패한 화면에서 버튼을 만들려다 KIS를 한 번 더 부르는 일이 생겼다.
        첫 호출이 예산을 다 쓴 뒤라 두 번째는 0.6초만 받고 같이 죽었고,
        로그에는 실패가 두 줄로 찍혀 원인이 더 흐려졌다.

        버튼 하나 때문에 응답 예산을 쓰지 않는다. 값이 없으면 목록 버튼으로
        물러선다.
        """
        return cls._popular_stock_cache.get("top")

    def _popular_stock_btn(self, emoji: str = "🔥", command: str = "/시세") -> Dict:
        """인기 1등 종목 버튼 (모르면 인기종목 목록 버튼)"""
        name = self._get_top_popular_stock()
        if name:
            return {
                "label": f"{emoji} {name}"[: KakaoResponse.BUTTON_LABEL_LIMIT],
                "action": "message",
                "messageText": f"{command} {name}",
            }
        return {"label": "📊 인기종목", "action": "message", "messageText": "/인기"}

    # ===========================================
    # Quick Reply 버튼 헬퍼
    # ===========================================

    def _get_game_buttons(self) -> list:
        """장 마감 시간에만 예측게임 버튼 반환"""
        if is_market_closed():
            return [
                {"label": "📈 예측게임", "action": "message", "messageText": "/예측"}
            ]
        return []

    def _get_quick_trade_buttons(self, stock_name: str = None) -> List[Dict]:
        """빠른 거래 버튼"""
        buttons = []
        if stock_name:
            buttons.extend(
                [
                    {
                        "label": f"📈 {stock_name} 매수",
                        "action": "message",
                        "messageText": f"/매수 {stock_name} 10",
                    },
                    {
                        "label": f"📉 {stock_name} 매도",
                        "action": "message",
                        "messageText": f"/매도 {stock_name} 10",
                    },
                ]
            )
        buttons.extend(
            [
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
            ]
        )
        return buttons

    def _get_continue_game_buttons(
        self, game_type: str, bet: int, choice: str = None
    ) -> List[Dict]:
        """예측게임 계속하기 버튼"""
        buttons = []

        if game_type == "lottery":
            buttons.append(
                {
                    "label": "🎁 한번 더!",
                    "action": "message",
                    "messageText": "/보물상자",
                }
            )
        elif game_type == "stock_quiz":
            buttons.extend(
                [
                    {
                        "label": "🔮 한번 더!",
                        "action": "message",
                        "messageText": f"/시장예측 {bet}",
                    },
                    {
                        "label": "🔮 2배!",
                        "action": "message",
                        "messageText": f"/시장예측 {bet * 2}",
                    },
                ]
            )
        elif game_type == "updown":
            buttons.extend(
                [
                    {
                        "label": "🔢 새 게임!",
                        "action": "message",
                        "messageText": f"/업다운 {bet}",
                    },
                ]
            )

        # 다른 예측게임 추천
        buttons.append(
            {"label": "📈 다른 예측", "action": "message", "messageText": "/예측"}
        )
        return buttons

    def _get_navigation_buttons(self) -> List[Dict]:
        """기본 내비게이션 버튼"""
        buttons = [
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
            {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
        ]
        buttons.extend(self._get_game_buttons())
        return buttons

    def _get_after_trade_buttons(
        self, stock_name: str, action: str = "buy"
    ) -> List[Dict]:
        """거래 후 추천 버튼 (도파민 유지)"""
        buttons = []

        if action == "buy":
            buttons.extend(
                [
                    {
                        "label": f"📈 {stock_name} 더 매수",
                        "action": "message",
                        "messageText": f"/전량매수 {stock_name}",
                    },
                    {
                        "label": f"📊 {stock_name} 시세",
                        "action": "message",
                        "messageText": f"/시세 {stock_name}",
                    },
                ]
            )
        else:
            buttons.extend(
                [
                    {
                        "label": f"📊 {stock_name} 시세",
                        "action": "message",
                        "messageText": f"/시세 {stock_name}",
                    },
                ]
            )

        buttons.extend(
            [
                {
                    "label": "💼 포폴 확인",
                    "action": "message",
                    "messageText": "/포트폴리오",
                },
                {
                    "label": "🚀 다른 급등주",
                    "action": "message",
                    "messageText": "/급등",
                },
            ]
        )
        buttons.extend(self._get_game_buttons())
        return buttons

    def _get_ranking_climb_buttons(self) -> List[Dict]:
        """랭킹 상승 유도 버튼"""
        return [
            {"label": "🚀 급등주 투자", "action": "message", "messageText": "/급등"},
            {"label": "📉 저점매수", "action": "message", "messageText": "/급락"},
            {"label": "📈 예측게임", "action": "message", "messageText": "/예측"},
            {"label": "💼 포폴", "action": "message", "messageText": "/포트폴리오"},
        ]

    # ===========================================
    # 파싱 헬퍼
    # ===========================================

    def _parse_parts(self, min_parts: int = 2) -> Tuple[List[str], bool]:
        """
        명령어 파싱
        Returns: (parts, is_valid)
        """
        parts = self.utterance.split()
        if len(parts) < min_parts:
            return parts, False
        return parts, True

    def _parse_with_amount(self) -> Tuple[str, Optional[int], bool]:
        """
        금액이 포함된 명령어 파싱
        예: /시장예측 50000
        Returns: (command, amount, is_valid)
        """
        parts = self.utterance.split()
        if len(parts) < 2:
            return parts[0] if parts else "", None, False

        try:
            amount = int(parts[1].replace(",", ""))
            return parts[0], amount, True
        except ValueError:
            return parts[0], None, False

    def _parse_with_choice(self) -> Tuple[str, Optional[int], Optional[str], bool]:
        """
        금액과 선택이 포함된 명령어 파싱
        예: /동전 50000 앞
        Returns: (command, amount, choice, is_valid)
        """
        parts = self.utterance.split()
        if len(parts) < 3:
            return parts[0] if parts else "", None, None, False

        try:
            amount = int(parts[1].replace(",", ""))
            choice = parts[2].strip()
            return parts[0], amount, choice, True
        except ValueError:
            return parts[0], None, parts[2] if len(parts) > 2 else None, False

    def _parse_stock_query(self, start_index: int = 1) -> str:
        """
        종목명 파싱 (띄어쓰기 포함)
        예: /시세 삼성전자
        """
        parts = self.utterance.split(maxsplit=start_index)
        if len(parts) <= start_index:
            return ""
        return parts[start_index].strip()

    # ===========================================
    # 메시지 포맷팅 헬퍼
    # ===========================================

    def _format_profit(self, profit: int) -> str:
        """수익 포맷팅"""
        if profit > 0:
            return f"📈 +{profit:,}원"
        elif profit < 0:
            return f"📉 {profit:,}원"
        return "➖ ±0원"

    def _format_rate(self, rate: float) -> str:
        """수익률 포맷팅"""
        if rate > 0:
            return f"▲{rate:+.2f}%"
        elif rate < 0:
            return f"▼{rate:.2f}%"
        return "0.00%"

    def _get_sell_celebration(self, profit_rate: float, profit: int = 0) -> str:
        """수익률 기반 축하 메시지 (매도 시 사용) - 도파민 극대화"""
        from utils import get_sell_exclamation

        return get_sell_exclamation(profit_rate, profit)

    def _add_celebration(self, msg: str, profit: int) -> str:
        """큰 수익에 축하 이펙트 추가"""
        celebration_msg, effect = self._get_profit_message(profit)
        if effect:
            return f"{effect}\n\n{msg}"
        return msg

    # ===========================================
    # 공통 에러 응답 (중복 제거)
    # ===========================================

    def _market_closed_response(self, message: str = None) -> Dict:
        """장 마감 시 공통 응답.

        막힌 건 '지금 사고파는 것'이지 시세를 보는 것이 아니다. 그런데
        버튼이 전부 게임으로만 가서, 장이 닫혔을 때 종목을 훑어볼 길이
        끊겼다. 인기종목(거래대금 상위)을 첫 버튼으로 둔다.
        """
        if message is None:
            message = (
                "📢 현재 장이 열려있지 않아요!\n\n"
                "📊 시세는 계속 볼 수 있어요. 다음 장을 준비해보세요."
            )
        return KakaoResponse.text_with_buttons(
            message,
            [
                {"label": "🔥 인기종목", "action": "message", "messageText": "/인기"},
                {
                    "label": "🎁 보물상자",
                    "action": "message",
                    "messageText": "/보물상자",
                },
            ],
        )

    # _market_closed_with_message는 _market_closed_response(message)로 통합됨

    def _check_market_closed_error(self, result: Dict) -> tuple:
        """
        서비스 결과에서 MARKET_CLOSED 에러 확인
        Returns: (is_market_closed, response or None)
        """
        if not result.get("success") and result.get("error_code") == "MARKET_CLOSED":
            return True, self._market_closed_response(
                result.get("message", "장이 마감되었습니다.")
            )
        return False, None

    def _game_failure_response(self, message: str) -> Dict:
        """게임 실패/에러 시 공통 응답 (현금 부족, 시스템 에러 등)"""
        return KakaoResponse.text_with_buttons(
            message,
            [
                {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                {
                    "label": "🎁 보물상자",
                    "action": "message",
                    "messageText": "/보물상자",
                },
                {
                    "label": "💼 포트폴리오",
                    "action": "message",
                    "messageText": "/포트폴리오",
                },
            ],
        )

    def _parse_bet_amount(self, default: int = None) -> Tuple[int, bool]:
        """
        투자 금액 파싱 헬퍼
        Returns: (amount, is_valid)
        """
        if default is None:
            default = GameConfig.DEFAULT_BET

        parts = self.utterance.split()
        if len(parts) < 2:
            return default, True  # 기본값 사용

        try:
            amount = int(parts[1].replace(",", ""))
            return amount, True
        except ValueError:
            return 0, False
