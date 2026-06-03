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
