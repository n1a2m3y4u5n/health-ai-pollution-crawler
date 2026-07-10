"""
yongin_load_model.py — 용인 반도체 클러스터 전력 수요 시뮬레이터
반도체 팹 특성 기반 수요 모델 (베이스로드 + 사이클 + 계절 변동)
"""

import logging
import math
import random
from config import YONGIN_SPEC

logger = logging.getLogger(__name__)

# 수요 구성 진폭 상수
_A_LOT = 0.05        # 웨이퍼 로트 사이클 (±5%)
_A_HVAC = 0.02       # 클린룸 HVAC (±2%)
_A_SEASONAL = 0.04   # 계절 변동 (±4%)
_A_NOISE = 0.005     # 랜덤 노이즈 (±0.5%)


class YonginLoadModel:
    """
    용인 반도체 클러스터 전력 수요 시뮬레이터.

    수요 구성:
      1. 베이스로드 85% — 클린룸 24/7 + 초순수 시스템
      2. 웨이퍼 로트 사이클 ±5% — 24시간 주기
      3. 클린룸 HVAC ±2% — 2시간 주기 (온도/습도 제어)
      4. 계절 변동 ±4% — 여름 냉방 부하
      5. 정기 유지보수 -10% — 주 1회 4시간 (월~목 00~04시)
      6. 랜덤 노이즈 ±0.5%
    """

    def __init__(self) -> None:
        self._ups_prev: float = YONGIN_SPEC['baseload_ratio']
        self._alpha: float = YONGIN_SPEC['ups_buffer_alpha']
        self._max_mw: float = YONGIN_SPEC['sim_max_gw'] * 1000.0
        logger.info("YonginLoadModel 초기화 완료 (최대 %.0f MW)", self._max_mw)

    # ── 내부 계산 ────────────────────────────────────────────
    def _maintenance_factor(self, t_hours: float) -> float:
        """정기 유지보수 -10% 적용 여부 판단 (주 1회, 00~04시)"""
        hour_of_day = t_hours % 24
        day_of_week = int(t_hours / 24) % 7   # 0=월, 6=일
        if day_of_week <= 3 and 0 <= hour_of_day < 4:
            return -0.10
        return 0.0

    def _raw_demand(self, t_hours: float) -> float:
        """정규화된 원시 수요값 계산 (UPS 버퍼 미적용)"""
        t_day = t_hours / 24.0

        # 각 구성 요소
        baseload = YONGIN_SPEC['baseload_ratio']
        lot_cycle = _A_LOT * math.sin(2 * math.pi / 24 * t_hours)
        hvac_cycle = _A_HVAC * math.sin(2 * math.pi / 2 * t_hours + math.pi / 4)
        seasonal = _A_SEASONAL * math.sin(2 * math.pi / 365 * t_day - math.pi / 2)
        maintenance = self._maintenance_factor(t_hours)
        noise = random.gauss(0, _A_NOISE)

        raw = baseload + lot_cycle + hvac_cycle + seasonal + maintenance + noise
        return max(0.1, min(1.0, raw))

    # ── 공개 API ─────────────────────────────────────────────
    def get_demand(self, t_hours: float) -> float:
        """
        현재 시각의 정규화 수요 반환 (0~1).
        UPS 버퍼 효과 적용:
          P_actual(t) = α×P_raw(t) + (1-α)×P_actual(t-1)
        """
        raw = self._raw_demand(t_hours)
        smoothed = self._alpha * raw + (1 - self._alpha) * self._ups_prev
        self._ups_prev = smoothed
        return smoothed

    def get_demand_mw(self, t_hours: float) -> float:
        """MW 단위 수요 반환"""
        return self.get_demand(t_hours) * self._max_mw

    def get_forecast(self, t_hours: float, horizon_hours: int = 24) -> list[float]:
        """
        향후 horizon_hours 수요 예측 (EMPC 입력용).
        반환: 정규화 수요값 리스트 (길이=horizon_hours)
        노이즈 없이 결정론적 예측 (UPS 평균 효과만 반영)
        """
        forecast = []
        ups_sim = self._ups_prev

        for h in range(horizon_hours):
            t = t_hours + h
            t_day = t / 24.0

            baseload = YONGIN_SPEC['baseload_ratio']
            lot_cycle = _A_LOT * math.sin(2 * math.pi / 24 * t)
            hvac_cycle = _A_HVAC * math.sin(2 * math.pi / 2 * t + math.pi / 4)
            seasonal = _A_SEASONAL * math.sin(2 * math.pi / 365 * t_day - math.pi / 2)
            maintenance = self._maintenance_factor(t)

            raw = max(0.1, min(1.0, baseload + lot_cycle + hvac_cycle + seasonal + maintenance))
            smoothed = self._alpha * raw + (1 - self._alpha) * ups_sim
            ups_sim = smoothed
            forecast.append(smoothed)

        return forecast


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    model = YonginLoadModel()

    print("=== 용인 부하 모델 24시간 테스트 ===")
    print(f"{'시각':>6} {'수요(정규화)':>12} {'수요(MW)':>10}")
    for h in range(0, 25, 3):
        d = model.get_demand(float(h))
        mw = model.get_demand_mw(float(h))
        print(f"{h:>5}h  {d:>12.4f}  {mw:>10.1f}")

    print("\n=== 24시간 예측 (현재=0h) ===")
    model2 = YonginLoadModel()
    fc = model2.get_forecast(0.0, 24)
    print(f"평균: {sum(fc)/len(fc):.4f}, 최대: {max(fc):.4f}, 최소: {min(fc):.4f}")
