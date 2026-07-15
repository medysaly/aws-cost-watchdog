# AWS Cost Watchdog

> Serverless FinOps watchdog for AWS — daily cost digests, idle resource detection, tag enforcement, and cost anomaly alerts, surfaced via Slack, Telegram, and a React dashboard. Provisioned via Terraform, deployed via GitHub Actions OIDC, target steady-state cost **<$2/month**.

Already paid for itself: surfaced a $21/mo zombie QuickSight subscription on the first real run.

## Status

Four Lambdas live, dashboard deployed, everything Terraform-managed and CI-deployed.

| Component | Status |
|---|---|
| Budget kill switch ($40 ceiling) | ✅ Live |
| Terraform remote state (S3 + DynamoDB lock) | ✅ Live |
| GitHub Actions OIDC federation + CI/CD workflows | ✅ Live |
| **Cost digest** — Cost Explorer → Slack + Telegram, daily 9 AM ET | ✅ Live |
| **Idle scanner** — EBS unattached, EC2 stopped, empty S3 buckets, snapshots >90d, daily midnight ET | ✅ Live |
| **Cost anomaly handler** — AWS Cost Anomaly Detection → SNS → Lambda → Slack + Telegram | ✅ Live |
| **Tag enforcement** — AWS Config `required-tags` rule → weekly Lambda → Slack + Telegram | ✅ Live |
| DynamoDB findings table — shared storage across scanner Lambdas | ✅ Live |
| **Dashboard** — React + Vite + Tailwind on S3 + CloudFront + API Gateway | ✅ Live |
| Dashboard CI/CD (auto-build + upload + invalidate CloudFront) | ✅ Live |
| Docs (architecture, threat model, tradeoffs, runbook, cost-of-running) | ⏳ Being written |

## Why this exists

Every team using AWS has someone responsible for keeping the bill predictable and resources tagged correctly. Most teams build something like this in-house. This is a self-contained, open implementation that does four jobs on a serverless stack for under $2/month:

1. **Daily cost digest** — yesterday's spend by service posted to Slack and Telegram every morning
2. **Idle resource detection** — unattached EBS volumes, stopped EC2 instances, empty S3 buckets, old EBS snapshots — findings persist in DynamoDB
3. **Tag enforcement** — AWS Config's `required-tags` rule watches for resources missing `Project`, `Environment`, `ManagedBy` tags; weekly report of violations
4. **Cost anomaly alerts** — AWS Cost Anomaly Detection events (ML-based) relayed via SNS to Slack + Telegram

