"""
monte_carlo_reserve.py — Monte Carlo 시뮬레이션으로 필요 예비력 계산
목표 신뢰도: 99.99% (LOLP < 0.0001)
"""

import logging
import random
import math
from config import PLANT_PROFILE, PLANT_NAMES, OLD_RESERVE_RATIO, YONGIN_SPEC

logger = logging.getLogger(__name__)

# 발전소 강제 정지 확률
_OUTAGE_PROB = {
    'nuclear': 0.005,
    'coal': 0.015,
    'lng': 0.020,
}

# 송전선 고장 확률
_TX_FAULT_PROB = 0.002

# 부하 예측 오차 표준편차
_LOAD_ERROR_SIGMA = 0.03


class MonteCarloReserveCalculator:
    """
    Monte Carlo 시뮬레이션으로 동적 예비력 계산.

    불확실성 원천:
      1. 부하 예측 오차: N(0, σ=0.03)
      2. 발전소 강제 정지: 연료별 확률
      3. 송전선 고장: p=0.002

    목표 신뢰도: 99.99% (LOLP < 0.0001)
    GSI가 높을수록 필요 예비력 감소 (스마트 그리드 이점)
    """

    N_SIMULATIONS = 10000
    TARGET_RELIABILITY = 0.9999

    def __init__(self) -> None:
        logger.info("MonteCarloReserveCalculator 초기화 (시뮬레이션 수=%d)", self.N_SIMULATIONS)

    def calculate(
        self,
        current_demand_mw: float,
        gsi: float,
    ) -> dict:
        """
        Monte Carlo로 필요 예비율 계산.

        Args:
            current_demand_mw: 현재 수요 (MW)
            gsi: 계통 안정도 지수 (0~1)

        Returns:
            {
              'required_reserve_ratio': float,
              'smart_reserve_ratio': float,
              'traditional_reserve_ratio': 0.15,
              'saved_ratio': float,
              'saved_mw': float,
              'risk_shortfall': float,
            }
        """
        shortfall_count = 0
        max_supply_list = []

        for _ in range(self.N_SIMULATIONS):
            # 1. 부하 예측 오차 시뮬레이션
            load_error = random.gauss(0, _LOAD_ERROR_SIGMA)
            simulated_demand = current_demand_mw * (1 + load_error)

            # 2. 각 발전소 가용 여부 시뮬레이션
            available_supply = 0.0
            for name in PLANT_NAMES:
                profile = PLANT_PROFILE[name]
                fuel = profile['fuel_type']
                outage_prob = _OUTAGE_PROB.get(fuel, 0.01)

                # 발전소 강제 정지 여부
                if random.random() < outage_prob:
                    continue  # 해당 발전소 탈락

                # 송전선 고장 여부
                if random.random() < _TX_FAULT_PROB:
                    continue

                # 정상 운전: p_min ~ p_max 사이 랜덤 출력
                ratio = random.uniform(profile['p_min_ratio'], profile['p_max_ratio'])
                raw_mw = ratio * profile['capacity_mw']
                sent_mw = raw_mw * (1 - profile['tx_loss_ratio'])
                available_supply += sent_mw

            max_supply_list.append(available_supply)

            # 공급 부족 판정
            if available_supply < simulated_demand:
                shortfall_count += 1

        # 통계 계산
        risk_shortfall = shortfall_count / self.N_SIMULATIONS

        # 99.99% 신뢰도를 위한 필요 공급 여유
        max_supply_array = sorted(max_supply_list)
        critical_idx = int((1 - self.TARGET_RELIABILITY) * self.N_SIMULATIONS)
        critical_supply = max_supply_array[max(0, critical_idx)]

        required_reserve = max(0.0, (current_demand_mw - critical_supply) / current_demand_mw)
        required_reserve = max(0.05, required_reserve)  # 최소 5% 예비율

        # GSI 반영: GSI가 높을수록 필요 예비력 감소
        # GSI=1.0 → 최소 5%, GSI=0.5 → 최대 8%
        gsi_factor = 1.0 - 0.3 * gsi
        smart_reserve = max(0.05, min(0.08, required_reserve * gsi_factor))

        # 절감량 계산
        saved_ratio = OLD_RESERVE_RATIO - smart_reserve
        saved_mw = saved_ratio * current_demand_mw

        result = {
            'required_reserve_ratio': required_reserve,
            'smart_reserve_ratio': smart_reserve,
            'traditional_reserve_ratio': OLD_RESERVE_RATIO,
            'saved_ratio': max(0.0, saved_ratio),
            'saved_mw': max(0.0, saved_mw),
            'risk_shortfall': risk_shortfall,
        }

        logger.debug(
            "Monte Carlo 결과: 기존=%.1f%%, 스마트=%.1f%%, 절감=%.0f MW, 위험도=%.4f%%",
            OLD_RESERVE_RATIO * 100, smart_reserve * 100,
            max(0.0, saved_mw), risk_shortfall * 100
        )
        return result


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    calc = MonteCarloReserveCalculator()

    print("=== Monte Carlo 예비력 계산 테스트 ===")
    result = calc.calculate(current_demand_mw=2550.0, gsi=0.85)

    print(f"필요 예비율 (Monte Carlo): {result['required_reserve_ratio']*100:.1f}%")
    print(f"스마트 예비율 (GSI 반영): {result['smart_reserve_ratio']*100:.1f}%")
    print(f"기존 고정 예비율:          {result['traditional_reserve_ratio']*100:.1f}%")
    print(f"절감 예비율:               {result['saved_ratio']*100:.1f}%")
    print(f"절감 전력:                 {result['saved_mw']:.0f} MW")
    print(f"공급 부족 위험:            {result['risk_shortfall']*100:.3f}%")
