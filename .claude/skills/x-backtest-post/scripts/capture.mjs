// 백테스트 결과 화면에서 사진 여러 장을 2배 해상도로 캡처한다. 결과 화면(아무 탭)이 열려 있으면 된다.
// 사용: node capture.mjs <접두사>   → <접두사>_<코드>_<이름>.png
//   b_overview  핵심 지표 + 수익 곡선(로그 패널 제외)      a_strategy  '내 전략' 팝업(글에는 텍스트로 쓰므로 보통 미첨부)
//   c_contrib   종목별·섹터별 기여도                         d_dist      거래 수익률·보유 기간 분포
//   e_factor    팩터 회귀(시장·규모·가치·모멘텀 베타)        f_risk      매매 회전율·하방 위험
//   g_stocks    종목 분석 탭 상단(종목별 평균 매수·매도가·수익)  h_trades    매매 기록 탭 상단(매수·매도 사유)
//   i_ai        AI 리포트 점수 카드(점수·LEVEL·성장성/안정성/일관성)
// b·c는 항상, 나머지는 해당 섹션이 있을 때만 찍힌다(없으면 건너뛰고 이유를 출력).
import { chromium } from 'playwright';
import fs from 'fs';

const prefix = process.argv[2] || 'shot';
const browser = await chromium.connectOverCDP('http://localhost:9222');
const ctx = browser.contexts()[0];
const page = ctx.pages()[0];
const cdp = await ctx.newCDPSession(page);

const shot = async (name, c) => {
  const { data } = await cdp.send('Page.captureScreenshot', {
    format: 'png', captureBeyondViewport: true,
    clip: { x: c.x, y: c.y, width: c.w, height: c.h, scale: 2 },
  });
  fs.writeFileSync(name, Buffer.from(data, 'base64'));
  console.log(name, JSON.stringify(c));
};
const boxOf = (fn) => page.evaluate(fn);

await page.setViewportSize({ width: 1440, height: 1500 });
await page.getByText('개요', { exact: true }).first().click();
await page.waitForTimeout(2000);
await page.mouse.move(2, 2); // 차트 크로스헤어·툴팁이 사진에 남지 않게
await shot(`${prefix}_b_overview.png`, { x: 0, y: 231, w: 1019, h: 619 });

await page.getByText('내 전략', { exact: true }).first().click();
await page.waitForTimeout(1200);
const pop = await boxOf(() => {
  const leaf = [...document.querySelectorAll('*')].find((e) => e.children.length === 0 && e.textContent.trim() === '프롬프트');
  let n = leaf;
  while (n && !['absolute', 'fixed'].includes(getComputedStyle(n).position)) n = n.parentElement;
  const r = n.getBoundingClientRect();
  return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height };
});
await shot(`${prefix}_a_strategy.png`, { x: pop.x, y: pop.y, w: pop.w, h: pop.h });
// 팝업은 Escape로 안 닫힌다 — 제목 영역을 눌러 닫는다
await page.getByText('백테스트 결과', { exact: true }).first().click({ position: { x: 5, y: 5 } });
await page.waitForTimeout(800);

await page.getByText('심화 분석', { exact: true }).first().click();
await page.waitForTimeout(3000);
await page.mouse.move(2, 2);
const sec = await boxOf(() => {
  const find = (t) => [...document.querySelectorAll('*')].find((e) => e.children.length === 0 && e.textContent.trim() === t);
  let n = find('종목별 기여도');
  const other = find('섹터별 기여도');
  while (n && !n.contains(other)) n = n.parentElement;
  const r = n.getBoundingClientRect();
  return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height };
});
await shot(`${prefix}_c_contrib.png`, { x: sec.x, y: sec.y, w: sec.w, h: sec.h });

// 선택 사진 — 두 문구를 함께 품은 가장 작은 상위 요소를 찍는다(startsWith 일치). maxH로 긴 해설 문단을 잘라낸다.
const cardShot = async (name, a, b, maxH = 760) => {
  const box = await page.evaluate(([a, b]) => {
    const leaf = (t) => [...document.querySelectorAll('*')].find((e) => e.children.length === 0 && e.textContent.trim().startsWith(t));
    let n = leaf(a);
    const other = leaf(b);
    while (n && other && !n.contains(other)) n = n.parentElement;
    if (!n || !other) return null;
    n.scrollIntoView({ block: 'start' });
    const r = n.getBoundingClientRect();
    return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height };
  }, [a, b]);
  if (!box) return console.log(`${name} 건너뜀 — '${a}' 섹션 없음`);
  await page.mouse.move(2, 2);
  // 스크롤한 채 찍으면 상단 고정 내비게이션 바가 사진 위에 겹친다 — 찍는 동안만 숨긴다
  const hidden = await page.evaluate(() => [...document.querySelectorAll('*')].filter((e) => ['fixed', 'sticky'].includes(getComputedStyle(e).position) && e.getBoundingClientRect().top < 10).map((e) => (e.style.visibility = 'hidden', e)).length);
  await shot(name, { x: box.x, y: box.y, w: box.w, h: Math.min(box.h, maxH) });
  if (hidden) await page.evaluate(() => document.querySelectorAll('*').forEach((e) => { if (e.style.visibility === 'hidden') e.style.visibility = ''; }));
};
await cardShot(`${prefix}_d_dist.png`, '거래 수익률 분포', '보유 기간 분포', 575); // 아래 MAE/MFE 표는 잘라낸다
await cardShot(`${prefix}_e_factor.png`, '팩터 회귀', '알파(연환산)', 530);
await cardShot(`${prefix}_f_risk.png`, '매매 회전율', '하방 위험');

// 다른 탭은 화면 상단(탭 줄 아래)을 뷰포트 기준으로 찍는다 — 표가 길어서 상위 ~9행만.
const topOfTab = async (tab, name, wait = 2500) => {
  await page.getByText(tab, { exact: true }).first().click();
  await page.waitForTimeout(wait);
  await page.evaluate(() => scrollTo(0, 0));
  await page.mouse.move(2, 2);
  await shot(name, { x: 0, y: 231, w: 1440, h: 670 });
};
await topOfTab('종목 분석', `${prefix}_g_stocks.png`);
await topOfTab('매매 기록', `${prefix}_h_trades.png`);
await page.getByText('AI 리포트', { exact: true }).first().click();
await page.waitForTimeout(3000);
await cardShot(`${prefix}_i_ai.png`, '/ 100', '일관성', 560);
await browser.close();
