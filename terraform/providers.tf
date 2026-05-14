provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "aws-cost-watchdog"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

provider "github" {
  owner = "medysaly"
  # Auth via GITHUB_TOKEN env var (already exported in ~/.zshrc)
}