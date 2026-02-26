"""Scheduled Task inspector: cron, systemd timers, at. Generates timer units from cron."""

import re
from pathlib import Path
from typing import Optional

from ..executor import Executor
from ..schema import ScheduledTaskSection


def _cron_to_on_calendar(cron_expr: str) -> str:
    """Convert simple cron (min hour * * *) to systemd OnCalendar. Default daily at 02:00."""
    parts = cron_expr.strip().split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        m, h = int(parts[0]), int(parts[1])
        return f"*-*-* {h:02d}:{m:02d}:00"
    return "*-*-* 02:00:00"


def _make_timer_service(name: str, cron_expr: str, path: str) -> tuple[str, str]:
    """Generate .timer and .service unit content. name is sanitized (e.g. cron-foo)."""
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


def run(
    host_root: Path,
    executor: Optional[Executor],
) -> ScheduledTaskSection:
    section = ScheduledTaskSection()
    host_root = Path(host_root)
    # cron.d
    cron_d = host_root / "etc/cron.d"
    if cron_d.exists():
        for f in cron_d.iterdir():
            if f.is_file() and not f.name.startswith("."):
                rel = str(f.relative_to(host_root))
                section.cron_jobs.append({"path": rel, "source": "cron.d"})
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
    # crontab
    crontab = host_root / "etc/crontab"
    if crontab.exists():
        section.cron_jobs.append({"path": "etc/crontab", "source": "crontab"})
    return section
