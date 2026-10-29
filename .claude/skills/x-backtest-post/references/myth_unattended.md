# 속설 검증 시리즈 — 무인 실행 (매일 13:00)

`scripts/myth_daily.sh`가 launchd(`~/Library/LaunchAgents/im.nullstock.myth-daily.plist`)로 매일 13:00 KST에
`claude -p "/x-backtest-post 속설 검증 무인 실행 …"`을 띄운다. 로그 `~/Library/Logs/nullstock-myth-daily.log`.

**사용자 상시 지시(2026-10-29)**: 주제 선정부터 전략 조건·영상·글·게시까지 알아서 한다. 이 지시가 SKILL.md의
"미리보기 없이 게시하지 않는다"·"게시 전에 사용자가 들어 봐야 한다"를 이 무인 실행에 한해 대신한다.
그 밖의 시리즈 규칙(SKILL.md "속설 검증 시리즈"·글 형식 1~7)은 전부 그대로 지킨다.

정해진 정책(사용자 선택):
- **검증에서 문제가 나오면 그 주제를 접고 다음 후보로 간다(최대 3개). 셋 다 안 되면 그날은 게시하지 않는다.**
  문제 = 해석이 문장과 다름 · 매수 표본 재계산 불일치 · 청산 손익 합≠총 손익 · 원인 못 찾은 상식 밖 결과 · 영상과 사진 실행의 지표가 다름.
  틀린 결과가 공개되는 것보다 하루 쉬는 쪽이 낫다. 문제를 글에 밝히고 올리는 길은 쓰지 않는다.
- **연구노트(`/notes`) 추가는 하지 않고 보류 목록에 남긴다** — 코드 수정·운영 DB 쓰기는 사람이 있는 세션에서 한다.
- 물을 사람이 없다: `AskUserQuestion`을 쓰지 않는다. 코드·스킬·데이터를 고치지 않는다(해석 결함은 보고만). 커밋하지 않는다.

## 1. 번호와 후보

- 번호 = `references/myth_series.md`에서 게시된 가장 큰 속설 번호 + 1. 같은 날 이미 게시된 편이 있으면(표의 날짜) 아무것도 하지 않고 끝낸다.
- 후보 3개를 순서대로 정한다: 표에 없는 흔한 매매 속설(게시·보류 줄 모두 제외 — 같은 속설을 조건만 바꿔 다시 하지 않는다), 직전 3편과 다른 계열(기술적·재무·수급·이벤트)로.
- 엔진이 표현할 수 있는 조건만 쓴다. 문장은 **매수 신호 + 매도 신호(또는 N거래일 보유 후 매도)**를 모두 담고, 시장(KOSPI·KOSDAQ·KOSPI200)을 정한다. 문장에 값이 없으면 되묻기가 생기므로 기준값을 문장에 넣는다.

## 2. 결과·사진 실행 (후보마다)

작업 폴더 `~/nullstock-cf/myth-<NN>-<영문 주제>-<MMDD>/`(이미 있으면 뒤에 `-r2`).

```bash
mkdir -p $D/photos && cat > $D/photos/spec.json   # {"prompt", "answers", "post_name"}
bash .claude/skills/news-strategy-test/scripts/run_test.sh $D/photos   # result.json·shot_*.png·trades.txt
```

`answers` 기본: `["최대 10종목", "리밸런싱 안 함", "손절 안 함", "익절 안 함", "최근 5년 데이터", "1,000만원"]`. 다른 설정 질문으로 멈추면 가장 중립적인 칩을 더해 다시 돈다. 매수·매도 신호를 되물으면 문장을 고친다(문장이 신호를 잃은 것이면 해석 결함 → 다음 후보).
"[중단] 9222"면 10분 간격 3번 다시 시도, 그래도 막히면 그날은 끝낸다.

## 3. 검증 — 하나라도 실패하면 다음 후보

1. `result.json`의 `summary`가 문장과 같은 말인가(시장·조건·기준값·기간·매도 방식). 문장에 없는 조건이 끼거나 값이 바뀌면 실패.
2. `trades.txt`(매매 기록 탭)와 `data/ohlcv/<코드>.parquet`으로 **매수 표본 30건을 다시 계산**해 신호 조건과 맞는지(전날 데이터 기준). 1건이라도 설명 못 하는 불일치면 실패.
3. 청산 손익 합이 총 수익과 몇 원 안에서 같은가.
4. 가장 큰 손실 거래 1~2건의 원인(거래정지·갭하락·하한가)을 가격·거래량으로 확인한다. 원인을 못 찾아도 실패는 아니지만 글에 원인을 쓰지 않는다.

