"""
배틀 서비스 - 2인 주가 예측 대결 (리팩토링)
- 장 열릴 때만 생성/참가 가능
- 장 마감 시 마감가 기준으로 결과 처리
- 트랜잭션 안전성 강화
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import Battle, User
from services.stock_service import StockService
from services.common import (
    get_user_with_error_for_update,
    validate_bet,
    safe_subtract,
    safe_add,
    error_response,
    success_response,
)
from config import is_market_open, is_market_closed, get_market_status_message, ErrorCode, BattleStatus
from utils import get_service_logger, log_battle

logger = get_service_logger()


class BattleService:
    """배틀 시스템 서비스"""

    # 기본 투자금
    DEFAULT_BET = 100_000
    MIN_BET = 10_000
    MAX_BET = 100_000_000  # 1억

    # 배틀 지속 시간 (분)
    DEFAULT_DURATION = 60
    MIN_DURATION = 5
    MAX_DURATION = 480  # 8시간

    # 예측 정규화 매핑
    PREDICTION_UP = {"상승", "오름", "up", "롱", "매수", "상", "업"}
    PREDICTION_DOWN = {"하락", "내림", "down", "숏", "매도", "하", "다운"}

    @classmethod
    def _normalize_prediction(cls, prediction: str) -> Optional[str]:
        """예측 문자열 정규화"""
        pred = prediction.lower().strip()
        if pred in cls.PREDICTION_UP:
            return "UP"
        elif pred in cls.PREDICTION_DOWN:
            return "DOWN"
        return None

    @classmethod
    def _get_market_closed_error(cls) -> Dict:
        """장 마감 에러 메시지 생성"""
        status_msg = get_market_status_message()
        return error_response(
            ErrorCode.MARKET_CLOSED,
            f"⚔️ 배틀은 정규장 시간에만 가능해요!\n\n{status_msg}\n\n"
            f"⏰ 배틀 가능 시간:\n• 평일 09:00~15:30\n\n"
            f"📈 장 마감 후에는 예측게임을 즐겨보세요!"
        )

    @classmethod
    def _get_user_display_name(cls, user: User, kakao_id: str) -> str:
        """유저 표시명 생성"""
        if user and user.nickname:
            return user.nickname
        return f"투자자{kakao_id[-4:]}"

    @classmethod
    def create_battle(
        cls,
        db: Session,
        challenger_id: str,
        stock_name: str,
        prediction: str,
        bet_amount: int = None,
        duration: int = None
    ) -> Dict:
        """
        배틀 생성 (도전장 던지기)
        prediction: "상승" or "하락"
        """
        # 장이 열려있을 때만 가능 (정규장)
        if not is_market_open():
            return cls._get_market_closed_error()

        # 유저 확인 (FOR UPDATE로 동시성 제어)
        user, err = get_user_with_error_for_update(db, challenger_id)
        if err:
            return err

        # 투자금 및 시간 설정
        bet = bet_amount or cls.DEFAULT_BET
        dur = duration or cls.DEFAULT_DURATION

        # 투자금 검증
        is_valid, err_msg = validate_bet(bet, user.cash, cls.MIN_BET, cls.MAX_BET)
        if not is_valid:
            return error_response(ErrorCode.INSUFFICIENT_CASH, f"❌ {err_msg}")

        # 시간 검증
        if dur < cls.MIN_DURATION or dur > cls.MAX_DURATION:
            return error_response(
                ErrorCode.INVALID_PARAMETER,
                f"❌ 배틀 시간은 {cls.MIN_DURATION}분~{cls.MAX_DURATION}분 사이여야 합니다."
            )

        # 종목 확인
        stock_info = StockService.get_price(stock_name)
        if not stock_info:
            return error_response(
                ErrorCode.STOCK_NOT_FOUND,
                f"❌ '{stock_name}' 종목을 찾을 수 없습니다."
            )

        # 예측 정규화
        pred = cls._normalize_prediction(prediction)
        if not pred:
            return error_response(
                ErrorCode.INVALID_PARAMETER,
                "❌ 예측은 '상승' 또는 '하락'으로 입력해주세요."
            )

        # 트랜잭션: 투자금 차감 및 배틀 생성
        try:
            user.cash = safe_subtract(user.cash, bet)

            battle = Battle(
                challenger_id=challenger_id,
                stock_code=stock_info["code"],
                stock_name=stock_info["name"],
                bet_amount=bet,
                challenger_prediction=pred,
                duration_minutes=dur,
                status=BattleStatus.WAITING
            )

            db.add(battle)
            db.commit()
            db.refresh(battle)
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"배틀 생성 DB 실패: {e}")
            return error_response(ErrorCode.INTERNAL_ERROR, "❌ 배틀 생성 중 오류가 발생했습니다.")

        pred_emoji = "📈" if pred == "UP" else "📉"
        pred_text = "상승" if pred == "UP" else "하락"

        return {
            "success": True,
            "battle_id": battle.id,
            "stock_name": stock_info["name"],
            "stock_code": stock_info["code"],
            "current_price": stock_info["price"],
            "prediction": pred_text,
            "pred_emoji": pred_emoji,
            "bet_amount": bet,
            "duration": dur,
            "message": f"⚔️ 배틀 생성 완료!\n\n다른 유저가 '/배틀참가 {battle.id}'로 참가할 수 있습니다."
        }

    @classmethod
    def join_battle(cls, db: Session, opponent_id: str, battle_id: int) -> Dict:
        """배틀 참가 (도전 수락)"""
        # 장이 열려있을 때만 가능 (정규장)
        if not is_market_open():
            return cls._get_market_closed_error()

        # 유저 확인 (FOR UPDATE로 동시성 제어)
        user, err = get_user_with_error_for_update(db, opponent_id)
        if err:
            return err

        # 배틀 확인 (FOR UPDATE로 동시 참가 방지)
        battle = db.query(Battle).filter(Battle.id == battle_id).with_for_update().first()
        if not battle:
            return error_response(ErrorCode.NOT_FOUND, "❌ 해당 배틀을 찾을 수 없습니다.")

        if battle.status != BattleStatus.WAITING:
            return error_response(
                ErrorCode.INVALID_STATE,
                "❌ 이미 진행 중이거나 종료된 배틀입니다."
            )

        if battle.challenger_id == opponent_id:
            return error_response(
                ErrorCode.INVALID_PARAMETER,
                "❌ 자신의 배틀에는 참가할 수 없습니다."
            )

        # 투자금 검증
        is_valid, err_msg = validate_bet(battle.bet_amount, user.cash)
        if not is_valid:
            return error_response(ErrorCode.INSUFFICIENT_CASH, f"❌ {err_msg}")

        # 현재 가격 조회
        stock_info = StockService.get_price(battle.stock_name)
        if not stock_info:
            return error_response(ErrorCode.STOCK_NOT_FOUND, "❌ 종목 정보를 가져올 수 없습니다.")

        # 상대방은 반대 예측
        opponent_pred = "DOWN" if battle.challenger_prediction == "UP" else "UP"

        # 트랜잭션: 투자금 차감 및 배틀 시작
        try:
            user.cash = safe_subtract(user.cash, battle.bet_amount)

            battle.opponent_id = opponent_id
            battle.opponent_prediction = opponent_pred
            battle.start_price = stock_info["price"]
            battle.started_at = datetime.now(timezone.utc)
            battle.status = BattleStatus.ACTIVE

            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"배틀 참가 DB 실패: {e}")
            return error_response(ErrorCode.INTERNAL_ERROR, "❌ 배틀 참가 중 오류가 발생했습니다.")

        challenger = db.query(User).filter(User.kakao_id == battle.challenger_id).first()
        challenger_name = cls._get_user_display_name(challenger, battle.challenger_id)
        opponent_name = cls._get_user_display_name(user, opponent_id)

        ch_pred = "상승" if battle.challenger_prediction == "UP" else "하락"
        op_pred = "상승" if opponent_pred == "UP" else "하락"

        return {
            "success": True,
            "battle_id": battle.id,
            "stock_name": battle.stock_name,
            "start_price": battle.start_price,
            "challenger_name": challenger_name,
            "challenger_prediction": ch_pred,
            "opponent_name": opponent_name,
            "opponent_prediction": op_pred,
            "bet_amount": battle.bet_amount,
            "duration": battle.duration_minutes,
            "message": f"⚔️ 배틀 시작!\n\n{battle.duration_minutes}분 후 결과 확인 가능\n/배틀결과 {battle.id}"
        }

    @classmethod
    def check_battle_result(cls, db: Session, battle_id: int) -> Dict:
        """배틀 결과 확인"""
        # FOR UPDATE로 배틀 상태 변경 시 동시 종료 처리 방지
        battle = db.query(Battle).filter(Battle.id == battle_id).with_for_update().first()
        if not battle:
            return error_response(ErrorCode.NOT_FOUND, "❌ 해당 배틀을 찾을 수 없습니다.")

        if battle.status == BattleStatus.WAITING:
            return error_response(ErrorCode.INVALID_STATE, "⏳ 아직 상대방을 기다리는 중입니다.")

        if battle.status == BattleStatus.CANCELLED:
            return error_response(ErrorCode.INVALID_STATE, "❌ 취소된 배틀입니다.")

        if battle.status == BattleStatus.FINISHED:
            # 이미 종료된 배틀 결과 반환
            return cls._get_finished_result(db, battle)

        # 장 마감 시 즉시 종료 (마감가 기준)
        if is_market_closed():
            return cls._finish_battle(db, battle, reason="market_close")

        # 배틀 종료 시간 확인
        end_time = battle.started_at + timedelta(minutes=battle.duration_minutes)
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for comparison
        if now_utc < end_time:
            remaining = end_time - now_utc
            mins = remaining.seconds // 60
            secs = remaining.seconds % 60
            return error_response(
                ErrorCode.INVALID_STATE,
                f"⏳ 배틀 진행 중!\n\n종목: {battle.stock_name}\n시작가: {battle.start_price:,}원\n남은 시간: {mins}분 {secs}초"
            )

        # 배틀 종료 처리
        return cls._finish_battle(db, battle)

    @classmethod
    def _finish_battle(cls, db: Session, battle: Battle, reason: str = None) -> Dict:
        """배틀 종료 및 결과 처리"""
        # 현재 가격 조회
        stock_info = StockService.get_price(battle.stock_name)
        if not stock_info:
            return error_response(ErrorCode.STOCK_NOT_FOUND, "❌ 종목 정보를 가져올 수 없습니다.")

        current_price = stock_info["price"]

        # 승패 판정 (start_price None 방어)
        start_price = battle.start_price or 0
        price_change = current_price - start_price
        actual_direction = "UP" if price_change > 0 else "DOWN" if price_change < 0 else "DRAW"

        # FOR UPDATE로 동시성 제어 (상금 지급 시 race condition 방지)
        challenger = db.query(User).filter(User.kakao_id == battle.challenger_id).with_for_update().first()
        opponent = db.query(User).filter(User.kakao_id == battle.opponent_id).with_for_update().first()

        # 유저 확인 (데이터 무결성 체크) - 생존 유저에게 투자금 환불
        if not challenger or not opponent:
            try:
                surviving_user = challenger or opponent
                if surviving_user:
                    surviving_user.cash = safe_add(surviving_user.cash, battle.bet_amount)
                battle.status = BattleStatus.CANCELLED
                db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"배틀 만료 취소 DB 실패: {e}")
            return error_response(ErrorCode.USER_NOT_FOUND, "❌ 배틀 참가자 정보를 찾을 수 없습니다. 투자금이 환불됩니다.")

        total_pot = battle.bet_amount * 2

        # 트랜잭션: 결과 처리
        try:
            battle.end_price = current_price
            battle.ended_at = datetime.now(timezone.utc)

            if actual_direction == "DRAW":
                # 무승부 - 투자금 반환
                challenger.cash = safe_add(challenger.cash, battle.bet_amount)
                opponent.cash = safe_add(opponent.cash, battle.bet_amount)
                battle.winner_id = None
            elif battle.challenger_prediction == actual_direction:
                # 도전자 승리
                challenger.cash = safe_add(challenger.cash, total_pot)
                battle.winner_id = battle.challenger_id
            else:
                # 상대방 승리
                opponent.cash = safe_add(opponent.cash, total_pot)
                battle.winner_id = battle.opponent_id

            battle.status = BattleStatus.FINISHED
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"배틀 결과 처리 DB 실패: {e}")
            return error_response(ErrorCode.INTERNAL_ERROR, "❌ 배틀 결과 처리 중 오류가 발생했습니다.")

        # 감사 로그
        log_battle(
            battle_id=battle.id,
            challenger_id=battle.challenger_id,
            opponent_id=battle.opponent_id,
            stock_name=battle.stock_name,
            bet_amount=battle.bet_amount,
            start_price=battle.start_price or 0,
            end_price=current_price,
            winner_id=battle.winner_id,
            prize=total_pot,
        )

        result = cls._get_finished_result(db, battle)

        # 장 마감으로 인한 종료 시 메시지 추가
        if reason == "market_close":
            result["market_closed"] = True

        return result

    @classmethod
    def _get_finished_result(cls, db: Session, battle: Battle) -> Dict:
        """종료된 배틀 결과 조회"""
        challenger = db.query(User).filter(User.kakao_id == battle.challenger_id).first()
        opponent = db.query(User).filter(User.kakao_id == battle.opponent_id).first()

        ch_name = cls._get_user_display_name(challenger, battle.challenger_id) if challenger else "???"
        op_name = cls._get_user_display_name(opponent, battle.opponent_id) if opponent else "???"

        start_price = battle.start_price or 0
        end_price = battle.end_price or 0
        price_change = end_price - start_price
        # 0으로 나누기 방지 + None 방어
        change_rate = (price_change / start_price) * 100 if start_price > 0 else 0

        if battle.winner_id == battle.challenger_id:
            winner_name = ch_name
            winner_emoji = "🏆"
        elif battle.winner_id == battle.opponent_id:
            winner_name = op_name
            winner_emoji = "🏆"
        else:
            winner_name = "무승부"
            winner_emoji = "🤝"

        return {
            "success": True,
            "finished": True,
            "battle_id": battle.id,
            "stock_name": battle.stock_name,
            "start_price": start_price,
            "end_price": end_price,
            "price_change": price_change,
            "change_rate": change_rate,
            "challenger_name": ch_name,
            "opponent_name": op_name,
            "winner": winner_name,
            "winner_emoji": winner_emoji,
            "bet_amount": battle.bet_amount,
            "prize": battle.bet_amount * 2
        }

    @classmethod
    def get_waiting_battles(cls, db: Session) -> List[Dict]:
        """대기 중인 배틀 목록"""
        battles = db.query(Battle).filter(Battle.status == BattleStatus.WAITING).all()

        # N+1 최적화: 모든 유저 ID 수집 후 배치 조회
        challenger_ids = {b.challenger_id for b in battles}
        users_map = {}
        if challenger_ids:
            users = db.query(User).filter(User.kakao_id.in_(challenger_ids)).all()
            users_map = {u.kakao_id: u for u in users}

        result = []
        for b in battles:
            user = users_map.get(b.challenger_id)
            name = cls._get_user_display_name(user, b.challenger_id)
            pred = "상승" if b.challenger_prediction == "UP" else "하락"

            result.append({
                "id": b.id,
                "challenger": name,
                "stock_name": b.stock_name,
                "prediction": pred,
                "bet_amount": b.bet_amount,
                "duration": b.duration_minutes
            })

        return result

    @classmethod
    def get_my_battles(cls, db: Session, kakao_id: str) -> List[Dict]:
        """내 배틀 목록"""
        battles = db.query(Battle).filter(
            (Battle.challenger_id == kakao_id) | (Battle.opponent_id == kakao_id)
        ).order_by(Battle.created_at.desc()).limit(10).all()

        result = []
        for b in battles:
            result.append({
                "id": b.id,
                "stock_name": b.stock_name,
                "status": b.status,
                "bet_amount": b.bet_amount,
                "is_winner": b.winner_id == kakao_id if b.winner_id else None
            })

        return result

    @classmethod
    def cancel_battle(cls, db: Session, kakao_id: str, battle_id: int) -> Dict:
        """대기 중인 배틀 취소"""
        battle = db.query(Battle).filter(Battle.id == battle_id).first()
        if not battle:
            return error_response(ErrorCode.NOT_FOUND, "❌ 해당 배틀을 찾을 수 없습니다.")

        if battle.challenger_id != kakao_id:
            return error_response(ErrorCode.PERMISSION_DENIED, "❌ 본인이 생성한 배틀만 취소할 수 있습니다.")

        if battle.status != BattleStatus.WAITING:
            return error_response(ErrorCode.INVALID_STATE, "❌ 대기 중인 배틀만 취소할 수 있습니다.")

        # FOR UPDATE로 동시성 제어 (투자금 환불 시 race condition 방지)
        user = db.query(User).filter(User.kakao_id == kakao_id).with_for_update().first()
        if not user:
            return error_response(ErrorCode.USER_NOT_FOUND, "❌ 유저 정보를 찾을 수 없습니다.")

        try:
            # 투자금 환불
            user.cash = safe_add(user.cash, battle.bet_amount)
            battle.status = BattleStatus.CANCELLED
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"배틀 취소 DB 실패: {e}")
            return error_response(ErrorCode.INTERNAL_ERROR, "❌ 배틀 취소 중 오류가 발생했습니다.")

        return success_response(
            f"✅ 배틀이 취소되었습니다.\n💰 {battle.bet_amount:,}원 환불 완료!",
            battle_id=battle_id,
            refund=battle.bet_amount,
            cash=user.cash
        )

    @classmethod
    def cleanup_stale_battles(cls, db: Session, max_waiting_hours: int = 24) -> int:
        """
        만료된 대기 배틀 정리 (투자금 환불)
        서버 시작 시 또는 주기적으로 호출
        Returns: 정리된 배틀 수
        """
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=max_waiting_hours)
        stale_battles = db.query(Battle).filter(
            Battle.status == BattleStatus.WAITING,
            Battle.created_at < cutoff
        ).all()

        cleaned = 0
        for battle in stale_battles:
            try:
                user = db.query(User).filter(User.kakao_id == battle.challenger_id).with_for_update().first()
                if user:
                    user.cash = safe_add(user.cash, battle.bet_amount)
                battle.status = BattleStatus.CANCELLED
                db.commit()
                cleaned += 1
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"만료 배틀 정리 실패 (id={battle.id}): {e}")

        if cleaned > 0:
            logger.info(f"만료 배틀 {cleaned}건 정리 완료 (투자금 환불)")
        return cleaned
