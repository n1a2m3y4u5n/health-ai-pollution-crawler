"""
digital_twin.py — 물리 회로의 디지털 미러
GSI, PQI, 주파수 편차, 예비력 실시간 계산
"""

import logging
import math
import threading
from typing import Optional
from config import (
    PLANT_PROFILE, PLANT_NAMES, YONGIN_SPEC,
    ISLAND_GRID_INERTIA_H, NOMINAL_FREQUENCY_HZ, OLD_RESERVE_RATIO,
)

logger = logging.getLogger(__name__)


class SmartGridDigitalTwin:
    """
    물리 회로의 디지털 미러.

    동기화 대상:
      - 각 채널 PWM 명령값 vs ACS712 실측값
      - 송전 손실 후 용인 도달 전력
      - 계통 안정도 지수 (GSI)
      - 회전예비력 현황

    한국 섬계통 주파수 모델:
      df/dt = (P_supply - P_demand) / (2 × H × S_base)
      H = 3.9초, S_base = 총 설비용량
    """

    # 전체 설비 용량 합 (MW)
    _TOTAL_CAPACITY_MW: float = sum(
        p['capacity_mw'] for p in PLANT_PROFILE.values()
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frequency_hz: float = NOMINAL_FREQUENCY_HZ
        self._state: dict = self._zero_state()
        logger.info("SmartGridDigitalTwin 초기화 완료")

    # ── 공개 API ─────────────────────────────────────────────
    def update(
        self,
        plant_outputs: dict[str, float],
        yongin_demand: float,
        sensor_data: Optional[dict[str, float]] = None,
    ) -> None:
        """
        매 제어 루프(1초)마다 호출.

        Args:
            plant_outputs: 발전소별 출력 비율 (0~1)
            yongin_demand: 용인 수요 (정규화 0~1)
            sensor_data: Arduino 실측 전류 (암페어, 선택)
        """
        # 1. 송전 손실 후 공급 계산
        supply_mw = 0.0
        tx_losses: dict[str, float] = {}
        plant_mw: dict[str, float] = {}

        for name in PLANT_NAMES:
            profile = PLANT_PROFILE[name]
            ratio = plant_outputs.get(name, profile['p_min_ratio'])
            raw_mw = ratio * profile['capacity_mw']
            loss_mw = raw_mw * profile['tx_loss_ratio']
            sent_mw = raw_mw - loss_mw
            plant_mw[name] = raw_mw
            tx_losses[name] = loss_mw
            supply_mw += sent_mw

        # 2. 용인 수요 MW 변환
        demand_mw = yongin_demand * YONGIN_SPEC['sim_max_gw'] * 1000.0

        # 3. 예비율
        total_gen_mw = sum(plant_mw.values())
        reserve_mw = supply_mw - demand_mw
        reserve_ratio = reserve_mw / demand_mw if demand_mw > 0 else 0.0

        # 4. 주파수 편차 계산 (섬계통 관성 모델)
        power_imbalance_pu = (supply_mw - demand_mw) / self._TOTAL_CAPACITY_MW
        df_dt = power_imbalance_pu / (2.0 * ISLAND_GRID_INERTIA_H)
        # 1초 적분 (제어 루프 주기)
        self._frequency_hz = NOMINAL_FREQUENCY_HZ + df_dt * 1.0
        self._frequency_hz = max(58.0, min(62.0, self._frequency_hz))

        # 5. GSI (Grid Stability Index)
        balance_ratio = supply_mw / demand_mw if demand_mw > 0 else 1.0
        freq_dev = abs(self._frequency_hz - NOMINAL_FREQUENCY_HZ) / NOMINAL_FREQUENCY_HZ
        gsi = 0.5 * balance_ratio + 0.3 * (1 - freq_dev * 10) + 0.2 * max(0, reserve_ratio)
        gsi = max(0.0, min(1.0, gsi))

        # 6. PQI (Power Quality Index)
        # 실제 전력망: 공급 >= 수요면 발전기 자동 조절 → PQI 정상(1.0)
        # 공급 부족 시에만 PQI 저하 (전압 강하 반영)
        if demand_mw <= 0:
            pqi = 1.0
        elif supply_mw >= demand_mw * 0.99:
            # 공급 충분 → PQI 우수 (주파수 편차만 반영)
            freq_penalty = min(0.01, abs(self._frequency_hz - NOMINAL_FREQUENCY_HZ) * 0.002)
            pqi = 1.0 - freq_penalty
        else:
            # 공급 부족 → PQI = 공급/수요 비율 (선형 저하)
            pqi = supply_mw / demand_mw
        pqi = max(0.0, min(1.0, pqi))

        if pqi < YONGIN_SPEC['pqi_threshold']:
            logger.warning("PQI 임계값 미달: %.4f < %.3f (반도체 공정 품질 경보)",
                           pqi, YONGIN_SPEC['pqi_threshold'])

        with self._lock:
            self._state = {
                'gsi': gsi,
                'frequency_hz': self._frequency_hz,
                'pqi': pqi,
                'supply_mw': supply_mw,
                'demand_mw': demand_mw,
                'reserve_ratio': reserve_ratio,
                'reserve_mw': reserve_mw,
                'plant_outputs': dict(plant_outputs),
                'plant_mw': plant_mw,
                'transmission_losses': tx_losses,
                'smart_reserve_ratio': max(0.05, min(0.08, reserve_ratio)),
                'old_reserve_ratio': OLD_RESERVE_RATIO,
                'saved_reserve_mw': max(0.0, (OLD_RESERVE_RATIO - max(0.05, min(0.08, reserve_ratio))) * demand_mw),
            }

        logger.debug(
            "디지털 트윈 업데이트: GSI=%.3f, freq=%.2fHz, PQI=%.4f, 예비율=%.1f%%",
            gsi, self._frequency_hz, pqi, reserve_ratio * 100
        )

    def get_state(self) -> dict:
        """
        현재 상태 스냅샷 반환.
        딕셔너리 키: gsi, frequency_hz, pqi, supply_mw, demand_mw,
                     reserve_ratio, plant_outputs, transmission_losses,
                     smart_reserve_ratio, saved_reserve_mw
        """
        with self._lock:
            return dict(self._state)

    # ── 내부 헬퍼 ────────────────────────────────────────────
    @staticmethod
    def _zero_state() -> dict:
        return {
            'gsi': 0.5,
            'frequency_hz': NOMINAL_FREQUENCY_HZ,
            'pqi': 1.0,
            'supply_mw': 0.0,
            'demand_mw': 0.0,
            'reserve_ratio': 0.0,
            'reserve_mw': 0.0,
            'plant_outputs': {name: PLANT_PROFILE[name]['p_min_ratio'] for name in PLANT_NAMES},
            'plant_mw': {name: 0.0 for name in PLANT_NAMES},
            'transmission_losses': {name: 0.0 for name in PLANT_NAMES},
            'smart_reserve_ratio': 0.08,
            'old_reserve_ratio': OLD_RESERVE_RATIO,
            'saved_reserve_mw': 0.0,
        }


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    twin = SmartGridDigitalTwin()

    outputs = {'한울': 0.87, '태안': 0.72, '보령': 0.65, '인천': 0.55, '울산': 0.48}
    twin.update(outputs, yongin_demand=0.85)

    state = twin.get_state()
    print("=== 디지털 트윈 상태 ===")
    for k, v in state.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        elif isinstance(v, dict):
            print(f"  {k}: {{{', '.join(f'{n}:{val:.3f}' for n,val in v.items())}}}")
        else:
            print(f"  {k}: {v}")
