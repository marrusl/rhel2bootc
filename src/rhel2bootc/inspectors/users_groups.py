"""User/Group inspector: non-system users and groups, sudoers, SSH key refs. Parses passwd/group under host_root."""

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import UserGroupSection


def _safe_iterdir(d: Path) -> List[Path]:
    try:
        return sorted(d.iterdir())
    except (PermissionError, OSError):
        return []


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> UserGroupSection:
    section = UserGroupSection()
    host_root = Path(host_root)

    passwd = host_root / "etc/passwd"
    try:
        if not passwd.exists():
            passwd = None
    except (PermissionError, OSError):
        passwd = None
    if passwd:
        for line in passwd.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(":")
                if len(parts) >= 7:
                    try:
                        uid = int(parts[2])
                        if uid >= 1000:
                            section.users.append({
                                "name": parts[0],
                                "uid": uid,
                                "gid": int(parts[3]) if parts[3].isdigit() else None,
                                "shell": parts[6],
                                "home": parts[5],
                            })
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
                            members = parts[3].split(",") if len(parts) > 3 and parts[3] else []
                            section.groups.append({"name": parts[0], "gid": gid, "members": members})
                    except ValueError:
                        pass

    for sudoers_path in ("etc/sudoers", "etc/sudoers.d"):
        sp = host_root / sudoers_path
        if sp.is_file():
            try:
                for line in sp.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("Defaults"):
                        section.sudoers_rules.append(line)
            except Exception:
                pass
        elif sp.is_dir():
            for f in _safe_iterdir(sp):
                if f.is_file() and not f.name.startswith("."):
                    try:
                        for line in f.read_text().splitlines():
                            line = line.strip()
                            if line and not line.startswith("#") and not line.startswith("Defaults"):
                                section.sudoers_rules.append(line)
                    except Exception:
                        pass

    for user_entry in section.users:
        home = user_entry.get("home", "")
        if home:
            auth_keys = host_root / home.lstrip("/") / ".ssh" / "authorized_keys"
            try:
                if auth_keys.exists():
                    section.ssh_authorized_keys_refs.append({
                        "user": user_entry["name"],
                        "path": f"{home}/.ssh/authorized_keys",
                    })
            except (PermissionError, OSError):
                pass

    return section
