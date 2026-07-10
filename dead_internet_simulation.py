# -*- coding: utf-8 -*-
"""
죽은 인터넷 이론 생태계 시뮬레이션 (Direction 2)
- AI 콘텐츠 점유율(a)과 AI 콘텐츠 품질(q)의 피드백 루프를 차분방정식으로 모형화
- 실제 데이터로 보정:  성장률 = 시계열(2020 11.4% -> 2025 29.1%),  품질감쇠 = C3 모델붕괴 실험
- 시나리오 비교 + '임계점(인터넷 건강성 지수<0.5)' 도달연도 추정
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy.optimize import minimize_scalar

# ---- 한글 폰트 ----
FP = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
fontprop = fm.FontProperties(fname=FP)
plt.rcParams['axes.unicode_minus'] = False

# ================== 1. 실제 데이터 (보정용) ==================
obs_years = np.array([2020, 2021, 2022, 2023, 2024, 2025])
obs_a     = np.array([0.114, 0.095, 0.150, 0.117, 0.184, 0.291])   # naver_blog 연도별 AI비율

# C3 모델붕괴: 품질(원본 대비 코사인 유사도=정보 충실도) 세대별
c3_fidelity = np.array([1.0,0.371,0.383,0.299,0.328,0.279,0.295,0.285,0.277,0.271,
                        0.271,0.257,0.268,0.239,0.258,0.244])   # 0~15세대
c3_ttr = np.array([0.7612,0.7315,0.7118,0.7124,0.6995,0.695,0.6906,0.6933,0.6871,
                   0.6992,0.6851,0.6892,0.6835,0.6774,0.6752,0.667])

# ================== 2. 성장률 alpha 보정 ==================
# 로지스틱 채택곡선:  a_{t+1} = a_t + alpha * a_t * (1 - a_t)
def sim_a_only(alpha, a0, steps):
    a=[a0]
    for _ in range(steps):
        a.append(min(0.999, a[-1] + alpha*a[-1]*(1-a[-1])))
    return np.array(a)

def loss(alpha):
    pred = sim_a_only(alpha, obs_a[0], len(obs_years)-1)
    return np.mean((pred-obs_a)**2)

res = minimize_scalar(loss, bounds=(0.01, 1.5), method='bounded')
ALPHA = res.x
print(f"[보정] 로지스틱 성장률 alpha = {ALPHA:.3f}  (관측 2020-2025 적합)")

# ================== 3. 품질감쇠 lambda 보정 ==================
# C3: 학습데이터가 100% AI일 때(=1세대 붕괴) 정보충실도가 1.0 -> 약 0.37로 급락(1세대).
# 이후 완만. 연 단위 모형에서 lambda 는 'AI 학습점유율당 품질감쇠 민감도'.
# 보수적으로 1세대 급락(빠름)과 TTR 완만감쇠(느림) 사이를 baseline 으로 두고 민감도분석.
LAMBDA_BASE = 0.35     # baseline (C3 정보충실도 급락과 정합)
LAMBDA_SLOW = 0.12     # TTR(다양성) 완만감쇠 기반 (낙관)
LAMBDA_FAST = 0.55     # 충실도 붕괴 강조 (비관)
MU_BASE  = 0.05        # 인간 콘텐츠에 의한 품질 복원율
print(f"[보정] 품질감쇠 lambda baseline = {LAMBDA_BASE} (C3 붕괴곡선 기반), 민감도 {LAMBDA_SLOW}~{LAMBDA_FAST}")

# ================== 4. 시뮬레이션 엔진 ==================
def simulate(alpha=ALPHA, lam=LAMBDA_BASE, mu=MU_BASE, phi=0.0,
             a0=0.114, q0=1.0, years=31):
    """phi: 플랫폼 표시/필터링으로 학습풀에서 제거되는 AI 비율(개입)"""
    a=[a0]; q=[q0]
    for _ in range(years-1):
        at, qt = a[-1], q[-1]
        a_next = at + alpha*at*(1-at) - phi*at
        a_next = min(0.999, max(0.0, a_next))
        # 학습데이터 중 실효 AI 점유율(개입 반영)
        a_train = at*(1-phi)
        q_next = qt - lam*a_train*qt + mu*(1-at)*(1-qt)
        q_next = min(1.0, max(0.0, q_next))
        a.append(a_next); q.append(q_next)
    a=np.array(a); q=np.array(q)
    ihi = 1 - a*(1-q)                     # 인터넷 건강성 지수
    return a, q, ihi

YEARS = 31   # 2020~2050
yrs = np.arange(2020, 2020+YEARS)

def cross_year(ihi, thr=0.5):
    idx = np.where(ihi < thr)[0]
    return int(yrs[idx[0]]) if len(idx) else None

scenarios = {
    "① 기본(관성 유지)":      dict(lam=LAMBDA_BASE, mu=MU_BASE, phi=0.0),
    "② 피드백 없음(반사실)":   dict(lam=0.0,          mu=MU_BASE, phi=0.0),
    "③ 플랫폼 표시·필터링":    dict(lam=LAMBDA_BASE, mu=MU_BASE, phi=0.15),
    "④ 리터러시+인간콘텐츠 진작": dict(lam=LAMBDA_BASE, mu=0.18,     phi=0.06),
}
colors = {"① 기본(관성 유지)":"#C0392B", "② 피드백 없음(반사실)":"#7F8C8D",
          "③ 플랫폼 표시·필터링":"#2E86C1", "④ 리터러시+인간콘텐츠 진작":"#27AE60"}

results={}
print("\n[결과] 인터넷 건강성 지수(IHI)<0.5 도달연도 / 2050년 AI점유율·IHI")
for name,p in scenarios.items():
    a,q,ihi = simulate(**p)
    results[name]=(a,q,ihi)
    cy = cross_year(ihi)
    print(f"  {name:22s} 임계점={cy if cy else '도달안함':>7} | 2050 a={a[-1]*100:4.1f}% q={q[-1]:.2f} IHI={ihi[-1]:.2f}")

# ================== 5. 시각화 ==================
fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.6))

# (좌) AI 콘텐츠 점유율
ax=axes[0]
for name,(a,q,ihi) in results.items():
    ax.plot(yrs, a*100, color=colors[name], lw=2.4, label=name)
ax.scatter(obs_years, obs_a*100, color='black', zorder=5, s=45,
           label="실측(2020-2025)")
ax.axhline(50, ls='--', color='gray', lw=1)
ax.text(2020.3, 51.5, "50% (콘텐츠 과반 AI)", fontproperties=fontprop, fontsize=9, color='gray')
ax.set_title("AI 콘텐츠 점유율 예측", fontproperties=fontprop, fontsize=14)
ax.set_xlabel("연도", fontproperties=fontprop, fontsize=11)
ax.set_ylabel("AI 콘텐츠 비율 (%)", fontproperties=fontprop, fontsize=11)
ax.set_ylim(0,100); ax.grid(alpha=0.25)
ax.legend(prop=fontprop, fontsize=9, loc='upper left')

# (우) 인터넷 건강성 지수
ax=axes[1]
for name,(a,q,ihi) in results.items():
    ax.plot(yrs, ihi, color=colors[name], lw=2.4, label=name)
ax.axhline(0.5, ls='--', color='crimson', lw=1.2)
ax.text(2020.3, 0.52, "임계점 IHI=0.5", fontproperties=fontprop, fontsize=9, color='crimson')
ax.set_title("인터넷 건강성 지수 (IHI = 1 − AI점유율×품질저하)", fontproperties=fontprop, fontsize=13)
ax.set_xlabel("연도", fontproperties=fontprop, fontsize=11)
ax.set_ylabel("건강성 지수 (1=건강, 0=붕괴)", fontproperties=fontprop, fontsize=11)
ax.set_ylim(0,1.02); ax.grid(alpha=0.25)
ax.legend(prop=fontprop, fontsize=9, loc='lower left')

fig.suptitle("죽은 인터넷 생태계 시뮬레이션 — AI 오염 피드백 루프 모형",
             fontproperties=fontprop, fontsize=15, y=1.02)
fig.tight_layout()
OUT="/sessions/peaceful-busy-bardeen/mnt/files/results/SIM_dead_internet.png"
fig.savefig(OUT, dpi=150, bbox_inches='tight')
print(f"\n[저장] {OUT}")

# 민감도 분석 (lambda) : 기본 시나리오에서 임계점 도달연도
print("\n[민감도] lambda 변화 시 임계점(IHI<0.5) 도달연도")
for lam,label in [(LAMBDA_SLOW,'낙관'),(LAMBDA_BASE,'기본'),(LAMBDA_FAST,'비관')]:
    a,q,ihi=simulate(lam=lam)
    print(f"  lambda={lam} ({label}): {cross_year(ihi)}년 | 2050 AI점유율 {a[-1]*100:.0f}%")
