"""
layout.py — Plotly Dash 대시보드 레이아웃 정의
"""

from dash import dcc, html
import dash_bootstrap_components as dbc


def create_layout() -> html.Div:
    """전체 대시보드 레이아웃 생성"""
    return html.Div(
        style={'fontFamily': 'Noto Sans KR, sans-serif', 'backgroundColor': '#f0f2f5'},
        children=[
            # ── 자동 업데이트 인터벌 ───────────────────────
            dcc.Interval(id='interval-update', interval=2000, n_intervals=0),

            # ── 상단 헤더 ──────────────────────────────────
            html.Div(
                style={
                    'background': 'linear-gradient(135deg, #1a237e, #283593)',
                    'color': 'white',
                    'padding': '16px 24px',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'space-between',
                    'boxShadow': '0 2px 8px rgba(0,0,0,0.3)',
                },
                children=[
                    html.Div([
                        html.H4('⚡ 지능형 전력망 — 용인 반도체 클러스터 전력 공급 최적화',
                                style={'margin': 0, 'fontSize': '18px'}),
                        html.Small('용인 반도체 클러스터 3GW 공급 목표 | 스마트 그리드 최적 급전',
                                   style={'opacity': 0.75}),
                    ]),
                    html.Div([
                        html.Span(id='status-badge', children='● 정상 운전',
                                  style={'marginRight': '16px', 'fontSize': '14px',
                                         'background': '#43a047', 'padding': '4px 12px',
                                         'borderRadius': '12px'}),
                        html.Span(id='clock-display', style={'fontSize': '13px', 'opacity': 0.8}),
                    ]),
                ],
            ),

            # ── 상단 메트릭 4개 ────────────────────────────
            html.Div(
                style={'display': 'grid', 'gridTemplateColumns': 'repeat(4, 1fr)',
                       'gap': '12px', 'padding': '16px 16px 0'},
                children=[
                    _metric_card('GSI', id='metric-gsi', unit='',
                                 desc='계통 안정도 지수', color='#1976d2'),
                    _metric_card('예비율', id='metric-reserve', unit='%',
                                 desc='공급 예비율 (스마트)', color='#388e3c'),
                    _metric_card('주파수', id='metric-freq', unit='Hz',
                                 desc='계통 주파수', color='#f57c00'),
                    _metric_card('PQI', id='metric-pqi', unit='',
                                 desc='전력품질지수', color='#7b1fa2'),
                ],
            ),

            # ── 메인 콘텐츠 영역 ──────────────────────────
            html.Div(
                style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                       'gap': '12px', 'padding': '12px 16px'},
                children=[
                    # 왼쪽: 한국 지도
                    html.Div(
                        style=_card_style(),
                        children=[
                            html.H6('🗺 전국 발전소 전력 흐름',
                                    style={'margin': '0 0 8px', 'color': '#37474f'}),
                            dcc.Graph(id='korea-map', style={'height': '480px'},
                                      config={'displayModeBar': False}),
                        ],
                    ),

                    # 오른쪽: 4개 서브 패널
                    html.Div(
                        style={'display': 'flex', 'flexDirection': 'column', 'gap': '12px'},
                        children=[
                            # 공급/수요 + 예비력 비교
                            html.Div(
                                style=_card_style(),
                                children=[
                                    html.H6('📊 공급/수요 및 예비력 절감 효과',
                                            style={'margin': '0 0 8px', 'color': '#37474f'}),
                                    dcc.Graph(id='supply-demand-chart',
                                              style={'height': '160px'},
                                              config={'displayModeBar': False}),
                                ],
                            ),

                            # 발전소별 출력 바 차트
                            html.Div(
                                style=_card_style(),
                                children=[
                                    html.H6('🏭 발전소별 현재 출력 (%)',
                                            style={'margin': '0 0 8px', 'color': '#37474f'}),
                                    dcc.Graph(id='plant-output-chart',
                                              style={'height': '160px'},
                                              config={'displayModeBar': False}),
                                ],
                            ),

                            # EMPC vs Q-Learning 비교
                            html.Div(
                                style=_card_style(),
                                children=[
                                    html.H6(id='algo-compare-title',
                                            children='🤖 EMPC vs Q-Learning 비용 비교 (최근 60초)',
                                            style={'margin': '0 0 8px', 'color': '#37474f'}),
                                    dcc.Graph(id='algo-compare-chart',
                                              style={'height': '130px'},
                                              config={'displayModeBar': False}),
                                ],
                            ),
                        ],
                    ),
                ],
            ),

            # ── 이벤트 로그 ────────────────────────────────
            html.Div(
                style={**_card_style(), 'margin': '0 16px 16px'},
                children=[
                    html.H6('📋 시스템 이벤트 로그',
                            style={'margin': '0 0 8px', 'color': '#37474f'}),
                    html.Div(id='event-log',
                             style={
                                 'height': '100px',
                                 'overflowY': 'auto',
                                 'fontFamily': 'monospace',
                                 'fontSize': '12px',
                                 'backgroundColor': '#1e1e1e',
                                 'color': '#d4d4d4',
                                 'padding': '8px',
                                 'borderRadius': '4px',
                             }),
                ],
            ),
        ],
    )


def _metric_card(label: str, id: str, unit: str, desc: str, color: str) -> html.Div:
    return html.Div(
        style={
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'padding': '12px 16px',
            'boxShadow': '0 1px 4px rgba(0,0,0,0.1)',
            'borderLeft': f'4px solid {color}',
        },
        children=[
            html.Div(label, style={'fontSize': '11px', 'color': '#78909c', 'fontWeight': '600',
                                   'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
            html.Div([
                html.Span(id=id, children='--',
                          style={'fontSize': '28px', 'fontWeight': '700', 'color': color}),
                html.Span(f' {unit}', style={'fontSize': '14px', 'color': '#90a4ae'}),
            ]),
            html.Div(desc, style={'fontSize': '11px', 'color': '#90a4ae', 'marginTop': '2px'}),
        ],
    )


def _card_style() -> dict:
    return {
        'backgroundColor': 'white',
        'borderRadius': '8px',
        'padding': '12px 16px',
        'boxShadow': '0 1px 4px rgba(0,0,0,0.1)',
    }
