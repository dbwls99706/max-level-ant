"""
감사 로그 (Audit Logger)
- 거래, 게임, 배틀 등 금전적 이벤트에 대한 감사 로그
- 분쟁 해결, 치팅 감지, 데이터 무결성 검증에 사용
- 별도 파일(audit.log)에 기록
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional


def _get_audit_logger() -> logging.Logger:
    """감사 로거 초기화"""
    audit_logger = logging.getLogger("audit")

    if audit_logger.handlers:
        return audit_logger

    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False  # 루트 로거로 전파 방지

    formatter = logging.Formatter(
        "%(asctime)s [AUDIT] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ"
    )

    # 콘솔 핸들러 (항상)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    audit_logger.addHandler(console_handler)

    # 파일 핸들러 (로그 디렉토리가 있을 때만)
    log_dir = os.getenv("LOG_DIR", "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "audit.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        audit_logger.addHandler(file_handler)
    except OSError:
        pass  # 파일 핸들러 실패 시 콘솔만 사용

    return audit_logger


_audit_logger = _get_audit_logger()


def _now_utc() -> str:
    """현재 UTC 시간 ISO 형식"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_trade(
    kakao_id: str,
    trade_type: str,
    stock_code: str,
    stock_name: str,
    quantity: int,
    price: int,
    total_amount: int,
    fee: int,
    cash_after: int,
    profit: Optional[int] = None,
    profit_rate: Optional[float] = None,
):
    """
    거래 감사 로그
    매수/매도 이벤트 기록
    """
    masked_id = f"{kakao_id[:4]}****" if len(kakao_id) > 4 else "****"
    msg = (
        f"TRADE | user={masked_id} | type={trade_type} | "
        f"stock={stock_name}({stock_code}) | qty={quantity} | "
        f"price={price:,} | total={total_amount:,} | fee={fee:,} | "
        f"cash_after={cash_after:,}"
    )
    if profit is not None:
        msg += f" | profit={profit:,} | profit_rate={profit_rate:.2f}%"

    _audit_logger.info(msg)


def log_game(
    kakao_id: str,
    game_type: str,
    bet: int,
    result: str,
    winnings: int,
    profit: int,
    cash_after: int,
    extra: str = "",
):
    """
    예측게임 감사 로그
    복권, 종목추첨, 시장예측, 업다운, 등락예측 결과 기록
    """
    masked_id = f"{kakao_id[:4]}****" if len(kakao_id) > 4 else "****"
    msg = (
        f"GAME | user={masked_id} | game={game_type} | "
        f"bet={bet:,} | result={result} | winnings={winnings:,} | "
        f"profit={profit:,} | cash_after={cash_after:,}"
    )
    if extra:
        msg += f" | {extra}"

    _audit_logger.info(msg)


def log_battle(
    battle_id: int,
    challenger_id: str,
    opponent_id: str,
    stock_name: str,
    bet_amount: int,
    start_price: int,
    end_price: int,
    winner_id: Optional[str],
    prize: int,
):
    """
    배틀 결과 감사 로그
    """
    masked_ch = f"{challenger_id[:4]}****" if len(challenger_id) > 4 else "****"
    masked_op = f"{opponent_id[:4]}****" if len(opponent_id) > 4 else "****"
    masked_winner = "DRAW" if winner_id is None else (
        f"{winner_id[:4]}****" if len(winner_id) > 4 else "****"
    )

    price_change = end_price - start_price
    change_pct = (price_change / start_price * 100) if start_price > 0 else 0.0

    msg = (
        f"BATTLE | id={battle_id} | challenger={masked_ch} | opponent={masked_op} | "
        f"stock={stock_name} | bet={bet_amount:,} | "
        f"start={start_price:,} | end={end_price:,} | "
        f"change={change_pct:+.2f}% | winner={masked_winner} | prize={prize:,}"
    )
    _audit_logger.info(msg)


def log_attendance(
    kakao_id: str,
    reward: int,
    streak: int,
    cash_after: int,
):
    """출석 보상 감사 로그"""
    masked_id = f"{kakao_id[:4]}****" if len(kakao_id) > 4 else "****"
    _audit_logger.info(
        f"ATTENDANCE | user={masked_id} | reward={reward:,} | "
        f"streak={streak} | cash_after={cash_after:,}"
    )


def log_achievement(
    kakao_id: str,
    achievement_id: str,
    achievement_name: str,
    reward: int,
    cash_after: int,
):
    """업적 달성 감사 로그"""
    masked_id = f"{kakao_id[:4]}****" if len(kakao_id) > 4 else "****"
    _audit_logger.info(
        f"ACHIEVEMENT | user={masked_id} | id={achievement_id} | "
        f"name={achievement_name} | reward={reward:,} | cash_after={cash_after:,}"
    )


def log_admin_action(action: str, details: str = ""):
    """관리자 액션 감사 로그"""
    msg = f"ADMIN | action={action}"
    if details:
        msg += f" | details={details}"
    _audit_logger.warning(msg)
