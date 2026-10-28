import { createHash } from "crypto";
import { EXAMPLES } from "@/components/strategy/strategyExamples";
import generated from "@/lib/strategy/exampleSimulations.json";

// 전략 시뮬레이션 대상 = 예시 전략(2026-10-28). 실행 설정은 scripts/build_example_simulations.py가 예시 문장을 해석하고
// 사람이 검토한 되묻기 답변(scripts/example_simulation_answers.json)을 적용해 만든 고정 파일에서 읽는다 — 요청 중 LLM 호출 없음.

/** 예시 문장이 정하지 않아 되묻기로 채운 값. random=true는 칩 중 무작위로 고른 값이다(화면에 그대로 표시). */
export type ExampleAssumption = { question: string; answer: string; random: boolean };

export type ExampleSimulationEntry = {
  key: string;
  title: string;
  promptSha256: string;
  snapshot: Record<string, unknown>;
  assumptions?: ExampleAssumption[];
};

export type ExampleStrategy = {
  key: string;
  title: string;
  prompt: string;
  settings: string;
  assumptions: ExampleAssumption[];
};

const sha256Hex = (text: string) => createHash("sha256").update(text, "utf8").digest("hex");

/**
 * 고정 파일의 항목 중 현재 예시 문장과 같은 것만 쓴다. 예시 문구가 바뀌었으면 그 실행 설정은 옛 문장의 해석이라
 * 스크립트로 다시 만들 때까지 목록에서 뺀다.
 */
export function buildExampleRegistry(
  entries: ExampleSimulationEntry[],
  examples: { title: string; prompt: string }[] = EXAMPLES,
): Map<string, ExampleStrategy> {
  const byTitle = new Map(examples.map((e) => [e.title, e]));
  const registry = new Map<string, ExampleStrategy>();
  for (const entry of entries) {
    const example = byTitle.get(entry.title);
    if (!example || sha256Hex(example.prompt) !== entry.promptSha256) continue;
    registry.set(entry.key, {
      key: entry.key,
      title: example.title,
      prompt: example.prompt,
      settings: JSON.stringify(entry.snapshot),
      assumptions: entry.assumptions ?? [],
    });
  }
  return registry;
}

let registry: Map<string, ExampleStrategy> | null = null;

export function exampleRegistry(): Map<string, ExampleStrategy> {
  registry ??= buildExampleRegistry((generated as { entries: ExampleSimulationEntry[] }).entries);
  return registry;
}
