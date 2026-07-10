"""
app.py — Plotly Dash 대시보드 앱 진입점
SmartGridSystem 인스턴스를 주입받아 실시간 상태 시각화
"""

import sys
import os

# python/ 디렉토리를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import dash
from dash import html
from config import DASH_PORT
from dashboard.layout import create_layout
from dashboard.callbacks import register_callbacks, set_system


def create_app(system=None):
    """
    Dash 앱 생성 및 콜백 등록.

    Args:
        system: SmartGridSystem 인스턴스 (없으면 더미 데이터 사용)

    Returns:
        Dash 앱 인스턴스
    """
    # Bootstrap 스타일 포함
    try:
        import dash_bootstrap_components as dbc
        external_stylesheets = [dbc.themes.BOOTSTRAP]
    except ImportError:
        external_stylesheets = []

    app = dash.Dash(
        __name__,
        external_stylesheets=external_stylesheets,
        suppress_callback_exceptions=True,
        title='지능형 전력망 — 용인 클러스터',
    )

    # 시스템 참조 주입
    if system is not None:
        set_system(system)
    else:
        # 더미 시스템 (독립 실행용)
        set_system(_DummySystem())

    app.layout = create_layout()
    register_callbacks(app)

    return app


class _DummySystem:
    """대시보드 독립 실행 테스트용 더미 시스템"""

    def __init__(self) -> None:
        import time
        self._start = time.time()
        self._fault_plant = None

    def get_shared_state(self) -> dict:
        import math
        import time
        t = time.time() - self._start
        h = t / 3600.0

        gsi = 0.85 + 0.1 * math.sin(t / 30)
        reserve = 0.10 + 0.03 * math.sin(t / 20)
        freq = 60.0 + 0.05 * math.sin(t / 10)
        pqi = 0.995 + 0.004 * math.sin(t / 15)
        demand_mw = 2550.0 + 200 * math.sin(t / 60)
        supply_mw = demand_mw * (1 + reserve)

        from config import PLANT_NAMES, PLANT_PROFILE, OLD_RESERVE_RATIO
        outputs = {n: 0.7 + 0.1 * math.sin(t / 20 + i) for i, n in enumerate(PLANT_NAMES)}
        smart_reserve = max(0.05, min(0.08, reserve * 0.6))
        saved_mw = max(0, (OLD_RESERVE_RATIO - smart_reserve) * demand_mw)

        cost_base = 5_000_000.0
        empc_hist = [cost_base * (1 + 0.05 * math.sin(t / 5 + i * 0.3)) for i in range(60)]
        q_hist = [cost_base * (1 + 0.08 * math.sin(t / 5 + i * 0.3 + 1)) for i in range(60)]

        return {
            'twin': {
                'gsi': gsi,
                'frequency_hz': freq,
                'pqi': pqi,
                'supply_mw': supply_mw,
                'demand_mw': demand_mw,
                'reserve_ratio': reserve,
                'plant_outputs': outputs,
                'transmission_losses': {n: 0.05 for n in PLANT_NAMES},
            },
            'mc': {
                'smart_reserve_ratio': smart_reserve,
                'traditional_reserve_ratio': OLD_RESERVE_RATIO,
                'saved_ratio': max(0, OLD_RESERVE_RATIO - smart_reserve),
                'saved_mw': saved_mw,
            },
            'dr': {'event_log': []},
            'final_outputs': outputs,
            'demand_mw': demand_mw,
            'empc_cost': cost_base,
            'q_cost': cost_base * 1.03,
            'empc_cost_history': empc_hist,
            'q_cost_history': q_hist,
            't_hours': h,
        }


# 독립 실행 (시뮬레이션 데이터만으로 대시보드 확인)
if __name__ == '__main__':
    app = create_app()
    print(f"대시보드 실행: http://localhost:{DASH_PORT}")
    app.run(host='0.0.0.0', port=DASH_PORT, debug=True)
