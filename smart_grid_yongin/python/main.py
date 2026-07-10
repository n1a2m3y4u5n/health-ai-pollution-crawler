"""
main.py — 지능형 전력망 시스템 진입점
3개 루프 threading으로 동시 실행:
  루프 A (100ms): Arduino 통신
  루프 B (1초):   제어 루프 (EMPC + Q-Learning + DR)
  루프 C (5분):   KPX API 업데이트
"""

import argparse
import logging
import os
import sys
import threading
import time
from typing import Optional

# 경로 설정 (python/ 디렉토리 기준)
sys.path.insert(0, os.path.dirname(__file__))

from config import (
    PLANT_NAMES, PLANT_PROFILE, YONGIN_SPEC, SMPS_MAX_CURRENT,
    CONTROL_LOOP_INTERVAL_SEC, API_UPDATE_INTERVAL_SEC, ARDUINO_LOOP_MS,
)
from grid_data_manager import GridDataManager
from digital_twin import SmartGridDigitalTwin
from empc_engine import EMPCEngine
from q_learning_agent import QLearningAgent
from monte_carlo_reserve import MonteCarloReserveCalculator
from demand_response import KoreanDemandResponse
from yongin_load_model import YonginLoadModel
from serial_bridge import SerialBridge
from kpx_api import KPXApiClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('main')


