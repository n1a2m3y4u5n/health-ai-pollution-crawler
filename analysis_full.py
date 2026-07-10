"""
건강정보 AI 오염 실태 연구 - 전체 통계 분석
A파트 (실태) / B파트 (언어통계) / E파트 (시계열)
"""

import os, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

warnings.filterwarnings("ignore")

# ── 한글 폰트 설정 ──────────────────────────────────────────
def set_korean_font():
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            fe = fm.FontEntry(fname=path, name="KoreanFont")
            fm.fontManager.ttflist.insert(0, fe)
            matplotlib.rc("font", family="KoreanFont")
            break
    else:
        matplotlib.rc("font", family="AppleGothic")
    matplotlib.rc("axes", unicode_minus=False)

set_korean_font()
os.makedirs("results", exist_ok=True)

# ── 데이터 로드 ──────────────────────────────────────────────
raw = pd.read_csv("data/health_blog_raw_scored_no_kin.csv")
ts  = pd.read_csv("data/health_blog_timeseries_scored.csv")

# 분석 가능한 행만
raw_a = raw[raw["AI여부"].isin(["AI", "인간"])].copy()
raw_a["AI탐지점수"] = pd.to_numeric(raw_a["AI탐지점수"], errors="coerce")
raw_a["노출순위"]   = pd.to_numeric(raw_a["노출순위"],   errors="coerce")
raw_a["is_ai"]     = (raw_a["AI여부"] == "AI").astype(int)

ts_a = ts[ts["AI여부"].isin(["AI", "인간"])].copy()
ts_a["is_ai"] = (ts_a["AI여부"] == "AI").astype(int)

summary = {}

print(f"RAW 분석 대상: {len(raw_a):,}개  |  TIMESERIES: {len(ts_a):,}개\n")


# ════════════════════════════════════════════════════════════
# A-1. 플랫폼별 AI 비율
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("A-1. 플랫폼별 AI 비율")
print("=" * 50)

platform_order = ["naver_blog","naver_news","naver_cafe","naver_kin","tistory","daum_cafe","brunch"]
rows_a1 = []
for p in platform_order:
    sub = raw_a[raw_a["플랫폼"] == p]
    n   = len(sub)
    if n == 0: continue
    p_val = sub["is_ai"].mean()
    se    = np.sqrt(p_val * (1 - p_val) / n)
    ci    = 1.96 * se
    rows_a1.append({"플랫폼": p, "n": n, "AI비율(%)": round(p_val*100,1),
                    "CI_lower": round((p_val-ci)*100,1), "CI_upper": round((p_val+ci)*100,1)})
    print(f"  {p:<15}: {p_val*100:.1f}%  (n={n:,}, 95%CI [{(p_val-ci)*100:.1f}~{(p_val+ci)*100:.1f}])")

df_a1 = pd.DataFrame(rows_a1)
df_a1.to_csv("results/A1_platform_ai_ratio.csv", index=False, encoding="utf-8-sig")

fig, ax = plt.subplots(figsize=(10, 5))
colors = ["#e74c3c" if r > 20 else "#3498db" for r in df_a1["AI비율(%)"]]
bars = ax.bar(df_a1["플랫폼"], df_a1["AI비율(%)"], color=colors, alpha=0.8, zorder=3)
err_low  = df_a1["AI비율(%)"] - df_a1["CI_lower"]
err_high = df_a1["CI_upper"]  - df_a1["AI비율(%)"]
ax.errorbar(df_a1["플랫폼"], df_a1["AI비율(%)"],
            yerr=[err_low, err_high], fmt="none", color="black", capsize=5, linewidth=1.5, zorder=4)
for bar, ratio in zip(bars, df_a1["AI비율(%)"]):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
            f"{ratio:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
ax.set_ylabel("AI 탐지 비율 (%)", fontsize=12)
ax.set_title("플랫폼별 AI 생성 콘텐츠 비율 (95% CI)", fontsize=14, fontweight="bold")
ax.set_ylim(0, max(df_a1["AI비율(%)"]) * 1.3)
ax.grid(axis="y", alpha=0.3, zorder=0)
ax.axhline(raw_a["is_ai"].mean()*100, color="gray", linestyle="--", linewidth=1, label=f"전체 평균 {raw_a['is_ai'].mean()*100:.1f}%")
ax.legend()
plt.tight_layout()
plt.savefig("results/A1_platform_ai_ratio.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → 저장 완료\n")

