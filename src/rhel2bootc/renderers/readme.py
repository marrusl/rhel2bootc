"""README.md renderer: summary, build/deploy commands, FIXME list."""

from pathlib import Path

from jinja2 import Environment

from ..schema import InspectionSnapshot


def render(
    snapshot: InspectionSnapshot,
    env: Environment,
    output_dir: Path,
) -> None:
    output_dir = Path(output_dir)
    lines = ["# rhel2bootc output", ""]
    if snapshot.os_release:
        lines.append(f"Generated from **{snapshot.os_release.pretty_name or snapshot.os_release.name}**.")
    lines.append("")
    lines.append("## Build")
    lines.append("")
    lines.append("```bash")
    lines.append("podman build -t my-bootc-image .")
    lines.append("```")
    lines.append("")
    lines.append("## Deploy")
    lines.append("")
    lines.append("```bash")
    lines.append("# After building, switch to the new image:")
    lines.append("bootc switch my-bootc-image:latest")
    lines.append("```")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("- `Containerfile` — image definition")
    lines.append("- `config/` — files to COPY into the image")
    lines.append("- `audit-report.md` — full findings")
    lines.append("- `report.html` — interactive report")
    lines.append("- `secrets-review.md` — redacted items to handle manually")
    lines.append("- `inspection-snapshot.json` — raw data for re-rendering")
    lines.append("")
    if snapshot.warnings:
        lines.append("## Warnings / FIXMEs")
        lines.append("")
        for w in snapshot.warnings:
            lines.append(f"- {w.get('message') or '—'}")
        lines.append("")
    (output_dir / "README.md").write_text("\n".join(lines))
