"""
empc_engine.py — Economic Model Predictive Control 최적 급전 엔진
scipy.optimize.minimize(SLSQP)로 24타임스텝 Receding Horizon 최적화
"""

import logging
import time
from typing import Optional
import numpy as np
from scipy.optimize import minimize, Bounds, LinearConstraint
from config import PLANT_PROFILE, PLANT_NAMES, YONGIN_SPEC

logger = logging.getLogger(__name__)

# 동서 계통 혼잡 패널티 (거리 비례)
_CONGESTION_PENALTY = {
    '한울': 0.15,   # 동해안 280km
    '태안': 0.05,   # 서해안 140km
    '보령': 0.04,   # 서해안 120km
    '인천': 0.01,   # 근거리 60km
    '울산': 0.18,   # 동해안 330km
}

N_PLANTS = len(PLANT_NAMES)


class EMPCEngine:
    """
    Economic Model Predictive Control.

    목적 함수 (최소화):
      J = Σ_{k=0}^{N} [ Σ_i C_i(P_i,k) + λ_balance × (ΣP_sent_i,k - P_demand_k)² ]
    비용 함수: C_i(P_i) = a_i × P_i² + b_i × P_i + c_i
    풀이: SLSQP, N=24 Receding Horizon
    """

    HORIZON = 24
    LAMBDA_BALANCE = 1000.0
    LAMBDA_CONGESTION = 50.0

    def __init__(self) -> None:
        # 발전소 파라미터 배열 (N_PLANTS 순서)
        self._a = np.array([PLANT_PROFILE[n]['cost_a'] for n in PLANT_NAMES])
        self._b = np.array([PLANT_PROFILE[n]['cost_b'] for n in PLANT_NAMES])
        self._c = np.array([PLANT_PROFILE[n]['cost_c'] for n in PLANT_NAMES])
        self._cap = np.array([PLANT_PROFILE[n]['capacity_mw'] for n in PLANT_NAMES])
        self._loss = np.array([PLANT_PROFILE[n]['tx_loss_ratio'] for n in PLANT_NAMES])
        self._p_min = np.array([PLANT_PROFILE[n]['p_min_ratio'] for n in PLANT_NAMES])
        self._p_max = np.array([PLANT_PROFILE[n]['p_max_ratio'] for n in PLANT_NAMES])
        self._ramp = np.array([PLANT_PROFILE[n]['ramp_rate_pct_per_min'] / 100.0 for n in PLANT_NAMES])
        self._congestion = np.array([_CONGESTION_PENALTY[n] for n in PLANT_NAMES])

        self._last_solution: Optional[np.ndarray] = None
        self._solve_count: int = 0
        logger.info("EMPCEngine 초기화 완료 (Horizon=%d)", self.HORIZON)

    # ── 공개 API ─────────────────────────────────────────────
    def solve(
        self,
        current_outputs: dict[str, float],
        demand_forecast: list[float],
        reserve_requirement: float,
    ) -> dict[str, float]:
        """
        최적 급전 계산 (Receding Horizon).

        Args:
            current_outputs: 현재 발전소별 출력 비율 (0~1)
            demand_forecast: 향후 HORIZON 시간 수요 예측 (정규화 0~1)
            reserve_requirement: 필요 예비율 (예: 0.08)

        Returns:
            최적 출력 비율 딕셔너리 {'한울': 0.87, ...}
        """
        t0 = time.perf_counter()

        # 현재 출력 배열
        P0 = np.array([current_outputs.get(n, self._p_min[i]) for i, n in enumerate(PLANT_NAMES)])

        # 수요 예측 배열 (MW)
        demand_mw = np.array([
            d * YONGIN_SPEC['sim_max_gw'] * 1000.0
            for d in demand_forecast[:self.HORIZON]
        ])

        # 초기값: 현재 출력 반복
        P_init = np.tile(P0, self.HORIZON)

        # 변수 경계 (각 타임스텝 × N_PLANTS)
        lb = np.tile(self._p_min, self.HORIZON)
        ub = np.tile(self._p_max, self.HORIZON)
        bounds = Bounds(lb, ub)

        # 최적화 실행 (제약 조건은 비용 함수 패널티로 처리)
        result = minimize(
            fun=self._cost_function,
            x0=P_init,
            args=(demand_mw, reserve_requirement, P0),
            method='L-BFGS-B',
            bounds=list(zip(lb, ub)),
            options={'maxiter': 300, 'ftol': 1e-8, 'disp': False},
        )

        dt = time.perf_counter() - t0
        self._solve_count += 1

        if result.success:
            # Receding Horizon: 첫 번째 타임스텝만 적용
            P_opt = result.x[:N_PLANTS]
            solution = {
                name: float(np.clip(P_opt[i], self._p_min[i], self._p_max[i]))
                for i, name in enumerate(PLANT_NAMES)
            }
            logger.debug(
                "EMPC 풀이 성공 (%.1fms, iter=%d): %s",
                dt * 1000, result.nit,
                {k: f"{v:.3f}" for k, v in solution.items()}
            )
            self._last_solution = result.x
            return solution
        else:
            logger.warning("EMPC 최적화 실패: %s → 현재값 유지", result.message)
            # 실패 시 현재 출력값 반환 (안전 기본값)
            return {n: float(np.clip(P0[i], self._p_min[i], self._p_max[i]))
                    for i, n in enumerate(PLANT_NAMES)}

    def get_current_cost(self, outputs: dict[str, float]) -> float:
        """현재 출력 설정의 발전 비용 계산 (원/MWh 개념)"""
        total = 0.0
        for i, name in enumerate(PLANT_NAMES):
            p = outputs.get(name, self._p_min[i])
            p_mw = p * self._cap[i]
            cost = self._a[i] * p_mw ** 2 + self._b[i] * p_mw + self._c[i]
            total += cost
        return total

    # ── 내부 헬퍼 ────────────────────────────────────────────
    def _cost_function(
        self,
        P_flat: np.ndarray,
        demand_mw: np.ndarray,
        reserve_req: float,
        P_prev: np.ndarray,
    ) -> float:
        """목적 함수: 발전 비용 + 수급 불균형 패널티 + 혼잡 패널티"""
        total_cost = 0.0
        P_current = P_prev.copy()

        for k in range(self.HORIZON):
            P_k = P_flat[k * N_PLANTS: (k + 1) * N_PLANTS]

            # 1. 발전 비용 (2차 함수)
            P_mw = P_k * self._cap
            gen_cost = np.sum(self._a * P_mw ** 2 + self._b * P_mw + self._c)

            # 2. 수급 균형 패널티
            P_sent = P_mw * (1 - self._loss)
            supply = np.sum(P_sent)
            required = demand_mw[k] * (1 + reserve_req) if k < len(demand_mw) else demand_mw[-1] * (1 + reserve_req)
            balance_penalty = self.LAMBDA_BALANCE * (supply - required) ** 2

            # 3. 동서 계통 혼잡 패널티
            congestion_penalty = self.LAMBDA_CONGESTION * np.sum(self._congestion * P_mw)

            # 4. Ramping 패널티 (급격한 변화 억제)
            delta = np.abs(P_k - P_current)
            ramp_penalty = 100.0 * np.sum(np.maximum(0, delta - self._ramp))

            total_cost += gen_cost + balance_penalty + congestion_penalty + ramp_penalty
            P_current = P_k

        return total_cost

    def _build_constraints(
        self,
        P0: np.ndarray,
        demand_mw: np.ndarray,
        reserve_req: float,
    ) -> list:
        """
        SLSQP 제약 조건: 첫 번째 타임스텝 수급 균형만 명시적 제약.
        나머지는 목적 함수 패널티로 처리 (제약 수 최소화로 수렴성 향상).
        """
        d0 = demand_mw[0] if len(demand_mw) > 0 else 2550.0
        required = d0 * (1 + reserve_req)
        cap = self._cap.copy()
        loss = self._loss.copy()

        def supply_constraint_t0(P_flat: np.ndarray) -> float:
            P_k = P_flat[:N_PLANTS]
            P_mw = P_k * cap
            P_sent = np.sum(P_mw * (1.0 - loss))
            return P_sent - required

        return [{'type': 'ineq', 'fun': supply_constraint_t0}]


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    engine = EMPCEngine()

    current = {'한울': 0.87, '태안': 0.72, '보령': 0.65, '인천': 0.55, '울산': 0.48}
    demand_fc = [0.85] * 24

    print("=== EMPC 최적화 테스트 ===")
    result = engine.solve(current, demand_fc, reserve_requirement=0.08)
    print("최적 출력 비율:")
    for name, ratio in result.items():
        mw = ratio * PLANT_PROFILE[name]['capacity_mw']
        print(f"  {name}: {ratio:.3f} ({mw:.0f} MW)")

    cost = engine.get_current_cost(result)
    print(f"\n총 발전 비용: {cost:.1f}")