summary["최고AI플랫폼"] = df_a1.loc[df_a1["AI비율(%)"].idxmax(), "플랫폼"]
summary["최고AI비율"]   = df_a1["AI비율(%)"].max()
summary["최저AI플랫폼"] = df_a1.loc[df_a1["AI비율(%)"].idxmin(), "플랫폼"]
summary["최저AI비율"]   = df_a1["AI비율(%)"].min()


# ════════════════════════════════════════════════════════════
# A-2. 위험도별 AI 비율 + 카이제곱 검정
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("A-2. 위험도별 AI 비율 + 카이제곱 검정")
print("=" * 50)

danger_order = ["상", "중", "하"]
rows_a2 = []
ct_table = []
for d in danger_order:
    sub = raw_a[raw_a["위험도"] == d]
    n_ai  = (sub["AI여부"] == "AI").sum()
    n_hum = (sub["AI여부"] == "인간").sum()
    n     = n_ai + n_hum
    ratio = n_ai / n * 100
    rows_a2.append({"위험도": d, "n": n, "AI비율(%)": round(ratio,1), "AI수": n_ai, "인간수": n_hum})
    ct_table.append([n_ai, n_hum])
    print(f"  위험도 {d}: {ratio:.1f}%  (AI={n_ai:,}, 인간={n_hum:,})")

chi2, p, dof, _ = stats.chi2_contingency(ct_table)
sig = "통계적으로 유의함 (p < 0.05)" if p < 0.05 else "통계적으로 유의하지 않음"
print(f"\n  카이제곱: χ²={chi2:.4f}, df={dof}, p={p:.4f} → {sig}")

df_a2 = pd.DataFrame(rows_a2)
with open("results/A2_chi2_result.txt", "w", encoding="utf-8") as f:
    f.write(f"위험도별 카이제곱 검정\n{'='*40}\n")
    f.write(df_a2.to_string(index=False))
    f.write(f"\n\nχ²={chi2:.4f}, df={dof}, p={p:.4f}\n{sig}\n")

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
colors_d = {"상": "#e74c3c", "중": "#f39c12", "하": "#2ecc71"}
for ax, (metric, ylabel) in zip(axes, [("AI비율(%)", "AI 탐지 비율 (%)"), ("n", "샘플 수")]):
    vals = [df_a2.loc[df_a2["위험도"]==d, metric].values[0] for d in danger_order]
    bars = ax.bar(danger_order, vals, color=[colors_d[d] for d in danger_order], alpha=0.85, zorder=3)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.3,
                f"{v:.1f}%" if metric=="AI비율(%)" else f"{v:,}", ha="center", fontsize=11, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(f"위험도별 {ylabel}", fontsize=12)
    ax.grid(axis="y", alpha=0.3)
axes[0].set_title(f"위험도별 AI 비율\n(χ²={chi2:.2f}, p={p:.4f})", fontsize=12)
plt.tight_layout()
plt.savefig("results/A2_danger_ai_ratio.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → 저장 완료\n")

summary["chi2"] = round(chi2, 4)
summary["chi2_p"] = round(p, 4)
summary["chi2_sig"] = sig


# ════════════════════════════════════════════════════════════
# A-3. 노출순위 × AI탐지점수 피어슨 상관계수
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("A-3. 노출순위 × AI탐지점수 상관계수")
print("=" * 50)

sub_a3 = raw_a.dropna(subset=["노출순위","AI탐지점수"])
r_val, p_val = stats.pearsonr(sub_a3["노출순위"], sub_a3["AI탐지점수"])
print(f"  피어슨 r={r_val:.4f}, p={p_val:.4f}")

bins   = [(1,10),(11,30),(31,60),(61,100)]
bin_rows = []
for lo, hi in bins:
    s = sub_a3[(sub_a3["노출순위"] >= lo) & (sub_a3["노출순위"] <= hi)]
    avg = s["AI탐지점수"].mean()
    bin_rows.append({"구간": f"{lo}~{hi}", "n": len(s), "평균AI점수": round(avg,4)})
    print(f"  순위 {lo:>3}~{hi:>3}위: 평균 AI점수 {avg:.4f} (n={len(s):,})")