## 4. 영상

`~/nullstock-cf/<slug>/spec.json`(같은 prompt·answers + `post_name`, `aiShot`)과 `meta.json`(`{"eyebrow": "속설 검증 #NN", "title": "“<속설>”"}`)을 쓰고
`bash .claude/skills/x-backtest-post/scripts/studio_make.sh <slug>`(Bash timeout 600000). 그 뒤:
- `result.json` 지표가 2의 결과와 같아야 한다(다르면 실패 → 다음 후보).
- `~/nullstock-cf/.work/<slug>/review_sheet.png`를 Read로 열어 합격 기준(그래프 장면·끝 카드 수치·잘림 없음)을 본다. 어긋나면 한 번 다시 만들고, 그래도 어긋나면 그날은 끝낸다.
- `ffprobe`로 1920×1080·`rotation` 없음·audio 스트림 있음을 확인한다. 소리는 직접 듣지 못한다 — report에 적는다.
- `studio_make.sh`가 `post1.txt`를 일반 글로 덮어쓴다 — 아래 5에서 속설 글로 다시 쓴다.

## 5. 글

- `post1.txt`: SKILL.md 글 형식 1·4-1·6·6-1·7을 따른다. 직전 3~4편의 `~/nullstock-cf/myth-*/post1.txt`·`post2_reply.txt`를 읽고 표현·소제목·순서를 겹치지 않게 새로 쓴다(X API로 읽지 않는다 — 로컬 파일이 같은 내용).
  링크는 `uv run python -c "import sys; sys.path.insert(0,'scripts'); from post_to_x import strategy_open_url; print(strategy_open_url(open('prompt.txt').read(), 'myth-<NN>'))"`로 만든 주소를 내 문구 안에 넣는다.
- `post2_reply.txt` + 사진 2~4장: `photos/shot_b_overview.png` 필수 + 이번 특징에 맞고 **직전 편과 다른 조합**(myth_series.md의 `사진=` 기록과 대조).
- 게시 전 자기 점검: 두 글에서 `추천|유망|권장|전망|적합|우수|유리|기대|보장|수혜|맞았|틀렸|대기 시간|위 수치는 과거 데이터로|미래 수익` 이 나오면 고쳐 쓴다. 숫자는 `result.json`·로그와 다시 대조한다.

## 6. 게시

```bash
uv run python scripts/post_to_x.py --file $OUT/post1.txt --long --video $OUT/final.mp4            # 미리보기 — 가중 글자 수 확인
uv run python scripts/post_to_x.py --file $OUT/post1.txt --long --video $OUT/final.mp4 --post     # → POSTED_ID 확인
uv run python scripts/post_to_x.py --file $OUT/post2_reply.txt --long --image … --reply-to <POSTED_ID> --post
```

하나씩 올리고 `POSTED_ID=`를 확인한 뒤 다음을 올린다. 끝나면 `GET /2/tweets?ids=…&tweet.fields=note_tweet,attachments,referenced_tweets`로 답글 연결·첨부를 확인한다.
첫 글 게시가 실패하면 다시 올리지 않고 끝낸다(중복 게시 방지 — 이미 올라갔을 수 있다).

## 7. 기록과 보고

- `references/myth_series.md`에 기존 줄과 같은 형식으로 한 줄 더한다(게시 id·영상 길이·링크 `myth-NN`·`사진=` 조합·검증 사실). 접은 후보도 `—` 번호로 이유와 함께 남긴다.
- 보고서 `~/nullstock-cf/myth-daily-<YYYY-MM-DD>.md`(게시하지 않은 날도 쓴다): 첫 줄은 `게시함: <링크>` 또는 `게시 안 함: <이유 한 줄>`.
  이어서 핵심 수치, 접은 후보와 이유, 내가 정한 값(주제·문장·칩), **연구노트 추가 대기**, 소리를 직접 못 들었다는 것. 알림·파일 열기는 `myth_daily.sh`가 한다.
