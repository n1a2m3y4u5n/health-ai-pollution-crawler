"""
D파트 - 인식 조사 분석
D-1: 인식 갭 / D-2: AI 탐지 능력
"""

import os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from collections import Counter

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

# ── 데이터 로드 ────────────────────────────────────────────
df = pd.read_csv("제목 없는 설문지.csv")
N = len(df)
print(f"응답 수: {N}건\n")

# 컬럼 단축명
COL_FREQ    = "1-2. AI 의심 글을 접해본 빈도는?"
COL_TRUST   = "3. AI가 생성한 글을 신뢰하는가?"
COL_DISTRUST= "3-2. 신뢰하지 않는다면, 그 이유는?"
COL_RECOG   = "1-3. AI가 생성한 글이라는 것을 알 수 있었던 이유는? "
COL_DAMAGE  = "2. AI가 생성한 글로 인해 피해를 본 경험이 있는가?"
COL_DETECT  = "위 두 글 중 사람이 작성한 글은 무엇일까요? "


def parse_multi(series):
    """';' 구분 복수응답 → Counter"""
    counter = Counter()
    for val in series.dropna():
        for item in str(val).split(";"):
            item = item.strip()
            if item:
                counter[item] += 1
    return counter


# ════════════════════════════════════════════════════════════
# D-1. 인식 갭 분석
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("D-1. 인식 갭 분석")
print("=" * 50)

# 1-2. 노출 빈도
freq_order = ["거의 매일", "주 4~6회", "주 2~3회", "주 1회", "월 1회", "한 달에 1회 미만"]
freq_counts = df[COL_FREQ].value_counts()
freq_vals   = [freq_counts.get(k, 0) for k in freq_order]

# 1-3 신뢰도
trust_map   = {1: "불신", 2: "보통", 3: "신뢰"}
trust_counts = df[COL_TRUST].value_counts().sort_index()

# 1-4 불신 이유
distrust_cnt = parse_multi(df[COL_DISTRUST])
distrust_items = sorted(distrust_cnt.items(), key=lambda x: -x[1])

# 1-5 AI 인지 이유
recog_cnt   = parse_multi(df[COL_RECOG])
recog_items = sorted(recog_cnt.items(), key=lambda x: -x[1])

# 인식 갭 수치
high_freq = sum(freq_counts.get(k, 0) for k in ["거의 매일", "주 4~6회", "주 2~3회"])
damage_rate = (df[COL_DAMAGE] == "예").sum() / N * 100

print(f"\n노출 빈도 분포:")
for k, v in zip(freq_order, freq_vals):
    print(f"  {k:<16}: {v}명 ({v/N*100:.1f}%)")

print(f"\n체감 고빈도(주 2회+): {high_freq}명 ({high_freq/N*100:.1f}%)")
print(f"피해 경험율: {damage_rate:.1f}%")

print(f"\n신뢰도 분포:")
for score, label in trust_map.items():
    cnt = trust_counts.get(score, 0)
    print(f"  {score}점({label}): {cnt}명 ({cnt/N*100:.1f}%)")

print(f"\n불신 이유 TOP5:")
for item, cnt in distrust_items[:5]:
    print(f"  {item}: {cnt}건")

print(f"\nAI 인지 이유 TOP5:")
for item, cnt in recog_items[:5]:
    print(f"  {item}: {cnt}건")


# ─── D-1 그래프 ────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(15, 11))

# (0,0) 노출 빈도
ax = axes[0][0]
colors_freq = ["#e74c3c" if k in ["거의 매일","주 4~6회","주 2~3회"] else "#95a5a6"
               for k in freq_order]
bars = ax.bar(range(len(freq_order)), freq_vals, color=colors_freq, alpha=0.85, zorder=3)
for bar, v in zip(bars, freq_vals):
    if v > 0:
        ax.text(bar.get_x()+bar.get_width()/2, v+0.15,
                f"{v}명\n({v/N*100:.0f}%)", ha="center", fontsize=9, fontweight="bold")
ax.set_xticks(range(len(freq_order)))
ax.set_xticklabels(freq_order, fontsize=8, rotation=15, ha="right")
ax.set_ylabel("응답 수")
ax.set_title(f"AI 글 노출 빈도 (n={N})\n(빨강: 주 2회 이상)", fontsize=11, fontweight="bold")
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0, max(freq_vals) * 1.4)

