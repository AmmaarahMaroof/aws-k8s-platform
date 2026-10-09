terraform {
  required_version = ">= 1.10"

  # This environment's state gets its own file in the same bucket
  backend "s3" {
    bucket       = "uptime-monitor-tfstate-099021515478"
    key          = "envs/prod/terraform.tfstate"
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

  default_tags {
    tags = {
      Project     = "uptime-monitor"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

# Prod's settings, all in one place
locals {
  name = "uptime-prod"
}

variable "http_allowed_cidr" {
  description = "Your IP/32, allowed to reach the app on port 80. Set in terraform.tfvars (gitignored) or TF_VAR_http_allowed_cidr."
  type        = string
}

# Use the network module with prod's values
module "network" {
  source = "../../modules/network"

  name               = local.name
  vpc_cidr           = "10.1.0.0/16"
  public_subnet_cidr = "10.1.1.0/24"
  availability_zone  = "eu-west-2a"
  http_allowed_cidr  = "84.68.198.220/32"
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_id" {
  value = module.network.public_subnet_id
}

module "compute" {
  source             = "../../modules/compute"
  name               = local.name
  subnet_id          = module.network.public_subnet_id
  security_group_ids = [module.network.app_security_group_id]
}

output "instance_id" {
  value = module.compute.instance_id
}

output "public_ip" {
  value = module.compute.public_ip
}
