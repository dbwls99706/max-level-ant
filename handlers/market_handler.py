"""
시장 관련 핸들러
- 급등주, 급락주, 인기종목
- 시장 현황, 뉴스, 검색
"""
from typing import Dict

from services import StockService, NewsService
from utils import KakaoResponse

from .base_handler import BaseHandlerMixin


class MarketHandlerMixin(BaseHandlerMixin):
    """시장 관련 핸들러 믹스인"""

    def handle_search(self) -> Dict:
        """종목 검색"""
        parts = self.utterance.split(maxsplit=1)

        if len(parts) < 2:
            return KakaoResponse.quick_replies(
                "🔍 어떤 종목을 찾으시나요?",
                [
                    {"label": "🔍 반도체", "action": "message", "messageText": "/검색 반도체"},
                    {"label": "🔍 자동차", "action": "message", "messageText": "/검색 자동차"},
                    {"label": "🔍 바이오", "action": "message", "messageText": "/검색 바이오"},
                ]
            )

        query = parts[1].strip()
        results = StockService.search_stocks(query, limit=5)

        if not results:
            return KakaoResponse.quick_replies(
                f"'{query}' 관련 종목을 찾을 수 없습니다.",
                [
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "📊 인기종목", "action": "message", "messageText": "/인기"},
                ]
            )

        # 검색 결과에 시세 미리보기 추가 (배치 조회로 성능 최적화)
        stock_codes = {r["code"] for r in results[:5] if r.get("code")}
        stock_info_map = StockService.batch_get_stock_info(stock_codes)

        msg = f"🔍 '{query}' 검색 결과\n"
        for i, r in enumerate(results[:5], 1):
            code = r.get("code")
            stock_info = stock_info_map.get(code) if code else None
            if stock_info:
                change_emoji = "📈" if stock_info.get("change", 0) >= 0 else "📉"
                msg += f"\n{i}. {r['name']}"
                msg += f"\n   {stock_info['price']:,}원 ({stock_info['change']:+.1f}%) {change_emoji}"
            else:
                msg += f"\n{i}. {r['name']}"

        buttons = [{"label": f"📊 {r['name']}", "action": "message", "messageText": f"/시세 {r['name']}"} for r in results[:3]]
        buttons.append({"label": "🚀 급등주", "action": "message", "messageText": "/급등"})
        buttons.extend(self._get_game_buttons())

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_top_volume(self) -> Dict:
        """거래량 상위 종목"""
        stocks = StockService.get_top_volume(limit=5)

        if not stocks:
            return KakaoResponse.quick_replies(
                "📊 거래량 데이터를 불러오는 중입니다.",
                [
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "📉 급락주", "action": "message", "messageText": "/급락"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                ]
            )

        msg = "📊 거래량 TOP 5\n"
        for i, s in enumerate(stocks, 1):
            emoji = "📈" if s["change"] >= 0 else "📉"
            msg += f"\n{i}. {s['name']}"
            msg += f"\n   {s['price']:,}원 ({s['change']:+.2f}%) {emoji}\n"

        buttons = [{"label": f"📊 {s['name']}", "action": "message", "messageText": f"/시세 {s['name']}"} for s in stocks[:4]]
        buttons.append({"label": "🚀 급등주", "action": "message", "messageText": "/급등"})

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_top_gainers(self) -> Dict:
        """급등주 조회"""
        stocks = StockService.get_top_gainers(limit=10)

        if not stocks:
            return KakaoResponse.quick_replies(
                "📊 급등주 데이터를 불러오는 중입니다.",
                [
                    {"label": "🔥 삼성전자", "action": "message", "messageText": "/시세 삼성전자"},
                    {"label": "📉 급락주", "action": "message", "messageText": "/급락"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                ]
            )

        msg = "🚀 오늘의 급등주 TOP 10\n"
        for i, s in enumerate(stocks, 1):
            msg += f"\n{i}. {s['name']} 📈{s['change']:+.1f}% ({s['price']:,}원)"

        buttons = [{"label": f"🔥 {s['name']}", "action": "message", "messageText": f"/시세 {s['name']}"} for s in stocks[:3]]
        buttons.append({"label": "📉 급락주", "action": "message", "messageText": "/급락"})

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_top_losers(self) -> Dict:
        """급락주 조회"""
        stocks = StockService.get_top_losers(limit=10)

        if not stocks:
            return KakaoResponse.quick_replies(
                "📊 급락주 데이터를 불러오는 중입니다.",
                [
                    {"label": "💎 카카오", "action": "message", "messageText": "/시세 카카오"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                ]
            )

        msg = "📉 오늘의 급락주 TOP 10 (저점매수 기회?)\n"
        for i, s in enumerate(stocks, 1):
            msg += f"\n{i}. {s['name']} 🔻{s['change']:+.1f}% ({s['price']:,}원)"

        buttons = [{"label": f"💎 {s['name']}", "action": "message", "messageText": f"/시세 {s['name']}"} for s in stocks[:3]]
        buttons.append({"label": "🚀 급등주", "action": "message", "messageText": "/급등"})

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_market_overview(self) -> Dict:
        """시장 현황 조회"""
        market = StockService.get_market_overview()

        if not market:
            return KakaoResponse.quick_replies(
                "📊 시장 데이터를 불러오는 중입니다.",
                [
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "📉 급락주", "action": "message", "messageText": "/급락"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                ]
            )

        msg = "📈 시장 현황\n"

        if "kospi" in market:
            k = market["kospi"]
            emoji = "🔺" if k["change"] >= 0 else "🔻"
            msg += f"\n🇰🇷 KOSPI"
            msg += f"\n   {k['price']:,.2f} ({k['change']:+.2f}%) {emoji}\n"

        if "kosdaq" in market:
            k = market["kosdaq"]
            emoji = "🔺" if k["change"] >= 0 else "🔻"
            msg += f"\n💹 KOSDAQ"
            msg += f"\n   {k['price']:,.2f} ({k['change']:+.2f}%) {emoji}\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "📉 급락주", "action": "message", "messageText": "/급락"},
                {"label": "📊 거래량", "action": "message", "messageText": "/인기"}
            ]
        )

    def handle_news(self) -> Dict:
        """뉴스 조회"""
        parts = self.utterance.split(maxsplit=1)

        if len(parts) < 2:
            news = NewsService.get_market_news(limit=3)
            title = "📰 주식시장 뉴스"
            buttons = [
                {"label": "📰 삼성전자", "action": "message", "messageText": "/뉴스 삼성전자"},
                {"label": "📰 반도체", "action": "message", "messageText": "/뉴스 반도체"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
            ]
        else:
            query = parts[1].strip()
            news = NewsService.get_stock_news(query, limit=3)
            title = f"📰 '{query}' 관련 뉴스"
            buttons = [
                {"label": f"📈 {query} 매수", "action": "message", "messageText": f"/매수 {query} 10"},
                {"label": f"📉 {query} 매도", "action": "message", "messageText": f"/매도 {query} 10"},
                {"label": "📰 다른 뉴스", "action": "message", "messageText": "/뉴스"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
            ]

        if not news:
            return KakaoResponse.quick_replies(
                "📰 뉴스를 불러오지 못했습니다.",
                [
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                ]
            )

        msg = f"{title}\n"
        for i, n in enumerate(news, 1):
            t = n['title']
            if len(t) > 35:
                t = t[:35] + "..."
            msg += f"\n{i}. {t}"

        buttons.extend(self._get_game_buttons())
        return KakaoResponse.quick_replies(msg, buttons)
