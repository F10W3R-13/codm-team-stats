# CLAUDE.md — CODM Team Stats 프로젝트 지침

이 파일은 AI 어시스턴트(Claude 등)가 이 프로젝트에서 작업할 때 참조하는 **앵커 문서**다.
모든 코드 변경/확장은 이 문서의 맥락을 존중해서 진행한다.

---

## 1. 프로젝트 배경과 목적

### 무엇인가
콜오브듀티 모바일(CODM) 이스포츠 팀의 **스탯 관리·분석 시스템**.
매치 스크린샷 2장을 GPT-4.1 비전으로 분석해 선수별 스탯을 추출·저장하고,
평균/순위/트렌드/커스텀 지표를 디스코드 봇과 웹 대시보드로 제공한다.

### 왜 만들었나
원래는 **make.com 시나리오**(`CODM stats interpreter (HP + SND)`)로 돌아갔다:
디스코드 채널 감시 → GPT 비전 분석 → 구글 시트 기록.
make.com 정액제/연산 소모와 유연성 한계 때문에 **자체 디스코드 봇 + 웹으로 독립**했다.
구글 시트는 더 이상 원본 저장소가 아니며(읽기 전용 백업/참고용), 진짜 데이터는 SQLite DB에 있다.

### 누가 쓰나
- **코치(사용자 본인, 한국어 원어민)** — 디스코드/웹 모두 한국어로 모니터링.
- **선수들(영어/스페인어 사용)** — 팀 소속 선수는 영어 또는 스페인어 사용.
  그래서 언어 정책이 이원화되어 있다(아래 §6 참고).

### 게임 맥락
- CODM 스크림은 주로 **4인 체제**(로스터 6명 + 간혹 용병). 정규는 5v5.
- 두 모드: **HP(하드포인트)** 와 **SND(수색섬멸)**. 스탯 구성이 다르다.
- 닉네임이 자주 바뀌고 특수문자/클랜태그가 붙어서 **정규화(alias 매핑)** 가 필수.

---

## 2. 아키텍처 개요

```
디스코드 채널(scrim-result) ──스크린샷──▶ bot.py (on_message)
                                              │
                                              ▼
                                    GPT-4.1 비전 (prompt.py)
                                              │
                                              ▼  JSON {mode, result[]}
                                    stats_repo.save_match()
                                              │
                                              ▼
                                         codm.db (SQLite)
                                              ▲
                                              │ queries.py / analytics.py
                          ┌───────────────────┴───────────────────┐
                          ▼                                       ▼
              web_api.py (FastAPI)                    commands_cog.py
              + templates/ (웹 대시보드)               (디스코드 슬래시 명령)
```

**3개 실행 단위가 같은 `codm.db`를 공유**한다:
- `bot.py` — 디스코드 봇 (스크린샷 감지 → 분석 → DB 기록 + 자동 리포트)
- `web_api.py` — FastAPI 웹 서버 (대시보드/선수/순위/매치/시계열)
- (일회성) `import_sheets.py` — 구글 시트 → DB 마이그레이션

봇이 DB에 쓰면 웹에 즉시 반영된다.

---

## 3. 파일 구조와 역할

