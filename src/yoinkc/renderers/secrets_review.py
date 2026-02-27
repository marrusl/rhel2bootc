"""secrets-review.md renderer: list of redacted items and remediation."""

from pathlib import Path

from jinja2 import Environment

from ..schema import InspectionSnapshot


def render(
    snapshot: InspectionSnapshot,
    env: Environment,
    output_dir: Path,
) -> None:
    output_dir = Path(output_dir)
    lines = ["# Secrets Review", ""]
    lines.append("The following items were redacted or excluded. Handle them manually (e.g. Kubernetes secret, systemd credential, env at deploy).")
    lines.append("")
    if not snapshot.redactions:
        lines.append("No redactions recorded.")
        (output_dir / "secrets-review.md").write_text("\n".join(lines))
        return
    lines.append("| Path | Pattern | Line | Remediation |")
    lines.append("|------|---------|------|-------------|")
    for r in snapshot.redactions:
        path = (r.get("path") or "").replace("|", "\\|")
        pattern = (r.get("pattern") or "").replace("|", "\\|")
        line = (r.get("line") or "").replace("|", "\\|")
        rem = (r.get("remediation") or "").replace("|", "\\|")
        lines.append(f"| {path} | {pattern} | {line} | {rem} |")
    lines.append("")
    (output_dir / "secrets-review.md").write_text("\n".join(lines))
