"""
C-1. 3단계 품질 비교 분석 v2
AI 글 / 비전문가(naver_blog+daum_cafe 인간) / 전문가(naver_news 인간) 비교
전문용어 목록: 의학 도메인별 100+ 단어 (임상/약리/진단/치료/증상)
"""

import os, re, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from collections import Counter
from scipy import stats

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

# ════════════════════════════════════════════════════════════
# 의학 전문 용어 목록 (도메인별 분류, 총 110개)
# ════════════════════════════════════════════════════════════
MEDICAL_TERMS = set([
    # 임상/진단
    '소견', '병변', '검진', '진단', '발병', '이환', '예후', '기저질환',
    '합병증', '병인', '발생률', '유병률', '악화', '호전', '관해', '재발',
    '전이', '침윤', '괴사', '허혈', '경색', '협착', '폐쇄', '천공',
    # 치료/시술
    '투여', '처방', '용량', '금기', '적응증', '항암', '방사선', '수술',
    '시술', '처치', '재활', '완화', '절제', '이식', '항생제', '항바이러스',
    '면역억제', '스테로이드', '화학요법', '방사선치료',
    # 증상/징후
    '증상', '징후', '통증', '발열', '부종', '염증', '출혈', '감염',
    '발진', '호흡곤란', '흉통', '두통', '어지럼', '구역', '구토',
    '설사', '변비', '빈뇨', '혈뇨',
    # 검사/수치
    '혈액검사', '조직검사', '생검', '혈당', '혈압', '혈중', '농도',
    '수치', '정상범위', '기준치', '양성', '음성', '민감도', '특이도',
    '영상검사', '내시경', '초음파',
    # 신체 계통/장기
    '심혈관', '신경계', '소화기', '내분비', '면역', '간', '신장',
    '췌장', '심장', '폐', '위장', '대장', '갑상선', '부신',
    '뇌하수체', '관절', '척추',
    # 약리/약물
    '약물', '부작용', '이상반응', '내성', '투약', '복용량', '반감기',
    '흡수', '대사', '배설', '혈중농도',
    # 근거/연구
    '임상', '연구', '근거', '가이드라인', '지침', '권고', '유효성',
    '안전성', '무작위', '대조군', '코호트', '메타분석', '통계적',
    # 질환명
    '고혈압', '당뇨병', '뇌졸중', '심근경색', '협심증', '부정맥',
    '우울증', '불안장애', '조현병', '치매', '파킨슨',
])

print(f"전문용어 목록: {len(MEDICAL_TERMS)}개")


# ════════════════════════════════════════════════════════════
# 데이터 로드 및 그룹 정의
# ════════════════════════════════════════════════════════════
print("\n=== 그룹 샘플링 ===")
raw = pd.read_csv("data/health_blog_raw_scored_no_kin.csv")
raw = raw[raw["설명"].notna() & (raw["설명"].str.len() >= 80)].copy()

# 그룹 1: AI 글
ai_pool = raw[raw["AI여부"] == "AI"]

# 그룹 2: 비전문가 (일반 블로그/카페)
noexp_pool = raw[
    (raw["AI여부"] == "인간") &
    (raw["플랫폼"].isin(["naver_blog", "daum_cafe"]))
]

# 그룹 3: 전문가 (뉴스 — 전문 저널리즘)
expert_pool = raw[
    (raw["AI여부"] == "인간") &
    (raw["플랫폼"] == "naver_news")
]

N = 500
ai_sample    = ai_pool.sample(min(N, len(ai_pool)),       random_state=42)["설명"].tolist()
noexp_sample = noexp_pool.sample(min(N, len(noexp_pool)), random_state=42)["설명"].tolist()
expert_sample = expert_pool.sample(min(N, len(expert_pool)), random_state=42)["설명"].tolist()

print(f"  AI 그룹:    {len(ai_sample)}건  (naver_blog/cafe/news 등 AI탐지)")
print(f"  비전문가:   {len(noexp_sample)}건  (naver_blog + daum_cafe 인간)")
print(f"  전문가:     {len(expert_sample)}건  (naver_news 인간 — 전문 저널리즘)")


