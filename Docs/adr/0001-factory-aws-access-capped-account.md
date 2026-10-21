# The factory gets AWS access, in a dedicated capped account

Factory runs may call real AWS services (Bedrock, Knowledge Base, DynamoDB, Step Functions). We chose this over a no-AWS factory so agents can check their own work against real services. Spend is capped by a dedicated AWS account with a $20 monthly budget (alerts at 50% and 90%), a role that denies NAT Gateway, provisioned search clusters and provisioned concurrency, and 1-hour credentials from GitHub OIDC. Every resource is tagged with its issue number and destroyed when the PR closes.

## Consequences

- A factory bug can spend real money, up to the $20 cap.
- The cheapest Bedrock model that passes the golden scenarios is the default. A larger model runs only in the manual release check.
- The role also denies Bedrock provisioned throughput, model customization jobs and OpenSearch Serverless collections, because each bills above the cap on its own. A Knowledge Base will use S3 Vectors, not OpenSearch.
- At 100% of the budget a budget action attaches a deny-all policy to the role.
- The first deploy lets the factory use Bedrock and DynamoDB. Lambda, Step Functions, S3, S3 Vectors and service roles are added to the factory role by the first ticket that needs each one.
- The budget action stops new factory calls. It does not tear down resources that already exist, so those rely on the destroy-on-PR-close rule.
- The factory-account stack is permanent and exempt from destroy-on-PR-close.
