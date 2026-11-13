"""Shared constants for the AWS platform adapter. Everything created is named gmo-* and tagged."""
import boto3

REGION = "us-east-1"
PROJECT_TAG = {"project": "governed-mcp-onboarding"}
TAGS = [{"Key": k, "Value": v} for k, v in PROJECT_TAG.items()]
REPO = "AHEAD-Labs/plugins"
LAMBDA_ROLE = "gmo-lambda-role"
DEPLOY_ROLE = "gmo-github-deploy"
FUNCTION = "gmo-project-status"
API_NAME = "gmo-gateway"
BUDGET = "gmo-monthly"


def session(profile: str | None = None):
    return boto3.Session(profile_name=profile, region_name=REGION)


def account(s) -> str:
    return s.client("sts").get_caller_identity()["Account"]


def bucket(acct: str) -> str:
    return f"gmo-state-{acct}"
