"""Network inspector: connections, firewall, DNS, proxy. File-based scan under host_root."""

from pathlib import Path
from typing import Optional

from ..executor import Executor
from ..schema import NetworkSection


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> NetworkSection:
    section = NetworkSection()
    host_root = Path(host_root)
    # Connection files
    for subdir in ("etc/NetworkManager/system-connections", "etc/sysconfig/network-scripts"):
        d = host_root / subdir
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    section.connections.append({"path": str(f.relative_to(host_root)), "name": f.name})
    # Firewalld zones and services (content for COPY)
    for sub in ("etc/firewalld/zones", "etc/firewalld/services"):
        fd = host_root / sub
        if fd.exists():
            for f in fd.iterdir():
                if f.is_file() and f.suffix == ".xml":
                    try:
                        content = f.read_text()
                    except Exception:
                        content = ""
                    section.firewall_zones.append({
                        "path": str(f.relative_to(host_root)),
                        "content": content,
                        "name": f.name,
                    })
    # resolv.conf
    r = host_root / "etc/resolv.conf"
    if r.exists():
        section.resolv_provenance = "file"
    return section
