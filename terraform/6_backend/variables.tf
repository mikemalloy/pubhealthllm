# terraform/6_backend/variables.tf

variable "project_name" {
  description = "Prefix for all AWS resource names"
  type        = string
  default     = "pubhealth"
}

variable "aws_region" {
  description = "AWS region for Lambda and Bedrock"
  type        = string
  default     = "us-west-1"
}

variable "sagemaker_endpoint" {
  description = "SageMaker embedding endpoint name"
  type        = string
  default     = "pubhealth-embedding-endpoint"
}

variable "vector_bucket" {
  description = "S3 Vectors bucket name (from Stage 3 terraform output)"
  type        = string
}

variable "index_name" {
  description = "S3 Vectors index name"
  type        = string
  default     = "mmwr-reports"
}

variable "aurora_cluster_arn" {
  description = "Aurora Serverless v2 cluster ARN (from Stage 5 terraform output)"
  type        = string
}

variable "aurora_secret_arn" {
  description = "Secrets Manager ARN for Aurora credentials (from Stage 5 terraform output)"
  type        = string
  sensitive   = true
}

variable "aurora_database" {
  description = "Aurora database name"
  type        = string
  default     = "pubhealth"
}

variable "clerk_jwks_url" {
  description = "Clerk JWKS URL for JWT verification (from Clerk dashboard)"
  type        = string
  sensitive   = true
}

variable "cors_origins" {
  description = "Comma-separated list of additional allowed CORS origins (e.g. your Vercel frontend domain)"
  type        = string
  default     = ""
}

variable "lambda_memory_mb" {
  description = "Lambda memory allocation in MB (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "lambda_timeout_s" {
  description = "Lambda timeout in seconds (Nova Pro can be slow; 900 = 15 min max)"
  type        = number
  default     = 900
}