with open("results/A3_pearson_result.txt", "w", encoding="utf-8") as f:
    f.write(f"노출순위 × AI탐지점수 피어슨 상관계수\n{'='*40}\n")
    f.write(f"r={r_val:.4f}, p={p_val:.4f}\n\n순위 구간별 평균 AI점수:\n")
    f.write(pd.DataFrame(bin_rows).to_string(index=False))

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
sample = sub_a3.sample(min(3000, len(sub_a3)), random_state=42)
axes[0].scatter(sample["노출순위"], sample["AI탐지점수"], alpha=0.15, s=8, color="#3498db")
m, b = np.polyfit(sub_a3["노출순위"], sub_a3["AI탐지점수"], 1)
x_line = np.array([sub_a3["노출순위"].min(), sub_a3["노출순위"].max()])
axes[0].plot(x_line, m*x_line+b, color="#e74c3c", linewidth=2)
axes[0].set_xlabel("노출순위", fontsize=11); axes[0].set_ylabel("AI탐지점수", fontsize=11)
axes[0].set_title(f"노출순위 × AI점수\nr={r_val:.3f}, p={p_val:.4f}", fontsize=12)

df_bin = pd.DataFrame(bin_rows)
bars = axes[1].bar(df_bin["구간"], df_bin["평균AI점수"], color="#9b59b6", alpha=0.8, zorder=3)
for bar, row in zip(bars, df_bin.itertuples()):
    axes[1].text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.002,
                 f"{row.평균AI점수:.3f}", ha="center", fontsize=10)
axes[1].set_xlabel("노출순위 구간", fontsize=11); axes[1].set_ylabel("평균 AI탐지점수", fontsize=11)
axes[1].set_title("구간별 평균 AI탐지점수", fontsize=12)
axes[1].grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("results/A3_rank_correlation.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → 저장 완료\n")

summary["pearson_r"] = round(r_val, 4)
summary["pearson_p"] = round(p_val, 4)


# ════════════════════════════════════════════════════════════
# A-4. 카테고리별 세부 분석
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("A-4. 카테고리별 AI 비율")
print("=" * 50)

cat_order = ["상_일반질환","상_정신건강","상_보완대체의학","중_생활건강","하_경증"]
rows_a4 = []
kw_rows  = []
for cat in cat_order:
    sub = raw_a[raw_a["카테고리"] == cat]
    n   = len(sub); ratio = sub["is_ai"].mean()*100
    rows_a4.append({"카테고리": cat, "n": n, "AI비율(%)": round(ratio,1)})
    print(f"  {cat:<18}: {ratio:.1f}%  (n={n:,})")
    # 상위 5 키워드
    for kw, grp in sub.groupby("키워드"):
        kw_rows.append({"카테고리": cat, "키워드": kw, "n": len(grp), "AI비율(%)": round(grp["is_ai"].mean()*100,1)})

df_a4  = pd.DataFrame(rows_a4)
df_kw  = pd.DataFrame(kw_rows).sort_values(["카테고리","AI비율(%)"], ascending=[True,False])
df_a4.to_csv("results/A4_category_ai_ratio.csv", index=False, encoding="utf-8-sig")
df_kw.to_csv("results/A4_category_ai_ratio.csv", mode="a", index=False, encoding="utf-8-sig")

print("\n  카테고리별 상위 5 키워드:")
for cat in cat_order:
    top5 = df_kw[df_kw["카테고리"]==cat].head(5)
    print(f"  [{cat}] " + " / ".join(f"{row['키워드']}({row['AI비율(%)']:.0f}%)" for _, row in top5.iterrows()))

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
bars = axes[0].barh(df_a4["카테고리"][::-1], df_a4["AI비율(%)"][::-1],
                    color=["#e74c3c","#e74c3c","#e74c3c","#f39c12","#2ecc71"], alpha=0.85)
