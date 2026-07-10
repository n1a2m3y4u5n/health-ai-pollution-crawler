# 건강정보 AI 오염 실태 연구 - 크롤링 모듈

## 파일 구조
```
config.py          ← API 키 & 키워드 설정 (여기만 수정하면 됨)
main_crawl.py      ← 메인 실행 파일
crawler_naver.py   ← 네이버 블로그 & 뉴스 (공식 API)
crawler_daum.py    ← 티스토리 & 브런치 (HTML 파싱)
```

## 1. 패키지 설치
```bash
pip install requests beautifulsoup4
```

## 2. API 키 입력
`config.py` 열어서 아래 두 줄 수정:
```python
NAVER_CLIENT_ID     = "발급받은_Client_ID"
NAVER_CLIENT_SECRET = "발급받은_Client_Secret"
```

## 3. 실행
```bash
python main_crawl.py
```

완료되면 `data/health_blog_raw.csv` 생성됨 (최대 24,000개)

## 4. 수집량 조정
`config.py`에서:
```python
POSTS_PER_KEYWORD = 100  # 줄이면 빠르게 테스트 가능
```

## 5. 플랫폼 일부만 테스트할 때
`main_crawl.py` 마지막 줄 수정:
```python
run_all(platforms=["naver_blog"], output_file="test.csv")
```

## 주의사항
- 티스토리/브런치는 Daum HTML 파싱이라 서버 응답에 따라
  수집량이 목표보다 적을 수 있음 (정상)
- 네이버 API 일일 한도: 25,000건 → 60키워드 × 2 플랫폼 = 120건이라 여유 있음
- 크롤링 중 오류 나도 다른 키워드는 계속 진행됨
