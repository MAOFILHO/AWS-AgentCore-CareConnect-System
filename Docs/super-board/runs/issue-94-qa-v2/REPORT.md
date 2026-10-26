# Issue 94 QA v2 (head de4dc81)

| AC | Check | Result |
|---|---|---|
| 1 | `test_both_functions_run_python_312`, `test_handlers_come_from_lambda_functions_dir`, `test_each_role_writes_only_its_own_log_group`; handlers import only `re` / `uuid` | pass |
| 2 | `test_pydantic_layer_is_a_parameter`, `test_no_provisioned_concurrency` | pass |
| 3 | `test_outputs_are_both_function_arns` | pass |
| 4 | `test/test_lambdas_template.py` 9/9; each mutation below makes it fail | pass |

Mutations, each reverted after the run: `logs:*` action, `python3.11` runtime,
`ReservedConcurrentExecutions: 1`, `issue=93` tag. All four fail the test.

Checks (fresh venv): `npm test` 69/69 · `PYTHONPATH=src python3 -m unittest discover -s test` 140 OK ·
`cfn-lint 1.47.1 infra/careconnect-lambdas.yaml` clean · typecheck, lint, build clean.
No account IDs or ARNs in the template.
