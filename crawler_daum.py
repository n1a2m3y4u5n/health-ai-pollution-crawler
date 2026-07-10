"""
티스토리 & 브런치 크롤러 (Kakao 블로그 검색 API)
- Kakao REST API 키 필요: https://developers.kakao.com
- config.py에 KAKAO_REST_API_KEY 추가 후 사용
- 티스토리: kakao 블로그 검색 결과에서 tistory.com 도메인 필터링
- 브런치:   kakao 블로그 검색 결과에서 brunch.co.kr 도메인 필터링
"""

import requests
import time
import re
from config import FETCH_DELAY, KAKAO_REST_API_KEY

def _clean(text):
    """Kakao API 응답의 HTML 태그 제거"""
    return re.sub(r"<[^>]+>", "", text or "").strip()

KAKAO_BLOG_URL = "https://dapi.kakao.com/v2/search/blog"

def _kakao_blog_search(keyword, page=1, size=50):
    """
    Kakao 블로그 검색 API 호출
    반환: [{"title", "link", "description", "datetime", "blogname"}, ...]
    """
    if not KAKAO_REST_API_KEY or KAKAO_REST_API_KEY == "여기에_Kakao_REST_API_KEY_입력":
        print("  [Kakao API 키 없음] config.py에 KAKAO_REST_API_KEY를 입력하세요")
        return []

    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params  = {"query": keyword, "page": page, "size": size, "sort": "accuracy"}
    try:
        resp = requests.get(KAKAO_BLOG_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("documents", [])
    except Exception as e:
        print(f"  [Kakao API 오류] {keyword} p{page}: {e}")
        return []

def _filter_by_domain(items, domain):
    return [i for i in items if domain in i.get("url", "")]

def _fetch_pages(keyword, domain, total=100):
    """여러 페이지를 순회하며 특정 도메인 결과 수집 (Kakao API 최대 page=50)"""
    collected = []
    page = 1
    while len(collected) < total and page <= 10:
        items = _kakao_blog_search(keyword, page=page, size=50)
        if not items:
            break
        filtered = _filter_by_domain(items, domain)
        collected.extend(filtered)
        # meta.is_end 확인
        page += 1
        time.sleep(FETCH_DELAY)

    return collected[:total]

def _parse_date(dt_str):
    """Kakao 날짜 포맷 변환: 2024-04-01T12:00:00.000+09:00 → 20240401"""
    if not dt_str:
        return ""
    return dt_str[:10].replace("-", "")

def fetch_tistory(keyword, total=100):
    """티스토리 블로그 글 수집"""
    items = _fetch_pages(keyword, "tistory.com", total)
    results = []
    for rank, item in enumerate(items, start=1):
        results.append({
            "플랫폼":   "tistory",
            "키워드":   keyword,
            "노출순위": rank,
            "제목":     _clean(item.get("title", "")),
            "설명":     _clean(item.get("contents", "")),
            "링크":     item.get("url", ""),
            "블로그명": item.get("blogname", ""),
            "작성일":   _parse_date(item.get("datetime", "")),
        })
    return results

def fetch_brunch(keyword, total=100):
    """브런치 글 수집 (에디터 큐레이션 플랫폼 — 대조군)"""
    items = _fetch_pages(keyword, "brunch.co.kr", total)
    results = []
    for rank, item in enumerate(items, start=1):
        results.append({
            "플랫폼":   "brunch",
            "키워드":   keyword,
            "노출순위": rank,
            "제목":     _clean(item.get("title", "")),
            "설명":     _clean(item.get("contents", "")),
            "링크":     item.get("url", ""),
            "블로그명": item.get("blogname", ""),
            "작성일":   _parse_date(item.get("datetime", "")),
        })
    return results
