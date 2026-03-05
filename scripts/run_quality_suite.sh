#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/docs/quality/local/latest"
PYTHON_BIN="${ROOT_DIR}/backend/venv/bin/python"

mkdir -p "${OUT_DIR}"
rm -f "${OUT_DIR}/junit.xml" "${OUT_DIR}/security_junit.xml" "${OUT_DIR}/pytest.log" "${OUT_DIR}/summary.json" "${OUT_DIR}/flaky.json"

PARALLEL_FLAG=""
if [[ "${1:-}" == "--parallel" ]]; then
  PARALLEL_FLAG="-n auto"
fi

STATUS="completed"

{
  echo "[quality] Running full pytest suite..."
  "${PYTHON_BIN}" -m pytest -q backend/tests --junitxml="${OUT_DIR}/junit.xml" ${PARALLEL_FLAG}
} >"${OUT_DIR}/pytest.log" 2>&1 || STATUS="failed"

{
  echo ""
  echo "=== SECURITY LANE ==="
  "${PYTHON_BIN}" -m pytest -q backend/tests/test_auth_security.py backend/tests/test_release_uat_smoke.py --junitxml="${OUT_DIR}/security_junit.xml"
} >>"${OUT_DIR}/pytest.log" 2>&1 || STATUS="failed"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/build_pytest_summary.py" "${OUT_DIR}/junit.xml" "${OUT_DIR}/summary.json" "${STATUS}"
echo '{"items":[]}' > "${OUT_DIR}/flaky.json"

echo "[quality] Artifacts generated in ${OUT_DIR}"
