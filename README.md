# rhel2bootc

Inspect RHEL/CentOS hosts and produce bootc image artifacts (Containerfile, config tree, audit report, etc.).

## Architecture

- **Inspectors** run against a host root (default `/host`) and produce structured JSON (the inspection snapshot).
- **Renderers** consume the snapshot and produce output artifacts (Containerfile, markdown report, HTML report, etc.).

## Usage

All renderers write to the **output directory**, which is created if it does not exist. Default: `./rhel2bootc-output`.

```bash
# Inspect host mounted at /host, write to default ./rhel2bootc-output
rhel2bootc

# Specify output directory
rhel2bootc --output-dir ./my-output
# or: rhel2bootc -o ./my-output

# Save snapshot only (no render)
rhel2bootc --inspect-only -o ./out

# Render from existing snapshot
rhel2bootc --from-snapshot ./out/inspection-snapshot.json -o ./rendered
```

## Development

```bash
pip install -e .
rhel2bootc --help
pytest
```

## Container

Build the tool image:

```bash
podman build -t rhel2bootc .
```

Run it against a host. **Typically you run the container on the host you are inspecting**, so both the host root and the output directory are bind-mounted from that same host. The tool reads the host via `/host` and writes artifacts to `--output-dir`; with the mount below, those artifacts end up on the host at `./rhel2bootc-output`.

```bash
# On the host being inspected: mount its root at /host and a directory on the host for output
podman run --rm \
  -v /:/host:ro \
  -v ./rhel2bootc-output:/output \
  rhel2bootc --output-dir /output
```

After the run, `./rhel2bootc-output` on the host contains the Containerfile, config tree, reports, and snapshot. You can then copy that directory off the host or push it to GitHub with `--push-to-github`. The HTML report (`report.html`) is **self-contained and portable**: all content is embedded, so you can share or archive that file alone.
