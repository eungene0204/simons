// 홍보 CF 후반부 녹화: 결과 화면 → 전략 최적화 → 워크포워드 실행·결과 → 몬테카를로 실행·결과
// → 계좌 만들기 → 모의투자 메뉴 → 가상계좌 상세(모니터링 종목 시세) → 종목 화면(현재가·차트).
// cf_server.mjs(studio_server 기반) 브라우저가 백테스트 결과 화면에 있어야 한다. studio_record.mjs 바로 뒤에 이어 돌린다.
//
// 사용: node cf_tail.mjs cf_spec.json
//   spec: { "accountName": "PER·PBR 가상계좌" }
// 출력: marks.jsonl에 이어 쓴다(장면 시작은 action=scene). 결과 수치는 cf_result.json.
import fs from 'fs';
import { connect, press, glide, waitFor, card, hold, mark } from './studio_lib.mjs';

const spec = JSON.parse(fs.readFileSync(process.argv[2] || 'cf_spec.json', 'utf8'));
const { browser, page } = await connect();
const button = (t) => page.locator('button:visible', { hasText: t }).first();
const log = (...a) => console.log(new Date().toTimeString().slice(0, 8), ...a);
const scene = (name) => mark('scene', { phase: 'scene', label: name });
const boxOf = async (loc) => { const b = await loc.boundingBox(); return b && { x: b.x, y: b.y, width: b.width, height: b.height }; };

// studio_record.mjs가 점수 카드를 찍으려고 숨긴 상단 바·커서를 되돌린다
await page.evaluate(() => document.querySelectorAll('*').forEach((e) => { if (e.style && e.style.visibility === 'hidden') e.style.visibility = ''; }));

/** 사람이 휠을 굴리듯 부드럽게 내려서 target의 윗변을 화면 y=top에 맞춘다(scrollIntoView는 한 프레임에 튄다). */
async function smoothScroll(target, top = 110, ms = 900) {
  const b = await target.boundingBox();
  if (!b) throw new Error('스크롤 대상 위치를 모른다');
  await glide(page, 1405, 600, 300); // 오른쪽 가장자리(본문 안)에서 굴린다 — 가운데 커서가 결과 화면을 가리지 않게
  const total = b.y - top;
  const n = Math.max(8, Math.round(ms / 16));
  let done = 0;
  for (let i = 1; i <= n; i++) {
    const u = i / n, e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    const step = Math.round(total * e) - done;
    done += step;
    await page.mouse.wheel(0, step);
    await page.waitForTimeout(ms / n);
  }
  await page.waitForTimeout(500);
}

const leafText = (t) => page.locator(`text=${t}`).locator('visible=true').first();

// ── 1. 워크포워드 ───────────────────────────────────────────────
await page.evaluate(() => document.querySelectorAll('*').forEach((e) => { if (e.scrollTop > 0) e.scrollTop = 0; }));
await page.waitForTimeout(800);
scene('optimize');
await press(page, button('전략 최적화'), '전략 최적화');
await waitFor(page, 'wf_panel', '최적화 대상 파라미터', 30);
await page.waitForTimeout(1500);
mark('card', { phase: 'card', label: 'wf_settings', box: await boxOf(page.locator('[data-testid="backtest-walk-forward-section"]')) });
await page.waitForTimeout(1500);
await smoothScroll(leafText('최적화 대상 파라미터'), 120, 1100);
mark('card', { phase: 'card', label: 'wf_params', box: await card(page, 'wf_params_raw', '최적화 대상 파라미터', '최적화 방법').catch(() => null) });
await page.waitForTimeout(1800);
scene('wf_run');
await press(page, button('워크포워드 분석 시작'), '워크포워드 분석 시작');
log('워크포워드 시작');
await waitFor(page, 'wf_progress', /진행|구간|남은/, 30).catch(() => log('진행 표시를 못 봤다'));
await waitFor(page, 'wf_result', '워크포워드 분석 결과', 900);
log('워크포워드 결과');
await page.waitForTimeout(1500);
scene('wf_result');
await smoothScroll(leafText('워크포워드 분석 결과'), 95, 1100);
await page.mouse.move(1430, 800); // 차트 툴팁이 남지 않게 커서를 치운다
fs.writeFileSync('cursor.json', JSON.stringify({ x: 1430, y: 800 }));
mark('card', { phase: 'card', label: 'wf_summary', box: await card(page, 'wf_summary_raw', '쉽게 이해하기', '검증 구간에서 계좌는').catch(() => null) });
await page.waitForTimeout(2500);
await smoothScroll(leafText('WALK-FORWARD EFFICIENCY'), 95, 1000);
mark('card', { phase: 'card', label: 'wf_metrics', box: await card(page, 'wf_metrics_raw', '검증기간 평균 성과', '평균 거래손익').catch(() => null) });
mark('card', { phase: 'card', label: 'wf_table', box: await card(page, 'wf_table_raw', '구간별 결과', 'W3').catch(() => null) });
mark('hold', { phase: 'wf_hold' });
await page.waitForTimeout(9000);
const wfText = await page.innerText('body');

