"""
C-3. 모델 붕괴 실험
인간 원본 → 5세대 반복 패러프레이징 → 언어 품질 지표 변화 측정
Claude CLI (claude -p) 사용
"""

import os, re, json, time, subprocess, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

warnings.filterwarnings("ignore")

def set_korean_font():
    for path in ["/System/Library/Fonts/AppleSDGothicNeo.ttc",
                 "/Library/Fonts/NanumGothic.ttf"]:
        if os.path.exists(path):
            fe = fm.FontEntry(fname=path, name="KoreanFont")
            fm.fontManager.ttflist.insert(0, fe)
            matplotlib.rc("font", family="KoreanFont")
            return
    matplotlib.rc("font", family="AppleGothic")

set_korean_font()
matplotlib.rc("axes", unicode_minus=False)
os.makedirs("results", exist_ok=True)

CACHE_FILE  = "results/C3_generations_cache.json"
GENERATIONS = 15
N_SAMPLES   = 20

PARAPHRASE_SYSTEM = "당신은 텍스트를 자연스럽게 다시 쓰는 도우미입니다."
PARAPHRASE_PROMPT = (
    "다음 글을 같은 의미를 유지하면서 다른 표현으로 바꿔 쓰세요. "
    "원문보다 길거나 짧아져도 됩니다. 오직 바꿔 쓴 글만 출력하세요.\n\n{text}"
)


# ── 형태소 분석 ────────────────────────────────────────────
try:
    from kiwipiepy import Kiwi
    kiwi = Kiwi()
    def tokenize(text):
        return [t.form for t in kiwi.tokenize(str(text)) if len(t.form) > 0]
    print("kiwipiepy 토크나이저 사용")
except Exception:
    def tokenize(text):
        return str(text).split()
    print("공백 기준 토크나이저 사용")


# ── 지표 계산 ──────────────────────────────────────────────
def compute_metrics_single(text):
    tokens = tokenize(str(text))
    if len(tokens) < 3:
        return None
    # TTR
    ttr = len(set(tokens)) / len(tokens)
    # 엔트로피
    freq = Counter(tokens)
    total = sum(freq.values())
    probs = [c/total for c in freq.values()]
    entropy = -sum(p * np.log2(p) for p in probs if p > 0)
    # Dist-2, Dist-3
    bigrams  = list(zip(tokens[:-1], tokens[1:]))
    trigrams = list(zip(tokens[:-2], tokens[1:-1], tokens[2:]))
    dist2 = len(set(bigrams))  / len(bigrams)  if bigrams  else 0
    dist3 = len(set(trigrams)) / len(trigrams) if trigrams else 0
    # 평균 문장 길이
    sents = [s.strip() for s in re.split(r'[.!?]+', str(text)) if len(s.strip()) > 2]
    avg_sent = np.mean([len(s.split()) for s in sents]) if sents else 0
    return {"TTR": ttr, "엔트로피": entropy, "Dist-2": dist2, "Dist-3": dist3,
            "평균문장길이": avg_sent}


def paraphrase_claude(text, idx, gen):
    prompt = PARAPHRASE_PROMPT.format(text=text)
    try:
        result = subprocess.run(
            ["claude", "-p", "--append-system-prompt", PARAPHRASE_SYSTEM, prompt],
            capture_output=True, text=True, timeout=90
        )
        output = result.stdout.strip()
        if output and len(output) > 10:
            return output
        print(f"  [샘플{idx} 세대{gen}] 빈 응답")
    except subprocess.TimeoutExpired:
        print(f"  [샘플{idx} 세대{gen}] 타임아웃")
    except Exception as e:
        print(f"  [샘플{idx} 세대{gen}] 오류: {e}")
    return None


# ── 원본 샘플 로드 ─────────────────────────────────────────
print("=== C-3. 모델 붕괴 실험 ===\n")
raw = pd.read_csv("data/health_blog_raw_scored_no_kin.csv")
origin_texts = (
    raw[(raw["AI여부"] == "인간") & (raw["설명"].str.len() >= 100)]
    .sample(N_SAMPLES, random_state=42)["설명"]
    .tolist()
)
print(f"원본 샘플: {len(origin_texts)}건\n")


