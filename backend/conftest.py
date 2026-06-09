"""Test configuration — setup sys.path for imports."""

import sys
from pathlib import Path

# backend 디렉토리를 sys.path에 추가해 모든 테스트 파일이 직접 import 가능하게
backend_root = Path(__file__).parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))
