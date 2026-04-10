#!/usr/bin/env ts-node

/**
 * compile-spec.ts
 *
 * Convert a rough Simons development request into a structured executable task spec.
 *
 * Usage:
 *   ts-node .codex/skills/spec-writer/scripts/compile-spec.ts "Fix RSI threshold bug"
 *
 * Optional:
 *   ts-node .codex/skills/spec-writer/scripts/compile-spec.ts "Improve strategy builder spacing" --json
 */

type BoundaryId =
  | "strategy-ui"
  | "backtest-transform"
  | "backtest-core"
  | "ai-xai-layer"
  | "dashboard-readonly-ui";

type BoundaryDefinition = {
  id: BoundaryId;
  name: string;
  purpose: string;
  files: string[];
  runCommands: string[];
  doNot: string[];
  keywordHints: string[];
  riskLevel: "low" | "medium" | "high";
};

type CompiledSpec = {
  task: string;
  boundary: string;
  filesAllowed: string[];
  doNot: string[];
  requirements: string[];
  run: string[];
  deliver: string[];
  notes?: string[];
};

const BOUNDARIES: BoundaryDefinition[] = [
  {
    id: "strategy-ui",
    name: "Strategy UI",
    purpose: "User-facing strategy builder and analytics interface.",
    files: [
      "app/analytics/**",
      "components/strategy/**",
      "lib/strategy-blocks.ts",
      "types/strategy.ts",
    ],
    runCommands: [
      "npm run test:frontend",
      "npm run lint",
      "npm run typecheck",
    ],
    doNot: [
      "Do not change backend logic.",
      "Do not modify API routes.",
      "Do not change database schema.",
    ],
    keywordHints: [
      "ui",
      "ux",
      "spacing",
      "layout",
      "button",
      "form",
      "input",
      "dropdown",
      "modal",
      "wizard",
      "strategy builder",
      "analytics page",
      "design",
      "style",
      "component",
      "props",
      "validation message",
    ],
    riskLevel: "low",
  },
  {
    id: "backtest-transform",
    name: "Backtest Transform",
    purpose: "Convert parsed strategy data into executable backtest request structures.",
    files: [
      "backend/engine/nl_parser.py",
      "backend/engine/strategy_converter.py",
      "types/strategy.ts",
      "lib/strategy/**",
    ],
    runCommands: [
      "cd backend && pytest tests/test_*.py -k strategy_converter",
      "npm run typecheck",
    ],
    doNot: [
      "Do not change simulator behavior.",
      "Do not modify provider logic.",
      "Do not change database schema.",
    ],
    keywordHints: [
      "parser",
      "parse",
      "convert",
      "converter",
      "mapping",
      "normalize",
      "normalization",
      "serialize",
      "serialization",
      "null",
      "optional",
      "schema",
      "request",
      "payload",
      "dsl",
    ],
    riskLevel: "medium",
  },
  {
    id: "backtest-core",
    name: "Backtest Core",
    purpose: "Core simulation, indicators, signals, and result handling.",
    files: [
      "backend/engine/loader.py",
      "backend/engine/indicators.py",
      "backend/engine/signals.py",
      "backend/engine/simulator.py",
      "backend/engine/result_handler.py",
      "backend/tests/**",
    ],
    runCommands: [
      "cd backend && pytest tests/test_engine_signals.py",
      "cd backend && pytest tests/test_engine_simulator.py",
    ],
    doNot: [
      "Do not redesign architecture.",
      "Do not modify more than one core module unless absolutely necessary.",
      "Do not change unrelated indicator behavior.",
    ],
    keywordHints: [
      "rsi",
      "macd",
      "signal",
      "indicator",
      "simulator",
      "simulation",
      "entry",
      "exit",
      "threshold",
      "edge case",
      "backtest bug",
      "trade",
      "position",
      "ranking",
      "metric",
      "drawdown",
    ],
    riskLevel: "high",
  },
  {
    id: "ai-xai-layer",
    name: "AI / XAI Layer",
    purpose: "AI prediction, summarization, and explainability behavior.",
    files: [
      "backend/ai/**",
      "app/api/backtest/summarize/**",
      "app/api/backtest/explain/**",
    ],
    runCommands: [
      "cd backend && pytest tests/test_summarize.py",
      "npm run typecheck",
    ],
    doNot: [
      "Do not redesign model architecture.",
      "Do not change provider logic.",
      "Do not change database schema.",
    ],
    keywordHints: [
      "ai",
      "xai",
      "shap",
      "summary",
      "summarize",
      "report",
      "explain",
      "explanation",
      "prediction",
      "prompt",
      "reason",
      "narrative",
    ],
    riskLevel: "medium",
  },
  {
    id: "dashboard-readonly-ui",
    name: "Dashboard / Read-only UI",
    purpose: "Visualization and read-only reporting UI.",
    files: [
      "components/dashboard/**",
      "components/portfolio/**",
      "app/backtest/**",
      "app/kospi/**",
    ],
    runCommands: [
      "npm run test:frontend",
      "npm run lint",
      "npm run typecheck",
    ],
    doNot: [
      "Do not change trading logic.",
      "Do not modify order execution behavior.",
      "Do not add backend side effects.",
    ],
    keywordHints: [
      "dashboard",
      "chart",
      "graph",
      "table",
      "portfolio",
      "empty state",
      "loading state",
      "read only",
      "visualization",
      "performance",
      "recharts",
      "backtest page",
      "kospi page",
    ],
    riskLevel: "low",
  },
];

