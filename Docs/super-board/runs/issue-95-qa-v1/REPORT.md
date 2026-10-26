# QA v1 issue 95
- Full suite: npm test 69 pass; python unittest 141 OK (10 in test_bedrock_stack).
- cfn-lint infra/careconnect-bedrock.yaml: clean (exit 0).
- scripts/start_ingestion.py: needs boto3 (not in requirements.txt); usage text path not run live.
- Not run: live deploy (AWS MCP sign-in expired; account is shared, no resources created).