for bar, v in zip(bars, df_a4["AI비율(%)"][::-1]):
    axes[0].text(v+0.2, bar.get_y()+bar.get_height()/2, f"{v:.1f}%", va="center", fontsize=10)
axes[0].set_xlabel("AI 탐지 비율 (%)"); axes[0].set_title("카테고리별 AI 비율", fontsize=12)
axes[0].grid(axis="x", alpha=0.3)

top_kw = df_kw.groupby("카테고리").head(3).sort_values("AI비율(%)", ascending=True)
bars2  = axes[1].barh(top_kw["키워드"], top_kw["AI비율(%)"], color="#3498db", alpha=0.75)
for bar, v in zip(bars2, top_kw["AI비율(%)"]):
    axes[1].text(v+0.2, bar.get_y()+bar.get_height()/2, f"{v:.1f}%", va="center", fontsize=8)
axes[1].set_xlabel("AI 탐지 비율 (%)"); axes[1].set_title("카테고리별 상위 3 키워드 AI 비율", fontsize=12)
axes[1].grid(axis="x", alpha=0.3)
plt.tight_layout()
plt.savefig("results/A4_category_ai_ratio.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → 저장 완료\n")


# ════════════════════════════════════════════════════════════
# A-5. 지식iN 특화 분석
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("A-5. 지식iN vs 기타 플랫폼 비교")
print("=" * 50)

kin   = raw_a[raw_a["플랫폼"] == "naver_kin"]
other = raw_a[raw_a["플랫폼"] != "naver_kin"]
kin_ratio   = kin["is_ai"].mean()*100
other_ratio = other["is_ai"].mean()*100
print(f"  naver_kin AI 비율: {kin_ratio:.1f}% (n={len(kin):,})")
print(f"  기타 플랫폼 평균: {other_ratio:.1f}% (n={len(other):,})")

z_stat, z_p = stats.ttest_ind(kin["is_ai"], other["is_ai"])
print(f"  t-검정: t={z_stat:.4f}, p={z_p:.4f}")

kin_by_cat = kin.groupby("카테고리")["is_ai"].agg(["mean","count"]).reset_index()
kin_by_cat.columns = ["카테고리","AI비율","n"]
kin_by_cat["AI비율"] *= 100
kin_by_cat.to_csv("results/A5_kin_analysis.csv", index=False, encoding="utf-8-sig")

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
comp_data = {"naver_kin": kin_ratio, "기타 플랫폼 평균": other_ratio}
bars = axes[0].bar(comp_data.keys(), comp_data.values(), color=["#e74c3c","#3498db"], alpha=0.8)
for bar, v in zip(bars, comp_data.values()):
    axes[0].text(bar.get_x()+bar.get_width()/2, v+0.3, f"{v:.1f}%", ha="center", fontsize=12, fontweight="bold")
axes[0].set_title(f"지식iN vs 기타 (t={z_stat:.2f}, p={z_p:.4f})", fontsize=12)
axes[0].set_ylabel("AI 비율 (%)"); axes[0].grid(axis="y", alpha=0.3)

bars2 = axes[1].barh(kin_by_cat["카테고리"], kin_by_cat["AI비율"], color="#9b59b6", alpha=0.8)
for bar, v in zip(bars2, kin_by_cat["AI비율"]):
    axes[1].text(v+0.2, bar.get_y()+bar.get_height()/2, f"{v:.1f}%", va="center", fontsize=9)
axes[1].set_title("지식iN 카테고리별 AI 비율", fontsize=12)
axes[1].set_xlabel("AI 비율 (%)"); axes[1].grid(axis="x", alpha=0.3)
plt.tight_layout()
plt.savefig("results/A5_kin_analysis.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → 저장 완료\n")


# ════════════════════════════════════════════════════════════
# B파트 — 언어통계 (kiwipiepy 사용)
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("B파트. 언어통계 분석")
print("=" * 50)

