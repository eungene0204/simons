# Advisor Decision Policy

> Status: current implementation policy
> Owner boundary: AI / XAI Layer
> Purpose: define the decision criteria used by the strategy advisor so future changes do not drift into vague or repetitive advice.

---

## 1. Scope

This document describes how the current strategy advisor should decide what to say.

The advisor is not a trading recommendation engine. It is a strategy validation assistant. Its job is to identify missing structure, risk controls, weak evidence, overfitting risk, and comparison experiments that the user can verify with backtests.

Primary implementation files:

- `backend/advisor/agent.py`
- `backend/advisor/diagnoser.py`
- `backend/advisor/rules.py`
- `backend/advisor/scoring.py`
- `backend/advisor/suggestion_engine.py`
- `backend/advisor/experiment_learning.py`
- `backend/advisor/advice_evaluator.py`

Related design document:

- `docs/architecture/rag-experience-memory-agent.md`

---

## 2. Inputs

The advisor may use these inputs:

- User prompt.
- Parsed strategy DSL.
- Backtest result, if available.
- Candidate backtest result, if available.
- News context, if available.
- Experiment-learning artifacts under `data/advisor-learning`.
- Strategy memory / Experience Memory, if provided in the request.

The advisor must treat unavailable inputs as unavailable. It must not imply that missing backtest, news, or memory evidence exists.

---

## 3. Output Priority

Advice priority is:

1. Missing required strategy components: universe, entry signal, exit signal, portfolio setting, or risk setting.
2. High news risk, when present.
3. Missing structural safety: no exit rule, no entry rule.
4. Risk controls: no stop loss, too tight stop, over-concentrated positions.
5. Backtest evidence: low trade count, high MDD, low Sharpe, overfit pattern.
6. Experiment-learning evidence from similar samples.
7. Experience Memory from similar historical cases.
8. Optional comparison experiments.
9. AI signal recommendation.

The UI may show only the first advice item. Therefore the first advice item must be the most useful action for the user, not a generic title or disclaimer.

---

## 4. Rule Criteria

### Required Components

Before giving performance, experiment-learning, or Experience Memory advice, the advisor must verify that the strategy has all required components:

- Universe: target market or symbol universe, such as KOSPI, KOSDAQ, or KOSPI200.
- Entry signal: at least one actionable buy condition, such as 52-week breakout, volume spike, RSI, moving-average crossover, or a fundamental filter.
- Exit signal: at least one actionable sell condition, such as technical exit, stop loss, take profit, trailing stop, or maximum holding period.
- Portfolio setting: max positions or equivalent allocation constraint.
- Risk setting: stop loss, take profit, trailing stop, max holding period, or another explicit risk control.

If any required component is missing or failed to parse, the first advice must identify that missing component and ask the user to complete or correct it. The advisor must not lead with backtest performance, RAG, experiment-learning, or generic improvement candidates until the missing component is resolved.

Example: if the prompt says "KOSDAQ에서 52주 신고가와 거래량 급증이면 진입" but the parsed strategy has no entry signal, the advisor must first say that the entry signal was not created and ask to confirm the intended entry rule. It should not first suggest stop loss, take profit, or experiment comparisons.

### Structure

- `MISSING_EXIT_RULE`: no technical exit, no stop loss, no take profit, no trailing stop, and no holding period.
- `NO_ENTRY_SIGNALS`: no entry signal and no fundamental filter.
- `TOO_MANY_FILTERS`: more than 5 fundamental filters.
- `NO_LIQUIDITY_FILTER`: broad universe without trading-value filter when position size makes liquidity meaningful.

### Risk

- `NO_STOP_LOSS`: no stop loss and no trailing stop.
- `NO_TAKE_PROFIT`: stop loss exists, but no take profit, no trailing stop, and no technical exit.
- `TOO_TIGHT_STOP`: stop loss below 3%.
- `POSITION_OVEREXPOSED`: max positions is 3 or fewer.

### Backtest

Only apply these rules when backtest results are available.

- `LOW_TRADE_COUNT`: fewer than 30 trades.
- `HIGH_MDD`: MDD worse than -30%.
- `OVERFIT_SUSPECT`: CAGR above 40% with fewer than 50 trades or at least 4 filters.
- `LOW_SHARPE`: Sharpe below 0.5.

### News

