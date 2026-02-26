"""Container inspector: quadlet units, compose files, optional podman socket query."""

import json
from pathlib import Path
from typing import Any, List, Optional

from ..executor import Executor
from ..schema import ContainerSection


def run(
    host_root: Path,
    executor: Optional[Executor],
    query_podman: bool = False,
) -> ContainerSection:
    section = ContainerSection()
    host_root = Path(host_root)
    for subdir in ("etc/containers/systemd", "usr/share/containers/systemd"):
        d = host_root / subdir
        if d.exists():
            for f in d.glob("*.container"):
                try:
                    content = f.read_text()
                except Exception:
                    content = ""
                section.quadlet_units.append({
                    "path": str(f.relative_to(host_root)),
                    "name": f.name,
                    "content": content,
                })
    for search_dir in ("opt", "srv", "etc"):
        d = host_root / search_dir
        if not d.exists():
            continue
        for f in d.rglob("docker-compose*.yml"):
            if f.is_file():
                section.compose_files.append({"path": str(f.relative_to(host_root))})
        for f in d.rglob("compose*.yaml"):
            if f.is_file():
                section.compose_files.append({"path": str(f.relative_to(host_root))})
    if query_podman and executor:
        r = executor(["podman", "ps", "-a", "--format", "json"])
        if r.returncode == 0 and r.stdout.strip():
            try:
                data = json.loads(r.stdout)
                if isinstance(data, list):
                    for c in data:
                        section.running_containers.append({
                            "id": c.get("ID", ""),
                            "names": c.get("Names", []),
                            "image": c.get("Image", ""),
                            "status": c.get("Status", ""),
                        })
                elif isinstance(data, dict):
                    section.running_containers.append(data)
            except json.JSONDecodeError:
                pass
    return section