try:
    from kiwipiepy import Kiwi
    kiwi = Kiwi()

    def tokenize(text):
        if not isinstance(text, str) or len(text.strip()) < 5:
            return []
        try:
            return [t.form for t in kiwi.tokenize(text) if t.tag not in ("SF","SP","SS","SE","SO","SW","SB","ZN","ZSN","ZSV")]
        except:
            return []

    # 샘플링 (속도 위해 각 1500개)
    ai_texts  = raw_a[raw_a["AI여부"]=="AI"]["설명"].dropna().sample(min(1500,sum(raw_a["AI여부"]=="AI")), random_state=42).tolist()
    hum_texts = raw_a[raw_a["AI여부"]=="인간"]["설명"].dropna().sample(min(1500,sum(raw_a["AI여부"]=="인간")), random_state=42).tolist()

    print("  토크나이징 중...")
    ai_tokens  = [tokenize(t) for t in ai_texts]
    hum_tokens = [tokenize(t) for t in hum_texts]

    # B-1. TTR
    print("\n  B-1. TTR")
    def ttr(tokens):
        return len(set(tokens))/len(tokens) if len(tokens) > 0 else np.nan

    ai_ttr  = [ttr(t) for t in ai_tokens  if len(t) >= 5]
    hum_ttr = [ttr(t) for t in hum_tokens if len(t) >= 5]
    ai_ttr_mean  = np.nanmean(ai_ttr)
    hum_ttr_mean = np.nanmean(hum_ttr)
    t_ttr, p_ttr = stats.ttest_ind(ai_ttr, hum_ttr, nan_policy="omit")
    print(f"    AI TTR:  {ai_ttr_mean:.4f}")
    print(f"    인간 TTR: {hum_ttr_mean:.4f}")
    print(f"    t={t_ttr:.4f}, p={p_ttr:.4f}")

    with open("results/B1_ttr_result.txt", "w", encoding="utf-8") as f:
        f.write(f"TTR 비교\nAI: {ai_ttr_mean:.4f} (n={len(ai_ttr)})\n인간: {hum_ttr_mean:.4f} (n={len(hum_ttr)})\n")
        f.write(f"t={t_ttr:.4f}, p={p_ttr:.4f}\n")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].hist(ai_ttr,  bins=40, alpha=0.6, color="#e74c3c", label=f"AI (μ={ai_ttr_mean:.3f})")
    axes[0].hist(hum_ttr, bins=40, alpha=0.6, color="#3498db", label=f"인간 (μ={hum_ttr_mean:.3f})")
    axes[0].set_xlabel("TTR"); axes[0].set_ylabel("빈도")
    axes[0].set_title(f"AI vs 인간 TTR 분포\n(t={t_ttr:.2f}, p={p_ttr:.4f})", fontsize=12)
    axes[0].legend()

    # B-2. Shannon Entropy
    print("\n  B-2. 어휘 엔트로피")
    from collections import Counter
    def entropy(tokens):
        if len(tokens) < 3: return np.nan
        counts = np.array(list(Counter(tokens).values()), dtype=float)
        probs  = counts / counts.sum()
        return -np.sum(probs * np.log2(probs + 1e-12))

    ai_ent  = [entropy(t) for t in ai_tokens  if len(t) >= 5]
    hum_ent = [entropy(t) for t in hum_tokens if len(t) >= 5]
    ai_ent_mean  = np.nanmean(ai_ent)
    hum_ent_mean = np.nanmean(hum_ent)
    t_ent, p_ent = stats.ttest_ind(ai_ent, hum_ent, nan_policy="omit")
    print(f"    AI 엔트로피:  {ai_ent_mean:.4f}")
    print(f"    인간 엔트로피: {hum_ent_mean:.4f}")
    print(f"    t={t_ent:.4f}, p={p_ent:.4f}")

    axes[1].hist(ai_ent,  bins=40, alpha=0.6, color="#e74c3c", label=f"AI (μ={ai_ent_mean:.3f})")
    axes[1].hist(hum_ent, bins=40, alpha=0.6, color="#3498db", label=f"인간 (μ={hum_ent_mean:.3f})")
    axes[1].set_xlabel("Shannon 엔트로피"); axes[1].set_ylabel("빈도")
    axes[1].set_title(f"AI vs 인간 어휘 엔트로피\n(t={t_ent:.2f}, p={p_ent:.4f})", fontsize=12)
    axes[1].legend()
    plt.tight_layout()
    plt.savefig("results/B1_ttr_comparison.png", dpi=150, bbox_inches="tight")
    plt.savefig("results/B2_entropy_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → 저장 완료")

    summary["ai_ttr"]      = round(ai_ttr_mean, 4)
    summary["hum_ttr"]     = round(hum_ttr_mean, 4)
    summary["ai_entropy"]  = round(ai_ent_mean, 4)
    summary["hum_entropy"] = round(hum_ent_mean, 4)

