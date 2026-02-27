"""kickstart-suggestion.ks renderer: deploy-time settings suggestion."""

from pathlib import Path

from jinja2 import Environment

from ..schema import InspectionSnapshot


def render(
    snapshot: InspectionSnapshot,
    env: Environment,
    output_dir: Path,
) -> None:
    output_dir = Path(output_dir)
    lines = [
        "# Kickstart suggestion — review and adapt for your environment",
        "# These settings belong at deploy time, not baked into the image.",
        "",
    ]

    if snapshot.network:
        dhcp_conns = [c for c in (snapshot.network.connections or []) if c.get("method") == "dhcp"]
        static_conns = [c for c in (snapshot.network.connections or []) if c.get("method") == "static"]
        if dhcp_conns:
            lines.append("# --- DHCP connections (deploy-time config) ---")
            for c in dhcp_conns:
                name = c.get("name", "eth0")
                lines.append(f"network --bootproto=dhcp --device={name}")
            lines.append("")
        if static_conns:
            lines.append("# --- Static connections (baked into image — shown here for reference) ---")
            for c in static_conns:
                name = c.get("name", "eth0")
                lines.append(f"# network --bootproto=static --device={name}  # already in image")
            lines.append("")

        if snapshot.network.hosts_additions:
            lines.append("# --- /etc/hosts additions detected ---")
            for h in snapshot.network.hosts_additions:
                lines.append(f"# {h}")
            lines.append("")

        if snapshot.network.resolv_provenance:
            lines.append("# --- DNS configuration ---")
            lines.append("# network --nameserver=<DNS_IP>")
            lines.append("")

        if snapshot.network.proxy:
            lines.append("# --- Proxy settings detected ---")
            for p in snapshot.network.proxy:
                lines.append(f"# {p.get('line') or ''}")
            lines.append("")

    hostname = ""
    if snapshot.meta:
        hostname = snapshot.meta.get("hostname") or ""
    if hostname:
        lines.append(f"# network --hostname={hostname}")
        lines.append("")

    lines.append("# --- Examples ---")
    lines.append("# network --bootproto=dhcp --device=eth0")
    lines.append("# network --hostname=myhost.example.com")
    lines.append("# network --bootproto=static --ip=192.168.1.10 --netmask=255.255.255.0 --gateway=192.168.1.1")
    lines.append("")

    if snapshot.storage:
        nfs_mounts = [e for e in (snapshot.storage.fstab_entries or []) if "nfs" in (e.get("fstype") or "").lower()]
        cifs_mounts = [e for e in (snapshot.storage.fstab_entries or []) if "cifs" in (e.get("fstype") or "").lower()]
        if nfs_mounts or cifs_mounts:
            lines.append("# --- Remote filesystem mounts detected ---")
            for m in nfs_mounts:
                lines.append(f"# NFS: {m.get('device') or ''} → {m.get('mount_point') or ''}")
            for m in cifs_mounts:
                lines.append(f"# CIFS: {m.get('device') or ''} → {m.get('mount_point') or ''}")
            lines.append("# Provide NFS/CIFS credentials at deploy time via secret injection.")
            lines.append("")

    (output_dir / "kickstart-suggestion.ks").write_text("\n".join(lines))