# ── 캐시 로드 또는 세대 생성 ───────────────────────────────
if os.path.exists(CACHE_FILE):
    print(f"캐시 로드: {CACHE_FILE}")
    with open(CACHE_FILE, encoding="utf-8") as f:
        all_generations = json.load(f)
    # 기존 캐시 검증
    completed = min(len(v) - 1 for v in all_generations.values())
    print(f"  완료된 세대: {completed}세대\n")
else:
    all_generations = {str(i): [origin_texts[i]] for i in range(N_SAMPLES)}
    completed = 0

WORKERS = 10  # 동시 병렬 호출 수

def paraphrase_one(args):
    idx, prev_text, gen = args
    new_text = paraphrase_claude(prev_text, idx+1, gen)
    if new_text is None:
        new_text = prev_text
    return idx, new_text

total_calls = 0
for gen in range(completed + 1, GENERATIONS + 1):
    print(f"--- {gen}세대 패러프레이징 (병렬 {WORKERS}개) ---")
    tasks = [(idx, all_generations[str(idx)][-1], gen) for idx in range(N_SAMPLES)]

    results_gen = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(paraphrase_one, t): t[0] for t in tasks}
        for future in as_completed(futures):
            idx, new_text = future.result()
            results_gen[idx] = new_text
            total_calls += 1
            print(f"  [{idx+1:2d}/{N_SAMPLES}] 세대{gen} 완료 ({len(new_text)}자)")

    for idx in range(N_SAMPLES):
        all_generations[str(idx)].append(results_gen[idx])

    # 세대별 캐시 저장
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_generations, f, ensure_ascii=False, indent=2)
    print(f"  → {gen}세대 캐시 저장\n")

print(f"총 API 호출: {total_calls}회\n")


# ── 세대별 지표 계산 ───────────────────────────────────────
print("지표 계산 중...")
metric_names = ["TTR", "엔트로피", "Dist-2", "Dist-3", "평균문장길이", "코사인유사도"]
gen_labels   = ["원본"] + [f"{g}세대" for g in range(1, GENERATIONS+1)]

# TF-IDF 기반 원본 대비 코사인 유사도
all_texts_flat = []
for idx in range(N_SAMPLES):
    all_texts_flat.extend(all_generations[str(idx)])

tfidf = TfidfVectorizer(analyzer="char", ngram_range=(2,3))
try:
    tfidf.fit(all_texts_flat)
    tfidf_fitted = True
except Exception:
    tfidf_fitted = False

# 세대별 × 샘플별 지표
results_by_gen = {g: {m: [] for m in metric_names} for g in range(GENERATIONS+1)}

for idx in range(N_SAMPLES):
    origin_text = all_generations[str(idx)][0]
    origin_vec  = tfidf.transform([origin_text]) if tfidf_fitted else None

    for gen_idx in range(GENERATIONS+1):
        text = all_generations[str(idx)][gen_idx]
        m = compute_metrics_single(text)
        if m is None:
            continue
        for key in ["TTR","엔트로피","Dist-2","Dist-3","평균문장길이"]:
            results_by_gen[gen_idx][key].append(m[key])

        # 코사인 유사도
        if tfidf_fitted and origin_vec is not None:
            try:
                vec = tfidf.transform([text])
                sim = cosine_similarity(origin_vec, vec)[0][0]
                results_by_gen[gen_idx]["코사인유사도"].append(float(sim))
            except Exception:
                pass

# 요약
print("\n=== 세대별 지표 ===")
summary_rows = []
for gen_idx, label in enumerate(gen_labels):
    row = {"세대": label}
    print(f"\n[{label}]")
    for m in metric_names:
        vals = results_by_gen[gen_idx][m]
        if vals:
            mean, std = np.mean(vals), np.std(vals)
            print(f"  {m:<10}: {mean:.4f} ± {std:.4f}")
            row[f"{m}_mean"] = round(mean, 4)
            row[f"{m}_std"]  = round(std, 4)
    summary_rows.append(row)

