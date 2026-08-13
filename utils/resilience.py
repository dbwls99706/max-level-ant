"""
외부 API 호출 보호용 유틸리티
- CircuitBreaker: 연속 실패 시 일시 차단 (서킷 브레이커 패턴)
- CallThrottle: 호출 간 최소 간격 보장 (유량 제한)
"""

import threading
import time
from contextlib import contextmanager
from typing import Optional

from .logger import get_service_logger

logger = get_service_logger()


class CircuitState:
    """서킷 상태"""

    CLOSED = "CLOSED"  # 정상 운영
    OPEN = "OPEN"  # 차단 중 (실패 임계값 초과)
    HALF_OPEN = "HALF_OPEN"  # 복구 프로브 진행 중


class CircuitOpenError(RuntimeError):
    """서킷이 열려 있어 호출이 차단됨"""


class CallPermit:
    """
    서킷을 통과한 호출 1건의 허가증.

    "어떤 자격으로 통과했는지"를 기억한다. 이게 중요한 이유:
    같은 성공이라도 복구 프로브(is_probe=True)의 성공만 서킷을 닫을 수 있고,
    일반 요청의 성공은 실패 카운터만 초기화해야 하기 때문이다.

    generation은 발급 시점의 서킷 세대다. 발급 이후 서킷이 한 번이라도 열렸다면
    세대가 달라지므로, 뒤늦게 도착한 결과(stale outcome)를 판별해 무시할 수 있다.
    """

    __slots__ = ("is_probe", "generation", "_failed", "_settled")

    def __init__(self, is_probe: bool, generation: int):
        self.is_probe = is_probe
        self.generation = generation
        self._failed = False
        self._settled = False

    def failure(self):
        """이 호출을 실패로 기록 (예외가 아닌 응답 본문 기준 실패에 사용)"""
        self._failed = True

    def success(self):
        """이 호출을 성공으로 기록 (기본값이므로 명시하지 않아도 된다)"""
        self._failed = False

    @property
    def failed(self) -> bool:
        return self._failed


