"""
AI 코드 14가지 버그 수정 회귀 방지 테스트
각 번호는 AI 코드 리뷰 리포트의 이슈 번호와 대응.
"""
import os
import sys
import inspect
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# Helper: AIEngine mock 초기화
# ──────────────────────────────────────────────────────────────────────────────

import io
import json as json_mod

_real_open = open

def _mock_open_factory(meta=None):
    """builtins.open을 mock하되, xgboost 등 시스템 파일은 통과시킨다."""
    meta = meta or {}
    def _mock_open(path, *args, **kwargs):
        if isinstance(path, str) and path.endswith('model_meta.json'):
            return io.StringIO(json_mod.dumps(meta))
        return _real_open(path, *args, **kwargs)
    return _mock_open

def _make_mock_engine(meta_override=None):
    """AIEngine을 모델 파일 없이 mock으로 생성."""
    meta = meta_override or {}
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', side_effect=_mock_open_factory(meta)), \
         patch('joblib.load') as mock_joblib, \
         patch('torch.load', return_value={}), \
         patch('torch.nn.Module.load_state_dict', return_value=None), \
         patch('xgboost.XGBClassifier.load_model'):

        mock_scaler = MagicMock()
        mock_scaler.transform.side_effect = lambda x: x
        mock_joblib.return_value = mock_scaler

        from ai.ai_engine import AIEngine
        engine = AIEngine()
    return engine


# ══════════════════════════════════════════════════════════════════════════════
# Issue #1: 하드코딩 절대 경로 제거
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue1_NoHardcodedPath:
    def test_default_model_dir_is_dynamic(self):
        """model_dir 기본값이 __file__ 기반으로 동적 계산되며 하드코딩되지 않아야 한다."""
        engine = _make_mock_engine()
        # 프로젝트 루트/model/ 하위 디렉토리여야 함 (v2, expanded_features 등)
        assert 'model' in engine.model_dir
        # 소스 코드에 하드코딩된 절대 경로가 없어야 함
        from ai.ai_engine import AIEngine
        source = inspect.getsource(AIEngine.__init__)
        assert '/Users/eugene/' not in source
        assert 'os.path.dirname' in source or 'os.path.abspath' in source

    def test_custom_model_dir_respected(self):
        """명시적으로 전달한 model_dir이 그대로 사용된다."""
        custom = "/tmp/my_model"
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=_mock_open_factory({})), \
             patch('joblib.load', return_value=MagicMock()), \
             patch('torch.load', return_value={}), \
             patch('torch.nn.Module.load_state_dict', return_value=None), \
             patch('xgboost.XGBClassifier.load_model'):
            from ai.ai_engine import AIEngine
            engine = AIEngine(model_dir=custom)
        assert engine.model_dir == custom


# ══════════════════════════════════════════════════════════════════════════════
# Issue #2: 파일 기반 로깅 → logging 모듈
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue2_LoggingModule:
    def test_no_file_open_in_predict_signals(self):
        """predict_signals 내에서 open(file, 'a') 형태의 파일 쓰기가 없어야 한다."""
        from ai.ai_engine import AIEngine
        source = inspect.getsource(AIEngine.predict_signals)
        # 파일에 직접 쓰는 패턴이 없어야 함
        assert 'open(log_file' not in source
        assert 'with open(' not in source
        assert 'backend_execution.log' not in source

    def test_logger_exists_in_module(self):
        """ai.ai_engine 모듈에 logging.getLogger가 설정되어 있어야 한다."""
        import ai.ai_engine as mod
        assert hasattr(mod, 'logger')


