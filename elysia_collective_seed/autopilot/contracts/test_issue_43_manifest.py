"""M01–M20 synthetic model schedules; never real storage/restart evidence."""
from copy import deepcopy
import json

import pytest

from .manifest_reference import ModelStore, decode, pointer
from .checkpoint_reference import snapshot_digest
from .test_issue_33_scope_inheritance import issue_33_state, assert_gated
from .admission import evaluate_admitted

ACCEPTED = 'ACCEPTED_MODEL_POINTER_NOT_AUTHORIZATION'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fixtures():
    state = issue_33_state()
    ungated = deepcopy(state['admissions'][0])
    ungated.update(entity_id='fixture:ungated-docs', objective_refs=['fixture:unrelated'],
                   repository_lineage_refs=['fixture:unrelated'], governance_lineage_refs=['fixture:unrelated'],
                   governance_gate_refs=[], action_classes=['docs_only'])
    state['admissions'].append(ungated)
    claim = {'claim_id': 'fixture:failed', 'scope': 'generation', 'state': 'FAIL', 'evidence_refs': ['fixture:breaker']}
    record = {'item_id': 'fixture:pr34', 'item_ref': 'fixture:pr34', 'entity_id': 'product-7374820',
              'action': 'semantic_code_write', 'product_sha': '7'*40, 'head_sha': '8'*40,
              'base_sha': '4'*40, 'acceptance_contract': {'ref': 'fixture:contract', 'digest': 'c'*64},
              'claims': [claim], 'blockers': ['fixture:human_gate'], 'disposition': 'BLOCKED'}
    inventory = {record['item_id']: record}
    pins = {'repository': 'fixture:MsElysia/Elysia', 'control_plane_ref': 'fixture:issue11',
            'inventory_ref': 'fixture:inventory:1', 'inventory_digest': snapshot_digest(inventory),
            'snapshot_ref': 'fixture:snapshot:33', 'snapshot_digest': snapshot_digest(state)}
    manifest = {'manifest_schema_version': 1, 'repository': pins['repository'],
                'control_plane_ref': pins['control_plane_ref'], 'manifest_generation': 1,
                'predecessor': {'pointer_schema_version': 1, 'repository': pins['repository'],
                                'control_plane_ref': pins['control_plane_ref'], 'manifest_generation': 1,
                                'manifest_digest': '0'*64},
                'checkpoint_ref': 'fixture:checkpoint:1',
                'governance_snapshot': {'ref': pins['snapshot_ref'], 'digest': pins['snapshot_digest'],
                                        'snapshot_generation': state['snapshot_generation']},
                'coverage': {'inventory_ref': pins['inventory_ref'], 'inventory_digest': pins['inventory_digest'],
                             'item_ids': sorted(inventory), 'unresolved_sources': []},
                'routing_records': list(inventory.values()),
                'retained_boundaries': {'snapshot_digest': pins['snapshot_digest'], 'archive_reconciliation': 'REQUIRED',
                    'closed_paths': ['runtime', 'provider', 'autonomy', 'live_memory', 'taskledger', 'executor',
                                     'merge', 'deploy', 'permission', 'private_data', 'credential', 'gate_release'],
                    'production_enforcement': 'NOT_IMPLEMENTED', 'external_write_enforcement': 'NOT_ENFORCED',
                    'human_trust_anchor': 'UNRESOLVED', 'release_validation': 'UNAVAILABLE'}}
    store = ModelStore(manifest, inventory, state, pins)
    return store, manifest, inventory, state, pins


def successor(store):
    current, old = store.read()
    new = deepcopy(old)
    new.update(manifest_generation=current['manifest_generation']+1, predecessor=current,
               checkpoint_ref='fixture:checkpoint:'+str(current['manifest_generation']+1))
    return new


def reject_without_change(store, candidate, expected='BLOCKED_INVALID_STATE'):
    before = store.state_bytes()
    raw = candidate if isinstance(candidate, str) else encoded(candidate)
    result, receipt = store.prepare(raw)
    assert result == expected and receipt is None
    assert store.state_bytes() == before


def prepared(store, candidate):
    status, receipt = store.prepare(encoded(candidate))
    assert status == 'PREPARED'
    return receipt


def test_M01_complete_successor_retains_gates_and_history():
    store, old, inventory, snapshot, pins = fixtures()
    before = store.state_bytes()
    receipt = prepared(store, successor(store))
    assert store.commit(receipt) == ACCEPTED
    assert store.read()[0]['manifest_generation'] == 2
    for digest, data in before[1].items():
        assert store.state_bytes()[1][digest] == data
        assert store.state_bytes()[2][digest] == before[2][digest]
    assert_gated(evaluate_admitted(snapshot, 'product-7374820', 'semantic_code_write',
                 trusted_current_digest=pins['snapshot_digest'], minimum_generation=33))


