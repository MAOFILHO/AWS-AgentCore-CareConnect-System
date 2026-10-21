"""Safety gate: deterministic rules, no AWS. Rules copied unchanged from
Docs/Repo/lambda-functions/careconnect-deterministic-safety/lambda_function.py."""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Patterns that indicate a CLINICAL question (must be escalated, not answered).
# UPDATE THIS list if your organisation phrases things differently.
# ---------------------------------------------------------------------------
CLINICAL_PATTERNS = [
    r"\bdiagnose\b",
    r"\bdiagnosis\b",
    r"\bwhat disease do i have\b",
    r"\bwhat condition do i have\b",
    r"\bshould i take\b",
    r"\bshould i increase\b",
    r"\bshould i decrease\b",
    r"\bdouble (my|the) dose\b",
    r"\bchange (my|the) dose\b",
    r"\bhow much .* should i take\b",
]

# Patterns that indicate an URGENT / emergency situation (must be escalated).
URGENT_PATTERNS = [
    r"\bchest pain\b",
    r"\bsevere difficulty breathing\b",
    r"\bcan't breathe\b",
    r"\bcannot breathe\b",
    r"\bunconscious\b",
    r"\bsevere bleeding\b",
    r"\bpassed out\b",
]

# Health or symptom wording. Any request that contains it is escalated before
# retrieval (fail closed), even if an approved document might answer it.
HEALTH_PATTERNS = [
    r"\bdizz(y|iness)\b",
    r"\bsymptoms?\b",
    r"\bfeels? (sick|unwell|faint|weak|ill)\b",
    r"\b(pain|nausea|nauseous|fever|vomiting|faint|faints|fainting|rash|bleeding|swelling)\b",
    r"\b(unwell|ill|sick)\b",
    r"\b(light-?headed|headaches?|cough(ing)?|ache|aching|hurts?|sore|infection|allergic|dehydrated|diarrh?oea)\b",
]

# Patterns that indicate a prompt-injection / manipulation attempt (must block).
MANIPULATION_PATTERNS = [
    r"\bignore previous instructions\b",
    r"\bignore all previous instructions\b",
    r"\boverride (the )?(rules|policy|policies|instructions)\b",
    r"\bignore (the )?(rules|policy|policies)\b",
    r"\breveal (the )?system prompt\b",
    r"\bshow (me )?(the )?system prompt\b",
    r"\bdisregard previous instructions\b",
]

# Personal data (PII) patterns. UPDATE the "mrn" pattern if your medical record
# number format is different from MRN-######## (8 digits).
PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "mrn": r"\bMRN-\d{8}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b",
}

# Lines inside a RETRIEVED document that look like injected instructions and
# should be stripped out before the document is used.
INSTRUCTION_LINE_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"override\s.*instructions",
    r"disregard\s+(all\s+)?(previous\s+)?instructions",
    r"forget\s+(all\s+|your\s+)?(previous\s+)?instructions",
    r"^\s*new\s+instructions\s*:",
    r"^\s*\[?\s*system\s*\]?\s*:",
    r"\bsystem prompt\s*:",
    r"^\s*you are now\b",
    r"^\s*developer\s*:",
    r"^\s*assistant\s*:",
]


# ---------------------------------------------------------------------------
# Helper: does any pattern match the text? (case-insensitive)
# ---------------------------------------------------------------------------
def matches(text, patterns):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


# Find which PII types appear, and how many of each.
def find_pii(text):
    findings = {}
    for pii_type, pattern in PII_PATTERNS.items():
        values = re.findall(pattern, text, re.IGNORECASE)
        if values:
            findings[pii_type] = len(values)
    return findings


# Replace personal data with placeholders like [EMAIL], [MRN], etc.
def mask_pii(text):
    masked = text
    replacements = {
        "email": "[EMAIL]",
        "ssn": "[SSN]",
        "mrn": "[MRN]",
        "phone": "[PHONE]",
    }
    for pii_type, pattern in PII_PATTERNS.items():
        masked = re.sub(pattern, replacements[pii_type], masked, flags=re.IGNORECASE)
    return masked


# Remove HTML comments, then drop each instruction-like line and the lines
# after it up to the next blank line (anti prompt-injection). Fail closed.
def sanitize_retrieved(text):
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u00ad\u180e\u200b-\u200f\u2060-\u2064\ufeff]", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*", "", text, flags=re.DOTALL)
    safe_lines = []
    injected = False
    for line in text.splitlines():
        if not line.strip():
            injected = False
        elif any(re.search(p, line, re.IGNORECASE) for p in INSTRUCTION_LINE_PATTERNS):
            injected = True
        if not injected:
            safe_lines.append(line)
    return "\n".join(safe_lines)


# Classify a piece of text across all four dimensions.
def classify(text):
    return {
        "clinical": matches(text, CLINICAL_PATTERNS),
        "urgent": matches(text, URGENT_PATTERNS),
        "injection": matches(text, MANIPULATION_PATTERNS),
        "pii": find_pii(text),
    }


# Does the text read as a health or symptom request?
def is_health_request(text):
    return matches(text, HEALTH_PATTERNS)
