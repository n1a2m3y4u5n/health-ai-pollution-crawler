"""C파트만 단독 실행"""
import os, json, time, re, subprocess, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from collections import Counter

warnings.filterwarnings("ignore")

def set_korean_font():
    for path in ["/System/Library/Fonts/AppleSDGothicNeo.ttc", "/Library/Fonts/NanumGothic.ttf"]:
        if os.path.exists(path):
            fe = fm.FontEntry(fname=path, name="KoreanFont")
            fm.fontManager.ttflist.insert(0, fe)
            matplotlib.rc("font", family="KoreanFont"); return
    matplotlib.rc("font", family="AppleGothic")

set_korean_font()
matplotlib.rc("axes", unicode_minus=False)
os.makedirs("results", exist_ok=True)

raw = pd.read_csv("data/health_blog_raw_scored.csv")
raw_a = raw[raw["AI여부"].isin(["AI","인간"])].copy()
raw_a["AI탐지점수"] = pd.to_numeric(raw_a["AI탐지점수"], errors="coerce")

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

print(f"분석 샘플: {len(top50)}개 | AI점수 범위: {top50['AI탐지점수'].min():.3f}~{top50['AI탐지점수'].max():.3f}\n")

def claude_factcheck(title, desc, idx):
    text = f"제목: {title}\n내용: {desc}\n\n반드시 JSON만 응답해."
    try:
        result = subprocess.run(
            ["claude", "-p", "--append-system-prompt", SYSTEM_PROMPT, text],
            capture_output=True, text=True, timeout=90
        )
        output = re.sub(r"```json\s*|```\s*", "", result.stdout.strip())
        m = re.search(r'\{.*\}', output, re.DOTALL)
        if m:
            return json.loads(m.group())
    except subprocess.TimeoutExpired:
        print(f"  [{idx}] 타임아웃")
    except Exception as e:
        print(f"  [{idx}] 오류: {e}")
    return None

factcheck_results = []
for i, (_, row) in enumerate(top50.iterrows(), 1):
    title  = str(row.get("제목",""))
    desc   = str(row.get("설명",""))
    result = claude_factcheck(title, desc, i)
    entry  = {"idx":i, "키워드":row.get("키워드",""), "카테고리":row.get("카테고리",""),
              "위험도":row.get("위험도",""), "AI탐지점수":row.get("AI탐지점수",""),
              "제목":title[:60], "factcheck":result}
    factcheck_results.append(entry)
    if result:
        ov = result.get("overall_verdict","?")
        rl = result.get("risk_level","?")
        nc = len(result.get("claims",[]))
        print(f"  [{i:2d}/50] {row.get('키워드',''):<14} | {ov} | 위험:{rl} | 주장 {nc}개")
    else:
        print(f"  [{i:2d}/50] {row.get('키워드',''):<14} | 실패")
    time.sleep(1.0)

with open("results/C2_factcheck_raw.json","w",encoding="utf-8") as f:
    json.dump(factcheck_results, f, ensure_ascii=False, indent=2)

valid    = [r for r in factcheck_results if r["factcheck"]]
verdicts = [r["factcheck"].get("overall_verdict","판단불가") for r in valid]
risks    = [r["factcheck"].get("risk_level","?") for r in valid]
vcount   = Counter(verdicts)
rcount   = Counter(risks)
error_cnt  = vcount.get("부분오류",0) + vcount.get("완전오류",0)
error_rate = error_cnt/len(valid)*100 if valid else 0
high_risk  = rcount.get("높음",0)

print(f"\n=== C파트. 의학적 오류율 ===")
print(f"분석 성공: {len(valid)}/50개\n")
print("판정 결과:")
for v in ["정확","부분오류","완전오류","오래된정보","판단불가"]:
    cnt=vcount.get(v,0); pct=cnt/len(valid)*100 if valid else 0
    print(f"  {v:<8}: {cnt:2d}개 ({pct:.1f}%)")
print(f"\n전체 오류율: {error_rate:.1f}%")
print(f"고위험 판정: {high_risk}개 ({high_risk/len(valid)*100:.1f}%)" if valid else "")

kw_err={}
for r in valid:
    kw=r["키워드"]; ov=r["factcheck"].get("overall_verdict","판단불가")
    kw_err.setdefault(kw,{"t":0,"e":0})
    kw_err[kw]["t"]+=1
    if ov in ("부분오류","완전오류"): kw_err[kw]["e"]+=1
top5_kw=sorted({k:v["e"]/v["t"]*100 for k,v in kw_err.items() if v["t"]>0}.items(),key=lambda x:-x[1])[:5]
print("\n오류 많은 키워드 TOP5:")
for i,(kw,rate) in enumerate(top5_kw,1):
    print(f"  {i}. {kw}: {rate:.1f}%")

# 저장
c_txt = f"분석 성공: {len(valid)}/50개\n오류율: {error_rate:.1f}%\n고위험: {high_risk}개\n\n"
c_txt += "\n".join(f"{v}: {vcount.get(v,0)}개" for v in ["정확","부분오류","완전오류","오래된정보","판단불가"])
with open("results/C2_factcheck_result.txt","w",encoding="utf-8") as f: f.write(c_txt)

# 그래프
fig, axes = plt.subplots(1, 2, figsize=(13, 6))
v_labels=[k for k in ["정확","부분오류","완전오류","오래된정보","판단불가"] if vcount.get(k,0)>0]
v_sizes=[vcount[k] for k in v_labels]
v_colors=["#2ecc71","#f39c12","#e74c3c","#9b59b6","#95a5a6"][:len(v_labels)]
wedges,texts,autotexts=axes[0].pie(v_sizes,labels=v_labels,colors=v_colors,autopct="%1.1f%%",startangle=140,pctdistance=0.75)
for at in autotexts: at.set_fontsize(10)
axes[0].set_title(f"AI 탐지 글 의학 정확성\n오류율 {error_rate:.1f}%",fontsize=12,fontweight="bold")

r_labels=[k for k in ["높음","중간","낮음"] if rcount.get(k,0)>0]
r_sizes=[rcount[k] for k in r_labels]
r_colors=["#e74c3c","#f39c12","#2ecc71"][:len(r_labels)]
bars=axes[1].bar(r_labels,r_sizes,color=r_colors,alpha=0.85)
for bar,v in zip(bars,r_sizes):
    axes[1].text(bar.get_x()+bar.get_width()/2,v+0.2,f"{v}개\n({v/len(valid)*100:.1f}%)",ha="center",fontsize=11,fontweight="bold")
axes[1].set_title("의료 위험도 판정",fontsize=12); axes[1].set_ylabel("건수"); axes[1].grid(axis="y",alpha=0.3)
plt.tight_layout()
plt.savefig("results/C2_factcheck_summary.png",dpi=150,bbox_inches="tight")
plt.close()

print(f"\n→ results/C2_* 저장 완료")
print(f'\n=== 포스터용 ===\nC: "AI 탐지 글의 {error_rate:.1f}%에서 의학적 오류 발견"')
