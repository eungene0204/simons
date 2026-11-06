---
name: intent-capture
description: 새 기능·변경 아이디어를 구현 전에 `docs/intent/<slug>.md`(proto-spec)로 정리하는 절차. 사용자가 "intent 작성해줘", "intent.md 만들어줘", "/intent-capture", "이 아이디어 정리해서 의도 문서로 남겨줘"라고 하거나, 구현 착수 전에 문제·기대 결과·제약을 먼저 합의하자고 할 때 쓴다. 구현 설계(spec)와 코드 작성은 이 스킬의 범위가 아니다.
---

# Intent 캡처

intent 문서는 개발 과정의 첫 산출물이다. **무엇을 원하는지, 왜인지, 어떤 제약 아래인지**를 originator의 말로
적은 사람이 읽는 proto-spec이고, 버전 관리되며 다음 단계(설계)가 바로 읽는다. 구현 방법은 쓰지 않는다.

## 절차

1. 사용자가 문제를 자기 말로 설명하게 한다. 지금 못 하는 것, 영향받는 사람, 나아진 모습, 범위 밖을 듣는다.
2. 구체해질 때까지 분석가처럼 묻는다 — 범위·사용자·제약·성공 기준. 한 번에 질문 몇 개만, 이미 말한 것은 다시 묻지 않는다.
3. `docs/intent/_template.md`의 섹션(Problem / Proposed outcome / Affected users and systems / Constraints / Open questions)으로
   `docs/intent/<slug>.md`를 쓴다. slug는 소문자 영문·하이픈.
4. 사용자가 읽고 오해를 고친다. 고친 뒤 Status를 `draft` → `accepted`로 바꾸는 것은 **사용자 승인 뒤에만** 한다.
5. 커밋은 사용자가 지시할 때만 한다(경로 명시 스테이징).

## 규칙

- 사용자가 말하지 않은 값·범위를 지어 채우지 않는다. 모르면 `Open questions`에 쓴다.
- Constraints에는 이 저장소의 계약을 해당될 때 옮겨 적는다 — 규제 안전 원칙(추천·전망 금지), 자연어 해석 계약(원문 정규식 금지).
- 이미 있는 intent를 고칠 때는 새 파일을 만들지 않고 같은 파일을 수정한다. 변경 이력은 git이 남긴다.
- intent는 설계 문서가 아니다. 파일·함수·스키마 이름이 본문에 나오기 시작하면 spec 단계로 넘길 내용이다.
