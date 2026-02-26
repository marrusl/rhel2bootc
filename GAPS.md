# Design vs implementation gaps

## Review summary

- **Schema**: Covers all inspector outputs; KernelBootSection and SelinuxSection use generic dict/list for design extras (modules-load.d, dracut, FIPS, PAM).
- **Renderers**: Audit report, HTML report, and Containerfile include all inspector sections; no orphaned snapshot fields.
- **CLI flags**: All wired and implemented (see below).
- **Fixture tests**: All 9 tests pass; renderers tested with full and minimal snapshots.

---

## Resolved gaps (all fixed)

### 1. CLI flags — implementation complete

| Flag | Status |
|------|--------|
| `--config-diffs` | **Resolved.** Config inspector uses rpm -qf, finds RPM in /var/cache/dnf, runs rpm2cpio \| cpio to extract original file, produces unified diff; sets diff_against_rpm on ConfigFileEntry. Fallback note in content when RPM not found. |
| `--deep-binary-scan` | **Resolved.** Non-RPM inspector runs `file` to detect binaries, then `strings` (full binary when True, first 4KB when False) and regex for version patterns; adds version/detected_via to items. |
| `--query-podman` | **Resolved.** Container inspector runs `podman ps -a --format json` when True; parses and populates running_containers in ContainerSection. |
| `--validate` | **Resolved.** Runs podman build --no-cache; on failure writes build-errors.log, appends "Build validation failed" to audit-report.md, injects warning div into report.html. |

### 2. Schema vs design

- **meta**: hostname (from /etc/hostname) and timestamp (UTC ISO) set in inspectors/__init__.py. Profile detection left as minimal baseline for now.
- **KernelBootSection / SelinuxSection**: Design extras (modules-load.d, dracut, FIPS, PAM) covered by existing fields or generic lists; no schema change.

### 3. Renderers consuming inspector data

- All sections (RPM, Services, Config, Network, Storage, Scheduled tasks, Containers, Non-RPM, Kernel/Boot, SELinux, Users/Groups) are consumed in audit report, HTML report, and Containerfile. running_containers and generated_timer_units included in audit.

### 4. config_diffs renderer usage

- Containerfile: comment when any file has diff_against_rpm. Audit: fenced diff block per file. HTML: Diff column with \<pre\> content.

### 5. Redaction verification on GitHub push

- push_to_github calls scan_directory_for_secrets(output_dir) and aborts if any pattern found.

### 6. Fixture tests

- test_run_all_with_fixtures asserts all inspector sections non-None. test_renderers_produce_all_artifacts and test_renderers_handle_minimal_snapshot cover renderer output.

### 7. None-safety

- All renderers guard with if snapshot.rpm, if snapshot.config, etc. _summary_counts uses else 0 for missing sections.

### 8. Containerfile: actual file output for quadlet, firewalld, timers

- **Resolved.** Container inspector captures quadlet file content; renderer writes output_dir/quadlet/\<name\> for each unit. Network inspector captures firewalld zone/service XML content; renderer writes config/etc/firewalld/ from firewall_zones (path + content). Scheduled tasks inspector generates .timer and .service from cron.d; renderer writes config/etc/systemd/system/ and Containerfile COPY + RUN systemctl enable for each generated timer.

### 9. Build validation reporting

- **Resolved.** On validate failure, build-errors.log is written, audit-report.md gets "## Build validation failed" with summary, and report.html gets an injected warning div.

### 10. Version check at startup

- **Resolved.** In `inspectors/__init__.py`, before building the snapshot, `_validate_supported_host(os_release, tool_root)` runs. If host is RHEL but version_id is not 9.6 or 9.7, or CentOS but not version 9, or the baseline manifest is missing, a `ValueError` is raised with the design’s error message. CLI catches it and exits non-zero.

### 11. Profile warning

- **Resolved.** When install profile cannot be determined (no anaconda-ks.cfg, original-ks.cfg, or anaconda log), `_profile_warning(host_root)` returns a warning string and it is appended to `snapshot.warnings` with source "rpm" and severity "warning". Audit/HTML can surface it.

### 12. Validate success reporting

- **Resolved.** After a successful `podman build`, `validate._report_build_success(output_dir)` runs `podman images --format "{{.ID}} {{.Size}}" -n 1` and prints "Build succeeded. Image ID: \<id\>  Size: \<size\>".

### 13. tmpfiles.d for /var structure

- **Resolved.** Containerfile renderer writes `config/etc/tmpfiles.d/rhel2bootc-var.conf` with comment lines and, when users exist, `d /home/<name> ...` lines (plus a fallback `d /var/lib/app ...`). Containerfile includes `COPY config/etc/tmpfiles.d/ /etc/tmpfiles.d/` so directories are created on every boot.

---

## Unresolved items

*None.* All design items are implemented; GAPS.md is fully resolved.
