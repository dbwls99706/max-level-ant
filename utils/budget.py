"""
요청 단위 시간 예산 (Deadline)

카카오 스킬 서버는 요청당 5초 안에 응답해야 한다. 초과하면 카카오는 이미
실패로 처리하므로, 그 뒤에 외부 API가 늦게 성공해도 의미가 없다.

한 번의 /skill 처리에서 외부 호출이 여러 번(토큰 발급 → 시세 조회 →
병렬 배치 조회) 일어날 수 있으므로, 호출마다 개별 타임아웃을 두는 것으로는
전체 소요를 5초 안에 묶을 수 없다. 그래서 요청 시작 시점에 '남은 예산'을
정해 두고, 모든 외부 호출이 그 예산을 나눠 쓰도록 한다.

사용:
    with request_budget(3.5):
        ...  # 이 안에서 일어나는 모든 외부 호출이 3.5초 예산을 공유
"""

import threading
import time
from contextlib import contextmanager
from typing import Optional


class Deadline:
    """요청 하나에 허용된 시간 예산"""

    __slots__ = ("_expires_at",)

    def __init__(self, budget: float):
        self._expires_at = time.monotonic() + budget

    def remaining(self) -> float:
        """남은 시간(초). 이미 초과했으면 0."""
        return max(0.0, self._expires_at - time.monotonic())

    def expired(self) -> bool:
        return self.remaining() <= 0

    def timeout_for(self, cap: float) -> float:
        """개별 호출에 줄 타임아웃 = min(호출 자체 상한, 남은 예산)"""
        return min(cap, self.remaining())


# 요청별 deadline. 스레드마다 독립적으로 보관한다.
# (ThreadPoolExecutor 워커는 부모 스레드 값을 자동으로 물려받지 않으므로
#  배치 조회처럼 워커를 쓰는 쪽에서 adopt()로 명시 전달한다.)
_local = threading.local()


def current_deadline() -> Optional[Deadline]:
    """현재 스레드에 설정된 deadline (없으면 None)"""
    return getattr(_local, "deadline", None)


def remaining(default: Optional[float] = None) -> Optional[float]:
    """남은 예산. deadline이 없으면 default."""
    dl = current_deadline()
    return dl.remaining() if dl is not None else default


def timeout_for(cap: float) -> float:
    """
    개별 외부 호출에 적용할 타임아웃.
    deadline이 없으면(배치 작업·테스트 등) 호출 자체 상한을 그대로 쓴다.
    """
    dl = current_deadline()
    return dl.timeout_for(cap) if dl is not None else cap


def exhausted(min_needed: float = 0.0) -> bool:
    """
    남은 예산이 min_needed에도 못 미치는지.
    True면 호출을 시작해도 응답 전에 카카오 타임아웃이므로 아예 보내지 않는다.
    """
    dl = current_deadline()
    if dl is None:
        return False
    return dl.remaining() <= min_needed


@contextmanager
def request_budget(budget: float):
    """요청 처리 구간에 시간 예산을 건다"""
    previous = getattr(_local, "deadline", None)
    _local.deadline = Deadline(budget)
    try:
        yield _local.deadline
    finally:
        _local.deadline = previous


@contextmanager
def adopt(deadline: Optional[Deadline]):
    """다른 스레드(워커)에서 부모 요청의 deadline을 이어받는다"""
    previous = getattr(_local, "deadline", None)
    _local.deadline = deadline
    try:
        yield
    finally:
        _local.deadline = previous
