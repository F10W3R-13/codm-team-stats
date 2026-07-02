# OCR → Alias Matching System (Fixed 6-Player Roster)

> 엔티티 매칭 파이프라인 사양서.
> 노이즈가 섞인 OCR 문자열(IGN as read)을 신뢰 가능한 엔티티(선수)에 연결하기 위한 다단계 게이트 시스템.
> 본 문서는 **고정 6인 로스터 + 운영자 수동 alias 관리** 변형을 기준으로 한다.

---

## 0. 전제 조건 (이 시스템이 가정하는 것)

- **로스터는 고정 6명.** 팀원이 바뀌지 않는 폐쇄 집합.
- **팀원은 스스로 IGN을 등록하지 않는다.** 셀프 등록 플로우가 없다.
- 운영자가 직접 "누가 누군지" 알아보고 alias를 부여/관리한다.
- OCR 엔진(LLM Vision 또는 전용 OCR)이 스크린샷에서 `IGN as read`(오염 문자열)를 뱉어낸다.

> ※ CQ Bot 원본 시스템과의 핵심 차이:
> 원본은 선수가 `/ign` 명령으로 self-register 하고, 퍼지 매칭으로 확정된 변형을 자동 학습한다.
> 본 변형은 **등록 플로우가 없으므로**, 운영자 주도로 canonical IGN + alias 사전을 수동 구축하며,
> 퍼지 자동 학습은 "운영자가 이미 부여한 alias 범위 내에서만" 보조적으로 동작한다.

---

## 1. 시스템 개요 (5-Layer Pipeline)

```
┌────────────────────────────────────────────────────────┐
│ Layer 1: OCR                                          │
│   스크린샷 → "IGN as read" (오염 문자열)              │
│   Roster hint 주입으로 1~2글자 오독 사전 교정         │
└────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 2: Matcher (3-stage gate)                       │
│   Stage 1: normalize → exact dict lookup              │
│   Stage 2: Jaro-Winkler 퍼지 (score + margin)         │
│   Stage 3: 임계치 미만 → no_match                     │
└────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 3: Decider (method → status/action 분기)        │
│   exact / fuzzy_auto → Matched (엔티티 연결)          │
│   review             → Needs Review (운영자 알림)     │
│   no_match           → Unmatched                      │
└────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 4: Alias Dictionary (운영자 수동 관리)          │
│   운영자가 확인 후 alias 영구 저장                    │
│   → 다음 OCR부터 Stage 1 exact hit                    │
└────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────┐
│ Layer 5: Reconcile (safety-net)                       │
│   주기적 TTL 리프레시 + 미매칭 레코드 재스캔          │
└────────────────────────────────────────────────────────┘
```

---

## 2. 데이터 스키마 (3-테이블 구조)

| 테이블 | 역할 | 핵심 필드 |
|--------|------|-----------|
| **Players** | 엔티티 마스터. 1인 1레코드 (고정 6행) | `Primary IGN` |
| **Aliases** | 변형 사전. N:1 → Players | `IGN`, `Player`(링크), `Source` |
| **Match Records** | 경기/raw 이벤트 row | `IGN as read`, `Player`(링크), `Status`, stats... |

### `Source` 값 (감사 추적용)
- `Manual` — 운영자가 직접 지정
- `OCR Auto` — 퍼지 자동 학습 (허용하는 경우에만)

### Players 테이블은 항상 6행으로 고정
- 새 행 추가/삭제 없음
- `Primary IGN` 값도 운영자가 수동으로 입력

---

## 3. Layer 1 — OCR 엔진

### 핵심: Roster hint 주입

비전 모델에게 **"정답 후보 6개"**를 프롬프트에 미리 준다.
6명뿐이므로 후보가 짧고, 프롬프트 비용도 거의 없다.

```
[0. Registered roster - OCR correction hint]
- Official registered IGNs in this server: ["Player1", "Player2", ..., "Player6"]
- If a name read from the screen clearly refers to one of the roster entries
  (off by 1-2 characters), correct it to the exact roster spelling.
- But if there is no matching roster entry, never force a match;
  output exactly what is shown.
```

**규칙의 양면성**:
- ✅ 1~2글자 오독은 적극 교정
- ❌ 강제 매칭 금지 — hallucination 방어. 모르면 그대로 출력

> 6인 고정 로스터라 후보가 적어, 원본 CQ Bot(수십~수백 명)보다
> 이 힌트의 효과가 훨씬 강력하다. 대부분의 IGN이 교정 단계에서 해결될 가능성이 큼.

---

## 4. Layer 2 — Matcher (3-Stage Gate)

