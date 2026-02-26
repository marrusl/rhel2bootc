"""SELinux/Security inspector: mode, modules, booleans, audit rules, FIPS, PAM. File-based + executor."""

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import SelinuxSection


def _safe_iterdir(d: Path) -> List[Path]:
    try:
        return list(d.iterdir())
    except (PermissionError, OSError):
        return []


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> SelinuxSection:
    section = SelinuxSection()
    host_root = Path(host_root)

    selinux_config = host_root / "etc/selinux/config"
    try:
        if selinux_config.exists():
            for line in selinux_config.read_text().splitlines():
                line = line.strip()
                if line.startswith("SELINUX="):
                    section.mode = line.split("=", 1)[1].strip()
                    break
    except (PermissionError, OSError):
        pass

    if executor:
        try:
            out = executor(["getsebool", "-a"])
            if out.returncode == 0 and out.stdout:
                for line in out.stdout.splitlines():
                    if " --> on" in line or " --> off" in line:
                        section.boolean_overrides.append({"raw": line.strip()})
        except Exception:
            pass

    audit_d = host_root / "etc/audit/rules.d"
    if audit_d.exists():
        for f in _safe_iterdir(audit_d):
            if f.is_file():
                section.audit_rules.append(str(f.relative_to(host_root)))

    fips_path = host_root / "proc/sys/crypto/fips_enabled"
    try:
        if fips_path.exists():
            section.fips_mode = fips_path.read_text().strip() == "1"
    except (PermissionError, OSError):
        pass

    pam_d = host_root / "etc/pam.d"
    if pam_d.exists():
        for f in _safe_iterdir(pam_d):
            if f.is_file():
                section.pam_configs.append(str(f.relative_to(host_root)))

    return section
