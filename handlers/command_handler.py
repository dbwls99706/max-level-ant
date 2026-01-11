"""
명령어 처리 핸들러
- 사용자 입력 파싱
- 적절한 서비스 호출
- 응답 생성
"""
import re
from typing import Dict
from sqlalchemy.orm import Session

from services import UserService, StockService, TradeService, RankingService, MissionService
from utils import KakaoResponse
from config import GameConfig, Messages


class CommandHandler:
    """명령어 처리 클래스"""
    
    def __init__(self, db: Session, kakao_id: str, utterance: str):
        self.db = db
        self.kakao_id = kakao_id
        self.utterance = utterance.strip()
    
    def handle(self) -> Dict:
        """
        명령어 처리 메인 함수
        """
        cmd = self.utterance.lower()
        
        # 명령어 라우팅
        if cmd.startswith("/시작") or cmd.startswith("/start"):
            return self.handle_start()
        
        elif cmd.startswith("/출석") or cmd.startswith("/ㅊㅅ"):
            return self.handle_attendance()
        
        elif cmd.startswith("/광고") or cmd.startswith("/ㄱㄱ"):
            return self.handle_ad()
        
        elif cmd.startswith("/시세") or cmd.startswith("/ㅅㅅ"):
            return self.handle_price()
        
        elif cmd.startswith("/매수") or cmd.startswith("/ㅁㅅ"):
            return self.handle_buy()
        
        elif cmd.startswith("/매도") or cmd.startswith("/ㅁㄷ"):
            return self.handle_sell()
        
        elif cmd.startswith("/전량매수"):
            return self.handle_buy_max()
        
        elif cmd.startswith("/전량매도"):
            return self.handle_sell_all()
        
        elif cmd.startswith("/잔고") or cmd.startswith("/ㅈㄱ"):
            return self.handle_balance()
        
        elif cmd.startswith("/포트폴리오") or cmd.startswith("/포폴") or cmd.startswith("/ㅍㅍ"):
            return self.handle_portfolio()
        
        elif cmd.startswith("/랭킹") or cmd.startswith("/ㄹㅋ"):
            return self.handle_ranking()
        
        elif cmd.startswith("/내순위"):
            return self.handle_my_rank()
        
        elif cmd.startswith("/검색"):
            return self.handle_search()
        
        elif cmd.startswith("/인기") or cmd.startswith("/거래량"):
            return self.handle_top_volume()

        elif cmd.startswith("/급등") or cmd.startswith("/상승"):
            return self.handle_top_gainers()

        elif cmd.startswith("/급락") or cmd.startswith("/하락"):
            return self.handle_top_losers()

        elif cmd.startswith("/시장") or cmd.startswith("/지수"):
            return self.handle_market_overview()

        elif cmd.startswith("/미션"):
            return self.handle_mission()

        elif cmd.startswith("/업적"):
            return self.handle_achievements()

        elif cmd.startswith("/거래내역") or cmd.startswith("/ㄱㄹ"):
            return self.handle_transactions()

        elif cmd.startswith("/도움말") or cmd.startswith("/help") or cmd.startswith("/ㄷㅇㅁ"):
            return self.handle_help()
        
        else:
            return self.handle_unknown()
    
    def handle_start(self) -> Dict:
        """게임 시작 / 회원가입"""
        user, is_new = UserService.create_user(self.db, self.kakao_id)
        
        if is_new:
            welcome_msg = Messages.WELCOME.format(
                initial_cash=GameConfig.INITIAL_CASH,
                attendance=GameConfig.ATTENDANCE_REWARD,
                ad=GameConfig.AD_REWARD,
                max_ads=GameConfig.MAX_ADS_PER_DAY
            )
            return KakaoResponse.quick_replies(
                welcome_msg,
                [
                    {"label": "📅 출석", "action": "message", "messageText": "/출석"},
                    {"label": "💰 잔고", "action": "message", "messageText": "/잔고"},
                    {"label": "📖 도움말", "action": "message", "messageText": "/도움말"}
                ]
            )
        else:
            return KakaoResponse.simple_text(Messages.ALREADY_REGISTERED)
    
    def handle_attendance(self) -> Dict:
        """출석 체크"""
        success, reward, streak, cash = UserService.check_attendance(self.db, self.kakao_id)
        
        if not success and reward == 0 and streak == 0:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")
        
        if success:
            msg = Messages.ATTENDANCE_SUCCESS.format(
                reward=reward,
                streak=streak,
                cash=cash
            )
        else:
            msg = Messages.ATTENDANCE_ALREADY.format(streak=streak)
        
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📺 광고보기", "action": "message", "messageText": "/광고"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )
    
    def handle_ad(self) -> Dict:
        """광고 시청"""
        success, reward, remaining, cash = UserService.watch_ad(self.db, self.kakao_id)
        
        if not success and reward == 0 and remaining == 0 and cash == 0:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")
        
        if success:
            msg = Messages.AD_SUCCESS.format(
                reward=reward,
                remaining=remaining,
                cash=cash
            )
        else:
            msg = Messages.AD_LIMIT.format(max_ads=GameConfig.MAX_ADS_PER_DAY)
        
        return KakaoResponse.simple_text(msg)
    
    def handle_price(self) -> Dict:
        """시세 조회"""
        parts = self.utterance.split(maxsplit=1)
        
        if len(parts) < 2:
            return KakaoResponse.simple_text("사용법: /시세 [종목명]\n예: /시세 삼성전자")
        
        query = parts[1].strip()
        stock_info = StockService.get_price(query)
        
        if not stock_info:
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
                {"label": "📈 매수", "action": "message", "messageText": f"/매수 {stock_info['name']} "},
                {"label": "📉 매도", "action": "message", "messageText": f"/매도 {stock_info['name']} "}
            ]
        )
    
    def handle_buy(self) -> Dict:
        """주식 매수"""
        # /매수 삼성전자 10 형태 파싱
        parts = self.utterance.split()
        
        if len(parts) < 3:
            return KakaoResponse.simple_text("사용법: /매수 [종목명] [수량]\n예: /매수 삼성전자 10")
        
        stock_query = parts[1]
        
        try:
            quantity = int(parts[2])
        except ValueError:
            return KakaoResponse.simple_text("수량은 숫자로 입력해주세요.\n예: /매수 삼성전자 10")
        
        result = TradeService.buy_stock(self.db, self.kakao_id, stock_query, quantity)
        
        if not result["success"]:
            if "data" in result and "shortage" in result.get("data", {}):
                data = result["data"]
                msg = Messages.NOT_ENOUGH_CASH.format(
                    required=data["required"],
                    cash=data["cash"],
                    shortage=data["shortage"]
                )
            else:
                msg = result["message"]
            return KakaoResponse.simple_text(msg)
        
        data = result["data"]
        msg = Messages.BUY_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            cash=data["cash"]
        )

        # 미션 완료 알림
        if data.get("mission_reward"):
            mr = data["mission_reward"]
            bonus_text = " (보너스 요일!)" if mr.get("is_bonus_day") else ""
            msg += f"\n\n🎯 **일간 미션 완료!**{bonus_text}\n💰 +{mr['reward']:,}원 획득!"

        # 업적 달성 알림
        if data.get("new_achievements"):
            for ach in data["new_achievements"]:
                msg += f"\n\n🏆 **업적 달성: {ach['name']}!**\n💰 +{ach['reward']:,}원 획득!"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": f"📊 {data['name']} 시세", "action": "message", "messageText": f"/시세 {data['name']}"}
            ]
        )
    
    def handle_sell(self) -> Dict:
        """주식 매도"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.simple_text("사용법: /매도 [종목명] [수량]\n예: /매도 삼성전자 10")

        stock_query = parts[1]

        try:
            quantity = int(parts[2])
        except ValueError:
            return KakaoResponse.simple_text("수량은 숫자로 입력해주세요.\n예: /매도 삼성전자 10")

        result = TradeService.sell_stock(self.db, self.kakao_id, stock_query, quantity)

        if not result["success"]:
            if "data" in result and "holding" in result.get("data", {}):
                data = result["data"]
                msg = Messages.NOT_ENOUGH_STOCK.format(
                    requested=data["requested"],
                    holding=data["holding"]
                )
            else:
                msg = result["message"]
            return KakaoResponse.simple_text(msg)

        data = result["data"]

        # 수익 텍스트
        if data["profit"] >= 0:
            profit_text = f"📈 수익: +{data['profit']:,}원 (+{data['profit_rate']:.2f}%)"
        else:
            profit_text = f"📉 손실: {data['profit']:,}원 ({data['profit_rate']:.2f}%)"

        msg = Messages.SELL_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            profit_text=profit_text,
            cash=data["cash"]
        )

        # 미션 완료 알림
        if data.get("mission_reward"):
            mr = data["mission_reward"]
            bonus_text = " (보너스 요일!)" if mr.get("is_bonus_day") else ""
            msg += f"\n\n🎯 **일간 미션 완료!**{bonus_text}\n💰 +{mr['reward']:,}원 획득!"

        # 업적 달성 알림
        if data.get("new_achievements"):
            for ach in data["new_achievements"]:
                msg += f"\n\n🏆 **업적 달성: {ach['name']}!**\n💰 +{ach['reward']:,}원 획득!"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"}
            ]
        )
    
    def handle_buy_max(self) -> Dict:
        """전량 매수"""
        parts = self.utterance.split()
        
        if len(parts) < 2:
            return KakaoResponse.simple_text("사용법: /전량매수 [종목명]\n예: /전량매수 삼성전자")
        
        stock_query = parts[1]
        result = TradeService.buy_max(self.db, self.kakao_id, stock_query)
        
        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])
        
        data = result["data"]
        msg = Messages.BUY_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            cash=data["cash"]
        )
        
        return KakaoResponse.simple_text(msg)
    
    def handle_sell_all(self) -> Dict:
        """전량 매도"""
        parts = self.utterance.split()
        
        if len(parts) < 2:
            return KakaoResponse.simple_text("사용법: /전량매도 [종목명]\n예: /전량매도 삼성전자")
        
        stock_query = parts[1]
        result = TradeService.sell_all(self.db, self.kakao_id, stock_query)
        
        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])
        
        data = result["data"]
        
        if data["profit"] >= 0:
            profit_text = f"📈 수익: +{data['profit']:,}원 (+{data['profit_rate']:.2f}%)"
        else:
            profit_text = f"📉 손실: {data['profit']:,}원 ({data['profit_rate']:.2f}%)"
        
        msg = Messages.SELL_SUCCESS.format(
            name=data["name"],
            quantity=data["quantity"],
            price=data["price"],
            total=data["total"],
            fee=data["fee"],
            profit_text=profit_text,
            cash=data["cash"]
        )
        
        return KakaoResponse.simple_text(msg)
    
    def handle_balance(self) -> Dict:
        """잔고 조회"""
        cash = UserService.get_balance(self.db, self.kakao_id)
        
        if cash is None:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")
        
        msg = Messages.BALANCE.format(cash=cash)
        
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "📈 인기종목", "action": "message", "messageText": "/인기"}
            ]
        )
    
    def handle_portfolio(self) -> Dict:
        """포트폴리오 조회"""
        portfolio = TradeService.get_portfolio(self.db, self.kakao_id)
        
        if portfolio is None:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")
        
        # 보유 주식 목록 생성
        if portfolio["holdings"]:
            holdings_text = ""
            for h in portfolio["holdings"]:
                emoji = "🔺" if h["profit_rate"] >= 0 else "🔻"
                holdings_text += f"\n┌ {h['name']} ({h['quantity']:,}주)"
                holdings_text += f"\n│ 평균단가: {h['avg_price']:,}원"
                holdings_text += f"\n│ 현재가: {h['current_price']:,}원"
                holdings_text += f"\n│ 수익률: {h['profit_rate']:+.2f}% {emoji}"
                holdings_text += f"\n└ 평가금액: {h['current_value']:,}원\n"
        else:
            holdings_text = "\n(보유 중인 주식이 없습니다)"
        
        msg = Messages.PORTFOLIO.format(
            cash=portfolio["cash"],
            holdings=holdings_text,
            total=portfolio["total_asset"],
            profit_rate=portfolio["profit_rate"]
        )
        
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"},
                {"label": "📊 인기종목", "action": "message", "messageText": "/인기"}
            ]
        )
    
    def handle_ranking(self) -> Dict:
        """랭킹 조회"""
        rankings = RankingService.get_ranking(self.db, limit=10)
        
        if not rankings:
            return KakaoResponse.simple_text("아직 랭킹 데이터가 없습니다.")
        
        ranking_list = ""
        for r in rankings:
            medal = ""
            if r["rank"] == 1:
                medal = "🥇"
            elif r["rank"] == 2:
                medal = "🥈"
            elif r["rank"] == 3:
                medal = "🥉"
            else:
                medal = f"{r['rank']}."
            
            emoji = "📈" if r["profit_rate"] >= 0 else "📉"
            ranking_list += f"\n{medal} {r['nickname']}"
            ranking_list += f"\n   {emoji} {r['profit_rate']:+.2f}% ({r['total_asset']:,}원)\n"
        
        msg = Messages.RANKING.format(ranking_list=ranking_list)
        
        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📍 내 순위", "action": "message", "messageText": "/내순위"}
            ]
        )
    
    def handle_my_rank(self) -> Dict:
        """내 순위 조회"""
        rank_info = RankingService.get_my_rank(self.db, self.kakao_id)
        
        if rank_info is None:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")
        
        msg = Messages.MY_RANK.format(
            rank=rank_info["rank"],
            total=rank_info["total"],
            profit_rate=rank_info["profit_rate"],
            total_asset=rank_info["total_asset"]
        )
        
        return KakaoResponse.simple_text(msg)
    
    def handle_search(self) -> Dict:
        """종목 검색"""
        parts = self.utterance.split(maxsplit=1)
        
        if len(parts) < 2:
            return KakaoResponse.simple_text("사용법: /검색 [키워드]\n예: /검색 반도체")
        
        query = parts[1].strip()
        results = StockService.search_stocks(query, limit=5)
        
        if not results:
            return KakaoResponse.simple_text(f"'{query}' 관련 종목을 찾을 수 없습니다.")
        
        msg = f"🔍 '{query}' 검색 결과:\n"
        for r in results:
            msg += f"\n• {r['name']} ({r['code']})"
        
        msg += "\n\n시세를 확인하려면 /시세 [종목명]"
        
        return KakaoResponse.simple_text(msg)
    
    def handle_top_volume(self) -> Dict:
        """거래량 상위 종목"""
        stocks = StockService.get_top_volume(limit=10)

        if not stocks:
            return KakaoResponse.simple_text("거래량 데이터를 조회할 수 없습니다.")

        msg = "📊 **거래량 TOP 10**\n"
        for i, s in enumerate(stocks, 1):
            emoji = "📈" if s["change"] >= 0 else "📉"
            msg += f"\n{i}. {s['name']}"
            msg += f"\n   {s['price']:,}원 ({s['change']:+.2f}%) {emoji}"
            msg += f"\n   거래량: {s['volume']:,}주\n"

        return KakaoResponse.simple_text(msg)

    def handle_transactions(self) -> Dict:
        """거래 내역 조회"""
        # 유저 확인 먼저
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")

        transactions = TradeService.get_transactions(self.db, self.kakao_id, limit=10)

        if not transactions:
            return KakaoResponse.simple_text("거래 내역이 없습니다.\n\n/시세 [종목명] 으로 주식을 검색해보세요!")

        msg = "📜 **최근 거래 내역**\n"
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

    def handle_top_gainers(self) -> Dict:
        """급등주 조회"""
        stocks = StockService.get_top_gainers(limit=10)

        if not stocks:
            return KakaoResponse.simple_text("급등주 데이터를 조회할 수 없습니다.")

        msg = "🚀 **오늘의 급등주 TOP 10**\n"
        for i, s in enumerate(stocks, 1):
            msg += f"\n{i}. {s['name']}"
            msg += f"\n   {s['price']:,}원 (📈 {s['change']:+.2f}%)"
            msg += f"\n   거래량: {s['volume']:,}주\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📉 급락주", "action": "message", "messageText": "/급락"},
                {"label": "📊 거래량", "action": "message", "messageText": "/인기"}
            ]
        )

    def handle_top_losers(self) -> Dict:
        """급락주 조회"""
        stocks = StockService.get_top_losers(limit=10)

        if not stocks:
            return KakaoResponse.simple_text("급락주 데이터를 조회할 수 없습니다.")

        msg = "📉 **오늘의 급락주 TOP 10**\n"
        for i, s in enumerate(stocks, 1):
            msg += f"\n{i}. {s['name']}"
            msg += f"\n   {s['price']:,}원 (🔻 {s['change']:+.2f}%)"
            msg += f"\n   거래량: {s['volume']:,}주\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "📊 거래량", "action": "message", "messageText": "/인기"}
            ]
        )

    def handle_market_overview(self) -> Dict:
        """시장 현황 조회"""
        market = StockService.get_market_overview()

        if not market:
            return KakaoResponse.simple_text("시장 데이터를 조회할 수 없습니다.")

        msg = "📈 **시장 현황**\n"

        if "kospi" in market:
            k = market["kospi"]
            emoji = "🔺" if k["change"] >= 0 else "🔻"
            msg += f"\n🇰🇷 **KOSPI**"
            msg += f"\n   {k['price']:,.2f} ({k['change']:+.2f}%) {emoji}\n"

        if "kosdaq" in market:
            k = market["kosdaq"]
            emoji = "🔺" if k["change"] >= 0 else "🔻"
            msg += f"\n💹 **KOSDAQ**"
            msg += f"\n   {k['price']:,.2f} ({k['change']:+.2f}%) {emoji}\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                {"label": "📉 급락주", "action": "message", "messageText": "/급락"},
                {"label": "📊 거래량", "action": "message", "messageText": "/인기"}
            ]
        )

    def handle_mission(self) -> Dict:
        """일간 미션 현황"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")

        status = MissionService.get_mission_status(self.db, self.kakao_id)
        mission = status["daily_mission"]

        # 주간 보너스 체크
        bonus_text = ""
        if status["is_bonus_day"]:
            bonus_text = f"\n\n🎉 **오늘은 보너스 요일!** (보상 {status['bonus_multiplier']}배)"

        # 미션 상태
        if mission["completed"]:
            mission_status = "✅ 완료!"
        else:
            mission_status = f"{mission['progress']}/{mission['target']}회"

        msg = f"""📋 **일간 미션**{bonus_text}

🎯 **오늘의 미션**: {GameConfig.DAILY_MISSION_TRADE_COUNT}회 거래하기
📊 진행 상황: {mission_status}
💰 보상: {mission['reward']:,}원

📈 총 거래 횟수: {status['total_trades']:,}회
💵 누적 실현 수익: {status['total_profit_realized']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 업적", "action": "message", "messageText": "/업적"},
                {"label": "📊 인기종목", "action": "message", "messageText": "/인기"}
            ]
        )

    def handle_achievements(self) -> Dict:
        """업적 현황"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.simple_text("먼저 /시작 으로 게임을 시작해주세요.")

        status = MissionService.get_mission_status(self.db, self.kakao_id)

        msg = f"""🏆 **업적 현황
달성: {status['achievements_completed']}/{status['achievements_total']}개

"""
        # 달성한 업적
        if status["achievements"]:
            msg += "**✅ 달성한 업적**\n"
            for ach in status["achievements"]:
                msg += f"{ach['icon']} {ach['name']}\n"
            msg += "\n"

        # 미달성 업적 (처음 3개만)
        if status["available_achievements"]:
            msg += "**🎯 도전 중**\n"
            for ach in status["available_achievements"][:3]:
                msg += f"⬜ {ach['name']}: {ach['description']}\n"
                msg += f"   보상: {ach['reward']:,}원\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📋 미션", "action": "message", "messageText": "/미션"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    def handle_help(self) -> Dict:
        """도움말"""
        return KakaoResponse.simple_text(Messages.HELP)
    
    def handle_unknown(self) -> Dict:
        """알 수 없는 명령어"""
        return KakaoResponse.quick_replies(
            Messages.UNKNOWN_COMMAND,
            [
                {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
                {"label": "🎮 시작하기", "action": "message", "messageText": "/시작"}
            ]
        )