except Exception as e:
    print(f"  [B-1/B-2 오류] {e}")
    summary["ai_ttr"] = summary["hum_ttr"] = summary["ai_entropy"] = summary["hum_entropy"] = "N/A"


# B-3. 코사인 유사도
print("\n  B-3. 코사인 유사도")
try:
    sample_kws = raw_a["키워드"].value_counts().head(10).index.tolist()
    ai_sims, hum_sims = [], []

    for kw in sample_kws:
        sub_kw = raw_a[raw_a["키워드"] == kw].dropna(subset=["설명"])
        ai_sub  = sub_kw[sub_kw["AI여부"]=="AI"]["설명"].tolist()
        hum_sub = sub_kw[sub_kw["AI여부"]=="인간"]["설명"].tolist()

        for texts, store in [(ai_sub, ai_sims), (hum_sub, hum_sims)]:
            if len(texts) < 2: continue
            texts = texts[:30]
            tfidf  = TfidfVectorizer(analyzer="char", ngram_range=(2,3)).fit_transform(texts)
            mat    = cosine_similarity(tfidf)
            n_t    = len(texts)
            mask   = np.triu(np.ones((n_t,n_t), bool), k=1)
            store.extend(mat[mask].tolist())

    ai_cos_mean  = np.mean(ai_sims)  if ai_sims  else 0
    hum_cos_mean = np.mean(hum_sims) if hum_sims else 0
    t_cos, p_cos = stats.ttest_ind(ai_sims, hum_sims) if (ai_sims and hum_sims) else (0,1)
    print(f"    AI 내부 코사인:  {ai_cos_mean:.4f}")
    print(f"    인간 내부 코사인: {hum_cos_mean:.4f}")
    print(f"    t={t_cos:.4f}, p={p_cos:.4f}")

    with open("results/B3_cosine_result.txt", "w", encoding="utf-8") as f:
        f.write(f"코사인 유사도 비교\nAI: {ai_cos_mean:.4f}\n인간: {hum_cos_mean:.4f}\nt={t_cos:.4f}, p={p_cos:.4f}\n")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(ai_sims[:3000],  bins=50, alpha=0.6, color="#e74c3c", label=f"AI 글 (μ={ai_cos_mean:.3f})")
    ax.hist(hum_sims[:3000], bins=50, alpha=0.6, color="#3498db", label=f"인간 글 (μ={hum_cos_mean:.3f})")
    ax.set_xlabel("코사인 유사도"); ax.set_ylabel("빈도")
    ax.set_title(f"같은 키워드 내 글 간 코사인 유사도\n(t={t_cos:.2f}, p={p_cos:.4f})", fontsize=12)
    ax.legend()
    plt.tight_layout()
    plt.savefig("results/B3_cosine_similarity.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → 저장 완료\n")

    summary["ai_cosine"]  = round(ai_cos_mean, 4)
    summary["hum_cosine"] = round(hum_cos_mean, 4)

except Exception as e:
    print(f"  [B-3 오류] {e}")
    summary["ai_cosine"] = summary["hum_cosine"] = "N/A"


# ════════════════════════════════════════════════════════════
# E-1. 시계열 연도별 AI 비율 추이
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("E-1. 시계열 AI 비율 추이")
print("=" * 50)

years = sorted(ts_a["연도"].unique())
yr_stats = []
for yr in years:
    sub   = ts_a[ts_a["연도"] == yr]
    n     = len(sub)
    p_yr  = sub["is_ai"].mean()
    se    = np.sqrt(p_yr*(1-p_yr)/n)
    ci    = 1.96*se
    yr_stats.append({"연도": yr, "n": n, "AI비율(%)": round(p_yr*100,1),
                     "CI_lower": round((p_yr-ci)*100,1), "CI_upper": round((p_yr+ci)*100,1)})
    label = "(이전)" if yr <= 2022 else "(이후)"
    print(f"  {yr}년 {label}: {p_yr*100:.1f}%  (n={n}, CI [{(p_yr-ci)*100:.1f}~{(p_yr+ci)*100:.1f}])")

