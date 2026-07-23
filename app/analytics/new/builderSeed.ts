type FundamentalFilter = {
  metric: string;
  operator: string;
  value: number;
};

type ParsedValueSeed = {
  fundamental_filters?: FundamentalFilter[] | null;
};

export function applyParsedValueStrategySeed(
  state: Record<string, unknown>,
  parsed: ParsedValueSeed | null | undefined,
): Record<string, unknown> {
  if (state.strategy_type && state.strategy_type !== "value") return state;

  const filters = parsed?.fundamental_filters ?? [];
  const pbr = filters.find(
    (filter) =>
      filter.metric.toLowerCase() === "pbr" &&
      (filter.operator === "<=" || filter.operator === "<") &&
      Number.isFinite(filter.value),
  );
  const roe = filters.find(
    (filter) =>
      ["roe", "roe_or_gpa"].includes(filter.metric.toLowerCase()) &&
      (filter.operator === ">=" || filter.operator === ">") &&
      Number.isFinite(filter.value),
  );

  if (!pbr || !roe) return state;

  return {
    ...state,
    strategy_type: "value",
    value_pbr: state.value_pbr ?? pbr.value,
    value_roe: state.value_roe ?? roe.value,
  };
}
