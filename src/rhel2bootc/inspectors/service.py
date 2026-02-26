"""
Service inspector: systemd unit state vs baseline (enabled/disabled/masked).
Uses executor for systemctl list-unit-files; loads service baseline manifest.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..executor import Executor
from ..schema import ServiceSection, ServiceStateChange


def _load_service_baseline(tool_root: Path, distro: str, version: str, profile: str = "minimal") -> Tuple[Set[str], Set[str]]:
    """Load default_enabled and default_disabled from service baseline JSON."""
    path = tool_root / "manifests" / distro / version / "minimal_services.json"
    if not path.exists():
        return set(), set()
    data = json.loads(path.read_text())
    enabled = set(data.get("default_enabled", []))
    disabled = set(data.get("default_disabled", []))
    return enabled, disabled


def _parse_systemctl_list_unit_files(stdout: str) -> Dict[str, str]:
    """Parse output of systemctl list-unit-files. Returns unit -> state (enabled, disabled, static, etc.)."""
    units = {}
    for line in stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            unit = parts[0]
            state = parts[1]
            units[unit] = state
    return units


def _find_service_baseline_manifest(host_root: Path, tool_root: Optional[Path] = None) -> Optional[Path]:
    """Return path to service baseline manifest (minimal_services.json) for this host."""
    os_release = host_root / "etc" / "os-release"
    if not os_release.exists():
        return None
    id_val = ""
    version_id = ""
    for line in os_release.read_text().splitlines():
        if line.startswith("ID="):
            id_val = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("VERSION_ID="):
            version_id = line.split("=", 1)[1].strip().strip('"')
    if not id_val or not version_id:
        return None
    distro = "rhel" if id_val == "rhel" else "centos-stream"
    if tool_root is None:
        tool_root = Path(__file__).resolve().parent.parent.parent.parent
    path = tool_root / "manifests" / distro / version_id / "minimal_services.json"
    return path if path.exists() else None


def run(
    host_root: Path,
    executor: Optional[Executor],
    tool_root: Optional[Path] = None,
) -> ServiceSection:
    """
    Run Service inspection. If executor is None, returns empty section (use fixture for tests).
    """
    host_root = Path(host_root)
    section = ServiceSection()

    if executor is None:
        return section

    # Get current unit state
    # systemctl list-unit-files --root /host (or run from host)
    cmd = ["systemctl", "list-unit-files", "--no-pager", "--no-legend"]
    # When inspecting container host we might need systemctl --root /host
    if str(host_root) != "/":
        cmd = ["systemctl", "--root", str(host_root), "list-unit-files", "--no-pager", "--no-legend"]
    result = executor(cmd)
    if result.returncode != 0:
        return section

    current = _parse_systemctl_list_unit_files(result.stdout)
    baseline_path = _find_service_baseline_manifest(host_root, tool_root)
    default_enabled: Set[str] = set()
    default_disabled: Set[str] = set()
    if baseline_path:
        data = json.loads(baseline_path.read_text())
        default_enabled = set(data.get("default_enabled", []))
        default_disabled = set(data.get("default_disabled", []))

    for unit, state in current.items():
        if not unit.endswith(".service") and not unit.endswith(".timer"):
            continue
        default_state = "enabled" if unit in default_enabled else ("disabled" if unit in default_disabled else "unknown")
        action = "unchanged"
        if state == "enabled" and unit not in default_enabled:
            action = "enable"
            section.enabled_units.append(unit)
        elif state == "disabled" and unit in default_enabled:
            action = "disable"
            section.disabled_units.append(unit)
        elif state == "masked":
            action = "mask"
        section.state_changes.append(
            ServiceStateChange(
                unit=unit,
                current_state=state,
                default_state=default_state,
                action=action,
            )
        )

    return section
