# terraform/6_backend/terraform.tfvars
# Non-sensitive variable values for the Lambda backend.
# Sensitive vars (aurora_secret_arn, clerk_jwks_url) must be passed via:
#   -var="aurora_secret_arn=..." or TF_VAR_aurora_secret_arn environment variable.

project_name       = "pubhealth"
aws_region         = "us-west-1"
sagemaker_endpoint = "pubhealth-embedding-endpoint"
vector_bucket      = "pubhealth-vectors-724533161045"
index_name         = "mmwr-reports"
aurora_cluster_arn = "arn:aws:rds:us-west-1:724533161045:cluster:pubhealth-aurora-cluster"
aurora_database    = "pubhealth"
cors_origins       = "https://pubhealth.chefmike.dev"
lambda_memory_mb   = 1024
lambda_timeout_s   = 900