// ── 2. 몬테카를로 ───────────────────────────────────────────────
scene('mc');
await page.evaluate(() => document.querySelectorAll('*').forEach((e) => { if (e.scrollTop > 0) e.scrollTop = 0; }));
await page.waitForTimeout(700);
await press(page, page.locator('[aria-label="몬테카를로"]:visible').first(), '몬테카를로', 'label');
await waitFor(page, 'mc_panel', '반복 횟수', 30);
await page.waitForTimeout(1200);
await press(page, button('2,000'), '2,000');
await page.waitForTimeout(600);
await press(page, button('몬테카를로 실행'), '몬테카를로 실행');
await waitFor(page, 'mc_result', 'CAGR 분포', 300);
log('몬테카를로 결과');
await page.waitForTimeout(1200);
scene('mc_result');
await smoothScroll(leafText('시뮬레이션 결과'), 95, 1100);
await page.mouse.move(1430, 800);
fs.writeFileSync('cursor.json', JSON.stringify({ x: 1430, y: 800 }));
mark('card', { phase: 'card', label: 'mc_stats', box: await card(page, 'mc_stats_raw', 'CAGR 중앙값', '원래 순서 MDD').catch(() => null) });
await page.waitForTimeout(2500);
await smoothScroll(leafText('CAGR 분포'), 110, 1000);
mark('card', { phase: 'card', label: 'mc_dist', box: await card(page, 'mc_dist_raw', 'CAGR 분포', 'MDD 분포').catch(() => null) });
mark('hold', { phase: 'mc_hold' });
await page.waitForTimeout(8000);
const mcText = await page.innerText('body');

// ── 3. 계좌 만들기 ──────────────────────────────────────────────
scene('account_create');
await page.evaluate(() => document.querySelectorAll('*').forEach((e) => { if (e.scrollTop > 0) e.scrollTop = 0; }));
await page.waitForTimeout(700);
await press(page, button('계좌 만들기'), '계좌 만들기');
await waitFor(page, 'account_modal', '계좌당 초기 모의 투자금', 30);
await page.waitForTimeout(900);
const nameBox = page.locator('input[placeholder*="저PBR 전략"]:visible').first();
const nb = await boxOf(nameBox);
mark('type', { phase: 'approach', label: 'account_name', box: nb });
await glide(page, nb.x + 60, nb.y + nb.height / 2);
await page.mouse.down(); await page.mouse.up();
await nameBox.fill(''); // 기본 이름(전략 이름 + 계좌)이 채워져 있다 — 비우고 친다
mark('type', { phase: 'typing', label: 'account_name', box: nb });
await nameBox.pressSequentially(spec.accountName || 'PER·PBR 가상계좌', { delay: 45 });
await page.waitForTimeout(700);
mark('card', { phase: 'card', label: 'account_modal', box: await card(page, 'account_modal_raw', '가상계좌 만들기', '만들기').catch(() => null) });
// 전략 시뮬레이션은 기본 ON이다 — 꺼져 있을 때만 누른다(누르면 토글이라 기본 ON을 끈다, 10-11 리허설 실측)
const simToggle = page.locator('button[aria-label^="전략 시뮬레이션"]:visible').first();
if ((await simToggle.getAttribute('aria-pressed')) !== 'true') await press(page, simToggle, '전략 시뮬레이션');
mark('card', { phase: 'card', label: 'sim_toggle', box: await boxOf(simToggle) });
await page.waitForTimeout(1200);
await press(page, page.locator('button:visible', { hasText: /^만들기$/ }).first(), '만들기');
await waitFor(page, 'account_toast', '가상계좌를 만들었습니다', 60).catch(() => log('토스트를 못 봤다'));
await page.waitForTimeout(1500);