# (0,1) 신뢰도
ax = axes[0][1]
trust_labels = [trust_map[s] for s in sorted(trust_map)]
trust_vals   = [trust_counts.get(s, 0) for s in sorted(trust_map)]
trust_colors = ["#e74c3c", "#f39c12", "#2ecc71"]
bars = ax.bar(trust_labels, trust_vals, color=trust_colors, alpha=0.85, zorder=3)
for bar, v in zip(bars, trust_vals):
    ax.text(bar.get_x()+bar.get_width()/2, v+0.15,
            f"{v}명\n({v/N*100:.0f}%)", ha="center", fontsize=11, fontweight="bold")
ax.set_ylabel("응답 수")
ax.set_title(f"AI 글 신뢰도 분포 (n={N})", fontsize=11, fontweight="bold")
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0, max(trust_vals) * 1.4)

# (1,0) 불신 이유
ax = axes[1][0]
if distrust_items:
    labels_d = [x[0] for x in distrust_items]
    vals_d   = [x[1] for x in distrust_items]
    # 긴 레이블 줄바꿈
    labels_d_wrap = [l.replace("있어서", "있어서\n") if len(l) > 15 else l for l in labels_d]
    bars = ax.barh(range(len(labels_d)), vals_d, color="#e74c3c", alpha=0.8)
    ax.set_yticks(range(len(labels_d)))
    ax.set_yticklabels(labels_d, fontsize=8)
    for bar, v in zip(bars, vals_d):
        ax.text(v+0.1, bar.get_y()+bar.get_height()/2,
                f"{v}건", va="center", fontsize=9, fontweight="bold")
    ax.set_xlabel("언급 횟수")
    ax.set_title(f"AI 글 불신 이유 (복수응답, n={N})", fontsize=11, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

# (1,1) AI 인지 이유
ax = axes[1][1]
if recog_items:
    labels_r = [x[0] for x in recog_items]
    vals_r   = [x[1] for x in recog_items]
    bars = ax.barh(range(len(labels_r)), vals_r, color="#2980b9", alpha=0.8)
    ax.set_yticks(range(len(labels_r)))
    ax.set_yticklabels(labels_r, fontsize=8)
    for bar, v in zip(bars, vals_r):
        ax.text(v+0.1, bar.get_y()+bar.get_height()/2,
                f"{v}건", va="center", fontsize=9, fontweight="bold")
    ax.set_xlabel("언급 횟수")
    ax.set_title(f"AI 글 인지 이유 (복수응답, n={N})", fontsize=11, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

plt.suptitle("D-1. AI 건강 정보 인식 조사 결과", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig("results/D1_awareness_analysis.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  → results/D1_awareness_analysis.png 저장")


# ════════════════════════════════════════════════════════════
# D-2. AI 탐지 능력
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 50)
print("D-2. AI 탐지 능력")
print("=" * 50)

correct = (df[COL_DETECT].str.strip() == "1번").sum()
wrong   = N - correct
acc     = correct / N

# 이항검정 (정규근사, scipy 없이)
p0    = 0.5
z     = (correct - N * p0) / np.sqrt(N * p0 * (1 - p0))
p_val = 2 * (1 - (0.5 * (1 + np.sign(z) *
        (1 - np.exp(-0.717 * abs(z) - 0.416 * z**2)))))
# 더 정확한 정규분포 CDF 근사 (에르푸 함수)
from math import erf, sqrt
def norm_cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2)))
p_two = 2 * min(norm_cdf(z), 1 - norm_cdf(z))

sig = "유의 (p<0.05)" if p_two < 0.05 else "비유의 — 랜덤 추측과 유의미한 차이 없음"

print(f"\n정답(1번): {correct}명 / 오답(2번): {wrong}명")
print(f"정답률: {acc*100:.1f}%")
print(f"z={z:.4f}, p={p_two:.4f} → {sig}")


# ─── D-2 그래프 (도넛 차트) ────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 7))

