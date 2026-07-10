"""
건강정보 AI 오염 실태 연구 - 메인 크롤링 실행
60 키워드 × 100개 × 4 플랫폼 = 최대 24,000개 수집
"""

import csv
import os
import time
from datetime import datetime

from config import KEYWORDS, DANGER_MAP, OUTPUT_DIR, POSTS_PER_KEYWORD
from crawler_naver import fetch_naver_blog, fetch_naver_news
from crawler_daum import fetch_tistory, fetch_brunch

# =============================================
# 플랫폼별 크롤러 매핑
# =============================================
CRAWLERS = {
    "naver_blog": fetch_naver_blog,
    "naver_news": fetch_naver_news,
    "tistory":    fetch_tistory,
    "brunch":     fetch_brunch,
}

def run_all(platforms=None, output_file="health_blog_raw.csv"):
    """
    전체 크롤링 실행
    platforms: 수집할 플랫폼 리스트 (None이면 전체)
    """
    if platforms is None:
        platforms = list(CRAWLERS.keys())

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, output_file)

    # 총 작업량 계산
    total_kw = sum(len(v) for v in KEYWORDS.values())
    total_tasks = total_kw * len(platforms)
    done = 0
    all_results = []

    print(f"{'='*60}")
    print(f"수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"키워드: {total_kw}개 | 플랫폼: {len(platforms)}개")
    print(f"목표 수집량: 최대 {total_tasks * POSTS_PER_KEYWORD:,}개")
    print(f"{'='*60}\n")

    for category, keyword_list in KEYWORDS.items():
        danger = DANGER_MAP[category]

        for keyword in keyword_list:
            for platform in platforms:
                done += 1
                print(
                    f"[{done}/{total_tasks}] "
                    f"'{keyword}' | {platform} | 위험도:{danger} | 카테고리:{category}"
                )

                # 크롤링 실행
                try:
                    items = CRAWLERS[platform](keyword, POSTS_PER_KEYWORD)
                except Exception as e:
                    print(f"  [오류] {e}")
                    items = []

                # 공통 필드 추가
                for item in items:
                    item["카테고리"] = category
                    item["위험도"]   = danger
                    item["수집일"]   = datetime.now().strftime("%Y-%m-%d")

                all_results.extend(items)
                print(f"  → {len(items)}개 수집 / 누적 {len(all_results):,}개")

    # CSV 저장
    _save_csv(all_results, filepath)
    return all_results


def _save_csv(results, filepath):
    if not results:
        print("수집된 데이터가 없습니다.")
        return

    fieldnames = [
        "플랫폼", "카테고리", "위험도", "키워드",
        "노출순위", "제목", "설명", "링크", "블로그명", "작성일", "수집일",
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\n{'='*60}")
    print(f"저장 완료: {filepath}")
    print(f"총 {len(results):,}개")

    # 플랫폼별 요약
    from collections import Counter
    platform_counts = Counter(r["플랫폼"] for r in results)
    print("\n플랫폼별 수집량:")
    for platform, count in sorted(platform_counts.items()):
        print(f"  {platform}: {count:,}개")
    print(f"{'='*60}")


# =============================================
# 실행 옵션
# =============================================
if __name__ == "__main__":
    # 전체 실행
    run_all(
        platforms=["naver_blog", "naver_news", "tistory", "brunch"],
        output_file="health_blog_raw.csv",
    )

    # 특정 플랫폼만 테스트할 때
    # run_all(platforms=["naver_blog"], output_file="test_naver.csv")
