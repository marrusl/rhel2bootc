# Tool Design: rhel2bootc

## Runtime Model

A privileged container (`--privileged` or at minimum `--pid=host --ipc=host -v /:/host:ro` plus a writable output mount) that inspects the host via `/host`. This is clean — no contamination of the source system, no installation required, and it naturally separates the tool from the thing being inspected.

Output goes to a mounted volume that becomes either local files, a local git repo, or gets pushed to GitHub via the API.

The tool itself ships as a container: `quay.io/yourorg/rhel2bootc:latest`.

## Architecture

The tool is structured as a pipeline of **inspectors** that each produce structured JSON, fed into **renderers** that produce the output artifacts. That separation is important — it means you can re-render from a saved inspection snapshot without re-running against the host, and you can test renderers in isolation.

### Inspector Modules

#### RPM Inspector

`rpm -qa --queryformat` to get the full package list with epoch/version/release/arch, then diff against a baseline generated from the distribution's comps XML (see [Baseline Generation](#baseline-generation)). Identifies: added packages, removed packages, modified package configs via `rpm -Va`.

Also captures repo definitions from `/host/etc/yum.repos.d/` and `/host/etc/dnf/`.

Additionally checks `dnf history` for packages that were installed and later removed, since these may have left behind config files or state that still affects the system.

#### Service Inspector

