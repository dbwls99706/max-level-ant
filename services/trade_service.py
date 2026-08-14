"""
주식 거래 서비스 (리팩토링)
- 매수/매도
- 포트폴리오 조회
- 트랜잭션 안전성 강화
- 오버플로우 방지
"""

from typing import Optional, Dict, List, Set
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import Holding, Transaction, User
from services.stock_service import StockService
from services.user_service import UserService
from services.mission_service import MissionService
from services.milestone_service import MilestoneService
from services.common import (
    get_user_with_error_for_update,
    validate_quantity,
    error_response,
    safe_add,
    safe_subtract,
)
from constants import TradeType
from errors import ErrorCode
from game_config import GameConfig
from market_calendar import is_trading_available, get_market_status_message
from messages import Messages
from utils import get_service_logger, log_trade

logger = get_service_logger()


class TradeService:
    """주식 거래 관련 서비스"""

    @staticmethod
    def find_holding_by_name(
        db: Session, kakao_id: str, stock_query: str
    ) -> Optional[Holding]:
        """
        유저 포트폴리오에서 종목명으로 검색
        동적 캐시가 사라져도 포트폴리오 종목은 찾을 수 있음
        """
        stock_query = stock_query.strip()

        # 1. 정확한 이름 매칭
        holding = (
            db.query(Holding)
            .filter(
                Holding.kakao_id == kakao_id,
                Holding.stock_name == stock_query,
                Holding.quantity > 0,
            )
            .first()
        )
        if holding:
            return holding

        # 2. 부분 이름 매칭
        holdings = (
            db.query(Holding)
            .filter(Holding.kakao_id == kakao_id, Holding.quantity > 0)
            .all()
        )

        for h in holdings:
            if stock_query in h.stock_name:
                return h

        return None

    @staticmethod
    def _safe_get_asset_and_profit(
        db: Session, kakao_id: str
    ) -> tuple[Optional[int], Optional[int]]:
        """총 자산·수익금 계산 (실패 시 (None, None), 세션 오염 방지 롤백)"""
        try:
            from services.asset_service import AssetService

            return AssetService.get_asset_and_profit(db, kakao_id)
        except Exception as e:
            db.rollback()
            logger.warning(f"총 자산 계산 실패 ({kakao_id}): {e}")
            return None, None

    @staticmethod
    def _update_trade_challenges(
        db: Session, kakao_id: str, total_asset: Optional[int]
    ) -> None:
        """거래 이벤트 기반 주간 챌린지 진행도 갱신 (실패해도 거래에는 영향 없음)"""
        try:
            from services.challenge_service import ChallengeService

            ChallengeService.update_challenge_progress(db, kakao_id, "TRADE_COUNT")
            ChallengeService.update_asset_challenges(db, kakao_id, total_asset)
        except Exception as e:
            db.rollback()
            logger.warning(f"챌린지 진행도 갱신 실패 ({kakao_id}): {e}")

    @staticmethod
    def _check_trading_time() -> Optional[Dict]:
        """거래 가능 시간 확인"""
        if not is_trading_available():
            status_msg = get_market_status_message()
            return error_response(
                ErrorCode.MARKET_CLOSED,
                Messages.MARKET_CLOSED_TRADING.format(status_msg=status_msg),
            )
        return None

    @staticmethod
    def _get_stock_info(db: Session, kakao_id: str, stock_query: str) -> tuple:
        """
        종목 정보 조회 (캐시 + 포트폴리오 폴백)

        Returns:
            (stock_info, error_response)
        """
        stock_info = StockService.get_price(stock_query)

        if not stock_info:
            holding = TradeService.find_holding_by_name(db, kakao_id, stock_query)
            if holding:
                stock_info = StockService.get_price(holding.stock_code)
                if stock_info:
                    stock_info["name"] = holding.stock_name
                    StockService._cache_stock(holding.stock_code, holding.stock_name)

        if not stock_info:
            # 종목명은 인식되지만 시세 API가 일시적으로 응답하지 않는 경우와
            # 정말로 종목을 찾지 못한 경우를 구분해 안내한다.
            if StockService.search_stock(stock_query):
                name = StockService.search_stock(stock_query)["name"]
                return None, error_response(
                    ErrorCode.PRICE_UNAVAILABLE,
                    Messages.STOCK_PRICE_UNAVAILABLE.format(name=name),
                )
            return None, error_response(
                ErrorCode.STOCK_NOT_FOUND, f"'{stock_query}' 종목을 찾을 수 없습니다."
            )

        return stock_info, None

    @staticmethod
    def _get_holding_fresh(db: Session, kakao_id: str, code: str) -> Optional[Holding]:
        """
        보유 종목을 최신 상태로 다시 읽는다.

        락 이전에 같은 종목을 읽었다면 identity map의 낡은 객체가 돌아오므로,
        락 획득 후 재검증에는 반드시 populate_existing()으로 갱신해 읽어야 한다.
        """
        return (
            db.query(Holding)
            .filter(Holding.kakao_id == kakao_id, Holding.stock_code == code)
            .populate_existing()
            .first()
        )

    @staticmethod
    def buy_stock(db: Session, kakao_id: str, stock_query: str, quantity: int) -> Dict:
        """
        주식 매수

        락 보유 시간을 줄이기 위해 외부 API(KIS 시세) 조회를 락 밖에서 끝낸다.
            종목 resolve + 시세 조회  ← 락 없음 (느릴 수 있는 구간)
                    ↓
            User FOR UPDATE
                    ↓
            잔고·보유량 재검증 + mutation + commit
        락 밖에서 읽은 값 중 신뢰하는 것은 '주가'뿐이고,
        돈과 보유량은 락을 잡은 뒤 다시 읽어 검증한다 (TOCTOU 방지).
        """
        # 거래 가능 시간 확인
        time_error = TradeService._check_trading_time()
        if time_error:
            return time_error

        # 수량 확인 (외부 호출 전에 걸러낸다)
        is_valid, qty_error = validate_quantity(quantity)
        if not is_valid:
            return error_response(ErrorCode.INVALID_QUANTITY, qty_error)

        # 종목 시세 조회 - 락을 잡기 전에 수행한다
        stock_info, stock_error = TradeService._get_stock_info(
            db, kakao_id, stock_query
        )
        if stock_error:
            return stock_error

        price_error = TradeService._check_price(stock_info)
        if price_error:
            return price_error

        # 여기서부터 락 구간
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        return TradeService._buy_stock_locked(db, user, stock_info, quantity)

    @staticmethod
    def _check_price(stock_info: Dict) -> Optional[Dict]:
        """주가 유효성 검사 (0원 또는 음수 방지)"""
        price = stock_info["price"]
        if price <= 0:
            logger.warning(
                f"비정상 주가 감지: {stock_info['name']}({stock_info['code']}) "
                f"= {price}원"
            )
            return error_response(
                ErrorCode.API_ERROR,
                f"'{stock_info['name']}' 시세가 비정상입니다. "
                f"잠시 후 다시 시도해주세요.",
            )
        return None

    @staticmethod
    def _buy_stock_locked(
        db: Session, user: User, stock_info: Dict, quantity: int
    ) -> Dict:
        """
        매수 실행 (락 보유 상태 전용)

        호출자는 user를 FOR UPDATE로 잠근 뒤 넘겨야 한다.
        외부 API 호출은 하지 않는다 - 락 보유 시간을 늘리기 때문이다.
        """
        kakao_id = user.kakao_id
        code = stock_info["code"]
        name = stock_info["name"]
        price = stock_info["price"]

        # 수량 재검증 (buy_max 등 다른 진입점도 이 함수를 쓴다)
        is_valid, qty_error = validate_quantity(quantity)
        if not is_valid:
            return error_response(ErrorCode.INVALID_QUANTITY, qty_error)

        # 종목 캐시 저장
        StockService._cache_stock(code, name)

        # 총 금액 계산 (수수료 포함)
        total_amount = price * quantity
        fee = int(total_amount * GameConfig.TRADE_FEE_RATE)
        required_cash = total_amount + fee

        # 금액 오버플로우 체크
        if required_cash > GameConfig.MAX_CASH:
            return error_response(
                ErrorCode.INVALID_AMOUNT, "거래 금액이 너무 큽니다. 수량을 줄여주세요."
            )

        # 잔고 확인 - 락을 잡고 읽은 최신 cash 기준
        if user.cash < required_cash:
            return error_response(
                ErrorCode.INSUFFICIENT_BALANCE,
                "잔고가 부족합니다.",
                data={
                    "required": required_cash,
                    "cash": user.cash,
                    "shortage": required_cash - user.cash,
                },
            )

        # 기존 보유 종목 확인 (락 이후 최신 상태로)
        holding = TradeService._get_holding_fresh(db, kakao_id, code)

        try:
            if holding:
                # 기존 보유 → 평균 단가 계산 (수수료 포함)
                total_qty = holding.quantity + quantity
                total_invested = holding.total_invested + total_amount + fee
                avg_price = total_invested // total_qty

                holding.quantity = total_qty
                holding.total_invested = total_invested
                holding.avg_price = avg_price
            else:
                # 신규 매수 (수수료 포함 평단가)
                total_invested = total_amount + fee
                holding = Holding(
                    kakao_id=kakao_id,
                    stock_code=code,
                    stock_name=name,
                    quantity=quantity,
                    avg_price=total_invested // quantity,
                    total_invested=total_invested,
                )
                db.add(holding)

            # 현금 차감
            user.cash = safe_subtract(user.cash, required_cash)

            # 거래 내역 기록
            transaction = Transaction(
                kakao_id=kakao_id,
                stock_code=code,
                stock_name=name,
                trade_type=TradeType.BUY,
                quantity=quantity,
                price=price,
                total_amount=total_amount,
                fee=fee,
            )
            db.add(transaction)

            db.commit()
            db.refresh(user)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"매수 DB 트랜잭션 실패: {e}")
            return error_response(
                ErrorCode.INTERNAL_ERROR, "거래 처리 중 오류가 발생했습니다."
            )

        # 미션 및 업적 처리
        mission_reward = MissionService.increment_trade_count(db, kakao_id)

        # 총 자산·수익금 계산 (업적/마일스톤/챌린지 판정용, 실패해도 거래에는 영향 없음)
        total_asset, total_profit = TradeService._safe_get_asset_and_profit(
            db, kakao_id
        )

        new_achievements = MissionService.check_and_award_achievements(
            db, kakao_id, total_profit=total_profit
        )

        # 마일스톤 자동 체크·지급 (수익금·거래 횟수 기준)
        new_milestones = MilestoneService.check_milestones(
            db,
            kakao_id,
            total_profit=total_profit,
            total_trades=user.total_trades,
        )

        # 주간 챌린지 진행도 갱신
        TradeService._update_trade_challenges(db, kakao_id, total_asset)

        # 감사 로그
        log_trade(
            kakao_id=kakao_id,
            trade_type="BUY",
            stock_code=code,
            stock_name=name,
            quantity=quantity,
            price=price,
            total_amount=total_amount,
            fee=fee,
            cash_after=user.cash,
        )

        # 자산 히스토리 기록 (실패해도 거래에는 영향 없음)
        try:
            from services.asset_service import AssetService

            AssetService.record_daily_asset(db, kakao_id)
        except Exception as e:
            db.rollback()  # 예외로 오염된 세션이 이후 커밋에 영향 주지 않도록
            logger.warning(f"자산 히스토리 기록 실패 (매수 후): {e}")

        return {
            "success": True,
            "message": "매수 완료",
            "data": {
                "code": code,
                "name": name,
                "quantity": quantity,
                "price": price,
                "total": total_amount,
                "fee": fee,
                "cash": user.cash,
                "mission_reward": mission_reward,
                "new_achievements": new_achievements,
                "new_milestones": new_milestones,
            },
        }

    @staticmethod
    def _resolve_stock_for_sell(db: Session, kakao_id: str, stock_query: str) -> tuple:
        """
        매도 대상 종목 resolve + 시세 조회 (락 없음)

        포트폴리오를 먼저 뒤지고, 없으면 일반 검색으로 넘어간다.
        여기서 읽은 보유 수량은 신뢰하지 않는다 - 락 이후 다시 읽는다.

        Returns:
            (stock_info, error_response)
        """
        holding = TradeService.find_holding_by_name(db, kakao_id, stock_query)

        if holding:
            code = holding.stock_code
            name = holding.stock_name
            stock_info = StockService.get_price(code)
            if not stock_info:
                return None, error_response(
                    ErrorCode.API_ERROR,
                    f"'{name}' 시세 조회 실패. 잠시 후 다시 시도해주세요.",
                )
            # 포트폴리오에 저장된 종목명을 우선한다
            stock_info = {**stock_info, "code": code, "name": name}
            StockService._cache_stock(code, name)
            return stock_info, None

        # 포트폴리오에 없으면 일반 검색
        stock_info = StockService.get_price(stock_query)
        if not stock_info:
            resolved = StockService.search_stock(stock_query)
            if resolved:
                return None, error_response(
                    ErrorCode.PRICE_UNAVAILABLE,
                    Messages.STOCK_PRICE_UNAVAILABLE.format(name=resolved["name"]),
                )
            return None, error_response(
                ErrorCode.STOCK_NOT_FOUND,
                f"'{stock_query}' 종목을 찾을 수 없습니다.",
            )
        return stock_info, None

    @staticmethod
    def sell_stock(db: Session, kakao_id: str, stock_query: str, quantity: int) -> Dict:
        """
        주식 매도

        매수와 같은 순서를 따른다.
            종목 resolve + 시세 조회  ← 락 없음
                    ↓
            User FOR UPDATE
                    ↓
            보유 수량 재조회·재검증 + mutation + commit
        """
        # 거래 가능 시간 확인
        time_error = TradeService._check_trading_time()
        if time_error:
            return time_error

        # 수량 확인 (외부 호출 전에 걸러낸다)
        is_valid, qty_error = validate_quantity(quantity)
        if not is_valid:
            return error_response(ErrorCode.INVALID_QUANTITY, qty_error)

        # 종목 resolve + 시세 조회 - 락을 잡기 전에 수행한다
        stock_info, stock_error = TradeService._resolve_stock_for_sell(
            db, kakao_id, stock_query
        )
        if stock_error:
            return stock_error

        price_error = TradeService._check_price(stock_info)
        if price_error:
            return price_error

        # 여기서부터 락 구간
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        return TradeService._sell_stock_locked(db, user, stock_info, quantity)

    @staticmethod
    def _sell_stock_locked(
        db: Session, user: User, stock_info: Dict, quantity: int
    ) -> Dict:
        """
        매도 실행 (락 보유 상태 전용)

        호출자는 user를 FOR UPDATE로 잠근 뒤 넘겨야 한다.
        외부 API 호출은 하지 않는다.
        """
        kakao_id = user.kakao_id
        code = stock_info["code"]
        name = stock_info["name"]
        price = stock_info["price"]

        is_valid, qty_error = validate_quantity(quantity)
        if not is_valid:
            return error_response(ErrorCode.INVALID_QUANTITY, qty_error)

        # 보유 수량은 락 이후 최신 상태로 다시 읽어 검증한다.
        # (락 밖에서 본 수량은 다른 요청이 이미 팔았을 수 있다)
        holding = TradeService._get_holding_fresh(db, kakao_id, code)
        if not holding or holding.quantity < quantity:
            holding_qty = holding.quantity if holding else 0
            return error_response(
                ErrorCode.INSUFFICIENT_STOCK,
                "보유 수량이 부족합니다.",
                data={"requested": quantity, "holding": holding_qty},
            )

        # 총 금액 계산
        total_amount = price * quantity
        fee = int(total_amount * GameConfig.TRADE_FEE_RATE)
        net_amount = total_amount - fee

        # 수익 계산
        cost_basis = holding.avg_price * quantity
        profit = net_amount - cost_basis
        profit_rate = round((profit / cost_basis) * 100, 2) if cost_basis > 0 else 0.0

        try:
            # 보유 수량 감소
            holding.quantity -= quantity
            holding.total_invested = safe_subtract(
                holding.total_invested, holding.avg_price * quantity
            )

            if holding.quantity == 0:
                db.delete(holding)

            # 현금 증가 (오버플로우 방지)
            user.cash = safe_add(user.cash, net_amount)

            # 거래 내역 기록
            transaction = Transaction(
                kakao_id=kakao_id,
                stock_code=code,
                stock_name=name,
                trade_type=TradeType.SELL,
                quantity=quantity,
                price=price,
                total_amount=total_amount,
                fee=fee,
                profit=profit,
                profit_rate=profit_rate,
            )
            db.add(transaction)

            db.commit()
            db.refresh(user)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"매도 DB 트랜잭션 실패: {e}")
            return error_response(
                ErrorCode.INTERNAL_ERROR, "거래 처리 중 오류가 발생했습니다."
            )

        # 미션 및 업적 처리
        mission_reward = MissionService.increment_trade_count(db, kakao_id)

        # 총 자산·수익금 계산 (업적/마일스톤/챌린지 판정용, 실패해도 거래에는 영향 없음)
        total_asset, total_profit = TradeService._safe_get_asset_and_profit(
            db, kakao_id
        )

        new_achievements = MissionService.check_and_award_achievements(
            db,
            kakao_id,
            trade_profit=profit if profit > 0 else 0,
            total_profit=total_profit,
        )

        # 마일스톤 자동 체크·지급 (수익금·거래 횟수 기준)
        new_milestones = MilestoneService.check_milestones(
            db,
            kakao_id,
            total_profit=total_profit,
            total_trades=user.total_trades,
        )

        # 주간 챌린지 진행도 갱신
        TradeService._update_trade_challenges(db, kakao_id, total_asset)

        # 감사 로그
        log_trade(
            kakao_id=kakao_id,
            trade_type="SELL",
            stock_code=code,
            stock_name=name,
            quantity=quantity,
            price=price,
            total_amount=total_amount,
            fee=fee,
            cash_after=user.cash,
            profit=profit,
            profit_rate=profit_rate,
        )

        # 자산 히스토리 기록 (실패해도 거래에는 영향 없음)
        try:
            from services.asset_service import AssetService

            AssetService.record_daily_asset(db, kakao_id)
        except Exception as e:
            db.rollback()  # 예외로 오염된 세션이 이후 커밋에 영향 주지 않도록
            logger.warning(f"자산 히스토리 기록 실패 (매도 후): {e}")

        return {
            "success": True,
            "message": "매도 완료",
            "data": {
                "code": code,
                "name": name,
                "quantity": quantity,
                "price": price,
                "total": total_amount,
                "fee": fee,
                "profit": profit,
                "profit_rate": profit_rate,
                "cash": user.cash,
                "mission_reward": mission_reward,
                "new_achievements": new_achievements,
                "new_milestones": new_milestones,
            },
        }

    @staticmethod
    def _max_affordable_quantity(cash: int, price: int) -> int:
        """
        주어진 현금으로 살 수 있는 최대 수량 (수수료 포함)

        buy_stock과 동일한 수수료 라운딩(내림)으로 필요 금액을 계산해
        float 오차로 경계 수량이 "잔고 부족"으로 실패하는 문제를 방지한다.
        """

        def required_cash(qty: int) -> int:
            amount = price * qty
            return amount + int(amount * GameConfig.TRADE_FEE_RATE)

        max_qty = int(cash / (price * (1 + GameConfig.TRADE_FEE_RATE)))
        max_qty = min(max_qty, GameConfig.MAX_QUANTITY)
        while max_qty > 0 and required_cash(max_qty) > cash:
            max_qty -= 1
        while max_qty < GameConfig.MAX_QUANTITY and required_cash(max_qty + 1) <= cash:
            max_qty += 1
        return max_qty

    @staticmethod
    def buy_max(db: Session, kakao_id: str, stock_query: str) -> Dict:
        """
        전량 매수 (보유 현금으로 최대 수량)

        수량이 잔고에 의존하므로 순서가 특히 중요하다.
            시세 조회 ← 락 없음
                ↓
            User FOR UPDATE
                ↓
            '락을 잡은 시점의' cash로 최대 수량 재계산
                ↓
            매수 실행
        락 밖의 잔고로 수량을 정하면 그 사이 잔고가 줄었을 때 초과 매수가 된다.
        """
        # 거래 가능 시간 확인 (예전에는 buy_stock에 위임했으나
        # 이제 락 안에서 직접 실행하므로 여기서 먼저 확인한다)
        time_error = TradeService._check_trading_time()
        if time_error:
            return time_error

        # 시세 조회 - 락 밖에서
        stock_info, stock_error = TradeService._get_stock_info(
            db, kakao_id, stock_query
        )
        if stock_error:
            return stock_error

        price_error = TradeService._check_price(stock_info)
        if price_error:
            return price_error

        # 여기서부터 락 구간
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 최대 수량은 반드시 '락으로 읽은 최신 cash' 기준으로 계산한다
        max_qty = TradeService._max_affordable_quantity(user.cash, stock_info["price"])
        if max_qty < 1:
            return error_response(ErrorCode.INSUFFICIENT_BALANCE, "잔고가 부족합니다.")

        return TradeService._buy_stock_locked(db, user, stock_info, max_qty)

    @staticmethod
    def sell_all(db: Session, kakao_id: str, stock_query: str) -> Dict:
        """
        전량 매도

        수량이 보유량에 의존하므로 buy_max와 같은 순서를 따른다.
            시세 조회 ← 락 없음
                ↓
            User FOR UPDATE
                ↓
            '락을 잡은 시점의' 보유 수량으로 전량 결정
                ↓
            매도 실행
        """
        time_error = TradeService._check_trading_time()
        if time_error:
            return time_error

        # 시세 조회 - 락 밖에서
        stock_info, stock_error = TradeService._resolve_stock_for_sell(
            db, kakao_id, stock_query
        )
        if stock_error:
            return stock_error

        price_error = TradeService._check_price(stock_info)
        if price_error:
            return price_error

        # 여기서부터 락 구간
        user, error = get_user_with_error_for_update(db, kakao_id)
        if error:
            return error

        # 전량 수량은 반드시 '락으로 읽은 최신 보유량' 기준으로 결정한다
        holding = TradeService._get_holding_fresh(db, kakao_id, stock_info["code"])
        if not holding or holding.quantity == 0:
            return error_response(
                ErrorCode.INSUFFICIENT_STOCK, "보유 중인 종목이 아닙니다."
            )

        return TradeService._sell_stock_locked(db, user, stock_info, holding.quantity)

    @staticmethod
    def get_portfolio(db: Session, kakao_id: str) -> Optional[Dict]:
        """
        포트폴리오 조회 (N+1 쿼리 최적화)
        """
        user = UserService.get_user(db, kakao_id)
        if not user:
            return None

        holdings = (
            db.query(Holding)
            .filter(Holding.kakao_id == kakao_id, Holding.quantity > 0)
            .all()
        )

        portfolio = {
            "cash": user.cash,
            "initial_cash": user.initial_cash,
            "holdings": [],
            "total_stock_value": 0,
            "total_asset": user.cash,
            "total_profit": 0,
            "profit_rate": 0.0,
        }

        # 모든 종목 코드 수집 후 배치 조회
        stock_codes: Set[str] = {h.stock_code for h in holdings}
        stock_prices = StockService.batch_get_prices(stock_codes)

        for h in holdings:
            current_price = stock_prices.get(h.stock_code, h.avg_price)

            current_value = current_price * h.quantity
            cost = h.avg_price * h.quantity
            profit = current_value - cost
            profit_rate = round((profit / cost) * 100, 2) if cost > 0 else 0.0

            portfolio["holdings"].append(
                {
                    "code": h.stock_code,
                    "name": h.stock_name,
                    "quantity": h.quantity,
                    "avg_price": h.avg_price,
                    "current_price": current_price,
                    "current_value": current_value,
                    "profit": profit,
                    "profit_rate": profit_rate,
                }
            )

            portfolio["total_stock_value"] += current_value

        portfolio["total_asset"] = portfolio["cash"] + portfolio["total_stock_value"]
        portfolio["total_profit"] = portfolio["total_asset"] - portfolio["initial_cash"]
        portfolio["profit_rate"] = (
            round((portfolio["total_profit"] / portfolio["initial_cash"]) * 100, 2)
            if portfolio["initial_cash"] > 0
            else 0.0
        )

        return portfolio

    @staticmethod
    def get_transactions(
        db: Session, kakao_id: str, limit: int = 10
    ) -> List[Transaction]:
        """최근 거래 내역 조회"""
        return (
            db.query(Transaction)
            .filter(Transaction.kakao_id == kakao_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .all()
        )