class SmartGridSystem:
    """
    전체 시스템 통합 관리자.
    세 루프를 독립 스레드로 운영하며 공유 상태를 Lock으로 보호.
    """

    def __init__(self, simulate: bool = False, fault_plant: Optional[str] = None) -> None:
        self._simulate = simulate or os.environ.get('SIMULATE', '0') == '1'
        self._fault_plant = fault_plant
        self._running = False

        # 컴포넌트 초기화
        logger.info("=== 지능형 전력망 시스템 초기화 ===")
        self._load_model = YonginLoadModel()
        self._kpx_api = KPXApiClient()
        self._data_mgr = GridDataManager()
        self._twin = SmartGridDigitalTwin()
        self._empc = EMPCEngine()
        self._q_agent = QLearningAgent(load_pretrained=True)
        self._monte_carlo = MonteCarloReserveCalculator()
        self._dr = KoreanDemandResponse()
        self._serial = SerialBridge()

        # 공유 상태
        self._state_lock = threading.Lock()
        self._current_pwm: dict[str, int] = {
            n: PLANT_PROFILE[n]['pwm_max'] // 2 for n in PLANT_NAMES
        }
        self._current_outputs: dict[str, float] = {
            n: PLANT_PROFILE[n]['p_min_ratio'] for n in PLANT_NAMES
        }
        self._shared_state: dict = {}
        self._empc_cost_history: list[float] = []
        self._q_cost_history: list[float] = []

        # 시스템 시작 시각 (부하 모델 시간 기준)
        self._start_time = time.time()

        logger.info("초기화 완료 (시뮬레이션=%s, 고장시뮬레이션=%s)",
                    self._simulate, fault_plant or '없음')

    # ── 루프 A: Arduino 통신 (100ms) ─────────────────────────
    def _loop_arduino(self) -> None:
        logger.info("루프 A (Arduino 통신) 시작")
        while self._running:
            t0 = time.time()

            # 1. 센서 데이터 읽기
            sensor_data = self._serial.read_sensor_data()

            if sensor_data:
                # 2. Kalman Filter 업데이트
                self._data_mgr.on_arduino_sensor(sensor_data)

                # 3. Digital Twin 업데이트
                with self._state_lock:
                    outputs = dict(self._current_outputs)
                demand = self._load_model.get_demand(self._elapsed_hours())
                self._twin.update(outputs, demand, sensor_data)

            # 4. 현재 PWM 전송
            with self._state_lock:
                pwm = dict(self._current_pwm)
            self._serial.send_pwm_commands(pwm)

            # 100ms 주기 유지
            elapsed = time.time() - t0
            sleep_t = max(0.0, ARDUINO_LOOP_MS / 1000.0 - elapsed)
            time.sleep(sleep_t)

    # ── 루프 B: 제어 루프 (1초) ──────────────────────────────
    def _loop_control(self) -> None:
        logger.info("루프 B (제어 루프) 시작")
        prev_q_outputs = dict(self._current_outputs)
        prev_q_state_tuple = (0.85, 0.10, 12.0)

        while self._running:
            t0 = time.time()
            t_hours = self._elapsed_hours()

            # 1. 현재 추정값 + 수요
            estimates = self._data_mgr.get_current_estimates()
            demand_norm = self._load_model.get_demand(t_hours)
            demand_mw = demand_norm * YONGIN_SPEC['sim_max_gw'] * 1000.0

            # 2. 수요 예측 (EMPC 입력)
            demand_forecast = self._load_model.get_forecast(t_hours, horizon_hours=24)

            # 3. Monte Carlo 예비력 계산
            twin_state = self._twin.get_state()
            gsi = twin_state.get('gsi', 0.85)
            mc_result = self._monte_carlo.calculate(demand_mw, gsi)
            reserve_req = mc_result['smart_reserve_ratio']

            # 4. EMPC 최적 급전
            empc_outputs = self._empc.solve(estimates, demand_forecast, reserve_req)
            empc_cost = self._empc.get_current_cost(empc_outputs)

            # 5. Q-Learning 대안 계산 (비교용)
            q_state = (
                demand_norm,
                twin_state.get('reserve_ratio', 0.10),
                t_hours % 24,
            )
            q_outputs, q_action_idx = self._q_agent.get_action_from_current(q_state, prev_q_outputs)
            q_cost = self._empc.get_current_cost(q_outputs)

            # Q-Learning 업데이트
            reward = self._q_agent.compute_reward(twin_state, prev_q_outputs, q_outputs)
            self._q_agent.update(prev_q_state_tuple, q_action_idx, reward, q_state)
            prev_q_outputs = q_outputs
            prev_q_state_tuple = q_state

            # 6. DR 적용
            dr_result = self._dr.check_and_dispatch(
                gsi=gsi,
                reserve_ratio=twin_state.get('reserve_ratio', 0.10),
                frequency_hz=twin_state.get('frequency_hz', 60.0),
                smp=120.0,  # 실제로는 KPX API에서 수신
            )

            # DR 수요 감축 적용
            effective_demand = self._dr.apply_curtailment(
                demand_mw, dr_result['curtail_ratio']
            )

            # 7. 고장 시뮬레이션 처리
            final_outputs = dict(empc_outputs)
            if self._fault_plant and self._fault_plant in final_outputs:
                final_outputs[self._fault_plant] = 0.0
                logger.warning("고장 시뮬레이션: %s 출력 0으로 설정", self._fault_plant)
                # 나머지 채널에 재배분
                final_outputs = self._redistribute_on_fault(
                    self._fault_plant, final_outputs, demand_mw
                )

            # 8. PWM 계산 (출력 비율 → PWM 정수)
            new_pwm = self._outputs_to_pwm(final_outputs)

            # 9. 공유 상태 업데이트
            with self._state_lock:
                self._current_outputs = final_outputs
                self._current_pwm = new_pwm
                self._empc_cost_history.append(empc_cost)
                self._q_cost_history.append(q_cost)
                # 최근 60초 데이터만 유지
                if len(self._empc_cost_history) > 60:
                    self._empc_cost_history.pop(0)
                    self._q_cost_history.pop(0)

                self._shared_state = {
                    'twin': self._twin.get_state(),
                    'mc': mc_result,
                    'dr': dr_result,
                    'empc_cost': empc_cost,
                    'q_cost': q_cost,
                    'empc_outputs': empc_outputs,
                    'q_outputs': q_outputs,
                    'final_outputs': final_outputs,
                    'demand_mw': demand_mw,
                    'effective_demand_mw': effective_demand,
                    't_hours': t_hours,
                    'reserve_req': reserve_req,
                    'empc_cost_history': list(self._empc_cost_history),
                    'q_cost_history': list(self._q_cost_history),
                }

            logger.info(
                "제어루프: GSI=%.3f, freq=%.2fHz, 예비율=%.1f%%, "
                "EMPC비용=%.0f, Q비용=%.0f, 절감=%.0fMW",
                gsi,
                twin_state.get('frequency_hz', 60.0),
                twin_state.get('reserve_ratio', 0) * 100,
                empc_cost, q_cost,
                mc_result['saved_mw'],
            )

            # 1초 주기 유지
            elapsed = time.time() - t0
            sleep_t = max(0.0, CONTROL_LOOP_INTERVAL_SEC - elapsed)
            time.sleep(sleep_t)

    # ── 루프 C: API 업데이트 (5분) ───────────────────────────
    def _loop_api(self) -> None:
        logger.info("루프 C (KPX API) 시작")
        while self._running:
            try:
                estimates = self._kpx_api.get_plant_estimates()
                self._data_mgr.on_api_update(estimates)
                logger.info("KPX API 업데이트 완료: %s",
                            {k: f"{v:.3f}" for k, v in estimates.items()})
            except Exception as exc:
                logger.warning("API 루프 에러: %s", exc)
            time.sleep(API_UPDATE_INTERVAL_SEC)

    # ── 실행 / 종료 ───────────────────────────────────────────
    def start(self) -> None:
        self._running = True
        threads = [
            threading.Thread(target=self._loop_arduino, name='loop-arduino', daemon=True),
            threading.Thread(target=self._loop_control, name='loop-control', daemon=True),
            threading.Thread(target=self._loop_api, name='loop-api', daemon=True),
        ]
        for t in threads:
            t.start()
        logger.info("=== 시스템 가동 시작 ===")

    def stop(self) -> None:
        self._running = False
        self._q_agent.save_qtable()
        logger.info("=== 시스템 정지 ===")

    def get_shared_state(self) -> dict:
        with self._state_lock:
            return dict(self._shared_state)

    # ── 내부 유틸리티 ─────────────────────────────────────────
    def _elapsed_hours(self) -> float:
        return (time.time() - self._start_time) / 3600.0

    def _outputs_to_pwm(self, outputs: dict[str, float]) -> dict[str, int]:
        """출력 비율 (0~1) → PWM 정수 (0~255)"""
        pwm: dict[str, int] = {}
        for name in PLANT_NAMES:
            ratio = outputs.get(name, 0.0)
            pwm_max = PLANT_PROFILE[name]['pwm_max']
            pwm[name] = int(round(ratio * pwm_max))
        return pwm

    def _redistribute_on_fault(
        self,
        failed: str,
        outputs: dict[str, float],
        demand_mw: float,
    ) -> dict[str, float]:
        """고장 발전소 출력을 나머지 채널에 비례 배분"""
        failed_mw = PLANT_PROFILE[failed]['capacity_mw'] * outputs.get(failed, 0.0)
        active = [n for n in PLANT_NAMES if n != failed]

        total_avail = sum(
            PLANT_PROFILE[n]['capacity_mw'] * (PLANT_PROFILE[n]['p_max_ratio'] - outputs.get(n, 0.0))
            for n in active
        )

        new_outputs = dict(outputs)
        for name in active:
            if total_avail > 0:
                share = PLANT_PROFILE[name]['capacity_mw'] * (
                    PLANT_PROFILE[name]['p_max_ratio'] - outputs.get(name, 0.0)
                ) / total_avail
                extra_ratio = (failed_mw * share) / PLANT_PROFILE[name]['capacity_mw']
                new_ratio = outputs.get(name, 0.0) + extra_ratio
                new_outputs[name] = min(PLANT_PROFILE[name]['p_max_ratio'], new_ratio)

        return new_outputs


