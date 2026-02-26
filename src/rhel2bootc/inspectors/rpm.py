"""
RPM inspector: package list, rpm -Va, repo files, dnf history removed.
Uses executor for all commands; reads repo files under host_root.
"""

import re
from pathlib import Path
from typing import Any, Callable, List, Optional, Set

from ..executor import Executor, RunResult
from ..schema import (
    PackageEntry,
    PackageState,
    RepoFile,
    RpmSection,
    RpmVaEntry,
)


RPM_QA_QUERYFORMAT = r"%{EPOCH}:%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}"


def _parse_nevr(nevra: str) -> Optional[PackageEntry]:
    """Parse a single NEVRA line from rpm -qa --queryformat."""
    # Format: epoch:name-version-release.arch (name can contain hyphens, e.g. audit-libs)
    s = nevra.strip()
    if ":" not in s:
        return None
    epoch_part, rest = s.split(":", 1)
    if not epoch_part.isdigit():
        return None
    # rest = name-version-release.arch
    if "." not in rest:
        return None
    base, arch = rest.rsplit(".", 1)
    parts = base.split("-")
    if len(parts) < 3:
        return None
    # release is last (e.g. 104.el9), version is second-to-last (e.g. 3.0.7), name is the rest
    release = parts[-1]
    version = parts[-2]
    name = "-".join(parts[:-2])
    return PackageEntry(
        name=name,
        epoch=epoch_part,
        version=version,
        release=release,
        arch=arch,
        state=PackageState.ADDED,
    )


def _parse_rpm_qa(stdout: str) -> List[PackageEntry]:
    packages = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        pkg = _parse_nevr(line)
        if pkg:
            packages.append(pkg)
    return packages


def _parse_rpm_va(stdout: str) -> List[RpmVaEntry]:
    """Parse rpm -Va output. Format: flags type path (e.g. S.5....T.  c /etc/foo)."""
    entries = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # First 9 chars are flags (e.g. S.5....T.), then optional whitespace and type (c/d), then path
        if len(line) < 11:
            continue
        flags = line[:9].strip()
        rest = line[9:].lstrip()
        # Rest can be "c /path" or "/path"
        if rest.startswith("c ") or rest.startswith("d "):
            path = rest[2:].strip()
        else:
            path = rest.strip()
        if path:
            entries.append(RpmVaEntry(path=path, flags=flags, package=None))
    return entries


def _load_baseline_packages(manifest_path: Path) -> Set[str]:
    """Load package names from a baseline manifest JSON."""
    import json
    data = json.loads(manifest_path.read_text())
    return set(data.get("packages", []))


def _find_baseline_manifest(host_root: Path, tool_root: Optional[Path] = None) -> Optional[Path]:
    """Resolve os-release from host and return path to baseline manifest if we have one."""
    os_release = host_root / "etc" / "os-release"
    if not os_release.exists():
        return None
    # Parse ID and VERSION_ID
    id_val = ""
    version_id = ""
    for line in os_release.read_text().splitlines():
        if line.startswith("ID="):
            id_val = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("VERSION_ID="):
            version_id = line.split("=", 1)[1].strip().strip('"')
    if not id_val or not version_id:
        return None
    # Map to manifest path: rhel -> rhel, centos stream -> centos-stream
    if id_val == "rhel":
        distro = "rhel"
    elif "centos" in id_val.lower():
        distro = "centos-stream"
    else:
        return None
    # Tool root: directory containing manifests (e.g. project root or /app in container)
    if tool_root is None:
        tool_root = Path(__file__).resolve().parent.parent.parent.parent
    manifest = tool_root / "manifests" / distro / version_id / "minimal.json"
    if manifest.exists():
        return manifest
    return None


def _collect_repo_files(host_root: Path) -> List[RepoFile]:
    """Read repo files from host_root/etc/yum.repos.d and host_root/etc/dnf."""
    repo_files = []
    for subdir in ("etc/yum.repos.d", "etc/dnf"):
        d = host_root / subdir
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and (f.suffix in (".repo", ".conf") or subdir == "etc/dnf"):
                try:
                    content = f.read_text()
                except Exception:
                    content = ""
                repo_files.append(RepoFile(path=str(f.relative_to(host_root)), content=content))
    return repo_files


