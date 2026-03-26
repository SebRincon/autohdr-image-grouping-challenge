# AutoHDR Image Grouping Challenge — Starter Kit

**$50,000 in cash prizes** — Build the best image grouping algorithm.

## The Challenge

You receive a folder of real estate photos from photoshoots. Each photo was taken from a specific camera angle, potentially at multiple exposures (HDR brackets). Your job: **figure out which images belong together** (same camera angle).

## Quick Start

### 1. Register
Sign up at **[bounty.autohdr.com](https://bounty.autohdr.com)** and verify your phone number.

### 2. Join the Competition
[Join on Codabench](https://www.codabench.org/competitions/15267/?secret_key=f8f2b5ab-b63e-4e5a-aec6-8575936dbb56)

### 3. Build Your Solution

Edit `solution.py` with your grouping algorithm, then build:

```bash
docker build --platform linux/amd64 -t yourusername/my-solution:v1 .
docker push yourusername/my-solution:v1
```

> **Mac users:** The `--platform linux/amd64` flag is required. Without it, your container will crash.

### 4. Submit

Edit `submission.yaml` with your Docker image name and registered email:

```yaml
docker_image: yourusername/my-solution:v1
machine_type: cpu-xlarge
email: your-registered-email@example.com
```

ZIP it and upload on the Codabench competition page:

```bash
zip submission.zip submission.yaml
```

## Container Contract

Your Docker container must:

| | Path | Details |
|---|---|---|
| **Read** | `/input/images/` | JPEG images (read-only) |
| **Write** | `/output/predictions.csv` | Your grouping predictions |

### predictions.csv format

```csv
filename,group_id
a7f3b2c1.jpg,0
d4e5f6a7.jpg,0
b8c9d0e1.jpg,1
f2a3b4c5.jpg,2
f2a3b4c5.jpg,2
```

- Images with the same `group_id` are in the same group
- `group_id` can be any string or number
- Order doesn't matter

## Scoring

```
score = exact_matches / total_groups
```

A predicted group counts as a match **only if the set of filenames exactly matches** a reference group. No partial credit — one missing or extra file means no match for that group.

## Machine Types

| Type | vCPU | RAM | Timeout |
|------|------|-----|---------|
| `cpu-large` | 8 | 16 GB | 60 min |
| `cpu-xlarge` | 16 | 32 GB | 60 min |

## Files in This Repo

- `solution.py` — Starter template for your algorithm
- `Dockerfile` — Docker build file
- `submission.yaml` — Codabench submission config template
- `SUBMISSION_GUIDE.md` — Detailed submission instructions
- `SCORING.md` — How scoring works with examples

## Tips

- Images are resized to 1024px max dimension
- Filenames are randomized UUIDs — no metadata hints there
- The test set has ~69K images across ~19K groups
- Most groups are 3 or 5 images (typical HDR brackets)
- Your container has **no internet access** during execution
- Print progress to stdout — it shows up in the submission logs

## Links

- [Register](https://bounty.autohdr.com)
- [Competition Page](https://www.codabench.org/competitions/15267/?secret_key=f8f2b5ab-b63e-4e5a-aec6-8575936dbb56)
- [Discord](https://discord.gg/RWrAN8Xv)