Systemctl state via `systemd-analyze dump` or direct unit file parsing. Diffs enabled/disabled/masked state against the defaults for the detected base install. Default service state is determined from systemd preset files shipped in the base packages (see [Baseline Generation](#baseline-generation)).

#### Config Inspector

Three passes:

1. **RPM-owned files that have been modified** (from `rpm -Va`) — with optional diffs against RPM defaults (see below)
2. **Files in `/etc` not owned by any RPM** — these are the hand-placed configs that would otherwise be lost entirely
3. **Config files from packages that were installed and later removed** (cross-referenced with `dnf history` from the RPM inspector) — orphaned configs that may still affect system behavior

The second category is particularly important. These are the files that represent the actual identity of the system beyond its package set.

**Unowned file detection (optimized):**

Rather than running `rpm -qf` per-file across `/etc` (which is O(n) RPM database lookups and painfully slow on large systems), the inspector builds a set of all RPM-owned paths in a single pass via `rpm -qla` and then diffs that set against the actual filesystem listing. This reduces thousands of individual RPM queries to one bulk query plus a set subtraction — typically seconds instead of minutes.

**Diff against RPM defaults (opt-in: `--config-diffs`):**

When enabled, for every modified RPM-owned config file, the inspector extracts the original package-shipped version via `rpm2cpio` + `cpio` from the installed RPM and produces a unified diff against the current file on disk. This means the output shows *what the operator actually changed* (e.g., "line 47: `MaxClients 256` → `MaxClients 1024`") rather than just "this file was modified."

Without this flag, modified RPM-owned configs are captured as full files with a note that they differ from the package default (based on `rpm -Va` output), but no diff is generated. The audit report and HTML report will show the `rpm -Va` verification flags (size, mtime, checksum, etc.) so operators still know *how* the file differs at a high level.

When `--config-diffs` is enabled:

RPM retrieval strategy:
1. Check the local dnf cache on the host (`/host/var/cache/dnf/`) — the original RPM is often still there.
2. If not cached, attempt to download the exact installed NEVRA from the configured repos (this requires network access from the tool container and working repo credentials).
3. If the RPM cannot be retrieved (offline host, repo no longer available, package from a decommissioned repo), fall back to capturing the full file with a `# NOTE: could not retrieve RPM default for diff — full file included` comment. The audit report lists these cases so the operator knows which files need manual comparison.

The diffs are stored in the inspection snapshot and rendered in both the markdown audit report (as fenced diff blocks) and the HTML report (as a side-by-side or unified diff view with syntax highlighting). This gives operators the context they need to decide whether each change is still relevant for the bootc target or can be dropped.

For the Containerfile, modified RPM-owned configs are always included as full-file COPYs. When `--config-diffs` is enabled, each COPY gets a comment summarizing the diff:

```dockerfile
# Modified from httpd-2.4.57 default:
#   - MaxClients: 256 → 1024
#   - ServerName: added (localhost:443)
#   - SSLProtocol: restricted to TLSv1.2+
# See audit-report.md or report.html for full diff
COPY config/etc/httpd/conf/httpd.conf /etc/httpd/conf/httpd.conf
```

This makes Containerfile review dramatically faster — operators can see at a glance whether a config change is intentional and relevant without having to manually diff each file.

#### Network Inspector

Captures the full network identity of the system:

- **NetworkManager profiles**: connection files from `/etc/NetworkManager/system-connections/` and `/etc/sysconfig/network-scripts/` (legacy). Classifies each as static config (likely image-bakeable) vs. DHCP/dynamic (likely runtime/kickstart territory).
- **Firewall rules**: `firewalld` zones, services, rich rules, and direct rules. Exported as both the raw XML zone files and as `firewall-cmd` commands in the Containerfile.
- **Static routes and policy routing**: `/etc/sysconfig/network-scripts/route-*`, `/etc/iproute2/`, and ip rule/route dumps.
- **DNS configuration**: `/etc/resolv.conf` provenance (is it managed by NetworkManager, systemd-resolved, or hand-edited?), `/etc/hosts` additions beyond localhost.
- **Proxy configuration**: system-wide proxy settings from `/etc/environment`, `/etc/profile.d/`, dnf proxy configs.

The audit report distinguishes between network config that belongs in the image (firewall rules, static interface definitions for known hardware) and config that should be applied at deployment time via kickstart (DHCP interfaces, site-specific DNS, hostname). This distinction is flagged with `# FIXME: consider moving to kickstart` comments in the Containerfile.

#### Storage Inspector

Does **not** attempt to reproduce storage config in the image, but captures it comprehensively in the audit report for migration planning:

- **Mount points**: `/etc/fstab` entries, currently mounted filesystems, automount maps (`/etc/auto.*`).
- **LVM layout**: volume groups, logical volumes, their sizes and mount points.
- **NFS/CIFS mounts**: remote filesystem dependencies, including credential references.
- **Block device configuration**: multipath, iSCSI initiator config, device-mapper entries.

The audit report gets a dedicated "Storage Migration Plan" section that maps each mount point to a recommended approach: image-embedded (for small, static data), PVC/volume mount (for application data), external storage service (for shared filesystems).

#### Scheduled Task Inspector

Captures and converts all scheduled execution:

- **Cron jobs**: `/etc/crontab`, `/etc/cron.d/*`, `/var/spool/cron/*` (per-user crontabs), `/etc/cron.{hourly,daily,weekly,monthly}/` scripts.
- **Systemd timers**: existing `.timer` units and their associated `.service` units.
- **At jobs**: any pending `at` jobs from `/var/spool/at/`.

For the Containerfile output, cron jobs are converted to systemd timer units (since bootc images should use systemd timers as the canonical scheduling mechanism). Each generated timer includes a comment with the original cron expression for reference. Jobs that can't be cleanly converted (e.g., per-user crontabs with environment variable dependencies) get a `# FIXME` comment and appear in the audit report.

#### Container Inspector

Discovers container workloads through a fast file-based scan:

1. **Quadlet units**: `/etc/containers/systemd/` and `/usr/share/containers/systemd/` — these are the primary source of truth and are always captured.
2. **Compose files**: podman-compose and docker-compose files (plenty of RHEL systems still have these from Docker-to-Podman migrations), found via a `find` across common locations (`/opt`, `/srv`, `/home`, `/etc`).
3. **Container image references**: parses discovered unit and compose files to extract image names and tags for the audit report.

**Live container query (opt-in: `--query-podman`):**

When enabled, connects to the podman socket to enumerate running containers, their configs, mounts, and network settings. This captures runtime state that may not be reflected in the unit files (e.g., containers started manually, containers with runtime overrides). Without this flag, the inspector relies entirely on the file-based scan, which is faster and covers the vast majority of cases since production workloads should be defined in unit files.

Translates to quadlet in the output since that's the bootc-blessed pattern. Docker-compose files get a `# FIXME: converted from docker-compose, verify quadlet translation` comment.

#### Non-RPM Software Inspector

This is the hardest inspector and the one most likely to produce incomplete or incorrect results. The tool is honest about this — it defaults to `# FIXME` comments rather than guessing wrong.

**Detection approach:**

`/opt` and `/usr/local`: check for embedded package metadata (`package.json`, `*.dist-info`, `METADATA`, `setup.py`, installer logs in common locations). Check if directories have their own `.git` history.

**Language-specific package managers:**

- **pip**: `pip list --path` against known venv and system paths. Captures `requirements.txt` or `pip freeze` output where possible. Flags venvs created with `--system-site-packages` as needing manual review since their dependency resolution is entangled with system packages.
- **npm**: scan for `node_modules` with `package-lock.json` or `yarn.lock`. Captures the lockfile for reproducibility.
- **gem/bundler**: check for `Gemfile.lock`, system gem installs.

**Binary detection:**

For binaries without any package manager metadata, the tool runs a **fast classification pass** by default:

1. `file` command to identify binary type (ELF, script, etc.) and architecture.
2. For ELF binaries, check for `.note.go.buildid` section (Go), `.rustc` debug section (Rust), or dynamic linker info (`readelf -d`, not `ldd` which is slower and attempts to resolve) to classify provenance.
3. Check for a `--version` or `-V` flag by inspecting the binary's help text (`strings` limited to the first 4KB of the binary, not the full file — version strings in self-identifying binaries are almost always near the start).

This fast pass covers the common cases (Go/Rust identification, self-versioning binaries) without the cost of scanning entire large binaries.

**Deep binary scan (opt-in: `--deep-binary-scan`):**

When enabled, runs `strings` against the full binary content with regex matching against a conservative allowlist of version patterns (e.g., `X.Y.Z` preceded by `version`, `-v`, or the binary's own name). This is slow on large statically-linked binaries (a 200MB Go binary can take 10+ seconds) and has high false-positive potential, but may recover version info that the fast pass misses.

**Explicitly flagged as "manual intervention" categories:**

- Statically-linked Go and Rust binaries (increasingly common in `/usr/local/bin`, essentially opaque — no reliable way to determine provenance or version).
- Software installed from local wheels, private package indexes, or tarballs where the upstream source no longer exists.
- Anything installed via `curl | bash` or `wget && make install` with no manifest left behind.

For all unknown provenance software, the output is a `COPY` directive with a prominent `# FIXME: unknown provenance — determine upstream source and installation method` comment. The tool never guesses at an installation command it can't verify.

**Multi-stage build detection:**

If pip packages with C extensions are detected (identified by `.so` files in `*.dist-info` directories or build-dependency packages in the RPM list), the renderer offers a multi-stage Containerfile variant that separates the build environment from the final image.

#### Kernel/Boot Inspector

- `/proc/cmdline` and `/etc/default/grub` — kernel boot parameters
- Kernel modules: loaded (`lsmod`) vs. default, with `/etc/modules-load.d/` and `/etc/modprobe.d/` configs
- Sysctl settings: diff `/etc/sysctl.d/` and `/etc/sysctl.conf` against defaults
- Dracut configuration: `/etc/dracut.conf.d/`

#### SELinux/Security Inspector

- SELinux mode and policy customizations (`semodule -l` diff against base)
- Custom boolean settings (`getsebool -a` diffed against defaults)
- Audit rules from `/etc/audit/rules.d/`
- FIPS mode status
- Custom PAM configurations

#### User/Group Inspector

Non-system users and groups added to the system (UID/GID above system threshold, or explicitly added entries in `/etc/passwd` and `/etc/group` not associated with any RPM).

Captures: home directory contents inventory (not contents — just the tree structure for audit), shell assignments, group memberships, sudoers rules, SSH authorized_keys references (flagged for manual handling, not copied).

### Baseline Generation

Rather than shipping static baseline manifests that need constant maintenance, the tool generates baselines dynamically at runtime by fetching and parsing the distribution's comps XML — the same group definitions the installer uses to determine what packages belong to each profile.

**How it works:**

1. **Detect host identity.** Read `/host/etc/os-release` to determine distribution (RHEL, CentOS Stream) and version.
2. **Fetch comps XML using the host's own repos.** The tool uses the repo configuration from `/host/etc/yum.repos.d/` and the host's subscription credentials (via `/host/etc/pki/`) to fetch the comps XML from the same repositories the host is subscribed to. This sidesteps the RHEL credential problem — the tool uses the host's own access rather than needing separate credentials. For CentOS Stream, the comps are available from public mirrors (e.g., `mirror.stream.centos.org`) and also maintained in git at `https://gitlab.com/CentOS/centos-stream-9-comps`.
3. **Resolve the install profile.** Detect which profile was originally installed from `/host/root/anaconda-ks.cfg`, `/host/root/original-ks.cfg`, or install log artifacts in `/host/var/log/anaconda/`. If the profile cannot be determined, fall back to `@minimal` and emit a warning.
4. **Parse group definitions.** Walk the comps XML to collect mandatory and default packages for the detected profile, resolving group dependencies (e.g., `@server` depends on `@core`, which is always included). This produces the package baseline.
5. **Determine service baseline.** Parse systemd preset files from the base packages to establish which services are enabled or disabled by default. This covers the gap that comps XML doesn't address — comps defines *packages*, presets define *service state*.
6. **Cache in the snapshot.** The resolved baseline is stored in `inspection-snapshot.json` so re-renders via `--from-snapshot` don't need network access.

**Profile detection fallback:**

If the original install profile cannot be determined, the tool falls back to `@minimal` (the smallest group, which will over-report "added" packages) and emits a clear warning:

```
WARNING: Could not determine original install profile. Using '@minimal' baseline.
Some packages reported as "added" may have been part of the original installation.
Review the package list in the audit report and remove false positives.
```

The `--profile NAME` flag overrides auto-detection entirely, which is useful when SELinux prevents the container from reading `/host/root/anaconda-ks.cfg` (a common situation with `:ro` bind mounts). Adding `--security-opt label=disable` to the `podman run` command is an alternative that restores full host filesystem access.

**No network / air-gapped fallback:**

If the comps XML cannot be fetched (air-gapped environment, broken repos, unreachable mirror), the tool degrades gracefully:

```
WARNING: Could not fetch comps XML from configured repositories.
No baseline available — all installed packages will be included in the Containerfile.
To reduce image size, provide a comps file via --comps-file or manually trim the package list.
```

In this mode, the Containerfile includes all installed packages rather than just the delta. The tool still performs all other inspection — config files, services, containers, non-RPM software, etc. — so it remains useful even without a baseline. The audit report's package section is labeled "no baseline — showing all packages" so operators understand why the list is comprehensive.

For environments that are permanently air-gapped, the `--comps-file` flag accepts a path to a local comps XML file (extracted from an ISO or downloaded separately).

**Version scope implications:**

Because baselines are generated dynamically, the tool is no longer limited to specific RHEL minor versions. It works against any RHEL 9.x or CentOS Stream 9 host that has accessible repos. The version constraint becomes "does a corresponding bootc base image exist for the output" rather than "do we have a pre-built manifest." Support for RHEL 10 and future versions requires no manifest work — only verification that the comps XML format hasn't changed and that a suitable bootc base image is available.

## Secret Handling

A dedicated redaction pass runs over all captured file contents **before any output is written or any git operations occur**. This ordering is critical — the redaction pass is not a separate stage that can be skipped, it's a gate that all content must pass through.

### Redaction Layers

**Pattern-based redaction:** Regex patterns for:
- API keys and tokens (AWS, GCP, Azure, GitHub, generic `API_KEY`/`TOKEN` patterns)
- Private key PEM blocks (`-----BEGIN.*PRIVATE KEY-----`)
- Password fields in config files (`password = ...`, `PASSWD=...`, `secret=...`)
- Connection strings with embedded credentials (JDBC, MongoDB, Redis, PostgreSQL URIs)
- Cloud provider credential files

Matched values are replaced with `REDACTED_<TYPE>_<hash>` where the hash is a truncated SHA-256 of the original value. This means you can tell redacted values apart without knowing them — useful for spotting "these three config files all use the same database password."

**Path-based exclusion:** These files are **never** included in content, only referenced in the audit report with a note that they need manual handling:
- `/etc/shadow`, `/etc/gshadow`
- `/etc/ssh/ssh_host_*` (host keys)
- `/etc/pki/` private keys
- TLS certificate private keys (`.key` files)
- Kerberos keytabs

**Flagging:** Anything redacted gets an entry in `secrets-review.md` listing:
- The file path
- The pattern that matched
- Line number (or "entire file" for excluded paths)
- Suggested remediation (e.g., "use a Kubernetes secret", "use a systemd credential", "inject via environment variable at deploy time")

### GitHub Push Guardrails

Pushing to GitHub means network egress from a container with read access to the entire host filesystem. Even with the redaction pass, this requires explicit safeguards:

1. **Explicit opt-in**: GitHub push is never a default. It requires `--push-to-github` with a repository target.
2. **Confirmation gate**: Before pushing, the tool prints a summary of what will be pushed — **total data size on disk**, file count, any `# FIXME` items, count of redacted values — and requires interactive confirmation (`--yes` to skip for automation, but this must be a conscious choice).
3. **Redaction verification**: The push step re-scans the entire output tree for known secret patterns as a second pass. If anything is found that the first pass missed, the push is aborted with an error.
4. **Private repo default**: If creating a new repo, it defaults to private. Creating a public repo requires `--public` flag.

## Output Artifacts

### Containerfile

Structured in a deliberate layer order to maximize cache efficiency:

```dockerfile
# === Base Image ===
# Automatically selected based on detected host OS and version:
#   RHEL 9.x  → registry.redhat.io/rhel9/rhel-bootc:9.x
#   CentOS S9 → quay.io/centos-bootc/centos-bootc:stream9
FROM registry.redhat.io/rhel9/rhel-bootc:9.6

# === Repository Configuration ===
# Detected: 2 additional repos beyond base RHEL
COPY config/etc/yum.repos.d/ /etc/yum.repos.d/

# === Package Installation ===
# Detected: 47 packages added beyond server baseline
# See audit-report.md for full package analysis
RUN dnf install -y \
    package1 \
    package2 \
    && dnf clean all

# === Service Enablement ===
# Detected: 5 non-default services enabled, 2 default services disabled
RUN systemctl enable httpd nginx && \
    systemctl disable kdump

# === Firewall Configuration ===
# Detected: custom firewalld zone with 3 additional services
COPY config/etc/firewalld/ /etc/firewalld/

# === Scheduled Tasks ===
# Converted from cron: 3 jobs → systemd timers
COPY config/etc/systemd/system/backup-daily.timer /etc/systemd/system/
COPY config/etc/systemd/system/backup-daily.service /etc/systemd/system/
RUN systemctl enable backup-daily.timer

# === Configuration Files ===
# Detected: 23 modified RPM-owned configs, 8 unowned configs
COPY config/etc/ /etc/

# === Non-RPM Software ===
# FIXME: verify these pip packages install correctly from PyPI
RUN pip install flask==2.3.2 gunicorn==21.2.0
# FIXME: unknown provenance — binary found in /usr/local/bin/mytool
COPY config/usr/local/bin/mytool /usr/local/bin/mytool

# === Container Workloads (Quadlet) ===
COPY quadlet/ /etc/containers/systemd/

# === Users and Groups ===
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m appuser

# === Kernel Configuration ===
# Detected: custom kernel args beyond defaults
RUN rpm-ostree kargs --append=hugepagesz=2M --append=hugepages=512

# === SELinux Customizations ===
# Detected: 2 custom policy modules, 3 modified booleans
COPY config/selinux/ /tmp/selinux/
RUN semodule -i /tmp/selinux/myapp.pp && rm -rf /tmp/selinux/
RUN setsebool -P httpd_can_network_connect on

# === Network Configuration ===
# NOTE: Static firewall rules are baked above. Interface-specific config
# (DHCP, site-specific DNS) should be applied via kickstart at deploy time.
# FIXME: review kickstart-suggestion.ks for deployment-time config

# === tmpfiles.d for /var structure ===
# /var is seeded from the image at initial bootstrap but never updated
# by subsequent bootc deployments. tmpfiles.d ensures directories exist
# on every boot. See audit-report.md "Data Migration Plan" section.
COPY config/etc/tmpfiles.d/app-dirs.conf /etc/tmpfiles.d/
```

Each section has comments explaining what was detected and why it was included. `FIXME` comments mark anything that needs human review.

### Git Repo Layout

```
/
├── Containerfile
├── README.md                  # what was found, how to build, how to deploy
├── secrets-review.md          # everything redacted, needs manual handling
├── audit-report.md            # full human-readable findings
├── config/                    # files to COPY into the image
│   ├── etc/                   # mirrors /etc structure for modified configs
│   │   ├── firewalld/         # firewall zone/service definitions
│   │   ├── systemd/system/    # generated timer units (from cron conversion)
│   │   ├── tmpfiles.d/        # directory structure for /var
│   │   └── ...
│   ├── opt/                   # non-RPM software (where COPYed)
│   └── usr/
├── quadlet/                   # container unit files
├── kickstart-suggestion.ks     # suggested kickstart snippet for deploy-time settings
├── report.html                # interactive HTML report (open in browser)
└── inspection-snapshot.json   # raw inspector output, for re-rendering
```

### README.md

Includes:
- Summary of what was found on the source system
- Exact `podman build` command to build the image
- Exact `bootc switch` or `bootc install` command to deploy (with the right flags for the detected scenario)
- List of `FIXME` items that need resolution before the image is production-ready
- Link to the audit report for full details

### Audit Report (audit-report.md)

A markdown document for version control and quick terminal reference. For the interactive view, see [HTML Report](#html-report-reporthtml) below.

Organized as:

1. **Executive Summary**: counts of packages added/removed, configs modified, containers found, secrets redacted, issues flagged. A clear triage: X items handled automatically, Y items handled with FIXME, Z items need manual intervention.

2. **Per-Inspector Sections** (each with tables):
   - RPM analysis (added, removed, modified packages)
   - Service state changes
   - Configuration changes (RPM-owned modified, unowned files)
   - Network configuration (what's baked vs. what should be kickstart)
   - Storage migration plan (mount points → recommended approach)
   - Scheduled tasks (cron → timer conversions, issues)
   - Container workloads
   - Non-RPM software (with confidence ratings: high/medium/low/unknown)
   - Kernel and boot configuration
   - SELinux customizations
   - Users and groups

3. **Data Migration Plan** (`/var` problem): dedicated section listing everything found under `/var/lib`, `/var/log`, `/var/data` that looks like application state — databases, app data directories, log directories — with explicit notes on what can be seeded in the image (deployed only at initial bootstrap, never updated by bootc afterward) vs. what needs a separate migration strategy. The Containerfile generates `systemd-tmpfiles.d` snippets to ensure expected directory structures exist on every boot.

4. **Items Requiring Manual Intervention**: consolidated list pulled from all inspectors, prioritized by risk.

### HTML Report (report.html)

A single self-contained HTML file (inline CSS/JS, no external dependencies) that provides an interactive view of the inspection results. This is the primary artifact operators will use to understand what the tool found and what work remains.

**Layout:**

The report opens to a **dashboard view** with:

- **Status banner**: hostname, RHEL version, inspection timestamp, overall health (how many items handled automatically vs. needing attention).
- **Warning panel** (prominently placed, always visible at the top): all warnings, FIXMEs, and errors from the run, color-coded by severity (red for "needs manual intervention", amber for "handled with FIXME", blue for informational). Each warning links to its detail section below. This panel is the first thing an operator should read.
- **Category cards**: one card per inspector area (Packages, Services, Config, Network, Storage, Scheduled Tasks, Containers, Non-RPM Software, Kernel/Boot, SELinux, Users/Groups). Each card shows a summary count (e.g., "47 packages added, 3 removed") and a status indicator (green checkmark if fully automated, amber if FIXMEs exist, red if manual intervention needed).

**Drill-down:**

Clicking any category card expands to the full detail view for that inspector:

- **Packages**: sortable/filterable table of added, removed, and modified packages with version info. Filter by status (added/removed/modified), search by package name.
- **Services**: table of state changes with columns for service name, current state, default state, and action taken in Containerfile.
- **Config files**: tree view mirroring the filesystem, with icons indicating modified (RPM-owned), unowned, or redacted. Clicking an unowned file shows the full file contents. For modified RPM-owned files: if `--config-diffs` was used, clicking shows the diff against the package default (unified or side-by-side view with syntax highlighting) with a summary of key changes; otherwise, shows the full file with `rpm -Va` verification flags indicating how it differs.
- **Network**: split view — left side shows what's baked into the image, right side shows what's deferred to kickstart, with explanations for each decision.
- **Non-RPM software**: table with columns for name, detected version, confidence level (high/medium/low/unknown), detection method, and Containerfile action. Low-confidence and unknown items are visually highlighted.
- **Secrets**: summary of all redacted items with file paths, pattern types, and remediation suggestions (mirrors `secrets-review.md` content).

**Warnings section:**

Accessible both from the top-level warning panel and as a dedicated tab. Displays all warnings in a flat, searchable list with:
- Severity (error / warning / info)
- Source inspector
- Short description
- Affected file or resource
- Suggested action
- Link to the relevant detail section

**Implementation:** Generated from `inspection-snapshot.json` by the renderer using a Jinja2 HTML template. The entire report is a single `.html` file (typically < 2MB) that can be opened in any browser, emailed, or served statically. No server required.

### Kickstart Suggestion File

A `kickstart-suggestion.ks` file containing suggested kickstart snippets for settings that belong at deploy time rather than in the image:
- DHCP network interfaces (`network --bootproto=dhcp ...`)
- Hostname (`network --hostname=...`)
- Site-specific DNS
- NFS mount credentials
- Any deployment-specific environment variables referenced in configs

This file is clearly marked as a **suggestion** — it needs to be reviewed and adapted for the target environment.

## The `/var` Problem — Explicitly Documented

bootc's contract is that `/var` content from the image is written to disk at initial bootstrap, but is **never updated by subsequent image deployments**. It becomes fully mutable state from that point forward. This means you *can* seed `/var` with initial directory structures and default data in the image, but anything that lives there is the operator's responsibility to manage, back up, and migrate going forward — bootc won't touch it again.

This has practical implications for the tool's output:

- `tmpfiles.d` snippets are generated to create expected directory structures (these run on every boot and are the right mechanism for ensuring directories exist).
- Small, static seed data (e.g., default config databases) *can* be included in the image and will land in `/var` on first install, but this is flagged with a `# NOTE: only deployed on initial bootstrap, not updated by bootc` comment.
- Application databases, runtime state, and log directories with significant data are **not** embedded. These appear in the audit report's "Data Migration Plan" section with explicit notes that they need a separate migration strategy.

This is called out prominently in:

1. The audit report's "Data Migration Plan" section
2. Comments in the Containerfile
3. The README's deployment instructions

## CLI Flags Summary

The default run is optimized for speed — it covers the vast majority of systems well without expensive operations. Opt-in flags enable deeper inspection at the cost of time and resources.

| Flag | Default | Effect |
|---|---|---|
| `--output-dir DIR` | `./rhel2bootc-output/` | Directory to write all output artifacts to. Created if it doesn't exist. |
| `--comps-file FILE` | off | Path to a local comps XML file for air-gapped environments where the tool cannot fetch comps from repos at runtime. |
| `--profile NAME` | auto-detect | Override the install profile used for baseline generation (e.g. `server`, `minimal`, `workstation`). Bypasses kickstart file auto-detection, which is useful when SELinux prevents access to `/host/root/`. |
| `--validate` | off | After generating output, run `podman build` against the Containerfile to verify it builds successfully. Reports build errors with context so operators can fix issues before manual review. Requires `podman` on the host or in the tool container. |
| `--config-diffs` | off | Extract RPM defaults via `rpm2cpio` and generate line-by-line diffs for modified config files. Requires RPMs to be in local cache or downloadable from repos. |
| `--deep-binary-scan` | off | Run full `strings` scan on unknown binaries in `/opt` and `/usr/local` for version detection. Slow on large statically-linked binaries. |
| `--query-podman` | off | Connect to the podman socket to enumerate running containers and runtime state beyond what's in unit/compose files. |
| `--push-to-github REPO` | off | Push output to a GitHub repository. Requires confirmation (or `--yes`). Shows total data size before push. |
| `--public` | off | When creating a new GitHub repo, make it public instead of private. |
| `--yes` | off | Skip interactive confirmation prompts (for automation). |

### Build Validation (`--validate`)

When enabled, the tool runs `podman build` against the generated Containerfile after all output artifacts are written. This catches a large class of errors before the operator spends time on manual review:

- Missing dependencies (a package referenced in `RUN dnf install` that doesn't exist in the configured repos)
- Broken COPY paths (a config file referenced in the Containerfile that wasn't written to the `config/` tree)
- Syntax errors in generated systemd units, timer files, or SELinux policy modules
- Base image pull failures (registry auth issues, wrong tag)

The build runs with `--no-cache` to ensure a clean test. On success, the tool reports the image ID and size. On failure, it captures the build log, appends a `build-errors.log` to the output, and adds a summary of failures to the HTML report's warning panel and the audit report.

The resulting image is not pushed or deployed — it's a local build test only. The operator is expected to review, refine, and rebuild before deployment.

Note: validation requires either `podman` available in the tool container (it already is for the container inspector) or access to the host's podman via the socket. It also requires network access to pull the base image and install packages, so it won't work in fully air-gapped runs without a pre-pulled base image.

## Implementation Language

Python makes the most sense — it's available in UBI base images, has good libraries for all of this (`rpm` bindings, `GitPython`, `PyGithub`, `jinja2` for templating the Containerfile), and is readable enough that the heuristic logic in the non-RPM inspector is maintainable.

The tool container is based on UBI and includes the inspection dependencies (`rpm`, `systemd` tools, `podman` CLI for container inspection). Target: `quay.io/yourorg/rhel2bootc:latest`.

## Future Work

The following are out of scope for the POC and v1 but represent the natural evolution of the tool:

**In-place migration.** The logical endpoint is a mode where the tool doesn't just generate artifacts — it applies them. The operational model is: run the tool against one representative host from a pool of identically-configured machines, generate and refine the Containerfile, build the image, then deploy that single image across the fleet via `bootc install-to-filesystem` or `system-reinstall-bootc`. The tool does not need to run against every host — that would produce a separate image per host, which defeats the purpose of image-based management. One image per role, deployed to many hosts, is the bootc model. Host-specific configuration (hostname, network, credentials) is applied at deploy time via kickstart or provisioning tooling. This is deliberately excluded from v1 because the tool's current value proposition is *safe and read-only* — it never touches the source system, which is what makes it trustworthy enough to run against production. The in-place migration mode should only be built once the read-only tool has been used across enough real systems to establish confidence in the accuracy of the generated Containerfiles.

**Fleet analysis mode.** For environments where hosts in the same role have drifted from each other over time, a mode that ingests multiple snapshots from the same nominal role, identifies the common base, and highlights per-host deviations. This helps operators decide which host is the most representative to use as the source for the golden image, and flags hosts that have diverged in ways that need reconciliation before fleet-wide deployment.

**Snapshot diffing and drift detection.** The structured inspection snapshot is independently valuable beyond migration. Diffing snapshots across hosts or across time enables configuration drift detection, compliance auditing, and fleet-wide inventory. A stable, well-documented snapshot schema is the foundation for this.

**Additional distribution support.** The dynamic comps-based baseline generation handles RHEL 9.x and CentOS Stream 9 automatically. RHEL 10 support requires verifying that the comps XML format is compatible and that suitable bootc base images are available. Fedora support would be a natural extension given that Fedora also uses comps and has bootc images.

**Enhanced cron-to-timer conversion.** Deeper semantic analysis of cron jobs to handle edge cases: `MAILTO` conversion to systemd journal notifications, `@reboot` entries mapped to oneshot services, `%` character handling, and environment variable inheritance differences.

**Config file semantic diffing.** Beyond line-level diffs (via `--config-diffs`), understanding the *meaning* of config changes — e.g., recognizing that a change to `MaxClients` in `httpd.conf` is a performance tuning decision vs. a change to `DocumentRoot` which is a structural decision. This would improve the audit report's guidance on which changes to keep vs. reconsider.
