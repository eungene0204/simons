from typing import Dict, Any, List, Optional
from engine.optuna_optimizer import OptunaOptimizer

class LocalOptimizationAgent:
    def __init__(self, engine):
        """
        engine: an instance of BacktestEngine
        """
        self.engine = engine
        self.optimizer = OptunaOptimizer(engine)

    # Mapping for parameter names to Korean
    PARAM_MAP = {
        "shortMA": "단기 이평선", "longMA": "장기 이평선",
        "crossType": "교차 종류", "signalType": "신호 구분",
        "value": "기준값",
        "operator": "비교 연산자", "threshold": "임계값",
        "fastPeriod": "단기 지수이평", "slowPeriod": "장기 지수이평",
        "signalPeriod": "시그널 기간", "stdDev": "표준편차 배수",
        "lookbackPeriod": "기준 기간", "stopLossPct": "손절 기준",
        "takeProfitPct": "익절 기준", "percentage": "하락률",
        "investorType": "투자 주체"
    }
    VALUE_MAP = {
        "golden": "골든크로스", "dead": "데드크로스",
        "buy": "매수", "sell": "매도",
        "above": "이상", "below": "이하",
        "institutional": "기관", "foreigner": "외국인", "individual": "개인"
    }
    METRIC_KR = {
        "cagr": "연평균 수익률", "winRate": "승률", "sharpe": "샤프 지수",
        "profitFactor": "손익비", "maxDrawdown": "최대 낙폭",
        "totalReturn": "총 수익률", "totalProfit": "총 수익"
    }

    def _display_param(self, key: str) -> str:
        return self.PARAM_MAP.get(key, key.replace('_', ' ').capitalize())

    def _display_value(self, v: Any) -> str:
        if isinstance(v, str):
            return self.VALUE_MAP.get(v, v)
        return str(v)

    @staticmethod
    def _fmt_pf(v: Any) -> str:
        """손익비 표기 — None(손실 거래 0건)은 정의되지 않음(∞)이지 0(최악)이 아니다."""
        return "∞" if v is None else f"{(v or 0):.2f}"

    def write_report(self, best_params: Dict[str, Any], top_results: List[Dict[str, Any]], target_metric: str, importances: Dict[str, float], total_trials: int, holdout: Optional[Dict[str, Any]] = None, user_prompt: Optional[str] = None) -> str:
        if not top_results:
            return "최적화 결과가 없습니다. 모든 시뮬레이션이 실패했을 수 있습니다."

        m = top_results[0]["metrics"]
        metric_name = self.METRIC_KR.get(target_metric, target_metric)

        # ── 1. 요약 ──
        report = f"### 최적화 결과\n\n"
        report += f"**{metric_name}** 기준으로 총 **{total_trials}회** 시뮬레이션한 결과입니다.\n\n"

        # ── 2. 최적 설정값 (표) ──
        report += "#### 최적 설정값\n\n"
        report += "| 항목 | 값 |\n|------|----|\n"
        for k, v in best_params.items():
            key = k.split('.')[-1]
            report += f"| {self._display_param(key)} | {self._display_value(v)} |\n"

        # ── 3. 성과 요약 (표) ──
        cagr = m.get("cagr") or 0
        total_return = m.get("totalReturn") or 0
        total_profit = m.get("totalProfit") or 0
        mdd = m.get("maxDrawdown") or 0
        pf_str = self._fmt_pf(m.get("profitFactor")) if "profitFactor" in m else "0.00"
        wr = m.get("winRate") or 0
        trades = m.get("trades") or 0

        report += f"""
#### 성과 요약

| 지표 | 결과 |
|------|------|
| 연평균 수익률 | {cagr:.2f}% |
| 총 수익률 | {total_return:.2f}% |
| 총 수익 | {total_profit:,.0f}원 |
| 최대 낙폭 | {mdd:.2f}% |
| 손익비 | {pf_str} |
| 승률 | {wr:.1f}% |
| 매매 횟수 | {trades}회 |
"""

        # ── 4. 설정값 영향도 ──
        if importances:
            report += "\n#### 설정값 영향도\n\n"
            report += "| 설정값 | 영향도 |\n|--------|--------|\n"
            sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
            for k, v in sorted_imp:
                key = k.split('.')[-1]
                report += f"| {self._display_param(key)} | {v*100:.1f}% 기여도 |\n"

        # ── 5. 과적합 검증 ──
        # 단일 70/30 홀드아웃(워크포워드 아님) — optimize(holdout_validation=True)의 결과
        if holdout:
            full_m = holdout.get("full_metrics", {})
            oos_m = holdout.get("oos_metrics", {})
            oos_period = holdout.get("oos_period", "")

            full_cagr = full_m.get("cagr") or 0
            oos_cagr = oos_m.get("cagr") or 0
            oos_trades = oos_m.get("trades") or 0

            cagr_degradation = 0
            if full_cagr > 0 and oos_cagr < full_cagr:
                cagr_degradation = (1 - oos_cagr / full_cagr) * 100

            if oos_trades == 0:
                emoji, verdict = "🔴", "위험"
                msg = "검증 구간에서 매매가 한 건도 없습니다. **이 설정값은 특정 기간에서만 우연히 작동한 조합**일 가능성이 매우 높습니다."
            elif cagr_degradation > 70:
                emoji, verdict = "🔴", "위험"
                msg = f"최근 구간 수익률이 **{cagr_degradation:.0f}% 하락**했습니다. 실전 적용을 권장하지 않습니다."
            elif cagr_degradation > 40:
                emoji, verdict = "🟡", "주의"
                msg = f"최근 구간 수익률이 **{cagr_degradation:.0f}% 하락**했습니다. 추가 검증이 필요합니다."
            else:
                emoji, verdict = "🟢", "양호"
                msg = "최근 구간에서도 비슷한 성과를 보여 신뢰도가 높습니다."

            report += f"""
#### 실전 신뢰도 검증 {emoji} {verdict}

최적 설정값이 **최근 데이터(후반 30%, {oos_period})** 에서도 통하는지 검증한 결과입니다.

| 지표 | 전체 기간 | 최근 검증 구간 |
|------|:---------:|:-------------:|
| 연평균 수익률 | {full_cagr:.2f}% | {oos_cagr:.2f}% |
| 최대 낙폭 | {(full_m.get("maxDrawdown") or 0):.2f}% | {(oos_m.get("maxDrawdown") or 0):.2f}% |
| 손익비 | {self._fmt_pf(full_m.get("profitFactor")) if "profitFactor" in full_m else "0.00"} | {self._fmt_pf(oos_m.get("profitFactor")) if "profitFactor" in oos_m else "0.00"} |
| 승률 | {(full_m.get("winRate") or 0):.1f}% | {(oos_m.get("winRate") or 0):.1f}% |
| 매매 횟수 | {(full_m.get("trades") or 0)}회 | {oos_trades}회 |

{msg}
"""
        else:
            report += "\n#### 실전 신뢰도 검증\n\n데이터가 부족하여 검증을 수행하지 못했습니다.\n"

        # ── 6. 주의사항 ──
        report += f"""
---
*{total_trials}회 시뮬레이션으로 찾은 결과이며, 과거 성과가 미래 수익을 보장하지 않습니다. 실전 적용 전 다양한 기간에서 추가 테스트를 권장합니다.*
"""
        return report.strip()

    def run_optimization_loop(self, base_request: Dict[str, Any], user_prompt: str, ranges: Dict[str, Any], target_metric: str = "cagr", n_trials: int = 50) -> Dict[str, Any]:
        """
        The main orchestration method replacing the LLM API loop.
        """
        print(f"[LocalOptimizationAgent] 1. Receiving search space for target: '{target_metric}', prompt: '{user_prompt}'")

        if not ranges:
            return {
                "status": "error",
                "message": "No parameter ranges were submitted for optimization.",
                "ranges_attempted": ranges
            }

        print(f"[LocalOptimizationAgent] 2. Running ML Optimizer for {n_trials} trials...")
        opt_results = self.optimizer.optimize(
            base_request, ranges, target_metric=target_metric, n_trials=n_trials, holdout_validation=True
        )

        if opt_results.get("status") == "error":
            return opt_results

        print(f"[LocalOptimizationAgent] 3. Writing Text Report Locally...")
        report = self.write_report(
            best_params=opt_results.get("best_parameters", {}),
            top_results=opt_results.get("top_results", []),
            target_metric=target_metric,
            importances=opt_results.get("param_importances", {}),
            total_trials=opt_results.get("total_iterations", n_trials),
            holdout=opt_results.get("holdout_validation")
        )

        return {
            "status": "success",
            "tested_ranges": ranges,
            "target_metric": target_metric,
            "total_iterations": opt_results["total_iterations"],
            "best_parameters": opt_results["best_parameters"],
            "best_metrics": opt_results["best_metrics"],
            "top_results": opt_results["top_results"],
            "report": report
        }
