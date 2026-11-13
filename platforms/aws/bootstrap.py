"""One-time, idempotent AWS guardrails + roles. Creates only gmo-* resources, tagged.

  uv run --extra aws python platforms/aws/bootstrap.py [--profile P] [--budget-usd 25] [--email you@x]
  uv run --extra aws python platforms/aws/bootstrap.py --destroy     # remove everything it made

Creates: monthly budget, S3 state bucket (revocations), GitHub OIDC provider, Lambda execution
role, GitHub deploy role (assumable only by the production environment of the repo).
"""
import argparse, json, sys

from botocore.exceptions import ClientError

from common import *  # noqa

GH_OIDC = "token.actions.githubusercontent.com"


def ensure_budget(s, acct, usd, email):
    b = s.client("budgets", region_name="us-east-1")
    try:
        b.describe_budget(AccountId=acct, BudgetName=BUDGET)
        print("budget exists")
    except ClientError:
        b.create_budget(AccountId=acct, Budget={
            "BudgetName": BUDGET, "BudgetType": "COST", "TimeUnit": "MONTHLY",
            "BudgetLimit": {"Amount": str(usd), "Unit": "USD"},
            "CostFilters": {"TagKeyValue": ["user:project$governed-mcp-onboarding"]}})
        print(f"budget created: ${usd}/month (tag-filtered)")
    if email:
        try:
            b.create_notification(AccountId=acct, BudgetName=BUDGET, Notification={
                "NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN",
                "Threshold": 80, "ThresholdType": "PERCENTAGE"},
                Subscribers=[{"SubscriptionType": "EMAIL", "Address": email}])
            print("budget alert at 80% -> email")
        except ClientError as e:
            print("budget alert:", e.response["Error"]["Code"])


def ensure_bucket(s, acct):
    c, name = s.client("s3"), bucket(acct)
    try:
        c.head_bucket(Bucket=name); print("bucket exists:", name)
    except ClientError:
        c.create_bucket(Bucket=name)
        c.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
            k: True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")})
        c.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
        c.put_bucket_tagging(Bucket=name, Tagging={"TagSet": TAGS})
        c.put_object(Bucket=name, Key="revocations.json", Body=b"[]", ContentType="application/json")
        print("bucket created:", name)


def _role(iam, name, trust, desc):
    try:
        iam.get_role(RoleName=name); iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
        print("role updated:", name)
    except ClientError:
        iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Description=desc, Tags=TAGS)
        print("role created:", name)


def ensure_roles(s, acct):
    iam = s.client("iam")
    _role(iam, LAMBDA_ROLE, {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
          "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}, "gmo lambda execution")
    iam.attach_role_policy(RoleName=LAMBDA_ROLE, PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    iam.put_role_policy(RoleName=LAMBDA_ROLE, PolicyName="revocations-read", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "s3:GetObject",
        "Resource": f"arn:aws:s3:::{bucket(acct)}/revocations.json"}]}))
    arn = f"arn:aws:iam::{acct}:oidc-provider/{GH_OIDC}"
    try:
        iam.get_open_id_connect_provider(OpenIDConnectProviderArn=arn); print("oidc provider exists")
    except ClientError:
        iam.create_open_id_connect_provider(Url=f"https://{GH_OIDC}", ClientIDList=["sts.amazonaws.com"],
            ThumbprintList=["6938fd4d98bab03faadb97b34396831e3780aea1"], Tags=TAGS)
        print("oidc provider created")
    _role(iam, DEPLOY_ROLE, {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
          "Principal": {"Federated": arn}, "Action": "sts:AssumeRoleWithWebIdentity",
          "Condition": {"StringEquals": {f"{GH_OIDC}:aud": "sts.amazonaws.com",
                                         f"{GH_OIDC}:sub": f"{SUB_PREFIX}:environment:production"}}}]},
          "GitHub Actions deploy for gmo-* only")
    fn = f"arn:aws:lambda:{REGION}:{acct}:function:gmo-*"
    iam.put_role_policy(RoleName=DEPLOY_ROLE, PolicyName="gmo-deploy", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "lambda:*", "Resource": fn},
        {"Effect": "Allow", "Action": ["apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH",
                                       "apigateway:DELETE", "apigateway:TagResource"],
         "Resource": [f"arn:aws:apigateway:{REGION}::/apis", f"arn:aws:apigateway:{REGION}::/apis/*",
                      f"arn:aws:apigateway:{REGION}::/tags/*"]},
        {"Effect": "Allow", "Action": "iam:PassRole", "Resource": f"arn:aws:iam::{acct}:role/{LAMBDA_ROLE}",
         "Condition": {"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}}},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:PutObjectTagging"], "Resource": f"arn:aws:s3:::{bucket(acct)}/*"},
        {"Effect": "Allow", "Action": "ssm:GetParameter", "Resource": f"arn:aws:ssm:{REGION}:{acct}:parameter/gmo/*"},
        {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:DescribeLogGroups", "logs:PutRetentionPolicy",
                                       "logs:TagResource"], "Resource": f"arn:aws:logs:{REGION}:{acct}:log-group:/aws/lambda/gmo-*"}]}))


def destroy(s, acct):
    iam, c = s.client("iam"), s.client("s3")
    for r in (DEPLOY_ROLE, LAMBDA_ROLE):
        try:
            for p in iam.list_role_policies(RoleName=r)["PolicyNames"]: iam.delete_role_policy(RoleName=r, PolicyName=p)
            for p in iam.list_attached_role_policies(RoleName=r)["AttachedPolicies"]:
                iam.detach_role_policy(RoleName=r, PolicyArn=p["PolicyArn"])
            iam.delete_role(RoleName=r); print("deleted role", r)
        except ClientError as e: print(r, e.response["Error"]["Code"])
    try:
        v = s.resource("s3").Bucket(bucket(acct)); v.object_versions.delete(); v.delete(); print("deleted bucket")
    except ClientError as e: print("bucket", e.response["Error"]["Code"])
    try: s.client("budgets").delete_budget(AccountId=acct, BudgetName=BUDGET); print("deleted budget")
    except ClientError as e: print("budget", e.response["Error"]["Code"])
    print("note: the GitHub OIDC provider is shared account-wide and is left in place")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--profile"); ap.add_argument("--budget-usd", type=int, default=25)
    ap.add_argument("--email"); ap.add_argument("--destroy", action="store_true"); a = ap.parse_args()
    s = session(a.profile); acct = account(s); print("account", acct)
    if a.destroy: destroy(s, acct); sys.exit()
    ensure_budget(s, acct, a.budget_usd, a.email); ensure_bucket(s, acct); ensure_roles(s, acct)
