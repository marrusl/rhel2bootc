"""
End-to-end integration tests: fixtures → inspectors → serialize → deserialize → renderers.

Test 1: Full pipeline with all fixtures; verify every output file is written and non-empty.
Test 2: Load snapshot via --from-snapshot path and run only renderers; verify identical output.
"""

import tempfile
from pathlib import Path
from typing import Optional

from rhel2bootc.executor import Executor, RunResult
from rhel2bootc.inspectors import run_all as run_all_inspectors
from rhel2bootc.pipeline import load_snapshot, save_snapshot
from rhel2bootc.redact import redact_snapshot
from rhel2bootc.renderers import run_all as run_all_renderers

FIXTURES = Path(__file__).parent / "fixtures"
TOOL_ROOT = Path(__file__).parent.parent

# Every file/dir the renderers produce (used by both tests)
EXPECTED_OUTPUT_FILES = [
    "Containerfile",
    "audit-report.md",
    "report.html",
    "README.md",
    "secrets-review.md",
    "kickstart-suggestion.ks",
]
EXPECTED_OUTPUT_DIRS = ["config"]
SNAPSHOT_FILENAME = "inspection-snapshot.json"


def _fixture_executor(cmd, cwd=None):
    """Executor that returns fixture file content for known commands (same as test_inspectors)."""
    if "rpm" in cmd and "-qa" in cmd:
        return RunResult(stdout=(FIXTURES / "rpm_qa_output.txt").read_text(), stderr="", returncode=0)
    if "rpm" in cmd and "-Va" in cmd:
        return RunResult(stdout=(FIXTURES / "rpm_va_output.txt").read_text(), stderr="", returncode=0)
    if "dnf" in cmd and "history" in cmd and "list" in cmd:
        return RunResult(stdout=(FIXTURES / "dnf_history_list.txt").read_text(), stderr="", returncode=0)
    if "dnf" in cmd and "history" in cmd and "info" in cmd and "4" in cmd:
        return RunResult(stdout=(FIXTURES / "dnf_history_info_4.txt").read_text(), stderr="", returncode=0)
    if "rpm" in cmd and "-ql" in cmd:
        return RunResult(stdout=(FIXTURES / "rpm_qla_output.txt").read_text(), stderr="", returncode=0)
    if "systemctl" in cmd and "list-unit-files" in cmd:
        return RunResult(stdout=(FIXTURES / "systemctl_list_unit_files.txt").read_text(), stderr="", returncode=0)
    return RunResult(stdout="", stderr="unknown command", returncode=1)


def _run_full_pipeline(output_dir: Path, comps_file: Optional[Path] = None) -> Path:
    """Run all inspectors (with fixtures), redact, save snapshot, run renderers. Returns path to snapshot."""
    host_root = FIXTURES / "host_etc"
    executor: Executor = _fixture_executor
    snapshot = run_all_inspectors(
        host_root,
        executor=executor,
        tool_root=TOOL_ROOT,
        config_diffs=False,
        deep_binary_scan=False,
        query_podman=False,
        comps_file=comps_file,
    )
    snapshot = redact_snapshot(snapshot)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / SNAPSHOT_FILENAME
    save_snapshot(snapshot, snapshot_path)
    run_all_renderers(snapshot, output_dir)
    return snapshot_path


def _verify_all_output_files_written_and_non_empty(output_dir: Path) -> None:
    """Assert every expected file exists and is non-empty; expected dirs exist."""
    for name in EXPECTED_OUTPUT_FILES:
        path = output_dir / name
        assert path.exists(), f"Expected output file missing: {name}"
        content = path.read_text()
        assert len(content.strip()) > 0, f"Expected output file non-empty: {name}"
    for name in EXPECTED_OUTPUT_DIRS:
        path = output_dir / name
        assert path.is_dir(), f"Expected output dir missing: {name}"


def _collect_output_file_paths(output_dir: Path):
    """Yield (relative_path, is_file) for all rendered outputs (files and files under config/)."""
    for name in EXPECTED_OUTPUT_FILES:
        yield name, True
    for name in EXPECTED_OUTPUT_DIRS:
        d = output_dir / name
        if d.is_dir():
            for p in sorted(d.rglob("*")):
                if p.is_file():
                    yield p.relative_to(output_dir).as_posix(), True


def test_full_pipeline_fixtures_end_to_end():
    """
    Run the full pipeline end-to-end with fixture data: load fixtures, run every inspector,
    serialize to snapshot, deserialize, run every renderer. Verify every expected output file
    is written and non-empty.
    """
    host_root = FIXTURES / "host_etc"
    executor: Executor = _fixture_executor
    comps_file = FIXTURES / "comps_minimal.xml"

    # 1. Run all inspectors (with comps for deterministic baseline)
    snapshot = run_all_inspectors(
        host_root,
        executor=executor,
        tool_root=TOOL_ROOT,
        config_diffs=False,
        deep_binary_scan=False,
        query_podman=False,
        comps_file=comps_file,
    )

    # 2. Redact (same as production pipeline)
    snapshot = redact_snapshot(snapshot)

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)

        # 3. Serialize snapshot
        snapshot_path = output_dir / SNAPSHOT_FILENAME
        save_snapshot(snapshot, snapshot_path)
        assert snapshot_path.exists(), "inspection-snapshot.json must be written"
        assert snapshot_path.stat().st_size > 0, "inspection-snapshot.json must be non-empty"

        # 4. Deserialize back
        loaded = load_snapshot(snapshot_path)

        # 5. Run all renderers on the deserialized snapshot
        run_all_renderers(loaded, output_dir)

        # 6. Verify every expected output file is written and non-empty
        _verify_all_output_files_written_and_non_empty(output_dir)


def test_from_snapshot_produces_identical_output():
    """
    Simulate --from-snapshot: run full pipeline once (save snapshot + render), then load
    snapshot from file and run only renderers. Verify the second run produces identical
    output (same files, same contents) as the first.
    """
    comps_file = FIXTURES / "comps_minimal.xml"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dir_first = root / "first"
        dir_second = root / "second"

        # 1. Full pipeline → snapshot + render to dir_first
        snapshot_path = _run_full_pipeline(dir_first, comps_file=comps_file)
        _verify_all_output_files_written_and_non_empty(dir_first)

        # 2. Load snapshot from file (--from-snapshot), run only renderers → dir_second
        loaded = load_snapshot(snapshot_path)
        loaded = redact_snapshot(loaded)
        dir_second.mkdir(parents=True, exist_ok=True)
        run_all_renderers(loaded, dir_second)

        # 3. Verify same outputs: every rendered file has identical content
        for rel_path, _ in _collect_output_file_paths(dir_first):
            p1 = dir_first / rel_path
            p2 = dir_second / rel_path
            assert p1.is_file(), f"First run missing file: {rel_path}"
            assert p2.exists(), f"Second run (from-snapshot) missing: {rel_path}"
            assert p2.is_file(), f"Second run path not file: {rel_path}"
            c1 = p1.read_text()
            c2 = p2.read_text()
            assert c1 == c2, (
                f"Output differs for {rel_path}: --from-snapshot render must match full pipeline render."
            )

        # Ensure second run also has all expected top-level files and config dir
        _verify_all_output_files_written_and_non_empty(dir_second)
