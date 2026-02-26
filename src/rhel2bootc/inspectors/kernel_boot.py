"""Kernel/Boot inspector: cmdline, grub, sysctl, modules-load.d, modprobe.d, dracut. File-based under host_root."""

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import KernelBootSection


def _safe_iterdir(d: Path) -> List[Path]:
    try:
        return list(d.iterdir())
    except (PermissionError, OSError):
        return []


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> KernelBootSection:
    section = KernelBootSection()
    host_root = Path(host_root)

    try:
        cmdline = host_root / "proc/cmdline"
        if cmdline.exists():
            section.cmdline = cmdline.read_text().strip()
    except (PermissionError, OSError):
        pass

    try:
        grub = host_root / "etc/default/grub"
        if grub.exists():
            section.grub_defaults = grub.read_text().strip()[:500]
    except (PermissionError, OSError):
        pass

    sysctl_d = host_root / "etc/sysctl.d"
    if sysctl_d.exists():
        for f in _safe_iterdir(sysctl_d):
            if f.is_file() and f.suffix in (".conf", ""):
                section.sysctl_overrides.append({"path": str(f.relative_to(host_root))})

    try:
        sysctl_conf = host_root / "etc/sysctl.conf"
        if sysctl_conf.exists():
            text = sysctl_conf.read_text().strip()
            if text and any(line.strip() and not line.strip().startswith("#") for line in text.splitlines()):
                section.sysctl_overrides.append({"path": "etc/sysctl.conf"})
    except (PermissionError, OSError):
        pass

    for dirname, target_list in [
        ("etc/modules-load.d", section.modules_load_d),
        ("etc/modprobe.d", section.modprobe_d),
        ("etc/dracut.conf.d", section.dracut_conf),
    ]:
        d = host_root / dirname
        if d.exists():
            for f in _safe_iterdir(d):
                if f.is_file() and f.suffix == ".conf":
                    target_list.append(str(f.relative_to(host_root)))

    return section