### 4.1 정규화 (Normalize)

매칭 전 노이즈 제거. **도메인 특화 규칙을 여기에 코딩한다.**

```python
def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)               # 전각 → 반각
    s = s.lower()
    s = re.sub(r"[\[\(<{].*?[\]\)>}]", "", s)          # [clan] (tag) 제거
    s = re.sub(r"[\s.\-_+~/|]+", "", s)                # 구분자 제거
    s = re.sub(r"[^\w]", "", s, flags=re.UNICODE)      # 나머지 기호
    return s.replace("_", "")
```

- **CJK 보존 필수**: Hangul/Katakana는 `\w + re.UNICODE`로 살아남아야 함
- IGN이 짧으므로(6~10글자) 정규화 한 글자가 매칭 결과를 크게 바꿈

### 4.2 임계치 (Tuning Knobs)

```python
T_HIGH = 0.92   # 이상 + margin 충족 → 자동 확정
T_LOW  = 0.75   # 미만 → no_match
MARGIN = 0.08   # top1 - top2 (다른 선수 기준)가 이보다 작으면 충돌 → review
```

> **6인 로스터에서의 캘리브레이션 제안**:
> 후보가 적어 conflict 확률이 낮으므로 MARGIN은 0.05 정도로 낮춰도 무방할 수 있다.
> 단, IGN끼리 비슷한 선수가 있다면(예: "Ace"/"Acer") MARGIN을 0.10~0.12로 올릴 것.
> 실데이터 1~2주 분량으로 confusion matrix 그려서 tuning.

### 4.3 판정 로직

| Stage | 조건 | method | 의미 |
|-------|------|--------|------|
| 1 | normalize 후 exact dict에 존재 | `exact` (score=1.0) | 이미 아는 변형 |
| 2 | score ≥ T_HIGH **and** margin ≥ MARGIN | `fuzzy_auto` | 자동 확정 |
| 2 | T_LOW ≤ score < T_HIGH **or** margin < MARGIN | `review` | 운영자 확인 필요 |
| 3 | score < T_LOW | `no_match` | 모르는 IGN (게스트/오탐 가능) |

### 4.4 ★ 핵심 디테일: Per-Entity Best Score

**이 로직을 빼먹으면 가장 흔한 버그가 생긴다.**

한 선수가 `Primary IGN` + 여러 alias로 candidates에 여러 번 등장한다.
이걸 그냥 전부 sort하면 **같은 선수의 두 변형이 1, 2위를 차지해서 가짜 conflict**가 발생한다.

```python
# 선수별 최고 점수만 남긴다
best = {}
for cand, pid in self.candidates:
    sc = JaroWinkler.similarity(n, cand)
    if pid not in best or sc > best[pid]:
        best[pid] = sc

ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
top_pid, top_score = ranked[0]
# margin = top1과 "다른 선수"의 최고 점수 차이
second = ranked[1][1] if len(ranked) > 1 else 0.0
margin = top_score - second
```

**왜 Jaro-Winkler인가**:
- 접두사 가중치(prefix bonus)가 있어서 짧은 IGN에서 앞부분 일치를 강하게 보상
- Levenshtein보다 사람 이름 매칭에 적합

### 4.5 ★ 6인 로스터 특화 고려사항: no_match의 의미

원본(수십 명 로스터)에서 `no_match` = "새로 가입한 사람/미등록자".
**6인 고정에서는 `no_match` = "이 6명 중 아무도 아님"** = 게스트/오탐/외부인 가능성.
운영자 알림을 `review`와 **구분해서** 처리할 것:
- `review`: 6명 중 누군가 같긴 한데 애매 → "이 선수 맞아?"
- `no_match`: 6명 밖 → "왜 모르는 이름이 나왔지?" (예: 게스트 참여, OCR 완전 실패)

---

## 5. Layer 3 — Decider (Status 분기)

매 레코드를 생성/갱신할 때 method에 따라 Status를 세팅한다.

```python
if method in ("exact", "fuzzy_auto"):
    fields[LINKED_PLAYER_FIELD] = [pid]
    fields["Status"] = STATUS_MATCHED
elif method == "review":
    fields["Status"] = STATUS_REVIEW
else:
    fields["Status"] = STATUS_UNMATCHED
```

### Status 값
- `Matched` — 선수 확정 연결
- `Needs Review` — 운영자 확인 필요
- `Unmatched` — 6인 중 안 됨

`review` / `no_match` 건은 운영자 채널로 Airtable 레코드 링크와 함께 알림.

---

