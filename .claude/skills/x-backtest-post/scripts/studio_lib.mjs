// 스튜디오 녹화 공통 동작 — studio_step.mjs(한 동작씩)와 studio_record.mjs(표준 흐름 전체)가 같이 쓴다.
// 모든 동작은 카메라가 따라갈 위치를 marks.jsonl에 남긴다: 위치는 CSS px(1440×810 화면), 시각은 ms(스크린캐스트와 같은 시계).
import { chromium } from 'playwright';
import fs from 'fs';

export async function connect() {
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const page = browser.contexts().flatMap((c) => c.pages()).find((p) => p.url().startsWith('http://localhost'));
  if (!page) throw new Error('녹화 브라우저(studio_server.mjs)의 앱 화면을 못 찾았다');
  return { browser, page };
}

export const mark = (action, entry) =>
  fs.appendFileSync('marks.jsonl', JSON.stringify({ t: Date.now(), action, ...entry }) + '\n');

const pos = () => { try { return JSON.parse(fs.readFileSync('cursor.json', 'utf8')); } catch { return { x: 1300, y: 700 }; } };
const ease = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const boxOf = (b) => b && { x: b.x, y: b.y, width: b.width, height: b.height };

// 사람 손처럼 가속·감속하며 옮긴다(Playwright 기본 steps는 등속이라 기계적으로 보인다)
export async function glide(page, x, y, ms = 750) {
  const from = pos();
  const n = Math.max(12, Math.round(ms / 16));
  for (let i = 1; i <= n; i++) {
    const u = ease(i / n);
    await page.mouse.move(from.x + (x - from.x) * u, from.y + (y - from.y) * u);
    await page.waitForTimeout(ms / n);
  }
  fs.writeFileSync('cursor.json', JSON.stringify({ x, y }));
}

export async function press(page, locator, label, action = 'click') {
  await locator.scrollIntoViewIfNeeded();
  let b = boxOf(await locator.boundingBox());
  if (!b) throw new Error(`위치를 알 수 없다: ${label}`);
  mark(action, { phase: 'approach', label, box: b });
  await glide(page, b.x + b.width / 2, b.y + b.height / 2);
  await page.waitForTimeout(280);
  // 커서가 다가가는 사이 배치가 바뀌면(그래프 재배치 등) 같은 자리의 다른 버튼을 누른다 — 누르기 직전에 위치를 다시 재서 따라간다
  let b2 = boxOf(await locator.boundingBox()) ?? b;
  for (let k = 0; k < 3 && (Math.abs(b2.x - b.x) > 2 || Math.abs(b2.y - b.y) > 2); k++) {
    b = b2;
    await glide(page, b.x + b.width / 2, b.y + b.height / 2);
    await page.waitForTimeout(400);
    b2 = boxOf(await locator.boundingBox()) ?? b;
  }
  b = b2;
  mark(action, { phase: 'press', label, box: b });
  await page.mouse.down(); await page.waitForTimeout(90); await page.mouse.up();
  await page.waitForTimeout(450);
}

export const visibleText = (page, text) => page.getByText(text, { exact: false }).locator('visible=true').first();

export async function typePrompt(page, text) {
  const box = page.locator('textarea:visible').last();
  const b = boxOf(await box.boundingBox());
  mark('type', { phase: 'approach', label: 'input', box: b });
  await glide(page, b.x + 40, b.y + 30);
  await page.mouse.down(); await page.mouse.up();
  mark('type', { phase: 'typing', label: 'input', box: b });
  await box.pressSequentially(text, { delay: 32 });
  await page.waitForTimeout(700);
  mark('type', { phase: 'send', label: 'input', box: boxOf(await box.boundingBox()) ?? b });
  await page.keyboard.press('Enter');
}

/** 글자(문자열 또는 RegExp)가 화면에 보일 때까지 기다렸다가 '나타난 순간'과 위치를 남긴다. */
export async function waitFor(page, name, text, timeoutSec = 300) {
  const loc = visibleText(page, text);
  await loc.waitFor({ state: 'visible', timeout: timeoutSec * 1000 });
  const b = boxOf(await loc.boundingBox());
  mark('appear', { phase: 'appear', label: name, box: b });
  return b;
}

/** 진행 표시('… 중...')가 사라질 때까지 기다린다(칩 답변 뒤 다음 질문이 뜨는 순간). */
export async function settle(page, timeoutSec = 90) {
  const busy = page.getByText(/분석 중\.\.\.|생각 중\.\.\.|확인 중\.\.\./).locator('visible=true');
  const until = Date.now() + timeoutSec * 1000;
  await page.waitForTimeout(800);
  while (Date.now() < until && (await busy.count()) > 0) await page.waitForTimeout(400);
}

