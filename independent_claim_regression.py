"""Independent Agent C probes; local temporary SQLite only. Run pytest this file."""
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from elysia_collective_seed.autopilot.task_ledger import TaskLedger
from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.dryrun_orchestrator import dispatch_and_claim

T = datetime(2030, 1, 1, tzinfo=timezone.utc)
W = Worker('alice', 'local', frozenset({'repair', 'audit'}), frozenset({'repo_write', 'deployment', 'external_write', 'sensitive_data', 'privileged'}))

def packet(**kw):
    return dict(dict(task_id='job', risk_class='repo_write', task_class='repair', required_capabilities=['audit'], dependencies=[], allowed_workers=[], human_approval_required=False, max_attempts=2), **kw)

@pytest.fixture
def db(tmp_path):
    ledger = TaskLedger(tmp_path/'db', execution_workers=[W])
    yield ledger
    ledger.close()

def snapshot(db):
    return [tuple(r) for r in db.conn.execute('SELECT * FROM tasks ORDER BY task_id')], [tuple(r) for r in db.conn.execute('SELECT * FROM events ORDER BY event_id')]

def legacy(db, stage):
    if stage != 'new':
        with db.conn:
            db.conn.execute("UPDATE tasks SET status='running', claimed_by='alice', attempt=1, lease_expires_at=? WHERE task_id='job'", ((T+timedelta(seconds=10)).isoformat(),))
    return T+timedelta(seconds=11) if stage == 'expired' else T

BAD = [{'risk_class':r} for r in ['deployment','external_write','sensitive_data','privileged','bogus',None,{},1]] + [{'human_approval_required':v} for v in [True,'false',0,[],None]] + [{f:v} for f in ['dependencies','allowed_workers','required_capabilities'] for v in [None,{},'alice',[1],[' ']]] + [{'task_class':False}]

@pytest.mark.parametrize('policy', BAD)
@pytest.mark.parametrize('stage', ['new','live','expired'])
def test_policy_all_mutations(db, policy, stage):
    db.put_task(packet(**policy)); now=legacy(db,stage); before=snapshot(db)
    assert not db.claim('job','alice',now=now).claimed
    assert snapshot(db)==before

@pytest.mark.parametrize('stage', ['new','live','expired'])
@pytest.mark.parametrize('mode', ['missing','unknown','offline','risk','class','capability','allowed'])
def test_eligibility_all_mutations(db, stage, mode):
    db.put_task(packet(allowed_workers=['other'] if mode=='allowed' else [])); now=legacy(db,stage)
    if mode=='missing': db.execution_workers={}
    elif mode=='unknown': db.execution_workers={'other':replace(W,worker_id='other')}
    elif mode=='offline': db.execution_workers={'alice':replace(W,available=False)}
    elif mode=='risk': db.execution_workers={'alice':replace(W,risk_classes=frozenset({'read_only'}))}
    elif mode in ['class','capability']: db.execution_workers={'alice':replace(W,capabilities=frozenset({'audit' if mode=='class' else 'repair'}))}
    before=snapshot(db)
    assert not db.claim('job','alice',now=now).claimed
    assert snapshot(db)==before

@pytest.mark.parametrize('status', [None,'queued','claimed','running','verifying','review','blocked','human_review','rejected','archived'])
@pytest.mark.parametrize('stage',['new','live','expired'])
def test_durable_dependencies(db,status,stage):
    if status is not None:
        db.put_task(packet(task_id='dep',status='completed'))
        with db.conn: db.conn.execute('UPDATE tasks SET status=? WHERE task_id=?',(status,'dep'))
    db.put_task(packet(dependencies=['dep'])); now=legacy(db,stage); before=snapshot(db)
    assert not db.claim('job','alice',now=now).claimed
    assert snapshot(db)==before

def test_missing_risk_self_dependency_and_malformed_legacy(db):
    p=packet(); del p['risk_class']; db.put_task(p)
    assert not db.claim('job','alice',now=T).claimed
    for payload in [packet(dependencies=['job']), [], None, 'invalid']:
        with db.conn: db.conn.execute('UPDATE tasks SET payload_json=? WHERE task_id=?',(json.dumps(payload),'job'))
        before=snapshot(db)
        assert not db.claim('job','alice',now=T).claimed
        assert snapshot(db)==before