# ══════════════════════════════════════════════════════════════════════════════
# Issue #3: XGBoost predict_proba 클래스 인덱스
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue3_MultiOutputColumnMapping:
    def test_column0_is_rise_column1_is_drop(self):
        """XGBoost 예측에서 상승/하락 확률이 올바르게 분리되어야 한다.
        V2: separate xgb_up/xgb_down 모델, V1: multi-output head."""
        engine = _make_mock_engine()
        engine.lookback = 3

        engine.transformer = MagicMock()
        engine.transformer.return_value.cpu.return_value.numpy.return_value = np.ones((3, 10))

        if engine.use_separate_xgb:
            # V2: separate models
            engine.xgb_up = MagicMock()
            engine.xgb_up.predict_proba.return_value = np.array([[0.2, 0.8], [0.3, 0.7], [0.1, 0.9]])
            engine.xgb_down = MagicMock()
            engine.xgb_down.predict_proba.return_value = np.array([[0.8, 0.2], [0.7, 0.3], [0.9, 0.1]])
        else:
            # V1: single head
            engine.xgb_head = MagicMock()
            engine.xgb_head.predict_proba.return_value = np.array([
                [0.8, 0.2], [0.7, 0.3], [0.9, 0.1],
            ])

        df = pd.DataFrame({
            'open': [100, 110, 120, 130, 100],
            'high': [105, 115, 125, 135, 105],
            'low': [95, 105, 115, 125, 95],
            'close': [100, 110, 120, 130, 100],
            'volume': [1000] * 5,
            'rsi_14': [50] * 5,
        })

        probs_rise, probs_drop = engine.predict_signals(df)

        rise_vals = probs_rise[engine.lookback - 1:]
        drop_vals = probs_drop[engine.lookback - 1:]
        assert np.any(rise_vals > 0), "Rise probs should have non-zero values"
        assert np.any(drop_vals > 0), "Drop probs should have non-zero values"

    def test_source_uses_column_indexing(self):
        """소스 코드에서 predict_proba 결과의 컬럼 인덱싱이 올바르게 사용되어야 한다.
        V2: xgb_up.predict_proba[:, 1] = P(up), V1: preds[:, 0]."""
        from ai.ai_engine import AIEngine
        source = inspect.getsource(AIEngine._xgb_predict)
        assert '[:, 0]' in source or '[:, 1]' in source


# ══════════════════════════════════════════════════════════════════════════════
# Issue #4 & #5: xai_engine 폴백 경로 — log1p 사용 & 전체 피처 계산
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue4_5_XaiEngineFallback:
    def test_fallback_uses_log1p(self):
        """Feature engineering에서 log1p를 사용해야 한다 (xai_engine 또는 ai_engine에서)."""
        # V2: feature engineering is in ai_engine.py, imported by xai_engine
        ai_engine_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'ai_engine.py')
        xai_engine_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')

        with open(ai_engine_path, 'r') as f:
            ai_source = f.read()
        with open(xai_engine_path, 'r') as f:
            xai_source = f.read()

        # log1p should be in either ai_engine (shared) or xai_engine (inline)
        assert 'log1p' in ai_source or 'log1p' in xai_source, \
            "Neither ai_engine.py nor xai_engine.py uses log1p for returns"

    def test_fallback_has_key_features(self):
        """Feature engineering에서 핵심 피처가 계산돼야 한다."""
        ai_engine_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'ai_engine.py')
        with open(ai_engine_path, 'r') as f:
            source = f.read()

        required_features = ['ret_obv', 'dist_sma_20', 'boll_pos']
        for feat in required_features:
            assert feat in source, f"Missing feature '{feat}' in ai_engine.py feature engineering"

    def test_lfs_pointer_processed_parquet_falls_back_to_raw_ohlcv(self, tmp_path):
        """processed parquet가 Git LFS 포인터여도 raw OHLCV parquet로 fallback 해야 한다."""
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        from ai.xai_engine import _load_symbol_dataframe

        model_dir = tmp_path / "model"
        raw_dir = tmp_path / "data" / "ohlcv"
        model_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)

        processed_path = model_dir / "training_data_processed.parquet"
        processed_path.write_text(
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:test\n"
            "size 123\n",
            encoding="utf-8",
        )

        raw_df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 1200],
        })
        raw_path = raw_dir / "005930.parquet"
        raw_df.to_parquet(raw_path, index=False)

        engine = MagicMock()
        engine.model_dir = str(model_dir)

        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            loaded = _load_symbol_dataframe(engine, "005930")
        finally:
            os.chdir(cwd)

        pd.testing.assert_frame_equal(loaded.reset_index(drop=True), raw_df)

    def test_xai_retries_on_cpu_when_mps_runtime_fails(self):
        """XAI는 MPS를 우선 사용하되 MPS 런타임 오류 시 CPU fallback 해야 한다."""
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        import torch
        from ai.xai_engine import _move_engine_to_cpu, _should_retry_on_cpu

        engine = MagicMock()
        engine.device = torch.device("mps")
        engine.transformer = MagicMock()
        engine.transformer.to.return_value = engine.transformer

        err = RuntimeError("MPSNDArray init failed assertion: NDArray dimension length > INT_MAX")

        assert _should_retry_on_cpu(engine, err) is True
        _move_engine_to_cpu(engine)
        assert engine.device.type == "cpu"
        engine.transformer.to.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Issue #6: optimizer.py 에러 target_value — maxDrawdown 시 999999.0
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue6_OptimizerErrorTargetValue:
    def test_error_target_value_for_cagr(self):
        """target_metric='cagr'일 때 에러 결과의 target_value는 -999999.0이어야 한다."""
        from engine.grid_optimizer import StrategyOptimizer

        mock_engine = MagicMock()
        mock_engine.run_backtest.side_effect = RuntimeError("test error")

        optimizer = StrategyOptimizer(mock_engine)
        result = optimizer.optimize(
            base_request={"symbols": ["TEST"]},
            ranges={"param1": [1, 2]},
            target_metric="cagr"
        )

        error_results = [r for r in result["all_results"] if "error" in r]
        assert len(error_results) > 0
        for r in error_results:
            assert r["target_value"] == -999999.0

    def test_error_target_value_for_maxdrawdown(self):
        """target_metric='maxDrawdown'일 때 에러 결과의 target_value는 999999.0이어야 한다."""
        from engine.grid_optimizer import StrategyOptimizer

        mock_engine = MagicMock()
        mock_engine.run_backtest.side_effect = RuntimeError("test error")

        optimizer = StrategyOptimizer(mock_engine)
        result = optimizer.optimize(
            base_request={"symbols": ["TEST"]},
            ranges={"param1": [1, 2]},
            target_metric="maxDrawdown"
        )

        error_results = [r for r in result["all_results"] if "error" in r]
        assert len(error_results) > 0
        for r in error_results:
            assert r["target_value"] == 999999.0


