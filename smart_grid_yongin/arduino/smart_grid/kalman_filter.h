/**
 * kalman_filter.h — 1D Kalman Filter (채널별 독립 실행)
 * 센서 노이즈 제거 및 상태 추정
 */

#pragma once
#include "config.h"

/**
 * 1차원 Kalman Filter 구조체
 * 각 발전소 채널별로 독립 인스턴스 생성
 */
struct KalmanFilter1D {
    float x;   // 상태 추정값 (전류, A)
    float P;   // 오차 공분산
    float Q;   // 시스템 노이즈 (연료별 다름)
    float R;   // 측정 노이즈 (ACS712 노이즈)
    float A;   // 상태 전이 (1.0 = 단위 시간 동일)
    float H;   // 측정 행렬 (1.0 = 직접 관측)
};

/**
 * Kalman Filter 초기화
 * x0: 초기 상태 추정값 (예: p_min 기준 전류)
 */
inline void kalman_init(KalmanFilter1D* kf, float Q, float R, float x0) {
    kf->x = x0;
    kf->P = 1.0f;
    kf->Q = Q;
    kf->R = R;
    kf->A = 1.0f;
    kf->H = 1.0f;
}

/**
 * 사전 추정 단계 (측정 없이 상태 전파)
 * API 업데이트 없는 사이 매 루프 호출
 */
inline float kalman_predict(KalmanFilter1D* kf) {
    // 상태 예측
    kf->x = kf->A * kf->x;
    // 공분산 예측
    kf->P = kf->A * kf->P * kf->A + kf->Q;
    return kf->x;
}

/**
 * 사후 추정 단계 (측정값 z로 상태 보정)
 * ACS712 전류값 수신 시 호출
 */
inline float kalman_update(KalmanFilter1D* kf, float z) {
    // 칼만 이득 계산
    float K = (kf->P * kf->H) / (kf->H * kf->P * kf->H + kf->R);
    // 상태 업데이트
    kf->x = kf->x + K * (z - kf->H * kf->x);
    // 공분산 업데이트
    kf->P = (1.0f - K * kf->H) * kf->P;
    // 음수 전류 방지
    if (kf->x < 0.0f) kf->x = 0.0f;
    return kf->x;
}

/**
 * 5개 채널 Kalman Filter 배열 초기화
 * p_min_currents[i] = 채널 i의 p_min 기준 전류값 (초기 추정)
 */
inline void kalman_init_all(
    KalmanFilter1D kf[N_PLANTS],
    const float p_min_currents[N_PLANTS]
) {
    // Q 값: 연료별 시스템 노이즈
    static const float Q_VALUES[N_PLANTS] = {
        KALMAN_Q_NUCLEAR,  // 한울 (원자력)
        KALMAN_Q_COAL,     // 태안 (석탄)
        KALMAN_Q_COAL,     // 보령 (석탄)
        KALMAN_Q_LNG,      // 인천 (LNG)
        KALMAN_Q_LNG,      // 울산 (LNG)
    };
    for (int i = 0; i < N_PLANTS; i++) {
        kalman_init(&kf[i], Q_VALUES[i], KALMAN_R, p_min_currents[i]);
    }
}
