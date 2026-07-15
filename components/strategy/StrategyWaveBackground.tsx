"use client";

import { useEffect, useRef } from "react";

type WavePoint = {
  x: number;
  y: number;
  column: number;
  row: number;
  phase: number;
  tint: number;
};

const smoothStep = (value: number) => {
  const clamped = Math.max(0, Math.min(1, value));
  return clamped * clamped * (3 - 2 * clamped);
};

export function StrategyWaveBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frameId = 0;
    let width = 0;
    let height = 0;
    let points: WavePoint[] = [];
    let resizeObserver: ResizeObserver | null = null;

    const buildPointField = () => {
      const gapX = 28;
      const gapY = 28;
      const nextPoints: WavePoint[] = [];
      let row = 0;

      for (let y = -gapY; y <= height + gapY; y += gapY) {
        let column = 0;
        for (let x = -gapX; x <= width + gapX; x += gapX) {
          nextPoints.push({
            x,
            y,
            column,
            row,
            phase: column * 0.37 + row * 0.21,
            tint: (column + row) % 7,
          });
          column += 1;
        }
        row += 1;
      }

      points = nextPoints;
    };

    const render = (time: number) => {
      context.clearRect(0, 0, width, height);
      context.lineCap = "round";

      if (width <= 0 || height <= 0) return;

      const glow = context.createRadialGradient(
        width * 0.5,
        height * 0.34,
        0,
        width * 0.5,
        height * 0.34,
        Math.max(width, height) * 0.75,
      );
      glow.addColorStop(0, "rgba(50, 121, 249, 0.08)");
      glow.addColorStop(0.34, "rgba(183, 191, 217, 0.035)");
      glow.addColorStop(1, "rgba(18, 19, 23, 0)");
      context.fillStyle = glow;
      context.fillRect(0, 0, width, height);

      const focusX = width * 0.5;
      const focusY = height * 0.36;
      const maxDistance = Math.hypot(width * 0.58, height * 0.6);

      for (const point of points) {
        const waveA = Math.sin(point.column * 0.34 + time * 0.00115 + point.phase);
        const waveB = Math.sin((point.column + point.row) * 0.18 - time * 0.0009 + point.phase);
        const waveC = Math.sin(point.row * 0.28 + time * 0.00125 + point.phase * 0.5);
        const crest = smoothStep((waveA * 0.52 + waveB * 0.34 + waveC * 0.18 + 1) / 2);
        const drawX = point.x + waveB * 2;
        const drawY = point.y + waveA * 7 + waveC * 2.6;

        const fieldDistance = Math.hypot(drawX - focusX, drawY - focusY);
        const fieldFalloff = smoothStep(1 - fieldDistance / maxDistance);
        const topFade = smoothStep(drawY / 120);
        const bottomFade = smoothStep((height - drawY) / 160);
        const edgeFade = topFade * bottomFade;
        const alpha = Math.min(
          0.56,
          (0.035 + fieldFalloff * 0.16 + crest * 0.12) * edgeFade,
        );

        if (alpha <= 0.01) continue;

        const barHeight = 1.8 + crest * 4;
        const isBlue = point.tint === 0;

        // 웨이브 정점(crest)일수록 색을 흰색 쪽으로 밀어 은은하게 빛나 보이게 함
        const shine = smoothStep((crest - 0.55) / 0.45);
        const red = Math.round((isBlue ? 112 : 183) + (255 - (isBlue ? 112 : 183)) * shine);
        const green = Math.round((isBlue ? 159 : 191) + (255 - (isBlue ? 159 : 191)) * shine);
        const blue = Math.round((isBlue ? 255 : 217) + (255 - (isBlue ? 255 : 217)) * shine);
        const litAlpha = Math.min(0.68, alpha + shine * 0.14);

        context.strokeStyle = `rgba(${red}, ${green}, ${blue}, ${litAlpha})`;
        context.lineWidth = 1.55;
        context.beginPath();
        context.moveTo(drawX, drawY - barHeight / 2);
        context.lineTo(drawX, drawY + barHeight / 2);
        context.stroke();
      }
    };

    const draw = (time: number) => {
      render(time);
      frameId = requestAnimationFrame(draw);
    };

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.offsetWidth;
      height = canvas.offsetHeight;
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      buildPointField();
      render(0);
    };

    resize();

    if (!reducedMotion) {
      frameId = requestAnimationFrame(draw);
    }

    window.addEventListener("resize", resize);

    if ("ResizeObserver" in window) {
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(canvas);
      if (canvas.parentElement) {
        resizeObserver.observe(canvas.parentElement);
      }
    }

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full opacity-80"
    />
  );
}
