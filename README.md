# CODM 스탯 봇

make.com 시나리오 **"CODM stats interpreter (HP + SND)"** 를 디스코드 봇 하나로 옮긴 프로젝트입니다.

디스코드 `scrim-result` 채널에 올라온 **CODM 스탯 스크린샷 2장**을 GPT-4.1 비전으로 분석해,
모드(HP / SND)를 자동으로 판별하고 선수별 통계를 구글 시트(`Database_HP` / `Database_SND`)에 기록합니다.

make.com과의 차이점은 **메시지 작성 시간(한국시)을 Date 열에 자동으로 기록**한다는 것뿐입니다.

---

## 파일 구성

| 파일 | 설명 |
|------|------|
| `bot.py` | 디스코드 봇 본체. 메시지 감지 → GPT 비전 분석 → 구글 시트 기록 |
| `prompt.py` | GPT 비전 프롬프트 (make.com에서 그대로 추출) |
| `config.py` | 채널 ID, 시트 ID, 칼럼 매핑 등 설정 |
| `requirements.txt` | 파이썬 의존성 |
| `.env.example` | 환경변수 템플릿 (복사해서 `.env`로 사용) |

---

## 사전 준비 (한 번만)

### 1. 디스코드 봇 만들기
1. https://discord.com/developers/applications 접속 → **New Application**
2. **Bot** 탭 → 토큰 복사(또는 Reset Token 후 복사)
3. 같은 탭 아래 **Privileged Gateway Intents** → **Message Content Intent**를 **ON**으로 변경 후 저장
4. **OAuth2 → URL Generator**: `bot` 스코프 체크, 권한은 `Send Messages` + `Read Message History` 정도면 충분
5. 생성된 초대 URL로 봇을 서버에 초대

### 2. OpenAI API 키 발급
- https://platform.openai.com/api-keys 에서 키 생성
- 결제수단 등록 + 크레딧 충전 필요 (GPT-4.1 비전 호출 비용 발생)

### 3. 구글 서비스 계정 만들기 (시트 자동 기록용)
1. https://console.cloud.google.com 에서 프로젝트 생성(또는 기존 프로젝트 사용)
2. **API 및 서비스 → 라이브러리** → **Google Sheets API** 사용 설정
3. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → 서비스 계정**
   - 이름 입력 → 만들기 → 완료
4. 생성된 서비스 계정 클릭 → **키** 탭 → **키 추가 → 새 키 만들기 → JSON**
   - 다운로드된 JSON 파일을 이 폴더에 `service-account.json` 이름으로 저장
5. JSON 파일 안의 `client_email`(예: `xxx@xxx.iam.gserviceaccount.com`) 복사
6. 구글 시트 `2026 NA data management`(`Database_HP` / `Database_SND` / `Alias` 포함)를 열고
   **공유** 버튼 → 위 이메일을 **편집자**로 추가

> 서비스 계정 방식은 비밀번호 없이 24시간 작동하므로 봇 자동화에 가장 적합합니다.

### 4. 환경변수 파일 작성
```bash
cp .env.example .env
```
`.env`를 열어 3개 값을 실제 값으로 채웁니다:
```
DISCORD_BOT_TOKEN=...
OPENAI_API_KEY=...
GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
```

---

## 실행

### 의존성 설치
```bash
pip install -r requirements.txt
```

### 봇 실행
```bash
python bot.py
```
콘솔에 `로그인 완료: ...` 가 뜨면 정상입니다. 이후 디스코드 `scrim-result` 채널에
CODM 스탯 스크린샷 2장을 올리면 자동으로 분석 후 시트에 기록합니다.

> PC가 켜져 있고 `python bot.py`가 실행 중일 때만 봇이 작동합니다.
> 나중에 24시간 운영하려면 클라우드 서버(VPS / Railway / Render 등)로 옮기면 됩니다.

---

---

## 웹 대시보드 실행

웹 대시보드는 별도의 FastAPI 서버로 동작합니다 (봇과 독립적).

```bash
python web_api.py
```
접속: **http://localhost:8000**

```bash
python web_api.py
```
접속: **http://localhost:8000**

### 화면
| 경로 | 설명 |
|------|------|
| `/` | 개요 대시보드 (총 통계, 맵 분포 차트, 최근 매치) |
| `/players` | 선수별 평균 스탯 표 (HP/SND 전환) |
| `/players/{name}` | 선수 상세 + K/D 트렌드 차트 |
| `/leaderboard` | 순위표 (모드·기준별) |
| `/matches` | 매치 히스토리 (페이지네이션, 모드 필터) |
| `/matches/{id}` | 매치 상세 (MOM, 팀 합계, 선수별 스탯) |

> 봇(`bot.py`)과 웹 서버(`web_api.py`)는 같은 `codm.db`를 공유하므로,
> 봇이 새 매치를 기록하면 웹 대시보드에 즉시 반영됩니다.
> 두 프로세스를 각각 실행하면 됩니다.

---

### 감시 대상
- 채널 ID: `1481522059086532629` (`scrim-result`) — `config.py` 의 `WATCH_CHANNEL_ID`
- 메시지에 **이미지 첨부 2장**이 있을 때만 작동. 1장이면 안내 메시지로 응답.

### 분석 (GPT-4.1 비전)
make.com 설정 그대로:
- `temperature=0`, `top_p=0`, `max_tokens=2048`, `response_format=json_object`
- 프롬프트: `prompt.py` (게임 모드 판별 규칙, 로스터 매핑, 모드별 데이터 추출, JSON 출력 형식 포함)

### 시트 기록
| 모드 | 시트 | 열 순서 |
|------|------|---------|
| HP | `Database_HP` | IGN, (actual name=빈칸), Kills, Deaths, K/D, OBJ(time), Score, Impact, Total Damage, Capture Kill, **Date** |
| SND | `Database_SND` | IGN, actual name(VLOOKUP 수식), Kills, Deaths, Assists, K/D, Score, Impact, ADR, First Kill, Lone Wolf Win, **Date** |

- SND의 actual name 열은 make.com처럼 `=IFERROR(VLOOKUP(...))` 수식을 `USER_ENTERED`로 넣습니다.
- **Date 열**은 메시지 작성 시간(한국시)을 `YYYY-MM-DD`로 자동 기록합니다. (make.com에는 없던 기능)
- 스크린샷 순서가 바뀌어 있어도 프롬프트가 알아서 처리합니다.

---

## 문제 해결

- **봇이 반응하지 않음**: Message Content Intent가 켜져 있는지, 봇이 해당 채널을 읽을 권한이 있는지 확인.
- **`gspread.exceptions.SpreadsheetNotFound`**: 서비스 계정 이메일이 시트에 공유되어 있는지, 스프레드시트 ID가 맞는지 확인.
- **`PermissionDenied`**: Google Sheets API가 활성화되어 있는지, 시트 공유 권한(편집자) 확인.
- **OpenAI 과금/에러**: API 키에 크레딧이 있는지, `gpt-4.1` 접근 권한이 있는지 확인.
- **GPT가 JSON을 깨뜨림**: 간혹 이미지 화질이 안 좋으면 JSON 파싱이 실패할 수 있음. 스크린샷을 선명하게 다시 올리면 됩니다.
