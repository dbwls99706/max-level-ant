"""
주식 뉴스 서비스
- 네이버 뉴스 RSS 활용
- 종목별/시장 뉴스 조회
"""
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict
from html import unescape
import re


class NewsService:
    """주식 뉴스 서비스"""

    NAVER_NEWS_RSS = "https://news.google.com/rss/search"

    @classmethod
    def _clean_title(cls, title: str) -> str:
        """HTML 엔티티 및 태그 정리"""
        title = unescape(title)
        title = re.sub(r'<[^>]+>', '', title)
        return title.strip()

    @classmethod
    def get_stock_news(cls, query: str, limit: int = 5) -> List[Dict]:
        """종목 관련 뉴스 검색"""
        try:
            params = {
                "q": f"{query} 주식",
                "hl": "ko",
                "gl": "KR",
                "ceid": "KR:ko"
            }

            resp = requests.get(cls.NAVER_NEWS_RSS, params=params, timeout=10)

            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items = root.findall(".//item")

                news_list = []
                for item in items[:limit]:
                    title = item.find("title")
                    link = item.find("link")
                    pub_date = item.find("pubDate")

                    if title is not None and link is not None:
                        news_list.append({
                            "title": cls._clean_title(title.text or ""),
                            "link": link.text or "",
                            "date": pub_date.text[:16] if pub_date is not None and pub_date.text else ""
                        })

                return news_list

        except Exception as e:
            print(f"❌ 뉴스 조회 실패: {e}")

        return []

    @classmethod
    def get_market_news(cls, limit: int = 5) -> List[Dict]:
        """시장 전체 뉴스"""
        return cls.get_stock_news("코스피 증시", limit)
