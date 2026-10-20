# The factory gets AWS access, in a dedicated capped account

Factory runs may call real AWS services (Bedrock, Knowledge Base, DynamoDB, Step Functions). We chose this over a no-AWS factory so agents can check their own work against real services. Spend is capped by a dedicated AWS account with a $20 monthly budget (alerts at 50% and 90%), a role that denies NAT Gateway, provisioned search clusters and provisioned concurrency, and 1-hour credentials from GitHub OIDC. Every resource is tagged with its issue number and destroyed when the PR closes.

## Consequences

- A factory bug can spend real money, up to the $20 cap.
- The cheapest Bedrock model that passes the golden scenarios is the default. A larger model runs only in the manual release check.