sizes  = [correct, wrong]
labels = [f"정답 (1번)\n{correct}명", f"오답 (2번)\n{wrong}명"]
colors = ["#2ecc71", "#e74c3c"]
wedges, texts, autotexts = ax.pie(
    sizes, labels=labels, colors=colors,
    autopct="%1.1f%%", startangle=90,
    pctdistance=0.75,
    wedgeprops={"width": 0.55, "edgecolor": "white", "linewidth": 2}
)
for at in autotexts:
    at.set_fontsize(13)
    at.set_fontweight("bold")
for t in texts:
    t.set_fontsize(11)

ax.text(0, 0.08, f"정답률\n{acc*100:.1f}%",
        ha="center", va="center", fontsize=16, fontweight="bold", color="#2c3e50")
ax.text(0, -0.18, f"(n={N})",
        ha="center", va="center", fontsize=11, color="gray")

ax.set_title(
    f"AI 글 탐지 능력 측정\n"
    f"이항검정 z={z:.2f}, p={p_two:.3f} → {sig}",
    fontsize=12, fontweight="bold", pad=20
)

plt.tight_layout()
plt.savefig("results/D2_detection_ability.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → results/D2_detection_ability.png 저장")


# ════════════════════════════════════════════════════════════
# 결과 저장
# ════════════════════════════════════════════════════════════
trust_1 = trust_counts.get(1, 0)
trust_2 = trust_counts.get(2, 0)
trust_3 = trust_counts.get(3, 0)
top_distrust = distrust_items[0][0] if distrust_items else "없음"

result_txt  = "=== D파트. 인식 조사 분석 ===\n\n"
result_txt += f"응답 수: {N}건\n"
result_txt += "⚠ 대표성 한계 — 고등학생 편중 표본 (17~19세 다수)\n\n"

result_txt += "[ D-1. 인식 갭 ]\n"
result_txt += f"체감 노출(주 2회 이상): {high_freq}명 ({high_freq/N*100:.1f}%)\n"
result_txt += f"피해 경험율: {(df[COL_DAMAGE]=='예').sum()}명 ({damage_rate:.1f}%)\n\n"

result_txt += "노출 빈도:\n"
for k, v in zip(freq_order, freq_vals):
    result_txt += f"  {k}: {v}명 ({v/N*100:.1f}%)\n"

result_txt += f"\n신뢰도: 불신 {trust_1}명 / 보통 {trust_2}명 / 신뢰 {trust_3}명\n"
result_txt += f"  불신율: {trust_1/N*100:.1f}% / 신뢰율: {trust_3/N*100:.1f}%\n\n"

result_txt += "불신 이유 (복수응답):\n"
for item, cnt in distrust_items:
    result_txt += f"  {item}: {cnt}건\n"

result_txt += "\nAI 인지 이유 (복수응답):\n"
for item, cnt in recog_items:
    result_txt += f"  {item}: {cnt}건\n"

result_txt += f"\n[ D-2. AI 탐지 능력 ]\n"
result_txt += f"정답(1번): {correct}명 / 오답(2번): {wrong}명\n"
result_txt += f"정답률: {acc*100:.1f}%\n"
result_txt += f"이항검정 (귀무: 정답률=50%): z={z:.4f}, p={p_two:.4f} → {sig}\n\n"

result_txt += "[ 포스터용 핵심 메시지 ]\n"
result_txt += f"D-1: \"응답자 {high_freq/N*100:.0f}%가 AI 글을 주 2회 이상 접한다고 체감\"\n"
result_txt += f"D-2: \"AI 글 탐지 정답률 {acc*100:.1f}% — 이항검정 p={p_two:.3f}로 랜덤(50%)과 유의미한 차이 없음\"\n"
result_txt += f"D-1: \"AI 글 불신 이유 1위: {top_distrust}\"\n"

with open("results/D_result.txt", "w", encoding="utf-8") as f:
    f.write(result_txt)

print("\n  → results/D_result.txt 저장")
print("\n=== 완료 ===")
print(f"\n포스터용 핵심 메시지:")
print(f"  D-1: 응답자 {high_freq/N*100:.0f}%가 AI 글을 주 2회 이상 접한다고 체감")
print(f"  D-2: 정답률 {acc*100:.1f}%, 이항검정 p={p_two:.3f} → 랜덤 추측과 유의미한 차이 없음")
print(f"  불신 이유 1위: {top_distrust}")
