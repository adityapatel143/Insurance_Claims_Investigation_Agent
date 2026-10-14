output "queue_arn" {
  description = "Investigation queue ARN."
  value       = aws_sqs_queue.main.arn
}

output "queue_url" {
  description = "Investigation queue URL."
  value       = aws_sqs_queue.main.id
}

output "queue_name" {
  description = "Investigation queue name."
  value       = aws_sqs_queue.main.name
}

output "dlq_arn" {
  description = "Dead-letter queue ARN."
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_name" {
  description = "Dead-letter queue name."
  value       = aws_sqs_queue.dlq.name
}
