"""
TradeService 단위 테스트
- 매수/매도 로직, 포트폴리오 조회
"""

from unittest.mock import patch, MagicMock

from services.trade_service import TradeService
from models import Holding
from config import GameConfig, ErrorCode


# 테스트용 가짜 주식 데이터
MOCK_STOCK = {
    "code": "005930",
    "name": "삼성전자",
    "price": 70_000,
    "change": 1.5,
    "volume": 1_000_000,
}


def _mock_stock_service(stock_info=None):
    """StockService 목 설정 헬퍼"""
    mock = MagicMock()
    mock.get_price.return_value = stock_info or MOCK_STOCK
    mock.search_stock.return_value = stock_info or MOCK_STOCK
    mock._cache_stock.return_value = None
    mock.batch_get_prices.return_value = {MOCK_STOCK["code"]: MOCK_STOCK["price"]}
    return mock


class TestBuyStock:
    """주식 매수 테스트"""

    def test_buy_stock_success(self, db, test_user):
        """기본 매수 성공"""
        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.MissionService") as MockMS,
            patch("services.trade_service.is_trading_available", return_value=True),
            patch("services.asset_service.AssetService.record_daily_asset"),
        ):
            MockSS.get_price.return_value = MOCK_STOCK
            MockSS._cache_stock.return_value = None
            MockMS.increment_trade_count.return_value = None
            MockMS.check_and_award_achievements.return_value = []

            result = TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", 10)

        assert result["success"] is True
        assert result["data"]["name"] == "삼성전자"
        assert result["data"]["quantity"] == 10

    def test_buy_stock_market_closed(self, db, test_user):
        """장 마감 시 매수 불가"""
        with (
            patch("services.trade_service.is_trading_available", return_value=False),
            patch(
                "services.trade_service.get_market_status_message",
                return_value="장 마감",
            ),
        ):
            result = TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", 10)

        assert result["success"] is False
        assert result["error_code"] == ErrorCode.MARKET_CLOSED

    def test_buy_stock_insufficient_balance(self, db, poor_user):
        """잔고 부족 매수"""
        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.is_trading_available", return_value=True),
        ):
            MockSS.get_price.return_value = MOCK_STOCK

            result = TradeService.buy_stock(db, poor_user.kakao_id, "삼성전자", 100)

        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INSUFFICIENT_BALANCE

    def test_buy_stock_not_found(self, db, test_user):
        """존재하지 않는 종목 매수 (시세 조회·종목 검색 모두 실패)"""
        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.is_trading_available", return_value=True),
        ):
            MockSS.get_price.return_value = None
            MockSS.search_stock.return_value = None  # 종목 자체가 인식 불가

            result = TradeService.buy_stock(db, test_user.kakao_id, "없는종목", 10)

        assert result["success"] is False
        assert result["error_code"] == ErrorCode.STOCK_NOT_FOUND

    def test_buy_stock_price_unavailable(self, db, test_user):
        """종목명은 인식되지만 KIS 시세 API가 일시적으로 응답하지 않는 경우"""
        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.is_trading_available", return_value=True),
        ):
            MockSS.get_price.return_value = None  # 시세 조회 실패
            MockSS.search_stock.return_value = {"code": "005930", "name": "삼성전자"}

            result = TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", 10)

        assert result["success"] is False
        # 오타로 오해시키지 않고 "시세 일시 불가"로 구분되어야 한다
        assert result["error_code"] == ErrorCode.PRICE_UNAVAILABLE

    def test_buy_stock_invalid_quantity_zero(self, db, test_user):
        """0주 매수 거부"""
        with patch("services.trade_service.is_trading_available", return_value=True):
            result = TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", 0)
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_QUANTITY

    def test_buy_stock_invalid_quantity_negative(self, db, test_user):
        """음수 수량 매수 거부"""
        with patch("services.trade_service.is_trading_available", return_value=True):
            result = TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", -5)
        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INVALID_QUANTITY

    def test_buy_stock_deducts_cash(self, db, test_user):
        """매수 후 현금 차감 확인"""
        initial_cash = test_user.cash
        quantity = 10
        price = MOCK_STOCK["price"]
        fee = int(price * quantity * GameConfig.TRADE_FEE_RATE)
        expected_deduction = price * quantity + fee

        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.MissionService") as MockMS,
            patch("services.trade_service.MilestoneService") as MockMile,
            patch("services.trade_service.is_trading_available", return_value=True),
            patch("services.asset_service.AssetService.record_daily_asset"),
        ):
            MockSS.get_price.return_value = MOCK_STOCK
            MockSS._cache_stock.return_value = None
            MockMS.increment_trade_count.return_value = None
            MockMS.check_and_award_achievements.return_value = []
            MockMile.check_milestones.return_value = []

            result = TradeService.buy_stock(
                db, test_user.kakao_id, "삼성전자", quantity
            )

        assert result["success"] is True
        db.refresh(test_user)
        assert test_user.cash == initial_cash - expected_deduction

    def test_buy_stock_creates_holding(self, db, test_user):
        """매수 후 보유 종목 생성 확인"""
        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.MissionService") as MockMS,
            patch("services.trade_service.is_trading_available", return_value=True),
            patch("services.asset_service.AssetService.record_daily_asset"),
        ):
            MockSS.get_price.return_value = MOCK_STOCK
            MockSS._cache_stock.return_value = None
            MockMS.increment_trade_count.return_value = None
            MockMS.check_and_award_achievements.return_value = []

            TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", 10)

        holding = (
            db.query(Holding)
            .filter(
                Holding.kakao_id == test_user.kakao_id,
                Holding.stock_code == MOCK_STOCK["code"],
            )
            .first()
        )
        assert holding is not None
        assert holding.quantity == 10

    def test_buy_stock_accumulates_holding(self, db, test_user):
        """동일 종목 추가 매수 시 수량 누적"""
        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.MissionService") as MockMS,
            patch("services.trade_service.is_trading_available", return_value=True),
            patch("services.asset_service.AssetService.record_daily_asset"),
        ):
            MockSS.get_price.return_value = MOCK_STOCK
            MockSS._cache_stock.return_value = None
            MockMS.increment_trade_count.return_value = None
            MockMS.check_and_award_achievements.return_value = []

            TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", 5)
            TradeService.buy_stock(db, test_user.kakao_id, "삼성전자", 3)

        holding = (
            db.query(Holding)
            .filter(
                Holding.kakao_id == test_user.kakao_id,
            )
            .first()
        )
        assert holding.quantity == 8


