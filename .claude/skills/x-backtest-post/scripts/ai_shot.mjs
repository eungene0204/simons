// AI 리포트 점수 카드(i_ai)만 찍는다 — AI 리포트 탭에서 리포트가 생성된 뒤에. 사용: node ai_shot.mjs <파일>.png
import { chromium } from 'playwright';
import fs from 'fs';
const browser = await chromium.connectOverCDP('http://localhost:9222');
// 녹화 브라우저(record_server.mjs)는 로그인용 컨텍스트를 닫고 새 컨텍스트를 쓴다 — 앱 화면이 열린 페이지를 찾는다
const page = browser.contexts().flatMap((c) => c.pages()).find((p) => p.url().startsWith('http://localhost'));
const ctx = page.context();
const cdp = await ctx.newCDPSession(page);
await page.setViewportSize({ width: 1440, height: 1500 });
const box = await page.evaluate(() => {
  const leaf = (t) => [...document.querySelectorAll('*')].find((e) => e.children.length === 0 && e.textContent.trim().startsWith(t));
  let n = leaf('/ 100'); const other = leaf('일관성');
  while (n && other && !n.contains(other)) n = n.parentElement;
  n.scrollIntoView({ block: 'start' });
  const r = n.getBoundingClientRect();
  return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: Math.min(r.height, 560) };
});
await page.mouse.move(2, 2);
await page.evaluate(() => [...document.querySelectorAll('*')].filter((e) => ['fixed', 'sticky'].includes(getComputedStyle(e).position) && e.getBoundingClientRect().top < 10).forEach((e) => (e.style.visibility = 'hidden')));
const { data } = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { ...{ x: box.x, y: box.y, width: box.w, height: box.h }, scale: 2 } });
fs.writeFileSync(process.argv[2], Buffer.from(data, 'base64'));
console.log(process.argv[2], JSON.stringify(box));
await browser.close();