A React dashboard displays all findings in one view — see [Dashboard](#dashboard) below.

## Architecture

```
                       ┌───────────────────────────────────────────────┐
                       │                    AWS Account                 │
                       │                                                │
   EventBridge cron    │                                                │
   (9 AM ET daily)  ───┼──→ cost_digest_lambda ────────┐               │
                       │                                │               │
   EventBridge cron    │                                │               │
   (midnight daily) ───┼──→ idle_scanner_lambda ───────┤               │
                       │                                │               │
   EventBridge cron    │                                ├─→ Slack       │
   (Monday weekly)  ───┼──→ tag_enforcer_lambda ───────┤               │
                       │                                │               │
   AWS Cost Anomaly    │                                ├─→ Telegram    │
   Detection ───SNS────┼──→ anomaly_handler_lambda ────┘               │
                       │                                                │
                       │   All Lambdas write findings → DynamoDB        │
                       │                                     ↑          │
                       │                                     │ scan     │
                       │   S3 + CloudFront (React) → API Gateway →      │
                       │                              dashboard_reader   │
                       │                                                │
                       │   Secrets Manager: slack-webhook, telegram-bot │
                       │                    (all Lambdas read at start) │
                       │                                                │
                       │   Safety: $40 Budget kill switch → deny policy │
                       └────────────────────────────────────────────────┘
```

A full architecture doc with rendered diagrams will land in `docs/architecture.md`.

## Tech stack

- **IaC**: Terraform 1.13+ with remote state in S3 + DynamoDB lock
- **CI/CD**: GitHub Actions with **OIDC federation** to AWS (zero static keys)
  - `terraform-plan.yml` runs on PR, previews changes
  - `terraform-apply.yml` runs on push to main, deploys via CI
- **Compute**: AWS Lambda (Python 3.12)
- **Scheduling**: Amazon EventBridge Scheduler
- **Data**: DynamoDB (schemaless findings table, shared across scanners)
- **Governance**: AWS Config (`required-tags` managed rule) + AWS Cost Anomaly Detection
- **Frontend**: React + Vite + Tailwind CSS 4 on S3 + CloudFront + API Gateway HTTP API
- **Notifications**: Slack incoming webhook + Telegram Bot API (multi-notifier pattern)
- **Secrets**: AWS Secrets Manager — never `.env`, never `*.tfvars`
- **Least privilege**: separate IAM role per Lambda; inline policies scoped to specific resource ARNs

## Dashboard

Single-page React app that reads from the DynamoDB findings table via API Gateway. Auto-refreshes every 30 seconds — leave it open and new Lambda findings appear without a page reload.

Key elements:
- **4 KPI cards** — total findings, estimated monthly waste, active-vs-monitored category count, last scan time
- **Distribution donut chart** with the total findings count centered in the ring — instant visual + numeric read
- **Monitored categories breakdown** — all 6 category types the watchdog can detect, with progress bars showing distribution. Zero-count categories stay visible but muted, so users see the full monitoring surface.
- **Filter chips** in the findings-table header, sourced from the full category list (grayed-out for empty categories, active for populated ones)
- **Findings table** with color-coded category badges, monospaced resource IDs, right-aligned tabular numbers
- **Manual refresh button** with animated spinner + subtle "auto-refresh 30s" indicator in the header

Frontend deploys automatically on `git push` — `dashboard-deploy.yml` builds React → uploads to S3 → invalidates CloudFront cache. Live in ~2 min.

## Real-world wins

- **$21/mo QuickSight zombie subscription** found and cancelled within the first hour of the cost digest running (~$250/year saved).
- **Daily spend visibility**: baseline ~$0.15/day, dominated by AWS WAF (~$0.12/day) — surfaced in Slack every morning.
- **Idle scanner tested end-to-end**: caught a test EBS volume immediately after creation; finding persisted in DynamoDB, summary posted to both Slack and Telegram.
- **Tag enforcer identifies real drift**: flagged 3 pre-existing S3 buckets (Terraform state bucket, Config's own bucket, an external SAM deployment bucket) as missing required tags.
- **Anomaly handler verified with simulated event**: fake anomaly published to SNS → Lambda parsed and formatted → Slack + Telegram both received the alert.

## Quick start

```bash
# Prereqs: AWS CLI configured, Terraform 1.13+, Python 3.12+, Node.js 20+, gh CLI

# 1. Bootstrap (one-time, manual)
#    - Create $40 budget kill switch in AWS Budgets
#    - Create S3 state bucket + DynamoDB lock table (scripts/bootstrap.sh)
#    - Register GitHub OIDC provider + create IAM role in AWS
#    - Enable AWS Config with narrow resource-type scope

# 2. Initialize Terraform (one-time)
terraform -chdir=terraform init

# 3. Deploy infrastructure — normally via CI (push to main), local also works
git push  # main → terraform-apply.yml runs

# 4. Set secret values (manual, one-time — never commit these)
aws secretsmanager put-secret-value --secret-id watchdog/slack-webhook --secret-string "https://hooks.slack.com/..."
aws secretsmanager put-secret-value --secret-id watchdog/telegram-bot --secret-string '{"bot_token":"...","chat_id":"..."}'

# 5. Dashboard deploys automatically on push — first time, install deps locally so the CI knows about them
cd dashboard/
npm install    # writes package-lock.json (commit this so CI uses `npm ci` deterministically)
cd ..
# From here: any change to dashboard/** + `git push` → CI builds, uploads to S3, invalidates CloudFront

# 6. Test — schedules run automatically, but you can invoke on-demand
aws lambda invoke --function-name watchdog-cost-digest-lambda /tmp/out.json
aws lambda invoke --function-name watchdog-idle-scanner-lambda /tmp/out.json
aws lambda invoke --function-name watchdog-tag-enforcer-lambda /tmp/out.json
aws logs tail /aws/lambda/watchdog-cost-digest-lambda --since 2m
```

## Cost

Target: **under $2/month** in steady state. Current running cost is well under.

Cost drivers:
- **Cost Explorer API**: ~$0.30/month (1 call/day × ~30 days × $0.01)
- **AWS Config** (narrow scope, change-triggered only): ~$0.10-0.20/month
- **Secrets Manager**: $0.40/month per secret × 2 secrets = $0.80
- **DynamoDB**: essentially free (on-demand, tiny row count)
- **Lambda**: essentially free (well within 1M invocations/month free tier)
- **API Gateway HTTP API**: essentially free at this volume
- **CloudFront**: essentially free (permanent free tier: 1 TB transfer + 10M requests/month)
- **S3 + DynamoDB (Terraform state, dashboard bucket)**: pennies
- **EventBridge Scheduler**: free tier covers all schedules

A full monthly breakdown will land in `docs/cost-of-running.md` once the project stabilizes.

## Documentation

*Being written as the project matures. Planned:*

- **Architecture** — system design and component interactions with rendered diagrams
- **Tradeoffs** — design decisions and reasoning (build vs buy, Terraform vs SAM, Config vs custom scan, etc.)
- **Threat model** — security analysis
- **Cost of running** — monthly cost breakdown with actual usage data
- **Runbook** — operational procedures (how to add a Lambda, how to recover from kill switch, etc.)

## Author

Built and maintained by [Mehdi Salhi](mailto:under.salhi@gmail.com).
