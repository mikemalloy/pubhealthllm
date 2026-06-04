# terraform/backend.tf
# Local state for portfolio use — upgrade to S3 backend for team use
terraform {
  backend "local" {}
}
