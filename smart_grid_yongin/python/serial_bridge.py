"""
serial_bridge.py — Arduino MEGA ↔ Python PC 시리얼 통신 브릿지
Arduino 없을 때 시뮬레이션 모드 자동 전환
"""

import logging
import threading
import time
import random
from typing import Optional
from config import (
    PLANT_NAMES, PLANT_PROFILE, CHANNEL_MAX_CURRENT,
    SERIAL_PORT, SERIAL_BAUD, SMPS_MAX_CURRENT,
)

logger = logging.getLogger(__name__)


class SerialBridge:
    """
    Arduino MEGA ↔ Python PC 시리얼 통신.

    수신 (Arduino → PC), 100ms 주기:
      형식: "S,{c0:.3f},{c1:.3f},{c2:.3f},{c3:.3f},{c4:.3f}\\n"
    송신 (PC → Arduino), 1초 주기:
      형식: "C,{p0},{p1},{p2},{p3},{p4}\\n"

    Arduino 없으면 시뮬레이션 모드로 자동 전환.
    """

    def __init__(self, port: str = SERIAL_PORT, baud: int = SERIAL_BAUD) -> None:
        self._port = port
        self._baud = baud
        self._serial = None
        self._lock = threading.Lock()
        self._connected = False
        self._simulate = False

        # 시뮬레이션 상태
        self._sim_pwm: dict[str, int] = {n: PLANT_PROFILE[n]['pwm_max'] // 2 for n in PLANT_NAMES}
        self._last_rx_ts: float = 0.0

        self._try_connect()

    # ── 공개 API ─────────────────────────────────────────────
    def send_pwm_commands(self, pwm_dict: dict[str, int]) -> None:
        """
        {'한울': 80, '태안': 47, ...} → Arduino 전송.
        시뮬레이션 모드에서는 내부 상태만 업데이트.
        """
        p = [int(pwm_dict.get(n, 0)) for n in PLANT_NAMES]
        p_clamped = [max(0, min(255, v)) for v in p]

        if self._simulate:
            for i, name in enumerate(PLANT_NAMES):
                self._sim_pwm[name] = p_clamped[i]
            return

        msg = f"C,{','.join(str(v) for v in p_clamped)}\n"
        with self._lock:
            if self._serial and self._connected:
                try:
                    self._serial.write(msg.encode('ascii'))
                    logger.debug("Arduino 송신: %s", msg.strip())
                except Exception as exc:
                    logger.warning("Arduino 송신 실패: %s", exc)
                    self._connected = False
                    threading.Thread(target=self._reconnect_loop, daemon=True).start()
            else:
                # 연결 끊김 → 시뮬레이션으로 임시 전환
                for i, name in enumerate(PLANT_NAMES):
                    self._sim_pwm[name] = p_clamped[i]

    def read_sensor_data(self) -> Optional[dict[str, float]]:
        """
        Arduino 전류 데이터 수신.
        반환: {'한울': 2.3, ...} (암페어) 또는 None
        """
        if self._simulate:
            return self._simulate_sensor()

        with self._lock:
            if not (self._serial and self._connected):
                return self._simulate_sensor()
            try:
                line = self._serial.readline()
                if not line:
                    return None
                return self._parse_sensor_line(line.decode('ascii', errors='replace').strip())
            except Exception as exc:
                logger.warning("Arduino 수신 실패: %s", exc)
                self._connected = False
                threading.Thread(target=self._reconnect_loop, daemon=True).start()
                return None

    def is_connected(self) -> bool:
        return self._connected and not self._simulate

    def is_simulating(self) -> bool:
        return self._simulate

    # ── 내부 헬퍼 ────────────────────────────────────────────
    def _try_connect(self) -> None:
        """시리얼 포트 연결 시도"""
        try:
            import serial
            self._serial = serial.Serial(self._port, self._baud, timeout=0.2)
            time.sleep(2.0)   # Arduino 부팅 대기
            self._connected = True
            self._simulate = False
            logger.info("Arduino 연결 성공: %s @ %d baud", self._port, self._baud)
        except ImportError:
            logger.warning("pyserial 미설치 → 시뮬레이션 모드")
            self._simulate = True
        except Exception as exc:
            logger.warning("Arduino 연결 실패 (%s) → 시뮬레이션 모드", exc)
            self._simulate = True

    def _reconnect_loop(self) -> None:
        """연결 끊김 시 재연결 시도 (백그라운드)"""
        while not self._connected:
            logger.info("Arduino 재연결 시도...")
            time.sleep(5.0)
            self._try_connect()

    def _parse_sensor_line(self, line: str) -> Optional[dict[str, float]]:
        """
        "S,2.34,1.82,1.44,0.78,0.65" 형식 파싱
        반환: {'한울': 2.34, ...}
        """
        try:
            parts = line.split(',')
            if len(parts) != N_PLANTS + 1 or parts[0] != 'S':
                return None
            return {name: float(parts[i + 1]) for i, name in enumerate(PLANT_NAMES)}
        except (ValueError, IndexError):
            logger.debug("센서 데이터 파싱 실패: %r", line)
            return None

    def _simulate_sensor(self) -> dict[str, float]:
        """
        PWM 명령값 기반으로 ACS712 전류 추정.
        노이즈 ±2% 추가로 현실감 부여.
        """
        result: dict[str, float] = {}
        for name in PLANT_NAMES:
            pwm = self._sim_pwm.get(name, 0)
            max_current = CHANNEL_MAX_CURRENT[name]
            base_current = max_current * (pwm / 255.0)
            noise = random.gauss(0, base_current * 0.02)
            result[name] = max(0.0, base_current + noise)
        return result


N_PLANTS = len(PLANT_NAMES)


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    bridge = SerialBridge()

    print(f"=== SerialBridge 테스트 (시뮬레이션={bridge.is_simulating()}) ===")

    # PWM 전송
    pwm = {'한울': 80, '태안': 47, '보령': 34, '인천': 18, '울산': 15}
    bridge.send_pwm_commands(pwm)

    # 센서 읽기
    for _ in range(5):
        data = bridge.read_sensor_data()
        if data:
            print("센서:", {k: f"{v:.3f}A" for k, v in data.items()})
        time.sleep(0.1)
