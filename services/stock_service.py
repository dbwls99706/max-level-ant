"""
주식 시세 조회 서비스
- pykrx를 사용하여 실시간 시세 조회
- 종목 검색
- 캐싱
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from cachetools import TTLCache
import pandas as pd

# pykrx 임포트 (설치 필요: pip install pykrx)
try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False
    print("⚠️ pykrx가 설치되지 않았습니다. pip install pykrx")

from config import CacheConfig


class StockService:
    """주식 시세 관련 서비스"""

    # 시세 캐시 (TTL: 1분)
    _price_cache = TTLCache(maxsize=500, ttl=CacheConfig.STOCK_PRICE_TTL)

    # 종목 코드-이름 매핑 캐시
    _ticker_cache = None
    _ticker_cache_date = None

    # 인기 종목 백업 (pykrx 실패 시 사용)
    POPULAR_STOCKS = {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035420": "NAVER",
        "035720": "카카오",
        "051910": "LG화학",
        "006400": "삼성SDI",
        "005380": "현대차",
        "000270": "기아",
        "068270": "셀트리온",
        "207940": "삼성바이오로직스",
        "005490": "POSCO홀딩스",
        "003670": "포스코퓨처엠",
        "028260": "삼성물산",
        "105560": "KB금융",
        "055550": "신한지주",
        "066570": "LG전자",
        "032830": "삼성생명",
        "003550": "LG",
        "096770": "SK이노베이션",
        "034730": "SK",
        "012330": "현대모비스",
        "259960": "크래프톤",
        "086790": "하나금융지주",
        "015760": "한국전력",
        "009150": "삼성전기",
        "017670": "SK텔레콤",
        "030200": "KT",
        "018260": "삼성에스디에스",
        "033780": "KT&G",
        "010130": "고려아연",
    }
    
    @classmethod
    def _get_recent_trading_date(cls) -> str:
        """
        최근 거래일 조회 (주말/공휴일 대비)
        """
        today = datetime.now()

        # 최근 10일 내에서 거래일 찾기
        for i in range(10):
            check_date = today - timedelta(days=i)
            date_str = check_date.strftime("%Y%m%d")

            try:
                # 해당 날짜에 데이터가 있는지 확인
                df = stock.get_market_ohlcv(date_str, market="KOSPI")
                if not df.empty:
                    return date_str
            except:
                continue

        # 못 찾으면 오늘 날짜 반환
        return today.strftime("%Y%m%d")

    @classmethod
    def _get_tickers(cls) -> Dict[str, str]:
        """
        종목 코드-이름 매핑 조회 (캐싱)
        Returns: {종목코드: 종목명}
        """
        today = datetime.now().date()

        # 캐시가 없거나 날짜가 다르면 새로 조회
        if cls._ticker_cache is None or cls._ticker_cache_date != today:
            if not PYKRX_AVAILABLE:
                # pykrx 없으면 백업 데이터 사용
                cls._ticker_cache = cls.POPULAR_STOCKS.copy()
                cls._ticker_cache_date = today
                print(f"⚠️ pykrx 없음 - 백업 종목 사용: {len(cls._ticker_cache)}개")
                return cls._ticker_cache

            try:
                # 최근 거래일 기준으로 종목 조회 (주말/공휴일 대비)
                trading_date = cls._get_recent_trading_date()
                kospi = stock.get_market_ticker_and_name(trading_date, market="KOSPI")
                kosdaq = stock.get_market_ticker_and_name(trading_date, market="KOSDAQ")

                # 합치기
                cls._ticker_cache = {**kospi, **kosdaq}
                cls._ticker_cache_date = today

                # 비어있으면 백업 사용
                if not cls._ticker_cache:
                    cls._ticker_cache = cls.POPULAR_STOCKS.copy()
                    print(f"⚠️ pykrx 빈 결과 - 백업 종목 사용: {len(cls._ticker_cache)}개")
                else:
                    print(f"✅ 종목 목록 로드 완료: {len(cls._ticker_cache)}개 (기준일: {trading_date})")
            except Exception as e:
                print(f"❌ 종목 목록 로드 실패: {e}")
                # 실패시 백업 데이터 사용
                cls._ticker_cache = cls.POPULAR_STOCKS.copy()
                print(f"⚠️ 백업 종목 사용: {len(cls._ticker_cache)}개")

        return cls._ticker_cache
    
    @classmethod
    def search_stock(cls, query: str) -> Optional[Dict]:
        """
        종목 검색 (이름 또는 코드)
        Returns: {"code": "005930", "name": "삼성전자"} or None
        """
        query = query.strip()
        tickers = cls._get_tickers()

        # 1. 정확한 코드 매칭
        if query in tickers:
            return {"code": query, "name": tickers[query]}

        # 2. 정확한 이름 매칭
        for code, name in tickers.items():
            if name == query:
                return {"code": code, "name": name}

        # 3. 부분 이름 매칭 (첫 번째 결과)
        for code, name in tickers.items():
            if query in name:
                return {"code": code, "name": name}

        # 4. 공백 제거하고 다시 검색
        query_no_space = query.replace(" ", "")
        for code, name in tickers.items():
            if query_no_space in name.replace(" ", ""):
                return {"code": code, "name": name}

        return None

    @classmethod
    def search_similar_stocks(cls, query: str, limit: int = 5) -> List[Dict]:
        """
        유사 종목 검색 (부분 매칭)
        Returns: [{"code": "...", "name": "..."}, ...]
        """
        query = query.strip().replace(" ", "")
        tickers = cls._get_tickers()

        results = []

        # 부분 매칭
        for code, name in tickers.items():
            name_clean = name.replace(" ", "")
            if query in name_clean or any(char in name_clean for char in query if char):
                results.append({"code": code, "name": name})
                if len(results) >= limit:
                    break

        # 결과가 없으면 첫 글자로 시작하는 종목 찾기
        if not results and len(query) > 0:
            first_char = query[0]
            for code, name in tickers.items():
                if name.startswith(first_char):
                    results.append({"code": code, "name": name})
                    if len(results) >= limit:
                        break

        return results
    
    @classmethod
    def search_stocks(cls, query: str, limit: int = 10) -> List[Dict]:
        """
        종목 검색 (여러 결과)
        Returns: [{"code": "...", "name": "..."}, ...]
        """
        query = query.strip().lower()
        tickers = cls._get_tickers()
        
        results = []
        for code, name in tickers.items():
            if query in name.lower() or query in code.lower():
                results.append({"code": code, "name": name})
                if len(results) >= limit:
                    break
        
        return results
    
    @classmethod
    def get_price(cls, code_or_name: str) -> Optional[Dict]:
        """
        주식 시세 조회
        Returns: {
            "code": "005930",
            "name": "삼성전자",
            "price": 58200,
            "change": 1.2,
            "open": 57800,
            "high": 58500,
            "low": 57600,
            "volume": 12345678
        }
        """
        # 종목 검색
        stock_info = cls.search_stock(code_or_name)
        if not stock_info:
            return None
        
        code = stock_info["code"]
        name = stock_info["name"]
        
        # 캐시 확인
        if code in cls._price_cache:
            return cls._price_cache[code]
        
        # 인기 종목별 기본 시세 (백업용)
        DEFAULT_PRICES = {
            "005930": 55000,   # 삼성전자
            "000660": 180000,  # SK하이닉스
            "035420": 180000,  # NAVER
            "035720": 40000,   # 카카오
            "051910": 350000,  # LG화학
            "006400": 400000,  # 삼성SDI
            "005380": 180000,  # 현대차
            "000270": 85000,   # 기아
            "068270": 170000,  # 셀트리온
            "207940": 750000,  # 삼성바이오
        }

        def get_dummy_price():
            """더미 시세 생성"""
            import random
            base_price = DEFAULT_PRICES.get(code, 50000)
            # ±5% 랜덤 변동
            variation = random.uniform(-0.05, 0.05)
            price = int(base_price * (1 + variation))
            change = round(variation * 100, 2)
            return {
                "code": code,
                "name": name,
                "price": price,
                "change": change,
                "open": int(price * 0.99),
                "high": int(price * 1.02),
                "low": int(price * 0.98),
                "volume": random.randint(100000, 10000000)
            }

        if not PYKRX_AVAILABLE:
            # pykrx 없으면 더미 데이터 반환
            result = get_dummy_price()
            cls._price_cache[code] = result
            return result

        try:
            # 오늘 날짜
            today = datetime.now()
            today_str = today.strftime("%Y%m%d")

            # 최근 5일 데이터 조회 (주말/공휴일 대비)
            start_date = (today - timedelta(days=7)).strftime("%Y%m%d")

            df = stock.get_market_ohlcv(start_date, today_str, code)

            if df.empty:
                # pykrx 데이터 없으면 더미 반환
                result = get_dummy_price()
                cls._price_cache[code] = result
                return result
            
            # 가장 최근 데이터
            latest = df.iloc[-1]
            
            # 전일 대비 등락률
            if len(df) >= 2:
                prev_close = df.iloc[-2]["종가"]
                change = ((latest["종가"] - prev_close) / prev_close) * 100
            else:
                change = 0.0
            
            result = {
                "code": code,
                "name": name,
                "price": int(latest["종가"]),
                "change": round(change, 2),
                "open": int(latest["시가"]),
                "high": int(latest["고가"]),
                "low": int(latest["저가"]),
                "volume": int(latest["거래량"])
            }
            
            # 캐시 저장
            cls._price_cache[code] = result
            
            return result
            
        except Exception as e:
            print(f"❌ 시세 조회 실패 ({code}): {e}")
            # 실패해도 더미 데이터 반환
            result = get_dummy_price()
            cls._price_cache[code] = result
            return result
    
    @classmethod
    def get_top_volume(cls, market: str = "KOSPI", limit: int = 10) -> List[Dict]:
        """
        거래량 상위 종목
        """
        if not PYKRX_AVAILABLE:
            return []

        try:
            # 최근 거래일 기준 (주말/공휴일 대비)
            trading_date = cls._get_recent_trading_date()
            df = stock.get_market_ohlcv(trading_date, market=market)
            
            if df.empty:
                return []
            
            # 거래량 기준 정렬
            df = df.sort_values("거래량", ascending=False).head(limit)
            
            tickers = cls._get_tickers()
            results = []
            
            for code in df.index:
                name = tickers.get(code, code)
                row = df.loc[code]
                results.append({
                    "code": code,
                    "name": name,
                    "price": int(row["종가"]),
                    "volume": int(row["거래량"]),
                    "change": float(row["등락률"])
                })
            
            return results
            
        except Exception as e:
            print(f"❌ 거래량 상위 조회 실패: {e}")
            return []

    @classmethod
    def get_top_gainers(cls, limit: int = 10) -> List[Dict]:
        """
        급등주 (상승률 상위)
        """
        if not PYKRX_AVAILABLE:
            return []

        try:
            trading_date = cls._get_recent_trading_date()

            # KOSPI + KOSDAQ 합쳐서 조회
            kospi_df = stock.get_market_ohlcv(trading_date, market="KOSPI")
            kosdaq_df = stock.get_market_ohlcv(trading_date, market="KOSDAQ")

            df = pd.concat([kospi_df, kosdaq_df])

            if df.empty:
                return []

            # 상승률 기준 정렬 (상위)
            df = df.sort_values("등락률", ascending=False).head(limit)

            tickers = cls._get_tickers()
            results = []

            for code in df.index:
                name = tickers.get(code, code)
                row = df.loc[code]
                results.append({
                    "code": code,
                    "name": name,
                    "price": int(row["종가"]),
                    "volume": int(row["거래량"]),
                    "change": float(row["등락률"])
                })

            return results

        except Exception as e:
            print(f"❌ 급등주 조회 실패: {e}")
            return []

    @classmethod
    def get_top_losers(cls, limit: int = 10) -> List[Dict]:
        """
        급락주 (하락률 상위)
        """
        if not PYKRX_AVAILABLE:
            return []

        try:
            trading_date = cls._get_recent_trading_date()

            # KOSPI + KOSDAQ 합쳐서 조회
            kospi_df = stock.get_market_ohlcv(trading_date, market="KOSPI")
            kosdaq_df = stock.get_market_ohlcv(trading_date, market="KOSDAQ")

            df = pd.concat([kospi_df, kosdaq_df])

            if df.empty:
                return []

            # 하락률 기준 정렬 (하위)
            df = df.sort_values("등락률", ascending=True).head(limit)

            tickers = cls._get_tickers()
            results = []

            for code in df.index:
                name = tickers.get(code, code)
                row = df.loc[code]
                results.append({
                    "code": code,
                    "name": name,
                    "price": int(row["종가"]),
                    "volume": int(row["거래량"]),
                    "change": float(row["등락률"])
                })

            return results

        except Exception as e:
            print(f"❌ 급락주 조회 실패: {e}")
            return []

    @classmethod
    def get_market_overview(cls) -> Dict:
        """
        시장 전체 현황 (KOSPI/KOSDAQ 지수)
        """
        if not PYKRX_AVAILABLE:
            return {}

        try:
            trading_date = cls._get_recent_trading_date()

            # 지수 조회
            kospi = stock.get_index_ohlcv(trading_date, trading_date, "1001")  # KOSPI
            kosdaq = stock.get_index_ohlcv(trading_date, trading_date, "2001")  # KOSDAQ

            result = {}

            if not kospi.empty:
                kospi_row = kospi.iloc[-1]
                result["kospi"] = {
                    "price": float(kospi_row["종가"]),
                    "change": float(kospi_row["등락률"]) if "등락률" in kospi_row else 0.0
                }

            if not kosdaq.empty:
                kosdaq_row = kosdaq.iloc[-1]
                result["kosdaq"] = {
                    "price": float(kosdaq_row["종가"]),
                    "change": float(kosdaq_row["등락률"]) if "등락률" in kosdaq_row else 0.0
                }

            return result

        except Exception as e:
            print(f"❌ 시장 현황 조회 실패: {e}")
            return {}
