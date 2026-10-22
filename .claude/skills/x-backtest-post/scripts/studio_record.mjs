// 스튜디오 표준 흐름을 한 번에 녹화한다(studio_server.mjs가 떠 있어야 한다).
// 입력 → 대화 기록 접기 → 해석 카드 → 칩 답변 → 확정 → 실행 → 결과 → AI 리포트 점수 카드.
// 해석 카드·결과가 '나타난 순간'을 직접 기록하므로 편집점을 눈으로 찾을 필요가 없다(make_plan.py가 읽는다).
//
// 사용: node studio_record.mjs spec.json
//   spec: { "prompt": "<문장 그대로>",
//           "answers": ["리밸런싱 안 함", "익절 안 함", "최근 5년 데이터", "1,000만원"],   // 칩 글자(우선순위 순)
//           "typed": [{"question": "기간", "text": "2021년 1월부터 2025년 12월까지"}],   // 칩에 없는 답(질문 문구 일부 → 입력)
//           "aiShot": "ai.png" }
// 출력: marks.jsonl(카메라 기록), result.json(해석 카드·지표·로그·AI 핵심 요약), trades.txt(매매 기록 탭), <aiShot>
// 준비된 답이 없는 질문이 나오면 질문을 출력하고 멈춘다 — 답을 정해 spec에 넣고 처음부터 다시 녹화한다.
import fs from 'fs';
import { connect, typePrompt, press, glide, visibleText, waitFor, settle, card, hold, mark, watchGraph, graphAdd, graphBox } from './studio_lib.mjs';

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const { browser, page } = await connect();
const button = (t) => page.locator('button:visible', { hasText: t }).first();
const log = (...a) => console.log(new Date().toTimeString().slice(0, 8), ...a);

await page.waitForTimeout(1500);
await watchGraph(page);
await typePrompt(page, spec.prompt);
log('입력 완료');
await waitFor(page, 'status', /분석 중|생각 중/, 30).catch(() => log('진행 표시를 못 봤다(카메라는 전체 화면으로 둔다)'));
try {
  await press(page, page.locator('[aria-label="대화 기록 닫기"]:visible').first(), '대화 기록 닫기', 'label');
} catch { log('대화 기록 패널이 없어 접지 않았다'); }

await waitFor(page, 'card', '현재까지 이해한', 420);
await settle(page);
const firstCard = await card(page, 'summary', '현재까지 이해한', '리스크 관리').catch(() => null);
log('해석 카드:', firstCard ? 'ok' : '위치 못 찾음');
// 처음 그려지는 그래프(노드가 하나씩 나타나는 연출, 최대 약 7초)가 끝날 때까지 칩을 누르지 않는다 — 편집이 이 구간을 통째로 보여 준다
const g0 = await graphAdd(page, 'initial', 0, { phase: 'initial', settleMs: 8500, timeoutSec: 15 });
log('처음 그래프:', g0 ? g0.texts.join(' / ') : '그래프를 못 찾음(편집은 텍스트 카드로 대체)');

