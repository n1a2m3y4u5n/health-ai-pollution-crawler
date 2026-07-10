/**
 * fuzzy_logic.h — Fuzzy Logic Controller
 * EMPC 목표값 대비 실측 오차를 PWM 보정량으로 변환
 * 중심법(COG: Center of Gravity) 비퍼지화
 */

#pragma once
#include "config.h"

// ─── 멤버십 함수 파라미터 (사다리꼴) ─────────────────────────────────
// [a, b, c, d]: a=왼쪽 시작, b=최대 왼쪽, c=최대 오른쪽, d=오른쪽 끝
struct TrapMF {
    float a, b, c, d;
};

// e, de 각각 5개 멤버십 함수
static const TrapMF MF_NB = {-1.0f, -1.0f, -0.6f, -0.3f};
static const TrapMF MF_NS = {-0.6f, -0.3f, -0.3f,  0.0f};
static const TrapMF MF_ZE = {-0.1f,  0.0f,  0.0f,  0.1f};
static const TrapMF MF_PS = { 0.0f,  0.3f,  0.3f,  0.6f};
static const TrapMF MF_PB = { 0.3f,  0.6f,  1.0f,  1.0f};

// 출력 싱글톤 값 (비퍼지화용 COG 중심)
static const float OUT_NB = -8.0f;
static const float OUT_NS = -4.0f;
static const float OUT_ZE =  0.0f;
static const float OUT_PS =  4.0f;
static const float OUT_PB =  8.0f;

/**
 * 사다리꼴 멤버십 함수 계산
 */
inline float trapMF(const TrapMF& mf, float x) {
    if (x <= mf.a || x >= mf.d) return 0.0f;
    if (x >= mf.b && x <= mf.c) return 1.0f;
    if (x < mf.b) return (x - mf.a) / (mf.b - mf.a + 1e-6f);
    return (mf.d - x) / (mf.d - mf.c + 1e-6f);
}

/**
 * 규칙 테이블 (e × de → ΔPWM 출력 레벨)
 * 인덱스: 0=NB, 1=NS, 2=ZE, 3=PS, 4=PB
 * 값: 출력 레벨 인덱스 (0~4)
 */
static const int RULE_TABLE[5][5] = {
    // de:  NB   NS   ZE   PS   PB
    {0,  0,  1,  1,  2},  // e=NB
    {0,  1,  1,  2,  3},  // e=NS
    {1,  1,  2,  3,  3},  // e=ZE
    {1,  2,  3,  3,  4},  // e=PS
    {2,  3,  3,  4,  4},  // e=PB
};

static const float OUT_SINGLETONS[5] = {OUT_NB, OUT_NS, OUT_ZE, OUT_PS, OUT_PB};

/**
 * Fuzzy Logic 추론: 오차 e, 오차 변화율 de → ΔPWM
 *
 * @param e     (목표 - 실측) / 최대전류  정규화 오차 [-1, 1]
 * @param de    e(t) - e(t-1)             오차 변화율 [-1, 1]
 * @return      ΔPWM ∈ [-10, +10]
 */
inline float fuzzy_compute(float e, float de) {
    // 클리핑
    e  = constrain(e,  -1.0f, 1.0f);
    de = constrain(de, -1.0f, 1.0f);

    // 각 입력 변수의 5개 멤버십 값 계산
    float mu_e[5]  = {trapMF(MF_NB, e),  trapMF(MF_NS, e),  trapMF(MF_ZE, e),
                      trapMF(MF_PS, e),  trapMF(MF_PB, e)};
    float mu_de[5] = {trapMF(MF_NB, de), trapMF(MF_NS, de), trapMF(MF_ZE, de),
                      trapMF(MF_PS, de), trapMF(MF_PB, de)};

    // 규칙 발화 강도 → COG 비퍼지화
    float num = 0.0f, den = 0.0f;

    for (int i = 0; i < 5; i++) {
        for (int j = 0; j < 5; j++) {
            // AND = min
            float strength = min(mu_e[i], mu_de[j]);
            int out_idx = RULE_TABLE[i][j];
            num += strength * OUT_SINGLETONS[out_idx];
            den += strength;
        }
    }

    if (den < 1e-6f) return 0.0f;
    float delta_pwm = num / den;
    return constrain(delta_pwm, -10.0f, 10.0f);
}
