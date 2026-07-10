"""
kpx_api.py — 한국전력거래소 공공데이터 API 클라이언트
API 없을 때 시뮬레이션 데이터로 자동 fallback
"""

import logging
import math
import time
import random
from typing import Optional
import requests
from config import KPX_API_KEY, PLANT_PROFILE, NATIONAL_CAPACITY_MW, PLANT_NAMES

logger = logging.getLogger(__name__)

# KPX API 엔드포인트
_BASE_URL = "https://apis.data.go.kr/B500001/powerStation"
_SUPPLY_ENDPOINT = "/realTimeGenerationCoal"   # 현재전력수급현황
_FUEL_ENDPOINT = "/realTimeGenerationCoal"     # 발전원별 발전량


class KPXApiClient:
    """
    한국전력거래소 Open API 클라이언트.

    사용 API:
      1. 현재전력수급현황 (data.go.kr/data/15056640)
         갱신 5분, 총수요(MW)/공급능력(MW)/예비율(%)
      2. 발전원별 발전량 (data.go.kr/data/15113384)
         갱신 5분, 원자력/유연탄/가스 MW

    개별 발전소 실시간 데이터는 비공개이므로,
    연료원 총량에 설비용량 비율을 곱해 각 발전소 추정 출력 계산.

    API 키 없을 때: simulate_api_data()로 fallback.
    API 에러 시: 마지막 성공 데이터 캐싱 후 반환.
    """

    def __init__(self, service_key: Optional[str] = None) -> None:
        self._key = service_key or KPX_API_KEY
        self._last_supply: Optional[dict] = None
        self._last_fuel: Optional[dict] = None
        self._last_success_ts: float = 0.0
        self._sim_start_ts: float = time.time()
        logger.info("KPXApiClient 초기화 (키: %s...)", self._key[:8] if self._key else 'None')

    # ── API 호출 ──────────────────────────────────────────────
    def fetch_realtime_supply(self) -> dict:
        """5분마다 호출. 실패 시 시뮬레이션 데이터 반환."""
        try:
            params = {
                'serviceKey': self._key,
                'numOfRows': 1,
                'pageNo': 1,
                'resultType': 'json',
            }
            resp = requests.get(
                f"{_BASE_URL}/realTimePowerSupplyDemand",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if not items:
                raise ValueError("API 응답에 데이터 없음")

            item = items[0] if isinstance(items, list) else items
            result = {
                'total_demand_mw': float(item.get('currPwr', 0)),
                'supply_capacity_mw': float(item.get('suppAbility', 0)),
                'reserve_ratio': float(item.get('rsvPwr', 0)) / 100.0,
                'source': 'api',
                'timestamp': time.time(),
            }
            self._last_supply = result
            self._last_success_ts = time.time()
            logger.debug("KPX 수급현황 수신: 수요=%.0f MW, 예비율=%.1f%%",
                         result['total_demand_mw'], result['reserve_ratio'] * 100)
            return result

        except Exception as exc:
            logger.warning("KPX 수급현황 API 실패: %s → 시뮬레이션 사용", exc)
            sim = self.simulate_api_data(self._elapsed_hours())
            sim['source'] = 'simulation'
            return sim

    def fetch_generation_by_fuel(self) -> dict:
        """연료원별 발전량 (MW) 반환."""
        try:
            params = {
                'serviceKey': self._key,
                'numOfRows': 1,
                'pageNo': 1,
                'resultType': 'json',
            }
            resp = requests.get(
                f"{_BASE_URL}/realTimeFuelSource",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if not items:
                raise ValueError("API 응답에 데이터 없음")

            item = items[0] if isinstance(items, list) else items
            result = {
                'nuclear_mw': float(item.get('nuclearPwr', 0)),
                'coal_mw': float(item.get('coalPwr', 0)),
                'lng_mw': float(item.get('lngPwr', 0)),
                'total_mw': float(item.get('totalPwr', 0)),
                'source': 'api',
                'timestamp': time.time(),
            }
            self._last_fuel = result
            logger.debug("KPX 연료원별 수신: 원전=%.0f, 석탄=%.0f, LNG=%.0f MW",
                         result['nuclear_mw'], result['coal_mw'], result['lng_mw'])
            return result

        except Exception as exc:
            logger.warning("KPX 연료원 API 실패: %s → 시뮬레이션 사용", exc)
            return self._simulate_fuel_by_hour(self._elapsed_hours())

    def get_plant_estimates(self) -> dict:
        """
        5개 발전소 추정 출력 비율 (0~1) 반환.
        연료원 총량 × (발전소 설비용량 / 전국 설비용량)
        """
        fuel = self.fetch_generation_by_fuel()

        estimates: dict[str, float] = {}
        for name in PLANT_NAMES:
            profile = PLANT_PROFILE[name]
            ftype = profile['fuel_type']

            if ftype == 'nuclear':
                total_fuel_mw = fuel.get('nuclear_mw', 0)
                national_cap = NATIONAL_CAPACITY_MW['nuclear']
            elif ftype == 'coal':
                total_fuel_mw = fuel.get('coal_mw', 0)
                national_cap = NATIONAL_CAPACITY_MW['coal']
            else:  # lng
                total_fuel_mw = fuel.get('lng_mw', 0)
                national_cap = NATIONAL_CAPACITY_MW['lng']

            # 발전소 추정 출력 (MW) = 연료 총량 × (발전소 용량 / 전국 용량)
            plant_mw = total_fuel_mw * (profile['capacity_mw'] / national_cap)
            # 정규화 (0~1)
            ratio = plant_mw / profile['capacity_mw']
            estimates[name] = max(profile['p_min_ratio'], min(1.0, ratio))

        logger.debug("발전소 추정 출력: %s", {k: f"{v:.3f}" for k, v in estimates.items()})
        return estimates

    # ── 시뮬레이션 ───────────────────────────────────────────
    def simulate_api_data(self, t_hours: float) -> dict:
        """
        Tier 1 시뮬레이션 데이터 생성 (API 없을 때 fallback).
        연료별 특성 반영:
          원자력: 일정 (이용률 87%), 정기 예방정비 시 0
          석탄: 야간 -8%, 주말 -5%, 계절 변동 ±6%
          LNG: 첨두시간(09~21시) +28%, 여름·겨울 추가 +10%
        """
        fuel = self._simulate_fuel_by_hour(t_hours)
        hour = t_hours % 24

        # 전국 총수요 추정 (가중 합산)
        total_demand = (
            fuel['nuclear_mw'] + fuel['coal_mw'] + fuel['lng_mw']
        ) * 1.05   # 재생에너지·기타 ~5% 추가

        supply_capacity = total_demand * 1.12   # 예비력 포함

        return {
            'total_demand_mw': total_demand,
            'supply_capacity_mw': supply_capacity,
            'reserve_ratio': 0.12 + 0.03 * math.sin(2 * math.pi / 24 * hour),
            'nuclear_mw': fuel['nuclear_mw'],
            'coal_mw': fuel['coal_mw'],
            'lng_mw': fuel['lng_mw'],
            'source': 'simulation',
            'timestamp': time.time(),
        }

    def _simulate_fuel_by_hour(self, t_hours: float) -> dict:
        """연료원별 시뮬레이션 데이터 (시간대별 특성 반영)"""
        hour = t_hours % 24
        day_of_week = int(t_hours / 24) % 7
        t_day = t_hours / 24.0
        is_weekend = day_of_week >= 5

        # 원자력: 이용률 87%, 계절·시간 무관
        nuclear_base = NATIONAL_CAPACITY_MW['nuclear'] * 0.87
        nuclear_mw = nuclear_base * (0.98 + 0.02 * random.gauss(0, 0.01))

        # 석탄: 야간 -8%, 주말 -5%, 계절 변동 ±6%
        coal_base = NATIONAL_CAPACITY_MW['coal'] * 0.65
        coal_night = -0.08 if (hour < 6 or hour >= 22) else 0.0
        coal_weekend = -0.05 if is_weekend else 0.0
        coal_seasonal = 0.06 * math.sin(2 * math.pi / 365 * t_day)
        coal_mw = coal_base * (1 + coal_night + coal_weekend + coal_seasonal)

        # LNG: 첨두시간 +28%, 여름/겨울 +10%
        lng_base = NATIONAL_CAPACITY_MW['lng'] * 0.45
        lng_peak = 0.28 if (9 <= hour < 21) else 0.0
        month = (t_day % 365) / 30.4
        lng_season = 0.10 if (month < 2 or month > 10) else 0.0
        lng_mw = lng_base * (1 + lng_peak + lng_season)

        return {
            'nuclear_mw': max(0, nuclear_mw),
            'coal_mw': max(0, coal_mw),
            'lng_mw': max(0, lng_mw),
            'total_mw': nuclear_mw + coal_mw + lng_mw,
        }

    def _elapsed_hours(self) -> float:
        """시스템 시작 이후 경과 시간 (시간 단위)"""
        return (time.time() - self._sim_start_ts) / 3600.0


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    client = KPXApiClient()

    print("=== KPX API 클라이언트 테스트 ===")
    estimates = client.get_plant_estimates()
    print("\n발전소 추정 출력 비율:")
    for name, ratio in estimates.items():
        mw = ratio * PLANT_PROFILE[name]['capacity_mw']
        print(f"  {name}: {ratio:.3f} ({mw:.0f} MW)")
