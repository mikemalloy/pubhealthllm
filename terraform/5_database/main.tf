terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.76"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "pubhealth-aurora-credentials-${random_id.suffix.hex}"
  recovery_window_in_days = 0

  tags = {
    Project = "pubhealth"
    Stage   = "5"
  }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = "pubhealthadmin"
    password = random_password.db_password.result
  })
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_db_subnet_group" "aurora" {
  name       = "pubhealth-aurora-subnet-group"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Project = "pubhealth"
    Stage   = "5"
  }
}

resource "aws_security_group" "aurora" {
  name        = "pubhealth-aurora-sg"
  description = "pubhealth Aurora cluster"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = "pubhealth"
    Stage   = "5"
  }
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier = "pubhealth-aurora-cluster"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = "16.6"
  database_name      = "pubhealth"
  master_username    = "pubhealthadmin"
  master_password    = random_password.db_password.result

  serverlessv2_scaling_configuration {
    min_capacity             = var.min_capacity
    max_capacity             = var.max_capacity
    seconds_until_auto_pause = var.seconds_until_auto_pause
  }

  enable_http_endpoint = true

  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  backup_retention_period      = 1
  preferred_backup_window      = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"
  skip_final_snapshot          = true
  apply_immediately            = true

  tags = {
    Project = "pubhealth"
    Stage   = "5"
  }
}

resource "aws_rds_cluster_instance" "aurora" {
  identifier         = "pubhealth-aurora-instance-1"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version

  performance_insights_enabled = false

  tags = {
    Project = "pubhealth"
    Stage   = "5"
  }
}
