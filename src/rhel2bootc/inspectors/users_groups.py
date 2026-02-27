"""User/Group inspector: non-system users and groups, sudoers, SSH key refs. Parses passwd/group under host_root."""

import os
import sys
from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import UserGroupSection

_DEBUG = bool(os.environ.get("RHEL2BOOTC_DEBUG", ""))


def _debug(msg: str) -> None:
    if _DEBUG:
        print(f"[rhel2bootc] users: {msg}", file=sys.stderr)


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

    passwd_path = host_root / "etc/passwd"
    _debug(f"checking {passwd_path}")
    passwd_text = None
    try:
        if passwd_path.exists():
            passwd_text = passwd_path.read_text()
            _debug(f"read {passwd_path} ({len(passwd_text)} bytes, {len(passwd_text.splitlines())} lines)")
        else:
            _debug(f"{passwd_path} does not exist")
    except (PermissionError, OSError) as exc:
        _debug(f"cannot read {passwd_path}: {exc}")

    if passwd_text:
        for line in passwd_text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(":")
                if len(parts) >= 7:
                    try:
                        uid = int(parts[2])
                        if uid >= 1000:
                            _debug(f"found user: {parts[0]} uid={uid} home={parts[5]} shell={parts[6]}")
                            section.users.append({
                                "name": parts[0],
                                "uid": uid,
                                "gid": int(parts[3]) if parts[3].isdigit() else None,
                                "shell": parts[6],
                                "home": parts[5],
                            })
                    except ValueError:
                        pass

    _debug(f"found {len(section.users)} non-system users (uid >= 1000)")

    group_path = host_root / "etc/group"
    _debug(f"checking {group_path}")
    group_text = None
    try:
        if group_path.exists():
            group_text = group_path.read_text()
            _debug(f"read {group_path} ({len(group_text)} bytes)")
        else:
            _debug(f"{group_path} does not exist")
    except (PermissionError, OSError) as exc:
        _debug(f"cannot read {group_path}: {exc}")

    if group_text:
        for line in group_text.splitlines():
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

    _debug(f"found {len(section.groups)} non-system groups (gid >= 1000)")

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
