"""
추가 수집 크롤러
- naver_blog/news 보충: 공식 API sort=date
- tistory 보충: Kakao API sort=recency
- naver_cafe: 공식 Naver API
- naver_kin: 공식 Naver API (지식iN)
- daum_cafe: Kakao cafe API
- naver_post: 최선 시도 (동적 페이지, 대부분 0개)
- brunch 보충: Kakao API 추가 페이지
"""

import requests
import time
import re
from datetime import datetime
from config import (
    NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY,
    REQUEST_DELAY, FETCH_DELAY,
)

NAVER_HEADERS = {
    "X-Naver-Client-Id":     NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}
KAKAO_HEADERS = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
HTML_HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

TODAY = datetime.now().strftime("%Y-%m-%d")


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────────────────────
# 1. naver_blog 보충 (sort=date)
# ─────────────────────────────────────────────
def fetch_naver_blog_date(keyword, total=20):
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/blog.json",
            headers=NAVER_HEADERS,
            params={"query": keyword, "display": min(total, 100),
                    "start": 1, "sort": "date"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as e:
        print(f"  [naver_blog_date 오류] {keyword}: {e}")
        return []
    results = []
    for rank, item in enumerate(items[:total], 1):
        results.append({
            "플랫폼": "naver_blog", "키워드": keyword, "노출순위": rank,
            "제목": _clean(item.get("title", "")),
            "설명": _clean(item.get("description", "")),
            "링크": item.get("link", ""),
            "블로그명": item.get("bloggername", ""),
            "작성일": item.get("postdate", ""),
            "수집일": TODAY,
        })
    time.sleep(REQUEST_DELAY)
    return results


# ─────────────────────────────────────────────
# 2. naver_news 보충 (sort=date)
# ─────────────────────────────────────────────
def fetch_naver_news_date(keyword, total=20):
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers=NAVER_HEADERS,
            params={"query": keyword, "display": min(total, 100),
                    "start": 1, "sort": "date"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as e:
        print(f"  [naver_news_date 오류] {keyword}: {e}")
        return []
    results = []
    for rank, item in enumerate(items[:total], 1):
        results.append({
            "플랫폼": "naver_news", "키워드": keyword, "노출순위": rank,
            "제목": _clean(item.get("title", "")),
            "설명": _clean(item.get("description", "")),
            "링크": item.get("originallink", item.get("link", "")),
            "블로그명": item.get("publisher", ""),
            "작성일": item.get("pubDate", "")[:10].replace("-", ""),
            "수집일": TODAY,
        })
    time.sleep(REQUEST_DELAY)
    return results


# ─────────────────────────────────────────────
# 3. tistory 보충 (Kakao sort=recency)
# ─────────────────────────────────────────────
def fetch_tistory_recency(keyword, total=50):
    collected = []
    for page in range(1, 6):          # 최대 5페이지 × size=50
        if len(collected) >= total:
            break
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/search/blog",
                headers=KAKAO_HEADERS,
                params={"query": keyword, "size": 50,
                        "page": page, "sort": "recency"},
                timeout=10,
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            meta = resp.json().get("meta", {})
        except Exception as e:
            print(f"  [tistory_recency 오류] {keyword} p{page}: {e}")
            break
        filtered = [d for d in docs if "tistory.com" in d.get("url", "")]
        collected.extend(filtered)
        if meta.get("is_end"):
            break
        time.sleep(FETCH_DELAY)

    results = []
    for rank, item in enumerate(collected[:total], 1):
        results.append({
            "플랫폼": "tistory", "키워드": keyword, "노출순위": rank,
            "제목": _clean(item.get("title", "")),
            "설명": _clean(item.get("contents", "")),
            "링크": item.get("url", ""),
            "블로그명": item.get("blogname", ""),
            "작성일": (item.get("datetime", "") or "")[:10].replace("-", ""),
            "수집일": TODAY,
        })
    time.sleep(REQUEST_DELAY)
    return results


# ─────────────────────────────────────────────
# 4. naver_cafe (공식 API)
# ─────────────────────────────────────────────
def fetch_naver_cafe(keyword, total=100):
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/cafearticle.json",
            headers=NAVER_HEADERS,
            params={"query": keyword, "display": min(total, 100),
                    "start": 1, "sort": "sim"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as e:
        print(f"  [naver_cafe 오류] {keyword}: {e}")
        return []
    results = []
    for rank, item in enumerate(items[:total], 1):
        results.append({
            "플랫폼": "naver_cafe", "키워드": keyword, "노출순위": rank,
            "제목": _clean(item.get("title", "")),
            "설명": _clean(item.get("description", "")),
            "링크": item.get("link", ""),
            "블로그명": item.get("cafename", ""),
            "작성일": item.get("postdate", ""),
            "수집일": TODAY,
        })
    time.sleep(REQUEST_DELAY)
    return results


# ─────────────────────────────────────────────
# 5. naver_kin (공식 API, 지식iN)
# ─────────────────────────────────────────────
def fetch_naver_kin(keyword, total=100):
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/kin.json",
            headers=NAVER_HEADERS,
            params={"query": keyword, "display": min(total, 100),
                    "start": 1, "sort": "sim"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as e:
        print(f"  [naver_kin 오류] {keyword}: {e}")
        return []
    results = []
    for rank, item in enumerate(items[:total], 1):
        results.append({
            "플랫폼": "naver_kin", "키워드": keyword, "노출순위": rank,
            "제목": _clean(item.get("title", "")),
            "설명": _clean(item.get("description", "")),
            "링크": item.get("link", ""),
            "블로그명": "",
            "작성일": "",
            "수집일": TODAY,
            "분석대상": "답변",
        })
    time.sleep(REQUEST_DELAY)
    return results


# ─────────────────────────────────────────────
# 6. daum_cafe (Kakao cafe API)
# ─────────────────────────────────────────────
def fetch_daum_cafe(keyword, total=100):
    collected = []
    for page in range(1, 5):          # 최대 4페이지 × size=50
        if len(collected) >= total:
            break
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/search/cafe",
                headers=KAKAO_HEADERS,
                params={"query": keyword, "size": 50,
                        "page": page, "sort": "accuracy"},
                timeout=10,
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            meta = resp.json().get("meta", {})
        except Exception as e:
            print(f"  [daum_cafe 오류] {keyword} p{page}: {e}")
            break
        collected.extend(docs)
        if meta.get("is_end"):
            break
        time.sleep(FETCH_DELAY)

    results = []
    for rank, item in enumerate(collected[:total], 1):
        results.append({
            "플랫폼": "daum_cafe", "키워드": keyword, "노출순위": rank,
            "제목": _clean(item.get("title", "")),
            "설명": _clean(item.get("contents", "")),
            "링크": item.get("url", ""),
            "블로그명": item.get("cafename", ""),
            "작성일": (item.get("datetime", "") or "")[:10].replace("-", ""),
            "수집일": TODAY,
        })
    time.sleep(REQUEST_DELAY)
    return results


# ─────────────────────────────────────────────
# 7. naver_post (최선 시도, 실패 시 빈 리스트)
# ─────────────────────────────────────────────
def fetch_naver_post(keyword, total=100):
    """네이버 포스트는 JS 동적 로딩 → 수집 불가 시 빈 리스트 반환"""
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(
            "https://search.naver.com/search.naver",
            headers=HTML_HEADERS,
            params={"where": "post", "query": keyword, "start": 1},
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for rank, a in enumerate(
            soup.select("a[href*='post.naver.com']")[:total], 1
        ):
            parent = a.find_parent(["li", "div"], class_=True)
            desc_tag = parent.select_one("[class*=desc], [class*=dsc]") if parent else None
            results.append({
                "플랫폼": "naver_post", "키워드": keyword, "노출순위": rank,
                "제목": a.get_text(strip=True)[:100],
                "설명": desc_tag.get_text(strip=True) if desc_tag else "",
                "링크": a["href"],
                "블로그명": "",
                "작성일": "",
                "수집일": TODAY,
            })
        time.sleep(FETCH_DELAY)
        return results
    except Exception as e:
        print(f"  [naver_post 오류] {keyword}: {e}")
        return []


# ─────────────────────────────────────────────
# 8. brunch 보충 (Kakao sort=recency 추가 페이지)
# ─────────────────────────────────────────────
def fetch_brunch_more(keyword, total=50):
    collected = []
    for page in range(1, 11):         # 최대 10페이지
        if len(collected) >= total:
            break
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/search/blog",
                headers=KAKAO_HEADERS,
                params={"query": keyword, "size": 50,
                        "page": page, "sort": "recency"},
                timeout=10,
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            meta = resp.json().get("meta", {})
        except Exception as e:
            print(f"  [brunch_more 오류] {keyword} p{page}: {e}")
            break
        filtered = [d for d in docs if "brunch.co.kr" in d.get("url", "")]
        collected.extend(filtered)
        if meta.get("is_end"):
            break
        time.sleep(FETCH_DELAY)

    results = []
    for rank, item in enumerate(collected[:total], 1):
        results.append({
            "플랫폼": "brunch", "키워드": keyword, "노출순위": rank,
            "제목": _clean(item.get("title", "")),
            "설명": _clean(item.get("contents", "")),
            "링크": item.get("url", ""),
            "블로그명": item.get("blogname", ""),
            "작성일": (item.get("datetime", "") or "")[:10].replace("-", ""),
            "수집일": TODAY,
        })
    time.sleep(REQUEST_DELAY)
    return results
