output "state_bucket_name" {
  description = "Use as `bucket` in each environment's backend configuration."
  value       = aws_s3_bucket.state.bucket
}

output "region" {
  description = "Region of the state bucket."
  value       = var.region
}