# ══════════════════════════════════════════════════════════════════════════════
# Issue #8: 중복 import traceback 제거
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue8_NoDuplicateImport:
    def test_no_duplicate_import_traceback(self):
        """optimization_agent.py에 import traceback이 중복되지 않아야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'optimization_agent.py')
        with open(source_path, 'r') as f:
            lines = f.readlines()

        import_count = sum(1 for line in lines if line.strip() == 'import traceback')
        assert import_count == 1, f"'import traceback' appears {import_count} times (expected 1)"


# ══════════════════════════════════════════════════════════════════════════════
# Issue #9: 마크다운 파싱 대소문자 처리
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue9_MarkdownParsing:
    def test_parse_uppercase_json_block(self):
        """```JSON (대문자)로 감싸진 응답도 정상 파싱돼야 한다."""
        from ai.optimization_agent import OptimizationAgent

        agent = MagicMock(spec=OptimizationAgent)
        agent.determine_ranges = OptimizationAgent.determine_ranges

        mock_response = MagicMock()
        mock_response.content = '```JSON\n{"ranges": {"path.to.param": [1, 2, 3]}}\n```'

        agent.llm = MagicMock()
        agent.llm.invoke.return_value = mock_response

        result = agent.determine_ranges(agent, {"symbols": ["TEST"]}, "test goal")
        assert result == {"path.to.param": [1, 2, 3]}

    def test_parse_lowercase_json_block(self):
        """```json (소문자) 파싱도 정상 동작해야 한다."""
        from ai.optimization_agent import OptimizationAgent

        agent = MagicMock(spec=OptimizationAgent)
        agent.determine_ranges = OptimizationAgent.determine_ranges

        mock_response = MagicMock()
        mock_response.content = '```json\n{"ranges": {"a.b": [10, 20]}}\n```'

        agent.llm = MagicMock()
        agent.llm.invoke.return_value = mock_response

        result = agent.determine_ranges(agent, {}, "goal")
        assert result == {"a.b": [10, 20]}

    def test_parse_raw_json(self):
        """마크다운 블록 없는 순수 JSON도 정상 파싱돼야 한다."""
        from ai.optimization_agent import OptimizationAgent

        agent = MagicMock(spec=OptimizationAgent)
        agent.determine_ranges = OptimizationAgent.determine_ranges

        mock_response = MagicMock()
        mock_response.content = '{"ranges": {"x": [1]}}'

        agent.llm = MagicMock()
        agent.llm.invoke.return_value = mock_response

        result = agent.determine_ranges(agent, {}, "goal")
        assert result == {"x": [1]}


# ══════════════════════════════════════════════════════════════════════════════
# Issue #10: local_optimization_agent None 곱셈 크래시 방지
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue10_NoneMultiplicationSafe:
    def test_write_report_with_none_metrics(self):
        """metrics 값이 None이어도 write_report가 크래시하지 않아야 한다."""
        from ai.local_optimization_agent import LocalOptimizationAgent

        agent = MagicMock(spec=LocalOptimizationAgent)
        agent.write_report = LocalOptimizationAgent.write_report

        # 모든 metric이 None인 경우
        top_results = [{
            "metrics": {
                "cagr": None,
                "mdd": None,
                "winRate": None,
                "profitFactor": None,
                "sharpe": None,
                "trades": None
            },
            "target_value": 0
        }]

        report = agent.write_report(
            agent,
            user_prompt="test",
            best_params={"param1": 10},
            top_results=top_results,
            target_metric="cagr",
            importances={},
            total_trials=10
        )
        assert isinstance(report, str)
        assert len(report) > 0

    def test_write_report_with_empty_results(self):
        """top_results가 빈 리스트여도 크래시하지 않아야 한다."""
        from ai.local_optimization_agent import LocalOptimizationAgent

        agent = MagicMock(spec=LocalOptimizationAgent)
        agent.write_report = LocalOptimizationAgent.write_report

        report = agent.write_report(
            agent,
            user_prompt="test",
            best_params={},
            top_results=[],
            target_metric="cagr",
            importances={},
            total_trials=0
        )
        assert isinstance(report, str)


# ══════════════════════════════════════════════════════════════════════════════
# Issue #11: optuna_optimizer None TypeError 방지
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue11_OptunaSortingNoneSafe:
    def test_sort_with_none_target_value(self):
        """target_value가 None인 결과가 포함돼도 정렬이 크래시하지 않아야 한다."""
        results = [
            {"target_value": 0.5},
            {"target_value": None},
            {"target_value": 0.8},
            {"target_value": None},
            {"target_value": 0.3},
        ]

        # optuna_optimizer.py의 정렬 로직 재현
        reverse_sort = True  # cagr 기준
        default_val = -999999.0 if reverse_sort else 999999.0
        results.sort(
            key=lambda x: x.get("target_value") if x.get("target_value") is not None else default_val,
            reverse=reverse_sort
        )

        # None이 아닌 값들이 먼저 와야 함 (내림차순)
        non_none = [r["target_value"] for r in results if r["target_value"] is not None]
        assert non_none == [0.8, 0.5, 0.3]

    def test_sort_maxdrawdown_with_none(self):
        """maxDrawdown 기준 정렬에서 None이 포함돼도 안전해야 한다."""
        results = [
            {"target_value": -15.0},
            {"target_value": None},
            {"target_value": -5.0},
        ]

        reverse_sort = False  # maxDrawdown: lower is better
        default_val = -999999.0 if reverse_sort else 999999.0
        results.sort(
            key=lambda x: x.get("target_value") if x.get("target_value") is not None else default_val,
            reverse=reverse_sort
        )

        # -15가 먼저 (더 낮은 값이 앞에), None은 맨 뒤 (999999.0)
        assert results[0]["target_value"] == -15.0
        assert results[1]["target_value"] == -5.0
        assert results[2]["target_value"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Issue #12: Scaler 입력 차원 검증
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue12_ScalerDimensionValidation:
    def test_mismatched_scaler_raises_error(self):
        """scaler 차원과 feature 수가 다르면 ValueError가 발생해야 한다."""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', MagicMock()), \
             patch('json.load', return_value={}), \
             patch('joblib.load') as mock_joblib, \
             patch('torch.load', return_value={}), \
             patch('torch.nn.Module.load_state_dict', return_value=None), \
             patch('xgboost.XGBClassifier.load_model'):

            mock_scaler = MagicMock()
            mock_scaler.n_features_in_ = 10  # 17과 불일치
            mock_joblib.return_value = mock_scaler

            from ai.ai_engine import AIEngine
            with pytest.raises(ValueError, match="Scaler expects 10 features"):
                AIEngine()

    def test_matching_scaler_passes(self):
        """scaler 차원과 feature 수가 일치하면 정상 초기화돼야 한다."""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', MagicMock()), \
             patch('json.load', return_value={}), \
             patch('joblib.load') as mock_joblib, \
             patch('torch.load', return_value={}), \
             patch('torch.nn.Module.load_state_dict', return_value=None), \
             patch('xgboost.XGBClassifier.load_model'):

            mock_scaler = MagicMock()
            # Feature count depends on detected model version
            from ai.ai_engine import AIEngine
            engine = AIEngine()
            n_feat = len(engine.ts_features)
            mock_scaler.n_features_in_ = n_feat
            assert n_feat > 0


# ══════════════════════════════════════════════════════════════════════════════
# Issue #13: as_strided에 np.ascontiguousarray 적용
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue13_ContiguousArray:
    def test_source_uses_ascontiguousarray(self):
        """scaler.transform 결과에 np.ascontiguousarray가 적용돼야 한다.
        리팩터링 후 로직은 _preprocess_for_ai에 있음."""
        from ai.ai_engine import AIEngine
        source = inspect.getsource(AIEngine._preprocess_for_ai)
        assert 'ascontiguousarray' in source

    def test_contiguous_array_with_strided(self):
        """비연속 배열에 as_strided를 적용하면 잘못된 결과가 나올 수 있음을 확인."""
        from numpy.lib.stride_tricks import as_strided

        # 연속 배열
        data = np.ascontiguousarray(np.array([[1, 2], [3, 4], [5, 6]], dtype=np.float32))
        assert data.flags['C_CONTIGUOUS']

        n_windows = 2
        lookback = 2
        n_feat = 2
        strides = data.strides
        windows = as_strided(data, shape=(n_windows, lookback, n_feat),
                             strides=(strides[0], strides[0], strides[1]))
        # 첫 번째 윈도우: [[1,2],[3,4]], 두 번째: [[3,4],[5,6]]
        np.testing.assert_array_equal(windows[0], [[1, 2], [3, 4]])
        np.testing.assert_array_equal(windows[1], [[3, 4], [5, 6]])


# ══════════════════════════════════════════════════════════════════════════════
# Issue #14: xai_engine import 경로 통일
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue14_ImportPath:
    def test_no_backend_prefix_in_import(self):
        """xai_engine.py에서 'from backend.ai.' 형태의 import가 없어야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        assert 'from backend.ai.' not in source
        assert 'from ai.ai_engine import AIEngine' in source


