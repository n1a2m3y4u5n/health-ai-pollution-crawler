"""
시계열 블로그 수집 크롤러
- 네이버 검색 NSO 파라미터로 연도별 블로그 수집
- HTML의 data-image-viewer-list JSON에서 link/title/dateInfo 추출
- 페이지당 최대 20개 (네이버 이미지 섹션 한계)
- 2020~2025 × 60키워드 = 목표 10,800개
- 403 시 지수 백오프 재시도, 기존 수집 조합 자동 건너뜀
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

YEARS      = [2020, 2021, 2022, 2023, 2024, 2025]
PAGE_DELAY = 2.0   # 페이지 요청 간격 (403 방지)
KW_DELAY   = 1.0   # 키워드 간격
TODAY      = datetime.now().strftime("%Y-%m-%d")

FIELDNAMES = [
    "플랫폼", "카테고리", "위험도", "키워드", "연도",
    "노출순위", "제목", "설명", "링크", "블로그명", "작성일", "수집일",
]


def _parse_date(date_str):
    """'2023.12.21.' → '20231221'"""
    cleaned = re.sub(r"[.\s]", "", date_str or "")
    return cleaned if re.match(r"20\d{6}$", cleaned) else ""


def fetch_naver_blog_by_year(keyword, year, count=30, retries=3):
    """
    NSO 파라미터로 특정 연도 네이버 블로그 수집.
    data-image-viewer-list JSON에서 link/title/dateInfo 추출.
    403 시 지수 백오프로 최대 retries회 재시도.
    """
    nso = f"so:r,p:from{year}0101to{year}1231"

    for attempt in range(retries):
        try:
            resp = requests.get(
                "https://search.naver.com/search.naver",
                headers=HEADERS,
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
                print(f"    [요청 오류] {keyword} {year}: {e}")
                return []
    else:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    raw_items = []
    for tag in soup.find_all(attrs={"data-image-viewer-list": True}):
        try:
            raw_items.extend(json.loads(unescape(tag["data-image-viewer-list"])))
        except Exception:
            pass

    time.sleep(PAGE_DELAY)

    results = []
    seen_links = set()
    for rank, item in enumerate(raw_items[:count], 1):
        link = item.get("link", "")
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        results.append({
            "플랫폼":   "naver_blog_timeseries",
            "키워드":   keyword,
            "연도":     year,
            "노출순위": rank,
            "제목":     re.sub(r"<[^>]+>", "", item.get("title", "")).strip(),
            "설명":     item.get("writerTitle", ""),
            "링크":     link,
            "블로그명": item.get("writerTitle", ""),
            "작성일":   _parse_date(item.get("dateInfo", "")),
            "수집일":   TODAY,
        })

    return results


def load_done_pairs(filepath):
    """기존 CSV에서 (키워드, 연도) 집합 로드 — 이미 수집된 조합 건너뛰기용"""
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


def run_timeseries(output_file="health_blog_timeseries.csv"):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, output_file)

    done_pairs  = load_done_pairs(filepath)
    total_kw    = sum(len(v) for v in KEYWORDS.values())
    total_tasks = total_kw * len(YEARS)
    done        = 0
    new_results = []

    print(f"{'='*60}")
    print(f"시계열 수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"키워드: {total_kw}개 | 연도: {YEARS}")
    print(f"이미 수집된 조합: {len(done_pairs)}개 → 건너뜀")
    print(f"{'='*60}\n")

    write_header = not os.path.exists(filepath)
    csv_file = open(filepath, "a", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
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

                    items = fetch_naver_blog_by_year(keyword, year, count=30)

                    for item in items:
                        item["카테고리"] = category
                        item["위험도"]   = danger

                    writer.writerows(items)
                    csv_file.flush()
                    new_results.extend(items)

                    if items:
                        print(
                            f"[{done}/{total_tasks}] {year}년 '{keyword}' "
                            f"→ {len(items)}개 / 신규 누적 {len(new_results):,}개"
                        )
                    else:
                        print(
                            f"[{done}/{total_tasks}] {year}년 '{keyword}' → 0개 (skip)"
                        )

                time.sleep(KW_DELAY)
    finally:
        csv_file.close()

    # ─── 완료 요약 ───
    all_year_counts = Counter()
    all_cat_counts  = Counter()
    with open(filepath, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            yr = row.get("연도", "")
            ct = row.get("카테고리", "")
            if yr:
                all_year_counts[int(yr)] += 1
            if ct:
                all_cat_counts[ct] += 1
    total_all = sum(all_year_counts.values())

    print(f"\n{'='*60}")
    print("=== 시계열 수집 완료 ===")
    print(f"신규 수집: {len(new_results):,}개 | 전체 누적: {total_all:,}개")
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
    print(f"\n저장: {filepath}")
    print(f"{'='*60}")

    return new_results


if __name__ == "__main__":
    run_timeseries()
