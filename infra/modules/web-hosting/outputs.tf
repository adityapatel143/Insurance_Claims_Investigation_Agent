output "bucket_name" {
  description = "Static web app bucket name."
  value       = aws_s3_bucket.this.bucket
}

output "website_url" {
  description = "S3 website URL (HTTP only); add it to the platform's web_allowed_origins."
  value       = "http://${aws_s3_bucket_website_configuration.this.website_endpoint}"
}
