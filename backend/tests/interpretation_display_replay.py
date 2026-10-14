"""Invoke installed frontend display functions locally, with ephemeral inputs."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def attach_display(cases, results):
    root = Path(__file__).resolve().parents[2]
    selected = [r for r in results if r.get("final") and any(
        s["stage"] == "api_postprocessing" for s in r.get("stages", []))]
    if not selected:
        return
    executable = root / "node_modules/.bin/vitest"
    if not executable.exists():
        for row in selected:
            row.update(status="INFRA_BLOCKED", display={"reason": "Installed Vitest is unavailable"})
        return
    with tempfile.TemporaryDirectory(prefix="simons-replay-display-") as temporary:
        input_path, output_path = Path(temporary) / "input.json", Path(temporary) / "output.json"
        input_path.write_text(json.dumps({"cases": cases, "results": selected}), encoding="utf-8")
        try:
            process = subprocess.run([str(executable), "run", "tests/interpretationReplayDisplay.test.ts"],
                cwd=root, env={**os.environ, "QA_REPLAY_INPUT": str(input_path),
                               "QA_REPLAY_OUTPUT": str(output_path)},
                capture_output=True, text=True, timeout=60)
            rendered = json.loads(output_path.read_text())
            by_id = {row["case_id"]: row for row in rendered}
            for row in selected:
                evidence = by_id[row["case_id"]]
                row["display"] = evidence
                if evidence["status"] != "PASS":
                    row["status"] = evidence["status"]
                elif process.returncode:
                    row["status"] = "HARNESS_INVALID"
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
            for row in selected:
                row.update(status="INFRA_BLOCKED", display={"reason": type(exc).__name__})
