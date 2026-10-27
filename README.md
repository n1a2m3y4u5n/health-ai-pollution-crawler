# 건강정보 AI 생성 실태 분석: 크롤러와 분석 코드

온라인 건강 정보에 AI가 쓴 글이 얼마나 섞여 있는지 조사한 「건강정보 AI 생성 실태 분석」 연구의 수집, 분석 코드입니다.

- 수상: 제28회 전국학생통계활용대회 동상 (국가데이터처장상)

## 소개

검색하면 나오는 건강 정보 글 중 AI가 쓴 글의 비율과 특징을 알아보기 위한 고등학생 통계 연구입니다. 네이버, 다음(카카오) 등 여러 플랫폼에서 건강 키워드별 글을 모으고, 한국어 AI 글 탐지 방법(KatFishNet)을 적용해 AI 글을 가려낸 뒤 통계로 분석합니다. 이 저장소에는 수집 코드, 탐지 코드, 분석 스크립트, 수집 데이터와 분석 결과가 모두 들어 있습니다.

## 주요 기능

- 수집: 키워드를 위험도(상, 중, 하)와 카테고리(일반질환, 정신건강, 보완대체의학, 생활건강, 경증)로 나누어 글을 모읍니다.
  - 네이버 블로그, 뉴스는 공식 검색 API (`crawler_naver.py`)
  - 티스토리, 브런치는 Daum 검색 HTML 파싱 (`crawler_daum.py`)
  - 보충 수집: 네이버 카페, 다음 카페, 티스토리, 브런치 (`crawler_supplement.py`)
  - 연도별 시계열 수집 (`crawler_timeseries_v2.py`, `recrawl_timeseries_api.py`)
- AI 글 탐지: KatFishNet의 쉼표 사용 패턴 특징 5가지와 로지스틱 회귀를 사용합니다 (`run_katfishnet.py`).
- 분석 (`analysis_*.py`): 결과는 `results/`에 저장됩니다.
  - A. 플랫폼, 위험도, 카테고리별 AI 글 비율, 노출 순위와의 상관
  - B. 언어 통계 비교: 어휘 다양성(TTR), 엔트로피, 문장 유사도, 문장 길이
  - C. 품질 비교: AI, 비전문가, 전문가 글의 문체 비교, 의학 정보 오류 판정, 모델 붕괴 실험(반복 패러프레이징)
  - D. 설문 기반 인식 조사 분석
  - E. 연도별 AI 글 비율 변화
- 시뮬레이션: AI 글 점유율과 품질의 되먹임을 차분방정식으로 모형화 (`dead_internet_simulation.py`)

## 기술

- Python: requests, beautifulsoup4 (수집), pandas, numpy, scipy, scikit-learn, matplotlib (분석), kiwipiepy, kss (탐지)
- 데이터: CSV (`data/`), 결과표와 그림 (`results/`)

## 실행 방법

```bash
pip install requests beautifulsoup4
```

`config.py`의 API 키(네이버 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, 카카오 `KAKAO_REST_API_KEY`)를 본인이 발급한 값으로 채웁니다.

```bash
python main_crawl.py         # 수집, data/health_blog_raw.csv 생성
```

키워드당 수집 수는 `config.py`의 `POSTS_PER_KEYWORD`로 조절합니다. 일부 플랫폼만 시험하려면 `main_crawl.py` 마지막 줄을 `run_all(platforms=["naver_blog"], output_file="test.csv")`처럼 바꿉니다. 티스토리와 브런치는 HTML 파싱이라 서버 응답에 따라 수집량이 목표보다 적을 수 있습니다.

분석 스크립트(`analysis_full.py` 등)는 `data/`의 CSV를 읽어 `results/`에 저장합니다.

```bash
pip install pandas numpy scipy scikit-learn matplotlib
python analysis_full.py
```

## 이 저장소의 다른 폴더

- `monitor/`: e-ICON 게시판 새 글을 확인해 이메일로 알리는 Node.js 서비스
- 그 밖에 연구와 직접 관련 없는 `smart_grid_yongin/`, `vuln_board/`, `solution.py`, `verify.py`, 부하 시험 파일(`load_test.*`, `jmeter_results.csv`)이 함께 들어 있습니다.
