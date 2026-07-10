"""B-4. 평균 문장 길이 분석"""
import os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats
import re

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

raw = pd.read_csv("data/health_blog_raw_scored_no_kin.csv")
raw = raw[raw["설명"].notna() & (raw["설명"].str.len() >= 30)]

ai_pool    = raw[raw["AI여부"] == "AI"]
human_pool = raw[raw["AI여부"] == "인간"]

N = 1500
ai_texts    = ai_pool.sample(min(N, len(ai_pool)),       random_state=42)["설명"].tolist()
human_texts = human_pool.sample(min(N, len(human_pool)), random_state=42)["설명"].tolist()

def avg_sent_len(texts):
    lens = []
    for text in texts:
        sents = [s.strip() for s in re.split(r'[.!?]+', str(text)) if len(s.strip()) > 2]
        if sents:
            lens.append(np.mean([len(s.split()) for s in sents]))
    return np.array(lens)

print("문장 길이 계산 중...")
ai_lens    = avg_sent_len(ai_texts)
human_lens = avg_sent_len(human_texts)

ai_mean, ai_std    = np.mean(ai_lens),    np.std(ai_lens)
hm_mean, hm_std    = np.mean(human_lens), np.std(human_lens)
t_stat, p_val      = stats.ttest_ind(ai_lens, human_lens)
sig = "유의 (p<0.05)" if p_val < 0.05 else "비유의"

print(f"\n=== B-4. 평균 문장 길이 ===")
print(f"  AI 글:  {ai_mean:.3f} ± {ai_std:.3f}  (n={len(ai_lens)})")
print(f"  인간 글: {hm_mean:.3f} ± {hm_std:.3f}  (n={len(human_lens)})")
print(f"  t={t_stat:.4f}, p={p_val:.4f} → {sig}")

# 그래프
fig, ax = plt.subplots(figsize=(7, 5))
groups = ["AI 글", "인간 글"]
means  = [ai_mean, hm_mean]
stds   = [ai_std,  hm_std]
colors = ["#e74c3c", "#3498db"]
bars = ax.bar(groups, means, color=colors, alpha=0.85, zorder=3)
ax.errorbar([0, 1], means, yerr=stds, fmt="none", color="black", capsize=8, lw=2, zorder=4)
for bar, m in zip(bars, means):
    ax.text(bar.get_x()+bar.get_width()/2, m+0.2,
            f"{m:.2f}어절", ha="center", fontsize=13, fontweight="bold")
ax.set_ylabel("평균 문장 길이 (어절 수)", fontsize=11)
ax.set_title(
    f"B-4. AI vs 인간 평균 문장 길이\n"
    f"(t={t_stat:.2f}, p={p_val:.4f}, n=1500)", fontsize=12, fontweight="bold"
)
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0, max(means)*1.4)
plt.tight_layout()
plt.savefig("results/B4_sentence_length.png", dpi=150, bbox_inches="tight")
plt.close()

result_txt = (
    f"=== B-4. 평균 문장 길이 ===\n"
    f"AI 글:  {ai_mean:.4f} ± {ai_std:.4f}  (n={len(ai_lens)})\n"
    f"인간 글: {hm_mean:.4f} ± {hm_std:.4f}  (n={len(human_lens)})\n"
    f"t={t_stat:.4f}, p={p_val:.4f} → {sig}\n"
)
with open("results/B4_sentence_length_result.txt", "w", encoding="utf-8") as f:
    f.write(result_txt)

print("  → results/B4_*.png, B4_*.txt 저장 완료")
