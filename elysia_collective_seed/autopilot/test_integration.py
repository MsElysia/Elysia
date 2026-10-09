import copy
import hashlib
import json
from pathlib import Path

import pytest

from elysia_collective_seed.autopilot import integration as i


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    i.git(root, 'init')
    i.git(root, 'config', 'user.name', 'producer')
    i.git(root, 'config', 'user.email', 'test@invalid.local')
    i.git(root, 'config', 'core.autocrlf', 'false')
    (root / '.gitignore').write_text('__pycache__/\n.pytest_cache/\n')
    (root / 'feature.py').write_text('old = 1\n')
    (root / 'tests').mkdir()
    (root / 'tests/test_feature.py').write_text('def test_feature():\n    assert 1 + 1 == 2\n')
    i.git(root, 'add', '.')
    i.git(root, 'commit', '-m', 'base')
    base = i.git(root, 'rev-parse', 'HEAD').decode().strip()
    (root / 'feature.py').write_text('old = 1\nnew = 2\n')
    i.git(root, 'commit', '-am', 'source')
    source = i.git(root, 'rev-parse', 'HEAD').decode().strip()
    patch = i.git(root, 'diff', '--binary', '--full-index', base, source, '--', 'feature.py')
    plan = dict(control_plane=i.CONTROL, issue=112, task_id='ELY-TASK-000112',
                toolkit_sha='a' * 40,
                closed_gates=sorted(i.GATES), independent_verifier_required=True,
                base={'pr': 110, 'sha': base}, sources=[{'pr': 101, 'sha': source}],
                changes=[{'source_pr': 101, 'from': base, 'to': source, 'files': ['feature.py'],
                          'scope': 'unique feature', 'patch_sha256': hashlib.sha256(patch).hexdigest()}],
                tests=[{'id': 'focused', 'runner': 'pytest', 'paths': ['tests/test_feature.py']}],
                checkpoint_comment=6089305304, checkpoint_sha256='a' * 64, verification_epoch=1)
    return root, plan


def test_composition_exact_single_commit(repo, tmp_path):
    root, plan = repo
    destination = tmp_path / 'isolated'
    branch, head = i.compose(root, plan, destination, 'producer')
    i.audit(destination, plan, head)
    assert i.git(destination, 'rev-list', '--count', f"{plan['base']['sha']}..{head}").strip() == b'1'
    assert branch.startswith('integration/issue112-')
    with pytest.raises(i.Refusal, match='existing destination'):
        i.compose(root, plan, destination, 'producer')


@pytest.mark.parametrize('attack', ['wrong-base', 'smuggling', 'dirty', 'wrong-head', 'symlink'])
def test_audit_attacks(repo, tmp_path, attack):
    root, plan = repo
    destination = tmp_path / 'isolated'
    _, head = i.compose(root, plan, destination, 'producer')
    if attack == 'wrong-base':
        plan['base']['sha'] = plan['sources'][0]['sha']
    elif attack == 'smuggling':
        (destination / 'unrelated.py').write_text('smuggled = True\n')
        i.git(destination, 'add', '.')
        i.git(destination, 'commit', '--amend', '--no-edit')
        head = i.git(destination, 'rev-parse', 'HEAD').decode().strip()
    elif attack == 'dirty':
        (destination / 'feature.py').write_text('changed\n')
    elif attack == 'wrong-head':
        head = plan['base']['sha']
    else:
        i.git(destination, 'update-index', '--cacheinfo', '120000',
              i.git(destination, 'hash-object', '-w', '--stdin', data=b'outside').decode().strip(), 'feature.py')
        i.git(destination, 'commit', '--amend', '--no-edit')
        head = i.git(destination, 'rev-parse', 'HEAD').decode().strip()
    with pytest.raises(i.Refusal):
        i.audit(destination, plan, head)


