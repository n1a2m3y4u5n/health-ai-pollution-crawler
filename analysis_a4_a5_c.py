"""
건강정보 AI 오염 실태 연구 - A-4, A-5, C파트 분석
"""

import os, json, time, warnings, subprocess, re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats

warnings.filterwarnings("ignore")

# ── 한글 폰트 ──────────────────────────────────────────────
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
raw = pd.read_csv("data/health_blog_raw_scored_no_kin.csv")
raw_a = raw[raw["AI여부"].isin(["AI","인간"])].copy()
raw_a["is_ai"] = (raw_a["AI여부"] == "AI").astype(int)
raw_a["AI탐지점수"] = pd.to_numeric(raw_a["AI탐지점수"], errors="coerce")
print(f"분석 대상: {len(raw_a):,}개\n")


# ════════════════════════════════════════════════════════════
# A-4. 카테고리별 세부 분석
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("A-4. 카테고리별 세부 분석")
print("=" * 55)

cat_order = ["상_일반질환","상_정신건강","상_보완대체의학","중_생활건강","하_경증"]
cat_colors = ["#c0392b","#e74c3c","#e67e22","#f39c12","#2ecc71"]

rows_cat = []
for cat in cat_order:
    sub = raw_a[raw_a["카테고리"] == cat]
    n   = len(sub)
    p   = sub["is_ai"].mean()
    se  = np.sqrt(p*(1-p)/n)
    ci  = 1.96*se
    rows_cat.append({"카테고리":cat,"n":n,"AI비율(%)":round(p*100,1),
                     "CI_lower":round((p-ci)*100,1),"CI_upper":round((p+ci)*100,1)})

df_cat = pd.DataFrame(rows_cat)
print("\n=== A-4 카테고리별 AI 비율 ===")
for _, r in df_cat.iterrows():
    print(f"  {r['카테고리']:<18}: {r['AI비율(%)']:.1f}%  (n={r['n']:,}, 95%CI [{r['CI_lower']}~{r['CI_upper']}])")

# 카이제곱 검정 (카테고리 간)
ct = [[raw_a[(raw_a["카테고리"]==cat)&(raw_a["AI여부"]=="AI")].shape[0],
       raw_a[(raw_a["카테고리"]==cat)&(raw_a["AI여부"]=="인간")].shape[0]] for cat in cat_order]
chi2_c, p_c, dof_c, _ = stats.chi2_contingency(ct)
sig_c = "유의함 (p<0.05)" if p_c < 0.05 else "유의하지 않음"
print(f"\n카이제곱 χ²={chi2_c:.4f}, df={dof_c}, p={p_c:.4f} → {sig_c}")

# 키워드별 AI 비율
kw_rows = []
for cat in cat_order:
    for kw, grp in raw_a[raw_a["카테고리"]==cat].groupby("키워드"):
        kw_rows.append({"카테고리":cat,"키워드":kw,"n":len(grp),
                        "AI비율(%)":round(grp["is_ai"].mean()*100,1)})
df_kw = pd.DataFrame(kw_rows).sort_values(["카테고리","AI비율(%)"],ascending=[True,False])

print("\n카테고리별 TOP5 키워드:")
for cat in cat_order:
    top5 = df_kw[df_kw["카테고리"]==cat].head(5)
    parts = [f"{r['키워드']}({r['AI비율(%)']:.1f}%)" for _,r in top5.iterrows()]
    print(f"  {cat}: " + " / ".join(parts))

# 저장
result_txt = f"=== A-4 카테고리별 AI 비율 ===\n"
result_txt += df_cat.to_string(index=False) + "\n\n"
result_txt += f"카이제곱 χ²={chi2_c:.4f}, df={dof_c}, p={p_c:.4f} → {sig_c}\n\n"
result_txt += "카테고리별 TOP5 키워드:\n"
for cat in cat_order:
    top5 = df_kw[df_kw["카테고리"]==cat].head(5)
    parts = [f"{r['키워드']}({r['AI비율(%)']:.1f}%)" for _,r in top5.iterrows()]
    result_txt += f"  {cat}: " + " / ".join(parts) + "\n"
with open("results/A4_result.txt","w",encoding="utf-8") as f:
    f.write(result_txt)