before = ts_a[ts_a["연도"] <= 2022]["is_ai"]
after  = ts_a[ts_a["연도"] >= 2023]["is_ai"]
t_ts, p_ts = stats.ttest_ind(before, after)
bef_mean = before.mean()*100
aft_mean = after.mean()*100
print(f"\n  ChatGPT 이전 평균: {bef_mean:.1f}%")
print(f"  ChatGPT 이후 평균: {aft_mean:.1f}%")
print(f"  변화량: +{aft_mean-bef_mean:.1f}%p")
print(f"  t-검정: t={t_ts:.4f}, p={p_ts:.4f}")

with open("results/E1_timeseries_result.txt", "w", encoding="utf-8") as f:
    f.write(pd.DataFrame(yr_stats).to_string(index=False))
    f.write(f"\n\nChatGPT 이전 평균: {bef_mean:.1f}%\nChatGPT 이후 평균: {aft_mean:.1f}%\n")
    f.write(f"변화량: +{aft_mean-bef_mean:.1f}%p\nt={t_ts:.4f}, p={p_ts:.4f}\n")

df_yr = pd.DataFrame(yr_stats)
fig, ax = plt.subplots(figsize=(10, 6))
colors_yr = ["#3498db" if yr <= 2022 else "#e74c3c" for yr in years]
bars = ax.bar([str(y) for y in years], df_yr["AI비율(%)"], color=colors_yr, alpha=0.8, zorder=3, width=0.6)
err_low  = df_yr["AI비율(%)"] - df_yr["CI_lower"]
err_high = df_yr["CI_upper"]  - df_yr["AI비율(%)"]
ax.errorbar([str(y) for y in years], df_yr["AI비율(%)"],
            yerr=[err_low, err_high], fmt="none", color="black", capsize=6, linewidth=1.5, zorder=4)
ax.plot([str(y) for y in years], df_yr["AI비율(%)"], "o-", color="gray", zorder=5, linewidth=1.5, markersize=6)
for bar, ratio in zip(bars, df_yr["AI비율(%)"]):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
            f"{ratio:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")
ax.axvline(x=2.5, color="orange", linewidth=2.5, linestyle="--", zorder=6)
ax.text(2.6, ax.get_ylim()[1]*0.92, "ChatGPT 출시\n(2022.11)", color="orange", fontsize=10, fontweight="bold")
ax.axhspan(0, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 35, xmin=0, xmax=3/6, alpha=0.04, color="#3498db")
ax.axhspan(0, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 35, xmin=3/6, xmax=1,   alpha=0.04, color="#e74c3c")
ax.set_ylabel("AI 탐지 비율 (%)", fontsize=12)
ax.set_title(f"연도별 AI 생성 콘텐츠 비율 추이 (2020~2025)\n"
             f"이전 {bef_mean:.1f}% → 이후 {aft_mean:.1f}%  (t={t_ts:.2f}, p={p_ts:.4f})", fontsize=13)
ax.grid(axis="y", alpha=0.3, zorder=0)
ax.set_ylim(0, max(df_yr["CI_upper"]) * 1.2)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color="#3498db", alpha=0.7, label="ChatGPT 이전"),
                   Patch(color="#e74c3c", alpha=0.7, label="ChatGPT 이후")], fontsize=10)
plt.tight_layout()
plt.savefig("results/E1_timeseries_ai_ratio.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → 저장 완료\n")

summary["ts_before"] = round(bef_mean, 1)
summary["ts_after"]  = round(aft_mean, 1)
summary["ts_change"] = round(aft_mean - bef_mean, 1)
summary["ts_p"]      = round(p_ts, 4)


# ════════════════════════════════════════════════════════════
# E-2. 카테고리별 시계열
# ════════════════════════════════════════════════════════════
print("=" * 50)
print("E-2. 카테고리별 시계열")
print("=" * 50)

