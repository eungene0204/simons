from typing import Dict, Any, List
from engine.optuna_optimizer import OptunaOptimizer

class LocalOptimizationAgent:
    def __init__(self, engine):
        """
        engine: an instance of BacktestEngine
        """
        self.engine = engine
        self.optimizer = OptunaOptimizer(engine)

    def write_report(self, user_prompt: str, best_params: Dict[str, Any], top_results: List[Dict[str, Any]], target_metric: str, importances: Dict[str, float], total_trials: int) -> str:
        """
        Generates a human-readable markdown report explaining the optimization results 
        programmatically without relying on an external LLM.
        """
        importances_md = "해당 최적화에서 영향력이 분석된 주요 변수들은 다음과 같습니다:"
        if importances:
            sorted_imp = sorted(importances.items(), key=lambda item: item[1], reverse=True)
            for k, v in sorted_imp:
                # Format key for readability
                display_key = k.split('.')[-1].replace('_', ' ').capitalize()
                importances_md += f"\n- **{display_key}**: {v*100:.1f}% 기여도"
        else:
            importances_md = "변수 기여도를 분석하기에는 시도 횟수(Trials)가 부족하거나 결과들의 분산이 작았습니다."

        if not top_results:
            return "최적화 결과가 없습니다. 모든 시뮬레이션이 실패했을 수 있습니다."

        best_metrics = top_results[0]["metrics"]
        win_rate = (best_metrics.get("winRate") or 0) * 100
        cagr = best_metrics.get("cagr") or 0
        mdd = best_metrics.get("maxDrawdown") or 0
        trades = best_metrics.get("trades") or 0

        # Mapping target metric backend name to readable string
        metric_kr = {
            "cagr": "연평균 수익률 (CAGR)",
            "winRate": "승률 (Win Rate)",
            "sharpe": "샤프 지수 (Sharpe Ratio)",
            "profitFactor": "수익 팩터 (Profit Factor)",
            "maxDrawdown": "최대 낙폭 (MDD)",
            "totalReturn": "총 수익률 (Total Return)"
        }.get(target_metric, target_metric)

        report = f"""
### 로컬 ML 최적화 결과 보고서

**1. 최적화 개요**
* 설정하신 목표 지표인 **{metric_kr}** 기준으로 총 **{total_trials}개의 경우의 수**를 베이지안 튜닝(Optuna) 방식으로 시뮬레이션 하였습니다.
* 사용자 분석 목표: "{user_prompt}"

**2. 찾아낸 최적의 파라미터 셋**
가장 우수한 성능을 보여준 파라미터 조합은 다음과 같습니다:
"""
        for k, v in best_params.items():
            display_key = k.split('.')[-1].replace('_', ' ').capitalize()
            report += f"* **{display_key}**: `{v}`\n"

        report += f"""
**3. 최적 파라미터 하의 핵심 성과 (Top 1)**
* **{metric_kr}**: 최고 수준 달성
* **연환산 수익률 (CAGR)**: {cagr:.2f}%
* **승률 (Win Rate)**: {win_rate:.1f}%
* **최대 낙폭 (MDD)**: {mdd:.2f}%
* **총 매매 횟수**: {trades}회

**4. 파라미터 중요도 (Optuna Importances)**
{importances_md}

**5. 시스템 분석 요약**
이 조합은 머신러닝 모델(Optuna의 TPE 샘플러)이 {total_trials}번의 탐색적 백테스트 끝에 발견한 지역 최적점(Local Optima)입니다.
발견된 파라미터는 백테스트 기간 내에서 {metric_kr}를 극대화하는 성질을 가집니다. 다만 특정 기간에 과최적화(Overfitting) 되었을 가능성도 존재하므로 실제 적용 전 다양한 시장 국면에서의 추가 검증(Forward Testing)을 권장합니다.
"""
        return report.strip()

    def run_optimization_loop(self, base_request: Dict[str, Any], user_prompt: str, ranges: Dict[str, Any], target_metric: str = "cagr", n_trials: int = 50) -> Dict[str, Any]:
        """
        The main orchestration method replacing the LLM API loop.
        """
        print(f"[LocalOptimizationAgent] 1. Receiving search space directly from UI for target: '{target_metric}'")
        
        if not ranges:
            return {
                "status": "error",
                "message": "No parameter ranges were submitted for optimization.",
                "ranges_attempted": ranges
            }
            
        print(f"[LocalOptimizationAgent] 2. Running ML Optimizer for {n_trials} trials...")
        opt_results = self.optimizer.optimize(base_request, ranges, target_metric=target_metric, n_trials=n_trials)
        
        if opt_results.get("status") == "error":
            return opt_results

        print(f"[LocalOptimizationAgent] 3. Writing Text Report Locally...")
        report = self.write_report(
            user_prompt=user_prompt,
            best_params=opt_results.get("best_parameters", {}),
            top_results=opt_results.get("top_results", []),
            target_metric=target_metric,
            importances=opt_results.get("param_importances", {}),
            total_trials=opt_results.get("total_iterations", n_trials)
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
