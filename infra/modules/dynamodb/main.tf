resource "aws_dynamodb_table" "jobs" {
  #checkov:skip=CKV_AWS_119:Use DynamoDB's AWS-owned encryption key in this learning stack instead of a customer-managed key.
  name                        = var.table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "job_id"
  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "job_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