# 그래프 1: 카테고리별 AI 비율
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
bars = axes[0].bar(range(len(cat_order)), df_cat["AI비율(%)"],
                   color=cat_colors, alpha=0.85, zorder=3)
err_low  = df_cat["AI비율(%)"] - df_cat["CI_lower"]
err_high = df_cat["CI_upper"]  - df_cat["AI비율(%)"]
axes[0].errorbar(range(len(cat_order)), df_cat["AI비율(%)"],
                 yerr=[err_low, err_high], fmt="none", color="black", capsize=6, lw=1.5)
for bar, r in zip(bars, df_cat.itertuples()):
    axes[0].text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.3,
                 f"{r[3]:.1f}%", ha="center", fontsize=11, fontweight="bold")
axes[0].set_xticks(range(len(cat_order)))
axes[0].set_xticklabels([c.replace("_","\n") for c in cat_order], fontsize=9)
axes[0].set_ylabel("AI 탐지 비율 (%)", fontsize=11)
axes[0].set_title(f"카테고리별 AI 비율\n(χ²={chi2_c:.2f}, p={p_c:.4f})", fontsize=12, fontweight="bold")
axes[0].grid(axis="y", alpha=0.3)
axes[0].axhline(raw_a["is_ai"].mean()*100, color="gray", linestyle="--", lw=1.2,
                label=f"전체 평균 {raw_a['is_ai'].mean()*100:.1f}%")
axes[0].legend(fontsize=9)

# 그래프 2: 카테고리별 n 수
axes[1].barh(range(len(cat_order)), df_cat["n"][::-1],
             color=cat_colors[::-1], alpha=0.75)
axes[1].set_yticks(range(len(cat_order)))
axes[1].set_yticklabels(cat_order[::-1], fontsize=9)
axes[1].set_xlabel("샘플 수", fontsize=11)
axes[1].set_title("카테고리별 샘플 수", fontsize=12)
for i, n in enumerate(df_cat["n"][::-1]):
    axes[1].text(n+50, i, f"{n:,}", va="center", fontsize=9)
axes[1].grid(axis="x", alpha=0.3)
plt.tight_layout()
plt.savefig("results/A4_category_ai_ratio.png", dpi=150, bbox_inches="tight")
plt.close()

