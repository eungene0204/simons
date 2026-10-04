// 백테스트 결과 화면에서 사진 3장을 2배 해상도로 캡처한다. 결과 화면(개요 탭)이 열려 있어야 한다.
// 사용: node capture.mjs <접두사>   → <접두사>_b_overview.png, <접두사>_a_strategy.png, <접두사>_c_contrib.png
//   b: 핵심 지표 + 수익 곡선(로그 패널 제외)  a: '내 전략' 팝업(프롬프트·조건·비용·기준값)  c: 종목별·섹터별 기여도
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
await browser.close();