@pytest.mark.parametrize('attack', ['duplicate', 'protected', 'protected-case', 'dot-alias', 'patch', 'omitted', 'source', 'gate', 'verifier', 'test'])
def test_plan_and_patch_attacks(repo, attack):
    root, plan = repo
    if attack == 'duplicate':
        plan['changes'] *= 2
    elif attack == 'protected':
        plan['changes'][0]['files'] = ['.github/workflows/smuggled.yml']
    elif attack == 'protected-case':
        plan['changes'][0]['files'] = ['.GITHUB/workflows/smuggled.yml']
    elif attack == 'dot-alias':
        plan['changes'][0]['files'] = ['project_guardian/./feature.py']
    elif attack == 'patch':
        plan['changes'][0]['patch_sha256'] = 'b' * 64
    elif attack == 'omitted':
        plan['changes'][0]['files'].append('missing.py')
    elif attack == 'source':
        plan['sources'][0]['sha'] = plan['base']['sha']
    elif attack == 'gate':
        plan['closed_gates'].remove('merge')
    elif attack == 'verifier':
        plan['independent_verifier_required'] = False
    else:
        plan['tests'] = []
    with pytest.raises(i.Refusal):
        i.validate(plan)
        i.patches(root, plan)


def test_stale_source_stops_before_receipt(repo, monkeypatch, tmp_path):
    _, plan = repo
    def fake_api(endpoint):
        if endpoint.startswith('issues/'):
            return {'issue_url': 'https://api.github.com/repos/MsElysia/Elysia/issues/11', 'body': 'checkpoint', 'created_at': '1970-01-01T00:00:01Z'}
        return {'state': 'open', 'draft': True, 'head': {'sha': 'c' * 40}}
    monkeypatch.setattr(i, 'api', fake_api)
    plan['checkpoint_sha256'] = hashlib.sha256(b'checkpoint').hexdigest()
    with pytest.raises(i.Refusal, match='stale'):
        i.source_gate(plan, {'checkpoint_comment': plan['checkpoint_comment'], 'minimum_verification_epoch': 1}, tmp_path, 'producer')


@pytest.mark.parametrize('attack', ['missing', 'spoof', 'producer', 'same-group', 'stale', 'fail', 'partial', 'wrong-sha', 'wrong-scope'])
def test_verifier_attacks(repo, tmp_path, attack):
    _, plan = repo
    receipt = {'subject': plan['base']['sha'], 'scope': i.digest(plan), 'verdict': 'PASS',
               'verifier': 'verifier', 'issued_at': 10, 'evidence': ['review evidence']}
    trust = {'allowed_signers': str(tmp_path / 'absent-signers'),
             'producers': {'producer': {'group': 'builder'}},
             'verifiers': {'verifier': {'group': 'reviewer'}, 'producer': {'group': 'builder'}}}
    if attack == 'producer': receipt['verifier'] = 'producer'
    if attack == 'same-group': trust['verifiers']['verifier']['group'] = 'builder'
    if attack == 'stale': receipt['issued_at'] = 0
    if attack in {'fail', 'partial'}: receipt['verdict'] = attack.upper()
    if attack == 'wrong-sha': receipt['subject'] = 'b' * 40
    if attack == 'wrong-scope': receipt['scope'] = 'b' * 64
    filename = tmp_path / 'receipt.json'
    if attack != 'missing': filename.write_text(json.dumps(receipt))
    with pytest.raises((i.Refusal, OSError)):
        i.verify_receipt(filename, trust, subject=plan['base']['sha'], scope=i.digest(plan), producer='producer', epoch=1)


@pytest.mark.parametrize('attack', ['missing-job', 'failed-job', 'wrong-toolkit', 'wrong-workflow', 'failed-run'])
def test_hosted_ci_attacks(repo, monkeypatch, attack):
    _, plan = repo
    request = {'plan': plan, 'candidate': plan['sources'][0]['sha'], 'toolkit': 'a' * 40}
    run = {'head_sha': 'd' * 40, 'path': '.github/workflows/bounded-integration.yml',
           'event': 'push', 'conclusion': 'success', 'head_branch': 'integration-evidence/' + i.digest(request)[:20]}
    jobs = [{'name': 'integration-linux', 'conclusion': 'success', 'id': 1},
            {'name': 'integration-windows', 'conclusion': 'success', 'id': 2}]
    if attack == 'missing-job': jobs.pop()
    if attack == 'failed-job': jobs[0]['conclusion'] = 'skipped'
    if attack == 'wrong-toolkit': run['head_branch'] = 'wrong'
    if attack == 'wrong-workflow': run['path'] = '.github/workflows/other.yml'
    if attack == 'failed-run': run['conclusion'] = 'failure'
    monkeypatch.setattr(i, 'api', lambda endpoint: {'jobs': jobs} if '/jobs?' in endpoint else run)
    monkeypatch.setattr(i, 'git', lambda *args, **kwargs: b'')
    monkeypatch.setattr(i, 'validate_request_commit', lambda *args: None)
    with pytest.raises(i.Refusal):
        i.hosted_evidence(plan, plan['sources'][0]['sha'], 'a' * 40, 123)


