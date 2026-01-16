"""
서비스 공통 유틸리티
- 트랜잭션 헬퍼: safe_commit
- 검증 유틸: validate_bet, validate_quantity
- 유저 헬퍼: get_user_with_error
- 응답 빌더: error_response, success_response
- 금액 안전 계산: safe_add, safe_subtract, safe_multiply
"""
from typing import Dict, Optional, TypeVar, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import User
from config import (
    GameConfig, Messages, ErrorCode,
    is_market_closed, get_market_status_message
)
from utils import get_service_logger

logger = get_service_logger()

# 제네릭 타입
T = TypeVar('T')


# ===========================================
# 트랜잭션 헬퍼
# ===========================================

def safe_commit(db: Session, error_message: str = "데이터베이스 오류가 발생했습니다.") -> Tuple[bool, str]:
    """
    안전한 DB 커밋 with 롤백

    Returns:
        (success: bool, error_message: str)
    """
    try:
        db.commit()
        return True, ""
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"DB commit 실패: {e}")
        return False, error_message


# ===========================================
# 유저 관련 헬퍼
# ===========================================

def get_user_or_none(db: Session, kakao_id: str) -> Optional[User]:
    """유저 조회 (없으면 None)"""
    return db.query(User).filter(User.kakao_id == kakao_id).first()


def get_user_for_update(db: Session, kakao_id: str) -> Optional[User]:
    """
    유저 조회 with FOR UPDATE (Row Lock)
    - 동시성 제어가 필요한 거래에서 사용
    - 트랜잭션 종료 시까지 해당 row lock 유지
    """
    return db.query(User).filter(
        User.kakao_id == kakao_id
    ).with_for_update().first()


def get_user_with_error(db: Session, kakao_id: str) -> Tuple[Optional[User], Optional[Dict]]:
    """
    유저 조회 with 에러 응답

    Returns:
        (user, error_response) - 유저가 있으면 (user, None), 없으면 (None, error_dict)
    """
    user = get_user_or_none(db, kakao_id)
    if not user:
        return None, {
            "success": False,
            "error_code": ErrorCode.USER_NOT_FOUND,
            "message": Messages.USER_NOT_FOUND
        }
    return user, None


def get_user_with_error_for_update(db: Session, kakao_id: str) -> Tuple[Optional[User], Optional[Dict]]:
    """
    유저 조회 with FOR UPDATE and 에러 응답
    - 거래 등 동시성 제어가 필요한 작업에서 사용
    - Race condition 방지

    Returns:
        (user, error_response) - 유저가 있으면 (user, None), 없으면 (None, error_dict)
    """
    user = get_user_for_update(db, kakao_id)
    if not user:
        return None, {
            "success": False,
            "error_code": ErrorCode.USER_NOT_FOUND,
            "message": Messages.USER_NOT_FOUND
        }
    return user, None


# ===========================================
# 배팅 검증
# ===========================================

def validate_bet(
    bet: int,
    user_cash: int,
    min_bet: int = None,
    max_bet: int = None
) -> Tuple[bool, str]:
    """
    배팅금 검증

    Args:
        bet: 배팅 금액
        user_cash: 유저 보유 현금
        min_bet: 최소 배팅금 (기본: GameConfig.MIN_BET)
        max_bet: 최대 배팅금 (기본: 100억)

    Returns:
        (is_valid: bool, error_message: str)
    """
    if min_bet is None:
        min_bet = GameConfig.MIN_BET
    if max_bet is None:
        max_bet = 10_000_000_000  # 100억 (오버플로우 방지)

    if bet <= 0:
        return False, "배팅금은 0보다 커야 합니다."

    if bet < min_bet:
        return False, f"최소 배팅금은 {min_bet:,}원입니다."

    if bet > max_bet:
        return False, f"최대 배팅금은 {max_bet:,}원입니다."

    if user_cash < bet:
        return False, f"잔액 부족! (보유: {user_cash:,}원, 필요: {bet:,}원)"

    return True, ""


def validate_quantity(
    quantity: int,
    min_qty: int = None,
    max_qty: int = None
) -> Tuple[bool, str]:
    """
    거래 수량 검증

    Args:
        quantity: 거래 수량
        min_qty: 최소 수량 (기본: GameConfig.MIN_TRADE_AMOUNT)
        max_qty: 최대 수량 (기본: GameConfig.MAX_QUANTITY)

    Returns:
        (is_valid: bool, error_message: str)
    """
    if min_qty is None:
        min_qty = GameConfig.MIN_TRADE_AMOUNT
    if max_qty is None:
        max_qty = GameConfig.MAX_QUANTITY

    if quantity <= 0:
        return False, "수량은 0보다 커야 합니다."

    if quantity < min_qty:
        return False, f"최소 {min_qty:,}주 이상 거래해야 합니다."

    if quantity > max_qty:
        return False, f"1회 최대 거래 수량은 {max_qty:,}주입니다."

    return True, ""


# ===========================================
# 시장 상태 검증
# ===========================================

def check_market_closed_for_game(game_emoji: str = "🎰") -> Tuple[bool, Optional[Dict]]:
    """
    게임 가능 시간 체크 (장 마감 시간에만 가능)

    Returns:
        (can_play: bool, error_response: Optional[Dict])
    """
    if not is_market_closed():
        status_msg = get_market_status_message()
        return False, {
            "success": False,
            "error_code": ErrorCode.MARKET_CLOSED,
            "message": f"{game_emoji} " + Messages.MARKET_CLOSED_GAME.format(status_msg=status_msg)
        }
    return True, None


# ===========================================
# 응답 빌더
# ===========================================

def error_response(
    error_code: str,
    message: str,
    **extra_data
) -> Dict:
    """에러 응답 생성"""
    response = {
        "success": False,
        "error_code": error_code,
        "message": message
    }
    if extra_data:
        response.update(extra_data)
    return response


def success_response(message: str = "성공", **data) -> Dict:
    """성공 응답 생성"""
    response = {
        "success": True,
        "message": message
    }
    response.update(data)
    return response


# ===========================================
# 게임 결과 계산 헬퍼
# ===========================================

def calculate_profit(bet: int, winnings: int) -> Dict:
    """
    게임 수익 계산

    Returns:
        {
            "profit": int (순이익),
            "profit_text": str (포맷된 문자열),
            "profit_emoji": str (📈/📉)
        }
    """
    profit = winnings - bet

    if profit > 0:
        return {
            "profit": profit,
            "profit_text": f"+{profit:,}원",
            "profit_emoji": "📈"
        }
    elif profit < 0:
        return {
            "profit": profit,
            "profit_text": f"{profit:,}원",
            "profit_emoji": "📉"
        }
    else:
        return {
            "profit": 0,
            "profit_text": "±0원",
            "profit_emoji": "➖"
        }


# ===========================================
# 금액 안전 계산 (오버플로우 방지)
# ===========================================

MAX_SAFE_AMOUNT = 10_000_000_000_000  # 10조 (Python int는 무제한이지만 합리적 상한)


def safe_add(a: int, b: int) -> int:
    """안전한 덧셈 (상한 적용)"""
    result = a + b
    return min(result, MAX_SAFE_AMOUNT)


def safe_multiply(a: int, b: float) -> int:
    """안전한 곱셈 (상한 적용)"""
    result = int(a * b)
    return min(result, MAX_SAFE_AMOUNT)


def safe_subtract(a: int, b: int) -> int:
    """안전한 뺄셈 (0 이상 보장)"""
    return max(0, a - b)
