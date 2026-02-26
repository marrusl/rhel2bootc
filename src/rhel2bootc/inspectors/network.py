"""Network inspector: connections, firewall, DNS, proxy, routes, hosts. File-based scan under host_root."""

from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import NetworkSection


def _safe_iterdir(d: Path) -> List[Path]:
    """Return list of entries in d, or empty list on permission/OS error."""
    try:
        return list(d.iterdir())
    except (PermissionError, OSError):
        return []


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> NetworkSection:
    section = NetworkSection()
    host_root = Path(host_root)

    for subdir in ("etc/NetworkManager/system-connections", "etc/sysconfig/network-scripts"):
        d = host_root / subdir
        if not d.exists():
            continue
        for f in _safe_iterdir(d):
            if f.is_file() and not f.name.startswith("."):
                section.connections.append({"path": str(f.relative_to(host_root)), "name": f.name})

    for sub in ("etc/firewalld/zones", "etc/firewalld/services"):
        fd = host_root / sub
        if not fd.exists():
            continue
        for f in _safe_iterdir(fd):
            if f.is_file() and f.suffix == ".xml":
                try:
                    content = f.read_text()
                except (PermissionError, OSError):
                    content = ""
                section.firewall_zones.append({
                    "path": str(f.relative_to(host_root)),
                    "content": content,
                    "name": f.name,
                })

    try:
        r = host_root / "etc/resolv.conf"
        if r.exists():
            section.resolv_provenance = "file"
    except (PermissionError, OSError):
        pass

    hosts = host_root / "etc/hosts"
    try:
        if hosts.exists():
            for line in hosts.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "localhost" not in line.lower():
                    section.hosts_additions.append(line)
    except (PermissionError, OSError):
        pass

    for route_dir in ("etc/sysconfig/network-scripts",):
        rd = host_root / route_dir
        if not rd.exists():
            continue
        for f in _safe_iterdir(rd):
            if f.is_file() and f.name.startswith("route-"):
                section.static_routes.append({"path": str(f.relative_to(host_root)), "name": f.name})
    iproute_d = host_root / "etc/iproute2"
    if iproute_d.exists() and iproute_d.is_dir():
        for f in _safe_iterdir(iproute_d):
            if f.is_file():
                section.static_routes.append({"path": str(f.relative_to(host_root)), "name": f.name})

    for proxy_path in ("etc/environment", "etc/profile.d"):
        pp = host_root / proxy_path
        try:
            if pp.is_file():
                for line in pp.read_text().splitlines():
                    low = line.lower()
                    if any(k in low for k in ("http_proxy", "https_proxy", "no_proxy", "ftp_proxy")):
                        section.proxy.append({"source": proxy_path, "line": line.strip()})
            elif pp.is_dir():
                for f in _safe_iterdir(pp):
                    if f.is_file():
                        try:
                            for line in f.read_text().splitlines():
                                low = line.lower()
                                if any(k in low for k in ("http_proxy", "https_proxy", "no_proxy", "ftp_proxy")):
                                    section.proxy.append({"source": str(f.relative_to(host_root)), "line": line.strip()})
                        except (PermissionError, OSError):
                            pass
        except (PermissionError, OSError):
            pass

    return section
