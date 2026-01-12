"""
명령어 처리 핸들러
- 사용자 입력 파싱
- 적절한 서비스 호출
- 응답 생성
"""
import re
from typing import Dict
from sqlalchemy.orm import Session

from services import (
    UserService, StockService, TradeService, RankingService,
    MissionService, GameService, NewsService, BattleService,
    ChallengeService, MilestoneService, AssetService
)
from utils import KakaoResponse, get_streak_display, get_profit_bar, get_tier_title, validate_nickname, validate_quantity
from config import GameConfig, Messages, is_market_closed


class CommandHandler:
    """명령어 처리 클래스"""

    def __init__(self, db: Session, kakao_id: str, utterance: str, nickname: str = None):
        self.db = db
        self.kakao_id = kakao_id
        self.utterance = utterance.strip()
        self.nickname = nickname

    def _get_game_buttons(self) -> list:
        """장 마감 시간에만 게임 버튼 반환"""
        if is_market_closed():
            return [
                {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                {"label": "🎰 게임", "action": "message", "messageText": "/게임"}
            ]
        return []
    
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
        
        # 광고 기능 비활성화 (수익 발생 방지)
        elif cmd.startswith("/광고") or cmd.startswith("/ㄱㄱ"):
            return KakaoResponse.simple_text("🚫 광고 기능은 현재 비활성화되어 있습니다.")
        
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

        elif cmd.startswith("/뉴스") or cmd.startswith("/ㄴㅅ"):
            return self.handle_news()

        elif cmd.startswith("/미션"):
            return self.handle_mission()

        elif cmd.startswith("/업적"):
            return self.handle_achievements()

        elif cmd.startswith("/거래내역") or cmd.startswith("/ㄱㄹ"):
            return self.handle_transactions()

        # 미니게임
        elif cmd.startswith("/복권") or cmd.startswith("/ㅂㄱ"):
            return self.handle_lottery()

        elif cmd.startswith("/슬롯머신") or cmd.startswith("/ㅅㄹㅁ"):
            return self.handle_slot()

        elif cmd.startswith("/동전") or cmd.startswith("/코인"):
            return self.handle_coin()

        elif cmd.startswith("/하이로우") or cmd.startswith("/ㅎㅇㄹㅇ"):
            return self.handle_highlow()

        elif cmd.startswith("/게임") or cmd.startswith("/미니게임"):
            return self.handle_game_menu()

        elif cmd.startswith("/닉네임") or cmd.startswith("/ㄴㄴ"):
            return self.handle_nickname()

        # 배틀 시스템
        elif cmd.startswith("/배틀설명"):
            return self.handle_battle_help()

        elif cmd.startswith("/배틀생성") or cmd.startswith("/배틀"):
            return self.handle_battle_create()

        elif cmd.startswith("/배틀참가"):
            return self.handle_battle_join()

        elif cmd.startswith("/배틀결과"):
            return self.handle_battle_result()

        elif cmd.startswith("/배틀목록") or cmd.startswith("/대기배틀"):
            return self.handle_battle_list()

        # 주간 챌린지
        elif cmd.startswith("/챌린지") or cmd.startswith("/주간"):
            return self.handle_challenge()

        elif cmd.startswith("/챌린지보상"):
            return self.handle_challenge_reward()

        # 마일스톤
        elif cmd.startswith("/마일스톤") or cmd.startswith("/목표"):
            return self.handle_milestone()

        elif cmd.startswith("/마일스톤보상"):
            return self.handle_milestone_reward()

        # 자산 차트
        elif cmd.startswith("/차트") or cmd.startswith("/자산차트"):
            return self.handle_asset_chart()

        elif cmd.startswith("/도움말") or cmd.startswith("/help") or cmd.startswith("/ㄷㅇㅁ"):
            return self.handle_help()

        else:
            return self.handle_unknown()
    
    def handle_start(self) -> Dict:
        """게임 시작 / 회원가입"""
        user, is_new = UserService.create_user(self.db, self.kakao_id, self.nickname)

        if is_new:
            welcome_msg = Messages.WELCOME.format(initial_cash=GameConfig.INITIAL_CASH)
            buttons = [
                {"label": "📅 출석 +200만", "action": "message", "messageText": "/출석"},
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

        # 스트릭 시각화
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

    # handle_ad() 제거됨 - 광고 기능 비활성화

    def handle_price(self) -> Dict:
        """시세 조회"""
        parts = self.utterance.split(maxsplit=1)

        if len(parts) < 2:
            # 종목명 없으면 인기 종목 추천
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
            # 포트폴리오에서 종목 검색 시도
            holding = TradeService.find_holding_by_name(self.db, self.kakao_id, query)
            if holding:
                # 포트폴리오에서 찾음 - 종목코드로 시세 조회
                stock_info = StockService.get_price(holding.stock_code)
                if stock_info:
                    # 포트폴리오의 종목명 사용 (API 이름이 코드일 수 있음)
                    stock_info["name"] = holding.stock_name
                    StockService._cache_stock(holding.stock_code, holding.stock_name)

        if not stock_info:
            # 유사 종목 추천
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

        # 원클릭 매수 버튼 (1주, 10주, 100주, 전량)
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
        # /매수 삼성전자 10 형태 파싱
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

        stock_query = parts[1]

        try:
            quantity = int(parts[2])
        except ValueError:
            return KakaoResponse.quick_replies(
                "수량은 숫자로 입력해주세요.\n예: /매수 삼성전자 10",
                [
                    {"label": f"📈 {parts[1]} 1주", "action": "message", "messageText": f"/매수 {parts[1]} 1"},
                    {"label": f"📈 {parts[1]} 10주", "action": "message", "messageText": f"/매수 {parts[1]} 10"}
                ]
            )
        
        result = TradeService.buy_stock(self.db, self.kakao_id, stock_query, quantity)
        
        if not result["success"]:
            if "data" in result and "shortage" in result.get("data", {}):
                data = result["data"]
                msg = Messages.NOT_ENOUGH_CASH.format(
                    required=data["required"],
                    cash=data["cash"],
                    shortage=data["shortage"]
                )
                # 돈 버는 방법 안내
                return KakaoResponse.quick_replies(
                    msg,
                    [
                        {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                        {"label": "🎰 복권", "action": "message", "messageText": "/복권"},
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

        # 미션 완료 알림
        if data.get("mission_reward"):
            mr = data["mission_reward"]
            bonus_text = " (보너스 요일!)" if mr.get("is_bonus_day") else ""
            msg += f"\n\n🎯 일간 미션 완료!{bonus_text}\n💰 +{mr['reward']:,}원 획득!"

        # 업적 달성 알림
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

        stock_query = parts[1]

        try:
            quantity = int(parts[2])
        except ValueError:
            return KakaoResponse.quick_replies(
                "수량은 숫자로 입력해주세요.\n예: /매도 삼성전자 10",
                [
                    {"label": f"📉 {parts[1]} 전량", "action": "message", "messageText": f"/전량매도 {parts[1]}"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        result = TradeService.sell_stock(self.db, self.kakao_id, stock_query, quantity)

        if not result["success"]:
            if "data" in result and "holding" in result.get("data", {}):
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
            msg += f"\n\n🎯 일간 미션 완료!{bonus_text}\n💰 +{mr['reward']:,}원 획득!"

        # 업적 달성 알림
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

        stock_query = parts[1]
        result = TradeService.buy_max(self.db, self.kakao_id, stock_query)

        if not result["success"]:
            # 잔고 부족 시 돈 버는 방법 안내
            if "잔고" in result["message"]:
                return KakaoResponse.quick_replies(
                    result["message"],
                    [
                        {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                        {"label": "🎰 복권", "action": "message", "messageText": "/복권"},
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

        stock_query = parts[1]
        result = TradeService.sell_all(self.db, self.kakao_id, stock_query)

        if not result["success"]:
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
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        # 보유 주식 목록 생성
        buttons = []
        if portfolio["holdings"]:
            holdings_text = ""
            for h in portfolio["holdings"]:
                emoji = "🔺" if h["profit_rate"] >= 0 else "🔻"
                holdings_text += f"\n{h['name']} {h['quantity']:,}주"
                holdings_text += f"\n  {h['current_price']:,}원 ({h['profit_rate']:+.1f}%) {emoji}\n"
                # 보유 주식 전량매도 버튼 추가 (최대 4개)
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

        # 시각적 요소 추가
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

        return KakaoResponse.quick_replies(msg, buttons)
    
    def handle_ranking(self) -> Dict:
        """랭킹 조회"""
        rankings = RankingService.get_ranking(self.db, limit=10)
        
        if not rankings:
            return KakaoResponse.quick_replies(
                "아직 랭킹 데이터가 없습니다.\n게임을 시작해서 첫 번째 랭커가 되어보세요!",
                [
                    {"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )
        
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
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        msg = Messages.MY_RANK.format(
            rank=rank_info["rank"],
            total=rank_info["total"],
            profit_rate=rank_info["profit_rate"],
            total_asset=rank_info["total_asset"]
        )

        buttons = [
            {"label": "🏆 전체 랭킹", "action": "message", "messageText": "/랭킹"},
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
        ]

        return KakaoResponse.quick_replies(msg, buttons)
    
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
        results = StockService.search_stocks(query, limit=3)

        if not results:
            return KakaoResponse.quick_replies(
                f"'{query}' 관련 종목을 찾을 수 없습니다.",
                [
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
                    {"label": "📊 인기종목", "action": "message", "messageText": "/인기"},
                ]
            )

        msg = f"🔍 '{query}' 검색 결과"

        # 검색 결과 버튼
        buttons = [{"label": f"📊 {r['name']}", "action": "message", "messageText": f"/시세 {r['name']}"} for r in results[:3]]
        buttons.append({"label": "🚀 급등주", "action": "message", "messageText": "/급등"})

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

        # 상위 종목 버튼
        buttons = [{"label": f"📊 {s['name']}", "action": "message", "messageText": f"/시세 {s['name']}"} for s in stocks[:4]]
        buttons.append({"label": "🚀 급등주", "action": "message", "messageText": "/급등"})

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_transactions(self) -> Dict:
        """거래 내역 조회"""
        # 유저 확인 먼저
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

        # 버튼은 3개만
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

        # 버튼은 3개만
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
            # 종목명 없으면 시장 뉴스
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
            # 해당 종목 매수/매도 + 다른 뉴스 보기
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
            # 제목이 30자 넘으면 자르기
            t = n['title']
            if len(t) > 35:
                t = t[:35] + "..."
            msg += f"\n{i}. {t}"

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_mission(self) -> Dict:
        """일간 미션 현황"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        status = MissionService.get_mission_status(self.db, self.kakao_id)
        mission = status["daily_mission"]

        # 주간 보너스 체크
        bonus_text = ""
        if status["is_bonus_day"]:
            bonus_text = f"\n\n🎉 오늘은 보너스 요일! (보상 {status['bonus_multiplier']}배)"

        # 미션 상태
        if mission["completed"]:
            mission_status = "✅ 완료!"
        else:
            mission_status = f"{mission['progress']}/{mission['target']}회"

        msg = f"""📋 일간 미션{bonus_text}

🎯 오늘의 미션: {GameConfig.DAILY_MISSION_TRADE_COUNT}회 거래하기
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
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        status = MissionService.get_mission_status(self.db, self.kakao_id)

        msg = f"""🏆 업적 현황
달성: {status['achievements_completed']}/{status['achievements_total']}개

"""
        # 달성한 업적
        if status["achievements"]:
            msg += "✅ 달성한 업적\n"
            for ach in status["achievements"]:
                msg += f"{ach['icon']} {ach['name']}\n"
            msg += "\n"

        # 미달성 업적 (처음 3개만)
        if status["available_achievements"]:
            msg += "🎯 도전 중\n"
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

    # ==========================================
    # 미니게임 핸들러
    # ==========================================

    def handle_game_menu(self) -> Dict:
        """게임 메뉴"""
        msg = """🎰 미니게임

🎫 /복권 - 1만원 복권 (1일 5회)
🎰 /슬롯머신 [금액] - 슬롯머신 (777 잭팟!)
🪙 /동전 [금액] [앞/뒤] - 동전던지기 (x1.95)
🎲 /하이로우 [금액] [높/낮] - 숫자게임 (x1.9)

⏰ 슬롯/동전/하이로우는 장 마감 후 이용 가능"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎫 무료복권", "action": "message", "messageText": "/복권"},
                {"label": "🎰 슬롯 5만", "action": "message", "messageText": "/슬롯머신 50000"},
                {"label": "🪙 동전 10만", "action": "message", "messageText": "/동전 100000 앞"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_lottery(self) -> Dict:
        """복권 긁기"""
        result = GameService.play_lottery(self.db, self.kakao_id)

        if not result["success"]:
            # 복권 한도 도달 또는 잔고 부족 시 다른 활동 안내
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 10000"},
                    {"label": "🪙 동전던지기", "action": "message", "messageText": "/동전 10000"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        # 등급별 이모지 효과
        tier = result["tier"]
        if "대박" in tier:
            effect = "🎆🎇🎆🎇🎆"
        elif "1등" in tier:
            effect = "✨✨✨"
        elif "2등" in tier:
            effect = "🎉🎉"
        elif "3등" in tier:
            effect = "🎊"
        else:
            effect = ""

        remaining = result.get("remaining", 0)
        profit = result.get("profit", 0)
        profit_emoji = "📈" if profit > 0 else "📉" if profit < 0 else "➖"
        profit_text = f"+{profit:,}" if profit > 0 else f"{profit:,}"

        msg = f"""🎫 복권 긁기 {effect}

{tier}! {result['message']}

🎟️ 복권 가격: -{result['cost']:,}원
💰 당첨금: +{result['reward']:,}원
{profit_emoji} 순이익: {profit_text}원

📍 오늘 남은 횟수: {remaining}회
💵 현재 잔고: {result['cash']:,}원"""

        buttons = []
        if remaining > 0:
            buttons.append({"label": "🎫 한번 더!", "action": "message", "messageText": "/복권"})
        buttons.extend([
            {"label": "🎰 슬롯머신", "action": "message", "messageText": "/슬롯머신 50000"},
            {"label": "🚀 급등주", "action": "message", "messageText": "/급등"},
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_slot(self) -> Dict:
        """슬롯머신"""
        parts = self.utterance.split()

        # 기본 배팅금 5만원
        bet = 50_000
        if len(parts) >= 2:
            try:
                bet = int(parts[1].replace(",", ""))
            except ValueError:
                return KakaoResponse.quick_replies(
                    "배팅금은 숫자로 입력해주세요.\n예: /슬롯머신 50000",
                    [
                        {"label": "🎰 1만원", "action": "message", "messageText": "/슬롯머신 10000"},
                        {"label": "🎰 5만원", "action": "message", "messageText": "/슬롯머신 50000"},
                        {"label": "🎰 10만원", "action": "message", "messageText": "/슬롯머신 100000"}
                    ]
                )

        result = GameService.play_slot(self.db, self.kakao_id, bet)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                    {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        slots = result["slots"]
        slot_display = f"[ {slots[0]} | {slots[1]} | {slots[2]} ]"

        if result["jackpot"]:
            effect = "🎆 JACKPOT!!! 🎆"
        elif result["multiplier"] >= 5:
            effect = "🎉 BIG WIN! 🎉"
        elif result["multiplier"] > 0:
            effect = "✨ WIN! ✨"
        else:
            effect = "💨 실패..."

        if result["profit"] >= 0:
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            profit_text = f"📉 {result['profit']:,}원"

        msg = f"""🎰 슬롯머신

{slot_display}

{effect}

💰 배팅: {result['bet']:,}원
🎯 배율: x{result['multiplier']}
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎰 한번 더!", "action": "message", "messageText": f"/슬롯머신 {bet}"},
                {"label": "🎰 2배 배팅", "action": "message", "messageText": f"/슬롯머신 {bet * 2}"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_coin(self) -> Dict:
        """동전 던지기"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "🪙 동전 던지기\n\n사용법: /동전 [금액] [앞/뒤]\n예: /동전 100000 앞",
                [
                    {"label": "🪙 10만 앞", "action": "message", "messageText": "/동전 100000 앞"},
                    {"label": "🪙 10만 뒤", "action": "message", "messageText": "/동전 100000 뒤"},
                    {"label": "🪙 50만 앞", "action": "message", "messageText": "/동전 500000 앞"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "배팅금은 숫자로 입력해주세요.",
                [
                    {"label": "🪙 10만 앞", "action": "message", "messageText": "/동전 100000 앞"},
                    {"label": "🪙 10만 뒤", "action": "message", "messageText": "/동전 100000 뒤"}
                ]
            )

        choice = parts[2]
        result = GameService.play_coin_flip(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                    {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        if result["won"]:
            effect = "🎉 WIN!"
            profit_text = f"📈 +{result['profit']:,}원"
        else:
            effect = "💨 LOSE"
            profit_text = f"📉 {result['profit']:,}원"

        msg = f"""🪙 동전 던지기

{result['emoji']} 결과: {result['result']}!
🎯 선택: {result['choice']}

{effect}

💰 배팅: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🪙 한번 더!", "action": "message", "messageText": f"/동전 {bet} {choice}"},
                {"label": "🪙 반대로!", "action": "message", "messageText": f"/동전 {bet} {'뒤' if choice == '앞' else '앞'}"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_highlow(self) -> Dict:
        """하이로우 게임"""
        parts = self.utterance.split()

        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "🎲 하이로우\n\n1~100 중 숫자가 50보다 높을까 낮을까?\n\n사용법: /하이로우 [금액] [높/낮]",
                [
                    {"label": "🔼 10만 높", "action": "message", "messageText": "/하이로우 100000 높"},
                    {"label": "🔽 10만 낮", "action": "message", "messageText": "/하이로우 100000 낮"},
                    {"label": "🔼 50만 높", "action": "message", "messageText": "/하이로우 500000 높"}
                ]
            )

        try:
            bet = int(parts[1].replace(",", ""))
        except ValueError:
            return KakaoResponse.quick_replies(
                "배팅금은 숫자로 입력해주세요.",
                [
                    {"label": "🔼 10만 높", "action": "message", "messageText": "/하이로우 100000 높"},
                    {"label": "🔽 10만 낮", "action": "message", "messageText": "/하이로우 100000 낮"}
                ]
            )

        choice = parts[2]
        result = GameService.play_high_low(self.db, self.kakao_id, bet, choice)

        if not result["success"]:
            return KakaoResponse.quick_replies(
                result["message"],
                [
                    {"label": "📅 출석체크", "action": "message", "messageText": "/출석"},
                    {"label": "🎫 복권", "action": "message", "messageText": "/복권"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        # 무승부 체크
        if result["won"] is None:
            msg = f"""🎲 하이로우

🔢 숫자: {result['number']}

😮 무승부! (50)
배팅금 반환!

💵 잔고: {result['cash']:,}원"""
        else:
            if result["won"]:
                effect = "🎉 WIN!"
                profit_text = f"📈 +{result['profit']:,}원"
            else:
                effect = "💨 LOSE"
                profit_text = f"📉 {result['profit']:,}원"

            arrow = "🔼" if result["actual"] == "높" else "🔽"

            msg = f"""🎲 하이로우

🔢 숫자: {result['number']} {arrow}
🎯 선택: {result['choice']} / 정답: {result['actual']}

{effect}

💰 배팅: {result['bet']:,}원
{profit_text}
💵 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🔼 높!", "action": "message", "messageText": f"/하이로우 {bet} 높"},
                {"label": "🔽 낮!", "action": "message", "messageText": f"/하이로우 {bet} 낮"},
                {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
            ]
        )

    def handle_nickname(self) -> Dict:
        """닉네임 설정"""
        parts = self.utterance.split(maxsplit=1)

        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        if len(parts) < 2:
            current = user.nickname if user.nickname else "없음"
            return KakaoResponse.simple_text(
                f"🏷️ 닉네임 설정\n\n현재 닉네임: {current}\n\n사용법: /닉네임 [새 닉네임]\n예: /닉네임 투자왕"
            )

        new_nickname = parts[1].strip()

        # 닉네임 유효성 검사 (강화된 검증)
        is_valid, error_msg = validate_nickname(new_nickname)
        if not is_valid:
            return KakaoResponse.simple_text(error_msg)

        # 닉네임 중복 검사
        if UserService.is_nickname_taken(self.db, new_nickname, self.kakao_id):
            return KakaoResponse.simple_text(f"❌ '{new_nickname}'은(는) 이미 사용 중인 닉네임입니다.\n다른 닉네임을 선택해주세요.")

        # 닉네임 업데이트
        success, msg = UserService.update_nickname(self.db, self.kakao_id, new_nickname)

        if not success:
            return KakaoResponse.simple_text(msg)

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    # ==========================================
    # 배틀 시스템 핸들러
    # ==========================================

    def handle_battle_help(self) -> Dict:
        """배틀 설명"""
        msg = """⚔️ 배틀 시스템 설명

🎯 배틀이란?
다른 유저와 주가 예측 대결!
종목의 주가가 오를지 내릴지 예측하세요.

📝 진행 방식
1. 도전자가 종목/예측/배팅금으로 배틀 생성
2. 상대방이 배틀에 참가 (반대 방향 예측)
3. 60분 후 주가 변동으로 승패 결정
4. 승자가 배팅금 x2 획득!

💡 예시
• 도전자: 삼성전자 "상승" 예측 (10만원)
• 상대방: 삼성전자 "하락" 예측 (10만원)
• 60분 후 삼성전자가 올랐다면 → 도전자 승리!
• 승자는 20만원 획득 🎉

⚠️ 주의사항
• 한 번 생성/참가하면 취소 불가
• 여러 배틀 동시 참여 가능
• 무승부시 배팅금 반환

📋 명령어
/배틀 [종목] [상승/하락] [금액] - 생성
/배틀참가 [ID] - 참가
/배틀결과 [ID] - 결과 확인
/배틀목록 - 대기 중인 배틀"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "⚔️ 배틀생성", "action": "message", "messageText": "/배틀"},
                {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"}
            ]
        )

    def handle_battle_create(self) -> Dict:
        """배틀 생성"""
        parts = self.utterance.split()

        # /배틀 [종목] [상승/하락] [금액(선택)]
        if len(parts) < 3:
            return KakaoResponse.quick_replies(
                "⚔️ 배틀 생성\n\n사용법: /배틀 [종목] [상승/하락] [금액]\n예: /배틀 삼성전자 상승 100000\n\n❓ /배틀설명 으로 자세한 설명 확인",
                [
                    {"label": "❓ 배틀설명", "action": "message", "messageText": "/배틀설명"},
                    {"label": "⚔️ 삼성전자 상승", "action": "message", "messageText": "/배틀 삼성전자 상승 100000"},
                    {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"}
                ]
            )

        stock_name = parts[1]
        prediction = parts[2]
        bet = 100_000
        if len(parts) >= 4:
            try:
                bet = int(parts[3].replace(",", ""))
            except ValueError:
                pass

        result = BattleService.create_battle(
            self.db, self.kakao_id, stock_name, prediction, bet
        )

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""⚔️ 배틀 생성 완료!

📊 종목: {result['stock_name']}
💰 현재가: {result['current_price']:,}원
{result['pred_emoji']} 내 예측: {result['prediction']}
💵 배팅금: {result['bet_amount']:,}원
⏱️ 진행시간: {result['duration']}분

🆔 배틀 ID: {result['battle_id']}

⏳ 상대방 대기 중...
다른 유저가 '/배틀참가 {result['battle_id']}'로 참가하면 배틀 시작!

⚠️ 생성 후 취소 불가"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"},
                {"label": "⚔️ 추가 배틀", "action": "message", "messageText": "/배틀"}
            ]
        )

    def handle_battle_join(self) -> Dict:
        """배틀 참가"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.quick_replies(
                "⚔️ 배틀 참가\n\n사용법: /배틀참가 [배틀ID]\n예: /배틀참가 1",
                [{"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"}]
            )

        try:
            battle_id = int(parts[1])
        except ValueError:
            return KakaoResponse.simple_text("배틀 ID는 숫자입니다.")

        result = BattleService.join_battle(self.db, self.kakao_id, battle_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""⚔️ 배틀 시작!

📊 종목: {result['stock_name']}
💰 시작가: {result['start_price']:,}원
💵 배팅금: {result['bet_amount']:,}원

🔵 {result['challenger_name']}: {result['challenger_prediction']}
🔴 {result['opponent_name']}: {result['opponent_prediction']}

⏱️ {result['duration']}분 후 결과 확인!
/배틀결과 {result['battle_id']}"""

        return KakaoResponse.quick_replies(
            msg,
            [{"label": f"📊 결과확인", "action": "message", "messageText": f"/배틀결과 {result['battle_id']}"}]
        )

    def handle_battle_result(self) -> Dict:
        """배틀 결과 확인"""
        parts = self.utterance.split()

        if len(parts) < 2:
            return KakaoResponse.simple_text("사용법: /배틀결과 [배틀ID]")

        try:
            battle_id = int(parts[1])
        except ValueError:
            return KakaoResponse.simple_text("배틀 ID는 숫자입니다.")

        result = BattleService.check_battle_result(self.db, battle_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        if result.get("finished"):
            change_emoji = "📈" if result["price_change"] >= 0 else "📉"

            # 장 마감으로 종료된 경우
            market_note = ""
            if result.get("market_closed"):
                market_note = "\n⏰ (장 마감으로 조기 종료)"

            # 승패 여부에 따른 강조 표시
            if result['winner'] == "무승부":
                result_header = "🤝 무승부!"
                result_detail = "주가 변동 없음 - 배팅금 반환"
            else:
                result_header = f"🎊🎊🎊 배틀 종료!{market_note} 🎊🎊🎊"
                result_detail = f"🏆 승자: {result['winner']}"

            msg = f"""⚔️ 배틀 결과

{result_header}

📊 종목: {result['stock_name']}
💰 시작가: {result['start_price']:,}원
💰 종료가: {result['end_price']:,}원
{change_emoji} 변동: {result['price_change']:+,}원 ({result['change_rate']:+.2f}%)

👤 {result['challenger_name']} vs {result['opponent_name']}

{result_detail}
💰 상금: {result['prize']:,}원

GG! 다음 배틀도 기대해주세요! 🎮"""

            return KakaoResponse.quick_replies(
                msg,
                [
                    {"label": "⚔️ 새 배틀", "action": "message", "messageText": "/배틀"},
                    {"label": "📋 배틀목록", "action": "message", "messageText": "/배틀목록"},
                    {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
                ]
            )

        return KakaoResponse.simple_text(result["message"])

    def handle_battle_list(self) -> Dict:
        """대기 중인 배틀 목록"""
        battles = BattleService.get_waiting_battles(self.db)

        if not battles:
            return KakaoResponse.quick_replies(
                "⚔️ 대기 중인 배틀이 없습니다.\n새로운 배틀을 시작해보세요!",
                [
                    {"label": "⚔️ 배틀생성", "action": "message", "messageText": "/배틀"},
                    {"label": "🚀 급등주", "action": "message", "messageText": "/급등"}
                ]
            )

        msg = "⚔️ 대기 중인 배틀\n"
        buttons = []
        for b in battles[:5]:
            pred_emoji = "📈" if b["prediction"] == "상승" else "📉"
            msg += f"\n🆔 {b['id']} | {b['challenger']}"
            msg += f"\n   {b['stock_name']} {pred_emoji}{b['prediction']} ({b['bet_amount']:,}원)\n"

            if len(buttons) < 3:
                buttons.append({
                    "label": f"⚔️ #{b['id']} 참가",
                    "action": "message",
                    "messageText": f"/배틀참가 {b['id']}"
                })

        buttons.append({"label": "⚔️ 새 배틀", "action": "message", "messageText": "/배틀"})

        return KakaoResponse.quick_replies(msg, buttons)

    # ==========================================
    # 주간 챌린지 핸들러
    # ==========================================

    def handle_challenge(self) -> Dict:
        """주간 챌린지 현황"""
        result = ChallengeService.get_user_challenge_progress(self.db, self.kakao_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        ch = result["challenge"]
        pr = result["progress"]

        # 진행 바 생성
        progress_bar = "▓" * int(pr["progress_rate"] / 10) + "░" * (10 - int(pr["progress_rate"] / 10))

        status = "✅ 완료!" if pr["completed"] else f"{pr['current']}/{pr['target']}"
        reward_status = "(수령완료)" if pr["reward_claimed"] else ""

        msg = f"""🎯 주간 챌린지

{ch['description']}

📊 진행: [{progress_bar}] {pr['progress_rate']:.0f}%
🎯 상태: {status} {reward_status}
💰 보상: {ch['reward']:,}원

📅 기간: {ch['start_date']} ~ {ch['end_date']}"""

        buttons = []
        if pr["completed"] and not pr["reward_claimed"]:
            buttons.append({"label": "🎁 보상받기", "action": "message", "messageText": "/챌린지보상"})

        buttons.extend([
            {"label": "🏆 마일스톤", "action": "message", "messageText": "/마일스톤"},
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_challenge_reward(self) -> Dict:
        """챌린지 보상 수령"""
        result = ChallengeService.claim_challenge_reward(self.db, self.kakao_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""🎉 챌린지 보상 수령!

💰 +{result['reward']:,}원
💵 현재 잔고: {result['cash']:,}원"""

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🎯 챌린지", "action": "message", "messageText": "/챌린지"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    # ==========================================
    # 마일스톤 핸들러
    # ==========================================

    def handle_milestone(self) -> Dict:
        """마일스톤 현황"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        result = MilestoneService.get_user_milestones(self.db, self.kakao_id)

        msg = f"""🏆 마일스톤

✅ 달성: {len(result['achieved'])}개
⬜ 미달성: {len(result['pending'])}개
"""

        if result["unclaimed_rewards"] > 0:
            msg += f"🎁 미수령 보상: {result['unclaimed_rewards']:,}원\n"

        # 달성한 마일스톤 (최근 3개)
        if result["achieved"]:
            msg += "\n✅ 최근 달성\n"
            for m in result["achieved"][-3:]:
                claimed = "✓" if m["reward_claimed"] else "🎁"
                msg += f"  {m['name']} {claimed}\n"

        # 다음 목표 (2개)
        if result["pending"]:
            msg += "\n🎯 다음 목표\n"
            for m in result["pending"][:2]:
                msg += f"  {m['name']}\n"
                msg += f"    {m['description']} (보상: {m['reward']:,}원)\n"

        buttons = []
        if result["unclaimed_rewards"] > 0:
            buttons.append({"label": "🎁 전체 보상받기", "action": "message", "messageText": "/마일스톤보상"})

        buttons.extend([
            {"label": "🎯 챌린지", "action": "message", "messageText": "/챌린지"},
            {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
        ])

        return KakaoResponse.quick_replies(msg, buttons)

    def handle_milestone_reward(self) -> Dict:
        """마일스톤 보상 수령"""
        result = MilestoneService.claim_all_rewards(self.db, self.kakao_id)

        if not result["success"]:
            return KakaoResponse.simple_text(result["message"])

        msg = f"""🎉 마일스톤 보상 수령!

💰 +{result['total_reward']:,}원 ({result['count']}개)
💵 현재 잔고: {result['cash']:,}원

달성 마일스톤:
"""
        for m in result["milestones"]:
            msg += f"  ✅ {m}\n"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "🏆 마일스톤", "action": "message", "messageText": "/마일스톤"},
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"}
            ]
        )

    # ==========================================
    # 자산 차트 핸들러
    # ==========================================

    def handle_asset_chart(self) -> Dict:
        """자산 차트 조회"""
        user = UserService.get_user(self.db, self.kakao_id)
        if not user:
            return KakaoResponse.quick_replies(
                "먼저 /시작 으로 게임을 시작해주세요.",
                [{"label": "🎮 게임 시작", "action": "message", "messageText": "/시작"}]
            )

        # 오늘 자산 기록
        AssetService.record_daily_asset(self.db, self.kakao_id)

        # 차트 생성
        chart = AssetService.generate_ascii_chart(self.db, self.kakao_id, days=7)

        # 요약 정보
        summary = AssetService.get_asset_summary(self.db, self.kakao_id)

        msg = f"📊 내 자산 차트 (7일)\n\n{chart}"

        if summary.get("has_history") and summary.get("changes"):
            msg += "\n\n📈 기간별 변동"
            if "day" in summary["changes"]:
                d = summary["changes"]["day"]
                emoji = "🔺" if d["amount"] >= 0 else "🔻"
                msg += f"\n  어제대비: {d['amount']:+,}원 ({d['rate']:+.1f}%) {emoji}"

            if "week" in summary["changes"]:
                w = summary["changes"]["week"]
                emoji = "🔺" if w["amount"] >= 0 else "🔻"
                msg += f"\n  주간: {w['amount']:+,}원 ({w['rate']:+.1f}%) {emoji}"

        return KakaoResponse.quick_replies(
            msg,
            [
                {"label": "💼 포트폴리오", "action": "message", "messageText": "/포트폴리오"},
                {"label": "🏆 랭킹", "action": "message", "messageText": "/랭킹"}
            ]
        )

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
        return KakaoResponse.quick_replies(
            Messages.UNKNOWN_COMMAND,
            [
                {"label": "📖 도움말", "action": "message", "messageText": "/도움말"},
                {"label": "🎮 시작하기", "action": "message", "messageText": "/시작"}
            ]
        )
