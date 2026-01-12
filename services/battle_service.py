"""
배틀 서비스 - 2인 주가 예측 대결
- 장 열릴 때만 생성/참가 가능
- 장 마감 시 마감가 기준으로 결과 처리
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from models import Battle, User
from services.stock_service import StockService
from config import is_market_open, is_market_closed


class BattleService:
    """배틀 시스템 서비스"""

    # 기본 배팅금
    DEFAULT_BET = 100_000

    # 배틀 지속 시간 (분)
    DEFAULT_DURATION = 60

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
        # 장이 열려있을 때만 가능
        if not is_market_open():
            return {
                "success": False,
                "message": "⚔️ 배틀은 장 운영 시간에만 가능합니다!\n\n⏰ 장 운영: 평일 09:00~15:30\n🎮 장 마감 후에는 미니게임을 즐겨보세요!"
            }

        # 유저 확인
        user = db.query(User).filter(User.kakao_id == challenger_id).first()
        if not user:
            return {"success": False, "message": "먼저 /시작 으로 게임을 시작해주세요."}

        bet = bet_amount or cls.DEFAULT_BET
        dur = duration or cls.DEFAULT_DURATION

        # 잔액 확인
        if user.cash < bet:
            return {
                "success": False,
                "message": f"❌ 잔액 부족!\n보유: {user.cash:,}원\n필요: {bet:,}원"
            }

        # 종목 확인
        stock_info = StockService.get_stock_price(stock_name)
        if not stock_info:
            return {"success": False, "message": f"❌ '{stock_name}' 종목을 찾을 수 없습니다."}

        # 예측 정규화
        pred = prediction.lower()
        if pred in ["상승", "오름", "up", "롱", "매수"]:
            pred = "UP"
        elif pred in ["하락", "내림", "down", "숏", "매도"]:
            pred = "DOWN"
        else:
            return {"success": False, "message": "❌ 예측은 '상승' 또는 '하락'으로 입력해주세요."}

        # 배팅금 차감 (중복 참여 허용)
        user.cash -= bet

        # 배틀 생성
        battle = Battle(
            challenger_id=challenger_id,
            stock_code=stock_info["code"],
            stock_name=stock_info["name"],
            bet_amount=bet,
            challenger_prediction=pred,
            duration_minutes=dur,
            status="WAITING"
        )

        db.add(battle)
        db.commit()
        db.refresh(battle)

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
        # 장이 열려있을 때만 가능
        if not is_market_open():
            return {
                "success": False,
                "message": "⚔️ 배틀은 장 운영 시간에만 가능합니다!\n\n⏰ 장 운영: 평일 09:00~15:30\n🎮 장 마감 후에는 미니게임을 즐겨보세요!"
            }

        # 유저 확인
        user = db.query(User).filter(User.kakao_id == opponent_id).first()
        if not user:
            return {"success": False, "message": "먼저 /시작 으로 게임을 시작해주세요."}

        # 배틀 확인
        battle = db.query(Battle).filter(Battle.id == battle_id).first()
        if not battle:
            return {"success": False, "message": "❌ 해당 배틀을 찾을 수 없습니다."}

        if battle.status != "WAITING":
            return {"success": False, "message": "❌ 이미 진행 중이거나 종료된 배틀입니다."}

        if battle.challenger_id == opponent_id:
            return {"success": False, "message": "❌ 자신의 배틀에는 참가할 수 없습니다."}

        # 잔액 확인
        if user.cash < battle.bet_amount:
            return {
                "success": False,
                "message": f"❌ 잔액 부족!\n보유: {user.cash:,}원\n필요: {battle.bet_amount:,}원"
            }

        # 현재 가격 조회
        stock_info = StockService.get_stock_price(battle.stock_name)
        if not stock_info:
            return {"success": False, "message": "❌ 종목 정보를 가져올 수 없습니다."}

        # 배팅금 차감
        user.cash -= battle.bet_amount

        # 상대방은 반대 예측
        opponent_pred = "DOWN" if battle.challenger_prediction == "UP" else "UP"

        # 배틀 시작
        battle.opponent_id = opponent_id
        battle.opponent_prediction = opponent_pred
        battle.start_price = stock_info["price"]
        battle.started_at = datetime.utcnow()
        battle.status = "ACTIVE"

        db.commit()

        challenger = db.query(User).filter(User.kakao_id == battle.challenger_id).first()
        challenger_name = challenger.nickname or f"투자자{battle.challenger_id[-4:]}"
        opponent_name = user.nickname or f"투자자{opponent_id[-4:]}"

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
        battle = db.query(Battle).filter(Battle.id == battle_id).first()
        if not battle:
            return {"success": False, "message": "❌ 해당 배틀을 찾을 수 없습니다."}

        if battle.status == "WAITING":
            return {"success": False, "message": "⏳ 아직 상대방을 기다리는 중입니다."}

        if battle.status == "CANCELLED":
            return {"success": False, "message": "❌ 취소된 배틀입니다."}

        if battle.status == "FINISHED":
            # 이미 종료된 배틀 결과 반환
            return cls._get_finished_result(db, battle)

        # 장 마감 시 즉시 종료 (마감가 기준)
        if is_market_closed():
            return cls._finish_battle(db, battle, reason="market_close")

        # 배틀 종료 시간 확인
        end_time = battle.started_at + timedelta(minutes=battle.duration_minutes)
        if datetime.utcnow() < end_time:
            remaining = end_time - datetime.utcnow()
            mins = remaining.seconds // 60
            secs = remaining.seconds % 60
            return {
                "success": False,
                "message": f"⏳ 배틀 진행 중!\n\n종목: {battle.stock_name}\n시작가: {battle.start_price:,}원\n남은 시간: {mins}분 {secs}초"
            }

        # 배틀 종료 처리
        return cls._finish_battle(db, battle)

    @classmethod
    def _finish_battle(cls, db: Session, battle: Battle, reason: str = None) -> Dict:
        """배틀 종료 및 결과 처리"""
        # 현재 가격 조회
        stock_info = StockService.get_stock_price(battle.stock_name)
        if not stock_info:
            return {"success": False, "message": "❌ 종목 정보를 가져올 수 없습니다."}

        current_price = stock_info["price"]
        battle.end_price = current_price
        battle.ended_at = datetime.utcnow()

        # 승패 판정
        price_change = current_price - battle.start_price
        actual_direction = "UP" if price_change > 0 else "DOWN" if price_change < 0 else "DRAW"

        challenger = db.query(User).filter(User.kakao_id == battle.challenger_id).first()
        opponent = db.query(User).filter(User.kakao_id == battle.opponent_id).first()

        total_pot = battle.bet_amount * 2

        if actual_direction == "DRAW":
            # 무승부 - 배팅금 반환
            challenger.cash += battle.bet_amount
            opponent.cash += battle.bet_amount
            battle.winner_id = None
            result_msg = "🤝 무승부! 배팅금 반환"
        elif battle.challenger_prediction == actual_direction:
            # 도전자 승리
            challenger.cash += total_pot
            battle.winner_id = battle.challenger_id
            result_msg = f"🏆 {challenger.nickname or f'투자자{battle.challenger_id[-4:]}'} 승리!"
        else:
            # 상대방 승리
            opponent.cash += total_pot
            battle.winner_id = battle.opponent_id
            result_msg = f"🏆 {opponent.nickname or f'투자자{battle.opponent_id[-4:]}'} 승리!"

        battle.status = "FINISHED"
        db.commit()

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

        ch_name = challenger.nickname or f"투자자{battle.challenger_id[-4:]}"
        op_name = opponent.nickname or f"투자자{battle.opponent_id[-4:]}" if opponent else "???"

        price_change = battle.end_price - battle.start_price
        change_rate = (price_change / battle.start_price) * 100

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
            "start_price": battle.start_price,
            "end_price": battle.end_price,
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
        battles = db.query(Battle).filter(Battle.status == "WAITING").all()

        result = []
        for b in battles:
            user = db.query(User).filter(User.kakao_id == b.challenger_id).first()
            name = user.nickname or f"투자자{b.challenger_id[-4:]}"
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
