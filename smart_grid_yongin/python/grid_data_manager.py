"""
grid_data_manager.py — KPX API(5분) + Kalman Filter(1초) 통합 데이터 관리자
API 갱신 공백 기간에는 Kalman predict()로 추정값 유지
"""

import logging
import threading
import time
from typing import Optional
from config import PLANT_PROFILE, PLANT_NAMES, KALMAN_R, CHANNEL_MAX_CURRENT

logger = logging.getLogger(__name__)


class KalmanFilter1D:
    """1차원 Kalman Filter (발전소별 독립 실행)"""

    def __init__(self, Q: float, R: float, x0: float = 0.5) -> None:
        self.x = x0    # 상태 추정값 (출력 비율 0~1)
        self.P = 1.0   # 오차 공분산
        self.Q = Q     # 시스템 노이즈
        self.R = R     # 측정 노이즈
        self.A = 1.0   # 상태 전이 (단위 시간)
        self.H = 1.0   # 측정 행렬

    def predict(self) -> float:
        """사전 추정 (측정 없이 상태 전파)"""
        self.x = self.A * self.x
        self.P = self.A * self.P * self.A + self.Q
        return self.x

    def update(self, z: float) -> float:
        """측정값 z로 사후 추정"""
        # 칼만 이득
        K = self.P * self.H / (self.H * self.P * self.H + self.R)
        # 상태 업데이트
        self.x = self.x + K * (z - self.H * self.x)
        # 공분산 업데이트
        self.P = (1 - K * self.H) * self.P
        return self.x


class GridDataManager:
    """
    KPX API(5분) + Kalman Filter(1초) 통합 데이터 관리자.

    5분 공백 처리 전략:
      API 수신 시: Kalman update() (실측값으로 보정)
      API 없는 사이: Kalman predict() (모델 기반 추정)

    Arduino 센서 데이터 수신 시에도 Kalman update() 적용.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # 발전소별 독립 Kalman Filter 초기화
        self._filters: dict[str, KalmanFilter1D] = {}
        for name in PLANT_NAMES:
            profile = PLANT_PROFILE[name]
            q = profile['kalman_Q']
            x0 = (profile['p_min_ratio'] + profile['p_max_ratio']) / 2.0
            self._filters[name] = KalmanFilter1D(Q=q, R=KALMAN_R, x0=x0)

        # 현재 추정값 캐시
        self._estimates: dict[str, float] = {
            name: PLANT_PROFILE[name]['p_min_ratio'] for name in PLANT_NAMES
        }
        self._last_update_ts: float = time.time()
        logger.info("GridDataManager 초기화 완료")

    # ── 공개 API ─────────────────────────────────────────────
    def get_current_estimates(self) -> dict[str, float]:
        """
        항상 최신 추정값 반환 (API 있든 없든).
        반환 형식: {'한울': 0.87, '태안': 0.71, ...} (0~1 정규화)
        """
        # API 공백이 너무 길면 predict 한 번 더 실행
        elapsed = time.time() - self._last_update_ts
        if elapsed > 60.0:
            self._run_predict_step()

        with self._lock:
            return dict(self._estimates)

    def on_api_update(self, api_data: dict) -> None:
        """5분마다 KPX API 새 데이터 도착 시 Kalman update 실행"""
        with self._lock:
            for name in PLANT_NAMES:
                measured = api_data.get(name)
                if measured is not None:
                    profile = PLANT_PROFILE[name]
                    z = max(profile['p_min_ratio'], min(1.0, float(measured)))
                    self._estimates[name] = self._filters[name].update(z)
                else:
                    # 측정값 없으면 predict만
                    self._estimates[name] = self._filters[name].predict()

            self._last_update_ts = time.time()
            logger.debug("API 업데이트 적용: %s",
                         {k: f"{v:.3f}" for k, v in self._estimates.items()})

    def on_arduino_sensor(self, sensor_data: dict) -> None:
        """
        100ms마다 Arduino ACS712 데이터 수신 시 Kalman update 실행.
        sensor_data: {'한울': 2.3, '태안': 1.8, ...} (암페어)
        암페어 → 출력 비율 변환: ratio = current / max_current_ch
        """
        with self._lock:
            for name in PLANT_NAMES:
                current_a = sensor_data.get(name)
                if current_a is not None:
                    max_a = CHANNEL_MAX_CURRENT[name]
                    ratio = float(current_a) / max_a if max_a > 0 else 0.0
                    profile = PLANT_PROFILE[name]
                    ratio = max(0.0, min(1.0, ratio))
                    self._estimates[name] = self._filters[name].update(ratio)
                else:
                    self._estimates[name] = self._filters[name].predict()

            self._last_update_ts = time.time()

    def run_predict_all(self) -> None:
        """모든 채널 predict 한 타임스텝 진행 (제어 루프 호출용)"""
        with self._lock:
            for name in PLANT_NAMES:
                self._estimates[name] = self._filters[name].predict()
            self._last_update_ts = time.time()

    # ── 내부 헬퍼 ────────────────────────────────────────────
    def _run_predict_step(self) -> None:
        with self._lock:
            for name in PLANT_NAMES:
                self._estimates[name] = self._filters[name].predict()
            self._last_update_ts = time.time()


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    mgr = GridDataManager()

    print("=== GridDataManager 테스트 ===")
    print("초기 추정값:", {k: f"{v:.3f}" for k, v in mgr.get_current_estimates().items()})

    # API 업데이트 시뮬레이션
    mock_api = {'한울': 0.87, '태안': 0.72, '보령': 0.65, '인천': 0.55, '울산': 0.48}
    mgr.on_api_update(mock_api)
    print("API 업데이트 후:", {k: f"{v:.3f}" for k, v in mgr.get_current_estimates().items()})

    # Arduino 센서 시뮬레이션
    from config import CHANNEL_MAX_CURRENT
    mock_sensor = {
        name: CHANNEL_MAX_CURRENT[name] * 0.80 for name in PLANT_NAMES
    }
    mgr.on_arduino_sensor(mock_sensor)
    print("센서 업데이트 후:", {k: f"{v:.3f}" for k, v in mgr.get_current_estimates().items()})
