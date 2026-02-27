"""SELinux/Security inspector: mode, modules, booleans, audit rules, FIPS, PAM. File-based + executor."""

import re
from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import SelinuxSection


def _safe_iterdir(d: Path) -> List[Path]:
    try:
        return list(d.iterdir())
    except (PermissionError, OSError):
        return []


def _policy_type(host_root: Path) -> str:
    """Read SELINUXTYPE from /etc/selinux/config, default to 'targeted'."""
    cfg = host_root / "etc/selinux/config"
    try:
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                line = line.strip()
                if line.startswith("SELINUXTYPE="):
                    return line.split("=", 1)[1].strip()
    except (PermissionError, OSError):
        pass
    return "targeted"


def _discover_custom_modules(
    host_root: Path, all_modules: List[str], policy_type: str,
) -> List[str]:
    """Cross-reference semodule output with the priority-400 module store.

    Modules at priority 400 were installed locally via ``semodule -i`` and
    are therefore custom.  If the priority-400 directory is unreadable we
    fall back to returning nothing (safe default).
    """
    local_store = (
        host_root / "etc/selinux" / policy_type / "active/modules/400"
    )
    try:
        if not local_store.is_dir():
            return []
    except (PermissionError, OSError):
        return []

    local_names = set()
    for child in _safe_iterdir(local_store):
        if child.is_dir():
            local_names.add(child.name)

    return sorted(m for m in all_modules if m in local_names)


_BOOL_RE = re.compile(
    r"^(\S+)\s+\((\w+)\s*,\s*(\w+)\)\s+(.*)"
)


def _parse_semanage_booleans(text: str) -> List[dict]:
    """Parse ``semanage boolean -l`` output.

    Returns all booleans where current state differs from the default,
    each as ``{"name": ..., "current": ..., "default": ..., "description": ...}``.
    """
    results: List[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("SELinux boolean"):
            continue
        m = _BOOL_RE.match(line)
        if not m:
            continue
        name, current, default, desc = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        results.append({
            "name": name,
            "current": current,
            "default": default,
            "non_default": current != default,
            "description": desc,
        })
    return results


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

    ptype = _policy_type(host_root)

    # --- Custom modules via semodule -l + priority-400 store ---
    if executor:
        try:
            out = executor(["semodule", "-l"])
            if out.returncode == 0 and out.stdout:
                all_modules = [
                    ln.split()[0]
                    for ln in out.stdout.splitlines()
                    if ln.strip()
                ]
                section.custom_modules = _discover_custom_modules(
                    host_root, all_modules, ptype,
                )
        except Exception:
            pass

    # --- Boolean overrides via semanage boolean -l ---
    if executor:
        try:
            out = executor(["semanage", "boolean", "-l"])
            if out.returncode == 0 and out.stdout:
                section.boolean_overrides = _parse_semanage_booleans(out.stdout)
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
