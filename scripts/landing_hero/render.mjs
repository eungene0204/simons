// 소개 페이지 영상 렌더 — 장면 HTML을 시간 t로 한 프레임씩 찍어 webm(VP9)·mp4(H.264)·포스터로 만든다.
// 시간을 직접 넣어 그리므로 녹화 지연이 없고 매번 같은 결과가 나온다(30fps).
// 사용: node scripts/landing_hero/render.mjs [hero|validate|paper ...]   (생략하면 셋 다)
//   hero     설계 단계(히어로 영상)  → public/videos/landing-hero.*
//   validate 검증 단계(워크포워드·몬테카를로) → public/videos/landing-validate.*
//   paper    모의투자 단계(가상계좌 연결)   → public/videos/landing-paper.*
// Playwright는 저장소 의존성이 아니다 — ~/nullstock-cf/.pw 의 것을 쓴다.
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const PW_DIR = path.join(os.homedir(), "nullstock-cf/.pw/");
if (!existsSync(path.join(PW_DIR, "node_modules/playwright"))) {
  console.error(`[중단] Playwright가 없다: ${PW_DIR}`);
  process.exit(1);
}
const { chromium } = createRequire(PW_DIR)("playwright");

const SCENES = { hero: "hero.html", validate: "validate.html", paper: "paper.html" };
const requested = process.argv.slice(2);
const names = requested.length ? requested : Object.keys(SCENES);
for (const name of names) {
  if (!SCENES[name]) {
    console.error(`[중단] 알 수 없는 장면: ${name} (hero|validate|paper)`);
    process.exit(1);
  }
}

const FPS = 30;
const outDir = path.join(ROOT, "public/videos");
mkdirSync(outDir, { recursive: true });
const ff = (args) => execFileSync("ffmpeg", ["-v", "error", "-y", ...args], { stdio: "inherit" });

const browser = await chromium.launch();
for (const name of names) {
  const tmp = path.join(process.env.HERO_TMP ?? os.tmpdir(), `landing-${name}-frames`);
  rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });

  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  await page.goto("file://" + path.join(HERE, SCENES[name]));
  await page.waitForFunction(() => typeof window.renderAt === "function");
  const { duration, posterAt } = await page.evaluate(() => ({ duration: window.DURATION, posterAt: window.POSTER_AT ?? 17.6 }));
  const total = Math.round(duration * FPS);
  for (let i = 0; i < total; i++) {
    await page.evaluate((t) => window.renderAt(t), i / FPS);
    await page.screenshot({ path: path.join(tmp, `f${String(i).padStart(4, "0")}.png`) });
  }
  await page.evaluate((t) => window.renderAt(t), posterAt);
  await page.screenshot({ path: path.join(tmp, "poster.png") });
  await page.close();

  const base = `landing-${name}`;
  const input = ["-framerate", String(FPS), "-i", path.join(tmp, "f%04d.png")];
  ff([...input, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "36", "-pix_fmt", "yuv420p", "-row-mt", "1", "-an", path.join(outDir, `${base}.webm`)]);
  ff([...input, "-c:v", "libx264", "-crf", "27", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", path.join(outDir, `${base}.mp4`)]);
  ff(["-i", path.join(tmp, "poster.png"), "-q:v", "4", path.join(outDir, `${base}-poster.jpg`)]);
  rmSync(tmp, { recursive: true, force: true });
  console.log("done", name);
}
await browser.close();
