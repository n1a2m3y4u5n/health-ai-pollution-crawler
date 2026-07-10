# 데이터 디렉토리

## EPSIS 데이터 다운로드

한국전력거래소 EPSIS(전력통계정보시스템)에서 실제 발전소 데이터를 다운로드할 수 있습니다.

### 접속 방법
1. http://epsis.kpx.or.kr 접속
2. 「발전현황」→「발전기별 발전량」메뉴
3. 기간: 원하는 날짜 범위 선택
4. 발전소: 한울, 태안, 보령, 인천(LNG), 울산(LNG) 선택
5. Excel 다운로드 → `data/` 폴더에 저장

### 공공데이터포털 API 활용

```
현재전력수급현황: https://data.go.kr/data/15056640/openapi.do
발전원별 발전량:  https://data.go.kr/data/15113384/openapi.do
```

API 키는 환경변수로 설정:
```bash
export KPX_API_KEY="your_api_key_here"
```

API 키 없이도 시뮬레이션 모드로 실행 가능:
```bash
python main.py --simulate
```