Only apply these rules when news context is available.

- `NEGATIVE_NEWS_CLUSTER`: negative news ratio at least 60%.
- `HIGH_NEWS_RISK_ALERT`: max news risk level is medium or high.
- `EVENT_DRIVEN_VOLATILITY`: at least 2 high-impact event types.
- `VALUE_TRAP_RISK`: low valuation filters plus concentrated negative news.

---

## 5. Scoring Criteria

`strategy_score` starts at 100 and subtracts issue penalties.

Current major penalties:

- Missing exit rule: 25.
- No entry signals: 25.
- No stop loss: 20.
- Overfit suspect: 18.
- Low trade count: 15.
- High MDD: 12.
- Too many filters: 10.
- No liquidity filter: 8.

`risk_score` accumulates risk contributions from active issues and news pressure.

Current major risk contributions:

- No stop loss: 25.
- Missing exit rule: 20.
- High MDD: 18.
- High news risk: 15.
- Negative news cluster: 12.
- Over-concentrated positions: 10.
- Overfit suspect: 10.

`overfit_risk` is:

- `high` when `OVERFIT_SUSPECT` exists, or when CAGR is above 35% with fewer than 50 trades.
- `medium` when there are at least 4 filters or low trade count.
- `low` otherwise.

Do not show low overfit risk as a positive claim unless backtest evidence exists.

---

## 6. Experiment Learning Criteria

Experiment-learning advice uses:

- Parsed strategy blocks.
- Extracted parameters.
- Jaccard similarity against known block combinations.
- Parameter similarity against sample parameters.
- Similar sample count.
- Median CAGR, Sharpe, MDD, Profit Factor, and trade count.
- Paired deltas when a sample compares baseline vs one changed parameter.

Confidence rules:

- Flat evidence where CAGR, Sharpe, and MDD are all near zero is low confidence.
- Similarity below 0.5 is low confidence.
- Similarity below 0.75 cannot remain high confidence.
- At least 20 similar strategies can support high confidence if evidence is not flat.
- At least 10 similar strategies can support medium confidence.
- Fewer than 10 similar strategies is low confidence.

Experiment-learning advice must:

- Avoid exposing internal confidence labels directly to the user.
- Prefer one-variable comparison candidates.
- Prefer paired-delta candidates over broad generic candidates.
- Avoid repeating the current strategy as the only recommendation.
- Use MDD and Sharpe together as the main accept/reject criteria for comparison candidates.

Experiment-learning advice must not:

- Claim stable performance from low confidence or flat evidence.
- Recommend multiple simultaneous changes as if causality is known.
- Treat similar samples as exact matches when parameter similarity is low.

---

## 7. Experience Memory Criteria

Experience Memory may be used when similar historical cases are provided.

If successful similar cases exist:

- Mention the improved metric family.
- Ask the user to compare the candidate under the same period and cost settings.

If failed similar cases exist:

- Warn that similar adjustments had limited improvement.
- Ask the user to split candidate changes and keep only changes that improve both MDD and Sharpe.

If success is unknown:

- Say that improvement success is not verified.
- Ask for separated comparison experiments.

Experience Memory must not be treated as proof. It is reusable context for deciding what to test next.

---

## 8. Candidate Evaluation

When both baseline and candidate backtest results are available, advice success is positive only when:

- CAGR or MDD improves.
- Sharpe, Calmar, or Sortino also improves.
- Trade count does not increase excessively.
- OOS result is not bad, if OOS is available.
- Liquidity check does not fail.
- Cost-adjusted profitability is not lost.
- Complexity increase is not high with weak improvement.

If some metrics improve and others worsen, net effect is neutral.

If no meaningful improvement is found, net effect is negative.

---

## 9. Wording Policy

The advisor should be direct and action-oriented.

Allowed wording:

- "제안 주신 전략과 비슷한 전략의 결과가 CAGR 중앙값 16.06%, Sharpe 중앙값 1.30, MDD 중앙값 -11.96%로 나왔습니다."
- "다음 백테스트에서는 A만 바꿔 비교하세요."
- "MDD와 Sharpe가 동시에 개선되는 후보만 남기세요."
- "거래 횟수가 적어 통계적 신뢰도가 낮습니다."
- "비슷한 실험 샘플 수가 적습니다."
- "성과 신호가 거의 없었습니다."

