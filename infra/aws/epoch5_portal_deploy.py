"""Deploy only a new JWT read route in ST. Defaults to plan-only."""
import argparse
import json
import pathlib
import subprocess
import tempfile
import boto3

REGION = "eu-central-1"
ACCOUNT = "634740393398"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PREFIX = "paper/epochs/NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH5_20261124/"
STACK = "stocklens-st-epoch5-portal-read"
ROUTE = "GET /v1/staging-epoch5"


def template(api, authorizer, code, scopes=()):
    ref = lambda n: {"Ref": n}
    arn = lambda n: {"Fn::GetAtt": [n, "Arn"]}
    bucket = "arn:aws:s3:::" + BUCKET
    return {"AWSTemplateFormatVersion": "2010-09-09", "Resources": {
        "ReaderRole": {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
            "ManagedPolicyArns": ["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"],
            "Policies": [{"PolicyName": "Epoch5ReadOnly", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion"],
                 "Resource": [bucket + "/signals/*", bucket + "/" + PREFIX + "*"]},
                {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": bucket,
                 "Condition": {"StringLike": {"s3:prefix": ["signals/*", PREFIX + "*"]}}}
            ]}}]}},
        "Reader": {"Type": "AWS::Lambda::Function", "Properties": {
            "Runtime": "python3.12", "Handler": "index.handler", "Role": arn("ReaderRole"),
            "Timeout": 28, "MemorySize": 256, "Code": {"ZipFile": code}}},
        "Integration": {"Type": "AWS::ApiGatewayV2::Integration", "Properties": {
            "ApiId": api, "IntegrationType": "AWS_PROXY", "IntegrationUri": arn("Reader"),
            "PayloadFormatVersion": "2.0", "TimeoutInMillis": 29000}},
        "Route": {"Type": "AWS::ApiGatewayV2::Route", "Properties": {
            "ApiId": api, "RouteKey": ROUTE, "AuthorizationType": "JWT", "AuthorizerId": authorizer,
            **({"AuthorizationScopes": list(scopes)} if scopes else {}),
            "Target": {"Fn::Join": ["/", ["integrations", ref("Integration")]]}}},
        "Permission": {"Type": "AWS::Lambda::Permission", "Properties": {
            "Action": "lambda:InvokeFunction", "FunctionName": ref("Reader"), "Principal": "apigateway.amazonaws.com",
            "SourceArn": f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{api}/*/GET/v1/staging-epoch5"}}
    }, "Outputs": {"Reader": {"Value": ref("Reader")}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()
    sdk = boto3.Session(region_name=REGION)
    if sdk.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise RuntimeError("WRONG_ACCOUNT")
    gw = sdk.client("apigatewayv2")
    apis = [a for page in gw.get_paginator("get_apis").paginate() for a in page["Items"]
            if a["Name"] == "stocklens-authenticated-journal"]
    if len(apis) != 1:
        raise RuntimeError("EXPECTED_ONE_JOURNAL_API")
    api = apis[0]["ApiId"]
    routes = [r for page in gw.get_paginator("get_routes").paginate(ApiId=api) for r in page["Items"]]
    existing = [r for r in routes if r["RouteKey"] == "GET /v1/staging"]
    if len(existing) != 1 or existing[0].get("AuthorizationType") != "JWT" or not existing[0].get("AuthorizerId"):
        raise RuntimeError("LEGACY_JWT_ROUTE_REQUIRED")
    authorizer = existing[0]["AuthorizerId"]
    scopes = existing[0].get("AuthorizationScopes", [])
    stages = gw.get_stages(ApiId=api)["Items"]
    if not stages or not all(s.get("AutoDeploy") for s in stages):
        raise RuntimeError("NON_AUTODEPLOY_STAGE_REVIEW_REQUIRED")
    if any(r["RouteKey"] == ROUTE for r in routes):
        resources = sdk.client("cloudformation").describe_stack_resources(StackName=STACK)["StackResources"]
        owned = [r["PhysicalResourceId"] for r in resources if r["LogicalResourceId"] == "Route"]
        current = next(r for r in routes if r["RouteKey"] == ROUTE)
        if owned != [current["RouteId"]] or current.get("AuthorizationType") != "JWT" or current.get("AuthorizerId") != authorizer or current.get("AuthorizationScopes", []) != scopes:
            raise RuntimeError("EXISTING_ROUTE_OWNERSHIP_OR_AUTH_DRIFT")
    code = pathlib.Path(__file__).with_name("epoch5_portal_reader.py").read_text()
    body = template(api, authorizer, code, scopes)
    print(json.dumps({"stack": STACK, "route": ROUTE, "jwt": True, "bucket": BUCKET,
                      "prefix": PREFIX, "mutations": args.deploy}, indent=2), flush=True)
    if not args.deploy:
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "reader.json"
        path.write_text(json.dumps(body))
        subprocess.run(["aws", "cloudformation", "deploy", "--region", REGION,
                        "--stack-name", STACK, "--template-file", str(path),
                        "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset"], check=True)
    routes = [r for page in gw.get_paginator("get_routes").paginate(ApiId=api) for r in page["Items"]]
    r = next(r for r in routes if r["RouteKey"] == ROUTE)
    if r.get("AuthorizationType") != "JWT" or r.get("AuthorizerId") != authorizer or r.get("AuthorizationScopes", []) != scopes:
        raise RuntimeError("DEPLOYED_ROUTE_AUTH_MISMATCH")
    print("EPOCH5_JWT_READ_ROUTE_DEPLOYED_NOT_PAPER_RUNTIME_PROOF")


if __name__ == "__main__":
    main()
