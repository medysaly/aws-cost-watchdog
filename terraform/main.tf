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
