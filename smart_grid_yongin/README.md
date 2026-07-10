# 지능형 전력망 시스템 — 용인 반도체 클러스터 전력 공급 최적화

## 프로젝트 개요

용인 반도체 클러스터(2027년 3GW 수요 목표)의 전력 공급 문제를 해결하기 위해, 전국 5개 발전소에서 지능형 전력망을 통해 최적 급전하는 하드웨어+소프트웨어 통합 시스템입니다.

**핵심 주장:** 지능형 전력망 도입 시 회전예비력을 기존 고정 15%에서 동적 5~8%로 줄일 수 있으며, 확보된 여유 전력을 용인 반도체 클러스터에 추가 공급할 수 있습니다.

## 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 시뮬레이션 모드 실행 (Arduino 불필요)

```bash
cd python
python main.py --simulate
```

브라우저에서 `http://localhost:8050` 접속

### 3. 고장 시뮬레이션

```bash
python main.py --simulate --fault 한울
```

### 4. Arduino 연결 실행

```bash
# Windows
SERIAL_PORT=COM3 python main.py

# Linux/Mac
SERIAL_PORT=/dev/ttyUSB0 python main.py
```

### 5. 대시보드만 독립 실행

```bash
cd python/dashboard
python app.py
```

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SIMULATE` | `0` | `1`이면 시뮬레이션 모드 |
| `SERIAL_PORT` | `COM3` | Arduino 시리얼 포트 |
| `KPX_API_KEY` | 내장값 | 한국전력거래소 API 키 |
| `DASH_PORT` | `8050` | 대시보드 포트 |

## 시스템 구성

### Python 모듈

| 파일 | 역할 |
|---|---|
| `main.py` | 시스템 진입점 (3개 루프 통합) |
| `config.py` | 발전소 파라미터, 시스템 상수 |
| `grid_data_manager.py` | Kalman Filter + KPX API 통합 |
| `digital_twin.py` | 물리 회로 디지털 미러 |
| `empc_engine.py` | Economic MPC (최적 급전) |
| `q_learning_agent.py` | Q-Learning 급전 에이전트 |
| `monte_carlo_reserve.py` | Monte Carlo 예비력 계산 |
| `demand_response.py` | 한국 수요반응(DR) 시뮬레이터 |
| `yongin_load_model.py` | 용인 반도체 클러스터 부하 모델 |
| `serial_bridge.py` | Arduino 시리얼 통신 |
| `kpx_api.py` | KPX 공공데이터 API 클라이언트 |

### Arduino 펌웨어

| 파일 | 역할 |
|---|---|
| `smart_grid.ino` | 메인 스케치 |
| `config.h` | 핀 배치, 상수 정의 |
| `kalman_filter.h` | 1D Kalman Filter |
| `fuzzy_logic.h` | Fuzzy Logic Controller |
| `mosfet_controller.h` | PWM 출력 제어 |
| `sensor_reader.h` | ACS712 전류 센서 읽기 |

## 5개 발전소

| 발전소 | 연료 | 설비용량 | 용인까지 |
|---|---|---|---|
| 한울 | 원자력 | 8,561 MW | 280 km |
| 태안 | 석탄 | 6,100 MW | 140 km |
| 보령 | 석탄 | 4,419 MW | 120 km |
| 인천 | LNG | 2,400 MW | 60 km |
| 울산 | LNG | 2,072 MW | 330 km |

## 검증 기준

1. `python main.py --simulate` — Arduino 없이 전체 시스템 실행
2. 대시보드 `http://localhost:8050` 정상 렌더링
3. 한국 지도에 발전소 마커 + 전력 흐름 라인
4. 2초마다 수치 자동 업데이트
5. EMPC vs Q-Learning 비용 비교 차트
6. 예비력 절감 수치 가시화 (기존 15% → 스마트 5~8%)
7. `--fault 한울` 고장 시뮬레이션 → 자동 재배분 + 경보
