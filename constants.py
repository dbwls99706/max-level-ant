"""
도메인 상태 상수
- 배틀 진행 상태
- 거래 타입
"""


class BattleStatus:
    """배틀 상태"""

    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class TradeType:
    """거래 타입"""

    BUY = "BUY"
    SELL = "SELL"