Avoid wording:

- "전략 실험 근거 기반 개선" as user-facing advice.
- "비교 실험 제안" as user-facing advice.
- "근거 수준은 높음/중간/낮음입니다."
- "근거 수준이 낮아 이 결과만으로 결론을 내리면 안 됩니다."
- "확신하기 어렵습니다."
- "가까운 샘플도 파라미터가 완전히 같지는 않으므로 후보별 delta만 비교하세요."
- "후보별 delta만 비교하세요."
- "과최적화 위험 낮음" when no backtest exists.
- "성과가 안정적입니다" when confidence is low.
- "추천합니다" without a validation condition.
- Repeating generic candidates like stop loss, take profit, and holding period without explaining why that candidate is relevant.

User-facing output should usually be one concise advice body. Titles are implementation metadata and should not be the main user-facing content.

---

## 10. Change Checklist

Before changing advisor behavior, verify:

- Which input source drives the advice: rule, backtest, experiment learning, memory, or news.
- Whether the first advice item is still the most useful user action.
- Whether universe, entry signal, exit signal, portfolio setting, and risk setting were all parsed before giving performance or experiment advice.
- Whether the advice depends on unavailable evidence.
- Whether confidence is disclosed when evidence is weak.
- Whether candidates are one-variable comparisons.
- Whether stop loss, take profit, trailing stop, and holding period are preserved from the parsed strategy.
- Whether tests cover the exact prompt and parsed strategy shape that triggered the change.

Recommended regression tests:

- Rule tests for each issue code.
- Experiment-learning tests for low similarity, flat evidence, paired deltas, and parameter mismatch.
- Advisor response tests that assert no user-facing metadata title is shown.
- Parser-to-advisor tests for realistic Korean prompts.

---

## 11. Premium AI Report (Strategy Validation Expert) — 2026-07-21

The Premium backtest report reuses the advisor's deterministic diagnosis but frames the whole
report as a **Strategy Validation Expert** deliverable (FR-BT-022), not a metric read-out. The
advisor still produces `strategy_score`, `risk_score`, `overfit_risk`, and grounding sections; the
report adds a deterministic **evidence pack** (`backend/ai/report_evidence.py`) and lets the LLM
write only the narrative sections.

### Division of responsibility

- **Deterministic (must be accurate):** score, advisor scores, overfit grade, strategy-profile
  tags, validation roadmap (rule-based), score-aware improvement priorities, and the evidence-pack
  fact sentences (return-time concentration, underwater duration, high-win-rate/low-expectancy,
  sample adequacy, turnover, symbol concentration).
- **LLM (narration only):** executive_summary, top_insights, strengths, weaknesses, hidden_risks,
  overfitting_analysis, strategy_profile_note, final_verdict. LLM output that echoes the prompt or
  leaks an unclosed `<think>` is discarded and the report is marked `degraded` (regenerate, never
  serve).

### Prompt principles (enforced in `build_expert_report_prompt`)

- Do not re-read numbers already on screen; explain their meaning.
- Every claim must be grounded in the provided metrics/evidence/advisor/corpus lines.
- Find risks before strengths; evaluate even good results critically.
- No investment / stock / buy-sell-timing / strategy recommendation. Focus on what to **validate** next.

### Score-aware next steps (Sections 8 and 9) — DSL edits forbidden

Improvement priorities and the validation roadmap must consider the strategy score:

- **High score / sufficient confidence:** prefer additional validation (walk-forward, Monte Carlo,
  sensitivity) over strategy changes.
- **Low score / clear structural problems:** prefer strategy-level direction — simplify the
  structure, re-examine the idea, check over-dependence on a specific market regime, or rebuild and
  re-backtest — rather than repeating validation.

In **all** cases the report must never propose concrete DSL edits: specific stop-loss/take-profit
values, adding/removing indicators, changing parameter values, or new entry/exit conditions. For the
same reason the advisor's `suggested_experiments` (which may name specific parameter values, e.g.
"stop 8–10% comparison") are **not** merged into the validation roadmap; the roadmap lists
validation *types* only.

Regression tests: `backend/tests/test_report_evidence.py`,
`backend/tests/test_summarize_endpoint.py` (validation-centric, DSL-free improvements),
`backend/tests/test_summarize.py` (expert parser/prompt).