# 그래프 3: 키워드 TOP5
fig, axes = plt.subplots(1, len(cat_order), figsize=(18, 5))
for ax, cat, col in zip(axes, cat_order, cat_colors):
    top5 = df_kw[df_kw["카테고리"]==cat].head(5).sort_values("AI비율(%)")
    bars = ax.barh(top5["키워드"], top5["AI비율(%)"], color=col, alpha=0.8)
    for bar, v in zip(bars, top5["AI비율(%)"]):
        ax.text(v+0.3, bar.get_y()+bar.get_height()/2, f"{v:.1f}%", va="center", fontsize=8)
    ax.set_title(cat.replace("_","\n"), fontsize=9, fontweight="bold", color=col)
    ax.set_xlabel("AI 비율 (%)", fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    ax.set_xlim(0, df_kw["AI비율(%)"].max()*1.2)
plt.suptitle("카테고리별 TOP5 키워드 AI 비율", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig("results/A4_keyword_top5.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  → results/A4_*.png, A4_result.txt 저장 완료\n")




# ════════════════════════════════════════════════════════════
# C파트. 의학적 오류율 측정 (claude CLI)
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("C파트. 의학적 오류율 측정 (Claude API 팩트체크)")
print("=" * 55)

FACTCHECK_JSON = "results/C2_factcheck_raw.json"

SYSTEM_PROMPT = """너는 의학 정보 팩트체커야.
주어진 건강 정보 텍스트에서 의학적 주장을 추출하고 각 주장의 정확성을 평가해.
판정 기준:
- 정확: 의학적으로 올바른 정보
- 부분오류: 일부만 맞거나 과장된 정보
- 완전오류: 사실과 다른 정보
- 오래된정보: 과거엔 맞았지만 현재 지침과 다름
- 판단불가: 근거 불충분

반드시 JSON으로만 응답해:
{"claims":[{"claim":"주장 내용","verdict":"정확/부분오류/완전오류/오래된정보/판단불가","reason":"판정 이유"}],"overall_verdict":"정확/부분오류/완전오류/오래된정보","risk_level":"높음/중간/낮음"}"""

# AI 점수 상위 50개 (위험도 상 우선)
top50 = (raw_a[raw_a["위험도"]=="상"]
         .dropna(subset=["AI탐지점수","설명"])
         .sort_values("AI탐지점수", ascending=False)
         .head(50))
if len(top50) < 50:
    extra = (raw_a[~raw_a.index.isin(top50.index)]
             .dropna(subset=["AI탐지점수","설명"])
             .sort_values("AI탐지점수", ascending=False)
             .head(50-len(top50)))
    top50 = pd.concat([top50, extra])

print(f"\n분석 샘플: {len(top50)}개 (AI점수 상위, 위험도 상 우선)")
print(f"AI점수 범위: {top50['AI탐지점수'].min():.3f} ~ {top50['AI탐지점수'].max():.3f}\n")

def claude_factcheck(title, desc, idx):
    text = f"제목: {title}\n내용: {desc}\n\n반드시 JSON만 응답해. 다른 텍스트 없이 JSON 객체만."
    try:
        result = subprocess.run(
            ["claude", "-p", "--append-system-prompt", SYSTEM_PROMPT, text],
            capture_output=True, text=True, timeout=90
        )
        output = result.stdout.strip()
        # JSON 추출 (마크다운 코드블록 포함 처리)
        output = re.sub(r"```json\s*", "", output)
        output = re.sub(r"```\s*", "", output)
        m = re.search(r'\{.*\}', output, re.DOTALL)
        if m:
            return json.loads(m.group())
    except subprocess.TimeoutExpired:
        print(f"  [{idx}] 타임아웃")
    except json.JSONDecodeError as e:
        print(f"  [{idx}] JSON 파싱 실패: {e}")
    except Exception as e:
        print(f"  [{idx}] 오류: {e}")
    return None

if os.path.exists(FACTCHECK_JSON):
    print(f"  기존 팩트체크 결과 로드: {FACTCHECK_JSON}")
    with open(FACTCHECK_JSON, encoding="utf-8") as f:
        factcheck_results = json.load(f)
else:
    factcheck_results = []
    for i, (_, row) in enumerate(top50.iterrows(), 1):
        title = str(row.get("제목",""))
        desc  = str(row.get("설명",""))
        result = claude_factcheck(title, desc, i)
        entry = {
            "idx": i,
            "키워드": row.get("키워드",""),
            "카테고리": row.get("카테고리",""),
            "위험도": row.get("위험도",""),
            "AI탐지점수": row.get("AI탐지점수",""),
            "제목": title[:60],
            "factcheck": result
        }
        factcheck_results.append(entry)
        if result:
            ov = result.get("overall_verdict","?")
            rl = result.get("risk_level","?")
            nc = len(result.get("claims",[]))
            print(f"  [{i:2d}/50] {row.get('키워드',''):<12} | {ov} | 위험:{rl} | 주장 {nc}개")
        else:
            print(f"  [{i:2d}/50] {row.get('키워드',''):<12} | 분석 실패")
        time.sleep(1.0)

# 결과 저장
with open("results/C2_factcheck_raw.json","w",encoding="utf-8") as f:
    json.dump(factcheck_results, f, ensure_ascii=False, indent=2)

# 집계
valid = [r for r in factcheck_results if r["factcheck"]]
verdicts = [r["factcheck"].get("overall_verdict","판단불가") for r in valid]
risks    = [r["factcheck"].get("risk_level","?") for r in valid]

from collections import Counter
vcount = Counter(verdicts)
rcount = Counter(risks)

error_cnt  = vcount.get("부분오류",0) + vcount.get("완전오류",0)
error_rate = error_cnt / len(valid) * 100 if valid else 0
high_risk  = rcount.get("높음",0)

print(f"\n=== C파트. 의학적 오류율 ===")
print(f"분석 성공: {len(valid)}/50개")
print(f"\n판정 결과:")
for v_name in ["정확","부분오류","완전오류","오래된정보","판단불가"]:
    cnt = vcount.get(v_name,0)
    pct = cnt/len(valid)*100 if valid else 0
    print(f"  {v_name:<8}: {cnt:2d}개 ({pct:.1f}%)")
print(f"\n전체 오류율: {error_rate:.1f}% (부분+완전오류)")
print(f"고위험 판정: {high_risk}개 ({high_risk/len(valid)*100:.1f}%)")

# 키워드별 오류율
kw_err = {}
for r in valid:
    kw = r["키워드"]
    ov = r["factcheck"].get("overall_verdict","판단불가")
    if kw not in kw_err:
        kw_err[kw] = {"total":0,"error":0}
    kw_err[kw]["total"] += 1
    if ov in ("부분오류","완전오류"):
        kw_err[kw]["error"] += 1

kw_err_rate = {k: v["error"]/v["total"]*100 for k,v in kw_err.items() if v["total"]>0}
top5_kw = sorted(kw_err_rate.items(), key=lambda x:-x[1])[:5]
print("\n오류 많은 키워드 TOP5:")
for i, (kw, rate) in enumerate(top5_kw, 1):
    print(f"  {i}. {kw}: {rate:.1f}%")

# 저장 텍스트
c_txt  = f"=== C파트 의학적 오류율 ===\n"
c_txt += f"분석 샘플: {len(valid)}/50개\n\n"
c_txt += "판정 결과:\n"
for v_name in ["정확","부분오류","완전오류","오래된정보","판단불가"]:
    cnt = vcount.get(v_name,0)
    c_txt += f"  {v_name}: {cnt}개 ({cnt/len(valid)*100:.1f}%)\n" if valid else ""
c_txt += f"\n전체 오류율: {error_rate:.1f}%\n"
c_txt += f"고위험 판정: {high_risk}개\n\nTOP5 오류 키워드:\n"
for i,(kw,rate) in enumerate(top5_kw,1):
    c_txt += f"  {i}. {kw}: {rate:.1f}%\n"
with open("results/C2_factcheck_result.txt","w",encoding="utf-8") as f:
    f.write(c_txt)

# 그래프
fig, axes = plt.subplots(1, 2, figsize=(13, 6))

# 판정 분포 파이차트
v_labels = [k for k in ["정확","부분오류","완전오류","오래된정보","판단불가"] if vcount.get(k,0)>0]
v_sizes  = [vcount[k] for k in v_labels]
v_colors = ["#2ecc71","#f39c12","#e74c3c","#9b59b6","#95a5a6"][:len(v_labels)]
wedges, texts, autotexts = axes[0].pie(
    v_sizes, labels=v_labels, colors=v_colors,
    autopct="%1.1f%%", startangle=140, pctdistance=0.75
)
for at in autotexts: at.set_fontsize(10)
axes[0].set_title(f"AI 탐지 글 의학 정확성 판정\n(오류율 {error_rate:.1f}%)", fontsize=12, fontweight="bold")

# 위험도 분포
r_labels = [k for k in ["높음","중간","낮음"] if rcount.get(k,0)>0]
r_sizes  = [rcount[k] for k in r_labels]
r_colors = ["#e74c3c","#f39c12","#2ecc71"][:len(r_labels)]
bars = axes[1].bar(r_labels, r_sizes, color=r_colors, alpha=0.85)
for bar, v in zip(bars, r_sizes):
    axes[1].text(bar.get_x()+bar.get_width()/2, v+0.2,
                 f"{v}개\n({v/len(valid)*100:.1f}%)", ha="center", fontsize=11, fontweight="bold")
axes[1].set_title("의료 위험도 판정 분포", fontsize=12)
axes[1].set_ylabel("건수", fontsize=11)
axes[1].grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("results/C2_factcheck_summary.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  → results/C2_*.png, C2_*.json, C2_*.txt 저장 완료")


# ════════════════════════════════════════════════════════════
# 포스터용 핵심 수치
# ════════════════════════════════════════════════════════════
best_cat = df_cat.loc[df_cat["AI비율(%)"].idxmax()]
overall  = raw_a["is_ai"].mean()*100

print(f"""
=== 포스터용 핵심 수치 ===
A-4: "{best_cat['카테고리']} 카테고리 AI 비율 {best_cat['AI비율(%)']:.1f}%로 최고"
C:   "AI 탐지 글의 {error_rate:.1f}%에서 의학적 오류 발견"
전체 AI 비율: {overall:.1f}%
""")
