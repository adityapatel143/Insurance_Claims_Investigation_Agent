output "repository_url" {
  description = "Repository URL used to tag and push the runtime image."
  value       = aws_ecr_repository.runtime.repository_url
}

output "repository_arn" {
  description = "Repository ARN."
  value       = aws_ecr_repository.runtime.arn
}
