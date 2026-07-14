resource "aws_secretsmanager_secret" "slack_webhook" {
  name        = "watchdog/slack-webhook"
  description = "slack incoming webhook url for watchdog"

}

# Lambda execution role for cost_digest
resource "aws_iam_role" "cost_digest_lambda" {
  name = "watchdog-cost-digest-lambda-role"


  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      },
    ]
  })
}

# Attach AWS-managed CloudWatch Logs policy to the cost_digest Lambda role
resource "aws_iam_role_policy_attachment" "cost_digest_lambda_logs" {
  role       = aws_iam_role.cost_digest_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Zip the Lambda Python code at plan-time
data "archive_file" "cost_digest" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/cost_digest/handler.py"
  output_path = "${path.module}/builds/cost_digest.zip"
}

# The actual Lambda function in AWS
resource "aws_lambda_function" "cost_digest" {
  function_name    = "watchdog-cost-digest-lambda"
  role             = aws_iam_role.cost_digest_lambda.arn
  filename         = data.archive_file.cost_digest.output_path
  source_code_hash = data.archive_file.cost_digest.output_base64sha256
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 30
}

# Inline policy: allow cost_digest Lambda to call Cost Explorer GetCostAndUsage
# Source: registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy
resource "aws_iam_role_policy" "cost_digest_lambda_ce" {
  name = "cost-explorer-read"
  role = aws_iam_role.cost_digest_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ce:GetCostAndUsage"
        Resource = "*"
      }
    ]
  })
}

