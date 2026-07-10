"""
KatFishNet 기반 건강 블로그 AI 탐지 파이프라인

원본 KatFishNet (ACL 2025) 의 punctuation feature 방식 사용:
- kiwipiepy (pure Python, Java 불필요) + kss 문장 분리
- KatFish essay 데이터로 LogisticRegression 학습 후 적용
- comma 패턴 5가지 피처: include_rate, avg_usage_rate,
  avg_relative_pos, avg_segment_len, pos_diversity_around_comma
"""

import csv
import json
import os
import pickle
import time
import warnings
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
from kiwipiepy import Kiwi
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────
# 경로
# ─────────────────────────────────────────────────────────
KATFISH_DIR  = "katfishnet"
DATA_DIR     = "data"
MODEL_PATH   = os.path.join(DATA_DIR, "katfishnet_model.pkl")
RAW_INPUT    = os.path.join(DATA_DIR, "health_blog_raw.csv")
TS_INPUT     = os.path.join(DATA_DIR, "health_blog_timeseries.csv")
RAW_OUTPUT   = os.path.join(DATA_DIR, "health_blog_raw_scored.csv")
TS_OUTPUT    = os.path.join(DATA_DIR, "health_blog_timeseries_scored.csv")
SUMMARY_JSON = os.path.join(DATA_DIR, "katfishnet_summary.json")

MIN_TEXT_LEN  = 50    # 50자 미만 스킵
BATCH_SAVE    = 1000  # N개마다 중간 저장
PROGRESS_STEP = 500   # N개마다 진행률 출력

# ─────────────────────────────────────────────────────────
# Kiwi 초기화 (전역, 1회)
# ─────────────────────────────────────────────────────────
print("Kiwi 형태소 분석기 초기화 중...", end=" ", flush=True)
kiwi = Kiwi()
print("완료")


# ─────────────────────────────────────────────────────────
# 피처 추출
# ─────────────────────────────────────────────────────────
def tokenize_text(text):
    """텍스트 → 문장별 (morphs, pos_tags) 리스트"""
    import kss as _kss
    try:
        sentences = _kss.split_sentences(text)
    except Exception:
        sentences = [text]

    result = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        try:
            tokens = kiwi.tokenize(sent)
            morphs = [t.form for t in tokens]
            pos    = [str(t.tag) for t in tokens]  # tag: str in v0.23, enum in older
            result.append((morphs, pos))
        except Exception:
            pass
    return result


def extract_comma_features(sentence_data):
    """
    문장별 (morphs, pos) 리스트 → 5차원 피처 벡터
    [include_rate, avg_usage_rate, avg_relative_pos, avg_segment_len, pos_diversity]
    """
    if not sentence_data:
        return [0.0, 0.0, 0.0, 0.0, 0.0]

    num_sentences       = len(sentence_data)
    num_comma_sentences = 0
    usage_rates         = []
    rel_positions       = []
    seg_lengths         = []
    pos_diversities     = []

    for morphs, pos in sentence_data:
        comma_idx = [i for i, m in enumerate(morphs) if m == ',']
        n = len(comma_idx)

        if n > 0:
            num_comma_sentences += 1
            rel_pos = [ci / len(morphs) for ci in comma_idx]

            segs, prev = [], 0
            for ci in comma_idx:
                segs.append(len(morphs[prev:ci]))
                prev = ci + 1
            segs.append(len(morphs[prev:]))

            pos_pairs = [(pos[i-1], pos[i+1])
                         for i in comma_idx if 0 < i < len(pos) - 1]
            diversity = (len(set(pos_pairs)) / len(pos_pairs)) if pos_pairs else 0.0

            usage_rates.append(n / len(morphs))
            rel_positions.append(float(np.mean(rel_pos)))
            seg_lengths.append(float(np.mean(segs)))
            pos_diversities.append(diversity)
        else:
            usage_rates.append(0.0)
            rel_positions.append(0.0)
            seg_lengths.append(0.0)
            pos_diversities.append(0.0)

    return [
        num_comma_sentences / num_sentences,
        float(np.mean(usage_rates)),
        float(np.mean(rel_positions)),
        float(np.mean(seg_lengths)),
        float(np.mean(pos_diversities)),
    ]


