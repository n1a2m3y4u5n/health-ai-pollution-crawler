"""
q_learning_agent.py — Q-Learning 기반 급전 최적화 에이전트
EMPC와 병렬 실행 후 성능 비교
"""

import logging
import os
import random
import itertools
from typing import Optional
import numpy as np
from config import PLANT_PROFILE, PLANT_NAMES

logger = logging.getLogger(__name__)

N_PLANTS = len(PLANT_NAMES)

# 상태 이산화 파라미터
_LOAD_BINS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]       # 부하율 5구간
_RESERVE_BINS = [0.0, 0.08, 0.15, 1.0]              # 예비율 3구간 (부족/적정/충분)
_TIME_BINS = [0, 6, 9, 22, 24]                       # 시간대 4구간

N_LOAD = 5
N_RESERVE = 3
N_TIME = 4
N_STATES = N_LOAD * N_RESERVE * N_TIME              # 60

# 액션: 각 발전소 출력 조정 (-5%, 0%, +5%) → 3^5 = 243가지
_DELTA_CHOICES = [-0.05, 0.0, 0.05]
_ALL_ACTIONS = list(itertools.product(_DELTA_CHOICES, repeat=N_PLANTS))
N_ACTIONS = len(_ALL_ACTIONS)   # 243


class QLearningAgent:
    """
    강화학습 기반 급전 최적화 에이전트.

    State: (부하율 구간, 예비율 구간, 시간대) → 60개
    Action: 5개 발전소 각 -5%/0%/+5% → 243개
    Reward: 수급 균형, PQI, 예비율, 비용, 고장 패널티
    """

    def __init__(self, load_pretrained: bool = True) -> None:
        self._alpha = 0.1     # 학습률
        self._gamma = 0.95    # 할인율
        self._epsilon = 0.1   # 탐험률
        self._epsilon_min = 0.01
        self._epsilon_decay = 0.9995

        # Q-테이블 초기화
        self._qtable = np.zeros((N_STATES, N_ACTIONS))
        self._step_count = 0

        if load_pretrained:
            self.load_qtable()

        logger.info("QLearningAgent 초기화 (states=%d, actions=%d, ε=%.3f)",
                    N_STATES, N_ACTIONS, self._epsilon)

    # ── 공개 API ─────────────────────────────────────────────
    def get_action(self, state: tuple) -> dict[str, float]:
        """
        ε-greedy 정책으로 액션 선택.
        반환: {'한울': 0.87, '태안': 0.72, ...} (절대 출력 비율)
        """
        state_idx = self._state_to_idx(state)

        if random.random() < self._epsilon:
            action_idx = random.randrange(N_ACTIONS)
        else:
            action_idx = int(np.argmax(self._qtable[state_idx]))

        deltas = _ALL_ACTIONS[action_idx]
        outputs: dict[str, float] = {}

        for i, name in enumerate(PLANT_NAMES):
            profile = PLANT_PROFILE[name]
            # 현재 Q-learning 추정 출력 = 중간값 + delta
            base = (profile['p_min_ratio'] + profile['p_max_ratio']) / 2.0
            ratio = base + deltas[i]
            ratio = max(profile['p_min_ratio'], min(profile['p_max_ratio'], ratio))
            outputs[name] = ratio

        return outputs

    def get_action_from_current(
        self, state: tuple, current_outputs: dict[str, float]
    ) -> dict[str, float]:
        """현재 출력에 delta를 더해 새 액션 계산"""
        state_idx = self._state_to_idx(state)

        if random.random() < self._epsilon:
            action_idx = random.randrange(N_ACTIONS)
        else:
            action_idx = int(np.argmax(self._qtable[state_idx]))

        deltas = _ALL_ACTIONS[action_idx]
        outputs: dict[str, float] = {}

        for i, name in enumerate(PLANT_NAMES):
            profile = PLANT_PROFILE[name]
            ratio = current_outputs.get(name, profile['p_min_ratio']) + deltas[i]
            ratio = max(profile['p_min_ratio'], min(profile['p_max_ratio'], ratio))
            outputs[name] = ratio

        return outputs, action_idx

    def update(
        self,
        state: tuple,
        action_idx: int,
        reward: float,
        next_state: tuple,
    ) -> None:
        """Q-Learning 업데이트 (벨만 방정식)"""
        s = self._state_to_idx(state)
        s2 = self._state_to_idx(next_state)

        q_old = self._qtable[s, action_idx]
        q_max_next = np.max(self._qtable[s2])
        q_new = q_old + self._alpha * (reward + self._gamma * q_max_next - q_old)
        self._qtable[s, action_idx] = q_new

        # ε 감소
        self._epsilon = max(self._epsilon_min, self._epsilon * self._epsilon_decay)
        self._step_count += 1

    def compute_reward(
        self,
        grid_state: dict,
        prev_outputs: dict[str, float],
        new_outputs: dict[str, float],
    ) -> float:
        """
        Reward 함수:
          +10.0 수급 균형 달성 (예비율 8~15%)
          +2.0  PQI > 0.99
          -5.0  예비율 < 8%
          -3.0  Ramping 제한 위반
          -비용  총 발전 비용 / 정규화 상수
          -20.0 고장 발생 (GSI < 0.5)
        """
        reward = 0.0

        reserve = grid_state.get('reserve_ratio', 0.0)
        pqi = grid_state.get('pqi', 1.0)
        gsi = grid_state.get('gsi', 1.0)

        # 수급 균형
        if 0.08 <= reserve <= 0.15:
            reward += 10.0
        elif reserve < 0.08:
            reward -= 5.0

        # PQI 보너스
        if pqi > 0.99:
            reward += 2.0

        # Ramping 위반 패널티
        for i, name in enumerate(PLANT_NAMES):
            profile = PLANT_PROFILE[name]
            delta = abs(new_outputs.get(name, 0) - prev_outputs.get(name, 0))
            max_delta = profile['ramp_rate_pct_per_min'] / 100.0
            if delta > max_delta:
                reward -= 3.0

        # 발전 비용 패널티 (정규화)
        total_cost = sum(
            PLANT_PROFILE[n]['cost_a'] * (new_outputs.get(n, 0) * PLANT_PROFILE[n]['capacity_mw']) ** 2
            + PLANT_PROFILE[n]['cost_b'] * (new_outputs.get(n, 0) * PLANT_PROFILE[n]['capacity_mw'])
            + PLANT_PROFILE[n]['cost_c']
            for n in PLANT_NAMES
        )
        reward -= total_cost / 1_000_000.0

        # 고장 패널티
        if gsi < 0.5:
            reward -= 20.0

        return reward

    def encode_state(self, grid_state: dict) -> tuple:
        """연속 상태 → 이산 상태 인코딩"""
        # 부하율 (수요 / 최대 수요)
        demand = grid_state.get('demand_mw', 1500.0)
        max_demand = 3000.0
        load_ratio = demand / max_demand

        # 예비율
        reserve = grid_state.get('reserve_ratio', 0.10)

        # 시간대
        t_hour = grid_state.get('t_hour', 12.0) % 24.0

        return (load_ratio, reserve, t_hour)

    def save_qtable(self, path: str = 'q_table.npy') -> None:
        try:
            np.save(path, self._qtable)
            logger.info("Q-테이블 저장: %s", path)
        except Exception as exc:
            logger.warning("Q-테이블 저장 실패: %s", exc)

    def load_qtable(self, path: str = 'q_table.npy') -> None:
        if os.path.exists(path):
            try:
                self._qtable = np.load(path)
                logger.info("Q-테이블 불러오기 성공: %s (스텝=%d)", path, self._step_count)
            except Exception as exc:
                logger.warning("Q-테이블 불러오기 실패: %s → 새로 시작", exc)
        else:
            logger.info("Q-테이블 파일 없음 → 새로 초기화")

    # ── 내부 헬퍼 ────────────────────────────────────────────
    def _state_to_idx(self, state: tuple) -> int:
        """(load_ratio, reserve, t_hour) → 단일 정수 인덱스"""
        load_ratio, reserve, t_hour = state

        # 부하율 이산화 (0~4)
        load_idx = min(N_LOAD - 1, max(0, int((load_ratio - 0.5) / 0.1)))

        # 예비율 이산화 (0~2)
        if reserve < 0.08:
            reserve_idx = 0
        elif reserve <= 0.15:
            reserve_idx = 1
        else:
            reserve_idx = 2

        # 시간대 이산화 (0~3)
        if t_hour < 6:
            time_idx = 0
        elif t_hour < 9:
            time_idx = 1
        elif t_hour < 22:
            time_idx = 2
        else:
            time_idx = 3

        idx = load_idx * (N_RESERVE * N_TIME) + reserve_idx * N_TIME + time_idx
        return int(idx % N_STATES)


# 단독 테스트
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    agent = QLearningAgent(load_pretrained=False)

    state = (0.85, 0.10, 14.0)
    action = agent.get_action(state)
    print("=== Q-Learning 에이전트 테스트 ===")
    print("상태:", state)
    print("액션:", {k: f"{v:.3f}" for k, v in action.items()})
    print(f"Q-테이블 크기: {agent._qtable.shape}, 전체 파라미터: {agent._qtable.size}")
