"""
Tests verifying every CLI flag is parsed and wired through to behavior.
"""

from pathlib import Path

from yoinkc.cli import parse_args


def test_defaults():
    args = parse_args([])
    assert args.host_root == Path("/host")
    assert args.output_dir == Path("./output")
    assert args.from_snapshot is None
    assert args.inspect_only is False
    assert args.baseline_packages is None
    assert args.config_diffs is False
    assert args.deep_binary_scan is False
    assert args.query_podman is False
    assert args.validate is False
    assert args.push_to_github is None
    assert args.public is False
    assert args.yes is False


def test_all_flags_set():
    args = parse_args([
        "--host-root", "/mnt/host",
        "--output-dir", "/tmp/out",
        "--from-snapshot", "/tmp/snap.json",
        "--inspect-only",
        "--baseline-packages", "/tmp/pkgs.txt",
        "--config-diffs",
        "--deep-binary-scan",
        "--query-podman",
        "--validate",
        "--push-to-github", "owner/repo",
        "--public",
        "--yes",
    ])
    assert args.host_root == Path("/mnt/host")
    assert args.output_dir == Path("/tmp/out")
    assert args.from_snapshot == Path("/tmp/snap.json")
    assert args.inspect_only is True
    assert args.baseline_packages == Path("/tmp/pkgs.txt")
    assert args.config_diffs is True
    assert args.deep_binary_scan is True
    assert args.query_podman is True
    assert args.validate is True
    assert args.push_to_github == "owner/repo"
    assert args.public is True
    assert args.yes is True


def test_baseline_packages_reaches_inspectors():
    """--baseline-packages is parsed and passed through __main__._run_inspectors to run_all."""
    import unittest.mock
    args = parse_args(["--baseline-packages", "/tmp/pkgs.txt"])
    assert args.baseline_packages == Path("/tmp/pkgs.txt")

    with unittest.mock.patch("yoinkc.inspectors.run_all") as mock_run_all:
        mock_run_all.return_value = unittest.mock.MagicMock()
        from yoinkc.__main__ import _run_inspectors
        _run_inspectors(Path("/host"), args)
        mock_run_all.assert_called_once()
        call_kwargs = mock_run_all.call_args
        assert call_kwargs.kwargs.get("baseline_packages_file") == Path("/tmp/pkgs.txt")
