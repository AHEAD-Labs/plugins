"""Shared constants for the AWS platform adapter. Everything created is named gmo-* and tagged."""
import boto3

REGION = "us-east-1"
PROJECT_TAG = {"project": "governed-mcp-onboarding"}
TAGS = [{"Key": k, "Value": v} for k, v in PROJECT_TAG.items()]
REPO = "AHEAD-Labs/plugins"
# GitHub issues OIDC subjects from immutable numeric ids for this repo (use_immutable_subject=true), e.g.
#   repo:AHEAD-Labs@9273742/plugins@1455892525:environment:production
# Read it with: gh api repos/AHEAD-Labs/plugins/actions/oidc/customization/sub  (sub_claim_prefix)
SUB_PREFIX = "repo:AHEAD-Labs@9273742/plugins@1455892525"
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
