"""
Inspectors produce structured data that is merged into the inspection snapshot.
Each inspector receives host_root and an executor; returns a section for the snapshot.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..executor import Executor, make_executor
from ..schema import InspectionSnapshot, OsRelease

from .rpm import run as run_rpm
from .config import run as run_config
from .service import run as run_service
from .network import run as run_network
from .storage import run as run_storage
from .scheduled_tasks import run as run_scheduled_tasks
from .container import run as run_container
from .non_rpm_software import run as run_non_rpm_software
from .kernel_boot import run as run_kernel_boot
from .selinux import run as run_selinux
from .users_groups import run as run_users_groups


def _tool_root() -> Path:
    """Project root (where manifests/ lives)."""
    # From .../src/rhel2bootc/inspectors/__init__.py -> .../ (project root)
    return Path(__file__).resolve().parent.parent.parent.parent


def _read_os_release(host_root: Path) -> Optional[OsRelease]:
    p = host_root / "etc" / "os-release"
    if not p.exists():
        return None
    data = {}
    for line in p.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k] = v.strip().strip('"')
    return OsRelease(
        name=data.get("NAME", ""),
        version_id=data.get("VERSION_ID", ""),
        version=data.get("VERSION", ""),
        id=data.get("ID", ""),
        id_like=data.get("ID_LIKE", ""),
        pretty_name=data.get("PRETTY_NAME", ""),
    )


def _validate_supported_host(os_release: Optional[OsRelease], tool_root: Path) -> Optional[str]:
    """Return error message if host is not supported, else None."""
    if not os_release or not os_release.version_id:
        return None
    vid = os_release.version_id
    if os_release.id == "rhel":
        if vid not in ("9.6", "9.7"):
            return (
                f"Host is running RHEL {vid}. This version of rhel2bootc only supports "
                "RHEL 9.6, RHEL 9.7, and CentOS Stream 9."
            )
        manifest = tool_root / "manifests" / "rhel" / vid / "minimal.json"
    elif "centos" in os_release.id.lower():
        if vid != "9":
            return (
                f"Host is running CentOS {vid}. This version of rhel2bootc only supports "
                "CentOS Stream 9."
            )
        manifest = tool_root / "manifests" / "centos-stream" / vid / "minimal.json"
    else:
        return None
    if not manifest.exists():
        return (
            f"No baseline manifest for {os_release.id} {vid}. "
            "rhel2bootc requires manifests/<distro>/<version>/minimal.json."
        )
    return None


def _profile_warning(host_root: Path) -> Optional[str]:
    """If install profile could not be determined, return warning message."""
    for p in ("root/anaconda-ks.cfg", "root/original-ks.cfg"):
        if (host_root / p).exists():
            return None
    anaconda = host_root / "var/log/anaconda"
    if anaconda.exists() and any(anaconda.iterdir()):
        return None
    return (
        "Could not determine original install profile. Using 'minimal' baseline. "
        "Some packages reported as 'added' may have been part of the original installation."
    )


def run_all(
    host_root: Path,
    executor: Optional[Executor] = None,
    tool_root: Optional[Path] = None,
    config_diffs: bool = False,
    deep_binary_scan: bool = False,
    query_podman: bool = False,
) -> InspectionSnapshot:
    """Run all inspectors and return a merged snapshot."""
    host_root = Path(host_root)
    if executor is None:
        executor = make_executor(str(host_root))
    if tool_root is None:
        tool_root = _tool_root()

    meta = {"host_root": str(host_root), "timestamp": datetime.utcnow().isoformat() + "Z"}
    hostname_path = host_root / "etc" / "hostname"
    if hostname_path.exists():
        try:
            meta["hostname"] = hostname_path.read_text().strip().splitlines()[0]
        except Exception:
            pass
    os_release = _read_os_release(host_root)
    err = _validate_supported_host(os_release, tool_root)
    if err:
        raise ValueError(err)
    snapshot = InspectionSnapshot(
        meta=meta,
        os_release=os_release,
    )
    profile_warn = _profile_warning(host_root)
    if profile_warn:
        snapshot.warnings.append({"source": "rpm", "message": profile_warn, "severity": "warning"})

    snapshot.rpm = run_rpm(host_root, executor, tool_root)
    snapshot.config = run_config(
        host_root,
        executor,
        rpm_section=snapshot.rpm,
        rpm_owned_paths_override=None,
        config_diffs=config_diffs,
    )
    snapshot.services = run_service(host_root, executor, tool_root)
    snapshot.network = run_network(host_root, executor)
    snapshot.storage = run_storage(host_root, executor)
    snapshot.scheduled_tasks = run_scheduled_tasks(host_root, executor)
    snapshot.containers = run_container(host_root, executor, query_podman=query_podman)
    snapshot.non_rpm_software = run_non_rpm_software(host_root, executor, deep_binary_scan=deep_binary_scan)
    snapshot.kernel_boot = run_kernel_boot(host_root, executor)
    snapshot.selinux = run_selinux(host_root, executor)
    snapshot.users_groups = run_users_groups(host_root, executor)

    return snapshot
