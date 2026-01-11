"""
주식 시세 조회 서비스
- 네이버 금융 API를 사용하여 실시간 시세 조회
- pykrx 백업 사용
- 종목 검색
- 캐싱
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from cachetools import TTLCache
import requests
import traceback

from config import CacheConfig

# pykrx 임포트
try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
    print("✅ pykrx 모듈 로드 성공")
except ImportError as e:
    PYKRX_AVAILABLE = False
    print(f"⚠️ pykrx ImportError: {e}")
except Exception as e:
    PYKRX_AVAILABLE = False
    print(f"⚠️ pykrx 로드 실패: {type(e).__name__}: {e}")


class StockService:
    """주식 시세 관련 서비스"""

    # 시세 캐시 (TTL: 1분)
    _price_cache = TTLCache(maxsize=500, ttl=CacheConfig.STOCK_PRICE_TTL)

    # 종목 코드-이름 매핑 캐시
    _ticker_cache = None
    _ticker_cache_date = None

    # HTTP 요청 헤더
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    @classmethod
    def _fetch_naver_stock_list(cls) -> Dict[str, str]:
        """
        네이버 금융에서 종목 리스트 가져오기
        Returns: {종목코드: 종목명}
        """
        tickers = {}

        try:
            # KOSPI 종목
            kospi_url = "https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=2000"
            resp = requests.get(kospi_url, headers=cls.HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("stocks", []):
                    code = item.get("stockCode", "")
                    name = item.get("stockName", "")
                    if code and name:
                        tickers[code] = name
                print(f"✅ KOSPI 종목 로드: {len(tickers)}개")
        except Exception as e:
            print(f"❌ KOSPI 종목 로드 실패: {e}")

        try:
            # KOSDAQ 종목
            kosdaq_url = "https://m.stock.naver.com/api/stocks/marketValue/KOSDAQ?page=1&pageSize=2000"
            resp = requests.get(kosdaq_url, headers=cls.HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                kosdaq_count = 0
                for item in data.get("stocks", []):
                    code = item.get("stockCode", "")
                    name = item.get("stockName", "")
                    if code and name:
                        tickers[code] = name
                        kosdaq_count += 1
                print(f"✅ KOSDAQ 종목 로드: {kosdaq_count}개")
        except Exception as e:
            print(f"❌ KOSDAQ 종목 로드 실패: {e}")

        return tickers

    @classmethod
    def _fetch_naver_price(cls, code: str) -> Optional[Dict]:
        """
        네이버 금융에서 개별 종목 시세 가져오기
        """
        try:
            url = f"https://m.stock.naver.com/api/stock/{code}/basic"
            resp = requests.get(url, headers=cls.HEADERS, timeout=10)

            if resp.status_code != 200:
                return None

            data = resp.json()

            # 현재가 파싱
            close_price = data.get("closePrice", "0").replace(",", "")
            open_price = data.get("openPrice", "0").replace(",", "")
            high_price = data.get("highPrice", "0").replace(",", "")
            low_price = data.get("lowPrice", "0").replace(",", "")
            volume = data.get("accumulatedTradingVolume", "0").replace(",", "")

            # 등락률
            compare_price = data.get("compareToPreviousClosePrice", "0").replace(",", "")
            fluctuations_ratio = data.get("fluctuationsRatio", "0").replace(",", "")

            return {
                "code": code,
                "name": data.get("stockName", code),
                "price": int(close_price) if close_price else 0,
                "change": float(fluctuations_ratio) if fluctuations_ratio else 0.0,
                "open": int(open_price) if open_price else 0,
                "high": int(high_price) if high_price else 0,
                "low": int(low_price) if low_price else 0,
                "volume": int(volume) if volume else 0
            }

        except Exception as e:
            print(f"❌ 네이버 시세 조회 실패 ({code}): {e}")
            return None

    @classmethod
    def _fetch_pykrx_tickers(cls) -> Dict[str, str]:
        """
        pykrx에서 종목 리스트 가져오기
        """
        if not PYKRX_AVAILABLE:
            return {}

        try:
            # 최근 거래일 찾기
            today = datetime.now()
            trading_date = None

            for i in range(10):
                check_date = (today - timedelta(days=i)).strftime("%Y%m%d")
                try:
                    tickers = stock.get_market_ticker_list(check_date, market="KOSPI")
                    if tickers:
                        trading_date = check_date
                        break
                except:
                    continue

            if not trading_date:
                print("❌ pykrx 거래일 찾기 실패")
                return {}

            kospi = stock.get_market_ticker_and_name(trading_date, market="KOSPI")
            kosdaq = stock.get_market_ticker_and_name(trading_date, market="KOSDAQ")

            result = {**kospi, **kosdaq}
            print(f"✅ pykrx 종목 로드: {len(result)}개 (기준일: {trading_date})")
            return result

        except Exception as e:
            print(f"❌ pykrx 종목 로드 실패: {e}")
            traceback.print_exc()
            return {}

    @classmethod
    def _get_tickers(cls) -> Dict[str, str]:
        """
        종목 코드-이름 매핑 조회 (캐싱)
        Returns: {종목코드: 종목명}
        """
        today = datetime.now().date()

        # 캐시가 유효하면 반환
        if cls._ticker_cache and cls._ticker_cache_date == today:
            return cls._ticker_cache

        # 1. 네이버 금융 API 시도
        tickers = cls._fetch_naver_stock_list()

        # 2. 네이버 실패시 pykrx 시도
        if not tickers:
            print("⚠️ 네이버 API 실패, pykrx 시도...")
            tickers = cls._fetch_pykrx_tickers()

        if tickers:
            cls._ticker_cache = tickers
            cls._ticker_cache_date = today
            print(f"✅ 총 종목 로드 완료: {len(tickers)}개")
        else:
            print("❌ 종목 로드 실패 - 모든 소스 실패")
            cls._ticker_cache = {}

        return cls._ticker_cache

    @classmethod
    def search_stock(cls, query: str) -> Optional[Dict]:
        """
        종목 검색 (이름 또는 코드)
        Returns: {"code": "005930", "name": "삼성전자"} or None
        """
        query = query.strip()
        tickers = cls._get_tickers()

        if not tickers:
            return None

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

        # 1. 네이버 금융 API 시도
        result = cls._fetch_naver_price(code)

        # 2. 네이버 실패시 pykrx 시도
        if not result and PYKRX_AVAILABLE:
            try:
                today = datetime.now()
                today_str = today.strftime("%Y%m%d")
                start_date = (today - timedelta(days=7)).strftime("%Y%m%d")

                df = stock.get_market_ohlcv(start_date, today_str, code)

                if not df.empty:
                    latest = df.iloc[-1]

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
            except Exception as e:
                print(f"❌ pykrx 시세 조회 실패 ({code}): {e}")

        # 캐시 저장
        if result:
            cls._price_cache[code] = result

        return result

    @classmethod
    def get_top_volume(cls, market: str = "KOSPI", limit: int = 10) -> List[Dict]:
        """
        거래량 상위 종목
        """
        try:
            # 네이버 금융 API
            url = f"https://m.stock.naver.com/api/stocks/tradingVolume/{market}?page=1&pageSize={limit}"
            resp = requests.get(url, headers=cls.HEADERS, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("stocks", []):
                    close_price = item.get("closePrice", "0").replace(",", "")
                    volume = item.get("accumulatedTradingVolume", "0").replace(",", "")
                    change = item.get("fluctuationsRatio", "0").replace(",", "")

                    results.append({
                        "code": item.get("stockCode", ""),
                        "name": item.get("stockName", ""),
                        "price": int(close_price) if close_price else 0,
                        "volume": int(volume) if volume else 0,
                        "change": float(change) if change else 0.0
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
        try:
            # 네이버 금융 API - 상승률 상위
            url = f"https://m.stock.naver.com/api/stocks/fluctuation/KOSPI?page=1&pageSize={limit}&sosok=KOSPI"
            resp = requests.get(url, headers=cls.HEADERS, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("stocks", []):
                    close_price = item.get("closePrice", "0").replace(",", "")
                    volume = item.get("accumulatedTradingVolume", "0").replace(",", "")
                    change = item.get("fluctuationsRatio", "0").replace(",", "")

                    results.append({
                        "code": item.get("stockCode", ""),
                        "name": item.get("stockName", ""),
                        "price": int(close_price) if close_price else 0,
                        "volume": int(volume) if volume else 0,
                        "change": float(change) if change else 0.0
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
        try:
            # 네이버 금융 API - 하락률 상위
            url = f"https://m.stock.naver.com/api/stocks/fluctuation/KOSPI?page=1&pageSize={limit}&order=desc"
            resp = requests.get(url, headers=cls.HEADERS, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("stocks", []):
                    close_price = item.get("closePrice", "0").replace(",", "")
                    volume = item.get("accumulatedTradingVolume", "0").replace(",", "")
                    change = item.get("fluctuationsRatio", "0").replace(",", "")

                    # 하락 종목만 필터 (음수)
                    change_val = float(change) if change else 0.0
                    if change_val >= 0:
                        continue

                    results.append({
                        "code": item.get("stockCode", ""),
                        "name": item.get("stockName", ""),
                        "price": int(close_price) if close_price else 0,
                        "volume": int(volume) if volume else 0,
                        "change": change_val
                    })

                    if len(results) >= limit:
                        break

                return results

        except Exception as e:
            print(f"❌ 급락주 조회 실패: {e}")

        return []

    @classmethod
    def get_market_overview(cls) -> Dict:
        """
        시장 전체 현황 (KOSPI/KOSDAQ 지수)
        """
        result = {}

        try:
            # KOSPI 지수
            kospi_url = "https://m.stock.naver.com/api/index/KOSPI/basic"
            resp = requests.get(kospi_url, headers=cls.HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                close_price = data.get("closePrice", "0").replace(",", "")
                change = data.get("fluctuationsRatio", "0").replace(",", "")
                result["kospi"] = {
                    "price": float(close_price) if close_price else 0.0,
                    "change": float(change) if change else 0.0
                }
        except Exception as e:
            print(f"❌ KOSPI 지수 조회 실패: {e}")

        try:
            # KOSDAQ 지수
            kosdaq_url = "https://m.stock.naver.com/api/index/KOSDAQ/basic"
            resp = requests.get(kosdaq_url, headers=cls.HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                close_price = data.get("closePrice", "0").replace(",", "")
                change = data.get("fluctuationsRatio", "0").replace(",", "")
                result["kosdaq"] = {
                    "price": float(close_price) if close_price else 0.0,
                    "change": float(change) if change else 0.0
                }
        except Exception as e:
            print(f"❌ KOSDAQ 지수 조회 실패: {e}")

        return result
