"""
추가 수집 오케스트레이터
작업1: naver_blog/news 보충 (sort=date) + tistory 보충 (recency)
작업2: naver_cafe, naver_kin, daum_cafe, naver_post, brunch 보충
"""

import csv
import os
from collections import Counter
from datetime import datetime

from config import KEYWORDS, DANGER_MAP, OUTPUT_DIR

from crawler_supplement import (
    fetch_naver_blog_date,
    fetch_naver_news_date,
    fetch_tistory_recency,
    fetch_naver_cafe,
    fetch_naver_kin,
    fetch_daum_cafe,
    fetch_naver_post,
    fetch_brunch_more,
)

RAW_CSV = os.path.join(OUTPUT_DIR, "health_blog_raw.csv")
FIELDNAMES = [
    "플랫폼", "카테고리", "위험도", "키워드",
    "노출순위", "제목", "설명", "링크", "블로그명", "작성일", "수집일",
    "분석대상",
]


def load_existing_links():
    """기존 CSV에서 링크 집합 로드 (중복 제거용)"""
    links = set()
    if not os.path.exists(RAW_CSV):
        return links
    with open(RAW_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("링크"):
                links.add(row["링크"])
    return links


def append_to_csv(rows):
    """기존 CSV에 행 추가"""
    if not rows:
        return
    write_header = not os.path.exists(RAW_CSV)
    with open(RAW_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def run_supplement():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    existing_links = load_existing_links()
    print(f"기존 링크 수: {len(existing_links):,}개")

    total_added = Counter()

    # ═══════════════════════════════════════════
    # 작업 1: 기존 플랫폼 보충
    # ═══════════════════════════════════════════
    print(f"\n{'='*60}")
    print("작업 1 - 기존 플랫폼 보충 수집")
    print(f"{'='*60}")

    job1_tasks = []
    for category, keyword_list in KEYWORDS.items():
        danger = DANGER_MAP[category]
        for keyword in keyword_list:
            for fn, platform in [
                (fetch_naver_blog_date, "naver_blog"),
                (fetch_naver_news_date, "naver_news"),
                (fetch_tistory_recency, "tistory"),
            ]:
                job1_tasks.append((fn, platform, keyword, category, danger))

    for idx, (fn, platform, keyword, category, danger) in enumerate(job1_tasks, 1):
        print(f"[{idx}/{len(job1_tasks)}] '{keyword}' | {platform}")
        try:
            items = fn(keyword)
        except Exception as e:
            print(f"  [오류] {e}")
            items = []

        new_items = []
        for item in items:
            link = item.get("링크", "")
            if link and link not in existing_links:
                item["카테고리"] = category
                item["위험도"]   = danger
                item.setdefault("분석대상", "")
                new_items.append(item)
                existing_links.add(link)

        append_to_csv(new_items)
        total_added[platform] += len(new_items)
        print(f"  → 신규 {len(new_items)}개 / 누적 추가 {sum(total_added.values()):,}개")

    # ═══════════════════════════════════════════
    # 작업 2: 신규 플랫폼 추가
    # ═══════════════════════════════════════════
    print(f"\n{'='*60}")
    print("작업 2 - 신규 플랫폼 수집")
    print(f"{'='*60}")

    job2_tasks = []
    for category, keyword_list in KEYWORDS.items():
        danger = DANGER_MAP[category]
        for keyword in keyword_list:
            for fn, platform in [
                (fetch_naver_cafe, "naver_cafe"),
                (fetch_naver_kin,  "naver_kin"),
                (fetch_daum_cafe,  "daum_cafe"),
                (fetch_naver_post, "naver_post"),
                (fetch_brunch_more,"brunch"),
            ]:
                job2_tasks.append((fn, platform, keyword, category, danger))

    for idx, (fn, platform, keyword, category, danger) in enumerate(job2_tasks, 1):
        print(f"[{idx}/{len(job2_tasks)}] '{keyword}' | {platform}")
        try:
            items = fn(keyword)
        except Exception as e:
            print(f"  [오류] {e}")
            items = []

        new_items = []
        for item in items:
            link = item.get("링크", "")
            if link and link not in existing_links:
                item["카테고리"] = category
                item["위험도"]   = danger
                item.setdefault("분석대상", "")
                new_items.append(item)
                existing_links.add(link)

        append_to_csv(new_items)
        total_added[platform] += len(new_items)
        print(f"  → 신규 {len(new_items)}개 / 누적 추가 {sum(total_added.values()):,}개")

    # ═══════════════════════════════════════════
    # 최종 요약
    # ═══════════════════════════════════════════
    print(f"\n{'='*60}")
    print("=== 추가 수집 완료 ===")

    # 전체 CSV 플랫폼별 집계
    final_counts = Counter()
    with open(RAW_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            final_counts[row["플랫폼"]] += 1

    platform_order = [
        "naver_blog", "naver_news", "naver_cafe", "naver_kin",
        "tistory", "naver_post", "daum_cafe", "brunch",
    ]
    print("플랫폼별 최종 수집량:")
    total = 0
    for p in platform_order:
        c = final_counts.get(p, 0)
        total += c
        print(f"  {p:<15}: {c:,}개")
    for p, c in final_counts.items():
        if p not in platform_order:
            total += c
            print(f"  {p:<15}: {c:,}개")
    print(f"  {'─'*22}")
    print(f"  {'합계':<15}: {total:,}개")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_supplement()
