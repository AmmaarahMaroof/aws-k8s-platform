variable "name" {
  description = "Repository name"
  type        = string
}

variable "images_to_keep" {
  description = "How many images to keep before old ones are deleted"
  type        = number
  default     = 5
}

resource "aws_ecr_repository" "this" {
  name = var.name

  # IMMUTABLE = once a tag like "abc123" is pushed, it can never be overwritten
  image_tag_mutability = "IMMUTABLE"

  # Scan every image for known vulnerabilities when it's pushed
  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# Delete old images automatically so storage (and cost) stays tiny
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.images_to_keep
      }
      action = { type = "expire" }
    }]
  })
}

output "repository_url" {
  value = aws_ecr_repository.this.repository_url
}