const GLOBAL_FORBIDDEN_PATHS = [
  "prisma/**",
  "backend/engine/providers/**",
  "app/api/login/**",
  "app/api/register/**",
  "app/api/user/**",
  "scripts/**",
];

function normalizeWhitespace(input: string): string {
  return input.replace(/\s+/g, " ").trim();
}

function scoreBoundary(request: string, boundary: BoundaryDefinition): number {
  const text = request.toLowerCase();
  let score = 0;

  for (const keyword of boundary.keywordHints) {
    if (text.includes(keyword.toLowerCase())) {
      score += keyword.split(" ").length > 1 ? 3 : 2;
    }
  }

  if (boundary.id === "backtest-core" && /(fix|bug|edge case|threshold|incorrect|wrong)/i.test(text)) {
    score += 2;
  }

  if (boundary.id === "strategy-ui" && /(spacing|layout|ui|component|visual|padding)/i.test(text)) {
    score += 2;
  }

  if (boundary.id === "dashboard-readonly-ui" && /(dashboard|chart|table|render|empty state)/i.test(text)) {
    score += 2;
  }

  if (boundary.id === "backtest-transform" && /(serialize|payload|mapping|null|optional|parse|convert)/i.test(text)) {
    score += 2;
  }

  if (boundary.id === "ai-xai-layer" && /(summary|explain|shap|report|ai)/i.test(text)) {
    score += 2;
  }

  return score;
}

function pickBoundary(request: string): BoundaryDefinition {
  const ranked = BOUNDARIES
    .map((boundary) => ({ boundary, score: scoreBoundary(request, boundary) }))
    .sort((a, b) => b.score - a.score);

  if (ranked[0].score <= 0) {
    return BOUNDARIES.find((boundary) => boundary.id === "strategy-ui")!;
  }

  return ranked[0].boundary;
}

