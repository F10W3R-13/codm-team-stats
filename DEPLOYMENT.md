# 배포 가이드 (Railway) — 초보용

이 문서는 **로컬에서 잘 돌아가는 CODM 스탯 봇+웹을 인터넷에 올리는(배포하는) 방법**을 한 단계씩 설명합니다.
배포 플랫폼은 **Railway**(레일웨이)를 사용합니다. 무료 트라이얼이 있고 설정이 가장 간단합니다.

> 💡 **배포가 뭐예요?** — 내 컴퓨터(로컬)에서만 켜져 있을 때만 봇/웹이 동작합니다.
> 배포하면 **클라우드(남의 컴퓨터)** 에서 24시간 켜져 있게 됩니다. 내 PC를 켜지 않아도 봇이 online으로 뜹니다.

---

## 전체 흐름 (5단계)

1. GitHub 저장소 준비 ✅ (이미 됨 — `F10W3R-13/codm-team-stats`)
2. Railway 가입 + 프로젝트 생성
3. PostgreSQL 데이터베이스 추가
4. 환경변수(비밀번호/키) 등록
5. 배포 → 확인

각 단계를 차례로 따라 하면 됩니다. **모르는 용어는 맨 아래 '용어 사전'을 보세요.**

---

## 사전 준비 체크리스트

배포 전에 이 값들을 손에 모아두세요. (README.md '사전 준비'에서 이미 발급받은 값들)

| 항목 | 어디서 구했는지 | 예시 |
|------|----------------|------|
| Discord 봇 토큰 | Discord Developer Portal | `MTIzNDU2...` |
| OpenAI API 키 | platform.openai.com | `sk-...` |
| Google 서비스 계정 JSON | Google Cloud Console | `service-account.json` 파일 전체 내용 |

---

## 1단계 — Railway 가입 및 프로젝트 생성

1. https://railway.com 접속 → **Login** (GitHub 계정으로 로그인 권장)
2. 로그인 후 대시보드에서 **New Project** 버튼 클릭
3. **Deploy from GitHub repo** 선택
4. `F10W3R-13/codm-team-stats` 저장소 선택
   - 안 보이면 **Configure GitHub App** 클릭 → 저장소 접근 권한 부여 후 다시 시도
5. 프로젝트가 생성되고, Railway가 자동으로 코드를 읽어 배포를 시도합니다
   - 이 시점에서는 **실패해도 됩니다** (환경변수가 아직 없어서). 다음 단계에서 고칩니다.

> ⚠️ Railway가 `start.py`를 어떻게 찾나요?
> 저장소 루트의 **`Procfile`** 이라는 파일에 `web: python start.py` 라고 적혀 있어서 Railway가 이 명령어로 앱을 실행합니다. (이미 설정됨)

---

## 2단계 — PostgreSQL 데이터베이스 추가

봇과 웹이 데이터를 저장할 DB를 추가합니다. (로컬의 `codm.db` 대신 클라우드 Postgres를 씁니다.)

1. Railway 프로젝트 화면에서 **+ (New)** 버튼 → **Database** → **Add PostgreSQL**
2. PostgreSQL 서비스가 생성됩니다 (1~2분 소요)
3. 생성되면 **`DATABASE_URL`** 이라는 환경변수가 자동으로 만들어집니다
   - 이 값은 **직접 입력하지 마세요**. Railway가 알아서 넣어줍니다.
   - 코드(`db.py`)는 `DATABASE_URL`이 있으면 Postgres 모드로 동작하도록 이미 짜여 있습니다.

---

## 3단계 — 환경변수 등록 (핵심 단계)

가장 중요합니다. **비밀 키들을 Railway에 등록**해야 봇이 정상 작동합니다.

1. Railway 프로젝트에서 웹 서비스(코드를 배포한 서비스) 클릭
2. **Variables** 탭 클릭
3. **New Variable** 버튼을 눌러 아래 3개를 하나씩 등록:

### 3-1. `DISCORD_BOT_TOKEN`
- Name: `DISCORD_BOT_TOKEN`
- Value: (Discord Developer Portal에서 복사한 봇 토큰)

### 3-2. `OPENAI_API_KEY`
- Name: `OPENAI_API_KEY`
- Value: `sk-...` (OpenAI에서 발급받은 키)

### 3-3. `GOOGLE_SERVICE_ACCOUNT_JSON` ⚠️ 중요
이 값은 **파일이 아니라 JSON 내용 통째로**를 넣어야 합니다. (Railway는 파일 업로드가 안 됩니다.)

**값 만드는 방법:**
1. 로컬의 `service-account.json` 파일을 메모장으로 열기
2. 내용 **전체**를 복사 (맨 처음 `{` 부터 맨 끝 `}` 까지)
3. Railway 변수 값란에 그대로 붙여넣기

예시 형태:
```
{"type":"service_account","project_id":"codm-stats-xxxxx","private_key_id":"...",...}
```

> 💡 **여러 줄이라도 괜찮습니다.** Railway는 자동으로 한 줄로 처리합니다. 그대로 붙여넣으세요.
>
> ⚠️ 주의: **`GOOGLE_SERVICE_ACCOUNT_FILE`은 등록하지 마세요.** 둘 다 있으면 충돌합니다.
> 배포 환경에서는 `GOOGLE_SERVICE_ACCOUNT_JSON`만 씁니다.

---

## 4단계 — 배포 확인

1. 환경변수 등록이 끝나면 Railway가 자동으로 재배포합니다
2. **Deployments** 탭에서 배포 상태 확인
   - ✅ 초록색 **Success** → 성공
   - ❌ 빨간색 **Failed** → 로그 확인 (아래 '문제 해결' 참조)
3. 성공하면 **Settings** 탭 → **Networking** → **Generate Domain** 클릭
   - `https://codm-team-stats-production.up.railway.app` 같은 주소가 발급됩니다
   - 이 주소로 접속하면 웹 대시보드가 뜹니다 🎉

### 봇이 online인지 확인
- Discord 서버에서 봇이 online(초록 점)으로 떠 있는지 확인
- 스크림 결과 채널에 스크린샷을 올려서 봇이 반응하는지 테스트

---

## 5단계 — 기존 데이터 옮기기 (선택이지만 권장)

로컬 `codm.db`에 이미 쌓인 매치 데이터를 클라우드 Postgres로 옮겨야 빈 대시보드가 아닙니다.

### 방법 A: 구글 시트에서 다시 가져오기 (권장)
Railway 콘솔에서 `import_sheets.py`를 실행해 구글 시트 → Postgres로 마이그레이션.

1. Railway 웹 서비스 → **Settings** → **Service Command** 부분 확인
2. Railway **CLI** 설치: https://docs.railway.app/develop/cli
3. 터미널에서:
   ```bash
   railway link <프로젝트-ID>
   railway run python import_sheets.py
   ```
   (이때 `DATABASE_URL`이 Railway Postgres를 가리켜서 자동으로 클라우드에 채워집니다.)

### 방법 B: 빈 DB로 시작
기존 데이터를 버리고 새로 시작해도 된다면 이 단계는 건너뛰세요. 봇이 새 스크린샷부터 자동으로 쌓기 시작합니다.

---

## 문제 해결 (자주 겪는 에러)

### 배포가 계속 실패해요
- Railway 웹 서비스 → **Deployments** → 실패한 배포 클릭 → **Logs** (로그) 확인
- `KeyError: 'DISCORD_BOT_TOKEN'` → 환경변수 이름 오타/미등록
- `ModuleNotFoundError` → `requirements.txt`에 빠진 패키지 (거의 발생 안 함)

### 봇이 online으로 안 떠요
- `DISCORD_BOT_TOKEN` 값이 맞는지 확인 (복사 시 공백 들어가기 쉬움)
- 로그에 Discord 연결 에러가 있는지 확인