// ── 4. 가상계좌 상세 — 모니터링 종목 시세 ─────────────────────────
scene('account');
await press(page, page.locator('a:visible, button:visible', { hasText: '모의투자' }).first(), '모의투자');
await waitFor(page, 'account_list', spec.accountName || 'PER·PBR 가상계좌', 60);
await page.waitForTimeout(1500);
await press(page, leafText(spec.accountName || 'PER·PBR 가상계좌'), '계좌 열기');
await waitFor(page, 'account_detail', '모니터링 종목', 60);
// 모니터링 종목 시세는 상세가 뜬 뒤 몇 초 지나 채워진다(10-11 리허설 약 5초) — 등락률 칸이 채워진 순간을 남긴다
await page.locator('[data-testid="tracked-symbols-table-scroll"]').getByText(/^[+-]?\d+\.\d{2}%$/).first().waitFor({ state: 'visible', timeout: 60000 });
mark('appear', { phase: 'appear', label: 'tracked_prices' });
await page.waitForTimeout(1500);
scene('account_live');
await page.mouse.move(1430, 800);
fs.writeFileSync('cursor.json', JSON.stringify({ x: 1430, y: 800 }));
mark('card', { phase: 'card', label: 'account_summary', box: await card(page, 'account_summary_raw', '총 자산', '평가 손익').catch(() => null) });
mark('card', { phase: 'card', label: 'tracked', box: await boxOf(page.locator('[data-testid="tracked-symbols-table-scroll"]').first()) });
mark('card', { phase: 'card', label: 'strategy', box: await card(page, 'strategy_raw', '운용 전략', '전략 교체').catch(() => null) });
mark('hold', { phase: 'account_hold' });
await page.waitForTimeout(12000);
const accountText = await page.innerText('body');

// ── 5. 종목 화면 — 첫 모니터링 종목의 현재가·차트(수동 주문 패널은 제품에서 꺼져 있다: stock-order SHOW_TRADE_PANEL)
scene('stock');
const firstRow = page.locator('[data-testid="tracked-symbols-table-scroll"] .cursor-pointer').first();
await press(page, firstRow, '종목 열기');
await waitFor(page, 'stock_page', '전일 종가', 60);
await page.waitForTimeout(1500);
await page.mouse.move(1430, 790);
fs.writeFileSync('cursor.json', JSON.stringify({ x: 1430, y: 790 }));
mark('card', { phase: 'card', label: 'stock_price', box: await card(page, 'stock_price_raw', '전일 종가', '거래량').catch(() => null) });
mark('hold', { phase: 'stock_hold' });
await page.waitForTimeout(9000);
const stockText = await page.innerText('body');
mark('done', { phase: 'done' });

fs.writeFileSync('cf_result.json', JSON.stringify({ wf: wfText, mc: mcText, account: accountText, stock: stockText }, null, 1));
log('완료 — cf_result.json');
await browser.close();
