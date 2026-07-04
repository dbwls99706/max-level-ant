"""
주식 뉴스 서비스 (리팩토링)
- Google News RSS 활용
- 종목별/시장 뉴스 조회
- print → logger 변경
"""

import requests
import xml.etree.ElementTree as ET
from typing import List, Dict
from html import unescape
import re

from utils import get_service_logger

logger = get_service_logger()


class NewsService:
    """주식 뉴스 서비스"""

    GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
    REQUEST_TIMEOUT = 10

    @classmethod
    def _clean_title(cls, title: str) -> str:
        """HTML 엔티티 및 태그 정리"""
        if not title:
            return ""
        title = unescape(title)
        title = re.sub(r"<[^>]+>", "", title)
        return title.strip()

    @classmethod
    def get_stock_news(cls, query: str, limit: int = 5) -> List[Dict]:
        """종목 관련 뉴스 검색"""
        try:
            params = {"q": f"{query} 주식", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}

            resp = requests.get(
                cls.GOOGLE_NEWS_RSS, params=params, timeout=cls.REQUEST_TIMEOUT
            )

            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items = root.findall(".//item")

                news_list = []
                for item in items[:limit]:
                    title = item.find("title")
                    link = item.find("link")
                    pub_date = item.find("pubDate")

                    if title is not None and link is not None:
                        news_list.append(
                            {
                                "title": cls._clean_title(title.text or ""),
                                "link": link.text or "",
                                "date": pub_date.text[:16]
                                if pub_date is not None and pub_date.text
                                else "",
                            }
                        )

                return news_list
            else:
                logger.warning(f"뉴스 API 응답 오류: status_code={resp.status_code}")

        except requests.Timeout:
            logger.warning(f"뉴스 조회 타임아웃: query={query}")
        except requests.RequestException as e:
            logger.error(f"뉴스 조회 요청 실패: {e}")
        except ET.ParseError as e:
            logger.error(f"뉴스 XML 파싱 실패: {e}")
        except Exception as e:
            logger.error(f"뉴스 조회 중 예상치 못한 오류: {e}")

        return []

    @classmethod
    def get_market_news(cls, limit: int = 5) -> List[Dict]:
        """시장 전체 뉴스"""
        return cls.get_stock_news("코스피 증시", limit)

    @classmethod
    def get_trending_stocks_news(cls, limit: int = 5) -> List[Dict]:
        """인기 종목 뉴스"""
        return cls.get_stock_news("급등주 테마주", limit)

    @classmethod
    def search_news(cls, keyword: str, limit: int = 5) -> List[Dict]:
        """키워드로 뉴스 검색"""
        if not keyword or not keyword.strip():
            return []
        return cls.get_stock_news(keyword.strip(), limit)
