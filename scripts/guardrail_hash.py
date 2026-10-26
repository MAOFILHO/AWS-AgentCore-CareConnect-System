"""Print a 12-hex-char hash of the Guardrail definition in the Bedrock stack template.

deploy.sh passes it as GuardrailHash, so a Guardrail change cuts a new GuardrailVersion.
Usage: python3 scripts/guardrail_hash.py <template>
"""
import hashlib
import json
import sys


def guardrail_hash(template):
    props = template["Resources"]["Guardrail"]["Properties"]
    return hashlib.sha256(json.dumps(props, sort_keys=True).encode()).hexdigest()[:12]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1]) as f:
        print(guardrail_hash(json.load(f)))
