# Codebase vs Design Doc — Gap Tracker

**Status: All gaps resolved. 46 tests pass.**

## Pass 1 — Schema + Inspector + Renderer gaps

- [x] G01: `NetworkSection` missing `static_routes`, `proxy`, `hosts_additions` (was str, now list) → added fields + inspector logic
- [x] G02: `KernelBootSection` missing `modules_load_d`, `modprobe_d`, `dracut_conf` → added fields + inspector logic
- [x] G03: `SelinuxSection` missing `fips_mode`, `audit_rules`, `pam_configs` → added fields + inspector logic
- [x] G04: `UserGroupSection` missing `shell`, `sudoers_rules`, `ssh_authorized_keys_refs` → added fields + inspector logic
- [x] G05: Network inspector not capturing proxy settings, static routes, `/etc/hosts` additions → now scans `/etc/environment`, `/etc/profile.d/`, route files, hosts file
- [x] G06: Kernel inspector not scanning `/etc/modules-load.d`, `/etc/modprobe.d`, `/etc/dracut.conf.d` → now scans all three
- [x] G07: SELinux inspector not detecting mode (from `/etc/selinux/config`), booleans (`getsebool -a`), FIPS (`/proc/sys/crypto/fips_enabled`), PAM configs → all implemented
- [x] G08: User/Group inspector not capturing shell, sudoers, SSH authorized_keys refs → now parses full passwd fields, sudoers.d, detects authorized_keys
- [x] G09: `RpmSection.dnf_history_removed` not rendered anywhere → now shown in audit report under "Previously installed then removed"
- [x] G10: `RpmSection.packages_modified` not rendered anywhere → now shown in audit report with version info
- [x] G11: `RpmSection.baseline_package_names` not shown → audit report now notes "Baseline: N packages from detected profile"
- [x] G12: Audit report storage section was just a flat list → now a table with device/mount/fstype/recommendation columns
- [x] G13: README missing FIXME list from Containerfile → now extracts FIXME comments and lists them

## Pass 2 — Deeper inspector logic

- [x] G14: Service inspector used static JSON manifests (`manifests/`) instead of dynamically parsing systemd preset files → now reads `/usr/lib/systemd/system-preset/*.preset` and `/etc/systemd/system-preset/*.preset`
- [x] G15: Scheduled tasks inspector only scanned `cron.d` and `crontab` → now also scans `/etc/cron.{hourly,daily,weekly,monthly}`, `/var/spool/cron/*` (per-user crontabs), `/var/spool/at/` (at jobs)
- [x] G16: Non-RPM inspector only did directory scanning in `/opt` and `/usr/local` → now also scans for pip `dist-info` directories, npm `package-lock.json`/`yarn.lock`, gem `Gemfile.lock`
- [x] G17: Storage inspector only parsed fstab → now also runs `findmnt --json --real` for mount points, `lvs --reportformat json` for LVM, detects iSCSI and multipath configs
- [x] G18: Kickstart renderer was minimal boilerplate → now references detected connections, hostname, DNS, proxy settings, and NFS/CIFS mounts from snapshot
- [x] G19: Config inspector's third pass (orphaned configs from removed packages) was a stub → now does best-effort detection by matching package names against `/etc` files

## Pass 3 — Final cross-reference

- [x] G22: Audit report and HTML report did not show `rpm_va_flags` for modified config files → audit report now shows flags and package; HTML report has a dedicated flags column
- [x] G23: Config inspector used O(n) per-package `rpm -ql` queries → now uses single bulk `rpm -qa --queryformat '[%{FILENAMES}\n]'`
- [x] G24: Container inspector searched `/opt`, `/srv`, `/etc` for compose files but missed `/home` → added `/home`
- [x] G25: HTML report was missing Kernel/Boot and SELinux category cards → added cards, tabs, and drill-down sections for both
- [x] G26: Redaction pass was missing GCP, Azure, GitHub, MongoDB URI, and generic TOKEN patterns → all added
- [x] G27: Containerfile renderer did not include diff summary comments on config COPYs when `--config-diffs` data was present → now adds per-file comments summarizing the diff (matches design doc example)
