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
from cachetools import TTLCache
import threading
import requests
from requests.exceptions import RequestException, Timeout
from sqlalchemy.exc import SQLAlchemyError

from config import CacheConfig, KISConfig, GameConfig
from database import SessionLocal
from utils import get_service_logger

logger = get_service_logger()


# ===========================================
# 서킷 브레이커 (KIS API 장애 대응)
# ===========================================
class CircuitBreaker:
    """
    KIS API 연속 실패 시 일시 차단 (서킷 브레이커 패턴)
    - CLOSED: 정상 운영
    - OPEN: 차단 중 (실패 임계값 초과 후)
    - HALF_OPEN: 복구 시도 중
    """
    FAILURE_THRESHOLD = 5    # 연속 실패 N회 시 차단
    RECOVERY_TIMEOUT = 60    # 차단 후 N초 뒤 복구 시도

    def __init__(self):
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = "CLOSED"
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        """서킷이 열려있으면(차단) True"""
        with self._lock:
            if self._state == "CLOSED":
                return False
            if self._state == "OPEN":
                # 복구 타임아웃 확인
                if self._last_failure_time and \
                        (datetime.now(timezone.utc) - self._last_failure_time).total_seconds() >= self.RECOVERY_TIMEOUT:
                    self._state = "HALF_OPEN"
                    logger.info("KIS API 서킷 브레이커: HALF_OPEN (복구 시도)")
                    return False
                return True
            return False  # HALF_OPEN: 한 번 시도 허용

    def record_success(self):
        """성공 기록 - 서킷 닫기"""
        with self._lock:
            if self._state != "CLOSED":
                logger.info("KIS API 서킷 브레이커: CLOSED (복구 완료)")
            self._failure_count = 0
            self._state = "CLOSED"

    def record_failure(self):
        """실패 기록 - 임계값 초과 시 서킷 열기"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(timezone.utc)
            if self._failure_count >= self.FAILURE_THRESHOLD:
                if self._state != "OPEN":
                    logger.warning(
                        f"KIS API 서킷 브레이커: OPEN "
                        f"(연속 {self._failure_count}회 실패, {self.RECOVERY_TIMEOUT}초 후 복구 시도)"
                    )
                self._state = "OPEN"


# 전역 서킷 브레이커 인스턴스
_circuit_breaker = CircuitBreaker()


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

    @classmethod
    def get_access_token(cls) -> Optional[str]:
        """OAuth 접근 토큰 발급 (24시간 유효)"""
        if not KISConfig.is_configured():
            logger.warning("KIS API 설정이 없습니다. 환경변수를 확인하세요.")
            return None

        # 서킷 브레이커 확인
        if _circuit_breaker.is_open():
            logger.warning("KIS API 서킷 브레이커 열림 - 토큰 발급 스킵")
            return None

        # 토큰이 아직 유효하면 재사용
        if cls._access_token and cls._token_expires_at:
            if datetime.now(timezone.utc) < cls._token_expires_at:
                return cls._access_token

        try:
            url = f"{KISConfig.BASE_URL}/oauth2/tokenP"
            headers = {"Content-Type": "application/json"}
            body = {
                "grant_type": "client_credentials",
                "appkey": KISConfig.APP_KEY,
                "appsecret": KISConfig.APP_SECRET
            }

            resp = requests.post(url, headers=headers, json=body, timeout=KISConfig.API_TIMEOUT)

            if resp.status_code == 200:
                data = resp.json()
                cls._access_token = data.get("access_token")
                # 토큰 만료시간 설정 (23시간 - 여유 1시간)
                cls._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=23)
                logger.info("KIS API 토큰 발급 성공")
                _circuit_breaker.record_success()
                return cls._access_token
            else:
                logger.error(f"KIS 토큰 발급 실패: {resp.status_code}")
                _circuit_breaker.record_failure()
                return None

        except Timeout:
            logger.error("KIS 토큰 발급 타임아웃")
            _circuit_breaker.record_failure()
            return None
        except RequestException as e:
            logger.error(f"KIS 토큰 발급 네트워크 에러: {e}")
            _circuit_breaker.record_failure()
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
        # 서킷 브레이커 확인
        if _circuit_breaker.is_open():
            logger.debug(f"KIS API 서킷 브레이커 열림 - 시세 조회 스킵 ({stock_code})")
            return None

        headers = cls._get_headers(cls.TR_ID_STOCK_PRICE)
        if not headers:
            return None

        try:
            url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",  # 주식
                "FID_INPUT_ISCD": stock_code
            }

            resp = requests.get(url, headers=headers, params=params, timeout=KISConfig.API_TIMEOUT)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":  # 성공
                    output = data.get("output", {})
                    # 필드값이 None/빈값/콤마/소수점이어도 안전하게 변환
                    # (한 필드 파싱 실패로 전체 시세가 버려지지 않도록 방어)
                    result = {
                        "code": stock_code,
                        "name": output.get("hts_kor_isnm") or stock_code,
                        "price": cls._safe_int(output.get("stck_prpr")),
                        "change": cls._safe_float(output.get("prdy_ctrt")),
                        "open": cls._safe_int(output.get("stck_oprc")),
                        "high": cls._safe_int(output.get("stck_hgpr")),
                        "low": cls._safe_int(output.get("stck_lwpr")),
                        "volume": cls._safe_int(output.get("acml_vol")),
                    }
                    _circuit_breaker.record_success()
                    return result
                else:
                    logger.warning(
                        f"KIS 시세 조회 응답 에러 ({stock_code}): "
                        f"rt_cd={data.get('rt_cd')} msg={data.get('msg1')}"
                    )
                    _circuit_breaker.record_failure()
            else:
                # KIS는 HTTP 500에도 본문(msg_cd/msg1)에 실패 사유를 담아준다.
                # (예: EGW00201 초당 거래건수 초과, 권한/헤더 문제 등)
                msg_cd = msg1 = None
                try:
                    body = resp.json()
                    msg_cd = body.get("msg_cd")
                    msg1 = body.get("msg1")
                except ValueError:
                    msg1 = (resp.text or "")[:200]
                logger.warning(
                    f"KIS 시세 조회 HTTP 에러 ({stock_code}): "
                    f"status={resp.status_code} msg_cd={msg_cd} msg={msg1}"
                )
                _circuit_breaker.record_failure()

        except Timeout:
            logger.warning(f"주식 시세 조회 타임아웃 ({stock_code})")
            _circuit_breaker.record_failure()
        except RequestException as e:
            logger.error(f"주식 시세 조회 네트워크 에러 ({stock_code}): {e}")
            _circuit_breaker.record_failure()
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
        headers = cls._get_headers(cls.TR_ID_VOLUME_RANK)
        if not headers:
            logger.warning(f"{label} 순위: 헤더 생성 실패")
            return []

        try:
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

            resp = requests.get(url, headers=headers, params=params, timeout=KISConfig.API_TIMEOUT)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for item in output[:cls.VOLUME_RANK_FETCH_SIZE]:
                        try:
                            results.append({
                                "code": item.get("mksc_shrn_iscd", "") or item.get("stck_shrn_iscd", ""),
                                "name": item.get("hts_kor_isnm", ""),
                                "price": int(item.get("stck_prpr", 0) or 0),
                                "change": float(item.get("prdy_ctrt", 0) or 0),
                                "volume": int(item.get("acml_vol", 0) or 0),
                                "trading_value": int(item.get("acml_tr_pbmn", 0) or 0),
                            })
                        except (ValueError, TypeError, KeyError):
                            continue
                    return results

        except Timeout:
            logger.warning(f"{label} 순위 조회 타임아웃")
        except RequestException as e:
            logger.error(f"{label} 순위 조회 네트워크 에러: {e}")

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
        return any(upper.startswith(prefix.upper()) for prefix in KISConfig.ETF_BRAND_PREFIXES)

    @classmethod
    def get_fluctuation_rank(cls, sort: str = "1", category: str = "stock") -> List[Dict]:
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
                s for s in items
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
        headers = cls._get_headers(cls.TR_ID_MARKET_INDEX)
        if not headers:
            return None

        try:
            url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": index_code
            }

            resp = requests.get(url, headers=headers, params=params, timeout=KISConfig.API_TIMEOUT)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", {})
                    return {
                        "price": float(output.get("bstp_nmix_prpr", 0)),
                        "change": float(output.get("bstp_nmix_prdy_ctrt", 0)),
                    }

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
    _price_cache = TTLCache(maxsize=500, ttl=CacheConfig.STOCK_PRICE_TTL)

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

        # 메모리 캐시
        cls._dynamic_stocks_by_name[name] = code
        cls._dynamic_stocks_by_code[code] = name

        # DB 영구 저장
        try:
            from models import StockCache
            db = SessionLocal()
            try:
                existing = db.query(StockCache).filter(StockCache.stock_code == code).first()
                if existing:
                    # 기존 이름이 코드가 아닌 경우에만 업데이트 스킵
                    if existing.stock_name != name and not existing.stock_name.isdigit():
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

        # 6. 부분 이름 매칭 (동적 캐시)
        for name, code in cls._dynamic_stocks_by_name.items():
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

        # 동적 캐시에서도 검색
        if len(results) < limit:
            for name, code in cls._dynamic_stocks_by_name.items():
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

        # 동적 캐시에서도 검색
        if len(results) < limit:
            for name, code in cls._dynamic_stocks_by_name.items():
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

        # 캐시 확인
        if code in cls._price_cache:
            return cls._price_cache[code]

        # KIS API 조회
        result = KISAPIClient.get_stock_price(code)

        if result:
            # API 응답의 이름 대신 우리 종목명 사용
            result["name"] = name
            cls._price_cache[code] = result
            return result

        # 종목은 인식했으나 KIS 시세 API가 응답하지 않은 경우
        # (종목명 오타가 아니라 시세 조회 실패임을 로그로 명확히 남긴다)
        logger.warning(f"시세 조회 실패: 종목 인식 OK이나 KIS 응답 없음 ({name}/{code})")
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
    def get_top_trading_value(cls, market: str = "KOSPI", limit: int = 10) -> List[Dict]:
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

        # 캐시에 있는 종목은 즉시 반환, 없는 것만 API 호출
        uncached_codes = []
        for code in stock_codes:
            if code in cls._price_cache:
                cached = cls._price_cache[code]
                prices[code] = cached["price"]
            else:
                uncached_codes.append(code)

        if not uncached_codes:
            return prices

        # 병렬로 API 호출 (최대 5개 동시)
        def fetch_price(code):
            stock_info = cls.get_price(code)
            return code, stock_info

        with ThreadPoolExecutor(max_workers=min(5, len(uncached_codes))) as executor:
            futures = {executor.submit(fetch_price, code): code for code in uncached_codes}
            for future in as_completed(futures):
                try:
                    code, stock_info = future.result(timeout=15)
                    if stock_info:
                        prices[code] = stock_info["price"]
                except Exception as e:
                    code = futures[future]
                    logger.warning(f"배치 시세 조회 실패 ({code}): {e}")

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

        def fetch_info(code):
            stock_info = cls.get_price(code)
            return code, stock_info

        with ThreadPoolExecutor(max_workers=min(5, len(stock_codes))) as executor:
            futures = {executor.submit(fetch_info, code): code for code in stock_codes}
            for future in as_completed(futures):
                try:
                    code, stock_info = future.result(timeout=15)
                    if stock_info:
                        result[code] = stock_info
                except Exception as e:
                    code = futures[future]
                    logger.warning(f"배치 종목 정보 조회 실패 ({code}): {e}")

        return result
