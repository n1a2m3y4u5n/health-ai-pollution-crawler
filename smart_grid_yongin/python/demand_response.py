"""
demand_response.py — 한국 수요반응(DR) 프로그램 시뮬레이터
전력시장 운영규칙 기반 3가지 DR 유형 구현
"""

import logging
import time
from config import YONGIN_SPEC

logger = logging.getLogger(__name__)

# DR 유형별 파라미터
_DR_PARAMS = {
    'ENC': {  # 긴급 감축형
        'curtail_ratio': 0.10,
        'duration_sec': 900,   # 15분
        'min_delay_sec': 120,  # 최소 2분 지연 (UPS 버퍼)
    },
    'FRC': {  # 주파수 감응형
        'curtail_ratio': 0.05,
        'duration_sec': 300,   # 5분
        'min_delay_sec': 0,
    },
    'PBDR': {  # 계획 감축형
        'curtail_ratio': 0.03,
        'duration_sec': 3600,  # 60분
        'min_delay_sec': 120,
    },
}


class KoreanDemandResponse:
    """
    한국 수요반응(DR) 프로그램 시뮬레이터.

    DR 유형:
      ENC  (긴급 감축형): 예비율 < 8% 또는 GSI < 0.80 → 10% 즉시 감축
      FRC  (주파수 감응형): |f - 60Hz| > 0.2Hz → 5% 자동 감축
      PBDR (계획 감축형): SMP > 200원/kWh → 3% 감축

    용인 반도체 클러스터 특성:
      - UPS 버퍼로 즉각 감축 불가 (최소 2분 지연)
      - UPS 평탄화: α=0.15
    """

    def __init__(self) -> None:
        self._alpha = YONGIN_SPEC['ups_buffer_alpha']
        self._ups_demand: float = YONGIN_SPEC['baseload_ratio'] * YONGIN_SPEC['sim_max_gw'] * 1000.0
        self._active_dr: dict[str, dict] = {}   # dr_type → {end_ts, curtail_ratio}
        self._event_log: list[dict] = []
        logger.info("KoreanDemandResponse 초기화")

    # ── 공개 API ─────────────────────────────────────────────
    def check_and_dispatch(
        self,
        gsi: float,
        reserve_ratio: float,
        frequency_hz: float,
        smp: float,
    ) -> dict:
        """
        DR 발동 조건 검사 및 디스패치.

        Args:
            gsi: 계통 안정도 지수 (0~1)
            reserve_ratio: 공급 예비율
            frequency_hz: 현재 계통 주파수 (Hz)
            smp: 계통 한계 가격 (원/kWh)

        Returns:
            {
              'active_dr': str | None,
              'curtail_ratio': float,
              'event_log': list,
            }
        """
        now = time.time()
        self._cleanup_expired(now)

        active_type = None
        total_curtail = 0.0

        # 1. ENC 발동 조건 검사
        if reserve_ratio < 0.08 or gsi < 0.80:
            if 'ENC' not in self._active_dr:
                self._dispatch_dr('ENC', now)
                logger.warning("ENC DR 발동: 예비율=%.1f%%, GSI=%.3f", reserve_ratio * 100, gsi)

        # 2. FRC 발동 조건 검사
        if abs(frequency_hz - 60.0) > 0.2:
            if 'FRC' not in self._active_dr:
                self._dispatch_dr('FRC', now)
                logger.warning("FRC DR 발동: 주파수=%.3f Hz (편차=%.3f Hz)",
                                frequency_hz, abs(frequency_hz - 60.0))

        # 3. PBDR 발동 조건 검사
        if smp > 200.0:
            if 'PBDR' not in self._active_dr:
                self._dispatch_dr('PBDR', now)
                logger.info("PBDR DR 발동: SMP=%.1f 원/kWh", smp)

        # 활성 DR 합산 (중복 최대 적용)
        if self._active_dr:
            total_curtail = max(v['curtail_ratio'] for v in self._active_dr.values())
            active_type = max(self._active_dr.keys(), key=lambda k: _DR_PARAMS[k]['curtail_ratio'])

        return {
            'active_dr': active_type,
            'curtail_ratio': total_curtail,
            'active_types': list(self._active_dr.keys()),
            'event_log': list(self._event_log[-10:]),   # 최근 10개
        }

    def apply_ups_buffer(self, raw_demand_mw: float) -> float:
        """
        UPS 버퍼 효과로 수요 평탄화.
        P_actual(t) = α×P_raw(t) + (1-α)×P_actual(t-1)
        """
        smoothed = self._alpha * raw_demand_mw + (1 - self._alpha) * self._ups_demand
        self._ups_demand = smoothed
        return smoothed

    def apply_curtailment(self, demand_mw: float, curtail_ratio: float) -> float:
        """DR 감축 비율 적용 후 실효 수요 반환"""
        return demand_mw * (1.0 - curtail_ratio)

    # ── 내부 헬퍼 ────────────────────────────────────────────
    def _dispatch_dr(self, dr_type: str, now: float) -> None:
        params = _DR_PARAMS[dr_type]
        self._active_dr[dr_type] = {
            'start_ts': now,
            'end_ts': now + params['duration_sec'],
            'curtail_ratio': params['curtail_ratio'],
        }
        event = {
            'ts': now,
            'type': dr_type,
            'action': 'dispatch',
            'curtail_pct': params['curtail_ratio'] * 100,
        }
        self._event_log.append(event)

    def _cleanup_expired(self, now: float) -> None:
        """만료된 DR 이벤트 제거"""
        expired = [k for k, v in self._active_dr.items() if v['end_ts'] < now]
        for k in expired:
            del self._active_dr[k]
            self._event_log.append({'ts': now, 'type': k, 'action': 'expired'})
            logger.info("DR %s 만료", k)


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    dr = KoreanDemandResponse()

    print("=== 수요반응 시뮬레이터 테스트 ===")

    # 정상 상태
    result = dr.check_and_dispatch(gsi=0.90, reserve_ratio=0.12, frequency_hz=60.01, smp=150.0)
    print(f"정상 상태: 활성 DR={result['active_dr']}, 감축률={result['curtail_ratio']*100:.1f}%")

    # 긴급 감축 발동
    result = dr.check_and_dispatch(gsi=0.75, reserve_ratio=0.06, frequency_hz=59.8, smp=150.0)
    print(f"긴급 상태: 활성 DR={result['active_dr']}, 감축률={result['curtail_ratio']*100:.1f}%")
    print(f"활성 유형: {result['active_types']}")

    # UPS 버퍼 테스트
    raw = 2550.0
    smoothed = dr.apply_ups_buffer(raw)
    print(f"\nUPS 버퍼: 원시 수요={raw:.0f} MW → 평탄화={smoothed:.0f} MW")
