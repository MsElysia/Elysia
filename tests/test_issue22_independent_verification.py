"""Independent issue-22 acceptance probes: public API, local SQLite/artifacts only."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.task_ledger import TaskLedger

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def open_db(tmp_path):
    return TaskLedger(tmp_path / 'independent.db', verification_workers=[
        Worker('review', 'independent', frozenset({'verification'}), frozenset({'repo_write'}))
    ], independence_groups={'producer': 'p', 'review': 'r'})


def begin(tmp_path):
    ledger = open_db(tmp_path)
    ledger.put_task(dict(task_id='probe', status='queued', title='local probe',
        objective='verify only', risk_class='repo_write', max_attempts=3,
        human_approval_required=False, required_capabilities=['verification'],
        required_checks=['bytes'], acceptance_criteria=['local artifact'], source_refs=['local:test']))
    assert ledger.claim('probe', 'producer', lease_seconds=60, now=NOW).claimed
    artifact = tmp_path / 'result.txt'
    artifact.write_bytes(b'independently checked content\n')
    return ledger, artifact


def submit(ledger, artifact, **kwargs):
    return ledger.submit_for_verification('probe', 'producer', 'packet-1', [str(artifact)],
        now=NOW, completion_checks=[dict(name='bytes', result='pass', evidence=[str(artifact)])], **kwargs)


def install_authority(ledger, artifact):
    # Authority comes from actual independently read bytes and the exact snapshot.
    # A trusted check report is persisted outside the ledger and subsequently reread.
    row = ledger.get('probe')
    report = artifact.with_suffix('.report.json')
    report.write_text(json.dumps(dict(digest=row['completion_submission_digest'],
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())))
    def authority(snapshot):
        proof = json.loads(report.read_text())
        raw = json.dumps(snapshot, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return (proof['digest'] == 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()
                and snapshot['evidence_refs'] == [str(artifact)]
                and artifact.read_bytes() == b'independently checked content\n'
                and hashlib.sha256(artifact.read_bytes()).hexdigest() == proof['artifact_sha256']
                and snapshot['checks'] == [dict(name='bytes', result='pass', evidence=[str(artifact)])])
    ledger.evidence_validator = authority
    return row['completion_submission_digest'], authority


def accept(ledger, digest, now=NOW):
    return ledger.accept_verification('probe', 'review', ['local:review-note'],
        now=now, expected_submission_digest=digest)


@pytest.mark.parametrize('damage', ['missing', 'invalid', 'missing_report'])
def test_invalid_or_missing_evidence_does_not_complete(tmp_path, damage):
    ledger, artifact = begin(tmp_path)
    try:
        assert submit(ledger, artifact)
        assert ledger.claim_verification('probe', 'review', now=NOW).claimed
        digest, _ = install_authority(ledger, artifact)
        if damage == 'missing': artifact.unlink()
        elif damage == 'invalid': artifact.write_bytes(b'wrong bytes')
        else: artifact.with_suffix('.report.json').unlink()
        history = ledger.events('probe')
        assert not accept(ledger, digest)
        assert ledger.get('probe')['status'] == 'verifying'
        assert ledger.events('probe') == history
    finally: ledger.close()


@pytest.mark.parametrize('conflict', ['checks', 'task_id', 'packet_id', 'outcome'])
def test_conflicting_completion_packet_and_checks_fail_closed(tmp_path, conflict):
    ledger, artifact = begin(tmp_path)
    try:
        packet = dict(task_id='probe', packet_id='packet-1', evidence_refs=[str(artifact)],
            worker={'provider': 'independent', 'role': 'engineer'}, summary='Local result',
            next_recommendation={'action': 'verify'}, outcome='completed',
            checks=[dict(name='bytes', result='pass', evidence=[str(artifact)])])
        if conflict == 'checks': packet['checks'][0]['result'] = 'fail'
        else: packet[conflict] = {'task_id': 'other-task', 'packet_id': 'other-packet', 'outcome': 'blocked'}[conflict]
        if not submit(ledger, artifact, completion_packet=packet):
            return  # Rejecting inconsistent input at submission is also safe.
        assert ledger.claim_verification('probe', 'review', now=NOW).claimed
        digest, _ = install_authority(ledger, artifact)
        assert not accept(ledger, digest), f'Conflicting packet {conflict} was accepted'
    finally: ledger.close()


def test_expired_producer_lease_rejects_submission(tmp_path):
    ledger, artifact = begin(tmp_path)
    try:
        assert not ledger.submit_for_verification('probe', 'producer', 'late', [str(artifact)],
            now=NOW + timedelta(seconds=60), completion_checks=[dict(name='bytes', result='pass')])
        assert ledger.get('probe')['status'] != 'completed'
    finally: ledger.close()


def test_consistent_full_packet_completes_and_survives_reopen(tmp_path):
    ledger, artifact = begin(tmp_path)
    packet = dict(task_id='probe', packet_id='packet-1', evidence_refs=[str(artifact)],
        worker={'provider': 'independent', 'role': 'engineer'}, summary='Local result',
        next_recommendation={'action': 'verify'}, outcome='completed', attempt=1,
        checks=[dict(name='bytes', result='pass', evidence=[str(artifact)])])
    assert submit(ledger, artifact, completion_packet=packet)
    assert ledger.claim_verification('probe', 'review', now=NOW).claimed
    digest, authority = install_authority(ledger, artifact)
    ledger.close()
    ledger = open_db(tmp_path)
    try:
        ledger.evidence_validator = authority
        assert accept(ledger, digest)
        assert ledger.get('probe')['completion_submission']['packet'] == packet
        assert ledger.get('probe')['status'] == 'completed'
    finally: ledger.close()


def test_expired_review_lease_rejects_acceptance(tmp_path):
    ledger, artifact = begin(tmp_path)
    try:
        assert submit(ledger, artifact)
        assert ledger.claim_verification('probe', 'review', lease_seconds=5, now=NOW).claimed
        digest, _ = install_authority(ledger, artifact)
        assert not accept(ledger, digest, NOW + timedelta(seconds=5))
    finally: ledger.close()


def test_reopen_and_duplicate_acceptance_preserve_exact_submission(tmp_path):
    ledger, artifact = begin(tmp_path)
    assert submit(ledger, artifact)
    assert ledger.claim_verification('probe', 'review', now=NOW).claimed
    digest, authority = install_authority(ledger, artifact)
    snapshot = ledger.get('probe')['completion_submission']
    ledger.close()
    ledger = open_db(tmp_path)
    try:
        assert not accept(ledger, digest)
        ledger.evidence_validator = authority
        assert accept(ledger, digest)
        history = ledger.events('probe')
        assert not accept(ledger, digest)
        assert ledger.events('probe') == history
        assert ledger.get('probe')['completion_submission'] == snapshot
        assert ledger.get('probe')['status'] == 'completed'
    finally: ledger.close()


def test_stale_submission_digest_cannot_accept_next_attempt(tmp_path):
    ledger, artifact = begin(tmp_path)
    try:
        assert submit(ledger, artifact)
        assert ledger.claim_verification('probe', 'review', now=NOW).claimed
        old, _ = install_authority(ledger, artifact)
        assert ledger.reject_verification('probe', 'review', 'retry', [], now=NOW)
        assert ledger.claim('probe', 'producer', now=NOW).claimed
        assert submit(ledger, artifact)
        assert ledger.claim_verification('probe', 'review', now=NOW).claimed
        current, _ = install_authority(ledger, artifact)
        assert old != current
        assert not accept(ledger, old)
        assert accept(ledger, current)
    finally: ledger.close()
