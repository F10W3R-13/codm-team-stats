# CODM 스탯 봇 + 웹 대시보드

디스코드 `scrim-result` 채널에 올라온 **CODM 스탯 스크린샷 2장**을 GPT 비전(gpt-5.6-luna)으로 분석해,
모드(HP / SND)를 자동 판별하고 선수별 통계를 **DB(SQLite/Postgres)에 기록**하는 봇과,
그 데이터를 보여주는 **FastAPI 웹 대시보드**(코칭 허브)로 구성된 프로젝트입니다.

> 작업 규칙·프로젝트 상세 지식(지표 공식, 아키텍처, 데이터 모델)은 **`AGENTS.md`** 참조.
> 배포(Railway) 단계별 가이드는 **`DEPLOYMENT.md`** 참조.

---

## 파일 구성 (핵심)

| 파일 | 설명 |
|------|------|
| `bot.py` | 디스코드 봇. 스크린샷 감지 → GPT 비전 분석 → `stats_repo.save_match()`로 DB 기록 |
| `commands_cog.py` | 디스코드 슬래시 명령 (영어) |
| `web_api.py` | FastAPI 웹 대시보드 (+ `templates/`, 3개국어 `i18n.py`) |
| `stats_repo.py` / `queries.py` / `analytics.py` | DB 저장·조회·분석 |
| `metrics.py` | 커스텀 지표 공식 (ZCS 등, 단일 진실 — 수정 금지) |
| `prompt.py` | GPT 비전 프롬프트 (make.com에서 추출 — 수정 금지) |
| `import_sheets.py` | 구글 시트 → DB 일회성 마이그레이션 |
| `config.py` | 채널 ID 등 설정 |
| `start.py` / `Procfile` | 통합 실행(봇+웹, 배포용) |

---

## 사전 준비 (한 번만)

### 1. 디스코드 봇 만들기
1. https://discord.com/developers/applications → **New Application**
2. **Bot** 탭 → 토큰 복사
3. **Privileged Gateway Intents** → **Message Content Intent** ON
4. **OAuth2 → URL Generator**: `bot` 스코프, `Send Messages` + `Read Message History` 권한으로 초대 URL 생성 → 서버에 초대

### 2. OpenAI API 키
- https://platform.openai.com/api-keys 에서 생성 (GPT 비전 호출 비용 발생)

### 3. 구글 서비스 계정 (시트 마이그레이션용 — `import_sheets.py` 쓸 때만 필요)
1. https://console.cloud.google.com → Google Sheets API 활성화
2. 서비스 계정 생성 → JSON 키를 `service-account.json`으로 이 폴더에 저장
3. 구글 시트 `2026 NA data management`에 서비스 계정 이메일을 **편집자**로 공유

### 4. 환경변수
```bash
cp .env.example .env
```
```
DISCORD_BOT_TOKEN=...
OPENAI_API_KEY=...
GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
```
- `DATABASE_URL`이 있으면 Postgres, 없으면 로컬 SQLite(`codm.db`) 사용.

---

## 실행

```bash
pip install -r requirements.txt
```

| 대상 | 명령 |
|------|------|
| 봇만 | `python bot.py` |
| 웹만 | `uvicorn web_api:app --port 8000` (CWD = 이 폴더) |
| 봇+웹 통합 (배포용) | `python start.py` |

접속: http://localhost:8000 — 봇과 웹은 같은 DB를 공유하므로 봇이 기록하면 즉시 반영됩니다.

### 웹 화면
| 경로 | 설명 |
|------|------|
| `/` | **코칭 허브** (트렌드, ZCS, 폼 경고, 강·약 맵, 승률) |
| `/overview` | 종합 대시보드 |
| `/players`, `/players/{name}` | 선수 목록/상세 (HP는 ZCS 컬럼, 역할 배지) |
| `/leaderboard` | 순위표 |
| `/compare` | 두 선수 비교 (레이더) |
| `/matches`, `/matches/{id}` | 매치 목록/상세 (승패 배지, AI 분석) |
| `/maps`, `/maps/{name}` | 맵 카드 그리드 → 맵 상세 |
| `/trends` | 시계열 |
| `/admin` | 관리 (승패·스코어 수동 입력) |

언어 전환: `?lang=ko|en|es`

---

## 봇 동작

- 감시 채널: `scrim-result` (`config.py`의 `WATCH_CHANNEL_ID`)
- **이미지 첨부 2장**일 때만 작동. 1장이면 안내 메시지로 응답.
- 분석: GPT 비전(gpt-5.6-luna), `response_format=json_object` + 세대별 파라미터 보정(`config.chat_params`) (프롬프트: `prompt.py`)
- 기록: 매치·선수 스탯을 DB에 저장 + Date는 메시지 작성 시간(한국시) 기준.

---

## 문제 해결

- **봇이 반응하지 않음**: Message Content Intent ON 여부, 채널 읽기 권한 확인.
- **OpenAI 과금/에러**: API 키 크레딧, `gpt-5.6-luna` 접근 권한 확인.
- **GPT가 JSON을 깨뜨림**: 이미지 화질 문제일 수 있음 → 선명한 스크린샷으로 재시도.
- **마이그레이션(gspread) 에러**: 서비스 계정 이메일이 시트에 공유돼 있는지, Sheets API 활성화 여부 확인.
- 배포 관련 에러는 `DEPLOYMENT.md`의 "문제 해결" 참조.
