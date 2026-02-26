"""
Config inspector: RPM-owned modified (from rpm_va), unowned /etc files, orphaned configs.
Uses RPM section from snapshot for rpm_va and dnf_history_removed; executor for rpm -qla; pathlib for /etc.
When config_diffs=True, extracts original from RPM (dnf cache or host) and sets diff_against_rpm.
"""

import difflib
from pathlib import Path
from typing import List, Optional, Set

from ..executor import Executor
from ..schema import ConfigFileEntry, ConfigFileKind, ConfigSection, RpmSection


def _rpm_owned_paths(executor: Optional[Executor], host_root: Path) -> Set[str]:
    """Build set of paths under /etc that are owned by some RPM. Uses rpm -qla style output."""
    if executor is None:
        return set()
    # Get all files from all packages: rpm -qa then rpm -ql each (expensive). Or use --queryformat to get all at once.
    # rpm has no single "list all owned paths". We use: rpm -qa --queryformat '%{NAME}\n' | while read p; do rpm -ql $p; done
    # For fixture we provide a single command that returns a list of paths. So we need executor to support that.
    # Alternative: in real run, we run a script. For fixture, executor returns content of rpm_qla_output.txt.
    cmd = ["rpm", "--root", str(host_root), "-qa", "--queryformat", "%{NAME}\n"]
    result = executor(cmd)
    if result.returncode != 0:
        return set()
    names = [n.strip() for n in result.stdout.strip().splitlines() if n.strip()]
    paths: Set[str] = set()
    for name in names:
        ql = executor(["rpm", "--root", str(host_root), "-ql", name])
        if ql.returncode == 0:
            for line in ql.stdout.strip().splitlines():
                p = line.strip()
                if p.startswith("/etc"):
                    paths.add(p)
    return paths


def _list_etc_recursive(host_root: Path, etc_dir: Path) -> List[Path]:
    """List all files under etc_dir (relative to host_root)."""
    out = []
    try:
        for p in etc_dir.rglob("*"):
            if p.is_file():
                out.append(p)
    except Exception:
        pass
    return out


def _get_owning_package(executor: Executor, host_root: Path, path: str) -> Optional[str]:
    """Return package name owning path, or None."""
    if not executor:
        return None
    r = executor(["rpm", "--root", str(host_root), "-qf", path])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.strip().splitlines()[0].strip()


def _find_rpm_in_cache(host_root: Path, package_name: str) -> Optional[Path]:
    """Find RPM file in /var/cache/dnf for the given package name (exact name match)."""
    cache = host_root / "var" / "cache" / "dnf"
    if not cache.exists():
        return None
    prefix = package_name + "-"
    for rpm in cache.rglob("*.rpm"):
        if rpm.name.startswith(prefix) and len(rpm.name) > len(prefix) and rpm.name[len(prefix)].isdigit():
            return rpm
    return None


def _extract_file_from_rpm(executor: Executor, rpm_path: Path, path_in_rpm: str) -> Optional[str]:
    """Extract a single file from RPM via rpm2cpio | cpio. path_in_rpm is e.g. etc/httpd/conf/httpd.conf."""
    if not executor:
        return None
    # Run on host: rpm2cpio and cpio must read the RPM (path may be under /host)
    cmd = ["sh", "-c", f"rpm2cpio {rpm_path!s} | cpio -i --to-stdout {path_in_rpm!s} 2>/dev/null"]
    r = executor(cmd)
    if r.returncode != 0:
        return None
    return r.stdout


def _unified_diff(original: str, current: str, path: str) -> str:
    """Produce unified diff string."""
    a = original.splitlines(keepends=True) or [""]
    b = current.splitlines(keepends=True) or [""]
    return "".join(
        difflib.unified_diff(a, b, fromfile="rpm", tofile="current", lineterm="")
    )


def run(
    host_root: Path,
    executor: Optional[Executor],
    rpm_section: Optional[RpmSection] = None,
    rpm_owned_paths_override: Optional[Set[str]] = None,
    config_diffs: bool = False,
) -> ConfigSection:
    """
    Run Config inspection. Requires rpm_section for rpm_va and dnf_history_removed.
    If rpm_owned_paths_override is provided (e.g. from tests), use it; else compute via executor.
    """
    host_root = Path(host_root)
    section = ConfigSection()
    etc = host_root / "etc"
    if not etc.exists():
        return section

    rpm_va_paths: Set[str] = set()
    if rpm_section:
        for entry in rpm_section.rpm_va:
            if entry.path.startswith("/etc"):
                rpm_va_paths.add(entry.path)
        rpm_va_by_path = {e.path: e for e in rpm_section.rpm_va}
    else:
        rpm_va_by_path = {}

    # 1) RPM-owned modified files (from rpm_va)
    for path, entry in rpm_va_by_path.items():
        full = host_root / path.lstrip("/")
        if not full.exists():
            continue
        try:
            content = full.read_text()
        except Exception:
            content = ""
        diff_against_rpm = None
        if config_diffs and executor:
            pkg = _get_owning_package(executor, host_root, path) or entry.package
            rpm_path = _find_rpm_in_cache(host_root, pkg) if pkg else None
            path_in_rpm = path.lstrip("/")
            if rpm_path:
                original = _extract_file_from_rpm(executor, rpm_path, path_in_rpm)
                if original is not None:
                    diff_against_rpm = _unified_diff(original, content, path)
                else:
                    content = (content or "") + "\n# NOTE: could not retrieve RPM default for diff — full file included\n"
            else:
                content = (content or "") + "\n# NOTE: could not retrieve RPM default for diff — full file included\n"
        section.files.append(
            ConfigFileEntry(
                path=path,
                kind=ConfigFileKind.RPM_OWNED_MODIFIED,
                content=content,
                rpm_va_flags=entry.flags,
                package=entry.package,
                diff_against_rpm=diff_against_rpm,
            )
        )

    # 2) Unowned files: in /etc but not in rpm_owned_paths
    if rpm_owned_paths_override is not None:
        rpm_owned = rpm_owned_paths_override
    else:
        rpm_owned = _rpm_owned_paths(executor, host_root)
    all_etc_files = _list_etc_recursive(host_root, etc)
    for f in all_etc_files:
        try:
            rel = f.relative_to(host_root)
            path_str = "/" + str(rel)
        except ValueError:
            continue
        if path_str in rpm_va_paths:
            continue  # already in modified
        if path_str in rpm_owned:
            continue
        try:
            content = f.read_text()
        except Exception:
            content = ""
        section.files.append(
            ConfigFileEntry(
                path=path_str,
                kind=ConfigFileKind.UNOWNED,
                content=content,
                rpm_va_flags=None,
                package=None,
                diff_against_rpm=None,
            )
        )

    # 3) Orphaned: configs from removed packages (dnf history). We'd need to know which paths belonged to removed pkgs.
    # Without rpm -ql for removed packages we can't easily list orphaned paths. Skip for now.
    return section
