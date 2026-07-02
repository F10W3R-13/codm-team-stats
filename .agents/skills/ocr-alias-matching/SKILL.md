---
name: ocr-alias-matching
description: Design and implement pipelines that match noisy string input (OCR output, voice transcription, handwritten/user-typed names) to a trusted set of entities using a multi-stage gate — normalize → exact alias dictionary → fuzzy (Jaro-Winkler + margin) → human review. Use this skill whenever the user wants to match OCR-extracted names/IGNs to a roster, build alias/nickname dictionaries, resolve entity name variants, deduplicate noisy identifiers, link screenshot-extracted data to known people/products/accounts, or asks about fuzzy name matching, entity resolution, "누가 누군지 매칭", "닉네임/별명 매칭", "OCR 이름 인식 오류" — even if they don't say "alias" or "matching pipeline" explicitly.
---

# OCR → Alias Matching (노이즈 입력 → 신뢰 엔티티 매칭)

노이즈 섞인 문자열(OCR/음성/수기 입력)을 신뢰 가능한 엔티티(선수/사람/제품/계정)에 연결하는 다단계 게이트 패턴. 원본은 고정 6인 로스터 + 운영자 수동 alias 관리 변형이지만, 폐쇄 집합 엔티티 매칭 전반에 재사용 가능하다.

**전체 사양(스키마, 참조 구현 클래스, 운영 워크플로우)은 `references/full-spec.md`를 읽을 것.** 아래는 설계 결정에 필요한 핵심만 요약.

## 5-Layer Pipeline

1. **OCR + Roster hint** — 비전 모델 프롬프트에 정답 후보 목록을 주입. 1~2글자 오독은 교정하되, 후보에 없으면 절대 강제 매칭 금지(읽힌 그대로 출력) → hallucination 방어.
2. **Matcher (3-stage gate)** — normalize → exact dict lookup → Jaro-Winkler 퍼지(score + margin).
3. **Decider** — method별 분기: `exact`/`fuzzy_auto` → Matched, `review` → 운영자 알림, `no_match` → Unmatched.
4. **Alias Dictionary** — 확인된 변형을 영구 저장 → 다음부터 exact hit. 자동 학습 여부는 정책 결정(아래).
5. **Reconcile (safety net)** — 주기적 TTL 캐시 리프레시 + 미매칭 레코드 재스캔. alias가 나중에 추가되면 과거 레코드 자동 정정.

## 판정 임계치 (시작값, 실데이터로 튜닝)

```python
T_HIGH = 0.92   # 이상 + margin 충족 → fuzzy_auto (자동 확정)
T_LOW  = 0.75   # 미만 → no_match
MARGIN = 0.08   # top1 − top2(다른 엔티티) 차이. 미만이면 충돌 → review
```

- 폐쇄 소집합(예: 6명)이면 MARGIN 0.05까지 낮춰도 되지만, 비슷한 이름 쌍이 있으면 0.10~0.12로 올릴 것.
- 튜닝은 실데이터 1~2주 confusion matrix로.

## 함정 3가지 (구현 시 반드시 확인)

1. **Per-entity best score** — 한 엔티티가 canonical + alias로 후보에 여러 번 등장한다. 전부 정렬하면 같은 엔티티의 두 변형이 1·2위를 차지해 **가짜 conflict**가 생긴다. 엔티티별 최고 점수만 남긴 뒤 margin을 계산할 것. (가장 흔한 버그 — 참조 구현의 `match()` 참고)
2. **정규화에서 CJK 보존** — `re.sub(r"[^\w]", "", s, flags=re.UNICODE)`로 한글/가나가 살아남아야 함. clan tag `[XX]`, 구분자 등 도메인 노이즈 제거는 normalize 한 곳에 모은다.
3. **alias 학습 안전장치** — 이미 다른 엔티티에 할당된 변형은 덮어쓰지 않기(`n in matcher.exact` 체크). `Source` 필드(Manual/Auto)로 감사 추적 → 잘못된 alias 롤백 가능.

## 정책 결정 2가지 (사용자와 확인)

- **자동 학습 ON/OFF**: 폐쇄 소집합은 OFF(운영자 주도) 권장 — 한 번 잘못 학습되면 영향이 큼. 대규모 개방 집합은 ON이 실용적.
- **no_match의 의미**: 폐쇄 집합에서 no_match = "집합 밖의 존재"(게스트/오탐). review("이 사람 맞아?")와 알림을 구분해서 처리.

## 새 도메인 적용 체크리스트

- [ ] 정규화 규칙: 도메인 노이즈(clan tag? 법인형태? 조사?)를 무엇으로 정의하나
- [ ] 엔티티 후보 수: 폐쇄 집합이면 MARGIN↓ + 자동 학습 보수적으로
- [ ] 부트스트랩: 누가 canonical 엔티티와 초기 alias를 입력하는가
- [ ] 임계치 3종 튜닝 계획
- [ ] Human-in-the-loop: review/no_match 알림 채널 + 수동 link/reject 명령
- [ ] Audit trail(`Source`) + Reconcile 주기

## 설계 원칙

Defense in depth(중첩 게이트가 정확도를 만든다) · Self-improving(판정된 변형은 다음 비용 0) · 자동화는 높은 신뢰구간만, 애매하면 human review · 폐쇄 집합의 특성(후보가 적음 = OCR hint 효과 극대화)을 활용.

데이터 스키마(3-테이블), 운영자 워크플로우, 전체 참조 구현 코드는 `references/full-spec.md` 참조.
