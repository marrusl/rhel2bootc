"""User/Group inspector: non-system users and groups. Parses passwd/group under host_root."""

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import UserGroupSection


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> UserGroupSection:
    section = UserGroupSection()
    host_root = Path(host_root)
    passwd = host_root / "etc/passwd"
    if passwd.exists():
        for line in passwd.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(":")
                if len(parts) >= 3:
                    try:
                        uid = int(parts[2])
                        if uid >= 1000:  # non-system
                            section.users.append({"name": parts[0], "uid": uid, "gid": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None})
                    except ValueError:
                        pass
    group = host_root / "etc/group"
    if group.exists():
        for line in group.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(":")
                if len(parts) >= 3:
                    try:
                        gid = int(parts[2])
                        if gid >= 1000:
                            section.groups.append({"name": parts[0], "gid": gid})
                    except ValueError:
                        pass
    return section
