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
        "# Use for deploy-time settings: DHCP, hostname, DNS, NFS, etc.",
        "",
        "# Example: network with DHCP",
        "# network --bootproto=dhcp --device=eth0",
        "",
        "# Example: hostname",
        "# network --hostname=myhost.example.com",
        "",
        "# Example: static IP",
        "# network --bootproto=static --ip=192.168.1.10 --netmask=255.255.255.0 --gateway=192.168.1.1",
        "",
    ]
    if snapshot.network and (snapshot.network.connections or []):
        lines.append("# Detected connection configs (consider applying via kickstart):")
        for c in (snapshot.network.connections or []):
            lines.append(f"#   {c.get('path') or c.get('name') or ''}")
        lines.append("")
    (output_dir / "kickstart-suggestion.ks").write_text("\n".join(lines))
