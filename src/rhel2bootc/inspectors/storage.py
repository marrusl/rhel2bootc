"""Storage inspector: fstab, mount points, LVM. File-based under host_root."""

from pathlib import Path
from typing import Optional

from ..executor import Executor
from ..schema import StorageSection


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> StorageSection:
    section = StorageSection()
    host_root = Path(host_root)
    fstab = host_root / "etc/fstab"
    if fstab.exists():
        for line in fstab.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split()
                if len(parts) >= 3:
                    section.fstab_entries.append(
                        {"device": parts[0], "mount_point": parts[1], "fstype": parts[2]}
                    )
    return section
