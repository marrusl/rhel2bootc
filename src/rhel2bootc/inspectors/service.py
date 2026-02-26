"""
Service inspector: systemd unit state vs baseline (enabled/disabled/masked).
Baseline is derived from systemd preset files on the host, not static manifests.
"""

from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from ..executor import Executor
from ..schema import ServiceSection, ServiceStateChange


def _parse_preset_files(host_root: Path) -> Tuple[Set[str], Set[str]]:
    """Parse systemd preset files to determine default-enabled and default-disabled services.

    Reads from /usr/lib/systemd/system-preset/ (vendor) and /etc/systemd/system-preset/ (admin),
    with /etc overriding /usr/lib (higher-priority presets come first).
    """
    default_enabled: Set[str] = set()
    default_disabled: Set[str] = set()
    already_matched: Set[str] = set()

    preset_dirs = [
        host_root / "etc/systemd/system-preset",
        host_root / "usr/lib/systemd/system-preset",
    ]
    all_files = []
    for d in preset_dirs:
        if d.exists():
            try:
                entries = sorted(d.iterdir())
            except (PermissionError, OSError):
                entries = []
            for f in entries:
                if f.is_file() and f.suffix == ".preset":
                    all_files.append(f)

    for preset_file in all_files:
        try:
            for line in preset_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                action = parts[0].lower()
                pattern = parts[1]

                if pattern.endswith("*"):
                    continue

                if pattern in already_matched:
                    continue
                already_matched.add(pattern)

                if action == "enable":
                    default_enabled.add(pattern)
                elif action == "disable":
                    default_disabled.add(pattern)
        except Exception:
            continue

    return default_enabled, default_disabled


def _parse_systemctl_list_unit_files(stdout: str) -> Dict[str, str]:
    """Parse output of systemctl list-unit-files. Returns unit -> state."""
    units = {}
    for line in stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            unit = parts[0]
            state = parts[1]
            units[unit] = state
    return units


def run(
    host_root: Path,
    executor: Optional[Executor],
    tool_root: Optional[Path] = None,
) -> ServiceSection:
    host_root = Path(host_root)
    section = ServiceSection()

    if executor is None:
        return section

    cmd = ["systemctl", "list-unit-files", "--no-pager", "--no-legend"]
    if str(host_root) != "/":
        cmd = ["systemctl", "--root", str(host_root), "list-unit-files", "--no-pager", "--no-legend"]
    result = executor(cmd)
    if result.returncode != 0:
        return section

    current = _parse_systemctl_list_unit_files(result.stdout)
    default_enabled, default_disabled = _parse_preset_files(host_root)

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
