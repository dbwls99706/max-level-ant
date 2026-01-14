"""
랭킹 서비스 (리팩토링)
- 수익률 기준 랭킹
- N+1 쿼리 최적화 적용
- 중복 로직 제거
"""
from typing import List, Dict, Optional, Tuple, Set
from sqlalchemy.orm import Session, joinedload
from cachetools import TTLCache

from models import User, Holding
from services.stock_service import StockService
from config import CacheConfig


class RankingService:
    """랭킹 관련 서비스"""

    # 랭킹 캐시
    _ranking_cache = TTLCache(maxsize=10, ttl=CacheConfig.RANKING_TTL)

    @classmethod
    def _get_display_name(cls, user: User) -> str:
        """유저 표시 이름 반환"""
        if user.nickname:
            return user.nickname
        return f"투자자{user.kakao_id[-4:]}"

    @classmethod
    def _prefetch_stock_prices(cls, stock_codes: Set[str]) -> Dict[str, int]:
        """
        주식 가격 일괄 조회 (캐시 활용)
        N+1 문제 해결을 위한 일괄 조회
        """
        prices = {}
        for code in stock_codes:
            stock_info = StockService.get_price(code)
            if stock_info:
                prices[code] = stock_info["price"]
        return prices

    @classmethod
    def _calculate_total_asset_batch(
        cls,
        user: User,
        user_holdings: List[Holding],
        stock_prices: Dict[str, int]
    ) -> Tuple[int, float]:
        """
        일괄 조회된 데이터로 총 자산 계산 (N+1 최적화)
        """
        total_asset = user.cash

        for h in user_holdings:
            if h.quantity > 0:
                price = stock_prices.get(h.stock_code, h.avg_price)
                total_asset += price * h.quantity

        # 수익률 계산 (0으로 나누기 방지)
        if user.initial_cash > 0:
            profit_rate = ((total_asset - user.initial_cash) / user.initial_cash) * 100
        else:
            profit_rate = 0.0

        return total_asset, profit_rate

    @classmethod
    def _build_rankings(cls, db: Session) -> List[Dict]:
        """
        전체 유저 랭킹 계산 (공통 로직)

        Returns:
            정렬된 랭킹 리스트 (순위 포함)
        """
        # 1. 모든 유저와 보유 주식을 한 번에 조회 (joinedload로 N+1 방지)
        users = db.query(User).options(joinedload(User.holdings)).all()

        if not users:
            return []

        # 2. 필요한 모든 종목 코드 수집 및 유저별 보유 주식 매핑
        all_stock_codes: Set[str] = set()
        user_holdings_map: Dict[str, List[Holding]] = {}

        for user in users:
            user_holdings = [h for h in user.holdings if h.quantity > 0]
            user_holdings_map[user.kakao_id] = user_holdings
            for h in user_holdings:
                all_stock_codes.add(h.stock_code)

        # 3. 주식 가격 일괄 조회 (캐시 활용)
        stock_prices = cls._prefetch_stock_prices(all_stock_codes)

        # 4. 각 유저의 총 자산 계산
        rankings = []
        for user in users:
            user_holdings = user_holdings_map.get(user.kakao_id, [])
            total_asset, profit_rate = cls._calculate_total_asset_batch(
                user, user_holdings, stock_prices
            )

            rankings.append({
                "kakao_id": user.kakao_id,
                "nickname": cls._get_display_name(user),
                "total_asset": total_asset,
                "profit_rate": profit_rate
            })

        # 5. 수익률 기준 정렬 및 순위 부여
        rankings.sort(key=lambda x: x["profit_rate"], reverse=True)
        for i, r in enumerate(rankings):
            r["rank"] = i + 1

        return rankings

    @classmethod
    def calculate_total_asset(cls, db: Session, user: User) -> Tuple[int, float]:
        """
        유저의 총 자산 및 수익률 계산 (단일 유저용)
        """
        total_asset = user.cash

        # 보유 주식 가치 계산
        holdings = db.query(Holding).filter(
            Holding.kakao_id == user.kakao_id,
            Holding.quantity > 0
        ).all()

        for h in holdings:
            stock_info = StockService.get_price(h.stock_code)
            if stock_info:
                total_asset += stock_info["price"] * h.quantity
            else:
                # 시세 조회 실패 시 평균 매수가 사용
                total_asset += h.avg_price * h.quantity

        # 수익률 계산 (0으로 나누기 방지)
        if user.initial_cash > 0:
            profit_rate = ((total_asset - user.initial_cash) / user.initial_cash) * 100
        else:
            profit_rate = 0.0

        return total_asset, profit_rate

    @classmethod
    def get_ranking(cls, db: Session, limit: int = 10) -> List[Dict]:
        """
        수익률 랭킹 TOP N (N+1 최적화)
        """
        # 캐시 확인
        cache_key = f"ranking_{limit}"
        if cache_key in cls._ranking_cache:
            return cls._ranking_cache[cache_key]

        # 전체 랭킹 계산
        rankings = cls._build_rankings(db)

        # TOP N 추출
        result = rankings[:limit]

        # 캐시 저장
        cls._ranking_cache[cache_key] = result

        return result

    @classmethod
    def get_my_rank(cls, db: Session, kakao_id: str) -> Optional[Dict]:
        """
        내 순위 조회 (N+1 최적화)
        """
        # 1. 전체 랭킹 캐시 확인 또는 계산
        full_ranking_key = "ranking_full"
        if full_ranking_key not in cls._ranking_cache:
            full_ranking = cls._build_rankings(db)
            cls._ranking_cache[full_ranking_key] = full_ranking
        else:
            full_ranking = cls._ranking_cache[full_ranking_key]

        # 2. 유저 조회
        user = db.query(User).filter(User.kakao_id == kakao_id).first()
        if not user:
            return None

        # 3. 전체 랭킹에서 내 순위 찾기
        for r in full_ranking:
            if r["kakao_id"] == kakao_id:
                return {
                    "rank": r["rank"],
                    "total": len(full_ranking),
                    "kakao_id": kakao_id,
                    "nickname": r["nickname"],
                    "total_asset": r["total_asset"],
                    "profit_rate": r["profit_rate"]
                }

        # 4. 캐시에 없으면 직접 계산 (새 유저 등)
        total_asset, profit_rate = cls.calculate_total_asset(db, user)

        # 나보다 높은 수익률 수 계산
        higher_count = sum(1 for r in full_ranking if r["profit_rate"] > profit_rate)

        return {
            "rank": higher_count + 1,
            "total": len(full_ranking) + 1,  # 새 유저 포함
            "kakao_id": kakao_id,
            "nickname": cls._get_display_name(user),
            "total_asset": total_asset,
            "profit_rate": profit_rate
        }

    @classmethod
    def clear_cache(cls):
        """랭킹 캐시 초기화"""
        cls._ranking_cache.clear()

    @classmethod
    def get_top_gainers(cls, db: Session, limit: int = 5) -> List[Dict]:
        """오늘 수익률 상위 유저 (빠른 조회)"""
        cache_key = f"top_gainers_{limit}"
        if cache_key in cls._ranking_cache:
            return cls._ranking_cache[cache_key]

        rankings = cls._build_rankings(db)
        # 양수 수익률만 필터링
        gainers = [r for r in rankings if r["profit_rate"] > 0][:limit]

        cls._ranking_cache[cache_key] = gainers
        return gainers

    @classmethod
    def get_top_losers(cls, db: Session, limit: int = 5) -> List[Dict]:
        """오늘 손실률 상위 유저 (빠른 조회)"""
        cache_key = f"top_losers_{limit}"
        if cache_key in cls._ranking_cache:
            return cls._ranking_cache[cache_key]

        rankings = cls._build_rankings(db)
        # 음수 수익률만 필터링 후 손실 큰 순서
        losers = sorted(
            [r for r in rankings if r["profit_rate"] < 0],
            key=lambda x: x["profit_rate"]
        )[:limit]

        cls._ranking_cache[cache_key] = losers
        return losers
