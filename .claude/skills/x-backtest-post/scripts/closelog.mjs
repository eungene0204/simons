// 녹화 화면 왼쪽 "대화 기록" 패널을 접는다(첫 입력 직후, 접는 순간은 편집에서 잘라낸다). 사용: node closelog.mjs
import { chromium } from 'playwright';
import fs from 'fs';
const b = await chromium.connectOverCDP('http://localhost:9222');
const p = b.contexts().flatMap((c) => c.pages()).find((x) => x.url().startsWith('http://localhost'));
fs.appendFileSync('marks.log', `${Date.now()} closelog\n`);
const btn = p.locator('[aria-label="대화 기록 닫기"]:visible').first();
await btn.waitFor({ timeout: 20000 });
await btn.click();
await p.mouse.move(1430, 120);
await b.close();
console.log('closed');