class CircuitBreaker:
    """
    연속 실패 시 외부 호출을 일시 차단하는 서킷 브레이커.

    상태 전이:
        CLOSED    --(연속 실패 N회)-->        OPEN
        OPEN      --(복구 타임아웃 경과)-->   HALF_OPEN (프로브 1건만 통과)
        HALF_OPEN --(프로브 성공)-->          CLOSED
        HALF_OPEN --(프로브 실패)-->          OPEN (타임아웃 재시작)

    이 전이표는 우회 경로가 없어야 한다. 그래서 두 가지를 지킨다.

    1) HALF_OPEN에서는 복구 확인용 프로브 **한 건만** 통과시킨다.
       프로브가 결과를 기록하기 전까지 다른 스레드는 차단되므로,
       장애 중인 API에 복구 시도 트래픽이 몰리지 않는다.

    2) 결과는 발급받은 허가증(CallPermit) 기준으로만 반영한다.
       ThreadPoolExecutor로 요청을 병렬 처리하면 CLOSED일 때 출발한 요청이
       서킷이 열린 뒤에 끝날 수 있다. 이 "뒤늦은 성공"이 OPEN을 CLOSED로
       되돌리면 복구 타임아웃도 프로브도 건너뛰고 전체 트래픽이 풀려버린다.
       허가증의 세대(generation)와 자격(is_probe)을 확인해 이런 결과는 무시한다.
       → OPEN을 닫을 수 있는 것은 오직 HALF_OPEN 프로브의 성공뿐이다.

    사용법 — guard() 컨텍스트 매니저 권장:

        try:
            with breaker.guard() as call:
                resp = requests.get(...)
                if resp.status_code != 200:
                    call.failure()
        except CircuitOpenError:
            return None  # 차단됨

    guard()는 블록을 어떤 경로로 빠져나가도(정상 종료·예외·return)
    허가증을 반드시 반납한다. 블록 안에서 예외가 나면 실패로 기록된다.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._opened_at: Optional[float] = None
        self._state = CircuitState.CLOSED
        self._probe_in_flight = False
        self._generation = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """현재 서킷 상태 (읽기 전용)"""
        with self._lock:
            return self._state

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @property
    def recovery_timeout(self) -> float:
        return self._recovery_timeout

    def acquire(self) -> Optional[CallPermit]:
        """
        호출 허가증 발급. 차단된 경우 None.

        발급받은 허가증은 **반드시** release()로 반납해야 한다
        (HALF_OPEN 프로브 슬롯이 여기서 풀린다). 직접 호출 대신 guard() 권장.
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return CallPermit(is_probe=False, generation=self._generation)

            if self._state == CircuitState.OPEN:
                if not self._recovery_elapsed():
                    return None
                # 복구 타임아웃 경과 → 프로브 1건만 통과시킨다
                self._state = CircuitState.HALF_OPEN
                self._probe_in_flight = True
                logger.info("서킷 브레이커: HALF_OPEN (복구 프로브 시작)")
                return CallPermit(is_probe=True, generation=self._generation)

            # HALF_OPEN: 이미 프로브가 진행 중이면 결과가 나올 때까지 차단
            if self._probe_in_flight:
                return None
            self._probe_in_flight = True
            return CallPermit(is_probe=True, generation=self._generation)

    def release(self, permit: Optional[CallPermit]):
        """허가증 반납 및 결과 반영 (두 번 호출해도 안전)"""
        if permit is None or permit._settled:
            return
        permit._settled = True

        with self._lock:
            if permit.is_probe:
                # 프로브 슬롯은 결과와 무관하게 반드시 반납한다
                self._probe_in_flight = False
                if (
                    permit.generation != self._generation
                    or self._state != CircuitState.HALF_OPEN
                ):
                    return  # 프로브가 무효화된 뒤 도착 (방어적)
                if permit.failed:
                    self._open_locked("복구 프로브 실패")
                else:
                    self._close_locked()
                return

            # 일반 요청: 발급 이후 서킷이 열린 적이 있거나 지금 CLOSED가 아니면
            # 이 결과는 이미 낡은 정보다. 상태를 되돌리지 않는다.
            if (
                permit.generation != self._generation
                or self._state != CircuitState.CLOSED
            ):
                logger.debug(
                    f"서킷 브레이커: 뒤늦은 결과 무시 "
                    f"(failed={permit.failed}, state={self._state})"
                )
                return

            if permit.failed:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._open_locked(f"연속 {self._failure_count}회 실패")
            else:
                self._failure_count = 0

    @contextmanager
    def guard(self):
        """
        서킷을 통과한 호출 한 건을 감싼다.

        Raises:
            CircuitOpenError: 서킷이 열려 있어 호출이 차단된 경우
        """
        permit = self.acquire()
        if permit is None:
            raise CircuitOpenError("서킷이 열려 있어 호출이 차단되었습니다")

        try:
            yield permit
        except BaseException:
            # 예외로 빠져나가면 실패로 간주 (허가증도 여기서 반납된다)
            permit.failure()
            self.release(permit)
            raise

        self.release(permit)

    def reset(self):
        """상태 초기화 (테스트/운영 수동 복구용). 진행 중인 허가증은 모두 무효화된다."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._probe_in_flight = False
            self._generation += 1

    def _open_locked(self, reason: str):
        """서킷 열기 (락 보유 상태에서 호출)"""
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._probe_in_flight = False
        # 세대를 올려 이 시점 이전에 발급된 허가증의 결과를 모두 무효화한다
        self._generation += 1
        logger.warning(
            f"서킷 브레이커: OPEN ({reason}, "
            f"{self._recovery_timeout:.0f}초 후 복구 시도)"
        )

    def _close_locked(self):
        """서킷 닫기 (락 보유 상태에서 호출)"""
        if self._state != CircuitState.CLOSED:
            logger.info("서킷 브레이커: CLOSED (복구 완료)")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None

    def _recovery_elapsed(self) -> bool:
        """복구 타임아웃 경과 여부 (락 보유 상태에서 호출)"""
        if self._opened_at is None:
            return True
        return (time.monotonic() - self._opened_at) >= self._recovery_timeout


class CallThrottle:
    """
    호출 간 최소 간격을 보장하는 유량 제한기.

    KIS REST 유량(초당 거래건수) 초과로 인한 HTTP 500(EGW00201)을 예방한다.
    배포 환경이 단일 프로세스(WEB_CONCURRENCY=1)이므로, 모든 호출을
    최소 간격으로 직렬화하면 앱키 기준 초당 호출 수를 안전 한도 이내로 유지할 수 있다.
    """

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def wait(self):
        """직전 호출과 최소 간격을 보장 (필요 시 대기)"""
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next_allowed_at - now
            # 다음 호출 허용 시각을 먼저 확정해 두면, 대기 중 들어온 다른 스레드도
            # 자기 슬롯을 예약하고 순서대로 나가게 된다 (락 유지로 직렬화).
            self._next_allowed_at = max(now, self._next_allowed_at) + self._min_interval
            if sleep_for > 0:
                time.sleep(sleep_for)
