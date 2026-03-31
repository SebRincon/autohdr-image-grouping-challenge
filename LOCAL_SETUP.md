# Local Setup

This repo is configured for the 500-image public sample only.

## 1. Download and extract the sample

```bash
scripts/download_sample.sh
```

This creates:

- `data/sample_500/images/`
- `data/sample_500/public_manifest.csv`

## 2. Build and run locally

```bash
scripts/run_local.sh
```

Notes:

- On macOS, the script builds with `--platform linux/amd64`
- Output is written to `output/predictions.csv`
- The `.dockerignore` excludes the dataset so Docker does not upload gigabytes into the build context

For faster iteration on a Mac, you can run the same `solution.py` directly on the host:

```bash
scripts/run_host.sh
```

## 3. Score your predictions on the sample

```bash
python3 scripts/score_sample.py
```

## 4. Fast reruns without rebuilding

```bash
scripts/run_local.sh --skip-build
```

Use `--skip-build` only if the image already exists and you did not change `solution.py`, the `Dockerfile`, or installed dependencies.

## 5. Package a Codabench submission

```bash
scripts/package_submission.sh youruser/autohdr-solution:v1 you@example.com cpu-xlarge
```

This rewrites `submission.yaml` and creates `submission.zip`.

To build the image, push it to Docker Hub, and package `submission.zip` in one flow:

```bash
docker login
scripts/publish_submission.sh youruser/autohdr-solution:v1 you@example.com cpu-xlarge
```
