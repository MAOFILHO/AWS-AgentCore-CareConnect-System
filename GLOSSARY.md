# CareConnect

A patient-support assistant for the fictional Riverside Health hospital network. It answers routine questions from approved documents with citations, and hands anything clinical to a licensed clinician.

## Language

**Approved document**:
A hospital-owned document the assistant may quote. It is the only source of patient-facing answers.
_Avoid_: knowledge, content, FAQ

**Citation**:
A reference from an answer back to the approved document passage it came from.
_Avoid_: source link, reference

**Clinical question**:
A patient request about dosages, diagnoses or urgent symptoms. Software never answers it.
_Avoid_: medical question, health question

**Escalation**:
Handing a request to a licensed clinician through a durable ticket and a human-approval workflow.
_Avoid_: handoff, forward

**Staged action**:
A high-impact request, such as a prescription refill, prepared by software and held until a human approves it.
_Avoid_: pending action, auto-submit

**Safety gate**:
The deterministic rule check that detects clinical, urgent, manipulation and PII intent. It is code, not an LLM agent.
_Avoid_: Safety agent, safety Lambda

**Agent**:
An LLM-driven component with its own responsibility. CareConnect has six: Supervisor, Retrieval, Document-Processing, Task/Tool, Verification, Escalation.
_Avoid_: bot, worker

**Verification**:
An independent check that a draft reply is grounded in its cited passages and passes the safety rules before it ships.
_Avoid_: validation, QA

**Golden scenario**:
A fixed patient request with a known correct outcome, used to gate a release.
_Avoid_: test case, eval prompt
