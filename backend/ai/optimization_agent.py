import os
import json
import traceback
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# Core Optimizer
from engine.optimizer import StrategyOptimizer, generate_permutations

class OptimizationAgent:
    def __init__(self, engine, model_name="gpt-4o", gemini_model_name="gemini-2.5-flash"):
        """
        engine: an instance of BacktestEngine
        """
        self.engine = engine
        self.optimizer = StrategyOptimizer(engine)
        
        # Initialize LLM
        openai_key = os.getenv("OPENAI_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")
        
        if openai_key:
            print("[OptimizationAgent] Using OpenAI for optimization.")
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=0.2,
                api_key=openai_key
            )
        elif google_key:
            print("[OptimizationAgent] Using Google Gemini for optimization.")
            self.llm = ChatGoogleGenerativeAI(
                model=gemini_model_name,
                temperature=0.2,
                google_api_key=google_key
            )
        else:
            print("[OptimizationAgent] WARNING: Neither OPENAI_API_KEY nor GOOGLE_API_KEY found. LLM features will fail.")
            # Fallback to dummy OpenAI to trigger standard error
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=0.2,
                api_key="DUMMY_KEY"
            )
        
    def determine_ranges(self, base_request: Dict[str, Any], user_prompt: str) -> Dict[str, List[Any]]:
        """
        Asks the LLM to analyze the base strategy and user prompt, and output 
        a JSON object defining the parameter ranges to test.
        """
        sys_prompt = """
        You are a quantitative trading strategy optimizer.
        The user wants to optimize a trading strategy based on a specific goal.
        
        Analyze the PROVIDED BASE STRATEGY JSON and the USER'S GOAL.
        Identify between 1 to 3 key parameters in the JSON that should be optimized to achieve this goal.
        
        Return ONLY a JSON object containing a "ranges" key. 
        The keys inside "ranges" MUST be the exact dot-notation path to the parameter in the strategy JSON.
        The values MUST be a list of 3-5 sensible values to test.
        
        Example Output:
        {{
            "ranges": {{
                "entry.conditions.0.params.period": [10, 14, 20, 25],
                "risk.stop_loss_pct": [3.0, 5.0, 7.0]
            }}
        }}

        Limit the total number of permutations (product of all list lengths) to a maximum of 30!
        DO NOT include markdown formatting or backticks in your response. Just raw JSON.
        """
        
        try:
            # We use invoke instead of simple predict for current langchain
            message = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"USER GOAL: {user_prompt}\n\nBASE STRATEGY:\n{json.dumps(base_request, indent=2)}"}
            ]
            response = self.llm.invoke(message)
            
            # Clean response if it contains markdown block
            content = response.content.strip()
            content_lower = content.lower()
            if content_lower.startswith("```json"):
                content = content[7:]
                if content.rstrip().endswith("```"):
                    content = content.rstrip()[:-3]
                content = content.strip()
            elif content_lower.startswith("```"):
                content = content[3:]
                if content.rstrip().endswith("```"):
                    content = content.rstrip()[:-3]
                content = content.strip()
                
            parsed = json.loads(content)
            ranges = parsed.get("ranges", {})
            return ranges
        except Exception as e:
            print(f"[OptimizationAgent] Error determining ranges: {e}")
            traceback.print_exc()
            return {}

    def write_report(self, base_request: Dict[str, Any], user_prompt: str, best_params: Dict[str, Any], top_results: List[Dict[str, Any]], target_metric: str) -> str:
        """
        Generates a human-readable markdown report explaining the optimization results.
        """
        sys_prompt = """
        You are an expert quantitative trading consultant.
        You have just completed a parameter grid-search optimization for a client's trading strategy.
        
        Write a concise, professional report in Korean (Markdown format).
        Explain:
        1. What the goal was.
        2. What the originally submitted parameters were, and what the newly found optimal parameters are.
        3. Why these new parameters likely perform better (financial/logical reason based on the metrics).
        
        Keep it structured, insightful, and under 500 words.
        """
        
        data_dump = {
            "user_goal": user_prompt,
            "target_metric": target_metric,
            "best_parameters_found": best_params,
            "top_5_results": top_results
        }
        
        try:
            message = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"OPTIMIZATION RESULTS:\n{json.dumps(data_dump, indent=2)}"}
            ]
            response = self.llm.invoke(message)
            return response.content.strip()
        except Exception as e:
            print(f"[OptimizationAgent] Error writing report: {e}")
            return f"보고서 생성 중 오류가 발생했습니다: {e}"

    def run_optimization_loop(self, base_request: Dict[str, Any], user_prompt: str, target_metric: str = "cagr") -> Dict[str, Any]:
        """
        The main orchestration method.
        """
        print(f"[OptimizationAgent] 1. Analyzing strategy and determining ranges for goal: '{user_prompt}'")
        ranges = self.determine_ranges(base_request, user_prompt)
        
        if not ranges:
            return {
                "status": "error",
                "message": "AI failed to determine valid parameter ranges for optimization.",
                "ranges_attempted": ranges
            }
            
        # Hard limit permutations safely 
        # (Though LLM is told to limit, we enforce it to avoid blowing up memory/time)
        perms = generate_permutations(ranges)
        if len(perms) > 50:
            return {
                "status": "error",
                "message": f"Too many permutations generated ({len(perms)}). Maximum is 50. Please simplify your request.",
                "ranges_attempted": ranges
            }
            
        print(f"[OptimizationAgent] 2. Running Numerical Optimizer for {len(perms)} permutations...")
        opt_results = self.optimizer.optimize(base_request, ranges, target_metric=target_metric)
        
        print(f"[OptimizationAgent] 3. Writing Final Report...")
        report = self.write_report(
            base_request=base_request,
            user_prompt=user_prompt,
            best_params=opt_results.get("best_parameters"),
            top_results=opt_results.get("top_results", []),
            target_metric=target_metric
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
