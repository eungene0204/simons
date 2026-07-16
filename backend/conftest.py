"""Test configuration — setup sys.path for imports."""

import os
import sys
from pathlib import Path

# backend 디렉토리를 sys.path에 추가해 모든 테스트 파일이 직접 import 가능하게
backend_root = Path(__file__).parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# 테스트는 LLM-first 인터프리터 모드와 무관하게 결정적이어야 한다 — 개발자의 .env
# (STRATEGY_INTERPRETER_MODE=primary)가 main.py load_dotenv로 새어 들어와 파스 경로를
# 바꾸지 않도록 기본 off로 고정한다. 모드 자체를 검증하는 테스트는 monkeypatch로 재설정.
os.environ["STRATEGY_INTERPRETER_MODE"] = "off"
