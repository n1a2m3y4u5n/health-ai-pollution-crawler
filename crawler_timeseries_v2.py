"""
시계열 블로그 수집 크롤러 v2
전략:
  1. NSO 연도 필터 + data-image-viewer-list → 연도 정확한 링크 수집
  2. 각 blog.naver.com 링크 → 모바일 페이지(.se-main-container) → 실제 본문 텍스트
  3. 기존 수집 (키워드, 연도) 조합 자동 건너뜀
"""

import csv
import json
import os
import random
import re
import time
from collections import Counter
from datetime import datetime
from html import unescape

import requests
from bs4 import BeautifulSoup

from config import KEYWORDS, DANGER_MAP, OUTPUT_DIR

SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.naver.com/",
}

MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

YEARS        = [2020, 2021, 2022, 2023, 2024, 2025]
PER_YEAR     = 10     # 연도×키워드당 목표 수집량 (속도 우선)
SEARCH_DELAY = 1.2    # NSO 검색 페이지 요청 간격
FETCH_DELAY  = 0.7    # 모바일 블로그 페이지 요청 간격
KW_DELAY     = 0.3    # 키워드 간격
TODAY        = datetime.now().strftime("%Y-%m-%d")

OUTPUT_FILE = os.path.join(OUTPUT_DIR, "health_blog_timeseries.csv")
FIELDNAMES  = [
    "플랫폼", "카테고리", "위험도", "키워드", "연도",
    "노출순위", "제목", "설명", "링크", "블로그명", "작성일", "수집일",
]


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"&[a-zA-Z0-9#]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(date_str):
    """'2022.06.20.' → '20220620'"""
    cleaned = re.sub(r"[.\s]", "", date_str or "")
    if re.match(r"20\d{6}$", cleaned):
        return cleaned
    return ""


def get_nso_links(keyword, year, retries=3):
    """
    NSO 연도 필터로 data-image-viewer-list에서 링크 수집.
    최대 20개 반환 (NSO 이미지 섹션 한계).
    """
    nso = f"so:r,p:from{year}0101to{year}1231"

    for attempt in range(retries):
        try:
            resp = requests.get(
                "https://search.naver.com/search.naver",
                headers=SEARCH_HEADERS,
                params={"where": "blog", "query": keyword, "nso": nso},
                timeout=15,
            )
            resp.raise_for_status()
            break
        except Exception as e:
            if "403" in str(e) and attempt < retries - 1:
                wait = 10 * (attempt + 1) + random.uniform(0, 5)
                print(f"    [403 재시도 {attempt+1}/{retries}] {wait:.1f}초 대기...")
                time.sleep(wait)
            else:
                print(f"    [검색 오류] {keyword} {year}: {e}")
                return []
    else:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    seen  = set()

    for tag in soup.find_all(attrs={"data-image-viewer-list": True}):
        try:
            items = json.loads(unescape(tag["data-image-viewer-list"]))
        except Exception:
            continue
        for item in items:
            lnk = item.get("link", "")
            if not lnk or lnk in seen:
                continue
            # Naver 블로그만
            if "blog.naver.com" not in lnk:
                continue
            seen.add(lnk)
            links.append({
                "link":      lnk,
                "title":     _clean(item.get("title", "")),
                "blogname":  item.get("writerTitle", ""),
                "postdate":  _parse_date(item.get("dateInfo", "")),
            })

    time.sleep(SEARCH_DELAY)
    return links


