"""
korea_map.py — 한국 지도 + 발전소 마커 + 전력 흐름 시각화
Plotly go.Scattergeo 사용
"""

from typing import Optional
import plotly.graph_objects as go
from config import PLANT_PROFILE, PLANT_NAMES, FUEL_COLORS, YONGIN_SPEC


def build_korea_map(
    plant_outputs: Optional[dict[str, float]] = None,
    twin_state: Optional[dict] = None,
) -> go.Figure:
    """
    한국 지도 + 발전소 마커 + 전력 흐름 라인 생성.

    Args:
        plant_outputs: 발전소별 출력 비율 (0~1)
        twin_state: 디지털 트윈 상태 (송전 손실 등)

    Returns:
        Plotly Figure
    """
    if plant_outputs is None:
        plant_outputs = {n: PLANT_PROFILE[n]['p_min_ratio'] for n in PLANT_NAMES}

    fig = go.Figure()

    yongin_lat, yongin_lon = YONGIN_SPEC['location']

    # ── 전력 흐름 라인 (각 발전소 → 용인) ──────────────────
    for name in PLANT_NAMES:
        profile = PLANT_PROFILE[name]
        ratio = plant_outputs.get(name, 0.0)
        lat_plant, lon_plant = profile['location']
        fuel = profile['fuel_type']
        color = FUEL_COLORS.get(fuel, '#888888')

        # 출력 비율 → 라인 두께 + 불투명도
        line_width = 1.0 + ratio * 5.0
        opacity = 0.3 + ratio * 0.6

        # 호버 텍스트
        raw_mw = ratio * profile['capacity_mw']
        loss_mw = raw_mw * profile['tx_loss_ratio']
        sent_mw = raw_mw - loss_mw

        hover = (
            f"{name} → 용인<br>"
            f"출력: {raw_mw:.0f} MW ({ratio*100:.1f}%)<br>"
            f"송전 손실: {loss_mw:.0f} MW ({profile['tx_loss_ratio']*100:.1f}%)<br>"
            f"도달 전력: {sent_mw:.0f} MW<br>"
            f"거리: {profile['distance_yongin_km']} km"
        )

        fig.add_trace(go.Scattergeo(
            lat=[lat_plant, yongin_lat],
            lon=[lon_plant, yongin_lon],
            mode='lines',
            line=dict(width=line_width, color=color),
            opacity=opacity,
            hoverinfo='text',
            hovertext=hover,
            name=f"{name} 송전",
            showlegend=False,
        ))

    # ── 발전소 마커 ──────────────────────────────────────────
    for name in PLANT_NAMES:
        profile = PLANT_PROFILE[name]
        ratio = plant_outputs.get(name, 0.0)
        lat, lon = profile['location']
        fuel = profile['fuel_type']
        color = FUEL_COLORS.get(fuel, '#888888')

        raw_mw = ratio * profile['capacity_mw']
        loss_mw = raw_mw * profile['tx_loss_ratio']

        hover = (
            f"<b>{name}</b><br>"
            f"연료: {fuel}<br>"
            f"설비용량: {profile['capacity_mw']:,} MW<br>"
            f"현재 출력: {raw_mw:.0f} MW ({ratio*100:.1f}%)<br>"
            f"송전 손실: {loss_mw:.0f} MW ({profile['tx_loss_ratio']*100:.1f}%)<br>"
            f"용인까지: {profile['distance_yongin_km']} km"
        )

        fig.add_trace(go.Scattergeo(
            lat=[lat],
            lon=[lon],
            mode='markers+text',
            marker=dict(
                size=10 + ratio * 15,
                color=color,
                opacity=0.85,
                line=dict(color='white', width=1),
            ),
            text=[name],
            textposition='top center',
            hoverinfo='text',
            hovertext=hover,
            name=name,
            showlegend=True,
        ))

    # ── 용인 클러스터 마커 ───────────────────────────────────
    demand_mw = (twin_state or {}).get('demand_mw', 2550.0)
    fig.add_trace(go.Scattergeo(
        lat=[yongin_lat],
        lon=[yongin_lon],
        mode='markers+text',
        marker=dict(
            size=22,
            color='#e53935',
            symbol='star',
            opacity=0.95,
            line=dict(color='white', width=2),
        ),
        text=['용인 클러스터'],
        textposition='bottom center',
        hoverinfo='text',
        hovertext=(
            f"<b>용인 반도체 클러스터</b><br>"
            f"현재 수요: {demand_mw:.0f} MW<br>"
            f"2027년 목표: 3,000 MW<br>"
            f"PQI 임계값: 99.0%"
        ),
        name='용인 클러스터',
        showlegend=True,
    ))

    # ── 지도 레이아웃 ────────────────────────────────────────
    fig.update_layout(
        title=dict(text='전국 발전소 → 용인 반도체 클러스터 전력 공급 현황', x=0.5),
        geo=dict(
            scope='asia',
            center=dict(lat=36.8, lon=127.8),
            projection_scale=8,
            showland=True,
            landcolor='rgb(243, 243, 243)',
            showocean=True,
            oceancolor='rgb(204, 229, 255)',
            showcountries=True,
            countrycolor='rgb(200, 200, 200)',
            showcoastlines=True,
            coastlinecolor='rgb(150, 150, 150)',
        ),
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.8)'),
        height=500,
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor='#f8f9fa',
    )

    return fig
