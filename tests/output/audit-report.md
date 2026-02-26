# Audit Report

**OS:** Red Hat Enterprise Linux 9.6 (Plow)

## Executive Summary

- Packages added (beyond baseline): 10
- Packages removed: 0
- Config files captured: 10
- Containers/quadlet found: 1
- Secrets redacted: 0

## RPM / Packages

### Added
- curl 7.76.1-26.el9.x86_64
- cyrus-sasl-lib 2.1.27-21.el9.x86_64
- httpd 2.4.57-3.el9.x86_64
- httpd-filesystem 2.4.57-3.el9.x86_64
- mod_ssl 2.4.57-3.el9.x86_64
- bash-completion 2.11-5.el9.noarch
- vim-minimal 8.2.2637-21.el9.x86_64
- tar 1.34-6.el9.x86_64
- rsync 3.2.6-4.el9.x86_64
- policycoreutils 3.4-5.el9.x86_64

### Modified configs (rpm -Va)
- `/etc/httpd/conf/httpd.conf` (S.5....T.)
- `/etc/ssh/sshd_config` (.......T.)
- `/etc/pam.d/system-auth` (..5....T.)
- `/etc/chrony.conf` (S.5....T.)
- `/etc/passwd` (....L....)

## Services

| Unit | Current | Default | Action |
|------|---------|---------|--------|
| httpd.service | enabled | disabled | enable |
| firewalld.service | enabled | disabled | enable |

## Configuration Files

- RPM-owned modified: 3
- Unowned: 7
- `/etc/httpd/conf/httpd.conf` (rpm_owned_modified)
- `/etc/ssh/sshd_config` (rpm_owned_modified)
- `/etc/passwd` (rpm_owned_modified)
- `/etc/fstab` (unowned)
- `/etc/os-release` (unowned)
- `/etc/yum.repos.d/redhat.repo` (unowned)
- `/etc/default/grub` (unowned)
- `/etc/audit/rules.d/99-foo.rules` (unowned)
- `/etc/cron.d/hourly-job` (unowned)
- `/etc/containers/systemd/nginx.container` (unowned)

## Storage migration plan

- `/dev/vda1` → / (xfs)

## Scheduled tasks

- Cron: `etc/cron.d/hourly-job` (cron.d)
- Generated: cron-hourly-job (from etc/cron.d/hourly-job)

## Container workloads

- Quadlet: `etc/containers/systemd/nginx.container`

## Non-RPM software

- `opt/dummy` (confidence: low)

## Kernel and boot

- cmdline: `BOOT_IMAGE=(hd0,gpt2)/vmlinuz-5.14.0-1.el9.x86_64 root=/dev/vda1 rhgb quiet`

## SELinux customizations

- Module/rule: `etc/audit/rules.d/99-foo.rules`

## Users and groups

- User: nobody (uid 65534)
- User: jdoe (uid 1000)
- Group: nobody (gid 65534)
- Group: jdoe (gid 1000)

## Data migration plan (/var)

Content under `/var` is seeded at initial bootstrap and not updated by subsequent bootc deployments. Review tmpfiles.d and application data under `/var/lib`, `/var/log`, `/var/data` for migration needs.

## Items requiring manual intervention

- Could not determine original install profile. Using 'minimal' baseline. Some packages reported as 'added' may have been part of the original installation.
