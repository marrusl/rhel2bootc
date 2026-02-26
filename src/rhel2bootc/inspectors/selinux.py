"""SELinux/Security inspector: mode, modules, booleans, audit rules, PAM. File-based + executor."""

from pathlib import Path
from typing import Optional

from ..executor import Executor
from ..schema import SelinuxSection


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> SelinuxSection:
    section = SelinuxSection()
    host_root = Path(host_root)
    # Custom audit rules
    audit_d = host_root / "etc/audit/rules.d"
    if audit_d.exists():
        for f in audit_d.iterdir():
            if f.is_file():
                section.custom_modules.append(str(f.relative_to(host_root)))
    return section
