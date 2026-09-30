terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket       = "uptime-monitor-tfstate-099021515478"
    key          = "bootstrap/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "eu-west-2"

  # Every resource gets these tags automatically
  default_tags {
    tags = {
      Project   = "uptime-monitor"
      ManagedBy = "terraform"
    }
  }
}

# Bucket names must be unique across ALL of AWS, so include your account ID
resource "aws_s3_bucket" "tf_state" {
  bucket = "uptime-monitor-tfstate-099021515478"


  # Stops "terraform destroy" from deleting your state by accident
  lifecycle {
    prevent_destroy = true
  }
}

# Keep every old version of the state, so a mistake can be rolled back
resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt the state at rest (it can contain sensitive values)
resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# The state must never be public
resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "state_bucket_name" {
  value = aws_s3_bucket.tf_state.bucket
}