# ── 대시보드 통합 실행 ────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description='지능형 전력망 시스템')
    parser.add_argument('--simulate', action='store_true', help='Arduino 없이 시뮬레이션 모드')
    parser.add_argument('--fault', type=str, default=None,
                        help='고장 시뮬레이션 발전소 이름 (예: --fault 한울)')
    parser.add_argument('--no-dashboard', action='store_true', help='대시보드 없이 실행')
    args = parser.parse_args()

    system = SmartGridSystem(simulate=args.simulate, fault_plant=args.fault)
    system.start()

    if not args.no_dashboard:
        try:
            from dashboard.app import create_app
            app = create_app(system)
            from config import DASH_PORT
            logger.info("대시보드 시작: http://localhost:%d", DASH_PORT)
            app.run(host='0.0.0.0', port=DASH_PORT, debug=False)
        except ImportError as exc:
            logger.warning("대시보드 로드 실패: %s → CLI 모드", exc)
            _cli_loop(system)
    else:
        _cli_loop(system)


def _cli_loop(system: SmartGridSystem) -> None:
    """대시보드 없이 터미널에서 상태 출력"""
    logger.info("CLI 모드 실행 (Ctrl+C로 종료)")
    try:
        while True:
            state = system.get_shared_state()
            if state:
                twin = state.get('twin', {})
                mc = state.get('mc', {})
                print(
                    f"\r[GSI={twin.get('gsi', 0):.3f}] "
                    f"[f={twin.get('frequency_hz', 60):.2f}Hz] "
                    f"[예비율={twin.get('reserve_ratio', 0)*100:.1f}%] "
                    f"[절감={mc.get('saved_mw', 0):.0f}MW]",
                    end='', flush=True
                )
            time.sleep(1.0)
    except KeyboardInterrupt:
        print()
        system.stop()
        logger.info("종료")


if __name__ == '__main__':
    main()