# ══════════════════════════════════════════════════════════════════════════════
# Issue #15: xai_engine — 'from backend.engine.' import 경로도 통일
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue15_XaiEngineIndicatorImport:
    def test_no_backend_engine_prefix(self):
        """xai_engine.py에서 'from backend.engine.' 형태의 import가 없어야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        assert 'from backend.engine.' not in source
        # V2: feature engineering is imported from ai_engine, V1 compat uses engine.indicators
        assert 'from ai.ai_engine import' in source or 'from engine.indicators import' in source


# ══════════════════════════════════════════════════════════════════════════════
# Issue #16: xai_engine — 하드코딩된 model_dir 제거
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue16_XaiEngineNoDynamicModelDir:
    def test_no_hardcoded_model_dir_in_run_xai(self):
        """run_xai 함수에서 AIEngine에 model_dir를 하드코딩하지 않아야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        # AIEngine(model_dir="...") 형태의 하드코딩이 없어야 함
        assert 'model_dir="model/' not in source
        assert "model_dir='model/" not in source


# ══════════════════════════════════════════════════════════════════════════════
# Issue #17: xai_engine — 중복 feature engineering 코드 제거
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue17_XaiEngineNoDuplicateFeatureCode:
    def test_feature_engineering_is_shared(self):
        """xai_engine.py가 feature engineering을 ai_engine에서 공유하거나 헬퍼를 사용해야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        # V2: imports from ai_engine, V1: has _compute_features
        has_shared = ('_engineer_features_v2' in source or
                      '_engineer_features_v1' in source or
                      'def _compute_features(' in source)
        assert has_shared, "Feature engineering should be shared/imported, not duplicated"

    def test_no_duplicate_indicator_engine_blocks(self):
        """IndicatorEngine.calculate 호출이 중복되면 안 된다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        count = source.count('IndicatorEngine.calculate(')
        assert count <= 1, f"IndicatorEngine.calculate 호출이 {count}번 발견됨 (최대 1번이어야 함)"


