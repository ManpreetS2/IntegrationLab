# Cost-conscious VPC:
# - 2 public subnets (ALB + Fargate tasks with public IPs)
# - 2 private database subnets (RDS only)
# - NO NAT Gateway (intentional portfolio/dev tradeoff)
#
# Stricter production would place ECS in private subnets behind NAT or
# VPC interface endpoints for ECR/Logs/Secrets Manager.

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.name_prefix}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${local.name_prefix}-igw"
  }
}

resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = local.public_subnet_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name_prefix}-public-${count.index + 1}"
    Tier = "public"
  }
}

resource "aws_subnet" "private_db" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = local.private_db_subnet_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name = "${local.name_prefix}-db-${count.index + 1}"
    Tier = "private-db"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${local.name_prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count = 2

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db"
  subnet_ids = aws_subnet.private_db[*].id

  tags = {
    Name = "${local.name_prefix}-db-subnets"
  }
}
