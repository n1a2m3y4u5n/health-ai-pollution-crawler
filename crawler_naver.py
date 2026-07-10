"""
네이버 블로그 & 뉴스 크롤러 (공식 API)
"""

import requests
import time
import re
from config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, REQUEST_DELAY, FETCH_DELAY

HEADERS = {
    "X-Naver-Client-Id":     NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}

def _clean_html(text):
    """HTML 태그 및 특수문자 제거"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _fetch_naver(endpoint, keyword, display, start, sort):
    """네이버 검색 API 공통 호출"""
    try:
        resp = requests.get(
            endpoint,
            headers=HEADERS,
            params={"query": keyword, "display": display,
                    "start": start, "sort": sort},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as e:
        print(f"  [네이버 API 오류] {keyword}: {e}")
        return []

def fetch_naver_blog(keyword, total=100):
    """
    네이버 블로그 검색 (정확도순)
    한 번에 최대 100개 → 100개 이하면 1회 호출로 완료
    """
    results = []
    batch = min(total, 100)
    items = _fetch_naver(
        "https://openapi.naver.com/v1/search/blog.json",
        keyword, batch, 1, "sim"
    )
    for rank, item in enumerate(items[:total], start=1):
        results.append({
            "플랫폼":   "naver_blog",
            "키워드":   keyword,
            "노출순위": rank,
            "제목":     _clean_html(item.get("title", "")),
            "설명":     _clean_html(item.get("description", "")),
            "링크":     item.get("link", ""),
            "블로그명": item.get("bloggername", ""),
            "작성일":   item.get("postdate", ""),
        })
    time.sleep(REQUEST_DELAY)
    return results

def fetch_naver_news(keyword, total=100):
    """
    네이버 뉴스 검색 (정확도순)
    언론사 건강 기사 AI 작성 비율 비교용
    """
    results = []
    batch = min(total, 100)
    items = _fetch_naver(
        "https://openapi.naver.com/v1/search/news.json",
        keyword, batch, 1, "sim"
    )
    for rank, item in enumerate(items[:total], start=1):
        results.append({
            "플랫폼":   "naver_news",
            "키워드":   keyword,
            "노출순위": rank,
            "제목":     _clean_html(item.get("title", "")),
            "설명":     _clean_html(item.get("description", "")),
            "링크":     item.get("originallink", item.get("link", "")),
            "블로그명": item.get("publisher", ""),   # 언론사명
            "작성일":   item.get("pubDate", "")[:10].replace("-", ""),
        })
    time.sleep(REQUEST_DELAY)
    return results
