#!/usr/bin/env bash
# Modal 백테스트 워커 이미지가 설치하는 의존성을 uv.lock에서 내보낸다.
#
# 결과 동일성 계약: Modal 워커는 앱 박스와 "같은 버전"으로 돌아야 한다. 종전에는
# modal_backtest.py의 PINNED_DEPS를 prod 컨테이너에서 손으로 실측해 적었고, 전이 의존
# (scipy·numba 등)은 아무도 고정하지 않아 조용히 갈라질 수 있었다. 이제 pyproject.toml의
# `modal` 그룹이 "무엇을 넣을지"를, uv.lock이 "어떤 버전으로"를 정한다.
#
#   pyproject.toml [dependency-groups] modal  을 고쳤거나 uv.lock을 갱신했으면 이 스크립트를
#   다시 돌리고 결과를 커밋한다. 잊으면 backend/tests/test_modal_requirements_export.py 가 실패한다.
set -euo pipefail
cd "$(dirname "$0")/.."
uv export --frozen --only-group modal --no-hashes --no-annotate --no-header \
    --output-file requirements-modal.txt
echo "requirements-modal.txt 갱신 완료 ($(grep -c . requirements-modal.txt)줄)"
