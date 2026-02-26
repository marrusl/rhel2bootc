"""Markdown audit report renderer."""

from pathlib import Path

from jinja2 import Environment

from ..schema import ConfigFileKind, InspectionSnapshot


def render(
    snapshot: InspectionSnapshot,
    env: Environment,
    output_dir: Path,
) -> None:
    output_dir = Path(output_dir)
    lines = ["# Audit Report", ""]
    if snapshot.os_release:
        lines.append(f"**OS:** {snapshot.os_release.pretty_name or snapshot.os_release.name}")
        lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    n_added = len(snapshot.rpm.packages_added) if snapshot.rpm else 0
    n_removed = len(snapshot.rpm.packages_removed) if snapshot.rpm else 0
    n_config = len(snapshot.config.files) if snapshot.config else 0
    n_redactions = len(snapshot.redactions)
    n_containers = 0
    if snapshot.containers:
        n_containers = len(snapshot.containers.quadlet_units or []) + len(snapshot.containers.compose_files or [])
    lines.append(f"- Packages added (beyond baseline): {n_added}")
    lines.append(f"- Packages removed: {n_removed}")
    lines.append(f"- Config files captured: {n_config}")
    lines.append(f"- Containers/quadlet found: {n_containers}")
    lines.append(f"- Secrets redacted: {n_redactions}")
    lines.append("")

    if snapshot.rpm:
        lines.append("## RPM / Packages")
        lines.append("")
        lines.append("### Added")
        for p in snapshot.rpm.packages_added[:50]:
            lines.append(f"- {p.name} {p.version}-{p.release}.{p.arch}")
        if len(snapshot.rpm.packages_added) > 50:
            lines.append(f"- ... and {len(snapshot.rpm.packages_added) - 50} more")
        lines.append("")
        if snapshot.rpm.packages_removed:
            lines.append("### Removed (from baseline)")
            for p in snapshot.rpm.packages_removed:
                lines.append(f"- {p.name}")
            lines.append("")
        if snapshot.rpm.rpm_va:
            lines.append("### Modified configs (rpm -Va)")
            for e in snapshot.rpm.rpm_va:
                lines.append(f"- `{e.path}` ({e.flags})")
        lines.append("")

    if snapshot.services and snapshot.services.state_changes:
        service_rows = [s for s in snapshot.services.state_changes if s.action != "unchanged"]
        if service_rows:
            lines.append("## Services")
            lines.append("")
            lines.append("| Unit | Current | Default | Action |")
            lines.append("|------|---------|---------|--------|")
            for s in service_rows:
                lines.append(f"| {s.unit} | {s.current_state} | {s.default_state} | {s.action} |")
            lines.append("")
        # If state_changes exist but all "unchanged", skip table to avoid header-only

    if snapshot.config and snapshot.config.files:
        lines.append("## Configuration Files")
        lines.append("")
        modified = [f for f in snapshot.config.files if f.kind == ConfigFileKind.RPM_OWNED_MODIFIED]
        unowned = [f for f in snapshot.config.files if f.kind == ConfigFileKind.UNOWNED]
        lines.append(f"- RPM-owned modified: {len(modified)}")
        lines.append(f"- Unowned: {len(unowned)}")
        for f in snapshot.config.files:
            lines.append(f"- `{f.path}` ({f.kind.value})")
            if f.diff_against_rpm and f.diff_against_rpm.strip():
                lines.append("  Diff against RPM default:")
                lines.append("```diff")
                lines.append(f.diff_against_rpm.strip())
                lines.append("```")
                lines.append("")
        lines.append("")

    if snapshot.network and (snapshot.network.connections or snapshot.network.firewall_zones):
        lines.append("## Network")
        lines.append("")
        if snapshot.network.connections:
            for c in snapshot.network.connections:
                path = (c.get("path") or c.get("name") or "")
                lines.append(f"- Connection: `{path}`")
        if snapshot.network.firewall_zones:
            for z in snapshot.network.firewall_zones:
                label = (z.get("name") or z.get("path") or "") if isinstance(z, dict) else str(z)
                lines.append(f"- Firewall: {label}")
        lines.append("")

    if snapshot.storage and (snapshot.storage.fstab_entries or snapshot.storage.mount_points):
        lines.append("## Storage migration plan")
        lines.append("")
        for e in (snapshot.storage.fstab_entries or [])[:30]:
            lines.append(f"- `{e.get('device') or ''}` → {e.get('mount_point') or ''} ({e.get('fstype') or ''})")
        lines.append("")

    if snapshot.scheduled_tasks and (snapshot.scheduled_tasks.cron_jobs or snapshot.scheduled_tasks.systemd_timers or snapshot.scheduled_tasks.generated_timer_units):
        lines.append("## Scheduled tasks")
        lines.append("")
        for j in (snapshot.scheduled_tasks.cron_jobs or [])[:20]:
            lines.append(f"- Cron: `{j.get('path') or ''}` ({j.get('source') or ''})")
        for t in (snapshot.scheduled_tasks.systemd_timers or [])[:20]:
            label = (t.get("name") or t.get("path") or str(t)) if isinstance(t, dict) else str(t)
            lines.append(f"- Timer: {label}")
        for u in (snapshot.scheduled_tasks.generated_timer_units or [])[:20]:
            lines.append(f"- Generated: {u.get('name') or ''} (from {u.get('source_path') or ''})")
        lines.append("")

    if snapshot.containers and (snapshot.containers.quadlet_units or snapshot.containers.compose_files or snapshot.containers.running_containers):
        lines.append("## Container workloads")
        lines.append("")
        for u in (snapshot.containers.quadlet_units or []):
            lines.append(f"- Quadlet: `{u.get('path') or u.get('name') or ''}`")
        for c in (snapshot.containers.compose_files or []):
            lines.append(f"- Compose: `{c.get('path') or ''}`")
        for r in (snapshot.containers.running_containers or []):
            lines.append(f"- Running: {r.get('id') or ''} {r.get('image') or ''} {r.get('status') or ''}")
        lines.append("")

    if snapshot.non_rpm_software and snapshot.non_rpm_software.items:
        lines.append("## Non-RPM software")
        lines.append("")
        for i in snapshot.non_rpm_software.items[:30]:
            path_or_name = (i.get('path') or i.get('name') or '')
            conf = (i.get('confidence') or 'unknown')
            lines.append(f"- `{path_or_name}` (confidence: {conf})")
        lines.append("")

    if snapshot.kernel_boot and (snapshot.kernel_boot.cmdline or snapshot.kernel_boot.sysctl_overrides):
        lines.append("## Kernel and boot")
        lines.append("")
        if snapshot.kernel_boot.cmdline:
            lines.append(f"- cmdline: `{snapshot.kernel_boot.cmdline[:200]}`")
        for s in (snapshot.kernel_boot.sysctl_overrides or [])[:20]:
            lines.append(f"- sysctl: `{s.get('path') or ''}`")
        lines.append("")

    if snapshot.selinux and (snapshot.selinux.mode or snapshot.selinux.custom_modules or snapshot.selinux.boolean_overrides):
        lines.append("## SELinux customizations")
        lines.append("")
        if snapshot.selinux.mode:
            lines.append(f"- Mode: {snapshot.selinux.mode}")
        for m in (snapshot.selinux.custom_modules or [])[:20]:
            lines.append(f"- Module/rule: `{m}`")
        lines.append("")

    if snapshot.users_groups and (snapshot.users_groups.users or snapshot.users_groups.groups):
        lines.append("## Users and groups")
        lines.append("")
        for u in (snapshot.users_groups.users or [])[:30]:
            lines.append(f"- User: {u.get('name') or ''} (uid {u.get('uid') or ''})")
        for g in (snapshot.users_groups.groups or [])[:30]:
            lines.append(f"- Group: {g.get('name') or ''} (gid {g.get('gid') or ''})")
        lines.append("")

    lines.append("## Data migration plan (/var)")
    lines.append("")
    lines.append("Content under `/var` is seeded at initial bootstrap and not updated by subsequent bootc deployments. Review tmpfiles.d and application data under `/var/lib`, `/var/log`, `/var/data` for migration needs.")
    lines.append("")

    if snapshot.warnings:
        lines.append("## Items requiring manual intervention")
        lines.append("")
        for w in snapshot.warnings:
            lines.append(f"- {w.get('message') or '—'}")
        lines.append("")

    if snapshot.redactions:
        lines.append("## Redactions (secrets)")
        lines.append("")
        for r in snapshot.redactions:
            lines.append(f"- **{r.get('path') or ''}**: {r.get('pattern') or ''} — {r.get('remediation') or ''}")
        lines.append("")

    (output_dir / "audit-report.md").write_text("\n".join(lines))
