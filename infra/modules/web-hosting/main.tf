resource "aws_s3_bucket" "this" {
  #checkov:skip=CKV2_AWS_6:Public website bucket (user-approved); ACLs stay blocked, reads come from the bucket policy.
  #checkov:skip=CKV_AWS_145:Anonymous website reads cannot use SSE-KMS; contents are public static assets.
  #checkov:skip=CKV_AWS_21:Static assets are rebuilt from git on every deploy; versioning adds no recovery value.
  #checkov:skip=CKV2_AWS_61:Objects are replaced by each deploy (sync --delete); no lifecycle needed.
  bucket        = var.bucket_name
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Anonymous website reads cannot decrypt SSE-KMS objects; the bucket holds only static, public assets.
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  #checkov:skip=CKV_AWS_54:The public-read bucket policy is the hosting mechanism for the S3 website endpoint.
  #checkov:skip=CKV_AWS_56:The public-read bucket policy is the hosting mechanism for the S3 website endpoint.
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

data "aws_iam_policy_document" "public_read" {
  statement {
    sid       = "PublicReadStaticAssets"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.public_read.json

  depends_on = [aws_s3_bucket_public_access_block.this]
}
