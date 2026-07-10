/**
 * mosfet_controller.h — MOSFET PWM 출력 제어
 * Ramping 제한, 고장 감지, 재배분 기능 포함
 */

#pragma once
#include "config.h"

// PWM 핀 배열 (인덱스: 한울=0, 태안=1, 보령=2, 인천=3, 울산=4)
static const int PWM_PINS[N_PLANTS] = {
    PIN_PWM_HANUL, PIN_PWM_TAEAN, PIN_PWM_BORYEONG,
    PIN_PWM_INCHEON, PIN_PWM_ULSAN
};

// LED 핀 배열
static const int LED_PINS[N_PLANTS] = {
    PIN_LED_HANUL, PIN_LED_TAEAN, PIN_LED_BORYEONG,
    PIN_LED_INCHEON, PIN_LED_ULSAN
};

// Ramping 제한 (루프당 최대 PWM 변화)
static const int RAMP_LIMITS[N_PLANTS] = {
    RAMP_HANUL, RAMP_TAEAN, RAMP_BORYEONG, RAMP_INCHEON, RAMP_ULSAN
};

// PWM 최대값 (설비용량 비례)
static const int PWM_MAX_VALUES[N_PLANTS] = {
    PWM_MAX_HANUL, PWM_MAX_TAEAN, PWM_MAX_BORYEONG,
    PWM_MAX_INCHEON, PWM_MAX_ULSAN
};

// 현재 PWM 값 (ramping 추적용)
static int current_pwm[N_PLANTS] = {0, 0, 0, 0, 0};

// 고장 플래그
static bool fault_flags[N_PLANTS] = {false, false, false, false, false};

/**
 * PWM 출력 설정 (ramping 제한 적용)
 * @param channel  채널 인덱스 (0~4)
 * @param target   목표 PWM (0~255)
 * @param max_delta 루프당 최대 변화량
 */
inline void set_pwm_with_ramp(int channel, int target_pwm, int max_delta) {
    target_pwm = constrain(target_pwm, 0, PWM_MAX_VALUES[channel]);
    int delta = target_pwm - current_pwm[channel];

    // Ramping 제한 적용
    if (delta > max_delta)  delta = max_delta;
    if (delta < -max_delta) delta = -max_delta;

    current_pwm[channel] = current_pwm[channel] + delta;
    current_pwm[channel] = constrain(current_pwm[channel], 0, PWM_MAX_VALUES[channel]);

    analogWrite(PWM_PINS[channel], current_pwm[channel]);
}

/**
 * 고장 감지: 명령 대비 실측 전류 편차 > 30% 시 고장 판정
 * @param channel         채널 인덱스
 * @param commanded_ratio 명령 출력 비율 (0~1)
 * @param measured_ratio  실측 전류 비율 (0~1)
 * @return true = 고장 감지
 */
inline bool detect_fault(int channel, float commanded_ratio, float measured_ratio) {
    // 저출력 구간에서는 편차 허용 범위 확대
    if (commanded_ratio < 0.1f) return false;

    float deviation = abs(commanded_ratio - measured_ratio) / max(commanded_ratio, 0.01f);
    fault_flags[channel] = (deviation > FAULT_THRESHOLD);
    return fault_flags[channel];
}

/**
 * 고장 채널 출력을 나머지 채널에 비례 재배분
 * @param failed_channel  고장 채널 인덱스
 * @param pwm_targets     PWM 목표값 배열 (입출력, 재배분 결과 반영)
 */
inline void redistribute_on_fault(int failed_channel, float pwm_targets[N_PLANTS]) {
    float failed_pwm = pwm_targets[failed_channel];
    pwm_targets[failed_channel] = 0.0f;   // 고장 채널 출력 0

    // 나머지 채널에 여유 용량 비례 배분
    float total_headroom = 0.0f;
    for (int i = 0; i < N_PLANTS; i++) {
        if (i == failed_channel) continue;
        float headroom = PWM_MAX_VALUES[i] - pwm_targets[i];
        if (headroom > 0) total_headroom += headroom;
    }

    if (total_headroom < 1.0f) return;  // 여유 없음

    for (int i = 0; i < N_PLANTS; i++) {
        if (i == failed_channel) continue;
        float headroom = PWM_MAX_VALUES[i] - pwm_targets[i];
        if (headroom <= 0) continue;
        float share = failed_pwm * (headroom / total_headroom);
        pwm_targets[i] = constrain(pwm_targets[i] + share, 0.0f, (float)PWM_MAX_VALUES[i]);
    }
}

/**
 * 모든 PWM 핀 초기화 (p_min 기준)
 */
inline void mosfet_init() {
    // p_min 비율 (원자력=0.80, 석탄=0.40, LNG=0.10)
    static const float P_MIN[N_PLANTS] = {
        P_MIN_RATIO_NUCLEAR,  // 한울
        P_MIN_RATIO_COAL,     // 태안
        P_MIN_RATIO_COAL,     // 보령
        P_MIN_RATIO_LNG,      // 인천
        P_MIN_RATIO_LNG,      // 울산
    };
    for (int i = 0; i < N_PLANTS; i++) {
        pinMode(PWM_PINS[i], OUTPUT);
        current_pwm[i] = (int)(P_MIN[i] * PWM_MAX_VALUES[i]);
        analogWrite(PWM_PINS[i], current_pwm[i]);
    }
}
