output "aws_region" {
  value = var.aws_region
}

output "cluster_name" {
  description = "Set as the EKS_CLUSTER_NAME repository variable."
  value       = module.eks.cluster_name
}

output "github_actions_role_arn" {
  description = "Set as the AWS_ROLE_ARN repository variable."
  value       = aws_iam_role.github_actions.arn
}

output "ecr_repository_urls" {
  value = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}

output "configure_kubectl" {
  value = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
