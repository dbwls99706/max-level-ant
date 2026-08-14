"""
주식 시세 조회 서비스 (개선)
- 한국투자증권 KIS API 사용 (공식 API)
- 실시간 주가, 거래량, 등락률 조회
- 개선된 캐시 전략 (TTL + 무효화)
- 서킷 브레이커 (연속 실패 시 일시적 차단)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from cachetools import TTLCache
import threading
import time
import requests
from requests.exceptions import RequestException, Timeout
from sqlalchemy.exc import SQLAlchemyError

from game_config import GameConfig
from settings import CacheConfig, KISConfig, SkillConfig
from database import SessionLocal
from contextlib import contextmanager

from utils import (
    BoundedConcurrency,
    CallThrottle,
    CircuitBreaker,
    CircuitOpenError,
    ConcurrencyLimitError,
    budget,
    get_service_logger,
)

logger = get_service_logger()

# 전역 서킷 브레이커 (KIS API 장애 시 호출 차단)
_circuit_breaker = CircuitBreaker(
    failure_threshold=KISConfig.CIRCUIT_FAILURE_THRESHOLD,
    recovery_timeout=KISConfig.CIRCUIT_RECOVERY_TIMEOUT,
)

# 전역 KIS 유량 제한기 (초당 ~1/min_interval 건)
# 급등/급락(순위 API)은 통과하는데 종목별 현재가(inquire-price)만 자주·병렬로
# 호출돼 한도를 넘던 증상을 완화한다.
_kis_throttle = CallThrottle(KISConfig.MIN_CALL_INTERVAL)

# 프로세스 전체 동시 KIS 호출 상한.
# throttle은 호출이 '시작되는 간격'만 제어하므로 상류가 느려지면 in-flight
# 호출이 계속 쌓인다. 요청 예산이 끝나면 응답은 먼저 돌려주지만
# (executor.shutdown(wait=False)) 그 worker와 소켓은 백그라운드에 남는다.
# 동시 실행 수 자체에 상한을 걸어 그 누적을 막는다.
_kis_limiter = BoundedConcurrency(KISConfig.MAX_CONCURRENT_CALLS)


@contextmanager
def _kis_call():
    """
    KIS 외부 호출 한 건을 감싸는 컨텍스트 (동시 실행 상한 + 서킷 브레이커).

    슬롯을 서킷 guard '바깥'에서 잡는 이유:
      - guard 안에서 잡으면 HALF_OPEN 프로브가 슬롯을 기다리는 동안
        복구 프로브 자리를 붙잡게 된다.
      - 슬롯 확보 실패는 로컬 자원 제한이지 API 장애가 아니므로
        서킷 실패로 집계되면 안 된다.

    슬롯 대기는 min(설정 상한, 남은 요청 예산)으로 제한되며,
    확보하지 못하면 ConcurrencyLimitError를 던진다(호출을 시작하지 않는다).
    """
    with _kis_limiter.slot(timeout=budget.timeout_for(KISConfig.SLOT_WAIT_CAP)):
        with _circuit_breaker.guard() as call:
            yield call


def _timeout_detail(started: float, applied: float) -> str:
    """타임아웃 로그에 붙일 진단 문구.

    '타임아웃'만 찍으면 상류가 느린 건지 우리가 상한을 너무 좁게 준 건지
    구분할 수 없다. 실제 대기 시간과 그때 적용한 상한을 함께 남긴다.
    남은 예산이 작아 상한이 깎였다면 그 사실도 여기서 드러난다.
    """
    return f"{time.monotonic() - started:.2f}초 대기 / 상한 {applied:.2f}초"


class _RankCache:
    """순위 조회 결과 캐시.

    순위(급등/급락/거래량/거래대금)는 유저마다 다르지 않다. 같은 데이터를
    사람 수만큼 다시 물어볼 이유가 없고, KIS가 느려지는 장중일수록 그
    낭비가 그대로 실패로 돌아온다.

    두 층으로 나눈다.
      - fresh: 짧은 TTL. 이 안에 있으면 KIS를 아예 안 부른다.
      - last_good: 만료 없는 마지막 성공값. 조회가 실패했을 때 빈 화면
        대신 조금 지난 데이터라도 보여주기 위한 것이다. 순위는 몇십 초
        늦어도 쓸모가 있지만, 빈 화면은 아무 쓸모가 없다.
    """

    TTL = 60  # 초

    def __init__(self):
        self._fresh = TTLCache(maxsize=16, ttl=self.TTL)
        self._last_good: Dict[str, List[Dict]] = {}
        self._lock = threading.Lock()

    def get_fresh(self, key: str) -> Optional[List[Dict]]:
        with self._lock:
            return self._fresh.get(key)

    def put(self, key: str, value: List[Dict]) -> None:
        if not value:
            return
        with self._lock:
            self._fresh[key] = value
            self._last_good[key] = value

    def get_stale(self, key: str) -> Optional[List[Dict]]:
        with self._lock:
            return self._last_good.get(key)

    def clear(self) -> None:
        with self._lock:
            self._fresh.clear()
            self._last_good.clear()


_rank_cache = _RankCache()


class KISAPIClient:
    """한국투자증권 API 클라이언트"""

    # API Transaction IDs
    TR_ID_STOCK_PRICE = "FHKST01010100"  # 주식 현재가 조회
    TR_ID_DAILY_PRICE = "FHKST03010100"  # 주식 기간별 시세 (일봉)
    TR_ID_VOLUME_RANK = "FHPST01710000"  # 거래량 순위 조회
    TR_ID_MARKET_INDEX = "FHPUP02100000"  # 시장 지수 조회

    # 거래량 순위 API에서 가져올 후보 종목 수
    # 급등/급락 산출 시 레버리지/인버스 등을 걸러내고도 충분한 후보를 확보하기 위해
    # 최종 노출 개수(10)보다 넉넉하게 가져온다.
    VOLUME_RANK_FETCH_SIZE = 30

    _access_token = None
    _token_expires_at = None
    _token_lock = threading.Lock()  # 토큰 중복 발급 방지

    # DB에 토큰을 남길 때 쓰는 발급처 식별자
    TOKEN_PROVIDER = "kis"

    # 토큰 만료 안전 여유.
    # 호출 도중 만료되는 일이 없도록 실제 만료보다 이만큼 일찍 폐기한다.
    TOKEN_EXPIRY_MARGIN = timedelta(hours=1)

    # KIS가 expires_in을 주지 않을 때 가정할 유효기간
    TOKEN_DEFAULT_LIFETIME = timedelta(hours=24)

    @classmethod
    def _token_ttl(cls, expires_in) -> timedelta:
        """
        응답의 expires_in(초)에서 실제로 신뢰할 유효기간을 계산.

        KIS가 값을 주지 않거나 이상한 값을 주면 기본값을 쓰고,
        만료 직전에 걸치지 않도록 안전 여유를 뺀다.
        """
        seconds = cls._safe_int(expires_in, 0)
        lifetime = (
            timedelta(seconds=seconds) if seconds > 0 else cls.TOKEN_DEFAULT_LIFETIME
        )
        # 여유를 빼서 음수/0이 되면 짧게라도 쓸 수 있게 최소치를 보장한다
        return max(lifetime - cls.TOKEN_EXPIRY_MARGIN, timedelta(minutes=1))

    @classmethod
    def _cached_token(cls) -> Optional[str]:
        """메모리에 남은 토큰이 아직 유효하면 반환"""
        if cls._access_token and cls._token_expires_at:
            if datetime.now(timezone.utc) < cls._token_expires_at:
                return cls._access_token
        return None

    @classmethod
    def _load_token_from_db(cls) -> Optional[str]:
        """
        DB에 저장된 토큰을 메모리로 복구.

        재배포·콜드스타트로 프로세스가 새로 떠도 만료 전이면 재발급하지 않는다.
        DB가 없거나 실패해도 토큰 발급 자체는 계속돼야 하므로 예외는 삼킨다.
        """
        from models import ApiToken

        try:
            db = SessionLocal()
            try:
                row = (
                    db.query(ApiToken)
                    .filter(ApiToken.provider == cls.TOKEN_PROVIDER)
                    .first()
                )
                if row is None or not row.access_token or row.expires_at is None:
                    return None

                # 저장은 naive UTC 규약
                expires_at = row.expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= datetime.now(timezone.utc):
                    return None

                cls._access_token = row.access_token
                cls._token_expires_at = expires_at
                logger.info("저장된 KIS 토큰 재사용 (재발급 생략)")
                return row.access_token
            finally:
                db.close()
        except SQLAlchemyError as e:
            logger.warning(f"저장된 KIS 토큰 조회 실패: {e}")
            return None

    @classmethod
    def _save_token_to_db(cls, token: str, expires_at: datetime) -> None:
        """발급받은 토큰을 DB에 저장 (실패해도 발급 결과는 유지)"""
        from models import ApiToken

        try:
            db = SessionLocal()
            try:
                naive_expiry = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
                row = (
                    db.query(ApiToken)
                    .filter(ApiToken.provider == cls.TOKEN_PROVIDER)
                    .first()
                )
                if row is None:
                    db.add(
                        ApiToken(
                            provider=cls.TOKEN_PROVIDER,
                            access_token=token,
                            expires_at=naive_expiry,
                        )
                    )
                else:
                    row.access_token = token
                    row.expires_at = naive_expiry
                db.commit()
            except SQLAlchemyError:
                # 다른 프로세스가 같은 PK를 먼저 넣었을 수도 있다. 토큰은 이미
                # 메모리에 있으므로 저장 실패가 조회를 막지는 않는다.
                db.rollback()
                raise
            finally:
                db.close()
        except SQLAlchemyError as e:
            logger.warning(f"KIS 토큰 저장 실패 (동작에는 영향 없음): {e}")

    @classmethod
    def get_access_token(cls) -> Optional[str]:
        """OAuth 접근 토큰 발급 (24시간 유효, 스레드 안전)"""
        if not KISConfig.is_configured():
            logger.warning("KIS API 설정이 없습니다. 환경변수를 확인하세요.")
            return None

        # 토큰이 아직 유효하면 재사용 (락 없이 빠른 확인)
        # 서킷 브레이커는 실제 HTTP 호출 직전에만 확인한다. 캐시된 토큰 반환 경로에서
        # 서킷을 통과시키면 HALF_OPEN 프로브 슬롯을 잡고도 반납하지 않게 된다.
        cached = cls._cached_token()
        if cached:
            return cached

        # 병렬 배치 조회 중 여러 스레드가 동시에 만료를 감지해도
        # 토큰 발급 요청은 한 번만 나가도록 락으로 직렬화
        with cls._token_lock:
            # 락 대기 중 다른 스레드가 이미 발급했으면 재사용
            cached = cls._cached_token()
            if cached:
                return cached

            # 재기동 직후라면 메모리만 비었을 뿐 DB에 유효한 토큰이 남아 있다.
            # HTTP 발급보다 먼저 확인해 불필요한 재발급을 막는다.
            stored = cls._load_token_from_db()
            if stored:
                return stored

            if budget.exhausted(SkillConfig.MIN_CALL_BUDGET):
                logger.warning("응답 예산 소진 - KIS 토큰 발급 스킵")
                return None

            try:
                with _kis_call() as call:
                    url = f"{KISConfig.BASE_URL}/oauth2/tokenP"
                    headers = {"Content-Type": "application/json"}
                    body = {
                        "grant_type": "client_credentials",
                        "appkey": KISConfig.APP_KEY,
                        "appsecret": KISConfig.APP_SECRET,
                    }

                    # 유량 제한 대기가 예산을 잡아먹지 않도록 상한을 건다
                    if not _kis_throttle.wait(max_wait=budget.remaining()):
                        logger.warning("응답 예산 부족 - KIS 토큰 발급 스킵")
                        return None
                    resp = requests.post(
                        url,
                        headers=headers,
                        json=body,
                        timeout=budget.timeout_for(KISConfig.TOKEN_TIMEOUT),
                    )

                    if resp.status_code != 200:
                        logger.error(
                            f"KIS 토큰 발급 실패: {resp.status_code} "
                            f"{cls._describe_error_body(resp)}"
                        )
                        call.failure()
                        return None

                    data = resp.json()
                    token = data.get("access_token")
                    if not token:
                        logger.error("KIS 토큰 발급 응답에 access_token이 없습니다")
                        call.failure()
                        return None

                    cls._access_token = token
                    cls._token_expires_at = datetime.now(timezone.utc) + cls._token_ttl(
                        data.get("expires_in")
                    )
                    # 다음 재기동에서 재발급하지 않도록 남겨둔다
                    cls._save_token_to_db(token, cls._token_expires_at)
                    logger.info("KIS API 토큰 발급 성공")
                    return cls._access_token

            except CircuitOpenError:
                logger.warning("KIS API 서킷 브레이커 열림 - 토큰 발급 스킵")
                return None
            except Timeout:
                logger.error("KIS 토큰 발급 타임아웃")
                return None
            except RequestException as e:
                logger.error(f"KIS 토큰 발급 네트워크 에러: {e}")
                return None

    @classmethod
    def _get_headers(cls, tr_id: str) -> Optional[Dict]:
        """API 요청 헤더 생성"""
        token = cls.get_access_token()
        if not token:
            return None

        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": KISConfig.APP_KEY,
            "appsecret": KISConfig.APP_SECRET,
            "tr_id": tr_id,
        }

    @staticmethod
    def _describe_error_body(resp) -> str:
        """실패 응답 본문에서 KIS 에러 코드/메시지를 추출 (로그용)"""
        try:
            body = resp.json()
        except ValueError:
            return f"body={(resp.text or '')[:200]}"
        return f"msg_cd={body.get('msg_cd')} msg={body.get('msg1')}"

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """KIS 응답 필드를 안전하게 정수로 변환 (콤마/소수점/빈값 허용)"""
        if value is None:
            return default
        s = str(value).strip().replace(",", "")
        if not s:
            return default
        try:
            # "70500.00" 같은 소수 표기도 허용
            return int(float(s))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """KIS 응답 필드를 안전하게 실수로 변환"""
        if value is None:
            return default
        s = str(value).strip().replace(",", "")
        if not s:
            return default
        try:
            return float(s)
        except (ValueError, TypeError):
            return default

    @classmethod
    def get_stock_price(cls, stock_code: str) -> Optional[Dict]:
        """
        주식 현재가 조회
        tr_id: FHKST01010100
        """
        # 남은 예산이 없으면 어차피 카카오 타임아웃이므로 호출하지 않는다
        if budget.exhausted(SkillConfig.MIN_CALL_BUDGET):
            logger.debug(f"응답 예산 소진 - 시세 조회 스킵 ({stock_code})")
            return None

        # 토큰 발급은 자체적으로 서킷을 통과 판정한다.
        # 아래 guard() 안에서 호출하면 프로브 슬롯을 중첩 요청하게 되므로 먼저 처리한다.
        headers = cls._get_headers(cls.TR_ID_STOCK_PRICE)
        if not headers:
            return None

        try:
            with _kis_call() as call:
                url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",  # 주식
                    "FID_INPUT_ISCD": stock_code,
                }

                # 초당 거래건수 초과 방지 (대기도 예산 안에서만)
                if not _kis_throttle.wait(max_wait=budget.remaining()):
                    logger.debug(f"응답 예산 부족 - 시세 조회 스킵 ({stock_code})")
                    return None
                resp = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=budget.timeout_for(KISConfig.API_TIMEOUT),
                )

                if resp.status_code != 200:
                    # KIS는 HTTP 500에도 본문(msg_cd/msg1)에 실패 사유를 담아준다.
                    # (예: EGW00201 초당 거래건수 초과, 권한/헤더 문제 등)
                    call.failure()
                    logger.warning(
                        f"KIS 시세 조회 HTTP 에러 ({stock_code}): "
                        f"status={resp.status_code} {cls._describe_error_body(resp)}"
                    )
                    return None

                data = resp.json()
                if data.get("rt_cd") != "0":
                    # rt_cd != "0"은 잘못된 종목코드 등 "데이터 없음" 응답 -
                    # API 자체는 정상 동작 중이므로 서킷 실패로 집계하지 않는다
                    # (존재하지 않는 종목 몇 번 조회로 전체 시세가 차단되는 오탐 방지)
                    logger.warning(
                        f"KIS 시세 조회 응답 에러 ({stock_code}): "
                        f"rt_cd={data.get('rt_cd')} msg={data.get('msg1')}"
                    )
                    return None

                output = data.get("output", {})
                # 필드값이 None/빈값/콤마/소수점이어도 안전하게 변환
                # (한 필드 파싱 실패로 전체 시세가 버려지지 않도록 방어)
                return {
                    "code": stock_code,
                    "name": output.get("hts_kor_isnm") or stock_code,
                    "price": cls._safe_int(output.get("stck_prpr")),
                    "change": cls._safe_float(output.get("prdy_ctrt")),
                    "open": cls._safe_int(output.get("stck_oprc")),
                    "high": cls._safe_int(output.get("stck_hgpr")),
                    "low": cls._safe_int(output.get("stck_lwpr")),
                    "volume": cls._safe_int(output.get("acml_vol")),
                }

        except ConcurrencyLimitError as e:
            logger.debug(f"KIS 동시 호출 상한 - 시세 조회 스킵 ({stock_code}): {e}")
        except CircuitOpenError:
            logger.debug(f"KIS API 서킷 브레이커 열림 - 시세 조회 스킵 ({stock_code})")
        except Timeout:
            logger.warning(f"주식 시세 조회 타임아웃 ({stock_code})")
        except RequestException as e:
            logger.error(f"주식 시세 조회 네트워크 에러 ({stock_code}): {e}")
        except (ValueError, KeyError) as e:
            logger.error(f"주식 시세 응답 파싱 실패 ({stock_code}): {e}")

        return None

    @classmethod
    def get_volume_rank(cls, market: str = "J", blng_cls_code: str = "0") -> List[Dict]:
        """
        거래량/거래대금 순위 조회
        tr_id: FHPST01710000
        blng_cls_code: 0=평균거래량, 1=거래증가율, 2=평균거래회전율, 3=거래금액순, 4=평균거래금액회전율
        """
        label = "거래대금" if blng_cls_code == "3" else "거래량"
        cache_key = f"volume:{market}:{blng_cls_code}"

        cached = _rank_cache.get_fresh(cache_key)
        if cached is not None:
            return cached

        if budget.exhausted(SkillConfig.MIN_CALL_BUDGET):
            logger.debug(f"응답 예산 소진 - {label} 순위 조회 스킵")
            return _rank_cache.get_stale(cache_key) or []
        headers = cls._get_headers(cls.TR_ID_VOLUME_RANK)
        if not headers:
            logger.warning(f"{label} 순위: 헤더 생성 실패")
            return _rank_cache.get_stale(cache_key) or []

        started = time.monotonic()
        applied = KISConfig.RANK_TIMEOUT
        try:
            with _kis_call() as call:
                url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"
                params = {
                    "FID_COND_MRKT_DIV_CODE": market,
                    "FID_COND_SCR_DIV_CODE": "20171",
                    "FID_INPUT_ISCD": "0000",
                    "FID_DIV_CLS_CODE": "0",
                    "FID_BLNG_CLS_CODE": blng_cls_code,
                    "FID_TRGT_CLS_CODE": "111111111",
                    "FID_TRGT_EXLS_CLS_CODE": "000000",
                    "FID_INPUT_PRICE_1": "",
                    "FID_INPUT_PRICE_2": "",
                    "FID_VOL_CNT": "",
                    "FID_INPUT_DATE_1": "",
                }

                # 초당 거래건수 초과 방지 (대기도 예산 안에서만)
                if not _kis_throttle.wait(max_wait=budget.remaining()):
                    logger.debug(f"응답 예산 부족 - {label} 순위 조회 스킵")
                    return []
                # 순위 API는 30여 종목을 한 번에 돌려주므로 단일 시세보다
                # 느리다. 같은 상한을 쓰면 장중에 통째로 실패한다.
                applied = budget.timeout_for(KISConfig.RANK_TIMEOUT)
                started = time.monotonic()
                resp = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=applied,
                )

                if resp.status_code != 200:
                    call.failure()
                    logger.warning(
                        f"{label} 순위 조회 HTTP 에러: status={resp.status_code} "
                        f"{cls._describe_error_body(resp)}"
                    )
                    return []

                data = resp.json()
                if data.get("rt_cd") != "0":
                    # 데이터 없음 응답 - API는 정상이므로 서킷 실패로 집계하지 않는다
                    logger.warning(
                        f"{label} 순위 조회 응답 에러: "
                        f"rt_cd={data.get('rt_cd')} msg={data.get('msg1')}"
                    )
                    return []

                results = []
                for item in data.get("output", [])[: cls.VOLUME_RANK_FETCH_SIZE]:
                    try:
                        results.append(
                            {
                                "code": item.get("mksc_shrn_iscd", "")
                                or item.get("stck_shrn_iscd", ""),
                                "name": item.get("hts_kor_isnm", ""),
                                "price": int(item.get("stck_prpr", 0) or 0),
                                "change": float(item.get("prdy_ctrt", 0) or 0),
                                "volume": int(item.get("acml_vol", 0) or 0),
                                "trading_value": int(item.get("acml_tr_pbmn", 0) or 0),
                            }
                        )
                    except (ValueError, TypeError, KeyError):
                        continue
                _rank_cache.put(cache_key, results)
                return results

        except ConcurrencyLimitError as e:
            logger.debug(f"KIS 동시 호출 상한 - {label} 순위 조회 스킵: {e}")
        except CircuitOpenError:
            logger.debug(f"KIS API 서킷 브레이커 열림 - {label} 순위 조회 스킵")
        except Timeout:
            logger.warning(
                f"{label} 순위 조회 타임아웃 - {_timeout_detail(started, applied)}"
            )
        except RequestException as e:
            logger.error(f"{label} 순위 조회 네트워크 에러: {e}")
        except ValueError as e:
            logger.error(f"{label} 순위 응답 파싱 실패: {e}")

        # 조회가 실패했다. 빈 화면보다 조금 지난 순위가 낫다.
        stale = _rank_cache.get_stale(cache_key)
        if stale:
            logger.info(f"{label} 순위 - 직전 성공값으로 응답 ({len(stale)}종목)")
            return stale
        return []

    @staticmethod
    def _is_excluded_from_ranking(name: str) -> bool:
        """레버리지/인버스 등 지수 배율 상품인지 판단 (개별 종목 순위에서 제외)"""
        if not name:
            return False
        return any(kw in name for kw in KISConfig.RANKING_EXCLUDE_KEYWORDS)

    @staticmethod
    def _is_etf_or_etn(name: str) -> bool:
        """ETF/ETN 종목인지 판단 (브랜드 접두사 또는 ETN 표기로 식별)"""
        if not name:
            return False
        upper = name.upper()
        if "ETN" in upper:
            return True
        return any(
            upper.startswith(prefix.upper()) for prefix in KISConfig.ETF_BRAND_PREFIXES
        )

    @classmethod
    def get_fluctuation_rank(
        cls, sort: str = "1", category: str = "stock"
    ) -> List[Dict]:
        """
        등락률 순위 조회 (거래량 순위 데이터를 등락률로 재정렬)
        sort: 1=상승률순, 2=하락률순
        category:
            - "stock": 개별 종목만 (ETF/ETN, 레버리지/인버스 제외)
            - "etf": ETF/ETN만
        """
        items = cls.get_volume_rank("J")
        if not items:
            return []

        if category == "etf":
            # ETF/ETN만 노출
            items = [s for s in items if cls._is_etf_or_etn(s.get("name", ""))]
        else:
            # 개별 종목만: ETF/ETN, 레버리지/인버스 제외
            items = [
                s
                for s in items
                if not cls._is_etf_or_etn(s.get("name", ""))
                and not cls._is_excluded_from_ranking(s.get("name", ""))
            ]

        # 등락률로 정렬
        if sort == "1":  # 상승률순
            items = sorted(items, key=lambda x: x.get("change", 0), reverse=True)
        else:  # 하락률순
            items = sorted(items, key=lambda x: x.get("change", 0))

        return items[:10]

    @classmethod
    def get_market_index(cls, index_code: str) -> Optional[Dict]:
        """
        시장 지수 조회 (KOSPI: 0001, KOSDAQ: 1001)
        tr_id: FHPUP02100000
        """
        if budget.exhausted(SkillConfig.MIN_CALL_BUDGET):
            logger.debug(f"응답 예산 소진 - 지수 조회 스킵 ({index_code})")
            return None

        headers = cls._get_headers(cls.TR_ID_MARKET_INDEX)
        if not headers:
            return None

        try:
            with _kis_call() as call:
                url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
                params = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": index_code}

                # 초당 거래건수 초과 방지 (대기도 예산 안에서만)
                if not _kis_throttle.wait(max_wait=budget.remaining()):
                    logger.debug(f"응답 예산 부족 - 지수 조회 스킵 ({index_code})")
                    return None
                resp = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=budget.timeout_for(KISConfig.API_TIMEOUT),
                )

                if resp.status_code != 200:
                    call.failure()
                    logger.warning(
                        f"지수 조회 HTTP 에러 ({index_code}): status={resp.status_code} "
                        f"{cls._describe_error_body(resp)}"
                    )
                    return None

                data = resp.json()
                if data.get("rt_cd") != "0":
                    # 데이터 없음 응답 - API는 정상이므로 서킷 실패로 집계하지 않는다
                    logger.warning(
                        f"지수 조회 응답 에러 ({index_code}): "
                        f"rt_cd={data.get('rt_cd')} msg={data.get('msg1')}"
                    )
                    return None

                output = data.get("output", {})
                return {
                    "price": cls._safe_float(output.get("bstp_nmix_prpr")),
                    "change": cls._safe_float(output.get("bstp_nmix_prdy_ctrt")),
                }

        except ConcurrencyLimitError as e:
            logger.debug(f"KIS 동시 호출 상한 - 지수 조회 스킵 ({index_code}): {e}")
        except CircuitOpenError:
            logger.debug(f"KIS API 서킷 브레이커 열림 - 지수 조회 스킵 ({index_code})")
        except Timeout:
            logger.warning(f"지수 조회 타임아웃 ({index_code})")
        except RequestException as e:
            logger.error(f"지수 조회 네트워크 에러 ({index_code}): {e}")
        except (ValueError, KeyError) as e:
            logger.error(f"지수 응답 파싱 실패 ({index_code}): {e}")

        return None


class StockService:
    """주식 시세 관련 서비스"""

    # 시세 캐시 (TTL: 1분)
    # TTLCache는 스레드 안전하지 않으므로 배치 병렬 조회 시 락으로 보호
    _price_cache = TTLCache(maxsize=500, ttl=CacheConfig.STOCK_PRICE_TTL)
    _price_cache_lock = threading.Lock()

    # 배치 조회에서 개별 future를 기다릴 최대 시간 (초).
    # 요청 예산이 걸려 있으면 그 잔여 시간을 넘기지 않는다.
    BATCH_WAIT_CAP = 3.0

    @staticmethod
    def _batch_wait() -> float:
        """배치 future 대기 시간 = min(상한, 요청에 남은 예산)"""
        return budget.timeout_for(StockService.BATCH_WAIT_CAP)

    @staticmethod
    def _cap_limit(limit: int, default: int = 10) -> int:
        """검색 결과 limit 제한 (악의적 대량 요청 방지)"""
        if limit <= 0:
            return default
        return min(limit, GameConfig.MAX_SEARCH_LIMIT)

    # 종목 코드-이름 매핑 (주요 종목)
    # 공개 정보로 KRX에서 제공하는 종목 코드
    STOCK_LIST = {
        # 시가총액 상위
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "373220": "LG에너지솔루션",
        "207940": "삼성바이오로직스",
        "005380": "현대차",
        "006400": "삼성SDI",
        "051910": "LG화학",
        "000270": "기아",
        "035420": "NAVER",
        "005490": "POSCO홀딩스",
        "035720": "카카오",
        "055550": "신한지주",
        "105560": "KB금융",
        "012330": "현대모비스",
        "068270": "셀트리온",
        "028260": "삼성물산",
        "003670": "포스코퓨처엠",
        "066570": "LG전자",
        "086790": "하나금융지주",
        "003550": "LG",
        "032830": "삼성생명",
        "015760": "한국전력",
        "034730": "SK",
        "096770": "SK이노베이션",
        "017670": "SK텔레콤",
        "009150": "삼성전기",
        "018260": "삼성에스디에스",
        "030200": "KT",
        "033780": "KT&G",
        "010130": "고려아연",
        "259960": "크래프톤",
        "000810": "삼성화재",
        "034220": "LG디스플레이",
        "011200": "HMM",
        "010950": "S-Oil",
        "316140": "우리금융지주",
        "024110": "기업은행",
        "003490": "대한항공",
        "009540": "HD한국조선해양",
        "010140": "삼성중공업",
        "036570": "엔씨소프트",
        "035250": "강원랜드",
        "090430": "아모레퍼시픽",
        "011170": "롯데케미칼",
        "005850": "에스엘",
        "000720": "현대건설",
        "047050": "포스코인터내셔널",
        "051900": "LG생활건강",
        "326030": "SK바이오팜",
        "377300": "카카오페이",
        "352820": "하이브",
        "263750": "펄어비스",
        "041510": "에스엠",
        "112040": "위메이드",
        "293490": "카카오게임즈",
    }

    # 이름 -> 코드 역매핑
    _name_to_code = {v: k for k, v in STOCK_LIST.items()}

    # API에서 가져온 종목 캐시 (급등주/급락주 등)
    # 쓰기는 _cache_load_lock으로 보호, 순회는 스냅샷(list) 사용
    # (순회 중 다른 스레드가 추가하면 RuntimeError 발생 방지)
    _dynamic_stocks_by_name = {}  # {name: code}
    _dynamic_stocks_by_code = {}  # {code: name}
    _cache_loaded = False  # DB 캐시 로드 여부
    _cache_load_lock = threading.Lock()  # Race Condition 방지

    @classmethod
    def load_stock_cache(cls):
        """서버 시작 시 DB에서 종목 캐시 로드 (Thread-safe)"""
        # 이중 체크 패턴 (lock 없이 빠른 체크 후, lock 안에서 재확인)
        if cls._cache_loaded:
            return

        with cls._cache_load_lock:
            if cls._cache_loaded:  # lock 획득 후 재확인 (Race Condition 방지)
                return

            try:
                from models import StockCache

                db = SessionLocal()
                try:
                    cached_stocks = db.query(StockCache).all()
                    for stock in cached_stocks:
                        cls._dynamic_stocks_by_name[stock.stock_name] = stock.stock_code
                        cls._dynamic_stocks_by_code[stock.stock_code] = stock.stock_name
                    cls._cache_loaded = True
                    logger.info(f"종목 캐시 로드 완료: {len(cached_stocks)}개")
                finally:
                    db.close()
            except SQLAlchemyError as e:
                logger.warning(f"종목 캐시 로드 DB 에러: {e}")

    @classmethod
    def _cache_stock(cls, code: str, name: str):
        """종목 캐시 (메모리 + DB 영구 저장)"""
        if not name or not code:
            return

        # 이름이 코드와 같으면 (API에서 이름 못 받은 경우) 캐시하지 않음
        if name == code or (name.isdigit() and len(name) == 6):
            # 기존에 저장된 이름이 있으면 그것 사용
            existing_name = cls._dynamic_stocks_by_code.get(code)
            if existing_name and existing_name != code:
                return  # 이미 좋은 이름이 있음
            return  # 코드를 이름으로 저장하지 않음

        # 이미 메모리 캐시에 동일한 이름으로 존재하면 DB 쓰기 스킵
        if cls._dynamic_stocks_by_code.get(code) == name:
            return

        # 메모리 캐시 (쓰기는 락으로 보호 - 순회 스냅샷과의 경합 방지)
        with cls._cache_load_lock:
            cls._dynamic_stocks_by_name[name] = code
            cls._dynamic_stocks_by_code[code] = name

        # DB 영구 저장
        try:
            from models import StockCache

            db = SessionLocal()
            try:
                existing = (
                    db.query(StockCache).filter(StockCache.stock_code == code).first()
                )
                if existing:
                    # 기존 이름이 코드가 아닌 경우에만 업데이트 스킵
                    if (
                        existing.stock_name != name
                        and not existing.stock_name.isdigit()
                    ):
                        pass  # 기존 좋은 이름 유지
                    else:
                        existing.stock_name = name
                        db.commit()
                else:
                    new_cache = StockCache(stock_code=code, stock_name=name)
                    db.add(new_cache)
                    db.commit()
            finally:
                db.close()
        except SQLAlchemyError as e:
            # DB 저장 실패해도 메모리 캐시는 유지
            logger.warning(f"종목 캐시 DB 저장 실패 ({code}): {e}")

    @classmethod
    def search_stock(cls, query: str) -> Optional[Dict]:
        """
        종목 검색 (이름 또는 코드)
        """
        query = query.strip()

        # 1. 정확한 코드 매칭 (STOCK_LIST)
        if query in cls.STOCK_LIST:
            return {"code": query, "name": cls.STOCK_LIST[query]}

        # 2. 정확한 코드 매칭 (동적 캐시)
        if query in cls._dynamic_stocks_by_code:
            return {"code": query, "name": cls._dynamic_stocks_by_code[query]}

        # 3. 정확한 이름 매칭 (STOCK_LIST)
        if query in cls._name_to_code:
            code = cls._name_to_code[query]
            return {"code": code, "name": query}

        # 4. 정확한 이름 매칭 (동적 캐시)
        if query in cls._dynamic_stocks_by_name:
            return {"code": cls._dynamic_stocks_by_name[query], "name": query}

        # 5. 부분 이름 매칭 (STOCK_LIST)
        for code, name in cls.STOCK_LIST.items():
            if query in name:
                return {"code": code, "name": name}

        # 6. 부분 이름 매칭 (동적 캐시) - 순회 중 변경 방지 위해 스냅샷 사용
        for name, code in list(cls._dynamic_stocks_by_name.items()):
            if query in name:
                return {"code": code, "name": name}

        # 7. 공백 제거 후 검색
        query_clean = query.replace(" ", "")
        for code, name in cls.STOCK_LIST.items():
            if query_clean in name.replace(" ", ""):
                return {"code": code, "name": name}

        # 8. 6자리 숫자면 직접 API 조회 시도
        if query.isdigit() and len(query) == 6:
            result = KISAPIClient.get_stock_price(query)
            if result and result.get("price", 0) > 0:
                cls._cache_stock(query, result.get("name", query))
                return {"code": query, "name": result.get("name", query)}

        return None

    @classmethod
    def search_similar_stocks(cls, query: str, limit: int = 5) -> List[Dict]:
        """유사 종목 검색"""
        limit = cls._cap_limit(limit, default=5)
        query = query.strip().replace(" ", "")
        results = []
        seen_codes = set()

        # STOCK_LIST에서 검색
        for code, name in cls.STOCK_LIST.items():
            name_clean = name.replace(" ", "")
            if query in name_clean or any(c in name_clean for c in query):
                results.append({"code": code, "name": name})
                seen_codes.add(code)
                if len(results) >= limit:
                    break

        # 동적 캐시에서도 검색 (스냅샷 순회)
        if len(results) < limit:
            for name, code in list(cls._dynamic_stocks_by_name.items()):
                if code in seen_codes:
                    continue
                name_clean = name.replace(" ", "")
                if query in name_clean or any(c in name_clean for c in query):
                    results.append({"code": code, "name": name})
                    seen_codes.add(code)
                    if len(results) >= limit:
                        break

        # 첫 글자로 시작하는 종목
        if not results and query:
            for code, name in cls.STOCK_LIST.items():
                if name.startswith(query[0]):
                    results.append({"code": code, "name": name})
                    if len(results) >= limit:
                        break

        return results

    @classmethod
    def search_stocks(cls, query: str, limit: int = 10) -> List[Dict]:
        """종목 검색 (여러 결과)"""
        limit = cls._cap_limit(limit, default=10)
        query = query.strip().lower()
        results = []
        seen_codes = set()

        # STOCK_LIST에서 검색
        for code, name in cls.STOCK_LIST.items():
            if query in name.lower() or query in code:
                results.append({"code": code, "name": name})
                seen_codes.add(code)
                if len(results) >= limit:
                    break

        # 동적 캐시에서도 검색 (스냅샷 순회)
        if len(results) < limit:
            for name, code in list(cls._dynamic_stocks_by_name.items()):
                if code in seen_codes:
                    continue
                if query in name.lower() or query in code:
                    results.append({"code": code, "name": name})
                    if len(results) >= limit:
                        break

        return results

    @classmethod
    def get_price(cls, code_or_name: str) -> Optional[Dict]:
        """주식 시세 조회"""
        stock_info = cls.search_stock(code_or_name)
        if not stock_info:
            return None

        code = stock_info["code"]
        name = stock_info["name"]  # 우리가 가진 종목명 사용

        # 캐시 확인 (TTL 만료 처리와 경합하지 않도록 락 보호)
        with cls._price_cache_lock:
            cached = cls._price_cache.get(code)
        if cached:
            return cached

        # KIS API 조회
        result = KISAPIClient.get_stock_price(code)

        if result:
            # API 응답의 이름 대신 우리 종목명 사용
            result["name"] = name
            with cls._price_cache_lock:
                cls._price_cache[code] = result
            return result

        # 종목은 인식했으나 KIS 시세 API가 응답하지 않은 경우
        # (종목명 오타가 아니라 시세 조회 실패임을 로그로 명확히 남긴다)
        logger.warning(
            f"시세 조회 실패: 종목 인식 OK이나 KIS 응답 없음 ({name}/{code})"
        )
        return None

    @classmethod
    def get_top_volume(cls, market: str = "KOSPI", limit: int = 10) -> List[Dict]:
        """거래량 상위 종목"""
        limit = cls._cap_limit(limit, default=10)
        market_code = "J" if market == "KOSPI" else "Q"
        stocks = KISAPIClient.get_volume_rank(market_code)[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_top_trading_value(
        cls, market: str = "KOSPI", limit: int = 10
    ) -> List[Dict]:
        """거래대금 상위 종목"""
        limit = cls._cap_limit(limit, default=10)
        market_code = "J" if market == "KOSPI" else "Q"
        stocks = KISAPIClient.get_volume_rank(market_code, blng_cls_code="3")[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_top_gainers(cls, limit: int = 10) -> List[Dict]:
        """급등주 (상승률 상위)"""
        limit = cls._cap_limit(limit, default=10)
        stocks = KISAPIClient.get_fluctuation_rank(sort="1")[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_top_losers(cls, limit: int = 10) -> List[Dict]:
        """급락주 (하락률 상위, 개별 종목)"""
        limit = cls._cap_limit(limit, default=10)
        stocks = KISAPIClient.get_fluctuation_rank(sort="2")[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_top_etf_gainers(cls, limit: int = 10) -> List[Dict]:
        """ETF/ETN 급등 (상승률 상위)"""
        limit = cls._cap_limit(limit, default=10)
        stocks = KISAPIClient.get_fluctuation_rank(sort="1", category="etf")[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_top_etf_losers(cls, limit: int = 10) -> List[Dict]:
        """ETF/ETN 급락 (하락률 상위)"""
        limit = cls._cap_limit(limit, default=10)
        stocks = KISAPIClient.get_fluctuation_rank(sort="2", category="etf")[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_market_overview(cls) -> Dict:
        """시장 현황 (KOSPI/KOSDAQ 지수)"""
        result = {}

        kospi = KISAPIClient.get_market_index("0001")
        if kospi:
            result["kospi"] = kospi

        kosdaq = KISAPIClient.get_market_index("1001")
        if kosdaq:
            result["kosdaq"] = kosdaq

        return result

    @classmethod
    def batch_get_prices(cls, stock_codes: set) -> Dict[str, int]:
        """
        여러 종목 시세 일괄 조회 (병렬 처리로 성능 개선)

        Args:
            stock_codes: 종목 코드 집합

        Returns:
            {종목코드: 현재가} 딕셔너리
        """
        if not stock_codes:
            return {}

        prices = {}

        # 캐시에 있는 종목은 즉시 반환, 없는 것만 API 호출 (락 보호)
        uncached_codes = []
        with cls._price_cache_lock:
            for code in stock_codes:
                cached = cls._price_cache.get(code)
                if cached:
                    prices[code] = cached["price"]
                else:
                    uncached_codes.append(code)

        if not uncached_codes:
            return prices

        # 워커 스레드는 요청 deadline을 자동으로 물려받지 않으므로 명시적으로 넘긴다
        deadline = budget.current_deadline()

        def fetch_price(code):
            with budget.adopt(deadline):
                return code, cls.get_price(code)

        # 병렬로 API 호출 (최대 5개 동시)
        # ThreadPoolExecutor를 with로 쓰면 블록을 나갈 때 shutdown(wait=True)라,
        # 예산이 끝나도 실행 중인 worker가 끝날 때까지 요청 스레드가 붙잡힌다.
        # 직접 관리하며 wait=False로 내려 곧바로 반환시킨다.
        executor = ThreadPoolExecutor(max_workers=min(5, len(uncached_codes)))
        futures = {executor.submit(fetch_price, code): code for code in uncached_codes}
        try:
            # 대기 상한은 as_completed에 건다. future.result(timeout=)에 걸면
            # as_completed가 이미 완료까지 기다린 뒤라 아무 효과가 없다.
            for future in as_completed(futures, timeout=cls._batch_wait()):
                try:
                    code, stock_info = future.result()
                    if stock_info:
                        prices[code] = stock_info["price"]
                except Exception as e:
                    logger.warning(f"배치 시세 조회 실패 ({futures[future]}): {e}")
        except FuturesTimeout:
            pending = [futures[f] for f in futures if not f.done()]
            logger.warning(f"배치 시세 조회 예산 초과 - 미완료 {len(pending)}건 포기")
        finally:
            # 아직 시작하지 않은 작업은 취소하고, 실행 중인 worker는 기다리지 않는다.
            # (파이썬 스레드는 강제 종료할 수 없어 백그라운드에서 마저 끝난다)
            executor.shutdown(wait=False, cancel_futures=True)

        return prices

    @classmethod
    def batch_get_stock_info(cls, stock_codes: set) -> Dict[str, Dict]:
        """
        여러 종목 전체 정보 일괄 조회 (병렬 처리)

        Args:
            stock_codes: 종목 코드 집합

        Returns:
            {종목코드: stock_info} 딕셔너리
        """
        if not stock_codes:
            return {}

        result = {}
        deadline = budget.current_deadline()

        def fetch_info(code):
            with budget.adopt(deadline):
                return code, cls.get_price(code)

        # with 대신 직접 관리 - 이유는 batch_get_prices의 주석 참고
        executor = ThreadPoolExecutor(max_workers=min(5, len(stock_codes)))
        futures = {executor.submit(fetch_info, code): code for code in stock_codes}
        try:
            for future in as_completed(futures, timeout=cls._batch_wait()):
                try:
                    code, stock_info = future.result()
                    if stock_info:
                        result[code] = stock_info
                except Exception as e:
                    logger.warning(f"배치 종목 정보 조회 실패 ({futures[future]}): {e}")
        except FuturesTimeout:
            pending = [futures[f] for f in futures if not f.done()]
            logger.warning(
                f"배치 종목 정보 조회 예산 초과 - 미완료 {len(pending)}건 포기"
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        return result