const answers = [...spec.answers];
const answered = [];
const retried = new Set();
let misses = 0;
for (let i = 0; i < 12; i++) {
  if (await button('이 전략으로 확정').count()) break;
  const hit = await (async () => {
    for (const a of answers) if (await button(a).count()) return a;
    // 누른 칩이 먹지 않아 같은 질문이 그대로 남았으면(카드 전환 중 클릭 소실, 10-21 스페이스X 실측) 그 칩을 한 번 더 누른다
    for (const a of answered) if (!retried.has(a) && await button(a).count()) { retried.add(a); answers.push(a); return a; }
    return null;
  })();
  if (!hit && (misses++ < 4 || (misses < 40 && await page.getByText('파싱 중').count()))) { await settle(page, 150); await page.waitForTimeout(1500); i--; continue; } // 다음 질문이 그려지기 전에 확인하는 경쟁 — 진행 표시('생각 중...')가 사라질 때까지(앱 응답이 느리면 10초 넘게) 기다렸다 다시 본다
  if (!hit) {
    const qs = (await page.innerText('body')).split('\n').filter((l) => /까요\?|주세요\.?$/.test(l.trim()));
    const q = qs.at(-1);
    // 마지막 줄은 '…입력창에 적어 주세요' 같은 안내일 수 있어 마지막 두 줄에서 찾는다
    const typed = (spec.typed || []).find((x) => qs.slice(-2).some((l) => l.includes(x.question)) && !answered.includes(x.text));
    if (typed) {
      // 칩에 없는 값(예: 끝 날짜를 정한 기간)은 카드의 입력창에 적어 보낸다 — 카메라는 칩처럼 입력창으로 다가간다
      const box = page.locator('input[placeholder*="직접 적어"]:visible, input[placeholder*="원하는 내용"]:visible').last();
      const b = await box.boundingBox();
      mark('click', { phase: 'approach', label: typed.text, box: b });
      await glide(page, b.x + 60, b.y + b.height / 2);
      await page.mouse.down(); await page.mouse.up();
      await box.pressSequentially(typed.text, { delay: 32 });
      await page.waitForTimeout(500);
      mark('click', { phase: 'press', label: typed.text, box: b });
      await page.keyboard.press('Enter');
      await page.waitForTimeout(450);
      answered.push(typed.text);
      misses = 0; // 직접 입력 뒤에도 다음 질문을 기다릴 재시도 횟수를 되살린다
      await settle(page);
      await graphAdd(page, typed.text, Date.now() - 20000);
      continue;
    }
    throw new Error(`준비된 답이 없는 질문: ${q ?? '(질문 문구 못 찾음)'} — spec.answers에 칩 글자(또는 spec.typed에 직접 입력)를 넣고 다시 녹화한다`);
  }
  misses = 0;
  const since = Date.now();
  await press(page, button(hit), hit);
  answers.splice(answers.indexOf(hit), 1);
  answered.push(hit);
  await settle(page);
  const ga = await graphAdd(page, hit, since);  // 이 답으로 그래프에 생긴 노드(없으면 null)
  log('그래프 변화:', hit, '→', ga ? ga.texts.join(' / ') : '없음');
}
log('칩 답변:', answered.join(' / '));

await graphBox(page, 'final');   // 확정 장면은 완성된 그래프로 당긴다
await card(page, 'summary_full', '현재까지 이해한', '리스크 관리');
const summaryText = await page.evaluate(() => {
  const leaf = [...document.querySelectorAll('body *')].find((e) => e.children.length === 0 && e.textContent.trim().startsWith('현재까지 이해한'));
  let n = leaf; while (n && !n.innerText.includes('리스크 관리')) n = n.parentElement;
  return n ? n.innerText : '';
});
await page.waitForTimeout(1200);
await press(page, button('이 전략으로 확정'), '이 전략으로 확정');
await button('백테스트 시작하기').waitFor({ state: 'visible', timeout: 60000 });
await page.waitForTimeout(1200);
// 지정 종목 — 확정된 전략 그래프의 '지정 종목 N개' 노드를 눌러 어떤 종목인지 펼쳐 보여 준다(2026-10-21 사용자 지시). 노드가 없으면 건너뛴다(편집도 이 기록이 있을 때만 장면을 만든다)
const uniNode = page.locator('[data-testid="strategy-graph-canvas"] [data-item-key]:visible', { hasText: /지정 종목 \d+개/ }).first();
if (await uniNode.count()) {
  const label = (await uniNode.innerText().catch(() => '지정 종목')).replace(/\s+/g, ' ').trim();
  await uniNode.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(500);
  await press(page, uniNode, label, 'universe');
  await page.waitForTimeout(1500);   // 펼침 애니메이션(노드 이동 450ms) + 목록 배치
  const cb = await page.evaluate(() => {
    const c = [...document.querySelectorAll('[data-testid="strategy-graph-canvas"]')].filter((e) => e.offsetParent !== null).at(-1);
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  });
  mark('card', { phase: 'card', label: 'universe', box: cb, count: (label.match(/\d+/) || [''])[0] });
  log('지정 종목 노드 펼침:', label, cb ? 'ok' : '그래프 위치 못 찾음');
  await page.waitForTimeout(5500);   // 편집이 목록을 읽을 시간 동안 정지
}
await button('백테스트 시작하기').evaluate((e) => e.scrollIntoView({ block: 'center' })); // 확정 요약이 길면(종목 칩 두 줄 등) 버튼이 하단 입력 패널 뒤에 가려져 클릭이 먹지 않는다(10-21 스페이스X 실측)
await page.waitForTimeout(600);
await press(page, button('백테스트 시작하기'), '백테스트 시작하기');
log('백테스트 시작');