# ════════════════════════════════════════════════════════════
# 형태소 분석 (kiwipiepy)
# ════════════════════════════════════════════════════════════
print("\n형태소 분석 중...")
try:
    from kiwipiepy import Kiwi
    kiwi = Kiwi()
    def tokenize(text):
        return [t.form for t in kiwi.tokenize(str(text)) if len(t.form) > 0]
except Exception as e:
    print(f"  kiwipiepy 오류: {e}, 공백 분리로 대체")
    def tokenize(text):
        return str(text).split()


def compute_metrics(texts):
    ttr_list, ent_list, sent_len_list, term_dens_list = [], [], [], []
    for text in texts:
        tokens = tokenize(str(text))
        if len(tokens) < 5:
            continue
        # TTR
        ttr_list.append(len(set(tokens)) / len(tokens))
        # 엔트로피
        freq = Counter(tokens)
        total = sum(freq.values())
        probs = [c / total for c in freq.values()]
        ent_list.append(-sum(p * np.log2(p) for p in probs if p > 0))
        # 평균 문장 길이
        sents = [s.strip() for s in re.split(r'[.!?]+', str(text)) if len(s.strip()) > 2]
        if sents:
            sent_len_list.append(np.mean([len(s.split()) for s in sents]))
        # 전문용어 밀도
        med_cnt = sum(1 for t in tokens if t in MEDICAL_TERMS)
        term_dens_list.append(med_cnt / len(tokens))

    return {
        "TTR":        np.array(ttr_list),
        "엔트로피":    np.array(ent_list),
        "평균문장길이": np.array(sent_len_list),
        "전문용어밀도": np.array(term_dens_list),
    }


groups = {"AI": ai_sample, "비전문가": noexp_sample, "전문가": expert_sample}
print("  지표 계산 중...")
metrics = {name: compute_metrics(texts) for name, texts in groups.items()}
print("  완료")


# ════════════════════════════════════════════════════════════
# 통계 분석
# ════════════════════════════════════════════════════════════
print("\n=== C-1. 3단계 품질 비교 ===")

METRIC_NAMES = ["TTR", "엔트로피", "평균문장길이", "전문용어밀도"]
GROUP_NAMES  = ["AI", "비전문가", "전문가"]
COLORS       = {"AI": "#e74c3c", "비전문가": "#95a5a6", "전문가": "#2980b9"}

summary_rows = []
stat_lines   = []

for metric in METRIC_NAMES:
    vals  = {g: metrics[g][metric] for g in GROUP_NAMES}
    means = {g: np.mean(v) for g, v in vals.items()}
    stds  = {g: np.std(v)  for g, v in vals.items()}
    ns    = {g: len(v)     for g, v in vals.items()}

    print(f"\n[{metric}]")
    for g in GROUP_NAMES:
        print(f"  {g:<6}: {means[g]:.4f} ± {stds[g]:.4f}  (n={ns[g]})")

    try:
        stat, p = stats.kruskal(*[vals[g] for g in GROUP_NAMES])
        test_name = "크루스칼-왈리스"
    except Exception:
        stat, p = stats.f_oneway(*[vals[g] for g in GROUP_NAMES])
        test_name = "ANOVA"

    sig = "유의 (p<0.05)" if p < 0.05 else "비유의"
    print(f"  {test_name}: stat={stat:.4f}, p={p:.4f} → {sig}")
    stat_lines.append(f"[{metric}] {test_name} stat={stat:.4f}, p={p:.4f} → {sig}")

    for g in GROUP_NAMES:
        summary_rows.append({
            "지표": metric, "그룹": g,
            "평균": round(means[g], 4), "표준편차": round(stds[g], 4),
            "n": ns[g]
        })

df_summary = pd.DataFrame(summary_rows)
df_summary.to_csv("results/C1_quality_comparison.csv", index=False, encoding="utf-8-sig")


