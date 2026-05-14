terraform {
  backend "s3" {
    bucket         = "watchdog-tfstate-ms-2026"
    key            = "watchdog/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "watchdog-tflock"
    encrypt        = true
  }
}