# Inline policy: allow cost_digest Lambda to read watchdog/* secrets
# Source: registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy
resource "aws_iam_role_policy" "cost_digest_lambda_secrets" {
  name = "secrets-manager-read"
  role = aws_iam_role.cost_digest_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:us-east-1:992550705663:secret:watchdog/*"
      }
    ]
  })
}


# Telegram bot credentials — value is JSON: {"bot_token": "...", "chat_id": "..."}
resource "aws_secretsmanager_secret" "telegram_bot" {
  name        = "watchdog/telegram-bot"
  description = "Telegram bot token + chat ID for FinOps notifications — value set manually"
}


# IAM role: EventBridge Scheduler assumes this to invoke our Lambda
resource "aws_iam_role" "scheduler_cost_digest" {
  name = "watchdog-scheduler-cost-digest-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# Inline policy: scheduler can invoke the cost_digest Lambda (and nothing else)
resource "aws_iam_role_policy" "scheduler_invoke_cost_digest" {
  name = "invoke-cost-digest-lambda"
  role = aws_iam_role.scheduler_cost_digest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.cost_digest.arn
      }
    ]
  })
}

# The daily schedule
# Source: registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/scheduler_schedule
resource "aws_scheduler_schedule" "cost_digest_daily" {
  name = "watchdog-cost-digest-daily"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 9 * * ? *)"
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = aws_lambda_function.cost_digest.arn
    role_arn = aws_iam_role.scheduler_cost_digest.arn
  }
}

# DynamoDB table: shared storage for findings from idle scanner, tag enforcer, anomaly handler
# Source: registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/dynamodb_table
# Schemaless except for the partition key (other attributes added per-item by the writers)
resource "aws_dynamodb_table" "findings" {
  name         = "watchdog-findings"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "finding_id"

  attribute {
    name = "finding_id"
    type = "S"
  }
}

# ============================================================
# Idle Resource Scanner Lambda — IAM role + permissions
# ============================================================

# Lambda execution role for idle_scanner
resource "aws_iam_role" "idle_scanner_lambda" {
  name = "watchdog-idle-scanner-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# CloudWatch Logs (AWS-managed)
resource "aws_iam_role_policy_attachment" "idle_scanner_logs" {
  role       = aws_iam_role.idle_scanner_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Read-only EC2 access
resource "aws_iam_role_policy" "idle_scanner_ec2_read" {
  name = "ec2-describe"
  role = aws_iam_role.idle_scanner_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeVolumes",
          "ec2:DescribeInstances",
          "ec2:DescribeSnapshots",
        ]
        Resource = "*"
      }
    ]
  })
}

# Write findings to DynamoDB
resource "aws_iam_role_policy" "idle_scanner_dynamodb_write" {
  name = "dynamodb-write-findings"
  role = aws_iam_role.idle_scanner_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "dynamodb:PutItem"
        Resource = aws_dynamodb_table.findings.arn
      }
    ]
  })
}

# Read watchdog/* secrets
resource "aws_iam_role_policy" "idle_scanner_secrets_read" {
  name = "secrets-manager-read"
  role = aws_iam_role.idle_scanner_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:us-east-1:992550705663:secret:watchdog/*"
      }
    ]
  })
}

# Read-only S3 access (for finding empty buckets)
resource "aws_iam_role_policy" "idle_scanner_s3_read" {
  name = "s3-list-read"
  role = aws_iam_role.idle_scanner_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListAllMyBuckets",
          "s3:ListBucket",
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# Idle Resource Scanner Lambda — function
# ============================================================

data "archive_file" "idle_scanner" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/idle_scanner/handler.py"
  output_path = "${path.module}/builds/idle_scanner.zip"
}

resource "aws_lambda_function" "idle_scanner" {
  function_name    = "watchdog-idle-scanner-lambda"
  role             = aws_iam_role.idle_scanner_lambda.arn
  filename         = data.archive_file.idle_scanner.output_path
  source_code_hash = data.archive_file.idle_scanner.output_base64sha256
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 60
}

# ============================================================
# Idle Scanner Schedule — nightly cron
# ============================================================

# IAM role: EventBridge Scheduler assumes this to invoke the idle scanner Lambda
resource "aws_iam_role" "scheduler_idle_scanner" {
  name = "watchdog-scheduler-idle-scanner-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# Inline policy: scheduler can invoke ONLY the idle scanner Lambda
resource "aws_iam_role_policy" "scheduler_invoke_idle_scanner" {
  name = "invoke-idle-scanner-lambda"
  role = aws_iam_role.scheduler_idle_scanner.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.idle_scanner.arn
      }
    ]
  })
}

# The nightly schedule (midnight ET)
resource "aws_scheduler_schedule" "idle_scanner_daily" {
  name = "watchdog-idle-scanner-daily"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 0 * * ? *)"
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = aws_lambda_function.idle_scanner.arn
    role_arn = aws_iam_role.scheduler_idle_scanner.arn
  }
}

# ============================================================
# Anomaly Handler Lambda — IAM role + permissions
# ============================================================

resource "aws_iam_role" "anomaly_handler_lambda" {
  name = "watchdog-anomaly-handler-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "anomaly_handler_logs" {
  role       = aws_iam_role.anomaly_handler_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "anomaly_handler_secrets_read" {
  name = "secrets-manager-read"
  role = aws_iam_role.anomaly_handler_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:us-east-1:992550705663:secret:watchdog/*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "anomaly_handler_dynamodb_write" {
  name = "dynamodb-write-findings"
  role = aws_iam_role.anomaly_handler_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "dynamodb:PutItem"
        Resource = aws_dynamodb_table.findings.arn
      }
    ]
  })
}

# ============================================================
# Anomaly Handler Lambda — function + SNS trigger (Terraform-managed)
# ============================================================

# SNS topic
resource "aws_sns_topic" "anomaly_alerts" {
  name = "watchdog-anomaly-alerts"
}

# Topic policy: allow Cost Anomaly Detection to publish
resource "aws_sns_topic_policy" "anomaly_alerts_ce_publish" {
  arn = aws_sns_topic.anomaly_alerts.arn

  policy = jsonencode({
    Version = "2008-10-17"
    Id      = "watchdog-anomaly-alerts-policy"
    Statement = [
      {
        Sid       = "AllowCostAnomalyDetectionToPublish"
        Effect    = "Allow"
        Principal = { Service = "costalerts.amazonaws.com" }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.anomaly_alerts.arn
      }
    ]
  })
}

# Zip the Lambda source
data "archive_file" "anomaly_handler" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/anomaly_handler/handler.py"
  output_path = "${path.module}/builds/anomaly_handler.zip"
}

# The Lambda function
resource "aws_lambda_function" "anomaly_handler" {
  function_name    = "watchdog-anomaly-handler-lambda"
  role             = aws_iam_role.anomaly_handler_lambda.arn
  filename         = data.archive_file.anomaly_handler.output_path
  source_code_hash = data.archive_file.anomaly_handler.output_base64sha256
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 30
}

# Allow SNS to invoke the Lambda
resource "aws_lambda_permission" "sns_invoke_anomaly_handler" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.anomaly_handler.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.anomaly_alerts.arn
}

# Subscribe the Lambda to the SNS topic
resource "aws_sns_topic_subscription" "anomaly_handler_from_sns" {
  topic_arn = aws_sns_topic.anomaly_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.anomaly_handler.arn
}

# ============================================================
# Tag Enforcer Lambda — IAM role + permissions
# ============================================================

resource "aws_iam_role" "tag_enforcer_lambda" {
  name = "watchdog-tag-enforcer-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "tag_enforcer_logs" {
  role       = aws_iam_role.tag_enforcer_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "tag_enforcer_config_read" {
  name = "config-compliance-read"
  role = aws_iam_role.tag_enforcer_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "config:GetComplianceDetailsByConfigRule",
          "config:DescribeComplianceByConfigRule",
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "tag_enforcer_dynamodb_write" {
  name = "dynamodb-write-findings"
  role = aws_iam_role.tag_enforcer_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "dynamodb:PutItem"
        Resource = aws_dynamodb_table.findings.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "tag_enforcer_secrets_read" {
  name = "secrets-manager-read"
  role = aws_iam_role.tag_enforcer_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:us-east-1:992550705663:secret:watchdog/*"
      }
    ]
  })
}


# ============================================================
# Tag Enforcer Lambda — function + weekly schedule
# ============================================================

# Zip the Lambda source
data "archive_file" "tag_enforcer" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/tag_enforcer/handler.py"
  output_path = "${path.module}/builds/tag_enforcer.zip"
}

# The Lambda function
resource "aws_lambda_function" "tag_enforcer" {
  function_name    = "watchdog-tag-enforcer-lambda"
  role             = aws_iam_role.tag_enforcer_lambda.arn
  filename         = data.archive_file.tag_enforcer.output_path
  source_code_hash = data.archive_file.tag_enforcer.output_base64sha256
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 60
}

# IAM role: EventBridge Scheduler assumes this to invoke our Lambda
resource "aws_iam_role" "scheduler_tag_enforcer" {
  name = "watchdog-scheduler-tag-enforcer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# Inline policy: scheduler can invoke ONLY the tag enforcer Lambda
resource "aws_iam_role_policy" "scheduler_invoke_tag_enforcer" {
  name = "invoke-tag-enforcer-lambda"
  role = aws_iam_role.scheduler_tag_enforcer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.tag_enforcer.arn
      }
    ]
  })
}

# Weekly schedule (Monday 9 AM ET)
resource "aws_scheduler_schedule" "tag_enforcer_weekly" {
  name = "watchdog-tag-enforcer-weekly"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 9 ? * MON *)"
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = aws_lambda_function.tag_enforcer.arn
    role_arn = aws_iam_role.scheduler_tag_enforcer.arn
  }
}

# ============================================================
# Dashboard Reader Lambda — IAM role + permissions
# ============================================================

resource "aws_iam_role" "dashboard_reader_lambda" {
  name = "watchdog-dashboard-reader-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "dashboard_reader_logs" {
  role       = aws_iam_role.dashboard_reader_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "dashboard_reader_dynamodb_read" {
  name = "dynamodb-read-findings"
  role = aws_iam_role.dashboard_reader_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "dynamodb:Scan"
        Resource = aws_dynamodb_table.findings.arn
      }
    ]
  })
}


# ============================================================
# Dashboard Reader Lambda — function
# ============================================================

data "archive_file" "dashboard_reader" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/dashboard_reader/handler.py"
  output_path = "${path.module}/builds/dashboard_reader.zip"
}

resource "aws_lambda_function" "dashboard_reader" {
  function_name    = "watchdog-dashboard-reader-lambda"
  role             = aws_iam_role.dashboard_reader_lambda.arn
  filename         = data.archive_file.dashboard_reader.output_path
  source_code_hash = data.archive_file.dashboard_reader.output_base64sha256
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 30
}
