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
    lines.append("- `kickstart-suggestion.ks` — deploy-time settings suggestion")
    lines.append("- `inspection-snapshot.json` — raw data for re-rendering")
    lines.append("")

    fixmes = _extract_fixmes(output_dir)
    if fixmes:
        lines.append("## FIXME Items (resolve before production)")
        lines.append("")
        for fixme in fixmes:
            lines.append(f"- {fixme}")
        lines.append("")

    if snapshot.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in snapshot.warnings:
            lines.append(f"- {w.get('message') or '—'}")
        lines.append("")

    lines.append("See `audit-report.md` or `report.html` for full details.")
    lines.append("")
    (output_dir / "README.md").write_text("\n".join(lines))


def _extract_fixmes(output_dir: Path) -> list:
    """Pull FIXME comments from the generated Containerfile."""
    cf = output_dir / "Containerfile"
    if not cf.exists():
        return []
    fixmes = []
    try:
        for line in cf.read_text().splitlines():
            stripped = line.strip()
            if "FIXME" in stripped and stripped.startswith("#"):
                fixmes.append(stripped.lstrip("# ").strip())
    except Exception:
        pass
    return fixmes