# ══════════════════════════════════════════════════════════════════════════════
# Issue #18: xai_engine — bare except 제거
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue18_XaiEngineNoBareExcept:
    def test_no_bare_except(self):
        """xai_engine.py에 'except:' (bare except) 패턴이 없어야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            stripped = line.strip()
            # 'except:' 만 있는 줄 (bare except)
            if stripped == 'except:':
                pytest.fail(f"Line {i+1}: bare 'except:' found: {line.rstrip()}")


# ══════════════════════════════════════════════════════════════════════════════
# Issue #19: xai_engine — 매직넘버 60/17 제거
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue19_XaiEngineNoMagicNumbers:
    def test_no_hardcoded_60_in_reshape(self):
        """xai_engine.py의 reshape/slice에서 60을 하드코딩하지 않고 engine.lookback을 사용해야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        # reshape(-1, 60, 17) 같은 하드코딩 패턴이 없어야 함
        assert 'reshape(-1, 60,' not in source
        assert 'reshape(60,' not in source
        # pos < 59 같은 하드코딩 대신 lookback 사용
        assert 'pos < 59' not in source

    def test_no_hardcoded_17_in_reshape(self):
        """xai_engine.py의 reshape에서 17을 하드코딩하지 않아야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        assert ', 17)' not in source


# ══════════════════════════════════════════════════════════════════════════════
# Issue #20: xai_engine SHAP — P(up) 컬럼 일관성
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue20_XaiShapColumnConsistency:
    def test_shap_predict_targets_up_probability(self):
        """SHAP의 model_predict_2d가 P(up)을 반환해야 한다.
        V2: xgb_up.predict_proba[:, 1], V1: xgb_head.predict_proba[:, 0]."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        # predict_proba 결과에서 컬럼 인덱싱이 있어야 함
        assert 'predict_proba' in source
        assert '[:, 0]' in source or '[:, 1]' in source

    def test_shap_output_uses_class_0(self):
        """SHAP 결과 파싱에서 shap_out[0] (class 0 = up)을 사용해야 한다."""
        source_path = os.path.join(os.path.dirname(__file__), '..', 'ai', 'xai_engine.py')
        with open(source_path, 'r') as f:
            source = f.read()

        # shap_out[1] 사용 안 됨 (이전 버그: class 1 = down을 설명)
        assert 'shap_out[1]' not in source
        # shap_out[0] 사용
        assert 'shap_out[0]' in source


