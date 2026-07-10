/**
 * sensor_reader.h — ACS712-20A 전류 센서 읽기
 * 감도: 100mV/A, 기준전압: 2.5V
 */

#pragma once
#include "config.h"

/**
 * ADC 값 → 암페어 변환
 * 공식: current = (voltage - 2.5) / 0.1
 */
inline float voltage_to_current(int adc_val) {
    // ADC → 전압 변환 (5V 레퍼런스, 10-bit)
    float voltage = adc_val * (ADC_VREF / ADC_RESOLUTION);
    // ACS712: (V - Vref) / sensitivity
    float current = (voltage - ACS712_VREF) / ACS712_SENSITIVITY;
    return current;
}

/**
 * 아날로그 핀 읽기 → 암페어 변환
 * 과샘플링 8회 평균으로 노이즈 감소
 */
inline float read_current_raw(int pin) {
    long sum = 0;
    // 8회 샘플 평균 (ADC 노이즈 감소)
    for (int i = 0; i < 8; i++) {
        sum += analogRead(pin);
        delayMicroseconds(100);
    }
    int avg_adc = sum / 8;
    float current = voltage_to_current(avg_adc);
    // 음수 전류 방지 (역방향 없음)
    return max(0.0f, current);
}

/**
 * 5개 채널 전류 일괄 읽기
 * currents[0~4] = 한울,태안,보령,인천,울산 순서
 */
inline void read_all_currents(float currents[N_PLANTS]) {
    static const int PINS[N_PLANTS] = {
        PIN_CURR_HANUL, PIN_CURR_TAEAN, PIN_CURR_BORYEONG,
        PIN_CURR_INCHEON, PIN_CURR_ULSAN
    };
    for (int i = 0; i < N_PLANTS; i++) {
        currents[i] = read_current_raw(PINS[i]);
    }
}
