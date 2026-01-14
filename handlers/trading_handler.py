"""
거래 관련 핸들러
- 매수, 매도, 전량매수, 전량매도
- 잔고, 포트폴리오
"""
from typing import Dict

from services import UserService, TradeService, StockService
from utils import KakaoResponse, get_profit_bar, get_tier_title
from config import Messages

from .base_handler import BaseHandlerMixin


class TradingHandlerMixin(BaseHandlerMixin):
    """거래 관련 핸들러 믹스인"""

    def handle_price(self) -> Dict:
        """시세 조회"""
        parts = self.utterance.split(maxsplit=1)

        if len(parts) < 2:
            return KakaoResponse.quick_replies(
                "📊 어떤 종목을 볼까요?",
                [
                    {"label": "🔥 삼성전자", "action": "message", "messageText": "/시세 삼성전자"},
                    {"label": "🚀 SK하이닉스", "action": "message", "messageText": "/시세 SK하이닉스"},
                    {"label": "⚡ 네이버", "action": "message", "messageText": "/시세 NAVER"},
                    {"label": "🎮 카카오", "action": "message", "messageText": "/시세 카카오"},
                    {"label": "📈 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        query = parts[1].strip()
        stock_info = StockService.get_price(query)

        if not stock_info:
            holding = TradeService.find_holding_by_name(self.db, self.kakao_id, query)
            if holding:
                stock_info = StockService.get_price(holding.stock_code)
                if stock_info:
                    stock_info["name"] = holding.stock_name
                    StockService._cache_stock(holding.stock_code, holding.stock_name)

        if not stock_info:
            similar = StockService.search_similar_stocks(query, limit=5)
            if similar:
                buttons = [{"label": f"📊 {s['name']}", "action": "message", "messageText": f"/시세 {s['name']}"} for s in similar]
                return KakaoResponse.quick_replies(
                    f"'{query}' 종목을 못 찾았어요 😅\n혹시 이 종목들 중에 있나요?",
                    buttons
                )
            return KakaoResponse.simple_text(Messages.STOCK_NOT_FOUND.format(query=query))

        msg = Messages.STOCK_PRICE.format(
            name=stock_info["name"],
            code=stock_info["code"],
            price=stock_info["price"],
            change=stock_info["change"],
            low=stock_info["low"],
            high=stock_info["high"],
            volume=stock_info["volume"]
        )

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "1주 매수", "action": "message", "messageText": f"/매수 {stock_info['name']} 1"},
                {"label": "10주 매수", "action": "message", "messageText": f"/매수 {stock_info['name']} 10"},
                {"label": "100주 매수", "action": "message", "messageText": f"/매수 {stock_info['name']} 100"},
                {"label": "💰 전량매수", "action": "message", "messageText": f"/전량매수 {stock_info['name']}"}
            ]
        )

    def handle_buy(self) -> Dict:
        """주식 매수"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "사용법: /매수 [종목명] [수량]\n예: /매수 삼성전자 10",
                [
                    {"label": "📈 삼성전자 1주", "action": "message", "messageText": "/매수 삼성전자 1"},
                    {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        try:
            quantity = int(parts[-1])
            stock_query = " ".join(parts[1:-1])
        except ValueError:
            return KakaoResponse.quick_replies(
                "수량은 숫자로 입력해주세요.\n예: /매수 삼성전자 10",
                [
                    {"label": "📈 1주 매수", "action": "message", "messageText": f"/매수 {parts[1]} 1"},
                    {"label": "📈 10주 매수", "action": "message", "messageText": f"/매수 {parts[1]} 10"}
                ]
            )

        if not stock_query:
            return KakaoResponse.quick_replies(
                "종목명을 입력해주세요.\n예: /매수 삼성전자 10",
                [
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"}
                ]
            )

        result = TradeService.buy_stock(self.db, self.kakao_id, stock_query, quantity)

        if not result["success"]:
            if result.get("error_code") == "MARKET_CLOSED":
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                        {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
                        {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                    ]
                )
            elif "data" in result and "shortage" in result.get("data", {}):
                data = result["data"]
                msg = Messages.NOT_ENOUGH_CASH.format(
                    required=data["required"],
                    cash=data["cash"],
                    shortage=data["shortage"]
                )
                return KakaoResponse.quick_replies(
                    msg,
                    [
                        {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                        {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                        {"label": "🎯 미션확인", "action": "message", "messageText": "/미션"}
                    ]
                )
            else:
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"},
                        {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                    ]
                )

        data = result["data"]
        msg = Messages.BUY_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            cash=data["cash"]
        )

        if data.get("mission_reward"):
            mr = data["mission_reward"]
            bonus_text = " (보너스 요일!)" if mr.get("is_bonus_day") else ""
            msg += f"\n\n🎯 일간 미션 완료!{bonus_text}\n💰 +{mr['reward']:,}원 획득!"

        if data.get("new_achievements"):
            for ach in data["new_achievements"]:
                msg += f"\n\n🏆 업적 달성: {ach['name']}!\n💰 +{ach['reward']:,}원 획득!"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": f"🔄 추가매수", "action": "message", "messageText": f"/시세 {data['name']}"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_sell(self) -> Dict:
        """주식 매도"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "사용법: /매도 [종목명] [수량]\n예: /매도 삼성전자 10",
                [
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                    {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"}
                ]
            )

        try:
            quantity = int(parts[-1])
            stock_query = " ".join(parts[1:-1])
        except ValueError:
            return KakaoResponse.quick_replies(
                "수량은 숫자로 입력해주세요.\n예: /매도 삼성전자 10",
                [
                    {"label": f"📉 {parts[1]} 전량", "action": "message", "messageText": f"/전량매도 {parts[1]}"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        if not stock_query:
            return KakaoResponse.quick_replies(
                "종목명을 입력해주세요.\n예: /매도 삼성전자 10",
                [
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        result = TradeService.sell_stock(self.db, self.kakao_id, stock_query, quantity)

        if not result["success"]:
            if result.get("error_code") == "MARKET_CLOSED":
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                        {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
                        {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                    ]
                )
            elif "data" in result and "holding" in result.get("data", {}):
                data = result["data"]
                msg = Messages.NOT_ENOUGH_STOCK.format(
                    requested=data["requested"],
                    holding=data["holding"]
                )
                return KakaoResponse.quick_replies(
                    msg,
                    [
                        {"label": f"📉 {stock_query} 전량", "action": "message", "messageText": f"/전량매도 {stock_query}"},
                        {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                    ]
                )
            else:
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                        {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"}
                    ]
                )

        data = result["data"]

        if data["profit"] >= 0:
            profit_text = f"📈 수익: +{data['profit']:,}원 (+{data['profit_rate']:.2f}%)"
        else:
            profit_text = f"📉 손실: {abs(data['profit']):,}원 ({data['profit_rate']:.2f}%)"

        msg = Messages.SELL_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            profit_text=profit_text,
            cash=data["cash"]
        )

        if data.get("mission_reward"):
            mr = data["mission_reward"]
            bonus_text = " (보너스 요일!)" if mr.get("is_bonus_day") else ""
            msg += f"\n\n🎯 일간 미션 완료!{bonus_text}\n💰 +{mr['reward']:,}원 획득!"

        if data.get("new_achievements"):
            for ach in data["new_achievements"]:
                msg += f"\n\n🏆 업적 달성: {ach['name']}!\n💰 +{ach['reward']:,}원 획득!"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"}
            ]
        )

    def handle_buy_max(self) -> Dict:
        """전량 매수"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.quick_replies(
                "사용법: /전량매수 [종목명]\n예: /전량매수 삼성전자",
                [
                    {"label": "💰 삼성전자", "action": "message", "messageText": "/전량매수 삼성전자"},
                    {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        stock_query = " ".join(parts[1:])
        result = TradeService.buy_max(self.db, self.kakao_id, stock_query)

        if not result["success"]:
            if result.get("error_code") == "MARKET_CLOSED":
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                        {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
                        {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                    ]
                )
            if "잔고" in result["message"]:
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                        {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                        {"label": "🎯 미션확인", "action": "message", "messageText": "/미션"}
                    ]
                )
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        data = result["data"]
        msg = Messages.BUY_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            cash=data["cash"]
        )

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_sell_all(self) -> Dict:
        """전량 매도"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.quick_replies(
                "사용법: /전량매도 [종목명]\n예: /전량매도 삼성전자",
                [
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                    {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"}
                ]
            )

        stock_query = " ".join(parts[1:])
        result = TradeService.sell_all(self.db, self.kakao_id, stock_query)

        if not result["success"]:
            if result.get("error_code") == "MARKET_CLOSED":
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                        {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
                        {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                    ]
                )
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                    {"label": "📊 시세 조회", "action": "message", "messageText": "/시세"}
                ]
            )

        data = result["data"]

        if data["profit"] >= 0:
            profit_text = f"📈 수익: +{data['profit']:,}원 (+{data['profit_rate']:.2f}%)"
        else:
            profit_text = f"📉 손실: {abs(data['profit']):,}원 ({data['profit_rate']:.2f}%)"

        msg = Messages.SELL_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            profit_text=profit_text,
            cash=data["cash"]
        )

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"}
            ]
        )

    def handle_balance(self) -> Dict:
        """잔고 조회"""
        cash = UserService.get_balance(self.db, self.kakao_id)

        if cash is None:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        msg = Messages.BALANCE.format(cash=cash)

        buttons = [
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
            {"label": "📈 인기종목", "action": "message", "messageText": "/인기"}
        ]
        buttons.extend(self._get_game_buttons())

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_portfolio(self) -> Dict:
        """포트폴리오 조회"""
        portfolio = TradeService.get_portfolio(self.db, self.kakao_id)

        if portfolio is None:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        buttons = []
        if portfolio["holdings"]:
            holdings_text = ""
            for h in portfolio["holdings"]:
                emoji = "🔺" if h["profit_rate"] >= 0 else "🔻"
                holdings_text += f"\n{h['name']} {h['quantity']:,}주"
                holdings_text += f"\n  {h['current_price']:,}원 ({h['profit_rate']:+.1f}%) {emoji}\n"
                if len(buttons) < 4:
                    buttons.append({
                        "label": f"💸 {h['name']} 전량매도",
                        "action": "message",
                        "messageText": f"/전량매도 {h['name']}"
                    })
        else:
            holdings_text = "\n아직 보유 주식이 없어요!"
            buttons = [
                {"label": "🔥 삼성전자", "action": "message", "messageText": "/시세 삼성전자"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "📊 인기종목", "action": "message", "messageText": "/인기"}
            ]

        tier = get_tier_title(portfolio['total_asset'])
        profit_bar = get_profit_bar(portfolio['profit_rate'])

        msg = f"""💼 내 포트폴리오

{tier}
💵 현금: {portfolio['cash']:,}원
{holdings_text}
{profit_bar}
💰 총자산: {portfolio['total_asset']:,}원"""

        if not buttons:
            buttons = [{"label": "📊 인기종목", "action": "message", "messageText": "/인기"}]

        buttons.extend(self._get_game_buttons())

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_transactions(self) -> Dict:
        """거래 내역 조회"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 게임을 시작해주세요!",
                [{"label": "🎮 시작하기", "action": "message", "messageText": "/시작"}]
            )

        transactions = TradeService.get_transactions(self.db, self.kakao_id, limit=10)

        if not transactions:
            return KakaoResponse.quick_replies(
                "거래 내역이 없습니다.\n주식을 매수해보세요!",
                [
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "🔥 삼성전자", "action": "message", "messageText": "/시세 삼성전자"},
                ]
            )

        msg = "📜 최근 거래 내역\n"
        for t in transactions:
            emoji = "📈" if t.trade_type == "BUY" else "📉"
            trade_type_str = "매수" if t.trade_type == "BUY" else "매도"
            time_str = t.created_at.strftime("%m/%d %H:%M")

            msg += f"\n{emoji} [{trade_type_str}] {t.stock_name}"
            msg += f"\n   {t.quantity:,}주 × {t.price:,}원"

            if t.trade_type == "SELL" and t.profit is not None:
                profit_emoji = "🔺" if t.profit >= 0 else "🔻"
                msg += f"\n   수익: {t.profit:+,}원 ({t.profit_rate:+.2f}%) {profit_emoji}"

            msg += f"\n   {time_str}\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"}
            ]
        )
