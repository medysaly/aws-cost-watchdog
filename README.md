# AWS Cost Watchdog

> A serverless FinOps watchdog that monitors AWS spend, detects idle resources, enforces tagging hygiene, and alerts to Slack — all running on a schedule for under $2/month.

<!-- Tagline above is the single most important line. Recruiters scan it for 3 seconds. Make sure it states (1) what it is, (2) the differentiator, (3) why it's impressive. -->

## Status

🚧 **Under active development.** Started 2026-05-08, target completion 2026-06-01.

| Component | Status |
|---|---|
| Budget kill switch | ✅ Manual setup complete |
| Terraform remote state | ⏳ Not started |
| GitHub Actions OIDC | ⏳ Not started |
| Cost digest Lambda | ⏳ Not started |
| Idle resource detection | ⏳ Not started |
| Tag enforcement (AWS Config) | ⏳ Not started |
| Cost anomaly alerts | ⏳ Not started |
| Dashboard | ⏳ Not started |

## Why this exists

<!-- This section answers "what problem does this solve" in language a non-engineer can read. -->

Every company using AWS has someone responsible for keeping the bill predictable and resources tagged correctly. Most teams build something like this in-house. This project is a self-contained, open implementation that handles four jobs:

1. **Daily cost digest** — every morning, a summary of yesterday's spend by service is posted to Slack
2. **Idle resource detection** — unattached EBS volumes, stopped EC2 instances, empty S3 buckets, old snapshots, all flagged with optional auto-cleanup
3. **Tag enforcement** — AWS Config rules ensure every resource has `Project`, `Environment`, and `Owner` tags
4. **Cost anomaly alerts** — AWS Cost Anomaly Detection events flow to Slack

## Architecture

<!-- TODO: add architecture diagram here (docs/architecture.md). -->

[Architecture details →](docs/architecture.md)

## Tech stack

- **IaC**: Terraform 1.13+
- **Compute**: AWS Lambda (Python 3.12)
- **CI/CD**: GitHub Actions with OIDC federation to AWS (no static keys)
- **Data**: DynamoDB (findings, dedup cache, audit log)
- **Governance**: AWS Config + AWS Cost Anomaly Detection
- **Frontend**: React + Vite + Tailwind on S3 + CloudFront
- **Notifications**: Slack incoming webhook
- **Secrets**: AWS Secrets Manager

## Quick start

<!-- TODO: fill in once Terraform bootstrap is complete. -->

## Cost

<!-- TODO: real numbers once running for a month. Aim for <$2/mo. -->

Target: under $2/month in steady state. Detailed breakdown in [docs/cost-of-running.md](docs/cost-of-running.md).

## Documentation

- [Architecture](docs/architecture.md) — system design and component interactions
- [Tradeoffs](docs/tradeoffs.md) — design decisions and the reasoning behind them
- [Threat model](docs/threat-model.md) — security analysis
- [Cost of running](docs/cost-of-running.md) — monthly cost breakdown
- [Runbook](docs/runbook.md) — operational procedures

## Author

Built by [Mehdi Salhi](mailto:under.salhi@gmail.com) as a portfolio project for cloud engineering roles.
