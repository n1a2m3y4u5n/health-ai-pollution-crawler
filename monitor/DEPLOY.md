# 배포 가이드

## 1. 네이버 메일 SMTP 설정 (먼저 해야 함)

1. 네이버 메일 접속 → 우측 상단 **환경설정** → **POP3/IMAP 설정**
2. **SMTP 사용** → **사용함** 체크 후 저장

> 2단계 인증을 쓰는 경우: 네이버 앱에서 **앱 비밀번호** 발급 후 그 비밀번호 사용

---

## 2. fly.io 계정 및 CLI 준비

```bash
# flyctl 설치 (Mac)
brew install flyctl

# 로그인
fly auth login
```

---

## 3. 앱 생성 & 볼륨 생성

```bash
cd monitor/

# 앱 생성 (이름 충돌 시 fly.toml에서 app 이름 변경)
fly apps create eicon-monitor

# 영속 볼륨 생성 (1GB, 무료 범위)
fly volumes create eicon_monitor_data --region nrt --size 1
```

---

## 4. 환경변수(시크릿) 설정

```bash
fly secrets set \
  NAVER_EMAIL="your_id@naver.com" \
  NAVER_PASSWORD="your_password" \
  NOTIFY_EMAIL="n1a2m3y4u5n@gmail.com"
```

---

## 5. 배포

```bash
fly deploy
```

---

## 6. 동작 확인

```bash
# 실시간 로그
fly logs

# 정상 출력 예시:
# [init] 기준선 설정 중...
# → 공지사항: 20건 기록
# → Q&A: 30건 기록
# [init] 기준선 설정 완료. 이후 새 글부터 알림 발송.
# [cron] 스케줄 시작 — "*/15 * * * *"
```

---

## 자주 쓰는 명령

| 작업 | 명령 |
|---|---|
| 로그 보기 | `fly logs` |
| 앱 상태 | `fly status` |
| 재시작 | `fly apps restart eicon-monitor` |
| 환경변수 수정 | `fly secrets set KEY=VALUE` |
| 중지 | `fly apps suspend eicon-monitor` |
| 재개 | `fly apps resume eicon-monitor` |

---

## 비용

- shared-cpu-1x + 256MB: 무료 할당량 내 (월 $0)
- 볼륨 1GB: 무료 할당량 내 (월 $0)