def _dnf_history_removed(executor: Executor, host_root: Path) -> List[str]:
    """Run dnf history and collect package names from Remove transactions."""
    # In real run: dnf history list --installroot /host, then for each Remove: dnf history info N
    result = executor(["dnf", "history", "list", "-q"], cwd=str(host_root))
    if result.returncode != 0:
        return []
    removed = []
    # Parse "     N | ... | Removed | M" and get transaction IDs for Removed
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) >= 4 and "Removed" in (parts[3].strip() if len(parts) > 3 else ""):
            try:
                tid = int(parts[0].strip())
            except ValueError:
                continue
            info_result = executor(["dnf", "history", "info", str(tid), "-q"], cwd=str(host_root))
            if info_result.returncode != 0:
                continue
            # Parse "Removed     pkg-name-ver-rel.arch"
            for iline in info_result.stdout.splitlines():
                if "Removed" in iline:
                    # Line like "    Removed     old-daemon-1.0-3.el9.x86_64"
                    pkg_part = iline.split("Removed", 1)[-1].strip().split()
                    if pkg_part:
                        # Take first word and strip version: old-daemon-1.0-3.el9.x86_64 -> old-daemon
                        nevra = pkg_part[0]
                        name = re.match(r"^([^-]+(?:-[^-]+)*?)-\d", nevra)
                        if name:
                            removed.append(name.group(1))
                        else:
                            removed.append(nevra.split("-")[0] if "-" in nevra else nevra)
    return removed


def run(
    host_root: Path,
    executor: Optional[Executor],
    tool_root: Optional[Path] = None,
) -> RpmSection:
    """
    Run RPM inspection. If executor is None, only repo files from host_root are collected
    (caller uses fixture data for rpm/dnf commands).
    """
    host_root = Path(host_root)
    section = RpmSection()

    # 1) rpm -qa
    if executor is not None:
        cmd_qa = ["rpm", "-qa", "--queryformat", RPM_QA_QUERYFORMAT + "\\n"]
        # With --root for containerized inspection
        if str(host_root) != "/":
            cmd_qa = ["rpm", "--root", str(host_root), "-qa", "--queryformat", RPM_QA_QUERYFORMAT + "\\n"]
        result_qa = executor(cmd_qa)
        installed = _parse_rpm_qa(result_qa.stdout)
    else:
        installed = []

    # 2) Baseline diff (added = installed not in baseline, removed = baseline not installed)
    # packages_modified is for config-modified packages; we fill from rpm_va package resolution if needed
    baseline_path = _find_baseline_manifest(host_root, tool_root)
    if baseline_path and installed:
        baseline_names = _load_baseline_packages(baseline_path)
        installed_names = {p.name for p in installed}
        added_names = installed_names - baseline_names
        removed_names = baseline_names - installed_names
        for p in installed:
            if p.name in added_names:
                p.state = PackageState.ADDED
                section.packages_added.append(p)
        for name in removed_names:
            section.packages_removed.append(
                PackageEntry(name=name, epoch="0", version="", release="", arch="noarch", state=PackageState.REMOVED)
            )
    elif installed:
        for p in installed:
            p.state = PackageState.ADDED
            section.packages_added.append(p)

    # 3) rpm -Va
    if executor is not None:
        cmd_va = ["rpm", "-Va", "--nodeps", "--noscripts"]
        if str(host_root) != "/":
            cmd_va = ["rpm", "--root", str(host_root), "-Va", "--nodeps", "--noscripts"]
        result_va = executor(cmd_va)
        section.rpm_va = _parse_rpm_va(result_va.stdout)
    else:
        section.rpm_va = []

    # 4) Repo files
    section.repo_files = _collect_repo_files(host_root)

    # 5) dnf history removed
    if executor is not None:
        section.dnf_history_removed = _dnf_history_removed(executor, host_root)
    else:
        section.dnf_history_removed = []

    return section