df_summary = pd.DataFrame(summary_rows)
df_summary.to_csv("results/C3_model_collapse.csv", index=False, encoding="utf-8-sig")


# ── 그래프 ─────────────────────────────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
x = np.arange(len(gen_labels))

for ax, metric in zip(axes.flat, metric_names):
    means = []
    stds  = []
    for gen_idx in range(GENERATIONS+1):
        vals = results_by_gen[gen_idx][metric]
        means.append(np.mean(vals) if vals else 0)
        stds.append(np.std(vals) if vals else 0)

    ax.errorbar(x, means, yerr=stds, fmt="-o", color="#e74c3c",
                capsize=5, lw=2, markersize=7, markerfacecolor="white",
                markeredgewidth=2, zorder=3)
    ax.fill_between(x,
                    np.array(means) - np.array(stds),
                    np.array(means) + np.array(stds),
                    alpha=0.15, color="#e74c3c")
    ax.set_xticks(x)
    ax.set_xticklabels(gen_labels, fontsize=9)
    ax.set_title(metric, fontsize=12, fontweight="bold")
    ax.set_ylabel("값", fontsize=9)
    ax.grid(alpha=0.3)

    # 변화 방향 표시
    if len(means) >= 2 and means[0] != 0:
        delta = means[-1] - means[0]
        sign  = "▲" if delta > 0 else "▼"
        color = "#c0392b" if delta < 0 else "#27ae60"
        ax.text(0.97, 0.05, f"{sign}{abs(delta):.3f}",
                transform=ax.transAxes, ha="right", fontsize=10,
                fontweight="bold", color=color)

plt.suptitle(
    f"C-3. 반복 패러프레이징에 따른 언어 품질 변화 (n={N_SAMPLES})\n"
    f"원본 인간 글 → {GENERATIONS}세대 Claude 패러프레이징",
    fontsize=13, fontweight="bold"
)
plt.tight_layout()
plt.savefig("results/C3_model_collapse.png", dpi=150, bbox_inches="tight")
plt.close()


# ── 결과 텍스트 ────────────────────────────────────────────
result_txt  = "=== C-3. 모델 붕괴 실험 결과 ===\n\n"
result_txt += f"원본: 인간 작성 글 {N_SAMPLES}건 (100자 이상)\n"
result_txt += f"세대: 원본 + {GENERATIONS}세대 패러프레이징\n"
result_txt += f"사용 모델: claude (CLI), 호출 수: {total_calls}회\n\n"
result_txt += "[ 세대별 지표 평균 ]\n"
for gen_idx, label in enumerate(gen_labels):
    result_txt += f"\n{label}:\n"
    for m in metric_names:
        vals = results_by_gen[gen_idx][m]
        if vals:
            result_txt += f"  {m:<10}: {np.mean(vals):.4f} ± {np.std(vals):.4f}\n"
result_txt += "\n[ 원본 → 5세대 변화 ]\n"
for m in metric_names:
    v0 = np.mean(results_by_gen[0][m]) if results_by_gen[0][m] else 0
    v5 = np.mean(results_by_gen[GENERATIONS][m]) if results_by_gen[GENERATIONS][m] else 0
    delta = v5 - v0
    direction = "증가" if delta > 0 else "감소"
    result_txt += f"  {m:<10}: {v0:.4f} → {v5:.4f} ({direction} {abs(delta):.4f})\n"
result_txt += f"\n사용 모델: claude-haiku (CLI 경유), 호출 수: {total_calls}회\n"

with open("results/C3_result.txt", "w", encoding="utf-8") as f:
    f.write(result_txt)

print(f"\n=== 저장 완료 ===")
print("  results/C3_model_collapse.png")
print("  results/C3_model_collapse.csv")
print("  results/C3_result.txt")

print("\n=== 원본 → 5세대 변화 ===")
for m in metric_names:
    v0 = np.mean(results_by_gen[0][m]) if results_by_gen[0][m] else 0
    v5 = np.mean(results_by_gen[GENERATIONS][m]) if results_by_gen[GENERATIONS][m] else 0
    print(f"  {m:<10}: {v0:.4f} → {v5:.4f} (Δ{v5-v0:+.4f})")
