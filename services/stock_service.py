"""
주식 시세 조회 서비스 (개선)
- 한국투자증권 KIS API 사용 (공식 API)
- 실시간 주가, 거래량, 등락률 조회
- 개선된 캐시 전략 (TTL + 무효화)
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set
from cachetools import TTLCache
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError as RequestsConnectionError
from sqlalchemy.exc import SQLAlchemyError

from config import CacheConfig, KISConfig
from database import SessionLocal
from utils import get_service_logger

logger = get_service_logger()


class KISAPIClient:
    """한국투자증권 API 클라이언트"""

    _access_token = None
    _token_expires_at = None

    @classmethod
    def get_access_token(cls) -> Optional[str]:
        """OAuth 접근 토큰 발급 (24시간 유효)"""
        if not KISConfig.is_configured():
            logger.warning("KIS API 설정이 없습니다. 환경변수를 확인하세요.")
            return None

        # 토큰이 아직 유효하면 재사용
        if cls._access_token and cls._token_expires_at:
            if datetime.now() < cls._token_expires_at:
                return cls._access_token

        try:
            url = f"{KISConfig.BASE_URL}/oauth2/tokenP"
            headers = {"Content-Type": "application/json"}
            body = {
                "grant_type": "client_credentials",
                "appkey": KISConfig.APP_KEY,
                "appsecret": KISConfig.APP_SECRET
            }

            resp = requests.post(url, headers=headers, json=body, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                cls._access_token = data.get("access_token")
                # 토큰 만료시간 설정 (23시간 - 여유 1시간)
                cls._token_expires_at = datetime.now() + timedelta(hours=23)
                logger.info("KIS API 토큰 발급 성공")
                return cls._access_token
            else:
                logger.error(f"KIS 토큰 발급 실패: {resp.status_code}")
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

    @classmethod
    def get_stock_price(cls, stock_code: str) -> Optional[Dict]:
        """
        주식 현재가 조회
        tr_id: FHKST01010100
        """
        headers = cls._get_headers("FHKST01010100")
        if not headers:
            return None

        try:
            url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",  # 주식
                "FID_INPUT_ISCD": stock_code
            }

            resp = requests.get(url, headers=headers, params=params, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":  # 성공
                    output = data.get("output", {})
                    return {
                        "code": stock_code,
                        "name": output.get("hts_kor_isnm", stock_code),
                        "price": int(output.get("stck_prpr", 0)),
                        "change": float(output.get("prdy_ctrt", 0)),
                        "open": int(output.get("stck_oprc", 0)),
                        "high": int(output.get("stck_hgpr", 0)),
                        "low": int(output.get("stck_lwpr", 0)),
                        "volume": int(output.get("acml_vol", 0)),
                    }
                else:
                    logger.warning(f"KIS API 에러: {data.get('msg1')}")

        except Timeout:
            logger.warning(f"주식 시세 조회 타임아웃 ({stock_code})")
        except RequestException as e:
            logger.error(f"주식 시세 조회 네트워크 에러 ({stock_code}): {e}")
        except (ValueError, KeyError) as e:
            logger.error(f"주식 시세 응답 파싱 실패 ({stock_code}): {e}")

        return None

    @classmethod
    def get_volume_rank(cls, market: str = "J") -> List[Dict]:
        """
        거래량 순위 조회
        tr_id: FHPST01710000
        """
        headers = cls._get_headers("FHPST01710000")
        if not headers:
            logger.warning("거래량 순위: 헤더 생성 실패")
            return []

        try:
            url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"
            params = {
                "FID_COND_MRKT_DIV_CODE": market,
                "FID_COND_SCR_DIV_CODE": "20171",
                "FID_INPUT_ISCD": "0000",
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",
                "FID_TRGT_CLS_CODE": "111111111",
                "FID_TRGT_EXLS_CLS_CODE": "000000",
                "FID_INPUT_PRICE_1": "",
                "FID_INPUT_PRICE_2": "",
                "FID_VOL_CNT": "",
                "FID_INPUT_DATE_1": "",
            }

            resp = requests.get(url, headers=headers, params=params, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", [])
                    results = []
                    for item in output[:10]:
                        try:
                            results.append({
                                "code": item.get("mksc_shrn_iscd", "") or item.get("stck_shrn_iscd", ""),
                                "name": item.get("hts_kor_isnm", ""),
                                "price": int(item.get("stck_prpr", 0) or 0),
                                "change": float(item.get("prdy_ctrt", 0) or 0),
                                "volume": int(item.get("acml_vol", 0) or 0),
                            })
                        except (ValueError, TypeError, KeyError):
                            continue
                    return results

        except Timeout:
            logger.warning("거래량 순위 조회 타임아웃")
        except RequestException as e:
            logger.error(f"거래량 순위 조회 네트워크 에러: {e}")

        return []

    @classmethod
    def get_fluctuation_rank(cls, sort: str = "1") -> List[Dict]:
        """
        등락률 순위 조회 (거래량 순위 데이터를 등락률로 재정렬)
        sort: 1=상승률순, 2=하락률순
        """
        items = cls.get_volume_rank("J")
        if not items:
            return []

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
        headers = cls._get_headers("FHPUP02100000")
        if not headers:
            return None

        try:
            url = f"{KISConfig.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": index_code
            }

            resp = requests.get(url, headers=headers, params=params, timeout=10)

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

    @classmethod
    def load_stock_cache(cls):
        """서버 시작 시 DB에서 종목 캐시 로드"""
        if cls._cache_loaded:
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
        except SQLAlchemyError:
            # DB 저장 실패해도 메모리 캐시는 유지
            pass

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

        return None

    @classmethod
    def get_top_volume(cls, market: str = "KOSPI", limit: int = 10) -> List[Dict]:
        """거래량 상위 종목"""
        market_code = "J" if market == "KOSPI" else "Q"
        stocks = KISAPIClient.get_volume_rank(market_code)[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_top_gainers(cls, limit: int = 10) -> List[Dict]:
        """급등주 (상승률 상위)"""
        stocks = KISAPIClient.get_fluctuation_rank(sort="1")[:limit]
        # 캐시에 저장
        for s in stocks:
            cls._cache_stock(s.get("code"), s.get("name"))
        return stocks

    @classmethod
    def get_top_losers(cls, limit: int = 10) -> List[Dict]:
        """급락주 (하락률 상위)"""
        stocks = KISAPIClient.get_fluctuation_rank(sort="2")[:limit]
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
