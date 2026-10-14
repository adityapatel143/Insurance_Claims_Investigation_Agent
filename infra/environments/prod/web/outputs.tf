output "web_bucket_name" {
  description = "Bucket that scripts/sh/web_deploy.sh syncs the web app into."
  value       = module.web.bucket_name
}

output "website_url" {
  description = "Web app URL (HTTP only); add it to platform web_allowed_origins."
  value       = module.web.website_url
}
