"""
Tests verifying every CLI flag is parsed and wired through to behavior.
"""

from pathlib import Path

from rhel2bootc.cli import parse_args


def test_defaults():
    args = parse_args([])
    assert args.host_root == Path("/host")
    assert args.output_dir == Path("./rhel2bootc-output")
    assert args.from_snapshot is None
    assert args.inspect_only is False
    assert args.comps_file is None
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
        "--comps-file", "/tmp/comps.xml",
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
    assert args.comps_file == Path("/tmp/comps.xml")
    assert args.config_diffs is True
    assert args.deep_binary_scan is True
    assert args.query_podman is True
    assert args.validate is True
    assert args.push_to_github == "owner/repo"
    assert args.public is True
    assert args.yes is True


def test_comps_file_reaches_inspectors():
    """--comps-file is parsed and passed through __main__._run_inspectors to run_all."""
    import unittest.mock
    args = parse_args(["--comps-file", "/tmp/comps.xml"])
    assert args.comps_file == Path("/tmp/comps.xml")

    with unittest.mock.patch("rhel2bootc.inspectors.run_all") as mock_run_all:
        mock_run_all.return_value = unittest.mock.MagicMock()
        from rhel2bootc.__main__ import _run_inspectors
        _run_inspectors(Path("/host"), args)
        mock_run_all.assert_called_once()
        call_kwargs = mock_run_all.call_args
        assert call_kwargs.kwargs.get("comps_file") == Path("/tmp/comps.xml") or \
               (len(call_kwargs.args) > 0 and call_kwargs[1].get("comps_file") == Path("/tmp/comps.xml"))
