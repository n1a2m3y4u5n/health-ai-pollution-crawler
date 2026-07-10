/**
 * config.h — Arduino 핀 배치 및 전역 상수 정의
 * 용인 반도체 클러스터 전력 공급 최적화 프로젝트
 */

#pragma once

// ─── PWM 출력 핀 (발전소별 MOSFET 게이트) ─────────────────────────
#define PIN_PWM_HANUL     2    // 한울 (원자력, 8561MW)
#define PIN_PWM_TAEAN     3    // 태안 (석탄, 6100MW)
#define PIN_PWM_BORYEONG  4    // 보령 (석탄, 4419MW)
#define PIN_PWM_INCHEON   5    // 인천 (LNG, 2400MW)
#define PIN_PWM_ULSAN     6    // 울산 (LNG, 2072MW)

// ─── 아날로그 입력 핀 (ACS712-20A 전류 센서) ───────────────────────
#define PIN_CURR_HANUL    A0
#define PIN_CURR_TAEAN    A1
#define PIN_CURR_BORYEONG A2
#define PIN_CURR_INCHEON  A3
#define PIN_CURR_ULSAN    A4

// ─── LED 상태 표시 핀 ──────────────────────────────────────────────
#define PIN_LED_HANUL     22   // 한울 상태 (ON=정상, BLINK=고장)
#define PIN_LED_TAEAN     23
#define PIN_LED_BORYEONG  24
#define PIN_LED_INCHEON   25
#define PIN_LED_ULSAN     26
#define PIN_LED_SYSTEM    13   // 시스템 상태 (1Hz=정상, 5Hz=경고)

// ─── 발전소 수 ─────────────────────────────────────────────────────
#define N_PLANTS          5

// ─── 시리얼 통신 ───────────────────────────────────────────────────
#define SERIAL_BAUD       9600  // PC ↔ Arduino 통신 속도

// ─── 제어 타이밍 ───────────────────────────────────────────────────
#define LOOP_INTERVAL_MS  100  // 메인 루프 주기 (ms)
#define PC_TIMEOUT_MS     3000 // PC 명령 타임아웃 (ms), 초과 시 마지막 명령 유지

// ─── PWM 최대값 (설비용량 비례: 255 × 용량/총용량) ────────────────
#define PWM_MAX_HANUL     93   // 8561 / 23552 × 255 ≈ 93
#define PWM_MAX_TAEAN     66   // 6100 / 23552 × 255 ≈ 66
#define PWM_MAX_BORYEONG  48   // 4419 / 23552 × 255 ≈ 48
#define PWM_MAX_INCHEON   26   // 2400 / 23552 × 255 ≈ 26
#define PWM_MAX_ULSAN     22   // 2072 / 23552 × 255 ≈ 22

// ─── P_MIN 비율 (초기 PWM 설정 기준) ──────────────────────────────
// 원자력 80%, 석탄 40%, LNG 10%
#define P_MIN_RATIO_NUCLEAR  0.80f
#define P_MIN_RATIO_COAL     0.40f
#define P_MIN_RATIO_LNG      0.10f

// ─── ACS712-20A 전류 센서 파라미터 ────────────────────────────────
#define ACS712_SENSITIVITY  0.1f    // 100mV/A
#define ACS712_VREF         2.5f    // 기준 전압 (V)
#define ADC_VREF            5.0f    // Arduino ADC 기준 전압
#define ADC_RESOLUTION      1024.0f // 10-bit ADC

// ─── 고장 감지 임계값 ──────────────────────────────────────────────
#define FAULT_THRESHOLD     0.30f   // 명령 대비 실측 편차 30% 초과 시 고장

// ─── Ramping 제한 (루프당 최대 PWM 변화) ───────────────────────────
#define RAMP_HANUL        1    // 원자력: 느림
#define RAMP_TAEAN        3    // 석탄
#define RAMP_BORYEONG     3    // 석탄
#define RAMP_INCHEON      8    // LNG: 빠름
#define RAMP_ULSAN        8    // LNG: 빠름

// ─── Kalman Filter 파라미터 ────────────────────────────────────────
#define KALMAN_Q_NUCLEAR  0.001f    // 원자력: 안정적 (노이즈 낮음)
#define KALMAN_Q_COAL     0.005f    // 석탄
#define KALMAN_Q_LNG      0.010f    // LNG: 변동성 높음
#define KALMAN_R          0.05f     // ACS712-20A 측정 노이즈

// ─── LED 점멸 주기 ─────────────────────────────────────────────────
#define LED_BLINK_FAULT_MS  200    // 고장 점멸 (5Hz)
#define LED_BLINK_WARN_MS   500    // 경고 점멸 (2Hz)
#define LED_BLINK_NORMAL_MS 1000   // 정상 점멸 (1Hz)
