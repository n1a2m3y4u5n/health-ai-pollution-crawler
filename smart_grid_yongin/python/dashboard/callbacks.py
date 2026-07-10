"""
callbacks.py — Plotly Dash 실시간 업데이트 콜백 정의
2초마다 모든 차트/수치 자동 갱신
"""

import time
from datetime import datetime
from dash import Output, Input, callback
import plotly.graph_objects as go
import plotly.express as px
from config import PLANT_NAMES, PLANT_PROFILE, FUEL_COLORS, OLD_RESERVE_RATIO
from dashboard.korea_map import build_korea_map

# 시스템 참조 (app.py에서 주입)
_system_ref = None


def set_system(system) -> None:
    """main.py의 SmartGridSystem 인스턴스 주입"""
    global _system_ref
    _system_ref = system


def register_callbacks(app) -> None:
    """Dash 앱에 모든 콜백 등록"""

    @app.callback(
        [
            Output('metric-gsi', 'children'),
            Output('metric-reserve', 'children'),
            Output('metric-freq', 'children'),
            Output('metric-pqi', 'children'),
            Output('status-badge', 'children'),
            Output('status-badge', 'style'),
            Output('clock-display', 'children'),
            Output('korea-map', 'figure'),
            Output('supply-demand-chart', 'figure'),
            Output('plant-output-chart', 'figure'),
            Output('algo-compare-chart', 'figure'),
            Output('algo-compare-title', 'children'),
            Output('event-log', 'children'),
        ],
        Input('interval-update', 'n_intervals'),
    )
    def update_all(n_intervals):
        state = _system_ref.get_shared_state() if _system_ref else {}
        twin = state.get('twin', {})
        mc = state.get('mc', {})
        dr = state.get('dr', {})

        # ── 메트릭 값 ──────────────────────────────────────
        gsi = twin.get('gsi', 0.0)
        reserve = twin.get('reserve_ratio', 0.0)
        freq = twin.get('frequency_hz', 60.0)
        pqi = twin.get('pqi', 1.0)
        demand_mw = state.get('demand_mw', 0.0)
        supply_mw = twin.get('supply_mw', 0.0)

        # ── 상태 배지 ──────────────────────────────────────
        if gsi >= 0.85 and reserve >= 0.08:
            badge_text = '● 정상 운전'
            badge_color = '#43a047'
        elif gsi >= 0.70:
            badge_text = '⚠ 주의 상태'
            badge_color = '#f57c00'
        else:
            badge_text = '🚨 경고 상태'
            badge_color = '#e53935'

        badge_style = {
            'marginRight': '16px', 'fontSize': '14px',
            'background': badge_color, 'padding': '4px 12px',
            'borderRadius': '12px',
        }

        clock = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # ── 한국 지도 ──────────────────────────────────────
        outputs = state.get('final_outputs', {})
        map_fig = build_korea_map(outputs, twin)

        # ── 공급/수요 + 예비력 비교 ─────────────────────────
        smart_reserve = mc.get('smart_reserve_ratio', 0.08)
        saved_mw = mc.get('saved_mw', 0.0)

        supply_fig = go.Figure()
        supply_fig.add_trace(go.Bar(
            name='공급(MW)', x=['전력 현황'],
            y=[supply_mw], marker_color='#1976d2', text=[f'{supply_mw:.0f}'],
            textposition='inside',
        ))
        supply_fig.add_trace(go.Bar(
            name='수요(MW)', x=['전력 현황'],
            y=[demand_mw], marker_color='#e53935', text=[f'{demand_mw:.0f}'],
            textposition='inside',
        ))
        supply_fig.add_trace(go.Bar(
            name=f'기존 예비 15%', x=['예비력 비교'],
            y=[demand_mw * OLD_RESERVE_RATIO], marker_color='#ef9a9a',
            text=[f'{demand_mw * OLD_RESERVE_RATIO:.0f}MW'], textposition='inside',
        ))
        supply_fig.add_trace(go.Bar(
            name=f'스마트 예비 {smart_reserve*100:.1f}%', x=['예비력 비교'],
            y=[demand_mw * smart_reserve], marker_color='#66bb6a',
            text=[f'{demand_mw * smart_reserve:.0f}MW'], textposition='inside',
        ))
        supply_fig.add_annotation(
            x='예비력 비교', y=demand_mw * OLD_RESERVE_RATIO * 0.5,
            text=f'<b>+{saved_mw:.0f}MW\n용인 추가 공급</b>',
            showarrow=False, font=dict(color='#1a237e', size=10),
        )
        supply_fig.update_layout(
            barmode='group', height=160,
            margin=dict(l=30, r=10, t=10, b=30),
            legend=dict(orientation='h', x=0, y=-0.3, font=dict(size=10)),
            paper_bgcolor='white', plot_bgcolor='white',
            xaxis=dict(showgrid=False), yaxis=dict(title='MW', tickfont=dict(size=9)),
        )

        # ── 발전소별 출력 바 차트 ────────────────────────────
        plant_names_disp = []
        plant_ratios = []
        plant_colors_list = []

        for name in PLANT_NAMES:
            ratio = outputs.get(name, 0.0)
            fuel = PLANT_PROFILE[name]['fuel_type']
            plant_names_disp.append(f"{name}\n({PLANT_PROFILE[name]['capacity_mw']//1000}GW)")
            plant_ratios.append(ratio * 100)
            plant_colors_list.append(FUEL_COLORS.get(fuel, '#888'))

        plant_fig = go.Figure(go.Bar(
            x=plant_names_disp,
            y=plant_ratios,
            marker_color=plant_colors_list,
            text=[f'{v:.1f}%' for v in plant_ratios],
            textposition='inside',
        ))
        plant_fig.add_hline(y=100, line_dash='dash', line_color='red', annotation_text='최대')
        plant_fig.update_layout(
            height=160,
            margin=dict(l=30, r=10, t=10, b=40),
            paper_bgcolor='white', plot_bgcolor='#fafafa',
            yaxis=dict(title='출력(%)', range=[0, 110], tickfont=dict(size=9)),
            xaxis=dict(tickfont=dict(size=9)),
        )

        # ── EMPC vs Q-Learning 비교 ──────────────────────────
        empc_hist = state.get('empc_cost_history', [])
        q_hist = state.get('q_cost_history', [])
        n = len(empc_hist)

        algo_fig = go.Figure()
        if n > 0:
            xs = list(range(-n + 1, 1))
            algo_fig.add_trace(go.Scatter(
                x=xs, y=empc_hist, name='EMPC', line=dict(color='#1976d2', width=2),
            ))
            algo_fig.add_trace(go.Scatter(
                x=xs, y=q_hist, name='Q-Learning', line=dict(color='#f57c00', width=2),
            ))

        empc_cost = state.get('empc_cost', 0.0)
        q_cost = state.get('q_cost', 0.0)
        if empc_cost <= q_cost:
            winner = 'EMPC 우위'
            w_color = '#1976d2'
        else:
            winner = 'Q-Learning 우위'
            w_color = '#f57c00'

        algo_title = f'🤖 EMPC vs Q-Learning 발전 비용 비교 — 현재 <span style="color:{w_color}">{winner}</span>'

        algo_fig.update_layout(
            height=130,
            margin=dict(l=40, r=10, t=10, b=30),
            paper_bgcolor='white', plot_bgcolor='#fafafa',
            legend=dict(orientation='h', x=0.5, y=-0.35, xanchor='center', font=dict(size=10)),
            xaxis=dict(title='초 전', tickfont=dict(size=9)),
            yaxis=dict(title='비용', tickfont=dict(size=9)),
        )

        # ── 이벤트 로그 ──────────────────────────────────────
        log_entries = dr.get('event_log', [])
        log_lines = []

        if _system_ref and hasattr(_system_ref, '_fault_plant') and _system_ref._fault_plant:
            log_lines.append(
                f'[{clock}] 🚨 고장 시뮬레이션: {_system_ref._fault_plant} 발전소 탈락'
            )

        for ev in reversed(log_entries[-8:]):
            ts = datetime.fromtimestamp(ev['ts']).strftime('%H:%M:%S')
            log_lines.append(f"[{ts}] DR {ev['type']} {ev['action']}")

        log_lines.insert(0,
            f"[{clock}] GSI={gsi:.3f} | f={freq:.3f}Hz | 예비율={reserve*100:.1f}% | "
            f"PQI={pqi:.4f} | 절감={mc.get('saved_mw', 0):.0f}MW"
        )

        log_html = '\n'.join(log_lines)

        return (
            f'{gsi:.3f}',
            f'{reserve * 100:.1f}',
            f'{freq:.3f}',
            f'{pqi:.4f}',
            badge_text,
            badge_style,
            clock,
            map_fig,
            supply_fig,
            plant_fig,
            algo_fig,
            algo_title,
            log_html,
        )
