"""Tests for baseline generation (base image query)."""

from pathlib import Path

import pytest

from yoinkc.baseline import (
    select_base_image,
    load_baseline_packages_file,
    get_baseline_packages,
)
from yoinkc.executor import RunResult


FIXTURES = Path(__file__).parent / "fixtures"


def test_select_base_image_rhel9():
    assert select_base_image("rhel", "9.4") == "registry.redhat.io/rhel9/rhel-bootc:9.4"


def test_select_base_image_centos_stream9():
    assert select_base_image("centos", "9") == "quay.io/centos-bootc/centos-bootc:stream9"


def test_select_base_image_unknown():
    assert select_base_image("fedora", "40") is None


def test_load_baseline_packages_file():
    path = FIXTURES / "base_image_packages.txt"
    names = load_baseline_packages_file(path)
    assert names is not None
    assert "bash" in names
    assert "glibc" in names
    assert len(names) > 10


def test_load_baseline_packages_file_missing(tmp_path):
    assert load_baseline_packages_file(tmp_path / "nope.txt") is None


def test_get_baseline_with_file():
    """--baseline-packages FILE loads the file directly, no podman needed."""
    host_root = FIXTURES / "host_etc"
    names, base_image, no_baseline = get_baseline_packages(
        host_root, "centos", "9",
        baseline_packages_file=FIXTURES / "base_image_packages.txt",
    )
    assert no_baseline is False
    assert names is not None
    assert "bash" in names
    assert base_image == "quay.io/centos-bootc/centos-bootc:stream9"


def test_get_baseline_with_podman():
    """When executor is provided, podman is called to query the base image."""
    host_root = FIXTURES / "host_etc"
    pkg_list = (FIXTURES / "base_image_packages.txt").read_text()

    def mock_executor(cmd, cwd=None):
        if "podman" in cmd and "rpm" in cmd:
            return RunResult(stdout=pkg_list, stderr="", returncode=0)
        return RunResult(stdout="", stderr="", returncode=1)

    names, base_image, no_baseline = get_baseline_packages(
        host_root, "centos", "9",
        executor=mock_executor,
    )
    assert no_baseline is False
    assert names is not None
    assert "bash" in names
    assert "glibc" in names


def test_get_baseline_no_podman_no_file():
    """Without executor or file, falls back to no-baseline mode."""
    host_root = FIXTURES / "host_etc"
    names, base_image, no_baseline = get_baseline_packages(
        host_root, "centos", "9",
    )
    assert no_baseline is True


def test_get_baseline_podman_fails():
    """When podman fails, falls back to no-baseline mode."""
    host_root = FIXTURES / "host_etc"

    def mock_executor(cmd, cwd=None):
        return RunResult(stdout="", stderr="Error: ...", returncode=125)

    names, base_image, no_baseline = get_baseline_packages(
        host_root, "centos", "9",
        executor=mock_executor,
    )
    assert no_baseline is True
    assert base_image == "quay.io/centos-bootc/centos-bootc:stream9"
