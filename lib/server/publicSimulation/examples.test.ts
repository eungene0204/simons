import { createHash } from "crypto";
import { describe, expect, it } from "vitest";

import { EXAMPLES } from "@/components/strategy/strategyExamples";
import { ENGINE_REQUEST_KEYS } from "@/lib/strategy/executableRequest";
import generated from "@/lib/strategy/exampleSimulations.json";
import { buildExampleRegistry, type ExampleSimulationEntry } from "./examples";

const sha = (text: string) => createHash("sha256").update(text, "utf8").digest("hex");
const entries = (generated as { entries: ExampleSimulationEntry[] }).entries;
const snapshot = { entry: { conditions: [] }, exit: { conditions: [] }, risk: { init_cash: 1 } };

describe("예시 전략 등록부", () => {
  it("현재 예시 문장과 같은 항목만 싣고, 문구가 바뀐 예시·없는 예시는 뺀다", () => {
    const examples = [
      { title: "A", prompt: "문장 A" },
      { title: "B", prompt: "문장 B(수정됨)" },
    ];
    const registry = buildExampleRegistry(
      [
        { key: "keyA", title: "A", promptSha256: sha("문장 A"), snapshot },
        { key: "keyB", title: "B", promptSha256: sha("문장 B"), snapshot },
        { key: "keyC", title: "C", promptSha256: sha("문장 C"), snapshot },
      ],
      examples,
    );
    expect([...registry.keys()]).toEqual(["keyA"]);
    expect(registry.get("keyA")).toEqual({ key: "keyA", title: "A", prompt: "문장 A", settings: JSON.stringify(snapshot), assumptions: [] });
  });

  it("되묻기로 정한 값(무작위 여부 포함)을 등록부에 그대로 싣는다", () => {
    const assumptions = [{ question: "익절 기준은?", answer: "익절 20%", random: true }];
    const registry = buildExampleRegistry([{ key: "keyA", title: "A", promptSha256: sha("문장 A"), snapshot, assumptions }], [{ title: "A", prompt: "문장 A" }]);
    expect(registry.get("keyA")?.assumptions).toEqual(assumptions);
  });

  it("고정 파일은 현재 예시와 맞고, 키는 제목 해시이며 스냅샷은 엔진 요청형 키만 가진다", () => {
    const byTitle = new Map(EXAMPLES.map((e) => [e.title, e]));
    for (const entry of entries) {
      const example = byTitle.get(entry.title);
      expect(example, entry.title).toBeTruthy();
      expect(entry.promptSha256, `${entry.title}: 예시 문구가 바뀌었으면 scripts/build_example_simulations.py를 다시 돌린다`).toBe(sha(example!.prompt));
      expect(entry.key).toBe(sha(entry.title).slice(0, 16));
      expect(Object.keys(entry.snapshot).every((k) => (ENGINE_REQUEST_KEYS as readonly string[]).includes(k)), entry.title).toBe(true);
      for (const role of ["entry", "exit", "risk"]) expect(entry.snapshot[role], `${entry.title}.${role}`).toBeTruthy();
    }
    expect(new Set(entries.map((e) => e.key)).size).toBe(entries.length);
  });
});
