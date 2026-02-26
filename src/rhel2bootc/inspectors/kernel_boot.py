"""Kernel/Boot inspector: cmdline, grub, sysctl, dracut. File-based under host_root."""

from pathlib import Path
from typing import Optional

from ..executor import Executor
from ..schema import KernelBootSection


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> KernelBootSection:
    section = KernelBootSection()
    host_root = Path(host_root)
    cmdline = host_root / "proc/cmdline"
    if cmdline.exists():
        section.cmdline = cmdline.read_text().strip()
    grub = host_root / "etc/default/grub"
    if grub.exists():
        section.grub_defaults = grub.read_text().strip()[:500]
    for f in (host_root / "etc/sysctl.d").iterdir() if (host_root / "etc/sysctl.d").exists() else []:
        if f.is_file() and f.suffix in (".conf", ""):
            section.sysctl_overrides.append({"path": str(f.relative_to(host_root))})
    return section