def fetch_blog_description(link, retries=2):
    """
    blog.naver.com/{blogId}/{logNo} → 모바일 페이지 → 설명 텍스트.
    """
    m = re.search(r"blog\.naver\.com/([^/?#]+)/(\d+)", link)
    if not m:
        return ""
    blog_id = m.group(1)
    log_no  = m.group(2)
    mobile_url = f"https://m.blog.naver.com/{blog_id}/{log_no}"

    for attempt in range(retries):
        try:
            resp = requests.get(
                mobile_url,
                headers=MOBILE_HEADERS,
                timeout=12,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                return ""
            break
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                return ""
    else:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    # 본문 컨테이너 (스마트에디터 신/구)
    for sel in [".se-main-container", ".post-view", "#postViewArea",
                ".se_component_wrap", ".blog_content"]:
        el = soup.select_one(sel)
        if el:
            text = re.sub(r"\s+", " ", el.get_text()).strip()
            if len(text) >= 30:
                return text[:500]   # 최대 500자만 저장 (KatFishNet용)
    return ""


def load_done_pairs(filepath):
    done = set()
    if not os.path.exists(filepath):
        return done
    with open(filepath, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            kw = row.get("키워드", "")
            yr = row.get("연도", "")
            if kw and yr:
                done.add((kw, int(yr)))
    return done


def run_timeseries_v2():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    done_pairs  = load_done_pairs(OUTPUT_FILE)
    total_kw    = sum(len(v) for v in KEYWORDS.values())
    total_tasks = total_kw * len(YEARS)
    done        = 0
    new_results = []

    print(f"{'='*60}")
    print(f"시계열 수집 v2 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"전략: NSO 이미지섹션 링크 → 모바일 블로그 본문 수집")
    print(f"키워드: {total_kw}개 | 연도: {YEARS} | 목표: {PER_YEAR}개/연도×키워드")
    print(f"이미 수집된 조합: {len(done_pairs)}개 → 건너뜀")
    print(f"{'='*60}\n")

    write_header = not os.path.exists(OUTPUT_FILE)
    csv_file = open(OUTPUT_FILE, "a", newline="", encoding="utf-8-sig")
    writer   = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
    if write_header:
        writer.writeheader()

    try:
        for category, keyword_list in KEYWORDS.items():
            danger = DANGER_MAP[category]

            for keyword in keyword_list:
                for year in YEARS:
                    done += 1
                    if (keyword, year) in done_pairs:
                        print(f"[{done}/{total_tasks}] {year}년 '{keyword}' → 이미 수집됨 (skip)")
                        continue

                    # 1단계: NSO 필터로 링크 수집
                    links = get_nso_links(keyword, year)

                    # 2단계: 각 링크에서 모바일 본문 수집
                    rows = []
                    for rank, lnk_info in enumerate(links[:PER_YEAR], 1):
                        desc = fetch_blog_description(lnk_info["link"])
                        time.sleep(FETCH_DELAY)
                        rows.append({
                            "플랫폼":   "naver_blog_timeseries",
                            "카테고리": category,
                            "위험도":   danger,
                            "키워드":   keyword,
                            "연도":     year,
                            "노출순위": rank,
                            "제목":     lnk_info["title"],
                            "설명":     desc,
                            "링크":     lnk_info["link"],
                            "블로그명": lnk_info["blogname"],
                            "작성일":   lnk_info["postdate"],
                            "수집일":   TODAY,
                        })

                    writer.writerows(rows)
                    csv_file.flush()
                    new_results.extend(rows)

                    desc_ok = sum(1 for r in rows if len(r["설명"]) >= 50)
                    if rows:
                        print(
                            f"[{done}/{total_tasks}] {year}년 '{keyword}' "
                            f"→ {len(rows)}개 (설명50자↑: {desc_ok}개) / 신규누적 {len(new_results):,}개"
                        )
                    else:
                        print(f"[{done}/{total_tasks}] {year}년 '{keyword}' → 0개")

                time.sleep(KW_DELAY)
    finally:
        csv_file.close()

    # 완료 요약
    all_year_counts = Counter()
    all_cat_counts  = Counter()
    desc_lens       = []
    with open(OUTPUT_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            yr = row.get("연도", "")
            ct = row.get("카테고리", "")
            if yr:
                all_year_counts[int(yr)] += 1
            if ct:
                all_cat_counts[ct] += 1
            d = row.get("설명", "")
            if d:
                desc_lens.append(len(d))

    total_all = sum(all_year_counts.values())
    avg_desc  = sum(desc_lens) // len(desc_lens) if desc_lens else 0
    usable    = sum(1 for l in desc_lens if l >= 50)

    print(f"\n{'='*60}")
    print("=== 시계열 수집 v2 완료 ===")
    print(f"신규 수집: {len(new_results):,}개 | 전체 누적: {total_all:,}개")
    print(f"설명 평균 길이: {avg_desc}자 / 50자 이상: {usable:,}개")
    print()
    print("연도별 수집량 (전체):")
    for yr in YEARS:
        label = "(ChatGPT 이전)" if yr <= 2022 else "(ChatGPT 이후)"
        print(f"  {yr}년: {all_year_counts.get(yr, 0):,}개  {label}")
    print()
    print("카테고리별 수집량 (전체):")
    cat_order = ["상_일반질환", "상_정신건강", "상_보완대체의학", "중_생활건강", "하_경증"]
    for cat in cat_order:
        print(f"  {cat:<18}: {all_cat_counts.get(cat, 0):,}개")
    print(f"\n저장: {OUTPUT_FILE}")
    print(f"{'='*60}")

    return new_results


if __name__ == "__main__":
    run_timeseries_v2()