def test_real_required_suite(repo, tmp_path):
    root, plan = repo
    destination = tmp_path / 'isolated'
    _, head = i.compose(root, plan, destination, 'producer')
    evidence = i.run_tests(destination, plan, head)
    assert evidence['candidate'] == head
    assert evidence['tests'][0]['result'] == 'pass'
    (destination / 'tests/test_feature.py').write_text('def test_feature():\n    assert False\n')
    # A changed test cannot bypass the tree audit, even before pytest is invoked.
    with pytest.raises(i.Refusal):
        i.run_tests(destination, plan, head)


def test_freshness_cannot_be_plan_selected(repo, tmp_path, monkeypatch):
    _, plan = repo
    monkeypatch.setattr(i, 'api', lambda _: {'issue_url': 'https://api.github.com/repos/MsElysia/Elysia/issues/11',
                                          'body': 'checkpoint', 'created_at': '2026-10-09T21:09:38Z'})
    plan['checkpoint_sha256'] = hashlib.sha256(b'checkpoint').hexdigest()
    with pytest.raises(i.Refusal, match='epoch predates'):
        i.source_gate(plan, {'checkpoint_comment': plan['checkpoint_comment'], 'minimum_verification_epoch': 1}, tmp_path, 'producer')


def test_signed_verdict_positive_and_tamper(repo, tmp_path):
    _, plan = repo
    key = tmp_path / 'verifier_key'
    i.command(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)])
    signers = tmp_path / 'allowed_signers'
    signers.write_text('verifier ' + Path(str(key) + '.pub').read_text())
    trust = {'allowed_signers': str(signers), 'producers': {'producer': {'group': 'builder'}},
             'verifiers': {'verifier': {'group': 'independent'}}}
    receipt = {'subject': plan['base']['sha'], 'scope': i.digest(plan), 'verdict': 'PASS',
               'verifier': 'verifier', 'issued_at': 10, 'evidence': ['synthetic independent review']}
    filename = tmp_path / 'receipt.json'
    filename.write_bytes(i.canonical(receipt))
    i.command(['ssh-keygen', '-Y', 'sign', '-n', 'elysia-issue11-integration', '-f', str(key), str(filename)])
    verdict = i.verify_receipt(filename, trust, subject=plan['base']['sha'], scope=i.digest(plan), producer='producer', epoch=1)
    assert verdict['verifier'] == 'verifier'
    receipt['evidence'] = ['forged']
    filename.write_bytes(i.canonical(receipt))
    with pytest.raises(i.Refusal):
        i.verify_receipt(filename, trust, subject=plan['base']['sha'], scope=i.digest(plan), producer='producer', epoch=1)


def test_evidence_request_commit_exactness(repo, tmp_path):
    root, plan = repo
    toolkit = i.git(root, 'rev-parse', 'HEAD').decode().strip()
    plan['toolkit_sha'] = toolkit
    request = {'plan': plan, 'candidate': plan['sources'][0]['sha'], 'toolkit': toolkit}
    (root / 'integration-request.json').write_bytes(i.canonical(request))
    i.git(root, 'add', 'integration-request.json')
    i.git(root, 'commit', '-m', 'evidence request')
    head = i.git(root, 'rev-parse', 'HEAD').decode().strip()
    i.validate_request_commit(root, head, request)
    (root / 'feature.py').write_text('modified tool\n')
    i.git(root, 'commit', '-am', 'tamper')
    with pytest.raises(i.Refusal):
        i.validate_request_commit(root, i.git(root, 'rev-parse', 'HEAD').decode().strip(), request)


def test_no_merge_or_activation_surface():
    source = Path(i.__file__).read_text()
    assert '"merge", "--' not in source
    assert '["gh", "pr", "merge"' not in source
    assert 'TaskLedger' not in source
    assert 'import project_guardian' not in source
