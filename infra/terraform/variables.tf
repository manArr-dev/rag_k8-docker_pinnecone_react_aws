variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name used for the cluster and as a prefix for other resources."
  type        = string
  default     = "rag"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version. Check `aws eks describe-cluster-versions` for what is currently in standard support."
  type        = string
  default     = "1.34"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway instead of one per AZ. Cheaper, but an outage in that AZ cuts outbound access (Pinecone, Anthropic) for every node."
  type        = bool
  default     = true
}

variable "node_instance_types" {
  description = "Instance types for the worker nodes."
  type        = list(string)
  default     = ["m6i.large"]
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 6
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "app_namespace" {
  description = "Kubernetes namespace the GitHub Actions role may deploy into."
  type        = string
  default     = "rag"
}

variable "github_repository" {
  description = "GitHub repository allowed to deploy, as \"owner/repo\"."
  type        = string
}

variable "github_deploy_branch" {
  description = "Only workflow runs on this branch can assume the deploy role."
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set to false if the AWS account already has one (there can only be one per account)."
  type        = bool
  default     = true
}
