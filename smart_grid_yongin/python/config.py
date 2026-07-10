"""
config.py — 시스템 전역 상수 및 발전소 파라미터 정의
용인 반도체 클러스터 전력 공급 최적화 프로젝트
"""

# ───────────────────────────────────────────────
# 발전소 프로필 (5개 채널)
# ───────────────────────────────────────────────
PLANT_PROFILE = {
    '한울': {
        'capacity_mw': 8561,
        'fuel_type': 'nuclear',
        'location': (37.09, 129.38),
        'distance_yongin_km': 280,
        'tx_loss_ratio': 0.084,
        'cost_a': 0.5, 'cost_b': 40.0, 'cost_c': 0.0,
        'p_min_ratio': 0.80,
        'p_max_ratio': 1.00,
        'ramp_rate_pct_per_min': 1.0,
        'ramp_pwm_per_loop': 1,
        'pwm_max': 93,
        'kalman_Q': 0.0001,
        'maintenance_interval_h': 13140,
        'maintenance_duration_h': 1080,
        'arduino_pin': 2,
    },
    '태안': {
        'capacity_mw': 6100,
        'fuel_type': 'coal',
        'location': (36.75, 126.30),
        'distance_yongin_km': 140,
        'tx_loss_ratio': 0.042,
        'cost_a': 1.2, 'cost_b': 85.0, 'cost_c': 500.0,
        'p_min_ratio': 0.40,
        'p_max_ratio': 1.00,
        'ramp_rate_pct_per_min': 3.0,
        'ramp_pwm_per_loop': 3,
        'pwm_max': 66,
        'kalman_Q': 0.0020,
        'maintenance_interval_h': 8760,
        'maintenance_duration_h': 720,
        'arduino_pin': 3,
    },
    '보령': {
        'capacity_mw': 4419,
        'fuel_type': 'coal',
        'location': (36.33, 126.61),
        'distance_yongin_km': 120,
        'tx_loss_ratio': 0.036,
        'cost_a': 1.2, 'cost_b': 88.0, 'cost_c': 500.0,
        'p_min_ratio': 0.40,
        'p_max_ratio': 1.00,
        'ramp_rate_pct_per_min': 3.0,
        'ramp_pwm_per_loop': 3,
        'pwm_max': 48,
        'kalman_Q': 0.0020,
        'maintenance_interval_h': 8760,
        'maintenance_duration_h': 720,
        'arduino_pin': 4,
    },
    '인천': {
        'capacity_mw': 2400,
        'fuel_type': 'lng',
        'location': (37.45, 126.70),
        'distance_yongin_km': 60,
        'tx_loss_ratio': 0.018,
        'cost_a': 2.0, 'cost_b': 130.0, 'cost_c': 200.0,
        'p_min_ratio': 0.10,
        'p_max_ratio': 1.00,
        'ramp_rate_pct_per_min': 8.0,
        'ramp_pwm_per_loop': 8,
        'pwm_max': 26,
        'kalman_Q': 0.0080,
        'maintenance_interval_h': 4380,
        'maintenance_duration_h': 336,
        'arduino_pin': 5,
    },
    '울산': {
        'capacity_mw': 2072,
        'fuel_type': 'lng',
        'location': (35.55, 129.31),
        'distance_yongin_km': 330,
        'tx_loss_ratio': 0.099,
        'cost_a': 2.0, 'cost_b': 135.0, 'cost_c': 200.0,
        'p_min_ratio': 0.10,
        'p_max_ratio': 1.00,
        'ramp_rate_pct_per_min': 8.0,
        'ramp_pwm_per_loop': 8,
        'pwm_max': 22,
        'kalman_Q': 0.0080,
        'maintenance_interval_h': 4380,
        'maintenance_duration_h': 336,
        'arduino_pin': 6,
    },
}

# 발전소 이름 순서 (인덱스 일관성 유지)
PLANT_NAMES = ['한울', '태안', '보령', '인천', '울산']

# ───────────────────────────────────────────────
# 용인 반도체 클러스터 스펙
# ───────────────────────────────────────────────
YONGIN_SPEC = {
    'location': (37.24, 127.20),
    'target_2027_gw': 3.0,
    'target_2030_gw': 6.0,
    'sim_max_gw': 3.0,
    'baseload_ratio': 0.85,
    'pqi_threshold': 0.990,
    'ups_buffer_alpha': 0.15,
}

# ───────────────────────────────────────────────
# 시스템 전역 상수
# ───────────────────────────────────────────────
SMPS_VOLTAGE = 12.0           # V — SMPS 출력 전압
SMPS_MAX_CURRENT = 29.0       # A — SMPS 최대 전류
KALMAN_R = 0.0025             # 측정 노이즈 (KPX API 오차 ~5%)
SERIAL_BAUD = 9600

# 환경변수 오버라이드 가능 (하드코딩 방지)
import os
SERIAL_PORT = os.environ.get('SERIAL_PORT', 'COM3')
API_UPDATE_INTERVAL_SEC = 300   # 5분
CONTROL_LOOP_INTERVAL_SEC = 1.0
ARDUINO_LOOP_MS = 100

# 계통 안정도 파라미터
ISLAND_GRID_INERTIA_H = 3.9   # 한국 섬계통 관성상수 (초)
NOMINAL_FREQUENCY_HZ = 60.0
OLD_RESERVE_RATIO = 0.15      # 기존 고정 예비율

# 전국 설비용량 (2024 기준, 발전소 추정 출력 계산용)
NATIONAL_CAPACITY_MW = {
    'nuclear': 26988,
    'coal': 30000,
    'lng': 41000,
}

# KPX API 키 (환경변수에서 읽기)
KPX_API_KEY = os.environ.get(
    'KPX_API_KEY',
    'f3ffae63bd0cf03c4ca275b9804bb2f1cb8fa5003b2531dfd0011c2e2e9a622d'
)

# 대시보드 포트
DASH_PORT = int(os.environ.get('DASH_PORT', '8050'))

# 연료별 색상 (대시보드용)
FUEL_COLORS = {
    'nuclear': '#1f77b4',   # 파랑
    'coal': '#ff7f0e',      # 주황
    'lng': '#2ca02c',       # 초록
}

# 채널별 최대 전류 계산 (PWM 비례)
# 각 채널 최대 전류 = SMPS_MAX_CURRENT × (pwm_max / 255)
CHANNEL_MAX_CURRENT = {
    name: SMPS_MAX_CURRENT * (profile['pwm_max'] / 255)
    for name, profile in PLANT_PROFILE.items()
}
