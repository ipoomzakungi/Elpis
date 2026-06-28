import subprocess
import sys


def test_run_xau_walk_forward_research_help_works() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_xau_walk_forward_research.py",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "research-only XAU walk-forward" in result.stdout
