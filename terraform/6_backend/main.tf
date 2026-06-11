# terraform/6_backend/main.tf
# pubHealthLLM API Lambda — ZIP deployment behind a public Function URL.
# Clerk JWT is validated inside FastAPI; Function URL uses authorization_type = "NONE".

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.76"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# S3 artifact bucket — stores Lambda ZIP (file may exceed 50 MB direct limit)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "lambda_artifacts" {
  bucket        = "${var.project_name}-lambda-artifacts-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Project = var.project_name
    Stage   = "6"
  }
}

resource "aws_s3_bucket_versioning" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ---------------------------------------------------------------------------
# IAM execution role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api_lambda" {
  name               = "${var.project_name}-api-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Project = var.project_name
    Stage   = "6"
  }
}

# CloudWatch Logs write access
resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.api_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api_permissions" {
  # Bedrock — Nova Pro inference via IAM (no API key)
  statement {
    sid = "BedrockInvoke"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.nova-pro-v1:0",
      "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:inference-profile/us.amazon.nova-pro-v1:0",
    ]
  }

  # SageMaker — sentence embedding endpoint
  statement {
    sid     = "SageMakerInvoke"
    actions = ["sagemaker:InvokeEndpoint"]
    resources = [
      "arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.sagemaker_endpoint}",
    ]
  }

  # S3 Vectors — MMWR vector index queries
  statement {
    sid     = "S3VectorsAccess"
    actions = [
      "s3vectors:QueryVectors",
      "s3vectors:GetVectors",
      "s3vectors:DescribeVectorBucket",
    ]
    resources = [
      "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${var.vector_bucket}",
      "arn:aws:s3vectors:${var.aws_region}:${data.aws_caller_identity.current.account_id}:bucket/${var.vector_bucket}/index/${var.index_name}",
    ]
  }

  # Aurora Data API — CDC PLACES + mortality queries
  statement {
    sid = "AuroraDataAPI"
    actions = [
      "rds-data:ExecuteStatement",
      "rds-data:BatchExecuteStatement",
      "rds-data:BeginTransaction",
      "rds-data:CommitTransaction",
      "rds-data:RollbackTransaction",
    ]
    resources = [var.aurora_cluster_arn]
  }

  # Secrets Manager — Aurora credentials (password fetched per connection)
  statement {
    sid       = "SecretsManagerRead"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.aurora_secret_arn]
  }
}

resource "aws_iam_role_policy" "api_permissions" {
  name   = "${var.project_name}-api-lambda-permissions"
  role   = aws_iam_role.api_lambda.id
  policy = data.aws_iam_policy_document.api_permissions.json
}

# ---------------------------------------------------------------------------
# Lambda function (ZIP uploaded to S3 by scripts/build_lambda.sh)
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "api" {
  function_name = "${var.project_name}-api"
  role          = aws_iam_role.api_lambda.arn

  # ZIP uploaded by scripts/build_lambda.sh before terraform apply
  s3_bucket = aws_s3_bucket.lambda_artifacts.bucket
  s3_key    = "pubhealth-backend.zip"

  handler     = "lambda_handler.handler"
  runtime     = "python3.12"
  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_s
  architectures = ["x86_64"]

  # Limit concurrency — Nova Pro is expensive; tune up if needed
  reserved_concurrent_executions = 10

  environment {
    variables = {
      PUBHEALTH_MODEL    = "bedrock:us.amazon.nova-pro-v1:0"
      AWS_REGION         = var.aws_region
      BEDROCK_REGION     = var.aws_region
      SAGEMAKER_ENDPOINT = var.sagemaker_endpoint
      VECTOR_BUCKET      = var.vector_bucket
      INDEX_NAME         = var.index_name
      AURORA_CLUSTER_ARN = var.aurora_cluster_arn
      AURORA_SECRET_ARN  = var.aurora_secret_arn
      AURORA_DATABASE    = var.aurora_database
      CLERK_JWKS_URL     = var.clerk_jwks_url
      CORS_ORIGINS       = var.cors_origins
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.basic_execution,
    aws_iam_role_policy.api_permissions,
    aws_s3_bucket.lambda_artifacts,
  ]

  tags = {
    Project = var.project_name
    Stage   = "6"
  }
}

# ---------------------------------------------------------------------------
# Function URL — public HTTPS, Clerk JWT validated inside FastAPI
# ---------------------------------------------------------------------------

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_headers     = ["Authorization", "Content-Type"]
    allow_methods     = ["GET", "POST", "OPTIONS"]
    allow_origins     = ["*"]
    max_age           = 86400
  }
}

resource "aws_lambda_permission" "function_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