# ─────────────────────────────────────────────────────────
# 모델 학습 / 로드
# ─────────────────────────────────────────────────────────
def train_katfishnet_model():
    """KatFish essay.jsonl로 LogisticRegression 학습"""
    essay_path = os.path.join(KATFISH_DIR, "katfish_dataset", "essay.jsonl")
    print(f"\n모델 학습 시작: {essay_path}")

    data = []
    with open(essay_path, encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))

    human_texts = [d["text"] for d in data if d["written_by"] == "human"]
    gpt_texts   = [d["text"] for d in data if d["written_by"] == "gpt-4o-2024-05-13"]
    print(f"  human: {len(human_texts)}개 / GPT-4o: {len(gpt_texts)}개")

    def extract_batch(texts, label):
        feats = []
        for i, t in enumerate(texts):
            if (i + 1) % 100 == 0:
                print(f"    [{label}] {i+1}/{len(texts)}", flush=True)
            feats.append(extract_comma_features(tokenize_text(t)))
        return feats

    print("  human 피처 추출...")
    human_feat = extract_batch(human_texts, "human")
    print("  GPT 피처 추출...")
    gpt_feat   = extract_batch(gpt_texts,   "GPT")

    X = np.array(human_feat + gpt_feat)
    y = np.array([0] * len(human_feat) + [1] * len(gpt_feat))

    scaler  = StandardScaler()
    X_sc    = scaler.fit_transform(X)
    model   = LogisticRegression(random_state=42, max_iter=1000)
    model.fit(X_sc, y)

    acc = model.score(X_sc, y)
    print(f"  학습 정확도 (train): {acc:.4f}")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler}, f)
    print(f"  모델 저장: {MODEL_PATH}")
    return model, scaler


def load_or_train_model():
    if os.path.exists(MODEL_PATH):
        print(f"저장된 모델 로드: {MODEL_PATH}")
        with open(MODEL_PATH, "rb") as f:
            obj = pickle.load(f)
        return obj["model"], obj["scaler"]
    return train_katfishnet_model()