/** a를 품은 상자 안에서 b를 찾아, 둘을 함께 품은 가장 작은 상자의 위치를 남긴다(요약 카드·지표 줄). */
export async function card(page, name, a, b) {
  const box = await page.evaluate(([a, b]) => {
    const leaf = (t) => [...document.querySelectorAll('body *')].find((e) => e.children.length === 0 && e.offsetParent !== null && e.textContent.trim().startsWith(t));
    // 두 번째 글자는 첫 글자를 품은 상자 안에서만 찾는다 — 화면 전체에서 찾으면 다른 패널의 같은 글자를 잡아 너무 큰 상자가 된다
    const inside = (n) => [...n.querySelectorAll('*')].some((e) => e.children.length === 0 && e.textContent.trim().startsWith(b));
    let n = leaf(a);
    while (n && !inside(n)) n = n.parentElement;
    if (!n) return null;
    const r = n.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  }, [a, b]);
  if (!box) throw new Error(`상자를 못 찾았다: ${a} / ${b}`);
  mark('card', { phase: 'card', label: name, box });
  return box;
}

export async function hold(page, sec = 3) {
  await glide(page, 1420, 790, 600);
  mark('hold', { phase: 'hold' });
  await page.waitForTimeout(sec * 1000);
}

// ── 전략 그래프 관찰(2026-10-19) ─────────────────────────────────────────────
// 결과 해석은 채팅의 항목 목록이 아니라 전략 그래프(data-testid="strategy-graph-canvas")로 그려진다. 칩에 답할 때마다 그래프에
// 노드가 붙으므로, '새 노드가 DOM에 생긴 순간'과 그 위치를 기록해 편집이 변화 지점으로 줌인할 수 있게 한다.

/** 마지막으로 보이는 그래프의 노드 집합 변화를 window.__gw.log에 남기는 관찰자를 건다(입력 전에 한 번). */
export async function watchGraph(page) {
  await page.evaluate(() => {
    if (window.__gw) return;
    const gw = (window.__gw = { log: [], prev: new Map(), pending: false });
    const scan = () => {
      gw.pending = false;
      const c = [...document.querySelectorAll('[data-testid="lab-canvas"]')].filter((e) => e.offsetParent !== null).at(-1);
      if (!c) return;
      const cur = new Map([...c.querySelectorAll('.react-flow__node')].map((g) => [g.dataset.id, g.innerText.replace(/\s+/g, ' ').trim()]));  // 연구소 캔버스(React Flow) 노드
      const added = [...cur].filter(([k]) => !gw.prev.has(k));
      if (added.length) gw.log.push({ t: Date.now(), added: added.map(([key, text]) => ({ key, text })) });
      gw.prev = cur;
    };
    new MutationObserver(() => { if (!gw.pending) { gw.pending = true; requestAnimationFrame(scan); } }).observe(document.body, { childList: true, subtree: true });
  });
}

/**
 * 그래프가 하단에 고정된 질문 패널 뒤에 가려져 있으면(실제 화면에서도 사용자가 위로 스크롤해야 보인다) 패널 위로 올라오게 스크롤한다.
 * 노드가 생기는 순간 바로 실행해야 편집의 카메라 상자(스크롤 뒤 위치)와 화면이 어긋나지 않는다. 스크롤한 시각(ms)을 돌려준다.
 */
async function revealGraph(page, top = 130, fit = true) {
  // 전략 연구소(2026-10-28): 캔버스는 화면 위쪽에 고정돼 있고, 앱은 처음 그래프만 화면에 맞춘다 — 칩 답변으로 붙은 노드는
  // 캔버스 아래(채팅 패널 뒤)로 나가 보이지 않는다(#30 영상 실측). 사용자가 하듯 '화면 맞춤'을 눌러 새 노드까지 캔버스 안에 담는다.
  const fitted = fit && await page.evaluate(() => {
    const b = [...document.querySelectorAll('[data-testid="lab-canvas"] button[aria-label="화면 맞춤"]')].find((e) => e.offsetParent !== null);
    if (!b) return false;
    b.click();
    return true;
  });
  if (fitted) { await page.waitForTimeout(450); return Date.now(); }  // 맞춤 애니메이션(200ms)이 끝난 뒤 위치를 잰다
  await page.evaluate((top) => {
    const c = [...document.querySelectorAll('[data-testid="lab-canvas"]')].filter((e) => e.offsetParent !== null).at(-1);
    if (!c) return;
    let p = c.parentElement;
    while (p && !(p.scrollHeight > p.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(p).overflowY))) p = p.parentElement;
    const r0 = c.getBoundingClientRect();
    if (r0.top >= 0 && r0.bottom <= window.innerHeight + 4) return;  // 연구소는 캔버스가 화면 안에 고정돼 있어 스크롤하지 않는다
    const dy = r0.top - top;
    if (p) p.scrollBy({ top: dy, behavior: 'instant' }); else window.scrollBy({ top: dy, behavior: 'instant' });
  }, top);
  return Date.now();
}

