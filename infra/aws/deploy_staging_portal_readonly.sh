#!/usr/bin/env bash
# Optional second stack in the FINAL reviewed release; NOT invoked by CI.
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-eu-central-1}"
[[ "$REGION" == eu-central-1 ]] || exit 2
PORTAL="${STOCKLENS_PORTAL_STACK:-}"
[[ -n "$PORTAL" && "$PORTAL" != stocklens-paper &&
   "$PORTAL" != stocklens-independent-staging ]] || {
  echo "REQUIRE_EXISTING_COGNITO_PORTAL_STACK" >&2; exit 3;
}
out() {
 aws cloudformation describe-stacks --region "$REGION" --stack-name "$1" \
 --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue|[0]" --output text
}
api="$(out "$PORTAL" PortalApiId)"
auth="$(out "$PORTAL" PortalAuthorizerId)"
bucket="$(out stocklens-independent-staging CandidateDataBucket)"
[[ -n "$api" && "$api" != None && -n "$auth" && "$auth" != None &&
   "$bucket" == stocklens-independent-staging-* ]] || {
 echo "REQUIRE_EXISTING_PRIVATE_API_AND_STAGING_BUCKET" >&2; exit 3;
}
issuer="$(aws apigatewayv2 get-authorizer --region "$REGION" \
 --api-id "$api" --authorizer-id "$auth" \
 --query '[AuthorizerType,JwtConfiguration.Issuer]' --output text)"
[[ "$issuer" == JWT*amazonaws.com/* ]] || {
 echo "REQUIRE_EXISTING_COGNITO_JWT_AUTHORIZER" >&2; exit 3;
}
[[ "$(aws s3api get-bucket-versioning --region "$REGION" \
 --bucket "$bucket" --query Status --output text)" == Enabled ]] || exit 3
aws cloudformation validate-template --region "$REGION" \
 --template-body file://infra/aws/staging-portal-readonly.yaml >/dev/null
echo "STAGING_PORTAL_READONLY_PREFLIGHT_PASS:JWT_COGNITO:S3_VERSIONED"
read -r -p 'Type DEPLOY_READ_ONLY_PORTAL_ROUTE to create only the private route: ' approval
[[ "$approval" == DEPLOY_READ_ONLY_PORTAL_ROUTE ]] || {
 echo "NOT_DEPLOYED" >&2; exit 3;
}
aws cloudformation deploy --region "$REGION" \
 --stack-name stocklens-staging-portal-readonly \
 --template-file infra/aws/staging-portal-readonly.yaml \
 --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
 --parameter-overrides PortalApiId="$api" PortalAuthorizerId="$auth" \
 StagingDataBucket="$bucket"
echo "STAGING_JWT_S3_READONLY_DEPLOYED:BROKER_DISABLED"