function inferRequirements(request: string, boundary: BoundaryDefinition): string[] {
  const text = request.toLowerCase();
  const requirements: string[] = [];

  requirements.push("Keep the change as small and reviewable as possible.");
  requirements.push("Preserve existing public API contracts unless explicitly requested otherwise.");

  if (/(bug|fix|incorrect|wrong|broken)/i.test(text)) {
    requirements.push("Fix the reported behavior without expanding scope.");
  }

  if (/(test|coverage|regression)/i.test(text)) {
    requirements.push("Add or update focused tests for the changed behavior.");
  } else {
    requirements.push("Add or update tests if behavior changes.");
  }

  if (boundary.id === "backtest-core") {
    requirements.push("Limit the work to one narrow bug or one small behavior change.");
  }

  if (boundary.id === "strategy-ui") {
    requirements.push("Do not change business logic while improving UI behavior.");
  }

  if (boundary.id === "dashboard-readonly-ui") {
    requirements.push("Keep the view read-only and avoid adding side effects.");
  }

  if (boundary.id === "backtest-transform") {
    requirements.push("Keep request/response shapes stable unless the request explicitly says otherwise.");
  }

  if (boundary.id === "ai-xai-layer") {
    requirements.push("Improve output quality without changing model architecture.");
  }

  return dedupe(requirements);
}

function inferTaskSentence(request: string, boundary: BoundaryDefinition): string {
  const cleaned = normalizeWhitespace(request);
  if (!cleaned) {
    return `Create a small safe change inside ${boundary.name}.`;
  }

  const capitalized = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  return capitalized.endsWith(".") ? capitalized : `${capitalized}.`;
}

function dedupe(values: string[]): string[] {
  return Array.from(new Set(values));
}

function buildSpec(request: string): CompiledSpec {
  const boundary = pickBoundary(request);
  const task = inferTaskSentence(request, boundary);

  const notes: string[] = [];

  if (boundary.riskLevel === "high") {
    notes.push("This boundary is high-risk. Keep the scope extremely narrow.");
  }

  notes.push("Review the generated Files allowed list before implementation.");
  notes.push(`Never include forbidden paths: ${GLOBAL_FORBIDDEN_PATHS.join(", ")}`);

  return {
    task,
    boundary: boundary.name,
    filesAllowed: boundary.files,
    doNot: dedupe([...boundary.doNot, "Do not modify forbidden paths."]),
    requirements: inferRequirements(request, boundary),
    run: boundary.runCommands,
    deliver: [
      "Small diff",
      "Summary of changed files",
      "Test results summary",
    ],
    notes,
  };
}

function formatSpec(spec: CompiledSpec): string {
  const sections = [
    `Task:\n${spec.task}`,
    `Boundary:\n${spec.boundary}`,
    `Files allowed:\n${spec.filesAllowed.map((value) => `- ${value}`).join("\n")}`,
    `Do not:\n${spec.doNot.map((value) => `- ${value}`).join("\n")}`,
    `Requirements:\n${spec.requirements.map((value) => `- ${value}`).join("\n")}`,
    `Run:\n${spec.run.map((value) => `- ${value}`).join("\n")}`,
    `Deliver:\n${spec.deliver.map((value) => `- ${value}`).join("\n")}`,
  ];

  if (spec.notes && spec.notes.length > 0) {
    sections.push(`Notes:\n${spec.notes.map((value) => `- ${value}`).join("\n")}`);
  }

  return sections.join("\n\n");
}

function main(): void {
  const args = process.argv.slice(2);
  const jsonMode = args.includes("--json");
  const rawArgs = args.filter((arg) => arg !== "--json");
  const request = normalizeWhitespace(rawArgs.join(" "));

  if (!request) {
    process.stderr.write(
      [
        "Usage:",
        '  ts-node .codex/skills/spec-writer/scripts/compile-spec.ts "Fix RSI threshold bug"',
        '  ts-node .codex/skills/spec-writer/scripts/compile-spec.ts "Improve strategy builder spacing" --json',
      ].join("\n") + "\n"
    );
    process.exit(1);
  }

  const spec = buildSpec(request);

  if (jsonMode) {
    process.stdout.write(JSON.stringify(spec, null, 2) + "\n");
    return;
  }

  process.stdout.write(formatSpec(spec) + "\n");
}

main();
