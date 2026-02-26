"""
End-to-end integration test: fixtures → inspectors → serialize → deserialize → renderers → verify outputs.
"""

import tempfile
from pathlib import Path

from rhel2bootc.executor import Executor, RunResult
from rhel2bootc.inspectors import run_all as run_all_inspectors
from rhel2bootc.pipeline import load_snapshot, save_snapshot
from rhel2bootc.redact import redact_snapshot
from rhel2bootc.renderers import run_all as run_all_renderers

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_executor(cmd, cwd=None):
    """Executor that returns fixture file content for known commands (same as test_inspectors)."""
    cmd_str = " ".join(cmd)
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


def test_full_pipeline_serialize_deserialize_render():
    """
    Load test fixtures, run all inspectors, redact, serialize to JSON,
    deserialize back, run all renderers, and verify every output file is written and non-empty.
    """
    host_root = FIXTURES / "host_etc"
    tool_root = Path(__file__).parent.parent
    executor: Executor = _fixture_executor

    # 1. Run all inspectors
    snapshot = run_all_inspectors(
        host_root,
        executor=executor,
        tool_root=tool_root,
        config_diffs=False,
        deep_binary_scan=False,
        query_podman=False,
    )

    # 2. Redact (same as production pipeline)
    snapshot = redact_snapshot(snapshot)

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)

        # 3. Serialize snapshot to JSON
        snapshot_path = output_dir / "inspection-snapshot.json"
        save_snapshot(snapshot, snapshot_path)
        assert snapshot_path.exists()
        assert snapshot_path.stat().st_size > 0

        # 4. Deserialize back
        loaded = load_snapshot(snapshot_path)

        # 5. Run all renderers on the deserialized snapshot
        run_all_renderers(loaded, output_dir)

        # 6. Verify every expected output file exists and is non-empty
        expected_files = [
            "Containerfile",
            "audit-report.md",
            "report.html",
            "README.md",
            "secrets-review.md",
            "kickstart-suggestion.ks",
        ]
        for name in expected_files:
            path = output_dir / name
            assert path.exists(), f"Expected output file missing: {name}"
            content = path.read_text()
            assert len(content.strip()) > 0, f"Expected output file non-empty: {name}"

        # Optional: config dir may contain written config tree
        config_dir = output_dir / "config"
        assert config_dir.is_dir()