@pytest.mark.parametrize('value', [True, False, None, '2', 2.0, [], {}, 0, -1])
def test_M02_exact_generation(value):
    store, *_ = fixtures(); candidate = successor(store)
    candidate['manifest_generation'] = value
    reject_without_change(store, candidate)


@pytest.mark.parametrize('mutation', ['unknown_version', 'missing_version', 'extra', 'duplicate_id', 'duplicate_claim'])
def test_M02_schema_and_duplicate_identity(mutation):
    store, *_ = fixtures(); candidate = successor(store)
    if mutation == 'unknown_version': candidate['manifest_schema_version'] = 2
    elif mutation == 'missing_version': del candidate['manifest_schema_version']
    elif mutation == 'extra': candidate['owner'] = 'MsElysia'
    elif mutation == 'duplicate_id': candidate['routing_records'] *= 2
    else: candidate['routing_records'][0]['claims'] *= 2
    reject_without_change(store, candidate)


@pytest.mark.parametrize('raw', ['{"manifest_generation":1,"manifest_generation":2}', '{"x":NaN}', '{"x":Infinity}', '{'])
def test_M02_duplicate_key_and_nonfinite_decode(raw):
    store, *_ = fixtures(); reject_without_change(store, raw)


@pytest.mark.parametrize('mutation', ['item', 'finding', 'criterion', 'catchall', 'unresolved_source'])
def test_M03_no_omissions_or_catchall(mutation):
    store, *_ = fixtures(); candidate = successor(store)
    if mutation == 'item': candidate['routing_records'] = []
    elif mutation == 'finding': candidate['routing_records'][0]['claims'] = []
    elif mutation == 'criterion': candidate['routing_records'][0]['blockers'] = []
    elif mutation == 'unresolved_source': candidate['coverage']['unresolved_sources'] = ['fixture:missing']
    else: candidate['coverage']['item_ids'] = ['all_unlisted_carry_forward']
    reject_without_change(store, candidate)


@pytest.mark.parametrize('field', ['inventory', 'snapshot'])
def test_M04_worker_self_hash_cannot_replace_independent_pin(field):
    store, *_ = fixtures(); candidate = successor(store)
    if field == 'inventory': candidate['coverage']['inventory_digest'] = snapshot_digest({'worker': 'replacement'})
    else: candidate['governance_snapshot']['digest'] = snapshot_digest({'gates': []})
    reject_without_change(store, candidate)


@pytest.mark.parametrize('mutation', ['closed_path', 'boundary_pin', 'release', 'disposition', 'scope', 'action'])
def test_M05_retained_boundaries_and_admitted_effect(mutation):
    store, *_ = fixtures(); candidate = successor(store)
    if mutation == 'closed_path': candidate['retained_boundaries']['closed_paths'].remove('merge')
    elif mutation == 'boundary_pin': candidate['retained_boundaries']['snapshot_digest'] = '0'*64
    elif mutation == 'release': candidate['retained_boundaries']['release_validation'] = 'AVAILABLE'
    elif mutation == 'disposition': candidate['routing_records'][0]['disposition'] = 'REVIEW_ONLY_NOT_AUTHORIZATION'
    elif mutation == 'scope': candidate['routing_records'][0]['entity_id'] = 'worker-root'
    else: candidate['routing_records'][0]['action'] = 'docs_only'
    reject_without_change(store, candidate)


@pytest.mark.parametrize('actor', ['OWNER', 'GitHub App', 'direct human'])
def test_M06_release_actor_assertion_is_not_authority(actor):
    store, *_ = fixtures(); candidate = successor(store)
    candidate['release'] = {'actor': actor, 'state': 'released'}
    reject_without_change(store, candidate)


def set_inventory(store, candidate, inventory, state, pins):
    pins = deepcopy(pins); pins['inventory_digest'] = snapshot_digest(inventory)
    store.replace_fixture_sources(inventory, state, pins)
    candidate['coverage'] = {'inventory_ref': pins['inventory_ref'], 'inventory_digest': pins['inventory_digest'],
                             'item_ids': sorted(inventory), 'unresolved_sources': []}
    candidate['routing_records'] = deepcopy(list(inventory.values()))
    return pins