### 핵심 Python 모듈
| 파일 | 역할 |
|------|------|
| `bot.py` | 디스코드 봇 본체. `on_message`로 스크린샷 2장 감지 → GPT 분석 → `stats_repo`로 DB 기록 + 자동 매치 리포트 게시 |
| `prompt.py` | GPT-4.1 비전 분석 프롬프트 (make.com 원본 그대로 추출 — 게임 모드 판별, 로스터 매핑, 모드별 데이터 추출, JSON 출력 형식 규칙) |
| `config.py` | 상수: 채널 ID, 스프레드시트 ID, 로스터, OpenAI 모델/파라미터. 환경변수에서 토큰/키 읽음 |
| `db.py` | SQLite 스키마 + 커넥션 관리 + 선수/alias 헬퍼. **모든 DB 접근의 기반** |
| `stats_repo.py` | 스탯 기록 계층. `save_match(mode, players, date)` — 봇이 호출 |
| `queries.py` | 집계 조회 계층. 선수 평균/리더보드/매치 요약/시계열 등. 봇 명령어+웹이 공유 |
| `analytics.py` | 분석 데이터 생성: 매치 리포트(MOM/팀평균), 주간 트렌드, 선수 폼 분석 |
| `analytics_insights.py` | GPT 자연어 인사이트 (매치/주간/트렌트 요약). 실패 시 빈 문자열 (리포트 표시에 영향 X) |
| `metrics.py` | **커스텀 지표 공식** (DPD/DPK/ID/AP%/ZCS/Impact). §5 참고 |
| `report_embeds.py` | 디스코드 Embed 빌더 (매치/주간/트렌드). 영어 응답 |
| `commands_cog.py` | 디스코드 슬래시 명령 Cog (10개 명령). 영어 응답 |
| `i18n.py` | 웹용 다국어 사전 (ko/en/es). 웹 전용 |
| `import_sheets.py` | 구글 시트 → DB 일회성 마이그레이션 (매치 분할 로직 포함) |
| `web_api.py` | FastAPI 웹 서버. Jinja2 직접 렌더링 (Starlette Jinja2Templates 버그 회피). 대시보드/선수/순위/매치/시계열/**관리(admin)** 페이지 |

### 웹 템플릿 (`templates/`)
| 파일 | 페이지 |
|------|--------|
| `base.html` | 공통 레이아웃 (TDS 디자인 토큰, 네비게이션, 언어 전환기, Chart.js) |
| `dashboard.html` | 개요 (총 통계, 맵 분포 차트, 최근 매치) |
| `players.html` | 선수별 평균 스탯 표 + HP 커스텀 지표 표 |
| `player_detail.html` | 선수 상세 (HP/SND 스탯 + K/D 트렌드 차트) |
| `leaderboard.html` | 순위표 (모드·지표별) |
| `matches.html` | 매치 히스토리 (페이지네이션) |
| `match_detail.html` | 매치 상세 (MOM, **팀 평균**, 선수별 스탯) |
| `trends.html` | 시계열 분석 (선수×모드×지표 차트 + 데이터 표) |
| `admin.html` | 관리 — 매치 목록 (result/score/map 포함, 필터링) |
| `admin_match.html` | 관리 — 매치 메타/선수 스탯 수정 + 매치 삭제 |

### 설정/데이터 파일
- `.env` — `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_FILE` (실제 값, **커밋 금지**)
- `.env.example` — 템플릿
- `service-account.json` — 구글 서비스 계정 키 (**커밋 금지**)
- `codm.db` — 실제 데이터베이스
- `codm.db.backup` — AyeoRaph 삭제 전 백업
- `requirements.txt` — discord.py, openai, gspread, python-dotenv, fastapi, uvicorn, jinja2

---

## 4. 데이터 모델과 중요한 특이점

### DB 스키마 (`codm.db`)
```
players(id, name, created_at)                        — 정규화된 표준 이름
aliases(ign, player_id → players.id)                — 닉네임 사전 (UNIQUE ign)
matches(id, mode[HP/SND], map_name, match_date, raw_date,
        result[WIN/LOSS], team_score, opponent_score, created_at)  — 매치 + 승패/점수
player_stats_hp(match_id, player_id, ign_raw, kills, deaths, kd_ratio,
                 obj_time, score, impact, total_damage, capture_kill)
player_stats_snd(match_id, player_id, ign_raw, kills, deaths, assists,
                  kd_ratio, score, impact, adr, first_kill, lone_wolf_win)
```
- **한 매치 = 1행** in `matches`, 그 매치의 선수 N명 = N행 in `player_stats_*`.
- `UNIQUE(match_id, player_id)` — 같은 매치 같은 선수 중복 불가.
- `result`/`team_score`/`opponent_score`는 전체 스크린샷 도입(2026-06-26) 후 추가.
  마이그레이션 전 기존 매치들은 NULL (승패 모름). `db.init_db()`가 자동 마이그레이션.

### ⚠️ 매치 분할 규칙 (import_sheets.py — 핵심 특이점)
구글 시트에는 match_id가 없었다. 매치를 어떻게 나누는지가 이 프로젝트의 가장 까다로운 부분:
- **같은 매치의 선수들이 연속된 행**으로 들어오고, 다음 매치는 다시 첫 선수부터 반복.
- 그래서 **"현재 매치에 이미 등장한 선수가 다시 나오면 새 매치 시작"** 으로 분할.
- 단순 고정 행 수(4행/5행)로 자르면 안 됨 — 한 날짜에 여러 매치 + 인원수 변동 때문에 실패.
- 이 규칙은 `import_sheets.py`의 `group_matches()`에 구현되어 있다.

### ⚠️ 이름 정규화
- 시트에 대소문자가 섞여 있었음 (`Unravel`/`unravel`, `Cartels`/`cartels`).
- `import_sheets.py`의 `normalize_name()` + `NAME_NORMALIZE` 맵으로 통일.
- 새 선수/닉네임은 디스코드 `/addalias`로 추가.

### 현재 데이터 현황 (2026-06-26 기준)
- 선수 7명: Cartels, Exile, Kingz, Maozyn, Shisui, Swish, unravel
- (AyeoRaph는 퇴단으로 삭제됨 — 삭제 전 백업 `codm.db.backup`)
- 매치 232개 (HP 226 / SND 6), 기간 2026-02-11 ~ 2026-06-24
- alias 94개

### 데이터 품질 이슈 (알려진 것)
- 일부 HP 매치가 3~6명 청크로 분할된 케이스 있음 (매치 분할 경계 애매) — 정제 가능하나 우선순위 낮음.
- 맵 이름 대소문자 중복 (`Combine`/`combine`) — `overview_stats()`에서 `GROUP BY LOWER(map_name)`으로 흡수 중.

---

## 5. 지표와 공식 출처

### GPT 비전 프롬프트 (`prompt.py`)
**전체 매치 스크린샷 2장**(기본 탭 + 디테일 탭)을 분석한다. (2026-06-26 변경)
이전에는 우리 팀만 크롭한 사진을 썼으나, 이제 전체 화면을 올린다.

프롬프트의 4단계 구조 (수정 시 매우 주의):
1. **게임 모드 판별** — 상단 텍스트(HARDPOINT/SEARCH AND DESTROY) + 열 제목 보조
2. **우리 팀 식별 ★가장 중요** — 로스터 6명 + alias에 매칭되는 선수가 많은 쪽 = 우리 팀.
   좌/우 양쪽 팀 중 어느 쪽이 우리 팀인지 확정 후 그쪽만 추출. **적 팀 데이터 절대 포함 금지** (단계적 도입 정책).
3. **승패/점수/맵 추출** — `VICTORY`→WIN/`DEFEAT`→LOSS, 점수 `96:250`, 맵 `HARDPOINT COMBINE`→"Combine".
   점수 순서 주의: 우리 팀이 좌측이면 첫 점수가 우리 점수.
4. **우리 팀 선수 스탯 추출** — 표준 이름 변환, 모드별 필드

출력 JSON 키 (중요 — 키 충돌 주의):
- `result` (문자열) = WIN/LOSS
- `players` (배열) = 선수 목록  ← 구버전은 `result` 배열이었으나 충돌로 분리
- 그 외: mode, team_score, opponent_score, map, our_team_side

로스터 매핑: `["Shisui","Cartels","unravel","Kingz","Maozyn","Exile"]` (용병은 그대로 출력)
GPT 파라미터: `gpt-4.1`, temperature=0, top_p=0, max_tokens=2048, response_format=json_object

### 커스텀 지표 (`metrics.py`)
출처: 구글 시트 "2026 NA data management" Dashboard 시트의 공식 정의. **수정 금지, 공식이 정해져 있음**:

| 지표 | 공식 | 비고 |
|------|------|------|
| Impact | `min(200, 73 + 2.6·K − 3.1·D + 0.92·OBJ + 0.009·TD)` | 스크린샷에서 직접 계산용 (보통 스크린샷에 값이 있어 안 씀) |
| DPD | `Total Damage / Deaths` | Damage Per Death |
| DPK | `Total Damage / Kills` | Damage Per Kill |
| ID | `Impact − Score/34` | Impact Delta (점수 대비 임팩트 초과분) |
| AP% | `(Capture Kill / Kills) × 100` | Assist Percentage — 킬 대비 캡처킬 비율 |
| ZCS | `max(0, 1.1·OBJ + 8·CK + 4.1·K − 5·D)` | Zone Control Score |

### ⚠️ ZCS 시트 오류 정정 (중요)
구글 시트 Dashboard의 "ZCS" 열(행 54)에 **Total Damage 값이 잘못 배치**되어 있었음 (예: Shisui 4953.89 = 실제론 평균 딜).
ZCS는 **위 공식(100~220 범위)으로 재계산**한 값을 정답으로 쓴다. 시트 원본을 믿지 말 것.

---

## 6. 언어/i18n 정책

### 이원화 정책
- **코치용 = 한국어**, **선수용 = 영어/스페인어**.
- **디스코드 봇**: 영어 고정 응답 (선수들이 보는 채널).
- **웹**: 3개국어 전환 (`?lang=ko|en|es`). 코치는 한국어, 선수에게는 EN/ES 링크 공유.
- **로그(콘솔)**: 한국어 (코치가 PC에서 모니터링).

### 구현
- 웹: `i18n.py` 사전 + 템플릿에서 `t.키` 형태 사용. `web_api.py`의 `render()`가 lang/t를 주입.
- 디스코드: `commands_cog.py`/`report_embeds.py`에 영어 텍스트 하드코딩.
- 새 UI 문자열 추가 시 `i18n.py`의 ko/en/es 세 언어에 모두 추가해야 함.

---

## 7. 운영/보안 주의사항

### 실행
- 봇: `python bot.py` (디스코드 연결, 감시 채널 `1481522059086532629`)
- 웹: `python web_api.py` → http://localhost:8000
- 두 프로세스를 각각 실행. 같은 DB 공유.
- 로컬 PC 실행 — PC가 꺼지면 둘 다 중지.

### ⚠️ DB 직접 수정 시 (매우 중요)
- **조회**: 봇/웹 실행 중에도 안전 (읽기 전용).
- **수정/삭제/구조 변경**: **반드시 봇과 웹을 먼저 중지**. SQLite는 동시 쓰기에 약해 충돌/손상 위험.
- 수정 전 `codm.db` 백업 필수 (`cp codm.db codm.db.backup`).

### 비밀 정보 (절대 커밋/공유 금지)
- `.env` (디스코드 토큰, OpenAI 키)
- `service-account.json` (구글 서비스 계정 키)
- 구글 시트 ID: `1nnyzo7_mH1JgTF5yln2AR1HuUiVGc9c7ZctVyA8PlgE` (비공개)
- 서비스 계정 이메일: `statbot@statbot-500600.iam.gserviceaccount.com`

### 외부 서비스 의존
- **OpenAI GPT-4.1** — 비전 분석(스크린샷), 자연어 인사이트. 호출 비용 발생.
- **구글 시트 API** — import_sheets.py(일회성)와 config의 ID만. 런타임에 시트 안 씀.

---

## 8. 디자인 시스템 (TDS — 토스 디자인 시스템)

웹은 **TDS 라이트 테마**를 따른다. 템플릿 수정 시 이 규칙 준수:

### 디자인 토큰 (`base.html`의 `:root`)
```
--bg: #f2f4f6 (Grey100 배경)
--card: #ffffff / --card-2: #f2f4f6 (hover)
--border: #e5e8eb
--text: #191f28 / --text-2: #4e5968 / --muted: #8b95a1
--accent: #3182f6 (Blue500 토스 블루) / --accent-weak: #e8f3ff
--accent-2: #15c47e (Green 긍정)
--hp: #ff9d00 (오렌지) / --snd: #8b5cf6 (퍼플) — 모드별 종목색
--radius: 20px / --radius-sm: 12px
--shadow: 0 1px 3px rgba(0,0,0,0.04), 0 6px 20px rgba(0,0,0,0.04)
```

### 규칙
- 폰트: **Pretendard** (CDN 로드).
- 색상은 CSS 변수로만. 하드코딩 금지 (예외: Chart.js JS 안의 색은 어쩔 수 없이 직접 — TDS 톤 유지).
- HP=오렌지, SND=퍼플 일관성 유지.
- 다크 테마로 돌아가지 말 것.
- 디자인 변경 시 `base.html`의 토큰과 `base.html.bak`(백업) 참고.

---

## 9. 개발 단계와 로드맵

### 완료된 Phase
- **Phase 1**: 구글 시트 → SQLite 마이그레이션 (`import_sheets.py`)
- **Phase 2**: 디스코드 슬래시 명령어 (10개: stats/compare/lastmatch/leaderboard/matchreport/weekly/trend/addalias/removealias/listalias)
- **Phase 3**: 자동 분석 리포트 + GPT 인사이트 (매치 후 자동, /weekly, /trend)
- **Phase 4**: 웹 대시보드 (대시보드/선수/순위/매치/시계열)
- **추가**: 커스텀 지표(DPD/DPK/ID/AP%/ZCS), Alias 관리 명령, i18n(3개국어), 시계열 뷰, AyeoRaph 데이터 삭제, 팀 평균 변경, 디스코드 영어화, TDS 디자인 적용

### 향후 후보 (Phase 5)
- 클라우드 배포 (VPS/Railway/Render) — 24시간 운영
- 맵 데이터 입력 자동화 (현재 대부분 수동/비어있음)
- 다중 팀 확장 (SaaS — 다른 팀도 가입해서 자기 팀 관리, 멀티테넌시)
- 데이터 정제 (매치 분할 경계 애매 케이스, 맵 이름 통합)
- Discord OAuth 웹 인증 (현재 인증 없음, 로컬 전용)

---

## 10. 작업 시 핵심 원칙

1. **DB 수정 전에는 반드시 봇/웹 중지 + 백업**.
2. **GPT 프롬프트(`prompt.py`)와 커스텀 지표 공식(`metrics.py`)은 함부로 수정 금지** — 출처가 정해져 있음. 특히 프롬프트의 `result`(문자열) vs `players`(배열) 키 분리 절대 헷갈리지 말 것.
3. **매치 분할 규칙**(`import_sheets.py`의 `group_matches`)을 이해하지 못한 채 데이터 재동기화 시도 금지.
4. **전체 스크린샷 분석 시 적 팀 데이터는 무시** (단계적 도입 정책). 우리 팀만 기록. 향후 적 팀 추가 시 별도 테이블 설계 필요.
5. 새 UI 문자열은 **i18n.py 3개 언어 모두**에 추가.
6. 디자인은 **TDS 토큰** 준수, 하드코딩 색상 회피.
7. 디스코드 응답은 **영어**, 로그는 한국어.
8. 비밀 정보(`.env`, `service-account.json`) 절대 외부 노출 금지.
9. DB 스키마 변경 시 `db.init_db()`에 마이그레이션 로직(ALTER TABLE)을 포함해 기존 데이터 보존.
10. 변경 후에는 봇/웹 재시작으로 검증.
11. **관리 페이지(`/admin`)는 인증 없음** — 데이터 수정/삭제가 누구나 가능. 로컬 전용이지만 외부 노출 시 반드시 인증 추가할 것. `queries.update_match_meta/update_player_stat/delete_match`가 편집 API. AI OCR 오류 정정용이 주 목적.
