output "collection_arn" {
  description = "Collection ARN (aoss:APIAccessAll resource)."
  value       = aws_opensearchserverless_collection.this.arn
}

output "collection_endpoint" {
  description = "Collection endpoint (CLAIMS_OPENSEARCH_ENDPOINT)."
  value       = aws_opensearchserverless_collection.this.collection_endpoint
}

output "collection_name" {
  description = "Collection name."
  value       = aws_opensearchserverless_collection.this.name
}
