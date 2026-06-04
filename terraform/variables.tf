# terraform/variables.tf
variable "project_name" {
  description = "Prefix for all AWS resource names"
  type        = string
  default     = "drug-discovery"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "app_runner_cpu" {
  description = "vCPU allocation for App Runner"
  type        = string
  default     = "1 vCPU"
}

variable "app_runner_memory" {
  description = "Memory allocation for App Runner"
  type        = string
  default     = "3 GB"
}

variable "clerk_jwks_url" {
  description = "Clerk JWKS URL for backend JWT verification (from Clerk dashboard)"
  type        = string
}