/** 캔버스 안에 보이는 노드 전부를 품은 상자(카메라가 그래프 전체를 담을 때 — 캔버스 상자는 빈 여백까지 품어 그래프가 잘린다). */
async function nodesBox(page) {
  return page.evaluate(() => {
    const c = [...document.querySelectorAll('[data-testid="lab-canvas"]')].filter((e) => e.offsetParent !== null).at(-1);
    if (!c) return null;
    const rs = [...c.querySelectorAll('.react-flow__node')].map((g) => g.getBoundingClientRect()).filter((r) => r.width > 0);
    if (!rs.length) return null;
    const x0 = Math.min(...rs.map((r) => r.x)), y0 = Math.min(...rs.map((r) => r.y));
    const x1 = Math.max(...rs.map((r) => r.right)), y1 = Math.max(...rs.map((r) => r.bottom));
    return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
  });
}

/**
 * since 이후 그래프에 새 노드가 생겼는지 기다렸다가(최대 timeoutSec), 연출이 끝나길 settleMs 기다린 뒤 변화 위치를 남긴다.
 * mark('graph', {phase: 'add'|'initial', label, t: 처음 생긴 시각, box: 새 노드들을 품은 상자, canvas: 그래프 전체 상자, texts})
 * 새 노드가 없으면 null(그 칩은 그래프를 바꾸지 않은 것 — 편집은 그래프 장면을 만들지 않는다).
 */
export async function graphAdd(page, label, since, { phase = 'add', settleMs = 2800, timeoutSec = 6 } = {}) {
  const until = Date.now() + timeoutSec * 1000;
  let hits = [];
  while (Date.now() < until) {
    hits = (await page.evaluate(() => window.__gw?.log ?? [])).filter((e) => e.t >= since);  // 입력 뒤 페이지가 다시 로드되면 관찰자가 사라진다(10-29 실측) — 변화 없음으로 본다
    if (hits.length) break;
    await page.waitForTimeout(100);
  }
  if (!hits.length) return null;
  const first = await revealGraph(page, 130, phase !== 'initial');  // 맞춘(스크롤한) 시각이 편집의 기준점이다. 처음 그래프는 앱이 스스로 맞춘다
  await page.waitForTimeout(Math.max(0, first + settleMs - Date.now()));  // 노드가 하나씩 나타나는 연출이 끝나길 기다린다(처음 그릴 때 최대 약 7초)
  const added = (await page.evaluate(() => { const l = window.__gw?.log ?? []; if (window.__gw) window.__gw.log = []; return l; })).filter((e) => e.t >= since).flatMap((e) => e.added);
  const keys = added.map((a) => a.key);
  const m = await page.evaluate((keys) => {
    const c = [...document.querySelectorAll('[data-testid="lab-canvas"]')].filter((e) => e.offsetParent !== null).at(-1);
    if (!c) return null;
    const rect = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
    const boxes = [...c.querySelectorAll('.react-flow__node')].filter((g) => keys.includes(g.dataset.id)).map(rect);
    const x0 = Math.min(...boxes.map((b) => b.x)), y0 = Math.min(...boxes.map((b) => b.y));
    const x1 = Math.max(...boxes.map((b) => b.x + b.w)), y1 = Math.max(...boxes.map((b) => b.y + b.h));
    const cv = rect(c);
    return { canvas: { x: cv.x, y: cv.y, width: cv.w, height: cv.h }, texts: [...c.querySelectorAll('.react-flow__node')].filter((g) => keys.includes(g.dataset.id)).map((g) => g.innerText.replace(/\s+/g, ' ').trim()), box: boxes.length ? { x: x0, y: y0, width: x1 - x0, height: y1 - y0 } : null };
  }, keys);
  if (!m) return null;
  const nodes = await nodesBox(page);
  const texts = (m.texts?.length ? m.texts : added.map((a) => a.text)).filter(Boolean);  // 노드는 DOM에 생긴 직후 비어 있을 수 있어 연출이 끝난 뒤 글자를 다시 읽는다
  mark('graph', { t: first, phase, label, texts, box: m.box ?? m.canvas, canvas: m.canvas, nodes });
  return { ...m, texts, t: first };
}

/** 지금 보이는 그래프 전체의 위치를 남긴다(확정 직전 완성된 모양 — 확정 장면이 이 상자로 당긴다). */
export async function graphBox(page, label) {
  await revealGraph(page);
  await page.waitForTimeout(400);
  const b = await page.evaluate(() => {
    const c = [...document.querySelectorAll('[data-testid="lab-canvas"]')].filter((e) => e.offsetParent !== null).at(-1);
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  });
  const nodes = await nodesBox(page);
  if (b) mark('graph', { phase: 'final', label, box: b, canvas: b, nodes, texts: [] });
  return b;
}
