import subprocess, sys, os
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_safety_gate_downgrades():
    p = subprocess.run(
        [sys.executable, "-m", "core.orchestrator",
         "--tickers", "600519.SS", "--date", "2026-07-17",
         "--mode", "live", "--force"],
        cwd=PROJ, capture_output=True, text=True, timeout=90,
    )
    assert "[SAFETY]" in (p.stdout + p.stderr)
    assert "dry_run" in p.stdout