## 6. Layer 4 — Alias Dictionary (★ 운영자 수동 관리 = 본 변형의 핵심)

### 6.1 원본과의 차이

| 구분 | 원본 CQ Bot | 본 변형 (6인 고정) |
|------|-------------|---------------------|
| 초기 canonical IGN | 선수가 `/ign`으로 등록 | **운영자가 직접 6행 입력** |
| Alias 초기 부여 | (거의 없음) | **운영자가 OCR 관찰 후 수동 지정** |
| Alias 자동 학습 | 퍼지 확정 시 자동 | **선택적** (아래 6.3 참고) |
| 부트스트랩 | 선수 가입에 의존 | **운영자가 사전에 사전을 채워야 함** |

### 6.2 운영자 워크플로우 (권장)

1. **초기 1회**: 6명의 `Primary IGN`을 Players 테이블에 입력
2. **첫 며칠**: OCR 결과를 관찰. `review`/`Unmatched`로 떨어지는 IGN을 보고
   - 누구인지 식별
   - 그 변형을 Aliases 테이블에 `Source = Manual`로 추가
3. **안정기**: 대부분의 변형이 사전에 등록되어 exact hit로 처리됨

### 6.3 Alias 자동 학습 — 허용 여부 정책 결정

**선택 A: 자동 학습 ON (원본 방식)**
- 퍼지 매칭으로 확정된 변형을 자동으로 Aliases에 저장
- 장점: 운영자 수고 감소
- 위험: 6명뿐이라 한 번 잘못 학습되면 영향이 큼 (예: 게스트 IGN이 퍼지로 잘못 확정되면 계속 그 선수에게 연결)

**선택 B: 자동 학습 OFF (운영자 주도, 권장)**
- 퍼지 매칭은 `review`로만 분류하고 자동 저장 안 함
- 운영자가 확인 후 직접 alias 추가
- 6명 폐쇄 집합이므로, 정확도 > 자동화가 유리

> 구현상 차이: 원본 `_learn_alias()` 호출을 `fuzzy_auto` 분기에서 제거하면 됨.
> 단, 운영자 수동 `/link` 명령으로 연결할 때는 여전히 alias를 학습시키는 게 편리.

### 6.4 학습 안전장치 (자동/수정 무관하게 필수)

```python
def add_alias(raw_ign, player_id, source="Manual"):
    n = normalize(raw_ign)
    if not n or n in matcher.exact:   # ← 중복/충돌 방지
        return
    aliases_table.create(
        {"IGN": raw_ign, "Player": [player_id], "Source": source},
        typecast=True,
    )
    matcher.exact[n] = player_id      # ← 메모리 캐시 즉시 갱신
```

- `n in matcher.exact` 체크: 이미 다른 선수에게 할당된 변형을 덮어쓰지 않음
- `Source` 필드: 감사 추적. 나중에 잘못된 alias 롤백 가능

---

## 7. Layer 5 — Reconcile (Safety Net)

주기적으로 (예: 45초마다):
1. **TTL-gated cache refresh** (예: 5분): 운영자가 DB/UI를 직접 편집한 것을 캡처
2. **미매칭 레코드 재스캔**: `{Player} = ''` 조건으로, alias가 나중에 추가되었을 때 과거 레코드를 자동 정정

정상 경로는 인라인 매칭이라 0 write. 안전망일 뿐이다.

### 운영자 `/link` 명령 후에도 reconcile 실행
운영자가 수동으로 review 레코드를 연결하면:
1. 해당 IGN을 alias로 학습
2. matcher.reload() 후 reconcile_once() → 비슷한 시점의 다른 미매칭 레코드까지 한 번에 정정

---

## 8. 전체 매칭 클래스 (참조 구현)

