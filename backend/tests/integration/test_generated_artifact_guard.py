import subprocess
from pathlib import Path


def test_generated_artifact_guard_passes_for_clean_repository():
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/check_generated_artifacts.ps1",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[3],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Generated artifact guard passed" in result.stdout


def test_generated_artifact_guard_fails_for_tracked_artifacts(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], check=True, cwd=repo, capture_output=True, text=True)
    generated = repo / "data" / "reports" / "run" / "metadata.json"
    generated.parent.mkdir(parents=True)
    generated.write_text("{}\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-f", "data/reports/run/metadata.json"],
        check=True,
        cwd=repo,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(Path(__file__).resolve().parents[3] / "scripts/check_generated_artifacts.ps1"),
            "-RepositoryRoot",
            str(repo),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Generated artifacts are tracked" in result.stderr
    assert "data/reports/run/metadata.json" in result.stderr
