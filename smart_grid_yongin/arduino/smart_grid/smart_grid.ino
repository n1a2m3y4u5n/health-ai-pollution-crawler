/**
 * smart_grid.ino — 지능형 전력망 Arduino MEGA 메인 스케치
 * 5개 MOSFET으로 발전소 출력 재현 + PC와 시리얼 통신
 *
 * 핀 배치:
 *   PWM: D2(한울) D3(태안) D4(보령) D5(인천) D6(울산)
 *   ADC: A0~A4 (ACS712-20A 전류 센서)
 *   Serial1(18,19): PC 통신 (9600 baud)
 *   LED: D22~D26 (채널 상태), D13 (시스템)
 */

#include "config.h"
#include "sensor_reader.h"
#include "kalman_filter.h"
#include "fuzzy_logic.h"
#include "mosfet_controller.h"

// ─── 전역 상태 ──────────────────────────────────────────────────────
KalmanFilter1D kf[N_PLANTS];         // 채널별 Kalman Filter
float filtered_currents[N_PLANTS];   // Kalman 필터링 후 전류 (A)
float raw_currents[N_PLANTS];        // ACS712 원시 전류 (A)
float target_pwm_f[N_PLANTS];        // PC에서 받은 목표 PWM (float)
float prev_error[N_PLANTS];          // Fuzzy Logic 이전 오차

unsigned long last_pc_cmd_ms = 0;    // 마지막 PC 명령 수신 시각
unsigned long last_loop_ms   = 0;    // 루프 타이밍

bool system_fault = false;           // 시스템 전반 고장 여부
int  fault_channel = -1;             // 고장 채널 (-1: 없음)

// ─── LED 상태 관리 ──────────────────────────────────────────────────
unsigned long led_toggle_ms[N_PLANTS] = {0};
bool          led_state[N_PLANTS]     = {true};
unsigned long sys_led_toggle_ms = 0;
bool          sys_led_state     = false;

// ─── 시리얼 수신 버퍼 ───────────────────────────────────────────────
#define RX_BUF_SIZE 64
char rx_buf[RX_BUF_SIZE];
int  rx_pos = 0;

// ─── setup() ────────────────────────────────────────────────────────
void setup() {
    // USB 디버그용 시리얼
    Serial.begin(115200);
    Serial.println(F("[SmartGrid] 부팅 시작"));

    // PC 통신용 Serial1 (핀 18/19)
    Serial1.begin(SERIAL_BAUD);

    // 시스템 LED 초기화
    pinMode(PIN_LED_SYSTEM, OUTPUT);
    for (int i = 0; i < N_PLANTS; i++) {
        pinMode(LED_PINS[i], OUTPUT);
        digitalWrite(LED_PINS[i], LOW);
    }

    // MOSFET 핀 초기화 (p_min 기준 PWM)
    mosfet_init();

    // ACS712 초기 전류 읽기 (p_min 기준 초기값)
    read_all_currents(raw_currents);
    for (int i = 0; i < N_PLANTS; i++) {
        filtered_currents[i] = raw_currents[i];
        target_pwm_f[i]      = (float)current_pwm[i];
        prev_error[i]        = 0.0f;
    }

    // Kalman Filter 초기화 (채널별 Q 값, 초기 전류값으로 x0 설정)
    kalman_init_all(kf, filtered_currents);

    // 부팅 확인 LED 시퀀스 (순차 점멸)
    for (int i = 0; i < N_PLANTS; i++) {
        digitalWrite(LED_PINS[i], HIGH);
        delay(150);
        digitalWrite(LED_PINS[i], LOW);
    }
    digitalWrite(PIN_LED_SYSTEM, HIGH);

    last_pc_cmd_ms = millis();
    last_loop_ms   = millis();
    Serial.println(F("[SmartGrid] 초기화 완료"));
}

