"""Scheduled Task inspector: cron (all locations), systemd timers, at jobs. Generates timer units from cron."""

import re
from pathlib import Path
from typing import List, Optional

from ..executor import Executor
from ..schema import ScheduledTaskSection


def _safe_iterdir(d: Path) -> List[Path]:
    try:
        return sorted(d.iterdir())
    except (PermissionError, OSError):
        return []


def _cron_to_on_calendar(cron_expr: str) -> str:
    """Convert simple cron (min hour * * *) to systemd OnCalendar. Default daily at 02:00."""
    parts = cron_expr.strip().split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        m, h = int(parts[0]), int(parts[1])
        return f"*-*-* {h:02d}:{m:02d}:00"
    return "*-*-* 02:00:00"


def _make_timer_service(name: str, cron_expr: str, path: str) -> tuple[str, str]:
    """Generate .timer and .service unit content."""
    on_calendar = _cron_to_on_calendar(cron_expr)
    timer_content = f"""[Unit]
Description=Generated from cron: {path}
# Original cron: {cron_expr}

[Timer]
OnCalendar={on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""
    service_content = f"""[Unit]
Description=Timer from cron {path}

[Service]
Type=oneshot
ExecStart=/bin/true
# FIXME: replace with actual command from cron
"""
    return timer_content, service_content


def _scan_cron_file(section: ScheduledTaskSection, host_root: Path, f: Path, source: str) -> None:
    """Parse a cron file for job entries and generate timer units."""
    rel = str(f.relative_to(host_root))
    section.cron_jobs.append({"path": rel, "source": source})
    try:
        text = f.read_text()
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and re.match(r"^[\d*]", line):
                parts = line.split()
                if len(parts) >= 5:
                    cron_expr = " ".join(parts[:5])
                    safe_name = "cron-" + f.name.replace(".", "-")
                    timer_content, service_content = _make_timer_service(safe_name, cron_expr, rel)
                    section.generated_timer_units.append({
                        "name": safe_name,
                        "timer_content": timer_content,
                        "service_content": service_content,
                        "cron_expr": cron_expr,
                        "source_path": rel,
                    })
                    break
    except Exception:
        pass


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> ScheduledTaskSection:
    section = ScheduledTaskSection()
    host_root = Path(host_root)

    cron_d = host_root / "etc/cron.d"
    if cron_d.exists():
        for f in _safe_iterdir(cron_d):
            if f.is_file() and not f.name.startswith("."):
                _scan_cron_file(section, host_root, f, "cron.d")

    crontab = host_root / "etc/crontab"
    try:
        if crontab.exists():
            section.cron_jobs.append({"path": "etc/crontab", "source": "crontab"})
    except (PermissionError, OSError):
        pass

    for period in ("hourly", "daily", "weekly", "monthly"):
        d = host_root / f"etc/cron.{period}"
        if d.exists():
            for f in _safe_iterdir(d):
                if f.is_file() and not f.name.startswith("."):
                    rel = str(f.relative_to(host_root))
                    section.cron_jobs.append({"path": rel, "source": f"cron.{period}"})

    spool = host_root / "var/spool/cron"
    if spool.exists():
        for f in _safe_iterdir(spool):
            if f.is_file() and not f.name.startswith("."):
                _scan_cron_file(section, host_root, f, f"spool/cron ({f.name})")

    at_spool = host_root / "var/spool/at"
    if at_spool.exists():
        for f in _safe_iterdir(at_spool):
            if f.is_file() and not f.name.startswith("."):
                rel = str(f.relative_to(host_root))
                section.cron_jobs.append({"path": rel, "source": "at"})

    return section
