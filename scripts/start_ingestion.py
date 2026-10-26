"""Start the Knowledge Base ingestion job (CloudFormation has no resource for it).

Usage: python3 scripts/start_ingestion.py <stack-name> [region]
Prints the ingestion job ID.
"""
import sys

import boto3


def main(stack, region="us-east-1"):
    cfn = boto3.client("cloudformation", region_name=region)
    outputs = cfn.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]
    out = {o["OutputKey"]: o["OutputValue"] for o in outputs}
    if not out.get("KnowledgeBaseId") or not out.get("DataSourceId"):
        sys.exit("KnowledgeBaseId or DataSourceId is empty in the stack outputs")
    agent = boto3.client("bedrock-agent", region_name=region)
    job = agent.start_ingestion_job(
        knowledgeBaseId=out["KnowledgeBaseId"], dataSourceId=out["DataSourceId"]
    )["ingestionJob"]
    print(job["ingestionJobId"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
