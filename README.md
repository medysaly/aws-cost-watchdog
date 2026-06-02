# AWS Cost Watchdog

> Serverless FinOps watchdog for AWS — daily cost digests, idle resource detection, tag enforcement, and anomaly alerts. Provisioned via Terraform, deployed via GitHub Actions OIDC, target steady-state cost **<$2/month**.

Built as a portfolio project for cloud engineering roles. Already paid for itself: surfaced a $21/mo zombie QuickSight subscription on first run.

## Status

🚧 **Under active development.** Started 2026-05-08, target completion 2026-06-01.

| Component | Status |
|---|---|
| Budget kill switch ($40 ceiling) | ✅ Live |
| Terraform remote state (S3 + DynamoDB) | ✅ Live |
| GitHub Actions OIDC federation | ✅ Live (smoke test passing) |
| Cost digest Lambda — Cost Explorer + multi-notifier (Slack + Telegram) | ✅ Works on manual invoke |
| EventBridge daily cron | ⏳ Next |
| Idle resource detection | ⏳ Not started |
| Tag enforcement (AWS Config) | ⏳ Not started |
| Cost anomaly alerts | ⏳ Not started |
| Dashboard (React on S3 + CloudFront) | ⏳ Not started |

## Why this exists

Every team using AWS has someone responsible for keeping the bill predictable and resources tagged correctly. Most teams build something like this in-house. This is a self-contained, open implementation that handles four jobs:

1. **Daily cost digest** — every morning, yesterday's spend by service is posted to Slack and Telegram
2. **Idle resource detection** — unattached EBS volumes, stopped EC2 instances, empty S3 buckets, old snapshots
3. **Tag enforcement** — AWS Config rules ensure every resource has `Project`, `Environment`, and `Owner` tags
4. **Cost anomaly alerts** — AWS Cost Anomaly Detection events relayed to chat

## Architecture

```
EventBridge cron ───→ cost_digest_lambda ───→ Cost Explorer API
                            │                 │
                            │                 └→ Secrets Manager (slack-webhook, telegram-bot)
                            │
                            ├──→ POST to Slack
                            └──→ POST to Telegram
```

See [docs/architecture.md](docs/architecture.md) for the full diagram and component details.

## Tech stack

- **IaC**: Terraform 1.13+ with remote state in S3 + DynamoDB lock
- **Compute**: AWS Lambda (Python 3.12)
- **CI/CD**: GitHub Actions with **OIDC federation** to AWS (zero static keys)
- **Data**: DynamoDB (findings, dedup cache, audit log)
- **Governance**: AWS Config + AWS Cost Anomaly Detection
- **Frontend**: React + Vite + Tailwind on S3 + CloudFront *(planned)*
- **Notifications**: Slack incoming webhook + Telegram Bot API (multi-notifier pattern)
- **Secrets**: AWS Secrets Manager — never `.env`, never `*.tfvars`

## Real-world wins (so far)

- **$21/mo QuickSight zombie subscription found and cancelled** within the first hour of running the cost digest manually. Would have been ~$250/year if unnoticed.
- Daily spend visibility: ~$0.15/day baseline, dominated by AWS WAF.

## Quick start

```bash
# Prereqs: AWS CLI configured, Terraform 1.13+, Python 3.12+, gh CLI

# 1. Bootstrap (one-time, manual)
#    - Create $40 budget kill switch in AWS Budgets (manual)
#    - Create S3 state bucket + DynamoDB lock table (CLI commands in scripts/bootstrap.sh, planned)
#    - Set up GitHub Actions OIDC role in IAM (manual)

# 2. Initialize and apply Terraform
terraform -chdir=terraform init
terraform -chdir=terraform plan
terraform -chdir=terraform apply

# 3. Set secret values (manual, one-time)
aws secretsmanager put-secret-value --secret-id watchdog/slack-webhook --secret-string "https://hooks.slack.com/..."
aws secretsmanager put-secret-value --secret-id watchdog/telegram-bot --secret-string '{"bot_token":"...","chat_id":"..."}'

# 4. Test (manual invoke)
aws lambda invoke --function-name watchdog-cost-digest-lambda /tmp/out.json
aws logs tail /aws/lambda/watchdog-cost-digest-lambda --since 2m
```

## Cost

Target: **under $2/month** in steady state. Detailed breakdown in [docs/cost-of-running.md](docs/cost-of-running.md) *(coming)*. Most services hit the AWS free tier; Cost Explorer API is the main per-call cost (~$0.30/month for daily runs).

## Documentation

- [Architecture](docs/architecture.md) — system design and component interactions
- [Tradeoffs](docs/tradeoffs.md) — design decisions and the reasoning behind them
- [Threat model](docs/threat-model.md) — security analysis
- [Cost of running](docs/cost-of-running.md) — monthly cost breakdown
- [Runbook](docs/runbook.md) — operational procedures

## Author

Built by [Mehdi Salhi](mailto:under.salhi@gmail.com) as a portfolio project for cloud engineering / DevOps roles.