fig, axes = plt.subplots(2, 3, figsize=(15, 9))
axes_flat = axes.flatten()
cat_colors = {"상_일반질환": "#e74c3c", "상_정신건강": "#c0392b",
              "상_보완대체의학": "#e67e22", "중_생활건강": "#f39c12", "하_경증": "#2ecc71"}

for idx, cat in enumerate(cat_order):
    ax = axes_flat[idx]
    sub_cat = ts_a[ts_a["카테고리"] == cat]
    yr_ratios = sub_cat.groupby("연도")["is_ai"].agg(["mean","count"]).reset_index()
    yr_ratios.columns = ["연도","비율","n"]
    yr_ratios["비율"] *= 100

    bef_c = sub_cat[sub_cat["연도"]<=2022]["is_ai"].mean()*100
    aft_c = sub_cat[sub_cat["연도"]>=2023]["is_ai"].mean()*100

    ax.plot(yr_ratios["연도"], yr_ratios["비율"], "o-", color=cat_colors.get(cat,"#3498db"),
            linewidth=2, markersize=7, zorder=3)
    ax.axvline(x=2022.9, color="orange", linewidth=1.5, linestyle="--", zorder=4)
    ax.fill_between(yr_ratios["연도"], yr_ratios["비율"], alpha=0.15, color=cat_colors.get(cat,"#3498db"))
    ax.set_title(f"{cat}\n이전 {bef_c:.1f}% → 이후 {aft_c:.1f}%", fontsize=10, fontweight="bold")
    ax.set_ylabel("AI 비율 (%)"); ax.set_xlabel("연도")
    ax.set_xticks(years); ax.grid(alpha=0.3)
    ax.set_ylim(0, max(yr_ratios["비율"].max()*1.3, 5))
    print(f"  {cat}: 이전 {bef_c:.1f}% → 이후 {aft_c:.1f}%  (변화 {aft_c-bef_c:+.1f}%p)")

axes_flat[5].set_visible(False)
plt.suptitle("카테고리별 연도별 AI 비율 추이", fontsize=14, fontweight="bold", y=1.01)
plt.tight_layout()
plt.savefig("results/E2_category_timeseries.png", dpi=150, bbox_inches="tight")
plt.close()
print("  → 저장 완료\n")


# ════════════════════════════════════════════════════════════
# 최종 요약
# ════════════════════════════════════════════════════════════
overall_ai = raw_a["is_ai"].mean()*100

final = f"""
========================================
건강정보 AI 오염 실태 연구 - 분석 결과 요약
========================================

[A. 실태]
전체 AI 비율: {overall_ai:.1f}%
가장 AI 비율 높은 플랫폼: {summary['최고AI플랫폼']} ({summary['최고AI비율']:.1f}%)
가장 AI 비율 낮은 플랫폼: {summary['최저AI플랫폼']} ({summary['최저AI비율']:.1f}%)
위험도 상 AI 비율: {rows_a2[0]['AI비율(%)']:.1f}% / 중: {rows_a2[1]['AI비율(%)']:.1f}% / 하: {rows_a2[2]['AI비율(%)']:.1f}%
카이제곱 χ²={summary['chi2']}, p={summary['chi2_p']} ({summary['chi2_sig']})
노출순위 피어슨 r={summary['pearson_r']}, p={summary['pearson_p']}

[B. 언어통계]
AI 글 평균 TTR: {summary['ai_ttr']} / 인간 글: {summary['hum_ttr']}
AI 글 평균 엔트로피: {summary['ai_entropy']} / 인간 글: {summary['hum_entropy']}
AI 글 내부 코사인 유사도: {summary['ai_cosine']} / 인간 글: {summary['hum_cosine']}

[E. 시계열]
ChatGPT 이전 평균 AI 비율: {summary['ts_before']:.1f}%
ChatGPT 이후 평균 AI 비율: {summary['ts_after']:.1f}%
변화량: +{summary['ts_change']:.1f}%p
t-검정 p값: {summary['ts_p']} ({'유의' if summary['ts_p'] < 0.05 else '비유의'})

========================================
"""

print(final)
with open("results/final_summary.txt", "w", encoding="utf-8") as f:
    f.write(final)

print("모든 결과 저장 완료: results/ 폴더")
