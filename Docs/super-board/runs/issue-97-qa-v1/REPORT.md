# Issue 97 QA v1

Head tested: 447412e (builder) plus the QA test commit.

| AC | Proof |
|---|---|
| AC1 Lambda 300 s, invoke scoped to runtime ARN, POST /careconnect, private S3 behind CloudFront OAC, PriceClass_100 | `test_proxy_lambda_has_300_second_timeout`, `test_invoke_policy_is_scoped_to_the_runtime_arn`, `test_api_routes_post_and_preflight_to_the_proxy`, `test_bucket_is_private_behind_cloudfront_oac_with_cheapest_price_class` |
| AC2 ALLOWED_ORIGIN from the CloudFront domain | `test_allowed_origin_is_the_cloudfront_domain` (exact `https://${Distribution.DomainName}`), `test_proxy_takes_runtime_arn_and_origin_from_environment` |
| AC3 Outputs | `test_outputs` (names), `test_outputs_point_at_the_stack_resources` (values, added by QA) |
| AC4 Python test | `test/test_api_stack.py`: tags, timeout, origin, price class, forbidden types |

Checks: verify command green (npm 69/69, Python 177/177 after the QA test), typecheck/lint/build green, cfn-lint clean.
Mutation: DistributionId output changed to Distribution.DomainName makes the new test fail (mutation.log).

Test gaps (not written): no live deploy (needs the runtime ARN from #123 and the owner account); S3 origin DomainName is not asserted to be FrontendBucket (Low).
