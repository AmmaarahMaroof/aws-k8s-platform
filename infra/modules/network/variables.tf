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