def test_M07_same_scope_fail_dominates_pass_but_narrow_pass_retained():
    store, _, inventory, state, pins = fixtures(); candidate = successor(store)
    updated = deepcopy(inventory)
    updated['fixture:pr34']['claims'] += [
        {'claim_id': 'fixture:pass', 'scope': 'generation', 'state': 'PASS', 'evidence_refs': ['fixture:ci']},
        {'claim_id': 'fixture:narrow', 'scope': 'static_other', 'state': 'PASS', 'evidence_refs': ['fixture:test']}]
    set_inventory(store, candidate, updated, state, pins)
    assert store.commit(prepared(store, candidate)) == ACCEPTED
    assert store.read()[1]['routing_records'][0]['disposition'] == 'BLOCKED'
    candidate = successor(store); updated['fixture:pr34']['disposition'] = 'REVIEW_ONLY_NOT_AUTHORIZATION'
    set_inventory(store, candidate, updated, state, store._pins)
    reject_without_change(store, candidate)


@pytest.mark.parametrize('has_blocker', [True, False])
def test_M07_ungated_passing_addition_still_respects_required_blocker(has_blocker):
    store, _, inventory, state, pins = fixtures(); candidate = successor(store)
    updated = deepcopy(inventory)
    record = deepcopy(updated['fixture:pr34'])
    record.update(item_id='fixture:docs', item_ref='fixture:docs', entity_id='fixture:ungated-docs',
                  action='docs_only', product_sha=None, head_sha=None, base_sha=None,
                  claims=[{'claim_id':'fixture:docs-pass', 'scope':'docs', 'state':'PASS', 'evidence_refs':['fixture:test']}],
                  blockers=['fixture:required_acceptance'] if has_blocker else [],
                  disposition='REVIEW_ONLY_NOT_AUTHORIZATION')
    updated[record['item_id']] = record
    set_inventory(store, candidate, updated, state, pins)
    if has_blocker:
        reject_without_change(store, candidate)
    else:
        assert store.commit(prepared(store, candidate)) == ACCEPTED


def test_M03_even_new_independent_inventory_cannot_drop_previous_blocker():
    store, _, inventory, state, pins = fixtures(); candidate = successor(store)
    updated = deepcopy(inventory); updated['fixture:pr34']['blockers'] = []
    set_inventory(store, candidate, updated, state, pins)
    reject_without_change(store, candidate)


@pytest.mark.parametrize('field', ['product_sha', 'head_sha', 'base_sha', 'acceptance_contract'])
def test_M08_product_and_contract_binding(field):
    store, *_ = fixtures(); candidate = successor(store)
    candidate['routing_records'][0][field] = {'ref':'fixture:other','digest':'b'*64} if field == 'acceptance_contract' else 'a'*40
    reject_without_change(store, candidate)


def test_M09_routing_generation_does_not_advance_snapshot():
    store, old, *_ = fixtures(); candidate = successor(store)
    assert store.commit(prepared(store, candidate)) == ACCEPTED
    assert store.read()[1]['governance_snapshot'] == old['governance_snapshot']


@pytest.mark.parametrize('field,value', [('manifest_digest','f'*64), ('repository','fixture:other'),
    ('control_plane_ref','fixture:other'), ('pointer_schema_version',2), ('manifest_generation',True)])
def test_M10_whole_predecessor_token(field,value):
    store, *_ = fixtures(); candidate = successor(store)
    candidate['predecessor'][field] = value
    reject_without_change(store, candidate, 'BLOCKED_INVALID_STATE' if field == 'pointer_schema_version' or value is True else 'STALE_PREDECESSOR')


@pytest.mark.parametrize('generation', [1, 0, 3])
def test_M11_equal_rollback_and_skipped_generation(generation):
    store, *_ = fixtures(); candidate = successor(store); candidate['manifest_generation'] = generation
    reject_without_change(store, candidate)


def test_M11_missing_predecessor_never_bootstraps():
    store, *_ = fixtures(); candidate = successor(store); del candidate['predecessor']
    reject_without_change(store, candidate)


def test_M12_validated_loser_cannot_overwrite_winner():
    store, *_ = fixtures(); a = successor(store); b = deepcopy(a); b['checkpoint_ref'] = 'fixture:B'
    ra, rb = prepared(store, a), prepared(store, b)
    assert store.commit(rb) == ACCEPTED
    before = store.state_bytes()
    assert store.commit(ra) == 'STALE_PREDECESSOR'
    assert store.state_bytes() == before


@pytest.mark.parametrize('first', [0,1])
def test_M13_deterministic_two_writer_orders(first):
    store, *_ = fixtures(); a = successor(store); b = deepcopy(a); b['checkpoint_ref'] = 'fixture:B'
    receipts = [prepared(store, a), prepared(store, b)]
    assert [store.commit(receipts[first]), store.commit(receipts[1-first])] == [ACCEPTED,'STALE_PREDECESSOR']