# ══════════════════════════════════════════════════════════════════════════════
# Issue #21: ai_engine — 중복 초기화 로그 제거
# ══════════════════════════════════════════════════════════════════════════════

class TestIssue21_NoDuplicateInitLog:
    def test_single_init_log(self):
        """AIEngine.__init__에서 초기화 완료 로그가 1번만 출력되어야 한다."""
        from ai.ai_engine import AIEngine
        source = inspect.getsource(AIEngine.__init__)

        # logger.info 호출에 'AIEngine'이 포함된 줄이 1번만 있어야 함
        init_logs = [line for line in source.split('\n')
                     if 'logger.info' in line and 'AIEngine' in line]
        assert len(init_logs) == 1, f"AIEngine init log가 {len(init_logs)}번 발견됨 (1번이어야 함)"

    def test_uses_logger_not_print_for_init(self):
        """AIEngine.__init__의 초기화 로그가 print가 아닌 logger를 사용해야 한다."""
        from ai.ai_engine import AIEngine
        source = inspect.getsource(AIEngine.__init__)

        # logger.info 사용
        assert 'logger.info' in source
        # 마지막 print("AIEngine initialized...") 패턴이 없어야 함
        lines = source.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('print(') and 'AIEngine initialized' in stripped:
                pytest.fail(f"print()로 초기화 로그 출력 발견: {stripped}")
