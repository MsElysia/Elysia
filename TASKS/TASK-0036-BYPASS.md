# TASK-0036 — Resolve Bypass Findings

## Goal

Resolve bypass findings: ensure all external actions go through gateways.

## Scope

* Modules listed below
* Gateway modules (if new gateways needed)

## Non-goals

* No refactors unrelated to bypass issues
* Do not redesign architecture

## Modules with Bypass Issues

- `project_guardian.gumroad_client` (`project_guardian/gumroad_client.py`): Network library: requests
- `project_guardian.slave_deployment` (`project_guardian/slave_deployment.py`): Subprocess: subprocess
- `project_guardian.metacoder` (`project_guardian/metacoder.py`): Subprocess: subprocess, File write pattern: shutil.move, File write pattern: shutil.copy
- `project_guardian.ai_tool_registry_engine` (`project_guardian/ai_tool_registry_engine.py`): Network library: requests
- `project_guardian.webscout_agent` (`project_guardian/webscout_agent.py`): Network library: httpx

## Resolution Strategy

For each module:
1. **Route through gateway**: If external action needed, route through appropriate gateway (WebReader, FileWriter, SubprocessRunner)
2. **Remove if unnecessary**: If external action is not needed, remove it
3. **Document exception**: If external action is intentional and safe, document why it's allowed

## Acceptance Criteria

* All bypass issues resolved (routed through gateways or removed)
* Invariant tests pass (no ungated external actions)
* `pytest -q` passes
* `.\scripts\acceptance.ps1` passes

## Rollback

Revert changes to modules.