class TestSellStock:
    """주식 매도 테스트"""

    def _create_holding(self, db, user, stock_code, stock_name, quantity, avg_price):
        """테스트용 보유 종목 생성"""
        holding = Holding(
            kakao_id=user.kakao_id,
            stock_code=stock_code,
            stock_name=stock_name,
            quantity=quantity,
            avg_price=avg_price,
            total_invested=avg_price * quantity,
        )
        db.add(holding)
        db.commit()
        return holding

    def test_sell_stock_success(self, db, test_user):
        """기본 매도 성공"""
        self._create_holding(db, test_user, "005930", "삼성전자", 10, 60_000)

        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.MissionService") as MockMS,
            patch("services.trade_service.is_trading_available", return_value=True),
            patch("services.asset_service.AssetService.record_daily_asset"),
        ):
            MockSS.get_price.return_value = MOCK_STOCK
            MockSS._cache_stock.return_value = None
            MockMS.increment_trade_count.return_value = None
            MockMS.check_and_award_achievements.return_value = []

            result = TradeService.sell_stock(db, test_user.kakao_id, "삼성전자", 5)

        assert result["success"] is True
        assert result["data"]["quantity"] == 5

    def test_sell_stock_insufficient_holdings(self, db, test_user):
        """보유량 초과 매도 거부"""
        self._create_holding(db, test_user, "005930", "삼성전자", 3, 60_000)

        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.is_trading_available", return_value=True),
        ):
            MockSS.get_price.return_value = MOCK_STOCK

            result = TradeService.sell_stock(db, test_user.kakao_id, "삼성전자", 10)

        assert result["success"] is False
        assert result["error_code"] == ErrorCode.INSUFFICIENT_STOCK

    def test_sell_stock_profit_calculation(self, db, test_user):
        """매도 수익 계산 정확성"""
        avg_price = 60_000
        sell_price = 70_000
        quantity = 5
        self._create_holding(db, test_user, "005930", "삼성전자", quantity, avg_price)

        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.MissionService") as MockMS,
            patch("services.trade_service.is_trading_available", return_value=True),
            patch("services.asset_service.AssetService.record_daily_asset"),
        ):
            MockSS.get_price.return_value = {**MOCK_STOCK, "price": sell_price}
            MockSS._cache_stock.return_value = None
            MockMS.increment_trade_count.return_value = None
            MockMS.check_and_award_achievements.return_value = []

            result = TradeService.sell_stock(
                db, test_user.kakao_id, "삼성전자", quantity
            )

        data = result["data"]
        total_amount = sell_price * quantity
        fee = int(total_amount * GameConfig.TRADE_FEE_RATE)
        net_amount = total_amount - fee
        cost = avg_price * quantity
        expected_profit = net_amount - cost

        assert data["profit"] == expected_profit
        assert data["profit_rate"] > 0

    def test_sell_all_removes_holding(self, db, test_user):
        """전량 매도 후 보유 종목 삭제"""
        self._create_holding(db, test_user, "005930", "삼성전자", 5, 60_000)

        with (
            patch("services.trade_service.StockService") as MockSS,
            patch("services.trade_service.MissionService") as MockMS,
            patch("services.trade_service.is_trading_available", return_value=True),
            patch("services.asset_service.AssetService.record_daily_asset"),
        ):
            MockSS.get_price.return_value = MOCK_STOCK
            MockSS._cache_stock.return_value = None
            MockMS.increment_trade_count.return_value = None
            MockMS.check_and_award_achievements.return_value = []

            TradeService.sell_stock(db, test_user.kakao_id, "삼성전자", 5)

        holding = (
            db.query(Holding)
            .filter(
                Holding.kakao_id == test_user.kakao_id,
            )
            .first()
        )
        assert holding is None


class TestPortfolio:
    """포트폴리오 조회 테스트"""

    def test_portfolio_empty(self, db, test_user):
        """보유 종목 없는 포트폴리오"""
        with patch("services.trade_service.StockService") as MockSS:
            MockSS.batch_get_prices.return_value = {}
            portfolio = TradeService.get_portfolio(db, test_user.kakao_id)

        assert portfolio is not None
        assert portfolio["cash"] == GameConfig.INITIAL_CASH
        assert portfolio["holdings"] == []

    def test_portfolio_nonexistent_user(self, db):
        """존재하지 않는 유저 포트폴리오"""
        portfolio = TradeService.get_portfolio(db, "nobody")
        assert portfolio is None
