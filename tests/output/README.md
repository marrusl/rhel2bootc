# rhel2bootc output

Generated from **Red Hat Enterprise Linux 9.6 (Plow)**.

## Build

```bash
podman build -t my-bootc-image .
```

## Deploy

```bash
# After building, switch to the new image:
bootc switch my-bootc-image:latest
```

## Artifacts

- `Containerfile` — image definition
- `config/` — files to COPY into the image
- `audit-report.md` — full findings
- `report.html` — interactive report
- `secrets-review.md` — redacted items to handle manually
- `inspection-snapshot.json` — raw data for re-rendering

## Warnings / FIXMEs

- Could not determine original install profile. Using 'minimal' baseline. Some packages reported as 'added' may have been part of the original installation.
