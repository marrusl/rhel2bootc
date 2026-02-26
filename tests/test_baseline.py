"""Tests for baseline (comps) parsing and resolution."""

from pathlib import Path

import pytest

from rhel2bootc.baseline import (
    parse_comps_xml,
    resolve_baseline_packages,
    detect_profile,
    get_baseline_packages,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_comps_xml():
    xml = (FIXTURES / "comps_minimal.xml").read_text()
    data = parse_comps_xml(xml)
    assert "minimal" in data
    pkgs, groupreqs = data["minimal"]
    assert "acl" in pkgs
    assert "bash" in pkgs
    assert "vim-enhanced" not in pkgs  # optional excluded
    assert groupreqs == []


def test_resolve_baseline_packages():
    xml = (FIXTURES / "comps_minimal.xml").read_text()
    data = parse_comps_xml(xml)
    baseline = resolve_baseline_packages(data, "minimal")
    assert "acl" in baseline
    assert "bash" in baseline
    assert "grep" in baseline
    assert "sed" in baseline


def test_detect_profile_empty_root(tmp_path):
    assert detect_profile(tmp_path) is None


def test_detect_profile_from_kickstart(tmp_path):
    (tmp_path / "root").mkdir(parents=True)
    (tmp_path / "root" / "anaconda-ks.cfg").write_text(
        "# Kickstart\n%packages\n@server\n%end\n"
    )
    assert detect_profile(tmp_path) == "server"


def test_resolve_baseline_packages_recursive_group_chain():
    """Group dependency resolution is recursive: @server -> @minimal -> @core; all packages included."""
    xml = (FIXTURES / "comps_server_core.xml").read_text()
    data = parse_comps_xml(xml)
    baseline = resolve_baseline_packages(data, "server")
    # From server
    assert "openssh-server" in baseline
    assert "httpd" in baseline
    # From minimal (server depends on minimal)
    assert "filesystem" in baseline
    assert "sed" in baseline
    # From core (minimal depends on core)
    assert "glibc" in baseline
    assert "bash" in baseline
    assert "coreutils" in baseline


def test_get_baseline_with_comps_file(host_root=None):
    host_root = host_root or (FIXTURES / "host_etc")
    comps_file = FIXTURES / "comps_minimal.xml"
    baseline_set, profile, no_baseline = get_baseline_packages(
        host_root, "rhel", "9.6", comps_file=comps_file
    )
    assert no_baseline is False
    assert profile == "minimal"
    assert baseline_set is not None
    assert "acl" in baseline_set
    assert "bash" in baseline_set


def test_get_baseline_comps_file_bypasses_network(host_root=None):
    """When --comps-file is provided, fetch_comps_from_repos is not called (no network)."""
    import unittest.mock
    host_root = host_root or (FIXTURES / "host_etc")
    comps_file = FIXTURES / "comps_minimal.xml"
    with unittest.mock.patch("rhel2bootc.baseline.fetch_comps_from_repos") as mock_fetch:
        baseline_set, profile, no_baseline = get_baseline_packages(
            host_root, "rhel", "9.6", comps_file=comps_file
        )
        mock_fetch.assert_not_called()
    assert no_baseline is False
    assert baseline_set is not None