```python
import re, unicodedata
from rapidfuzz.distance import JaroWinkler

T_HIGH = 0.92
T_LOW  = 0.75
MARGIN = 0.08   # 6인 로스터에서는 0.05~0.12 범위로 튜닝 권장

def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.lower()
    s = re.sub(r"[\[\(<{].*?[\]\)>}]", "", s)
    s = re.sub(r"[\s.\-_+~/|]+", "", s)
    s = re.sub(r"[^\w]", "", s, flags=re.UNICODE)
    return s.replace("_", "")


class Matcher:
    def __init__(self, players_table, aliases_table):
        self.players_table = players_table
        self.aliases_table = aliases_table
        self.exact = {}        # normalized_ign -> player_record_id
        self.candidates = []   # [(normalized_ign, player_record_id), ...]
        self.roster = []       # 원본 스펠링 (OCR hint용)
        self.reload()

    def reload(self):
        self.exact.clear()
        self.candidates.clear()
        self.roster.clear()

        # 1) Players (고정 6행) 의 Primary IGN
        for p in self.players_table.all(fields=["Primary IGN"]):
            pid = p["id"]
            ign = p["fields"].get("Primary IGN")
            if ign:
                self.roster.append(ign)
                n = normalize(ign)
                if n:
                    self.exact.setdefault(n, pid)
                    self.candidates.append((n, pid))

        # 2) 모든 Aliases 변형 (Manual + OCR Auto)
        for a in self.aliases_table.all(fields=["IGN", "Player"]):
            ign = a["fields"].get("IGN")
            players = a["fields"].get("Player") or []
            if ign and players:
                n = normalize(ign)
                pid = players[0]["id"] if isinstance(players[0], dict) else players[0]
                if n:
                    self.exact.setdefault(n, pid)
                    self.candidates.append((n, pid))

    def add_alias(self, normalized_ign, player_id):
        """캐시에 즉시 반영 (영속 저장은 add_alias() 헬퍼에서 담당)."""
        self.exact.setdefault(normalized_ign, player_id)
        self.candidates.append((normalized_ign, player_id))

    def match(self, ign_as_read: str):
        """Returns (player_id | None, score, method)
        method in {'exact','fuzzy_auto','review','no_match'}"""
        n = normalize(ign_as_read)
        if not n:
            return (None, 0.0, "no_match")

        # Stage 1: exact
        if n in self.exact:
            return (self.exact[n], 1.0, "exact")

        # Stage 2: fuzzy
        if not self.candidates:
            return (None, 0.0, "no_match")

        # per-entity best (가짜 conflict 방지)
        best = {}
        for cand, pid in self.candidates:
            sc = JaroWinkler.similarity(n, cand)
            if pid not in best or sc > best[pid]:
                best[pid] = sc
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        top_pid, top_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - second

        if top_score >= T_HIGH and margin >= MARGIN:
            return (top_pid, top_score, "fuzzy_auto")
        if top_score < T_LOW:
            return (None, top_score, "no_match")
        return (top_pid, top_score, "review")
```

---

## 9. 다른 도메인에 재적용하기 위한 체크리스트

이 시스템은 "노이즈 많은 입력(OCR/음성/수기) → 신뢰 가능 엔티티" 범용 패턴이다.

- [ ] **정규화 규칙**: 도메인 특화 노이즈 제거 (clan tag? 법인형태? 동/호 표기? 조사?)
- [ ] **엔티티 후보 수**: 폐쇄 집합(6명처럼)이면 MARGIN↓, 자동 학습은 보수적으로
- [ ] **부트스트랩**: 누가 엔티티를 입력하는가? (본 변형 = 운영자 수동)
- [ ] **T_HIGH / T_LOW / MARGIN**: 실 데이터 1~2주로 confusion matrix tuning
- [ ] **Conflict 감지(margin)**: 같은 엔티티의 변형이 가짜 충돌 일으키지 않게 per-entity best
- [ ] **Self-learning 정책**: 자동 ON vs 운영자 주도, 위양성 비용에 따라 결정
- [ ] **Audit trail**: `Source` 필드로 자동/수동 구분, 롤백 가능하게
- [ ] **Human-in-the-loop**: review/no_match 알림, 수동 `/link`/`/reject` 명령
- [ ] **Reconcile safety net**: 주기적 TTL 리프레시 + 미매칭 재스캔

---

## 10. 핵심 설계 원칙 (다른 곳에 옮길 때 지킬 것)

1. **Defense in depth** — OCR hint / exact / fuzzy / margin / human review / reconcile. 어느 하나만으로는 부족하고 중첩된 게이트가 정확도를 만든다.
2. **Self-improving** — 한 번 판정된 변형은 다음 판정 비용을 0으로. 운영할수록 정확해진다. 단, 6인 폐쇄 집합에서는 자동 학습보다 운영자 주도가 더 안전할 수 있다.
3. **Per-entity de-dup before margin** — 가장 흔한 버그 원인. 같은 엔티티의 변형이 충돌처럼 보이는 걸 방지.
4. **Human-in-the-loop escape hatch** — 자동화는 높은 신뢰구간만 담당, 애매한 건은 review queue로.
5. **관측 가능성** — `Source`, `Status`, score 기록, 운영자 로그. 임계치 튜닝의 데이터가 됨.
6. **폐쇄 집합의 특성 활용** — 후보가 6명뿐이므로 OCR hint 효과가 강하다. 정확도 우선, 자동화는 보조로.
