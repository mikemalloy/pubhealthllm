# terraform/6_backend/outputs.tf

output "function_url" {
  description = "Lambda Function URL — public HTTPS endpoint for the API"
  value       = aws_lambda_function_url.api.function_url
}

output "lambda_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.api.arn
}

output "artifact_bucket" {
  description = "S3 bucket name for Lambda ZIP artifacts (pass to build_lambda.sh)"
  value       = aws_s3_bucket.lambda_artifacts.bucket
}
