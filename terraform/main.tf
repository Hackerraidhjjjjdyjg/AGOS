# AGOS — Terraform Infrastructure as Code
# Provisions cloud resources on AWS (switchable to GCP/Azure)

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "agos-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-west-2"
  }
}

provider "aws" {
  region = var.region
}

# ─── Variables ──────────────────────────────────────────────────
variable "region" {
  default = "us-west-2"
}
variable "environment" {
  default = "production"
}
variable "db_password" {
  sensitive = true
}

# ─── VPC ────────────────────────────────────────────────────────
resource "aws_vpc" "agos" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = { Name = "agos-${var.environment}" }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.agos.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${var.region}a"
  tags = { Name = "agos-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.agos.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.region}b"
  tags = { Name = "agos-private-b" }
}

# ─── EKS Cluster ────────────────────────────────────────────────
resource "aws_eks_cluster" "agos" {
  name     = "agos-${var.environment}"
  role_arn = aws_iam_role.eks.arn

  vpc_config {
    subnet_ids = [
      aws_subnet.private_a.id,
      aws_subnet.private_b.id,
    ]
  }

  tags = {
    Environment = var.environment
    Project     = "agos"
  }
}

resource "aws_eks_node_group" "agos_workers" {
  cluster_name    = aws_eks_cluster.agos.name
  node_group_name = "agos-workers"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  scaling_config {
    desired_size = 3
    max_size     = 10
    min_size     = 2
  }

  instance_types = ["m6i.xlarge"]  # 4 vCPU, 16GB RAM
}

# ─── RDS PostgreSQL ─────────────────────────────────────────────
resource "aws_db_instance" "agos" {
  identifier     = "agos-${var.environment}"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.r6g.large"  # 2 vCPU, 16GB RAM

  allocated_storage     = 100
  max_allocated_storage = 500

  db_name  = "agos_db"
  username = "agos"
  password = var.db_password

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.agos.name

  backup_retention_period = 7
  multi_az               = true
  deletion_protection    = true
  storage_encrypted      = true

  tags = {
    Environment = var.environment
    Project     = "agos"
  }
}

resource "aws_db_subnet_group" "agos" {
  name       = "agos-${var.environment}"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

# ─── ElastiCache Redis ──────────────────────────────────────────
resource "aws_elasticache_cluster" "agos" {
  cluster_id      = "agos-${var.environment}"
  engine          = "redis"
  node_type       = "cache.r6g.large"
  num_cache_nodes = 1

  subnet_group_name  = aws_elasticache_subnet_group.agos.name
  security_group_ids = [aws_security_group.redis.id]
}

resource "aws_elasticache_subnet_group" "agos" {
  name       = "agos-${var.environment}"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

# ─── S3 (File Storage) ──────────────────────────────────────────
resource "aws_s3_bucket" "agos_data" {
  bucket = "agos-data-${var.environment}"
  tags   = { Project = "agos" }
}

resource "aws_s3_bucket_versioning" "agos_data" {
  bucket = aws_s3_bucket.agos_data.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "agos_data" {
  bucket = aws_s3_bucket.agos_data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

# ─── IAM Roles ──────────────────────────────────────────────────
resource "aws_iam_role" "eks" {
  name = "agos-eks-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role" "eks_nodes" {
  name = "agos-eks-nodes-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks.name
}

resource "aws_iam_role_policy_attachment" "eks_worker" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

# ─── Security Groups ────────────────────────────────────────────
resource "aws_security_group" "rds" {
  name   = "agos-rds-${var.environment}"
  vpc_id = aws_vpc.agos.id
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
}

resource "aws_security_group" "redis" {
  name   = "agos-redis-${var.environment}"
  vpc_id = aws_vpc.agos.id
  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
}

# ─── Outputs ────────────────────────────────────────────────────
output "eks_endpoint" {
  value = aws_eks_cluster.agos.endpoint
}
output "rds_endpoint" {
  value = aws_db_instance.agos.endpoint
}
output "redis_endpoint" {
  value = aws_elasticache_cluster.agos.cache_nodes[0].address
}
output "s3_bucket" {
  value = aws_s3_bucket.agos_data.bucket
}
