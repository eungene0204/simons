// 소개 페이지 단계 영상(검증·모의투자)의 공통 도구. render.mjs가 시간 t를 넣어 한 프레임씩 찍는다.
const $ = (id) => document.getElementById(id);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const prog = (t, a, b) => clamp((t - a) / (b - a));
const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const easeOut = (x) => 1 - Math.pow(1 - x, 3);
const NS = "http://www.w3.org/2000/svg";

function seeded(seed) {
  let s = seed;
  return () => ((s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296);
}

function show(el, o, transform = "") {
  el.style.opacity = o;
  el.style.transform = transform;
  el.style.visibility = o <= 0.001 ? "hidden" : "visible";
}

function svgEl(name, attrs = {}, parent) {
  const el = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}

// 마우스 포인터·클릭 물결·루프 이음새를 무대에 얹는다.
function mountOverlay() {
  const stage = $("stage");
  stage.insertAdjacentHTML(
    "beforeend",
    `<div class="abs hide" id="ripple"></div>
     <svg class="abs hide" id="ptr" viewBox="0 0 26 26"><path d="M4 2 L4 20 L9 15.5 L12.5 23 L15.8 21.5 L12.3 14.2 L19 14 Z" fill="#fff" stroke="#141413" stroke-width="1.6" stroke-linejoin="round"/></svg>
     <div class="abs" id="fade"></div>`,
  );
}

// 요소 id의 중심 좌표(무대 기준) — 숨겨진 요소도 자리는 있으므로 목표로 쓸 수 있다.
function centerOf(target) {
  if (Array.isArray(target)) return target;
  const r = $(target).getBoundingClientRect();
  return [r.left + r.width / 2 - 8, r.top + r.height / 2 - 6];
}

// keys: [[t, 목표(요소 id 또는 [x, y])], ...] 시각 순. hide: 포인터를 감추는 [시작, 끝] 구간들.
function drivePointer(t, keys, clicks, hide = []) {
  const ptr = $("ptr");
  const rp = $("ripple");
  let pos = null;
  if (t >= keys[0][0] && t <= keys[keys.length - 1][0] && !hide.some(([a, b]) => t > a && t < b)) {
    for (let i = 0; i < keys.length - 1; i++) {
      const [t0, a] = keys[i];
      const [t1, b] = keys[i + 1];
      if (t >= t0 && t <= t1) {
        const k = ease(prog(t, t0, t1));
        const [x0, y0] = centerOf(a);
        const [x1, y1] = centerOf(b);
        pos = [x0 + (x1 - x0) * k, y0 + (y1 - y0) * k];
        break;
      }
    }
  }
  if (pos) {
    show(ptr, 1);
    ptr.style.left = pos[0] + "px";
    ptr.style.top = pos[1] + "px";
  } else show(ptr, 0);
  let rippling = false;
  for (const c of clicks) {
    const d = t - c;
    if (d >= 0 && d < 0.5 && pos) {
      const k = d / 0.5;
      show(rp, 1 - k);
      rp.style.left = pos[0] - 18 + "px";
      rp.style.top = pos[1] - 14 + "px";
      rp.style.transform = `scale(${0.4 + k})`;
      rippling = true;
    }
  }
  if (!rippling) show(rp, 0);
}

function loopFade(t, duration) {
  $("fade").style.opacity = Math.max(1 - prog(t, 0, 0.6), prog(t, duration - 0.6, duration));
}

// 눌림 연출 — 시각 c 주변 0.12초 동안 살짝 작아진다.
const pressScale = (t, c) => 1 - 0.05 * Math.max(0, 1 - Math.abs(t - c) * 8);