await waitFor(page, 'result', '투자 수익률', 900);
await page.waitForTimeout(2500);
await card(page, 'metrics', '총 수익', '손익비');
await hold(page, 20); // 결과 둘러보기(make_plan.py)는 이 정지 화면에서 찍는다 — 약 16초 + 사건 구간마다 4.5초
const body = await page.innerText('body');
log('결과 화면 기록');

// 지표: 라벨 줄 다음 두 줄 안의 값(벤치마크는 이름 줄이 하나 더 있다)
const lines = body.split('\n').map((l) => l.trim()).filter(Boolean);
const after = (label, skip = 1) => { const i = lines.indexOf(label); return i < 0 ? null : lines[i + 1 + skip]; };
const metrics = {
  total_profit: after('총 수익'), trades: after('총 거래 수'), cagr: after('연평균수익률'), mdd: after('최대낙폭'),
  roi: after('투자 수익률'), sharpe: after('샤프 비율'), sortino: after('소티노 지수'), win_rate: after('승률'),
  profit_factor: after('손익비'), benchmark_name: after('벤치마크', 0), benchmark: after('벤치마크', 1),
};
const logLines = lines.slice(lines.indexOf('백테스트 로그') + 1).filter((l) => l !== '[INFO]').slice(0, 20);

// 매매 기록 — 수익 곡선의 급락·급등 원인을 녹화 뒤에 확인할 수 있게 저장한다(이 구간은 편집에서 버린다)
await visibleText(page, '매매 기록').click();
await page.waitForTimeout(3000);
fs.writeFileSync('trades.txt', await page.innerText('body'));

fs.writeFileSync('result.json', JSON.stringify({ prompt: spec.prompt, answered, summary: summaryText, metrics, log: logLines, ai_summary: '' }, null, 2));
let aiSummary = '';
try {
// AI 리포트 — 이미 생성돼 있을 수 있다(없으면 생성 버튼)
await visibleText(page, 'AI 리포트').click();
await page.waitForTimeout(2500);
if (await button('리포트 생성').count()) await button('리포트 생성').click();
await page.waitForTimeout(2500);
if (await button('리포트 생성').count()) await button('리포트 생성').click();
await visibleText(page, '/ 100').waitFor({ state: 'visible', timeout: 180000 });
await page.waitForTimeout(1500);
const aiText = await page.innerText('body');
aiSummary = (aiText.split('핵심 요약')[1] || '').split('핵심 통찰')[0].trim();
const aiBox = await page.evaluate(() => {
  const leaf = (t) => [...document.querySelectorAll('body *')].find((e) => e.children.length === 0 && e.textContent.trim().startsWith(t));
  let n = leaf('/ 100'); const other = leaf('일관성');
  while (n && other && !n.contains(other)) n = n.parentElement;
  n.scrollIntoView({ block: 'center' });
  const r = n.getBoundingClientRect();
  return { x: r.x, y: r.y, width: r.width, height: Math.min(r.height, 560) };
});
await page.evaluate(() => [...document.querySelectorAll('*')].filter((e) => ['fixed', 'sticky'].includes(getComputedStyle(e).position) && e.getBoundingClientRect().top < 10 && e.id !== '__studio_cursor').forEach((e) => (e.style.visibility = 'hidden')));
// 가짜 커서도 숨긴다 — 남겨 두면 점수 카드의 '안정성' 숫자를 가린다(10-11 #2·#3 실측)
await page.evaluate(() => { const c = document.getElementById('__studio_cursor'); if (c) c.style.visibility = 'hidden'; });
await page.screenshot({ path: spec.aiShot || 'ai.png', clip: aiBox });

} catch (e) { log('AI 리포트 단계 실패(영상 재료는 유지):', String(e).slice(0, 120)); }
mark('done', { phase: 'done' });

fs.writeFileSync('result.json', JSON.stringify({ prompt: spec.prompt, answered, summary: summaryText, metrics, log: logLines, ai_summary: aiSummary }, null, 2));
log('완료 — result.json, marks.jsonl,', spec.aiShot || 'ai.png');
console.log(JSON.stringify(metrics));
await browser.close();
