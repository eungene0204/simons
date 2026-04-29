import { createHash } from "crypto";

const NON_HASH_KEYS = new Set(["id", "name", "description", "created_at", "updated_at", "strategy_id", "metadata"]);

export function canonicalizeStrategyDsl(value: any): string {
  const normalize = (input: any): any => {
    if (Array.isArray(input)) return input.map(normalize);
    if (!input || typeof input !== "object") return input;
    return Object.keys(input)
      .filter((key) => !NON_HASH_KEYS.has(key))
      .sort()
      .reduce((acc: Record<string, any>, key) => {
        const normalized = normalize(input[key]);
        if (normalized !== undefined) acc[key] = normalized;
        return acc;
      }, {});
  };

  return JSON.stringify(normalize(value));
}

export function createStrategyId(strategyDsl: any) {
  return createHash("sha256").update(canonicalizeStrategyDsl(strategyDsl)).digest("hex");
}
