output "aurora_cluster_arn" {
  description = "ARN of the Aurora cluster"
  value       = aws_rds_cluster.aurora.arn
}

output "aurora_cluster_endpoint" {
  description = "Writer endpoint"
  value       = aws_rds_cluster.aurora.endpoint
}

output "aurora_secret_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "database_name" {
  description = "Database name"
  value       = aws_rds_cluster.aurora.database_name
}

output "setup_instructions" {
  value = <<-EOT

    Aurora Serverless v2 deployed!

    Add to backend/.env:
    AURORA_CLUSTER_ARN=${aws_rds_cluster.aurora.arn}
    AURORA_SECRET_ARN=${aws_secretsmanager_secret.db_credentials.arn}
    AURORA_DATABASE=pubhealth

    Smoke test:
    aws rds-data execute-statement \
      --resource-arn "${aws_rds_cluster.aurora.arn}" \
      --secret-arn "${aws_secretsmanager_secret.db_credentials.arn}" \
      --database pubhealth \
      --sql "SELECT version()"
  EOT
}
