variable "backup_bucket_name" {
  description = "S3 bucket the server may write database backups to (null = no backup access)"
  type        = string
  default     = null
}