# ════════════════════════════════════════════════════════════
# 그래프
# ════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
for ax, metric in zip(axes.flat, METRIC_NAMES):
    group_vals = [metrics[g][metric] for g in GROUP_NAMES]
    means_list = [np.mean(v) for v in group_vals]
    stds_list  = [np.std(v)  for v in group_vals]

    bars = ax.bar(GROUP_NAMES, means_list,
                  color=[COLORS[g] for g in GROUP_NAMES], alpha=0.85, zorder=3)
    ax.errorbar(range(len(GROUP_NAMES)), means_list, yerr=stds_list,
                fmt="none", color="black", capsize=6, lw=1.5, zorder=4)
    for bar, mean in zip(bars, means_list):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + max(stds_list) * 0.05,
                f"{mean:.3f}", ha="center", fontsize=11, fontweight="bold")
    ax.set_title(metric, fontsize=13, fontweight="bold")
    ax.set_ylabel("값", fontsize=10)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.set_ylim(0, max(means_list) * 1.35)

# 범례 설명
fig.text(0.5, 0.01,
         "그룹: AI = AI탐지 글 / 비전문가 = 일반블로그+카페 인간 / 전문가 = 뉴스 인간(전문 저널리즘)",
         ha="center", fontsize=9, color="gray")

plt.suptitle("AI / 비전문가 / 전문가 글 언어 품질 비교 (C-1)",
             fontsize=14, fontweight="bold")
plt.tight_layout(rect=[0, 0.04, 1, 1])
plt.savefig("results/C1_quality_comparison.png", dpi=150, bbox_inches="tight")
plt.close()


# ════════════════════════════════════════════════════════════
# 결과 저장
# ════════════════════════════════════════════════════════════
result_txt  = "=== C-1. 3단계 품질 비교 분석 ===\n\n"
result_txt += "[ 그룹 정의 ]\n"
result_txt += "  AI       : AI탐지 글 (모든 플랫폼, AI여부=AI)\n"
result_txt += "  비전문가  : naver_blog + daum_cafe 인간 작성 글\n"
result_txt += "  전문가    : naver_news 인간 작성 글 (전문 저널리즘)\n\n"
result_txt += f"[ 전문용어 목록 ]\n  총 {len(MEDICAL_TERMS)}개 (임상/진단/치료/약리/증상/검사/계통/질환명)\n\n"
result_txt += "[ 그룹별 샘플 수 ]\n"
for g in GROUP_NAMES:
    result_txt += f"  {g}: {len(groups[g])}건\n"
result_txt += "\n[ 지표별 평균 ± 표준편차 ]\n"
for metric in METRIC_NAMES:
    result_txt += f"\n{metric}:\n"
    for g in GROUP_NAMES:
        v = metrics[g][metric]
        result_txt += f"  {g:<6}: {np.mean(v):.4f} ± {np.std(v):.4f}  (n={len(v)})\n"
result_txt += "\n[ 통계 검정 결과 ]\n"
for line in stat_lines:
    result_txt += f"  {line}\n"
result_txt += "\n[ 포스터용 수치 ]\n"
for metric in METRIC_NAMES:
    ai_m, ne_m, ex_m = (np.mean(metrics[g][metric]) for g in GROUP_NAMES)
    result_txt += f"  {metric}: AI={ai_m:.3f} / 비전문가={ne_m:.3f} / 전문가={ex_m:.3f}\n"

with open("results/C1_result.txt", "w", encoding="utf-8") as f:
    f.write(result_txt)

print("\n=== 저장 완료 ===")
print("  results/C1_quality_comparison.png")
print("  results/C1_quality_comparison.csv")
print("  results/C1_result.txt")

print("\n=== 포스터용 핵심 수치 ===")
for metric in METRIC_NAMES:
    ai_m, ne_m, ex_m = (np.mean(metrics[g][metric]) for g in GROUP_NAMES)
    print(f"  {metric}: AI={ai_m:.3f} / 비전문가={ne_m:.3f} / 전문가={ex_m:.3f}")
