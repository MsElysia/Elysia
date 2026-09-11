"""Independent breaker evidence for exact SHA 0843d9c; never runtime evidence."""
from copy import deepcopy
import random

import pytest

from elysia_collective_seed.autopilot.contracts.checkpoint_reference import evaluate, snapshot_digest

WRITES = ['claim', 'repo_write', 'semantic_write', 'integration', 'merge', 'deploy', 'external_write']


def node(name, parents=()):
    return dict(entity_id=name, parent_refs=list(parents), objective_refs=['objective:'+name],
                lineage_refs=['lineage:'+name], governance_gate_refs=[])


def gate(name, scope):
    return dict(gate_id=name, generation=3, kind='human_governance_required', state='active',
                scope=scope, inherit_to_children=True, blocked_actions=WRITES[:],
                reason='Independent synthetic gate', source_refs=['fixture:breaker'], release=None)


def fixture():
    root = node('root')
    return dict(schema_version=1, revision=9, source_refs=['fixture:breaker'],
                entities=[root], gates=[gate('g', {k:root[k][:] for k in ('objective_refs','lineage_refs')})])


def run(state, entity='root', action='merge', pin=None, checkpoint=None):
    return evaluate(state, dict(entity_id=entity, action=action),
                    trusted_current_digest=snapshot_digest(state) if pin is None else pin,
                    checkpoint=checkpoint)


@pytest.mark.parametrize('seed', range(20))
def test_generated_dags_match_independent_ancestor_walk(seed):
    rng = random.Random(seed)
    state = fixture()
    nodes = [node(str(i), [str(j) for j in range(i) if rng.random() < .12]) for i in range(24)]
    state['entities'] = nodes
    state['gates'] = []
    for i in range(0,24,3):
        scope = {'objective_refs':['objective:'+str(i)], 'lineage_refs':['unmatched:'+str(i)]}
        if i % 2:
            scope = {'objective_refs':['unmatched:'+str(i)], 'lineage_refs':['lineage:'+str(i)]}
        state['gates'].append(gate('gate:'+str(i), scope))
    extra = gate('explicit', {'objective_refs':['nowhere'], 'lineage_refs':['nowhere']})
    state['gates'].append(extra)
    nodes[7]['governance_gate_refs'] = ['explicit']
    lookup = {n['entity_id']:n for n in nodes}
    rng.shuffle(state['entities'])
    for target in lookup:
        ancestors = set()
        todo = [target]
        while todo:
            current = todo.pop()
            if current not in ancestors:
                ancestors.add(current)
                todo.extend(lookup[current]['parent_refs'])
        expected = {('gate:'+a,3) for a in ancestors if int(a)%3 == 0}
        if '7' in ancestors:
            expected.add(('explicit',3))
        result = run(state,target)
        assert set(result.effective_active_gates) == expected
        assert result.disposition == ('BLOCKED_PENDING_HUMAN_RELEASE' if expected else 'NO_MATCHING_BLOCK_NOT_AUTHORIZATION')
        assert result.release_validation == 'UNAVAILABLE'
        assert result.external_write_enforcement == 'NOT_ENFORCED'


@pytest.mark.parametrize('action',WRITES)
def test_newer_checkpoint_and_released_null_cannot_clear_gate(action):
    state = fixture()
    state['gates'][0]['state'] = 'released'
    # Deliberately no release claim at all; stored status still cannot authorize.
    newer = {'source':'issue:11/comment:5639976542',
             'candidate':'7374820642fad52a6264c86df8632c3a630df592',
             'next':'verify and continue CWA', 'effective_active_gates':[]}
    result = run(state,action=action,checkpoint=newer)
    assert result.disposition == 'BLOCKED_PENDING_HUMAN_RELEASE'
    assert result.effective_active_gates == (('g',3),)


@pytest.mark.parametrize('value',[None,False,0,1.5,'',[],{},['root','root'],['absent']])
def test_disconnected_parent_record_invalidates_even_read(value):
    state = fixture()
    bad = node('bad')
    bad['parent_refs'] = value
    if value == []: # Valid empty parents become a disconnected two-node cycle.
        bad['parent_refs'] = ['other']
        state['entities'].append(node('other',['bad']))
    state['entities'].append(bad)
    assert run(state,action='read').disposition == 'BLOCKED_INVALID_STATE'


@pytest.mark.parametrize('field',['objective_refs','lineage_refs','governance_gate_refs'])
def test_unknown_reference_fields_cannot_override_parent_scope(field):
    state = fixture()
    descendant = node('child',['root'])
    descendant[field] = [] if field == 'governance_gate_refs' else ['fresh-label']
    state['entities'].append(descendant)
    assert run(state,'child').disposition == 'BLOCKED_PENDING_HUMAN_RELEASE'


@pytest.mark.parametrize('mutation',['omit','replay','released','scope','child'])
def test_current_pin_rejects_rollback_or_substitution(mutation):
    state = fixture()
    state['entities'].append(node('child',['root']))
    pin = snapshot_digest(state)
    modified = deepcopy(state)
    if mutation == 'omit': modified['gates'] = []
    if mutation == 'replay': modified['gates'][0]['generation'] = 2
    if mutation == 'released': modified['gates'][0]['state'] = 'released'
    if mutation == 'scope': modified['gates'][0]['scope']['objective_refs'] = ['other']
    if mutation == 'child': modified['entities'][1]['parent_refs'] = []
    assert run(modified,'child',pin=pin).disposition == 'BLOCKED_INVALID_STATE'


def test_custom_read_block_and_multiple_released_gates_remain_effective():
    state = fixture()
    second = deepcopy(state['gates'][0])
    second.update(gate_id='second',state='released',generation=99)
    second['blocked_actions'].append('read')
    state['gates'].append(second)
    result = run(state,action='read')
    assert result.disposition == 'BLOCKED_PENDING_HUMAN_RELEASE'
    assert result.effective_active_gates == (('g',3),('second',99))


def test_deep_reverse_chain_has_no_recursion_escape():
    state = fixture()
    state['entities'] += [node(f'n{i:04}', ['root' if i == 0 else f'n{i-1:04}']) for i in range(1100)]
    state['entities'].reverse()
    assert run(state,'n1099').disposition == 'BLOCKED_PENDING_HUMAN_RELEASE'


def test_caller_chosen_omitted_state_pin_is_explicitly_not_protected():
    state = fixture()
    state['gates'] = []
    result = run(state)
    assert result.disposition == 'NO_MATCHING_BLOCK_NOT_AUTHORIZATION'
    assert result.external_write_enforcement == 'NOT_ENFORCED'
    assert result.release_validation == 'UNAVAILABLE'
