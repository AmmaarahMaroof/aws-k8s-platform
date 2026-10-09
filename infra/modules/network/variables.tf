variable "name" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_cidr" {
  description = "IP range for the whole VPC"
  type        = string
}

variable "public_subnet_cidr" {
  description = "IP range for the public subnet (must sit inside the VPC range)"
  type        = string
}

variable "availability_zone" {
  description = "Which AWS data centre the subnet lives in"
  type        = string
}

variable "http_allowed_cidr" {
  description = "Single CIDR allowed to reach the app on port 80 (e.g. your home IP/32). Kept out of Git."
  type        = string
}