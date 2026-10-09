"""Issue #112 bounded integration worker. Issue #11 remains the authority.

No scheduling, runtime wiring, merge, deployment, or local synchronization.
Verifier trust is supplied separately from the untrusted integration plan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime

REPO = "MsElysia/Elysia"
CONTROL = "https://github.com/MsElysia/Elysia/issues/11"
GATES = {"merge", "deploy", "permissions", "runtime", "providers", "autonomy",
         "live_memory", "external_action", "governance_release", "local_sync"}
PROTECTED = (".git", ".github/", "AGENTS.md", "elysia_collective_seed/autopilot/",
             "elysia_collective_seed/governance/", ".aws/", ".codex/")


class Refusal(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Refusal(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def command(args, cwd=None, data=None):
    result = subprocess.run(args, cwd=cwd, input=data, capture_output=True)
    require(result.returncode == 0, f"{args[0:2]} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout


def git(repo, *args, data=None):
    return command(["git", *args], repo, data)


def api(path):
    return json.loads(command(["gh", "api", f"repos/{REPO}/{path}"]))


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value), "full exact SHA required")


def path(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_./-]+", value)
            and not value.startswith(("/", "-")) and ".." not in value.split("/")
            and not value.endswith("/") and all(p and p != "." and not p.endswith(".") for p in value.split("/")), "unsafe path")


def validate(plan):
    require(plan["control_plane"] == CONTROL and plan["issue"] == 112, "wrong control plane")
    require(re.fullmatch(r"ELY-TASK-[0-9]{6,}", plan["task_id"]), "invalid task packet identity")
    require(set(plan["closed_gates"]) == GATES, "protected gates must remain closed")
    require(plan["independent_verifier_required"] is True, "independent verifier mandatory")
    require(plan["base"]["pr"] > 0 and plan["sources"] and plan["changes"], "explicit base/source/change list required")
    sha(plan["base"]["sha"])
    sha(plan["toolkit_sha"])
    seen_sources = set()
    for source in plan["sources"]:
        sha(source["sha"])
        require(source["pr"] not in seen_sources, "duplicate source")
        seen_sources.add(source["pr"])
    seen = set()
    for change in plan["changes"]:
        sha(change["from"])
        sha(change["to"])
        require(change["source_pr"] in seen_sources and change["scope"], "missing source/scope")
        require(re.fullmatch(r"[0-9a-f]{64}", change["patch_sha256"]), "exact patch digest required")
        require(change["patch_sha256"] not in seen, "duplicate ported change")
        seen.add(change["patch_sha256"])
        require(change["files"] and len(set(change["files"])) == len(change["files"]), "empty/duplicate files")
        for name in change["files"]:
            path(name)
            require(not any(name.casefold().startswith(p.casefold()) for p in PROTECTED), "protected-scope change")
    require(plan["tests"] and len({t["id"] for t in plan["tests"]}) == len(plan["tests"]), "missing/duplicate required tests")
    for test in plan["tests"]:
        require(test["runner"] in {"pytest", "safe-stack"}, "unsupported test runner")
        require(test["paths"] if test["runner"] == "pytest" else test["paths"] == [], "invalid test paths")
        for name in test["paths"]:
            path(name)
            require(name.endswith(".py") and (name.startswith("tests/") or "/tests/" in name), "test file required")
    require(plan["checkpoint_comment"] > 0 and re.fullmatch(r"[0-9a-f]{64}", plan["checkpoint_sha256"]), "pinned Issue #11 checkpoint required")
    require(isinstance(plan["verification_epoch"], int) and plan["verification_epoch"] > 0, "freshness epoch required")
    return digest(plan)


def verify_receipt(receipt_path, trust, *, subject, scope, producer, epoch):
    """SSH signatures authenticate evidence; they confer no human/governance release."""
    receipt_path = Path(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    require(receipt["subject"] == subject and receipt["scope"] == scope, "stale/wrong verdict subject or scope")
    require(receipt["verdict"] == "PASS" and receipt["evidence"], "missing PASS/evidence; repair required")
    require(receipt["issued_at"] >= epoch, "verdict predates required fresh verification")
    verifier = receipt["verifier"]
    require(verifier != producer and verifier in trust["verifiers"], "producer/untrusted verifier")
    require(trust["verifiers"][verifier]["group"] != trust["producers"][producer]["group"], "same-group verifier")
    # Caller-provided signer files/identities are never accepted from a plan or receipt.
    command(["ssh-keygen", "-Y", "verify", "-f", trust["allowed_signers"],
             "-I", verifier, "-n", "elysia-issue11-integration", "-s", str(receipt_path) + ".sig"],
            data=canonical(receipt))
    return {"sha256": digest(receipt), "verifier": verifier, "evidence": receipt["evidence"]}


def source_gate(plan, trust, receipts, producer):
    require(plan["checkpoint_comment"] == trust["checkpoint_comment"], "checkpoint not pinned by trusted Issue #11 adapter")
    checkpoint = api(f"issues/comments/{plan['checkpoint_comment']}")
    require(checkpoint["issue_url"].endswith("/issues/11"), "checkpoint belongs to another issue")
    require(hashlib.sha256(checkpoint["body"].encode()).hexdigest() == plan["checkpoint_sha256"], "checkpoint changed")
    floor = max(trust["minimum_verification_epoch"], int(datetime.fromisoformat(checkpoint["created_at"].replace("Z", "+00:00")).timestamp()))
    require(plan["verification_epoch"] >= floor, "verification epoch predates trusted checkpoint")
    evidence = []
    for item in [plan["base"], *plan["sources"]]:
        current = api(f"pulls/{item['pr']}")
        require(current["state"] == "open" and current["draft"] and current["head"]["sha"] == item["sha"], "stale/non-draft candidate")
        evidence.append(verify_receipt(Path(receipts) / f"pr-{item['pr']}.json", trust,
                        subject=item["sha"], scope=digest(plan), producer=producer,
                        epoch=plan["verification_epoch"]))
    return evidence


def patches(repo, plan):
    out = []
    sources = {s["pr"]: s["sha"] for s in plan["sources"]}
    for change in plan["changes"]:
        # The range must be on the pinned source lineage, with an explicit file selection.
        git(repo, "merge-base", "--is-ancestor", change["from"], change["to"])
        git(repo, "merge-base", "--is-ancestor", change["to"], sources[change["source_pr"]])
        patch = git(repo, "diff", "--binary", "--full-index", change["from"], change["to"], "--", *change["files"])
        require(patch and hashlib.sha256(patch).hexdigest() == change["patch_sha256"], "patch mismatch/omitted change")
        names = git(repo, "diff", "--name-only", change["from"], change["to"], "--", *change["files"]).decode().splitlines()
        require(set(names) == set(change["files"]), "omitted declared file")
        out.append(patch)
    return out


def audit(repo, plan, candidate):
    validate(plan)
    sha(candidate)
    require(git(repo, "rev-parse", "HEAD").decode().strip() == candidate, "checkout/SHA mismatch")
    require(not git(repo, "status", "--porcelain"), "dirty candidate")
    parents = git(repo, "rev-list", "--parents", "-n", "1", candidate).decode().split()
    require(parents == [candidate, plan["base"]["sha"]], "wrong base/unrelated commit history")
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / "expected"
        git(repo, "worktree", "add", "--detach", str(target), plan["base"]["sha"])
        try:
            for patch in patches(repo, plan):
                git(target, "apply", "--check", "-", data=patch)
                git(target, "apply", "--index", "-", data=patch)
            expected = git(target, "write-tree").strip()
            require(expected == git(repo, "rev-parse", f"{candidate}^{{tree}}").strip(), "unrelated/omitted/duplicate changes")
            modes = git(repo, "diff", "--raw", plan["base"]["sha"], candidate).decode()
            require("120000" not in modes and "160000" not in modes, "symlink/submodule port refused")
        finally:
            git(repo, "worktree", "remove", "--force", str(target))


def compose(repo, plan, destination, producer):
    branch = "integration/issue112-" + digest(plan)[:20]
    destination = Path(destination).resolve()
    require(not destination.exists(), "existing destination: use resume, never reset")
    git(repo, "worktree", "add", "-b", branch, str(destination), plan["base"]["sha"])
    for patch in patches(repo, plan):
        git(destination, "apply", "--check", "-", data=patch)
        git(destination, "apply", "--index", "-", data=patch)
    git(destination, "-c", f"user.name={producer}", "-c", "user.email=integration@invalid.local",
        "commit", "-m", f"integration: Issue #112 bounded plan {digest(plan)}")
    head = git(destination, "rev-parse", "HEAD").decode().strip()
    audit(destination, plan, head)
    return branch, head


def publish(repo, plan, branch, head):
    require(git(repo, "remote", "get-url", "origin").decode().strip() in
            {f"https://github.com/{REPO}.git", f"https://github.com/{REPO}", f"git@github.com:{REPO}.git"}, "wrong origin")
    audit(repo, plan, head)
    base = api(f"pulls/{plan['base']['pr']}")
    require(base["head"]["sha"] == plan["base"]["sha"], "base moved")
    remote = git(repo, "ls-remote", "origin", f"refs/heads/{branch}").decode().split()
    require(not remote or remote[0] == head, "conflicting remote branch")
    if not remote:
        git(repo, "push", "origin", f"{head}:refs/heads/{branch}")
    existing = json.loads(command(["gh", "pr", "list", "--repo", REPO, "--state", "all",
                                  "--head", branch, "--json", "url,headRefOid,isDraft,state,baseRefName"]))
    if existing:
        require(len(existing) == 1 and existing[0]["headRefOid"] == head and existing[0]["isDraft"]
                and existing[0]["state"] == "OPEN" and existing[0]["baseRefName"] == base["head"]["ref"], "conflicting prior PR")
        return existing[0]["url"]
    with tempfile.TemporaryDirectory() as temp:
        body = Path(temp) / "body.md"
        body.write_text(f"Issue #112 bounded integration under {CONTROL}.\n\nPlan `{digest(plan)}`; exact base `{plan['base']['sha']}`; composed head `{head}`.\n\nProvenance:\n```json\n{json.dumps(plan['changes'], indent=2)}\n```\n\nAwaiting exact-head CI and fresh independent signed verification. Operator retains merge authority. All protected gates remain closed.\n", encoding="utf-8")
        return command(["gh", "pr", "create", "--repo", REPO, "--draft", "--head", branch,
                        "--base", base["head"]["ref"], "--title", "Issue #112: bounded consolidation",
                        "--body-file", str(body)]).decode().strip()


def run_tests(repo, plan, candidate):
    audit(repo, plan, candidate)
    evidence = []
    for test in plan["tests"]:
        args = [sys.executable, "-m", "pytest", "-q", *test["paths"]] if test["runner"] == "pytest" else [sys.executable, "scripts/run_safe_stack_smoke_tests.py"]
        output = command(args, repo)
        evidence.append({"id": test["id"], "result": "pass", "output_sha256": hashlib.sha256(output).hexdigest(), "command": args[1:]})
    # No test can leave source changes behind and still receive PASS.
    audit(repo, plan, candidate)
    return {"plan_sha256": digest(plan), "candidate": candidate, "tests": evidence}


def schedule_ci(plan, candidate, toolkit_repo):
    """Push one evidence request above the pinned tool; no default-branch workflow required."""
    toolkit = git(toolkit_repo, "rev-parse", "HEAD").decode().strip()
    require(toolkit == plan["toolkit_sha"], "toolkit differs from independently reviewed plan")
    require(not git(toolkit_repo, "status", "--porcelain"), "toolkit checkout must be clean")
    request = {"plan": plan, "candidate": candidate, "toolkit": toolkit}
    branch = "integration-evidence/" + digest(request)[:20]
    remote = git(toolkit_repo, "ls-remote", "origin", f"refs/heads/{branch}").decode().split()
    if remote:
        git(toolkit_repo, "fetch", "origin", remote[0])
        validate_request_commit(toolkit_repo, remote[0], request)
        return {"branch": branch, "request_sha": remote[0], "toolkit_sha": toolkit}
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / "request"
        git(toolkit_repo, "worktree", "add", "--detach", str(target), toolkit)
        try:
            (target / "integration-request.json").write_bytes(canonical(request))
            git(target, "add", "integration-request.json")
            git(target, "-c", "user.name=Integration evidence", "-c", "user.email=evidence@invalid.local",
                "commit", "-m", f"ci: exact-head evidence request {digest(request)}")
            head = git(target, "rev-parse", "HEAD").decode().strip()
            git(target, "push", "origin", f"{head}:refs/heads/{branch}")
            return {"branch": branch, "request_sha": head, "toolkit_sha": toolkit}
        finally:
            git(toolkit_repo, "worktree", "remove", "--force", str(target))


def validate_request_commit(repo, head, request):
    require(request["toolkit"] == request["plan"]["toolkit_sha"], "unapproved evidence toolkit")
    require(git(repo, "rev-list", "--parents", "-n", "1", head).decode().split() == [head, request["toolkit"]], "wrong evidence toolkit parent")
    require(git(repo, "diff", "--name-only", request["toolkit"], head).decode().splitlines() == ["integration-request.json"], "modified evidence workflow/tool")
    require(git(repo, "show", f"{head}:integration-request.json") == canonical(request), "wrong hosted evidence request")


def hosted_evidence(plan, candidate, toolkit, run_id, repo=None):
    run = api(f"actions/runs/{int(run_id)}")
    require(run["path"] == ".github/workflows/bounded-integration.yml"
            and run["event"] == "push" and run["conclusion"] == "success", "wrong/failed hosted run")
    request = {"plan": plan, "candidate": candidate, "toolkit": toolkit}
    require(run["head_branch"] == "integration-evidence/" + digest(request)[:20], "wrong evidence branch")
    git(repo, "fetch", "origin", run["head_sha"])
    validate_request_commit(repo, run["head_sha"], request)
    jobs = api(f"actions/runs/{int(run_id)}/jobs?filter=latest&per_page=100")["jobs"]
    require(len(jobs) == 2 and {j["name"] for j in jobs} == {"integration-linux", "integration-windows"}
            and all(j["conclusion"] == "success" for j in jobs), "missing/failed mandatory job")
    with tempfile.TemporaryDirectory() as temp:
        command(["gh", "run", "download", str(run_id), "--repo", REPO, "--dir", temp])
        for platform in ("linux", "windows"):
            report = json.loads((Path(temp) / f"integration-{platform}" / "evidence.json").read_text())
            require(report["candidate"] == candidate and report["plan_sha256"] == digest(plan), "hosted evidence SHA/plan mismatch")
            require([t["id"] for t in report["tests"]] == [t["id"] for t in plan["tests"]]
                    and all(t["result"] == "pass" for t in report["tests"]), "missing/failed required test")
    return {"run_id": run_id, "toolkit_sha": toolkit, "jobs": [j["id"] for j in jobs]}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("stage", choices=["start", "resume", "ci", "finish"])
    parser.add_argument("--plan", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--result", required=True)
    parser.add_argument("--trust")
    parser.add_argument("--receipts")
    parser.add_argument("--producer")
    parser.add_argument("--destination")
    parser.add_argument("--candidate")
    parser.add_argument("--toolkit")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    result = {"control_plane": CONTROL, "task_id": plan.get("task_id"), "state": "BLOCKED", "closed_gates": sorted(GATES)}
    try:
        result["plan_sha256"] = validate(plan)
        if args.stage == "ci":
            result.update(run_tests(args.repo, plan, args.candidate))
            result["state"] = "CI_PASS_PENDING_INDEPENDENT_VERIFICATION"
        else:
            toolkit_repo = Path(__file__).resolve().parents[2]
            require(git(toolkit_repo, "rev-parse", "HEAD").decode().strip() == plan["toolkit_sha"], "wrong pinned toolkit")
            require(not git(toolkit_repo, "status", "--porcelain"), "dirty toolkit checkout")
            trust = json.loads(Path(args.trust).read_text())
            result["prerequisites"] = source_gate(plan, trust, args.receipts, args.producer)
            if args.stage == "start":
                branch, head = compose(args.repo, plan, args.destination, args.producer)
                repo = args.destination
            else:
                repo = args.repo
                head = args.candidate
                branch = "integration/issue112-" + digest(plan)[:20]
            result.update(candidate=head, provenance=plan["changes"])
            # Recheck sources after composition, immediately before publishing.
            result["prerequisites"] = source_gate(plan, trust, args.receipts, args.producer)
            result["pull_request"] = publish(repo, plan, branch, head)
            toolkit_repo = Path(__file__).resolve().parents[2]
            result["ci_request"] = schedule_ci(plan, head, toolkit_repo)
            result["state"] = "VERIFYING"
            if args.stage == "finish":
                sha(args.toolkit)
                require(args.toolkit == git(Path(__file__).resolve().parents[2], "rev-parse", "HEAD").decode().strip(), "untrusted toolkit SHA")
                result["hosted_ci"] = hosted_evidence(plan, head, args.toolkit, args.run_id, toolkit_repo)
                result["verification"] = verify_receipt(Path(args.receipts) / "composed.json", trust,
                    subject=head, scope=digest(plan), producer=args.producer, epoch=plan["verification_epoch"])
                result["prerequisites"] = source_gate(plan, trust, args.receipts, args.producer)
                result["state"] = "READY_FOR_MERGE_REVIEW"
    except (Refusal, KeyError, TypeError, OSError, ValueError) as exc:
        result["state"] = "BLOCKED_REPAIR_REQUIRED"
        result["reason"] = str(exc)
    Path(args.result).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["state"] not in {"BLOCKED", "BLOCKED_REPAIR_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