### 웹은 뜨는데 데이터가 비어 있어요
- 5단계(데이터 마이그레이션)를 안 했기 때문. 빈 DB이므로 정상입니다.
- 구글 시트에서 데이터를 가져오거나 새 스크린샷부터 쌓이도록 두면 됩니다.

### 구글 시트 연동 에러
- `GOOGLE_SERVICE_ACCOUNT_JSON`이 올바른 JSON인지 확인
- 서비스 계정 이메일(`xxx@yyy.iam.gserviceaccount.com`)이 구글 시트에 **공유**되어 있는지 확인 (시트 우상단 공유 버튼)

### Postgres 연결 에러
- `DATABASE_URL`이 자동 주입되어 있는지 Variables 탭에서 확인
- PostgreSQL 서비스가 Running 상태인지 확인

---

## 재배포 & 롤백

### 코드 변경 시 재배포 (자동)
- `main` 브랜치에 **push 하면 Railway가 감지해서 자동 재배포** (보통 1~2분).
- 별도 버튼 안 눌러도 됨. 로컬에서 `git push origin main` 하면 끝.
- 배포 상태는 Railway → **Deployments** 탭에서 확인 (빌드 로그 실시간).
- 환경변수(Variables)를 변경해도 자동 재배포됨.

### 수동 재배포
- Railway → 웹 서비스 → **Deployments** 탭 → 가장 최근 배포 옆 **⋮** 또는 **Redeploy** 버튼.

### 롤백 (이전 버전으로 되돌리기)
최신 배포에 문제가 생기면 이전 정상 버전으로 즉시 되돌릴 수 있음:
1. Railway → 웹 서비스 → **Deployments** 탭
2. 목록에서 **정상 작동하던 이전 배포** 클릭
3. **Deploy** 또는 **Rollback to this deployment** 버튼 클릭
4. 1분 내로 그 버전으로 전환됨

> 💡 코드 수준 롤백이 필요하면 로컬에서 `git revert <커밋해시>` 후 push.

### 현재 배포 주소
`https://web-production-4deec.up.railway.app`
(도메인은 Railway → 웹 서비스 → Settings → Networking에서 확인/변경 가능)

---

## 비용 안내

- Railway는 **무료 크레딧($5 또는 500시간)** 제공 후 종량제
- 이 프로젝트 규모(봇+웹+소형 Postgres)면 월 **$5 미만**으로 예상
- 사용량은 Railway 대시보드 **Usage** 탭에서 확인 가능
- 과금이 우려되면 **볼륨을 절전(sleep)** 모드로 설정 가능 (다만 봇이 응답 안 함)

---

## 용어 사전 (초보용)

| 용어 | 뜻 |
|------|----|
| **배포 (Deploy)** | 내 코드를 인터넷상의 남의 컴퓨터(서버)에서 실행되게 하는 것 |
| **클라우드** | 남의 컴퓨터(데이터센터)를 빌려 쓰는 것. 내 PC와 달리 24시간 켜져 있음 |
| **Railway** | 코드만 올리면 자동으로 실행해주는 배포 플랫폼. 설정이 쉬운 편 |
| **PostgreSQL (Postgres)** | 로컬의 SQLite(`codm.db`) 클라우드 버전. 같은 역할 |
| **환경변수** | 비밀번호/키 같은 값들을 코드에 직접 적지 않고 따로 설정하는 값. 남에게 노출되지 않게 함 |
| **`DATABASE_URL`** | Postgres 위치를 알려주는 주소. Railway가 자동으로 만들어줌 |
| **`Procfile`** | Railway에게 "이 명령어로 실행해"라고 알려주는 지시서. 이 프로젝트는 `web: python start.py` |
| **도메인 (Domain)** | 웹사이트 주소. Railway가 `xxx.up.railway.app` 형태로 발급 |

---

## 도움이 필요하면

- Railway 공식 문서: https://docs.railway.app
- 배포 중 막히는 부분이 있으면 로그(Deployments → Logs) 내용을 같이 알려주세요.
