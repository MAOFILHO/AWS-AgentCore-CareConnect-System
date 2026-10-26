# QA v1 · issue 108 · PR 112 @ 76442ec

Result: pass. `npm test` 66/66, `PYTHONPATH=src python3 -m unittest discover -s test` 120/120.

| AC | Proof |
|---|---|
| Waiting text after submit, before reply | test/chat.test.js "the waiting text shows after submit and the reply replaces it" (pending fake fetch) |
| Reply or fixed error replaces it | same test (reply); "the fixed error replaces the waiting text" |
| Empty question shows none | "an empty question shows no waiting text" |
| Fake fetch resolves later; npm test passes | pending-promise fake in the first test; suite green |

Test gaps (not written): the error test does not assert the waiting text showed first (Low).
