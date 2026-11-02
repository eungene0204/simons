// 몬테카를로 경로 분포(팬 차트) 수집기 — 시나리오마다 자산 배수(시작=1)를 정해진 체크포인트에서만 적어 두고,
// 끝나면 체크포인트별 백분위(5·25·50·75·95)를 낸다. 난수를 소비하지 않으므로 시뮬레이션 결과(분포·지표)는
// 수집기 유무와 무관하게 같다.

export interface MonteCarloFan {
  /** 경로의 한 걸음 단위 — returns 모드는 거래일, trades 모드는 완결 거래 1건. */
  stepUnit: "day" | "trade";
  /** 체크포인트의 걸음 위치(0=시작). */
  steps: number[];
  p05: number[];
  p25: number[];
  p50: number[];
  p75: number[];
  p95: number[];
  /** 재표본하지 않은 원래 순서의 경로. */
  observed: number[];
  /** 배경에 옅게 그릴 개별 시나리오 몇 개. */
  samples: number[][];
  /** returns 모드에서 첫·마지막 걸음의 날짜(축 라벨용). */
  startDate?: string;
  endDate?: string;
}

const FAN_CHECKPOINTS = 100;
const FAN_SAMPLE_PATHS = 24;

/** 0..totalSteps 사이를 고르게 나눈 체크포인트(중복 없음, 0과 끝 포함). */
export function fanCheckpoints(totalSteps: number, count = FAN_CHECKPOINTS): number[] {
  if (totalSteps <= count) return Array.from({ length: totalSteps + 1 }, (_, i) => i);
  const out: number[] = [];
  for (let i = 0; i <= count; i += 1) {
    const step = Math.round((i * totalSteps) / count);
    if (out[out.length - 1] !== step) out.push(step);
  }
  return out;
}

function quantile(sorted: Float64Array, q: number): number {
  const index = (sorted.length - 1) * q;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  const weight = index - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

export function createFanRecorder(totalSteps: number, iterations: number) {
  const steps = fanCheckpoints(totalSteps);
  const width = steps.length;
  const values = new Float64Array(iterations * width);
  let row = -1;
  let column = 0;

  return {
    /** 새 시나리오 시작 — 시작점(배수 1)을 적는다. */
    begin() {
      row += 1;
      values[row * width] = 1;
      column = 1;
    },
    /** stepIndex(1부터)번째 걸음을 마친 뒤의 자산 배수. */
    record(stepIndex: number, multiple: number) {
      if (column < width && steps[column] === stepIndex) {
        values[row * width + column] = multiple;
        column += 1;
      }
    },
    finish(observed: number[], stepUnit: MonteCarloFan["stepUnit"], dates?: { startDate?: string; endDate?: string }): MonteCarloFan {
      const rows = row + 1;
      const bands = { p05: [] as number[], p25: [] as number[], p50: [] as number[], p75: [] as number[], p95: [] as number[] };
      const columnValues = new Float64Array(rows);
      for (let c = 0; c < width; c += 1) {
        for (let r = 0; r < rows; r += 1) columnValues[r] = values[r * width + c];
        columnValues.sort();
        bands.p05.push(quantile(columnValues, 0.05));
        bands.p25.push(quantile(columnValues, 0.25));
        bands.p50.push(quantile(columnValues, 0.5));
        bands.p75.push(quantile(columnValues, 0.75));
        bands.p95.push(quantile(columnValues, 0.95));
      }
      const sampleCount = Math.min(FAN_SAMPLE_PATHS, rows);
      const stride = rows / Math.max(1, sampleCount);
      const samples = Array.from({ length: sampleCount }, (_, i) => {
        const r = Math.floor(i * stride);
        return Array.from(values.subarray(r * width, (r + 1) * width));
      });
      return {
        stepUnit,
        steps,
        ...bands,
        observed: steps.map((step) => observed[step] ?? observed[observed.length - 1]),
        samples,
        ...(dates ?? {}),
      };
    },
  };
}

/** 성장배수 스텝을 순서대로 곱한 원래 경로(시작=1, 길이 = 스텝 수 + 1). */
export function cumulativePath(steps: number[], toGrowth: (step: number) => number): number[] {
  const path = [1];
  let multiple = 1;
  for (const step of steps) {
    multiple *= toGrowth(step);
    path.push(multiple);
  }
  return path;
}