def test_reopen_and_retry_budget(db):
    db.put_task(packet()); assert db.claim('job','alice',lease_seconds=10,now=T).claimed
    reopened=TaskLedger(db.path)
    try:
        for now in [T+timedelta(seconds=1), T+timedelta(seconds=11)]:
            before=snapshot(reopened); assert not reopened.claim('job','alice',now=now).claimed; assert snapshot(reopened)==before
        reopened.execution_workers={'alice':W}
        assert reopened.claim('job','alice',lease_seconds=10,now=T+timedelta(seconds=11)).claimed
        assert reopened.get('job')['attempt']==2
        assert reopened.claim('job','alice',lease_seconds=10,now=T+timedelta(seconds=12)).reason=='renewed'
        assert reopened.get('job')['attempt']==2
        assert not reopened.claim('job','alice',now=T+timedelta(seconds=23)).claimed
        assert reopened.get('job')['status']=='human_review'
    finally: reopened.close()

def test_reap_then_recheck(db):
    db.put_task(packet()); assert db.claim('job','alice',lease_seconds=10,now=T).claimed
    assert db.reap_expired(T+timedelta(seconds=11))==['job']
    db.execution_workers={}; before=snapshot(db)
    assert not db.claim('job','alice',now=T+timedelta(seconds=12)).claimed
    assert snapshot(db)==before
    db.execution_workers={'alice':W}
    assert db.claim('job','alice',now=T+timedelta(seconds=12)).claimed
    assert db.get('job')['attempt']==2

def test_bridge_advisory_inputs(db):
    db.put_task(packet(task_id='dep',status='queued'))
    assert dispatch_and_claim(db,packet(dependencies=['dep']),{'dep':'completed'},[W]).state=='blocked'
    with db.conn: db.conn.execute("UPDATE tasks SET status='completed' WHERE task_id='dep'")
    db.execution_workers={'alice':replace(W,available=False)}
    assert dispatch_and_claim(db,packet(),{'dep':'completed'},[W]).state=='blocked'
    db.execution_workers={'alice':W}
    result=dispatch_and_claim(db,packet(),{'dep':'blocked'},[])
    assert result.state=='claimed'

def test_stale_bridge_selection_is_rechecked(db,monkeypatch):
    db.put_task(packet(task_id='dep',status='completed'))
    real=db.claim
    def race(*args,**kwargs):
        with sqlite3.connect(db.path) as other: other.execute("UPDATE tasks SET status='blocked' WHERE task_id='dep'")
        return real(*args,**kwargs)
    monkeypatch.setattr(db,'claim',race)
    result=dispatch_and_claim(db,packet(dependencies=['dep']),{'dep':'completed'},[W])
    assert result.state=='claim_blocked' and db.get('job')['attempt']==0

def test_transaction_holds_dependency_and_policy_until_mutation(db):
    db.put_task(packet(task_id='dep',status='completed')); db.put_task(packet(dependencies=['dep']))
    attempted=[]
    def trace(sql):
        if sql.startswith("UPDATE tasks SET status='claimed'"):
            for statement in ["UPDATE tasks SET status='blocked' WHERE task_id='dep'", "UPDATE tasks SET payload_json='{}' WHERE task_id='job'"]:
                with sqlite3.connect(db.path,timeout=0) as other:
                    try: other.execute(statement)
                    except sqlite3.OperationalError as exc: attempted.append(str(exc))
    db.conn.set_trace_callback(trace)
    assert db.claim('job','alice',now=T).claimed
    db.conn.set_trace_callback(None)
    assert len(attempted)>=2 and all('locked' in e for e in attempted)

def test_competing_claims_have_one_owner(db):
    db.put_task(packet()); barrier=Barrier(2)
    def attempt(name):
        ledger=TaskLedger(db.path,execution_workers=[replace(W,worker_id=name)])
        try:
            barrier.wait(timeout=10)
            return ledger.claim('job',name,now=T).claimed
        finally: ledger.close()
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(attempt,['alice','bob']))
    assert sum(results)==1 and db.get('job')['attempt']==1

def test_nonpreferred_worker_and_completion_gate(db):
    db.execution_workers['bob']=replace(W,worker_id='bob',quality=0)
    db.put_task(packet(preferred_worker='alice'))
    assert db.claim('job','bob',now=T).claimed
    assert not db.submit_for_verification('job','alice','p',['local:evidence'],now=T)
    assert db.submit_for_verification('job','bob','p',['local:evidence'],now=T)
    assert db.get('job')['status']=='verifying'
    assert not db.claim('job','bob',now=T).claimed
    assert not db.claim_verification('job','bob',now=T).claimed
    assert not db.accept_verification('job','alice',['local:evidence'],now=T)
