"""Container inspector: quadlet units, compose files, optional podman query.

Parses Image= from quadlet .container files, image: from compose YAML,
and optionally runs podman inspect for live container details.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..executor import Executor
from ..schema import ContainerSection


def _safe_glob(d: Path, pattern: str) -> List[Path]:
    try:
        return list(d.glob(pattern))
    except (PermissionError, OSError):
        return []


def _safe_rglob(d: Path, pattern: str) -> List[Path]:
    try:
        return list(d.rglob(pattern))
    except (PermissionError, OSError):
        return []


def _safe_read(p: Path) -> str:
    try:
        return p.read_text()
    except (PermissionError, OSError):
        return ""


def _extract_quadlet_image(content: str) -> str:
    """Extract the Image= value from a quadlet .container file."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("Image="):
            return stripped.split("=", 1)[1].strip()
    return ""


def _extract_compose_images(content: str) -> List[Dict[str, str]]:
    """Extract image: fields from a compose YAML without requiring PyYAML.

    Returns a list of {service, image} dicts. Uses simple regex parsing
    to avoid adding a dependency.
    """
    results: List[Dict[str, str]] = []
    lines = content.splitlines()
    current_service = ""
    in_services = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if stripped == "services:" or stripped.startswith("services:"):
            in_services = True
            continue

        if in_services and indent == 2 and stripped.endswith(":") and not stripped.startswith("-"):
            current_service = stripped.rstrip(":")
            continue

        # Top-level key that isn't services — stop looking
        if indent == 0 and ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":")[0].strip()
            if key != "services":
                in_services = False
                continue

        if in_services and current_service:
            m = re.match(r"image:\s*(.+)", stripped)
            if m:
                image_ref = m.group(1).strip().strip("'\"")
                results.append({"service": current_service, "image": image_ref})

    return results


def _parse_podman_inspect(data: List[dict]) -> List[dict]:
    """Normalize podman inspect JSON into our schema format."""
    results: List[dict] = []
    for c in data:
        mounts = []
        for m in (c.get("Mounts") or []):
            mounts.append({
                "type": m.get("Type", ""),
                "source": m.get("Source", ""),
                "destination": m.get("Destination", ""),
                "mode": m.get("Mode", ""),
                "rw": m.get("RW", True),
            })

        net_settings = c.get("NetworkSettings") or {}
        networks = {}
        for net_name, net_info in (net_settings.get("Networks") or {}).items():
            networks[net_name] = {
                "ip": net_info.get("IPAddress", ""),
                "gateway": net_info.get("Gateway", ""),
                "mac": net_info.get("MacAddress", ""),
            }
        ports = net_settings.get("Ports") or {}

        env_list = (c.get("Config") or {}).get("Env") or []

        state = c.get("State") or {}

        results.append({
            "id": c.get("Id", ""),
            "name": c.get("Name", ""),
            "image": c.get("Image", ""),
            "image_id": c.get("ImageID", ""),
            "status": state.get("Status", ""),
            "mounts": mounts,
            "networks": networks,
            "ports": ports,
            "env": env_list,
        })
    return results


def run(
    host_root: Path,
    executor: Optional[Executor],
    query_podman: bool = False,
) -> ContainerSection:
    section = ContainerSection()
    host_root = Path(host_root)

    # --- Quadlet units ---
    for subdir in ("etc/containers/systemd", "usr/share/containers/systemd"):
        d = host_root / subdir
        if d.exists():
            for f in _safe_glob(d, "*.container"):
                content = _safe_read(f)
                image_ref = _extract_quadlet_image(content)
                section.quadlet_units.append({
                    "path": str(f.relative_to(host_root)),
                    "name": f.name,
                    "content": content,
                    "image": image_ref,
                })

    # --- Compose files ---
    for search_dir in ("opt", "srv", "home", "etc"):
        d = host_root / search_dir
        if not d.exists():
            continue
        for pattern in ("docker-compose*.yml", "docker-compose*.yaml",
                        "compose*.yml", "compose*.yaml"):
            for f in _safe_rglob(d, pattern):
                if not f.is_file():
                    continue
                content = _safe_read(f)
                images = _extract_compose_images(content)
                section.compose_files.append({
                    "path": str(f.relative_to(host_root)),
                    "images": images,
                })

    # --- Podman query ---
    if query_podman and executor:
        # podman ps for the container list
        r = executor(["podman", "ps", "-a", "--format", "json"])
        if r.returncode == 0 and r.stdout.strip():
            try:
                ps_data = json.loads(r.stdout)
            except json.JSONDecodeError:
                ps_data = []

            if isinstance(ps_data, list) and ps_data:
                container_ids = [c.get("ID", "") for c in ps_data if c.get("ID")]
                if container_ids:
                    ir = executor(["podman", "inspect"] + container_ids)
                    if ir.returncode == 0 and ir.stdout.strip():
                        try:
                            inspect_data = json.loads(ir.stdout)
                            if isinstance(inspect_data, list):
                                section.running_containers = _parse_podman_inspect(inspect_data)
                        except json.JSONDecodeError:
                            pass

                # Fallback: if inspect failed, use ps data
                if not section.running_containers:
                    for c in ps_data:
                        if isinstance(c, dict):
                            section.running_containers.append({
                                "id": c.get("ID", ""),
                                "name": c.get("Names", [""])[0] if isinstance(c.get("Names"), list) else str(c.get("Names", "")),
                                "image": c.get("Image", ""),
                                "status": c.get("Status", ""),
                            })

    return section
