# terraform/outputs.tf
output "api_url" {
  description = "App Runner HTTPS endpoint"
  value       = "https://${aws_apprunner_service.backend.service_url}"
}

output "ecr_repository_url" {
  description = "ECR repository URL for docker push"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_url" {
  description = "S3 static website URL"
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

output "frontend_bucket" {
  description = "S3 bucket name for frontend sync"
  value       = aws_s3_bucket.frontend.id
}
