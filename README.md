# AWS Cost Watchdog

> Serverless FinOps watchdog for AWS — daily cost digests, idle resource detection, tag enforcement, and anomaly alerts. Provisioned via Terraform, deployed via GitHub Actions OIDC, target steady-state cost **<$2/month**.

Built as a portfolio project for cloud engineering roles. Already paid for itself: surfaced a $21/mo zombie QuickSight subscription on first run.

## Status

🚧 **Under active development.** Started 2026-05-08.

| Component | Status |
|---|---|
| Budget kill switch ($40 ceiling) | ✅ Live |
| Terraform remote state (S3 + DynamoDB lock) | ✅ Live |
| GitHub Actions OIDC federation | ✅ Live |
| **CI/CD** — `terraform-plan.yml` on PR + `terraform-apply.yml` on main | ✅ Live (no more local applies) |
| Cost digest Lambda — Cost Explorer → Slack + Telegram, daily @ 9 AM ET | ✅ Live |
| DynamoDB findings table (shared storage for scanner Lambdas) | ✅ Live |
| Idle resource detection — **EBS unattached volumes**, daily @ midnight ET | ✅ Live |
| Idle detection — EC2 stopped, empty S3 buckets, old snapshots | ⏳ Next |
| Cost anomaly alerts (SNS + Lambda) | ⏳ Not started |
| Tag enforcement (AWS Config) | ⏳ Not started |
| Dashboard (React on S3 + CloudFront + API Gateway) | ⏳ Not started |

## Why this exists

Every team using AWS has someone responsible for keeping the bill predictable and resources tagged correctly. Most teams build something like this in-house. This is a self-contained, open implementation that handles four jobs:

1. **Daily cost digest** — every morning, yesterday's spend by service is posted to Slack and Telegram
2. **Idle resource detection** — unattached EBS volumes, stopped EC2 instances, empty S3 buckets, old snapshots — findings persist in DynamoDB
3. **Tag enforcement** — AWS Config rules ensure every resource has `Project`, `Environment`, and `Owner` tags
4. **Cost anomaly alerts** — AWS Cost Anomaly Detection events relayed to chat

## Architecture

```
                                     ┌─────────────────────┐
                                     │ AWS Cost Explorer   │
                                     └──────────┬──────────┘
                                                │ (yesterday's spend)
   EventBridge cron (9 AM ET) ──→ cost_digest_lambda
                                                │
                                                ├→ POST → Slack
                                                └→ POST → Telegram

                                     ┌────────────────────┐
                                     │ EC2/EBS/S3 APIs    │
                                     └──────────┬─────────┘
                                                │ (unattached volumes, stopped instances)
   EventBridge cron (midnight ET) ──→ idle_scanner_lambda
                                                │
                                                ├→ DynamoDB (watchdog-findings)
                                                ├→ POST → Slack
                                                └→ POST → Telegram

   Secrets (slack-webhook, telegram-bot) ← Secrets Manager ← both Lambdas at cold start
```

See [docs/architecture.md](docs/architecture.md) for full diagrams and component details.

## Tech stack

- **IaC**: Terraform 1.13+ with remote state in S3 + DynamoDB lock
- **CI/CD**: GitHub Actions with **OIDC federation** to AWS (zero static keys)
  - `terraform-plan.yml` runs on PR, previews changes
  - `terraform-apply.yml` runs on push to main, deploys via CI
- **Compute**: AWS Lambda (Python 3.12)
- **Scheduling**: Amazon EventBridge Scheduler (newer than legacy EventBridge Rules)
- **Data**: DynamoDB (findings, dedup cache, audit log)
- **Governance** *(planned)*: AWS Config + AWS Cost Anomaly Detection
- **Frontend** *(planned)*: React + Vite + Tailwind on S3 + CloudFront
- **Notifications**: Slack incoming webhook + Telegram Bot API (multi-notifier pattern)
- **Secrets**: AWS Secrets Manager — never `.env`, never `*.tfvars`
- **Least privilege**: separate IAM role per Lambda; inline policies scoped to specific resource ARNs

## Real-world wins (so far)

- **$21/mo QuickSight zombie subscription** found and cancelled within the first hour of the cost digest running. Would have been ~$250/year if unnoticed.
- **Daily spend visibility**: baseline ~$0.15/day, dominated by AWS WAF (~$0.12/day).
- **Idle scanner tested end-to-end**: caught a test EBS volume the moment it was created; finding persisted in DynamoDB, summary landed in both Slack and Telegram.

## Quick start

```bash
# Prereqs: AWS CLI configured, Terraform 1.13+, Python 3.12+, gh CLI

# 1. Bootstrap (one-time, manual)
#    - Create $40 budget kill switch in AWS Budgets (manual — protects against runaway)
#    - Create S3 state bucket + DynamoDB lock table (CLI commands in scripts/bootstrap.sh, planned)
#    - Register GitHub OIDC provider + create IAM role in AWS (manual)

# 2. Initialize Terraform (one-time)
terraform -chdir=terraform init

# 3. Deploy — normally via CI, but locally works too
git push  # main → terraform-apply.yml runs, applies automatically
# OR: terraform -chdir=terraform apply

# 4. Set secret values (manual, one-time — never commit these)
aws secretsmanager put-secret-value --secret-id watchdog/slack-webhook --secret-string "https://hooks.slack.com/..."
aws secretsmanager put-secret-value --secret-id watchdog/telegram-bot --secret-string '{"bot_token":"...","chat_id":"..."}'

# 5. Test (manual invoke — schedules also run automatically daily)
aws lambda invoke --function-name watchdog-cost-digest-lambda /tmp/out.json
aws lambda invoke --function-name watchdog-idle-scanner-lambda /tmp/out.json
aws logs tail /aws/lambda/watchdog-cost-digest-lambda --since 2m
```

## Cost

Target: **under $2/month** in steady state. Current running cost is well under that.

Cost drivers:
- **Cost Explorer API**: ~$0.30/month (1 call/day × ~30 days × $0.01)
- **Lambda**: essentially free (well within 1M invocations/month free tier)
- **DynamoDB**: essentially free (on-demand, tiny row count)
- **Secrets Manager**: $0.40/month per secret × 2 secrets = $0.80
- **EventBridge Scheduler**: free tier covers all schedules
- **S3 + DynamoDB (Terraform state)**: pennies

Detailed breakdown in [docs/cost-of-running.md](docs/cost-of-running.md) *(coming)*.

## Documentation

- [Architecture](docs/architecture.md) — system design and component interactions
- [Tradeoffs](docs/tradeoffs.md) — design decisions and the reasoning behind them
- [Threat model](docs/threat-model.md) — security analysis
- [Cost of running](docs/cost-of-running.md) — monthly cost breakdown
- [Runbook](docs/runbook.md) — operational procedures

*(Docs are being written as the project matures.)*

## Author

Built by [Mehdi Salhi](mailto:under.salhi@gmail.com) as a portfolio project for cloud engineering / DevOps roles.