@pytest.mark.parametrize('source', ['inventory','snapshot'])
def test_M14_source_race_fenced_with_unchanged_pointer(source):
    store, _, inventory, state, pins = fixtures(); receipt = prepared(store, successor(store))
    pins = deepcopy(pins); pins[source+'_ref'] += ':new_revision'
    store.replace_fixture_sources(inventory, state, pins)
    before = store.state_bytes()
    assert store.commit(receipt) == 'STALE_SOURCE'
    assert store.state_bytes() == before


def test_M15_materialization_failure_retains_all_bytes():
    store, *_ = fixtures(); before = store.state_bytes()
    assert store.prepare(encoded(successor(store)), fail_materialization=True) == ('MATERIALIZATION_UNAVAILABLE',None)
    assert store.state_bytes() == before


@pytest.mark.parametrize('damage', ['candidate','dependency'])
def test_M15_prepared_dependency_unavailable_never_publishes(damage):
    store, *_ = fixtures(); receipt = prepared(store, successor(store)); current = deepcopy(store._pointer)
    digest = receipt['candidate']['manifest_digest']
    if damage == 'candidate': store._objects[digest] = '{}'
    else: del store._dependencies[digest]
    # Commit must require previously materialized candidate dependencies.
    assert store.commit(receipt) == 'BLOCKED_INVALID_STATE'
    assert store._pointer == current


def test_M16_interrupt_boundaries_are_old_complete_or_new_complete_model_only():
    store, old, *_ = fixtures(); receipt = prepared(store, successor(store))
    assert store.read()[1] == old  # Interrupted before commit: prepared object not current.
    assert store.commit(receipt) == ACCEPTED
    assert store.read()[0] == receipt['candidate']  # Lost reply: new complete state.
    assert store.commit(receipt) == 'ALREADY_CURRENT'


def test_M17_reader_between_each_prepare_and_commit_step():
    store, *_ = fixtures(); old = store.read(); candidate = successor(store)
    receipt = prepared(store, candidate); assert store.read() == old
    assert store.commit(receipt) == ACCEPTED
    assert store.read() == (pointer(candidate), candidate)


def test_M18_duplicate_request_then_replay_after_successor():
    store, *_ = fixtures(); candidate = successor(store); receipt = prepared(store, candidate)
    assert store.commit(receipt) == ACCEPTED
    before = store.state_bytes(); assert store.prepare(encoded(candidate)) == ('ALREADY_CURRENT',None)
    assert store.commit(receipt) == 'ALREADY_CURRENT'; assert store.state_bytes() == before
    assert store.commit(prepared(store, successor(store))) == ACCEPTED
    before = store.state_bytes(); assert store.commit(receipt) == 'STALE_PREDECESSOR'
    reject_without_change(store, candidate, 'STALE_PREDECESSOR'); assert store.state_bytes() == before


@pytest.mark.parametrize('damage', ['missing_pointer','corrupt_pointer','missing_current_object','missing_current_dependency'])
def test_M19_unavailable_pointer_has_no_prose_fallback(damage):
    store, *_ = fixtures(); candidate = successor(store)
    if damage == 'missing_pointer': store._pointer = None
    elif damage == 'corrupt_pointer': store._pointer['manifest_digest'] = 'f'*64
    elif damage == 'missing_current_object': store._objects.clear()
    else: store._dependencies.clear()
    reject_without_change(store, candidate)


def test_M19_nonatomic_store_refuses_commit():
    store, *_ = fixtures(); store.atomic = False; receipt = prepared(store, successor(store))
    before = store.state_bytes(); assert store.commit(receipt) == 'ATOMIC_ACCEPTANCE_UNAVAILABLE'
    assert store.state_bytes() == before


def test_M19_reader_schema_corruption_returns_unavailable_diagnostic():
    store, *_ = fixtures()
    store._pointer['pointer_schema_version'] = 2
    before = store.state_bytes()
    with pytest.raises(ValueError, match='unavailable_current_state'):
        store.read()
    assert store.state_bytes() == before


def test_M20_json_reconstruction_and_replay_are_deterministic_not_real_restart():
    def schedule():
        store, old, inventory, state, pins = fixtures()
        restored = ModelStore(decode(encoded(old)), decode(encoded(inventory)), decode(encoded(state)), decode(encoded(pins)))
        receipt = prepared(restored, successor(restored))
        result = restored.commit(receipt)
        return result, restored.read(), restored.state_bytes()
    assert schedule() == schedule()
