"""Non-RPM Software inspector: /opt, /usr/local, pip/npm/gem. File-based scan. Optional deep strings scan."""

import re
from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import NonRpmSoftwareSection

VERSION_PATTERNS = [
    re.compile(rb"version\s*[=:]\s*[\"']?([0-9]+\.[0-9]+(?:\.[0-9]+)?)", re.I),
    re.compile(rb"v([0-9]+\.[0-9]+(?:\.[0-9]+)?)[\s\-]"),
    re.compile(rb"([0-9]+\.[0-9]+\.[0-9]+)(?:\s|$|\))"),
]


def _is_binary(executor: Optional[Executor], host_root: Path, path: Path) -> bool:
    if not executor:
        return False
    r = executor(["file", "-b", str(path)])
    if r.returncode != 0:
        return False
    out = r.stdout.lower()
    return "elf" in out or "executable" in out or "script" in out


def _strings_version(executor: Optional[Executor], path: Path, limit_kb: Optional[int] = None) -> Optional[str]:
    """Run strings on path and return first version-like match. If limit_kb set, only first N KB of binary (fast pass)."""
    if not executor:
        return None
    if limit_kb:
        cmd = ["sh", "-c", f"head -c {limit_kb * 1024} {path!s} | strings"]
    else:
        cmd = ["strings", str(path)]
    r = executor(cmd)
    if r.returncode != 0:
        return None
    data = r.stdout.encode() if isinstance(r.stdout, str) else r.stdout
    for pat in VERSION_PATTERNS:
        m = pat.search(data)
        if m:
            return m.group(1).decode("utf-8", errors="replace").strip()
    return None


def run(
    host_root: Path,
    executor: Optional[Executor],
    deep_binary_scan: bool = False,
) -> NonRpmSoftwareSection:
    section = NonRpmSoftwareSection()
    host_root = Path(host_root)
    for base in ("opt", "usr/local"):
        d = host_root / base
        if not d.exists():
            continue
        for entry in d.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                item = {"path": str(entry.relative_to(host_root)), "name": entry.name, "confidence": "low"}
                if executor and (deep_binary_scan or True):
                    try:
                        for f in entry.rglob("*"):
                            if not f.is_file():
                                continue
                            if _is_binary(executor, host_root, f):
                                limit = None if deep_binary_scan else 4
                                ver = _strings_version(executor, f, limit_kb=limit)
                                if ver:
                                    item["version"] = ver
                                    item["detected_via"] = "strings" if deep_binary_scan else "strings (first 4KB)"
                                    break
                    except Exception:
                        pass
                section.items.append(item)
    return section
