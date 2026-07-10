"""
시계열 재수집: Naver Blog API sort=date + 연도별 버킷팅
- HTML 스크래핑 대신 공식 API 사용 → 제대로 된 description 텍스트 확보
- 현재 날짜가 2026년이므로 API 최근 결과는 2026년 포스트 → 최대 100페이지 페이지네이션으로 2020-2025 도달
- 2026년 포스트는 수집하지 않고 건너뜀 (목표 연도: 2020~2025)
- 기존 health_blog_timeseries.csv 덮어씀
"""

import csv
import os
import re
import time
from collections import Counter
from datetime import datetime

import requests

from config import KEYWORDS, DANGER_MAP, OUTPUT_DIR, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

NAVER_HEADERS = {
    "X-Naver-Client-Id":     NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}

YEARS         = [2020, 2021, 2022, 2023, 2024, 2025]
PER_YEAR      = 20      # 연도×키워드당 목표 수집량
PAGE_SIZE     = 100     # API 한 번에 최대 100개
MAX_PAGES     = 10      # Naver API 하드 한계: start 최대 1000 → 10페이지가 실질 상한
REQUEST_DELAY = 0.2     # API 호출 간격
KW_DELAY      = 0.3     # 키워드 간격
TODAY         = datetime.now().strftime("%Y-%m-%d")

OUTPUT_FILE = os.path.join(OUTPUT_DIR, "health_blog_timeseries.csv")
FIELDNAMES  = [
    "플랫폼", "카테고리", "위험도", "키워드", "연도",
    "노출순위", "제목", "설명", "링크", "블로그명", "작성일", "수집일",
]


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_all_years(keyword):
    """
    Naver Blog API sort=date로 페이지네이션하며 연도별 버킷팅.
    - 현재(2026년) 포스트는 건너뛰고 2020~2025 포스트만 수집
    - 모든 버킷이 목표치 달성하거나 API 결과 소진 시 종료
    반환: {year: [item, ...], ...}
    """
    buckets      = {y: [] for y in YEARS}
    min_year     = min(YEARS)
    max_year     = max(YEARS)

    for page in range(MAX_PAGES):
        # Naver API: start는 최대 1000 (start + display - 1 <= 1000)
        start = page * PAGE_SIZE + 1
        if start > 1000:
            break

        # 모든 버킷이 목표치 달성 시 조기 종료
        if all(len(buckets[y]) >= PER_YEAR for y in YEARS):
            break

        try:
            resp = requests.get(
                "https://openapi.naver.com/v1/search/blog.json",
                headers=NAVER_HEADERS,
                params={
                    "query":   keyword,
                    "display": PAGE_SIZE,
                    "start":   start,
                    "sort":    "date",
                },
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as e:
            print(f"    [API 오류] {keyword} p{page+1}: {e}")
            break

        if not items:
            break

        oldest_in_page = None
        for item in items:
            pd = item.get("postdate", "")  # YYYYMMDD
            if not pd or len(pd) < 4:
                continue
            try:
                yr = int(pd[:4])
            except ValueError:
                continue

            oldest_in_page = yr
            # 목표 연도 범위 내 포스트만 버킷에 추가
            if min_year <= yr <= max_year and len(buckets[yr]) < PER_YEAR:
                buckets[yr].append(item)

        time.sleep(REQUEST_DELAY)

        # 페이지의 마지막 날짜가 목표 최소 연도보다 이전이면 종료
        if oldest_in_page is not None and oldest_in_page < min_year:
            break

    return buckets


def run_recrawl():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_kw = sum(len(v) for v in KEYWORDS.values())
    done     = 0
    all_rows = []

    print(f"{'='*60}")
    print(f"시계열 API 재수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"키워드: {total_kw}개 | 연도: {YEARS} | 연도×키워드 목표: {PER_YEAR}개")
    print(f"{'='*60}\n")

    for category, keyword_list in KEYWORDS.items():
        danger = DANGER_MAP[category]

        for keyword in keyword_list:
            done += 1
            buckets = fetch_all_years(keyword)

            kw_total = 0
            for year in YEARS:
                items = buckets[year]
                for rank, item in enumerate(items, 1):
                    all_rows.append({
                        "플랫폼":   "naver_blog_timeseries",
                        "카테고리": category,
                        "위험도":   danger,
                        "키워드":   keyword,
                        "연도":     year,
                        "노출순위": rank,
                        "제목":     _clean(item.get("title", "")),
                        "설명":     _clean(item.get("description", "")),
                        "링크":     item.get("link", ""),
                        "블로그명": item.get("bloggername", ""),
                        "작성일":   item.get("postdate", ""),
                        "수집일":   TODAY,
                    })
                kw_total += len(items)

            year_summary = " / ".join(
                f"{y}:{len(buckets[y])}" for y in YEARS
            )
            print(f"[{done}/{total_kw}] '{keyword}' → {kw_total}개  ({year_summary})")
            print(f"  누적: {len(all_rows):,}개")

            time.sleep(KW_DELAY)

    # CSV 저장
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    # 완료 요약
    year_counts = Counter(r["연도"] for r in all_rows)
    cat_counts  = Counter(r["카테고리"] for r in all_rows)

    # 설명 컬럼 길이 통계
    desc_lens   = [len(r["설명"]) for r in all_rows if r["설명"]]
    avg_desc    = sum(desc_lens) // len(desc_lens) if desc_lens else 0
    usable      = sum(1 for l in desc_lens if l >= 50)

    print(f"\n{'='*60}")
    print("=== API 재수집 완료 ===")
    print(f"총 수집: {len(all_rows):,}개")
    print(f"설명 평균 길이: {avg_desc}자 / 50자 이상: {usable:,}개")
    print()
    print("연도별 수집량:")
    for yr in YEARS:
        label = "(ChatGPT 이전)" if yr <= 2022 else "(ChatGPT 이후)"
        print(f"  {yr}년: {year_counts.get(yr, 0):,}개  {label}")
    print()
    print("카테고리별 수집량:")
    for cat in ["상_일반질환","상_정신건강","상_보완대체의학","중_생활건강","하_경증"]:
        print(f"  {cat:<18}: {cat_counts.get(cat, 0):,}개")
    print(f"\n저장: {OUTPUT_FILE}")
    print(f"{'='*60}")

    return all_rows


if __name__ == "__main__":
    run_recrawl()
