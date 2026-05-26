#!/usr/bin/env bash
set -euo pipefail

# AI Visibility — deploy to AWS ECS Fargate
# Usage: ./infra/deploy.sh

REGION="us-east-1"
ACCOUNT_ID="416338226790"
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/ai-visibility"
CLUSTER="ai-visibility"
SERVICE="ai-visibility"

echo "==> Building image (linux/amd64)..."
docker build --platform linux/amd64 -t ai-visibility .

echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Pushing to ECR..."
docker tag ai-visibility:latest "${ECR_REPO}:latest"
docker push "${ECR_REPO}:latest"

echo "==> Deploying to ECS..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --force-new-deployment \
  --region "$REGION" \
  --query "service.deployments[0].status" --output text

echo "==> Waiting for deployment to stabilize..."
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE" --region "$REGION"

echo "==> Done! Site live at:"
echo "    http://ai-visibility-alb-312676641.us-east-1.elb.amazonaws.com"