// ─── loop() — 100ms 주기 ────────────────────────────────────────────
void loop() {
    unsigned long now = millis();

    // 100ms 주기 적용
    if (now - last_loop_ms < LOOP_INTERVAL_MS) return;
    last_loop_ms = now;

    // ① 전류 센서 읽기 (ACS712-20A)
    read_all_currents(raw_currents);

    // ② Kalman Filter update (측정값 반영)
    for (int i = 0; i < N_PLANTS; i++) {
        filtered_currents[i] = kalman_update(&kf[i], raw_currents[i]);
    }

    // ③ Fuzzy Logic PWM 보정
    //    목표 전류 = target_pwm / 255 × 채널_최대_전류
    static const float MAX_CURRENTS[N_PLANTS] = {
        // 각 채널 최대 전류 = SMPS_MAX_CURRENT × (pwm_max/255)
        29.0f * (PWM_MAX_HANUL    / 255.0f),
        29.0f * (PWM_MAX_TAEAN    / 255.0f),
        29.0f * (PWM_MAX_BORYEONG / 255.0f),
        29.0f * (PWM_MAX_INCHEON  / 255.0f),
        29.0f * (PWM_MAX_ULSAN    / 255.0f),
    };

    float fuzzy_pwm[N_PLANTS];
    for (int i = 0; i < N_PLANTS; i++) {
        float target_current = (target_pwm_f[i] / 255.0f) * MAX_CURRENTS[i];
        float max_c = MAX_CURRENTS[i];
        if (max_c < 0.01f) { fuzzy_pwm[i] = target_pwm_f[i]; continue; }

        float e  = (target_current - filtered_currents[i]) / max_c;
        float de = e - prev_error[i];
        prev_error[i] = e;

        float delta = fuzzy_compute(e, de);
        // Ramping 제한 내에서 보정 적용
        delta = constrain(delta, -(float)RAMP_LIMITS[i], (float)RAMP_LIMITS[i]);
        fuzzy_pwm[i] = constrain(target_pwm_f[i] + delta, 0.0f, (float)PWM_MAX_VALUES[i]);
    }

    // ④ Ramping 제한 적용 후 PWM 출력
    for (int i = 0; i < N_PLANTS; i++) {
        if (fault_flags[i]) {
            // 고장 채널: PWM 0
            set_pwm_with_ramp(i, 0, RAMP_LIMITS[i]);
        } else {
            set_pwm_with_ramp(i, (int)fuzzy_pwm[i], RAMP_LIMITS[i]);
        }
    }

    // ⑤ 고장 감지 (명령 대비 실측 편차 > 30%)
    for (int i = 0; i < N_PLANTS; i++) {
        float cmd_ratio  = target_pwm_f[i] / (float)PWM_MAX_VALUES[i];
        float meas_ratio = (MAX_CURRENTS[i] > 0.01f)
            ? filtered_currents[i] / MAX_CURRENTS[i]
            : 0.0f;
        if (detect_fault(i, cmd_ratio, meas_ratio)) {
            if (fault_channel != i) {
                fault_channel = i;
                Serial.print(F("[FAULT] 채널 고장 감지: "));
                Serial.println(i);
                // 나머지 채널에 재배분
                redistribute_on_fault(i, target_pwm_f);
            }
        }
    }

    // ⑥ Arduino → PC 전송: "S,c0,c1,c2,c3,c4\n"
    Serial1.print('S');
    for (int i = 0; i < N_PLANTS; i++) {
        Serial1.print(',');
        Serial1.print(filtered_currents[i], 3);
    }
    Serial1.println();

    // ⑦ PC → Arduino 수신: "C,p0,p1,p2,p3,p4\n"
    while (Serial1.available()) {
        char c = Serial1.read();
        if (c == '\n') {
            rx_buf[rx_pos] = '\0';
            parse_pc_command(rx_buf);
            rx_pos = 0;
            last_pc_cmd_ms = now;
        } else if (rx_pos < RX_BUF_SIZE - 1) {
            rx_buf[rx_pos++] = c;
        }
    }

    // 하트비트: PC 타임아웃 시 마지막 명령 유지 (아무 동작 없음)
    // (target_pwm_f가 변경되지 않으면 자동 유지됨)

    // ⑧ LED 상태 업데이트
    update_leds(now);
}

// ─── PC 명령 파싱 ────────────────────────────────────────────────────
void parse_pc_command(const char* buf) {
    // 형식: "C,93,47,34,18,15"
    if (buf[0] != 'C') return;

    int idx = 0;
    const char* p = buf + 2;  // 'C,' 이후부터

    while (*p && idx < N_PLANTS) {
        target_pwm_f[idx] = (float)atoi(p);
        target_pwm_f[idx] = constrain(target_pwm_f[idx], 0.0f, (float)PWM_MAX_VALUES[idx]);
        idx++;
        // 다음 쉼표로 이동
        while (*p && *p != ',') p++;
        if (*p == ',') p++;
    }
}

// ─── LED 상태 업데이트 ───────────────────────────────────────────────
void update_leds(unsigned long now) {
    // 채널 LED: 정상=ON, 고장=BLINK(5Hz)
    for (int i = 0; i < N_PLANTS; i++) {
        if (fault_flags[i]) {
            if (now - led_toggle_ms[i] >= LED_BLINK_FAULT_MS) {
                led_state[i] = !led_state[i];
                digitalWrite(LED_PINS[i], led_state[i] ? HIGH : LOW);
                led_toggle_ms[i] = now;
            }
        } else {
            digitalWrite(LED_PINS[i], HIGH);
        }
    }

    // 시스템 LED: 정상=1Hz, 경고=5Hz
    unsigned long blink_interval = system_fault ? LED_BLINK_FAULT_MS : LED_BLINK_NORMAL_MS;
    if (now - sys_led_toggle_ms >= blink_interval) {
        sys_led_state = !sys_led_state;
        digitalWrite(PIN_LED_SYSTEM, sys_led_state ? HIGH : LOW);
        sys_led_toggle_ms = now;
    }
}