# ─────────────────────────────────────────────────────────
# 탐지 파이프라인
# ─────────────────────────────────────────────────────────
def load_done_links(filepath):
    """기존 scored CSV에서 완료된 링크 집합 반환"""
    done = set()
    if not os.path.exists(filepath):
        return done
    with open(filepath, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            lnk = row.get("링크", "")
            if lnk:
                done.add(lnk)
    return done


def run_detection(input_csv, output_csv, model, scaler, label=""):
    """CSV 한 파일 탐지 처리 (resume 지원)"""
    # 원본 컬럼 파악
    with open(input_csv, encoding="utf-8-sig") as f:
        orig_fields = csv.DictReader(f).fieldnames or []
    new_fields = orig_fields + ["AI탐지점수", "AI여부"]

    # 전체 행 로드
    all_rows = []
    with open(input_csv, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            all_rows.append(row)
    total = len(all_rows)

    # 이미 처리된 링크
    done_links = load_done_links(output_csv)

    print(f"\n{'='*60}")
    print(f"[{label}] 탐지 시작: {input_csv}")
    print(f"  전체: {total:,}개 | 이미 완료: {len(done_links):,}개")

    write_header = not os.path.exists(output_csv)
    processed = skipped = errors = new_count = 0
    start_time = time.time()

    with open(output_csv, "a", newline="", encoding="utf-8-sig") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=new_fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        batch = []

        for idx, row in enumerate(all_rows):
            lnk = row.get("링크", "")

            # 이미 처리됨 → 스킵
            if lnk and lnk in done_links:
                continue

            text = row.get("설명", "").strip()

            if len(text) < MIN_TEXT_LEN:
                row["AI탐지점수"] = ""
                row["AI여부"]     = "미분석"
                skipped += 1
            else:
                try:
                    feats = extract_comma_features(tokenize_text(text))
                    score = float(model.predict_proba(scaler.transform([feats]))[0][1])
                    row["AI탐지점수"] = f"{score:.4f}"
                    row["AI여부"]     = "AI" if score >= 0.5 else "인간"
                    processed += 1
                except Exception:
                    row["AI탐지점수"] = ""
                    row["AI여부"]     = "미분석"
                    errors += 1

            batch.append(row)
            new_count += 1

            # 중간 저장
            if len(batch) >= BATCH_SAVE:
                writer.writerows(batch)
                out_f.flush()
                batch = []

            # 진행률
            if new_count > 0 and new_count % PROGRESS_STEP == 0:
                elapsed = time.time() - start_time
                todo    = total - len(done_links) - new_count
                rate    = new_count / elapsed if elapsed > 0 else 1
                eta     = str(timedelta(seconds=int(todo / rate))) if rate > 0 else "?"
                pct     = (idx + 1) / total * 100
                print(f"  [{new_count:,}/{total - len(done_links):,}] "
                      f"{pct:.1f}% | ETA: {eta}", flush=True)

        if batch:
            writer.writerows(batch)

    elapsed = time.time() - start_time
    print(f"  완료 — 분석: {processed:,} / 스킵: {skipped:,} / 오류: {errors:,} "
          f"| 소요: {str(timedelta(seconds=int(elapsed)))}")
    return processed, skipped, errors


# ─────────────────────────────────────────────────────────
# 통계 출력
# ─────────────────────────────────────────────────────────
def ai_ratio(rows, key=None, val=None):
    """필터 조건에 맞는 행의 AI 비율과 n 반환"""
    sub = rows if key is None else [r for r in rows if r.get(key) == val]
    analyzed = [r for r in sub if r.get("AI여부") in ("AI", "인간")]
    if not analyzed:
        return None, 0
    n_ai = sum(1 for r in analyzed if r["AI여부"] == "AI")
    return n_ai / len(analyzed) * 100, len(analyzed)


def print_stats(raw_out, ts_out, summary_path):
    print(f"\n{'='*60}")
    print("=== KatFishNet 탐지 완료 ===")

    def load_csv(path):
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    raw = load_csv(raw_out)
    ts  = load_csv(ts_out)

    n_analyzed = sum(1 for r in raw if r.get("AI여부") in ("AI", "인간"))
    n_skipped  = sum(1 for r in raw if r.get("AI여부") == "미분석")
    print(f"총 분석: {n_analyzed:,}개 / 스킵: {n_skipped:,}개")

    overall, overall_n = ai_ratio(raw)
    if overall is not None:
        print(f"\n전체 AI 비율: {overall:.1f}%")

    # 플랫폼별
    print("\n플랫폼별 AI 비율:")
    platforms = ["naver_blog","naver_news","naver_cafe","naver_kin",
                 "tistory","daum_cafe","brunch"]
    plat_stats = {}
    for p in platforms:
        r, n = ai_ratio(raw, "플랫폼", p)
        if r is not None:
            print(f"  {p:<15}: {r:.1f}% (n={n:,})")
            plat_stats[p] = {"ratio": round(r, 2), "n": n}

    # 위험도별
    print("\n위험도별 AI 비율:")
    danger_stats = {}
    for d in ["상", "중", "하"]:
        r, n = ai_ratio(raw, "위험도", d)
        if r is not None:
            print(f"  {d} : {r:.1f}% (n={n:,})")
            danger_stats[d] = {"ratio": round(r, 2), "n": n}

    # 카테고리별
    print("\n카테고리별 AI 비율:")
    cat_order = ["상_일반질환","상_정신건강","상_보완대체의학","중_생활건강","하_경증"]
    cat_stats = {}
    for cat in cat_order:
        r, n = ai_ratio(raw, "카테고리", cat)
        if r is not None:
            print(f"  {cat:<18}: {r:.1f}%")
            cat_stats[cat] = {"ratio": round(r, 2), "n": n}

    # 시계열 연도별
    year_stats = {}
    if ts:
        print("\n시계열 연도별 AI 비율 (timeseries):")
        for yr in [2020, 2021, 2022, 2023, 2024, 2025]:
            label = "(ChatGPT 이전)" if yr <= 2022 else "(ChatGPT 이후)"
            sub   = [r for r in ts if str(r.get("연도", "")) == str(yr)]
            r, n  = ai_ratio(sub)
            if r is not None:
                print(f"  {yr}년: {r:.1f}%  {label} (n={n:,})")
                year_stats[str(yr)] = {"ratio": round(r, 2), "n": n}

    # JSON 저장
    summary = {
        "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overall":         {"ratio": round(overall, 2) if overall else None, "n": overall_n},
        "platforms":       plat_stats,
        "danger":          danger_stats,
        "categories":      cat_stats,
        "timeseries_years": year_stats,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n통계 저장: {summary_path}")
    print(f"{'='*60}")


# ─────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. 모델
    model, scaler = load_or_train_model()

    # 2. raw 탐지
    run_detection(RAW_INPUT, RAW_OUTPUT, model, scaler, "raw")

    # 3. timeseries 탐지
    run_detection(TS_INPUT, TS_OUTPUT, model, scaler, "timeseries")

    # 4. 통계
    print_stats(RAW_OUTPUT, TS_OUTPUT, SUMMARY_JSON)
