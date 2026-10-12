// motion.html의 장면을 프레임(JPEG)으로 찍는다 — 시간을 직접 넘겨 그리므로 결정적이다.
// 사용: [MOTION_SCRIPT=cf2_script.json] node render_motion.mjs <data.json> <logo.png> <out_dir> <장면:초> [장면:초 ...]
//   MOTION_SCRIPT의 copy(화면 문구)를 window.COPY로 넘긴다 — 대본과 화면 문구를 한 파일에서 고친다
// 출력: <out_dir>/<장면>/<번호>.jpg (30fps)
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const [, , dataPath, logoPath, outDir, ...specs] = process.argv;
const here = path.dirname(fileURLToPath(import.meta.url));
const html = process.env.MOTION_HTML || path.join(here, 'motion.html');
const data = fs.readFileSync(dataPath, 'utf8');
const logo = 'data:image/png;base64,' + fs.readFileSync(logoPath).toString('base64');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const copy = process.env.MOTION_SCRIPT ? JSON.stringify(JSON.parse(fs.readFileSync(process.env.MOTION_SCRIPT, 'utf8')).copy || {}) : '{}';
await page.addInitScript(`window.DATA = ${data}; window.LOGO = ${JSON.stringify(logo)}; window.COPY = ${copy};`);
await page.goto('file://' + html);
await page.evaluate(() => window.ready);
await page.evaluate(() => document.fonts.ready);
for (const spec of specs) {
  const [scene, sec] = spec.split(':');
  const D = Number(sec), n = Math.round(D * 30);
  const dir = path.join(outDir, scene);
  fs.mkdirSync(dir, { recursive: true });
  for (let k = 0; k < n; k++) {
    await page.evaluate(([s, t, D]) => window.draw(s, t, D), [scene, k / 30, D]);
    await page.screenshot({ path: path.join(dir, String(k).padStart(5, '0') + '.jpg'), type: 'jpeg', quality: 93 });
  }
  console.log(scene, n, 'frames');
}
await browser.close();
