"""Real local extraction/persistence; no model or network required."""
import hashlib
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from test_control_panel_restricted_runtime import _auth, _memory, _panel
from project_guardian.document_ingestion import DocumentLibrary, ImportFailure
from project_guardian.local_memory_chat import build_context_from_adapter


FACT = 'The Veridia expedition stores its cobalt compass in the Lumenport observatory.'


def test_text_restart_dedupe_and_grounding(tmp_path):
    memory = _memory(tmp_path / 'memory.json')
    library = DocumentLibrary(memory)
    receipt = library.import_bytes('compass.txt', FACT.encode())
    assert receipt['status'] == 'completed'
    count = len(memory.memory_log)
    assert library.import_bytes('renamed.txt', FACT.encode())['duplicate']
    assert len(memory.memory_log) == count
    restored = DocumentLibrary(_memory(tmp_path / 'memory.json'))
    matches = restored.search('Where is the Veridia compass kept?')
    assert matches[0]['source_id'] == receipt['source_id']
    assert matches[0]['text'] == FACT
    assert (library.root / receipt['managed_copy']).read_bytes() == FACT.encode()
    panel = _panel(restored.memory, config={'contained_startup': True})
    bundle = build_context_from_adapter(panel._restricted_adapter(), 'Where is the Veridia compass kept?', {})
    assert bundle['evidence'][0]['source_id'] == receipt['source_id']
    assert bundle['evidence'][0]['trust'] == 'untrusted_document'
    assert not panel._restricted_adapter().current_fact_snapshots()


def test_pdf_docx_csv_extractors(tmp_path):
    pytest.importorskip('pypdf')
    canvas = pytest.importorskip('reportlab.pdfgen.canvas')
    docx = pytest.importorskip('docx')
    pdf = io.BytesIO()
    c = canvas.Canvas(pdf)
    c.drawString(50, 750, FACT)
    c.showPage()
    c.drawString(50, 750, 'The expedition departure date is 19 November 2026.')
    c.save()
    document = docx.Document()
    document.add_paragraph(FACT)
    word = io.BytesIO()
    document.save(word)
    library = DocumentLibrary(_memory(tmp_path / 'memory.json'))
    for name, raw in [('guide.pdf', pdf.getvalue()), ('guide.docx', word.getvalue()), ('guide.csv', b'item,location\ncompass,Lumenport observatory')]:
        receipt = library.import_bytes(name, raw)
        assert receipt['status'] == 'completed'
        assert library.import_bytes(name, raw)['duplicate']
    assert any(row['page'] == 2 for row in library.search('departure November'))


@pytest.mark.parametrize('name,raw', [('../escape.txt', b'abc'), ('bad.exe', b'abc'), ('bad.txt', b'\x00binary'), ('bad.pdf', b'%PDF-broken'), ('empty.txt', b''), ('fake.txt', b'%PDF-1.4 pretend')])
def test_unsafe_or_unextractable_never_searchable(tmp_path, name, raw):
    library = DocumentLibrary(_memory(tmp_path / 'memory.json'))
    with pytest.raises(ImportFailure):
        library.import_bytes(name, raw)
    assert not library.search('binary broken pretend')
    assert not any(r['status'] == 'completed' for r in library.receipts())


def test_interrupted_index_retry_and_concurrent_dedupe(tmp_path, monkeypatch):
    library = DocumentLibrary(_memory(tmp_path / 'memory.json'))
    original = library._save
    state = {'failed': False}
    def fail_once(category, text, meta):
        if category == 'document_source' and meta['status'] == 'completed' and not state['failed']:
            state['failed'] = True
            raise OSError('synthetic disk failure')
        original(category, text, meta)
    monkeypatch.setattr(library, '_save', fail_once)
    with pytest.raises(ImportFailure):
        library.import_bytes('guide.txt', FACT.encode())
    assert not library.search('Veridia compass')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: library.import_bytes('guide.txt', FACT.encode()), range(2)))
    assert sum(r['duplicate'] for r in results) == 1
    assert len([e for e in library.memory.memory_log if e['category'] == 'document_chunk']) == 1


def test_upload_api_requires_operator_and_preserves_sources(tmp_path):
    panel = _panel(_memory(tmp_path / 'memory.json'), config={'contained_startup': True})
    client = panel.app.test_client()
    assert client.post('/api/documents').status_code == 401
    preview = client.post('/api/documents/preview', headers=_auth(panel), data={'file': (io.BytesIO(FACT.encode()), 'guide.txt')})
    assert preview.status_code == 200, preview.get_json()
    body = preview.get_json()['preview']
    assert body['chunk_count'] >= 1
    assert 'Veridia' in body['preview_text']
    assert body['ocr_available'] is False
    response = client.post('/api/documents', headers=_auth(panel), data={'file': (io.BytesIO(FACT.encode()), 'guide.txt')})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['document']['status'] == 'completed'
    result = client.post('/api/documents/search', headers=_auth(panel), json={'query': 'Veridia compass'})
    assert result.get_json()['matches'][0]['filename'] == 'guide.txt'
    status = client.get('/api/documents', headers=_auth(panel)).get_json()
    assert status['state'] == 'Idle'
    assert status['indexed_chunks'] == 1
    assert len([e for e in status['events'] if e['event'].startswith('Document import') or e['event'].startswith('Document chunks')]) == 2
    assert FACT not in json.dumps(status['events'])
    assert 'blank_console_note' in status
    assert client.get('/api/documents', headers=_auth(panel), environ_overrides={'REMOTE_ADDR': '203.0.113.3'}).status_code == 403



def _seed_hard_link(sentinel, planted):
    """Place a same-volume hard link, not a symlink, in the managed area."""
    sentinel.write_bytes(b'outside-library-sentinel-must-survive')
    planted.parent.mkdir(parents=True, exist_ok=True)
    os.link(sentinel, planted)
    assert planted.samefile(sentinel)


def test_preview_never_overwrites_or_deletes_preexisting_hardlink(tmp_path):
    library = DocumentLibrary(_memory(tmp_path / 'memory.json'))
    raw = FACT.encode('utf-8')
    source = 'doc_' + hashlib.sha256(raw).hexdigest()
    planted = library.root / ('_preview_' + source + '.txt')
    sentinel = tmp_path / 'outside-preview-sentinel.txt'
    _seed_hard_link(sentinel, planted)

    preview = library.preview_bytes('compass.txt', raw)
    assert preview['source_id'] == source
    assert 'Veridia expedition' in preview['preview_text']
    assert sentinel.read_bytes() == b'outside-library-sentinel-must-survive'
    assert planted.samefile(sentinel)
    assert not list(library.root.glob('.extract-*'))


def test_import_never_overwrites_preexisting_worker_output_hardlink(tmp_path):
    library = DocumentLibrary(_memory(tmp_path / 'memory.json'))
    raw = FACT.encode('utf-8')
    source = 'doc_' + hashlib.sha256(raw).hexdigest()
    planted = library.root / (source + '.extracted.json')
    sentinel = tmp_path / 'outside-import-sentinel.json'
    _seed_hard_link(sentinel, planted)

    receipt = library.import_bytes('compass.txt', raw)
    assert receipt['status'] == 'completed'
    assert (library.root / receipt['managed_copy']).read_bytes() == raw
    assert sentinel.read_bytes() == b'outside-library-sentinel-must-survive'
    assert planted.samefile(sentinel)
    assert not list(library.root.glob('.extract-*'))


def test_worker_refuses_to_replace_existing_output_file(tmp_path):
    library = DocumentLibrary(_memory(tmp_path / 'memory.json'))
    raw = FACT.encode('utf-8')
    source = tmp_path / 'input.txt'
    output = tmp_path / 'preexisting-output.json'
    source.write_bytes(raw)
    output.write_bytes(b'existing-output-sentinel')
    with pytest.raises(ImportFailure):
        library._run_extract_worker(source, '.txt', output, len(raw))
    assert output.read_bytes() == b'existing-output-sentinel'


def test_model_status_does_not_confuse_configuration_with_connectivity(tmp_path, monkeypatch):
    from project_guardian.local_memory_chat import LocalOllama, ChatBoundaryError
    monkeypatch.setenv('ELYSIA_LOCAL_MODEL', 'test-local:1')
    panel = _panel(_memory(tmp_path / 'memory.json'), config={'contained_startup': True})
    def fail(self):
        raise ChatBoundaryError('Ollama disconnected')
    monkeypatch.setattr(LocalOllama, 'installed_models', fail)
    status = panel.app.test_client().get('/api/local-model/status').get_json()
    assert status['configured'] and not status['connected'] and not status['available']
    monkeypatch.setattr(LocalOllama, 'installed_models', lambda self: ['test-local:1'])
    assert panel.app.test_client().get('/api/local-model/status').get_json()['available']


def test_first_homepage_send_persists_without_start_new(tmp_path, monkeypatch):
    from project_guardian import local_memory_chat as chat
    monkeypatch.setenv('ELYSIA_LOCAL_MODEL', 'test-local:1')
    monkeypatch.setattr(chat.LocalOllama, 'generate', lambda self, messages, **kw: '{"answer":"Hello from the test model."}')
    config = {'contained_startup': True, 'disposable_root': str(tmp_path)}
    panel = _panel(_memory(tmp_path / 'memory.json'), config=config)
    DocumentLibrary(panel._runtime_memory_core()).import_bytes('hello.txt', b'Hello Elysia. This is synthetic evidence for the greeting test.')
    result = panel.app.test_client().post('/api/chat', json={'message': 'Hello Elysia', 'use_local_model': True})
    assert result.status_code == 200, result.get_json()
    cid = result.get_json()['conversation_id']
    restored = _panel(_memory(tmp_path / 'memory.json'), config=config)
    history = restored.app.test_client().get('/api/conversations/' + cid).get_json()['conversation']['messages']
    assert [m['role'] for m in history] == ['user', 'assistant']
    assert history[0]['content'] == 'Hello Elysia'
    assert history[1]['content'] == 'Hello from the test model.'
    assert history[1]['source_references'][0]['filename'] == 'hello.txt'


def test_failed_history_write_cannot_report_success(tmp_path, monkeypatch):
    from project_guardian import local_memory_chat as chat
    from project_guardian.conversation_continuity import ConversationStore
    monkeypatch.setenv('ELYSIA_LOCAL_MODEL', 'test-local:1')
    monkeypatch.setattr(chat.LocalOllama, 'generate', lambda self, messages, **kw: '{"answer":"A real-shaped reply."}')
    def fail(*args, **kwargs):
        raise OSError('synthetic full disk')
    monkeypatch.setattr(ConversationStore, 'append_message', fail)
    panel = _panel(_memory(tmp_path / 'memory.json'), config={'contained_startup': True, 'disposable_root': str(tmp_path)})
    response = panel.app.test_client().post('/api/chat', json={'message': 'Hello Elysia', 'use_local_model': True})
    assert response.status_code == 503
    assert response.get_json()['success'] is False
    assert response.get_json()['conversation_saved'] is False


def test_real_document_duplicates_do_not_hide_conflicting_source_after_restart(tmp_path):
    """Distinct source bytes can decode to identical chunks (line endings)."""
    from itertools import product
    from project_guardian.local_memory_chat import canonical, EVIDENCE_BYTE_CAP

    def variants(location):
        lines = [
            f"Zircon beacon location {location}.", "Survey notes.",
            "Equipment inventory.", "Archive copy.", "End of record.",
        ]
        for separators in product(("\n", "\r\n"), repeat=4):
            text = "".join(line + separator for line, separator in zip(lines, separators)) + lines[-1]
            yield text.encode("utf-8")

    # Fix the stable source-ID tie break so canonical's first six matches
    # really are all duplicate text, rather than relying on import order.
    digest_key = lambda raw: hashlib.sha256(raw).hexdigest()
    duplicate_bytes = sorted(variants("Cedar Pier"), key=digest_key)[:8]
    conflict_bytes = max(variants("Basalt Point"), key=digest_key)
    assert max(map(digest_key, duplicate_bytes)) < digest_key(conflict_bytes)
    query = "Zircon beacon location"
    path = tmp_path / "memory.json"
    library = DocumentLibrary(_memory(path))
    receipts = [
        library.import_bytes(f"copy-{i}.txt", raw)
        for i, raw in enumerate(duplicate_bytes)
    ]
    conflict = library.import_bytes("different-survey.txt", conflict_bytes)
    assert all(row["status"] == "completed" and not row["duplicate"]
               for row in receipts + [conflict])
    all_ids = {row["source_id"] for row in receipts + [conflict]}
    assert len(all_ids) == 9

    restored = DocumentLibrary(_memory(path))
    assert {row["source_id"] for row in restored.receipts()} == all_ids
    panel = _panel(restored.memory, config={"contained_startup": True})
    before = path.read_bytes()
    ordinary = restored.search(query)
    assert len(ordinary) == 6
    assert len({row["text"] for row in ordinary}) == 1
    assert conflict["source_id"] not in {row["source_id"] for row in ordinary}
    distinct = restored.search(query, context_distinct=True)
    assert len(distinct) == 2
    assert distinct[0]["source_id"] == receipts[0]["source_id"]
    assert distinct[1]["source_id"] == conflict["source_id"]
    adapter = panel._restricted_adapter()
    bundle = build_context_from_adapter(adapter, query, {})
    evidence = bundle["evidence"]
    assert [row["source_id"] for row in evidence] == [
        receipts[0]["source_id"], conflict["source_id"],
    ]
    assert "Cedar Pier" in evidence[0]["highlights"][0]["text"]
    assert "Basalt Point" in evidence[1]["highlights"][0]["text"]
    assert [row["source_sha256"] for row in evidence] == [
        row["content_sha256"] for row in distinct
    ]
    assert [row["chunk_id"] for row in evidence] == [row["chunk_id"] for row in distinct]
    assert all(row["trust"] == "untrusted_document" and row["revision"] == 1
               for row in evidence)
    assert len(canonical(evidence).encode("utf-8")) <= EVIDENCE_BYTE_CAP
    assert build_context_from_adapter(adapter, query, {}) == bundle
    assert path.read_bytes() == before
    for receipt, raw in zip(receipts + [conflict], duplicate_bytes + [conflict_bytes]):
        assert (restored.root / receipt["managed_copy"]).read_bytes() == raw



def test_context_document_candidates_filter_bad_metadata_before_cap(tmp_path):
    library = DocumentLibrary(_memory(tmp_path / "memory.json"))
    text = "Veridia beacon location is Cedar Pier."
    legitimate = library.import_bytes("survey.txt", text.encode("utf-8"))
    # Synthetic completed records with diagnostic/malformed metadata are
    # present in the same store, not just a patched search return.
    for i in range(7):
        source = f"aaa_diagnostic_{i}"
        library._save("document_source", "Synthetic completed receipt", {
            "source_id": source, "status": "completed",
        })
        library._save("document_chunk", text, {
            "source_id": source, "chunk_id": source + ":1",
            "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "filename": "diagnostic.txt", "page": 1,
            "collection": " Diagnostic-Logs " if i % 2 else ["diagnostic_logs"],
        })
    library._save("document_chunk", text, {
        "source_id": ["malformed"], "chunk_id": "aaa_invalid",
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "filename": "malformed.txt", "page": 1,
    })
    matches = library.search("Veridia beacon location", context_distinct=True)
    assert [row["source_id"] for row in matches] == [legitimate["source_id"]]


# EA-11A-B-DOC1: real authenticated import, not a simulated tagged chunk.
_DOC_TEXT = 'Client selected water-based deck finish.'
_DOC_QUERY = 'Which coating did we decide on?'
_DOC_FIELD = 'approved_document_association_v1'
_DOC_LINK = {'concept': '#finish_choice', 'aliases': ['coating'], 'state': 'selected_existing'}


def _doc_approval(raw, links=None):
    return {'preview_sha256': hashlib.sha256(raw).hexdigest(),
            'links': [_DOC_LINK] if links is None else links}


def _tagged_upload(panel, raw, approval, *, headers=None):
    return panel.app.test_client().post(
        '/api/documents', headers=_auth(panel) if headers is None else headers,
        data={'file': (io.BytesIO(raw), 'decision.txt'), _DOC_FIELD: json.dumps(approval)},
    )


def test_approved_document_association_fresh_context_and_model_payload(tmp_path, monkeypatch):
    from project_guardian.local_memory_chat import (
        EVIDENCE_BYTE_CAP, EVIDENCE_ITEM_CAP, LocalOllama, ManualAuthorization,
        _context_tokens, canonical, converse_bundle,
    )
    raw = _DOC_TEXT.encode()
    assert not set(_context_tokens(_DOC_TEXT)) & set(_context_tokens(_DOC_QUERY))
    # Baseline remains RED for a real unapproved import in a separate store.
    (tmp_path / 'baseline').mkdir()
    (tmp_path / 'approved').mkdir()
    baseline = _panel(_memory(tmp_path / 'baseline' / 'memory.json'),
                      config={'contained_startup': True})
    assert baseline.app.test_client().post('/api/documents', headers=_auth(baseline),
        data={'file': (io.BytesIO(raw), 'decision.txt')}).status_code == 200
    assert build_context_from_adapter(baseline._restricted_adapter(), _DOC_QUERY, {})['evidence'] == []
    path = tmp_path / 'approved' / 'memory.json'
    panel = _panel(_memory(path), config={'contained_startup': True})
    preview = panel.app.test_client().post('/api/documents/preview', headers=_auth(panel),
        data={'file': (io.BytesIO(raw), 'decision.txt')}).get_json()['preview']
    assert preview['chunk_count'] == 1
    response = _tagged_upload(panel, raw, {'preview_sha256': preview['sha256'], 'links': [_DOC_LINK]})
    assert response.status_code == 200, response.get_json()
    receipt = response.get_json()['document']
    assert receipt['status'] == 'completed' and not receipt['duplicate']
    association = receipt[_DOC_FIELD]
    assert association['approving_actor'] == 'dashboard-operator'
    assert association['raw_sha256'] == preview['sha256']
    assert association['content_sha256'] == hashlib.sha256(raw).hexdigest()
    assert association['source_id'] == receipt['source_id']
    restored = _panel(_memory(path), config={'contained_startup': True})
    before = path.read_bytes()
    library = DocumentLibrary(restored._runtime_memory_core())
    assert (library.root / receipt['managed_copy']).read_bytes() == raw
    assert library.search(_DOC_QUERY) == []  # ordinary document search remains lexical
    assert library.search('deck finish')[0]['source_id'] == receipt['source_id']
    bundle = build_context_from_adapter(restored._restricted_adapter(), _DOC_QUERY, {})
    assert [row['source_id'] for row in bundle['evidence']] == [receipt['source_id']]
    row = bundle['evidence'][0]
    assert row['chunk_id'] == association['chunk_id']
    assert row['source_sha256'] == association['content_sha256']
    assert row['highlights'][0]['text'] == _DOC_TEXT
    assert row['revision'] == 1 and row['trust'] == 'untrusted_document'
    assert row['matched_tokens'] == []
    assert row['recall_reasons'] == [{
        'type': 'approved_semantic_tag', 'concept': 'finish_choice', 'matched_alias': 'coating',
        'project_id': None, 'method': 'authenticated_operator', 'rule_version': 'document-tags-v1',
    }]
    assert len(bundle['evidence']) <= EVIDENCE_ITEM_CAP
    assert len(canonical(bundle['evidence']).encode()) <= EVIDENCE_BYTE_CAP
    assert build_context_from_adapter(restored._restricted_adapter(), 'Where is the telescope?', {})['evidence'] == []
    captured = []
    def fake_generate(model, messages, *, json_mode=False):
        captured.append(json.loads(messages[-1]['content']))
        return json.dumps({'answer': 'Synthetic source reply.'})
    monkeypatch.setattr(LocalOllama, 'generate', fake_generate)
    result = converse_bundle(bundle, _DOC_QUERY, ManualAuthorization(
        'doc-association-fixture', True, True, frozenset({'local.chat', 'memory.read'})
    ), LocalOllama('fixture-model'), recent=())
    assert captured[0]['context_bundle'] == bundle
    assert result['tools_executed'] == [] and result['memory_written'] is False
    assert path.read_bytes() == before


@pytest.mark.parametrize('invalid', ['candidate', 'wrong-sha', 'project', 'extra', 'null', 'empty', 'duplicate-alias', 'multi-chunk', 'unauthorized'])
def test_document_approval_rejects_before_authoritative_writes(tmp_path, invalid):
    path = tmp_path / 'memory.json'
    panel = _panel(_memory(path), config={'contained_startup': True})
    raw = _DOC_TEXT.encode() if invalid != 'multi-chunk' else b'word ' * 500
    approval = _doc_approval(raw)
    if invalid == 'candidate':
        approval['links'] = [{**_DOC_LINK, 'state': 'candidate_proposed'}]
    elif invalid == 'wrong-sha':
        approval['preview_sha256'] = '0' * 64
    elif invalid == 'project':
        approval['links'] = [{**_DOC_LINK, 'project_id': 'larkspur'}]
    elif invalid == 'extra':
        approval['links'] = [{**_DOC_LINK, 'approving_actor': 'dashboard-operator'}]
    elif invalid == 'null':
        approval = None
    elif invalid == 'empty':
        approval['links'] = []
    elif invalid == 'duplicate-alias':
        approval['links'] = [{**_DOC_LINK, 'aliases': ['coating', 'Coating']}]
    before = path.read_bytes() if path.exists() else None
    response = _tagged_upload(panel, raw, approval, headers={} if invalid == 'unauthorized' else None)
    assert response.status_code == (401 if invalid == 'unauthorized' else 400), response.get_json()
    assert (path.read_bytes() if path.exists() else None) == before
    library = DocumentLibrary(panel._runtime_memory_core())
    assert not library.receipts()
    assert not list(library.root.glob('doc_*'))
    assert build_context_from_adapter(panel._restricted_adapter(), _DOC_QUERY, {})['evidence'] == []


def test_document_approval_cannot_retag_duplicate_or_interrupted_import(tmp_path, monkeypatch):
    path = tmp_path / 'memory.json'
    panel = _panel(_memory(path), config={'contained_startup': True})
    library = DocumentLibrary(panel._runtime_memory_core())
    raw = _DOC_TEXT.encode()
    old = library.import_bytes('original.txt', raw)
    before = path.read_bytes()
    assert _tagged_upload(panel, raw, _doc_approval(raw)).status_code == 400
    assert path.read_bytes() == before
    assert library.import_bytes('renamed.txt', raw)['duplicate']
    assert path.read_bytes() == before
    assert (library.root / old['managed_copy']).read_bytes() == raw
    assert build_context_from_adapter(panel._restricted_adapter(), _DOC_QUERY, {})['evidence'] == []
    other = b'Customer chose an opaque acrylic.'
    original = DocumentLibrary._save
    def fail_completion(self, category, text, meta):
        if category == 'document_source' and meta.get('status') == 'completed':
            raise OSError('synthetic interrupted completion')
        return original(self, category, text, meta)
    monkeypatch.setattr(DocumentLibrary, '_save', fail_completion)
    response = _tagged_upload(panel, other, _doc_approval(other))
    assert response.status_code == 400
    assert build_context_from_adapter(panel._restricted_adapter(), _DOC_QUERY, {})['evidence'] == []
    monkeypatch.setattr(DocumentLibrary, '_save', original)
    before = path.read_bytes()
    assert _tagged_upload(panel, other, _doc_approval(other)).status_code == 400
    assert path.read_bytes() == before
    assert library.import_bytes('decision.txt', other)['status'] == 'completed'
    assert build_context_from_adapter(panel._restricted_adapter(), _DOC_QUERY, {})['evidence'] == []


@pytest.mark.parametrize('field', ['source_id', 'chunk_id', 'content_sha256', 'raw_sha256', 'approving_actor', 'state', 'incomplete', 'text'])
def test_document_approval_persisted_mismatch_is_not_associative_evidence(tmp_path, field):
    path = tmp_path / 'memory.json'
    panel = _panel(_memory(path), config={'contained_startup': True})
    raw = _DOC_TEXT.encode()
    response = _tagged_upload(panel, raw, _doc_approval(raw))
    assert response.status_code == 200, response.get_json()
    records = json.loads(path.read_text(encoding='utf-8'))
    receipt = next(e['metadata'] for e in records if e['category'] == 'document_source'
                   and e['metadata']['status'] == 'completed')
    if field == 'incomplete':
        receipt['status'] = 'processing'
    elif field == 'state':
        receipt[_DOC_FIELD]['links'][0]['state'] = 'candidate_proposed'
    elif field == 'text':
        next(e for e in records if e['category'] == 'document_chunk')['thought'] = 'Different synthetic evidence.'
    else:
        receipt[_DOC_FIELD][field] = 'invalid'
    path.write_text(json.dumps(records), encoding='utf-8')
    restored = _panel(_memory(path), config={'contained_startup': True})
    before = path.read_bytes()
    assert build_context_from_adapter(restored._restricted_adapter(), _DOC_QUERY, {})['evidence'] == []
    assert path.read_bytes() == before


def test_tagged_document_does_not_enter_recognized_explicit_project(tmp_path):
    panel = _panel(_memory(tmp_path / 'memory.json'), config={'contained_startup': True})
    raw = _DOC_TEXT.encode()
    response = _tagged_upload(panel, raw, _doc_approval(raw))
    assert response.status_code == 200, response.get_json()
    adapter = panel._restricted_adapter()
    fact = adapter.handle('POST', '/api/restricted/v1/facts', headers=_auth(panel), body={
        'statement': 'Owner approved acrylic for the surface.',
        'approved_semantic_links_v1': [{**_DOC_LINK, 'project_id': 'larkspur'}],
    })
    assert fact.status == 201, fact.body
    q = 'Which coating for project Larkspur?'
    bundle = build_context_from_adapter(adapter, q, {})
    assert [row['source_id'] for row in bundle['evidence']] == [fact.body['fact']['fact_id']]



@pytest.mark.parametrize('distractors', [5, 6])
def test_document_association_survives_lexical_prefilter(tmp_path, monkeypatch, distractors):
    from project_guardian.local_memory_chat import (
        EVIDENCE_BYTE_CAP, EVIDENCE_ITEM_CAP, LocalOllama, ManualAuthorization,
        canonical, converse_bundle,
    )
    path = tmp_path / 'memory.json'
    panel = _panel(_memory(path), config={'contained_startup': True})
    raw = _DOC_TEXT.encode()
    preview = panel.app.test_client().post('/api/documents/preview', headers=_auth(panel),
        data={'file': (io.BytesIO(raw), 'decision.txt')}).get_json()['preview']
    response = _tagged_upload(panel, raw, {'preview_sha256': preview['sha256'], 'links': [_DOC_LINK]})
    assert response.status_code == 200, response.get_json()
    receipt = response.get_json()['document']
    noise_ids = []
    for i in range(distractors):
        noise = f'Which coating did we decide on? Index card {i}: unrelated reference, no selected finish.'
        response = panel.app.test_client().post('/api/documents', headers=_auth(panel),
            data={'file': (io.BytesIO(noise.encode()), f'noise-{i}.txt')})
        assert response.status_code == 200, response.get_json()
        noise_ids.append(response.get_json()['document']['source_id'])
    restored = _panel(_memory(path), config={'contained_startup': True})
    library = DocumentLibrary(restored._runtime_memory_core())
    before = path.read_bytes()
    ordinary = library.search(_DOC_QUERY)
    assert len(ordinary) == distractors
    assert {row['source_id'] for row in ordinary} == set(noise_ids)
    hits = library.search(_DOC_QUERY, context_distinct=True)
    assert len(hits) == 6
    assert [row['source_id'] for row in hits[:-1]] == sorted(noise_ids)[:5]
    assert hits[-1]['source_id'] == receipt['source_id']
    assert hits[-1]['score'] == 0.85
    assert hits[-1]['recall_reasons'][0]['matched_alias'] == 'coating'
    assert library.search(_DOC_QUERY, limit=0, context_distinct=True) == []
    assert [row['source_id'] for row in library.search(
        _DOC_QUERY, limit=1, context_distinct=True)] == [receipt['source_id']]
    assert library.search(_DOC_QUERY, limit=1)[0]['source_id'] in noise_ids
    assert library.search('Where is the telescope?', context_distinct=True) == []
    bundle = build_context_from_adapter(restored._restricted_adapter(), _DOC_QUERY, {})
    row = next(row for row in bundle['evidence'] if row['source_id'] == receipt['source_id'])
    assert row['chunk_id'] == receipt[_DOC_FIELD]['chunk_id']
    assert row['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert row['matched_tokens'] == [] and row['trust'] == 'untrusted_document'
    assert row['highlights'][0]['text'] == _DOC_TEXT
    assert row['recall_reasons'][0]['type'] == 'approved_semantic_tag'
    assert len(bundle['evidence']) <= EVIDENCE_ITEM_CAP
    assert len(canonical(bundle['evidence']).encode()) <= EVIDENCE_BYTE_CAP
    captured = []
    def fake_generate(model, messages, *, json_mode=False):
        captured.append(json.loads(messages[-1]['content']))
        return json.dumps({'answer': 'Synthetic source reply.'})
    monkeypatch.setattr(LocalOllama, 'generate', fake_generate)
    reply = converse_bundle(bundle, _DOC_QUERY, ManualAuthorization(
        'doc-reservation-fixture', True, True, frozenset({'local.chat', 'memory.read'})
    ), LocalOllama('fixture-model'), recent=())
    assert captured[0]['context_bundle'] == bundle
    assert reply['tools_executed'] == [] and reply['memory_written'] is False
    assert path.read_bytes() == before


def test_document_reservation_rejects_duplicate_chunk_id_before_exact_text_dedup(tmp_path):
    # All three uploads decode to the same text, with distinct raw identities.
    # The invalid association sorts first and must not suppress the valid one.
    path = tmp_path / 'memory.json'
    panel = _panel(_memory(path), config={'contained_startup': True})
    text = 'Which coating did we decide on? Synthetic reference.'
    variants = sorted([text.encode(), (text + '\n').encode(), ('\ufeff' + text).encode()],
                      key=lambda raw: hashlib.sha256(raw).hexdigest())
    invalid_raw, ordinary_raw, valid_raw = variants
    ids = []
    for raw in (invalid_raw, valid_raw):
        response = _tagged_upload(panel, raw, _doc_approval(raw))
        assert response.status_code == 200, response.get_json()
        ids.append(response.get_json()['document']['source_id'])
    library = DocumentLibrary(panel._runtime_memory_core())
    ordinary = library.import_bytes('ordinary.txt', ordinary_raw)
    records = json.loads(path.read_text(encoding='utf-8'))
    duplicate = next(e for e in records if e['category'] == 'document_chunk'
                     and e['metadata']['source_id'] == ids[0])
    # The conflicting ID counts even when the extra chunk is otherwise ineligible.
    conflicting = {**duplicate, 'metadata': {**duplicate['metadata'], 'source_id': ['malformed']}}
    records.append(conflicting)
    path.write_text(json.dumps(records), encoding='utf-8')
    restored = _panel(_memory(path), config={'contained_startup': True})
    library = DocumentLibrary(restored._runtime_memory_core())
    before = path.read_bytes()
    rows = library.search(_DOC_QUERY, limit=1, context_distinct=True)
    assert [row['source_id'] for row in rows] == [ids[1]]
    assert rows[0]['recall_reasons'][0]['matched_alias'] == 'coating'
    assert library.approved_recall_reasons(rows[0], _DOC_QUERY)
    bundle = build_context_from_adapter(restored._restricted_adapter(), _DOC_QUERY, {})
    assert [row['source_id'] for row in bundle['evidence']] == [ids[1]]
    assert bundle['evidence'][0]['recall_reasons']
    assert ordinary['source_id'] != ids[1]
    assert path.read_bytes() == before


def test_document_reservation_overflow_stays_bounded_and_deterministic(tmp_path):
    panel = _panel(_memory(tmp_path / 'memory.json'), config={'contained_startup': True})
    ids = []
    for i in range(7):
        raw = f'Client selected water-based deck finish reference {i}.'.encode()
        response = _tagged_upload(panel, raw, _doc_approval(raw))
        assert response.status_code == 200, response.get_json()
        ids.append(response.get_json()['document']['source_id'])
    library = DocumentLibrary(panel._runtime_memory_core())
    for limit in (1, 2, 6, 7, 9):
        hits = library.search(_DOC_QUERY, limit=limit, context_distinct=True)
        assert [row['source_id'] for row in hits] == sorted(ids)[:limit]
        assert all(row['score'] == 0.85 and row['recall_reasons'] for row in hits)
        assert hits == library.search(_DOC_QUERY, limit=limit, context_distinct=True)
    assert library.search(_DOC_QUERY, context_distinct=False) == []
    bundle = build_context_from_adapter(panel._restricted_adapter(), _DOC_QUERY, {})
    assert 0 < len(bundle['evidence']) <= 4
    assert {row['source_id'] for row in bundle['evidence']} <= set(ids)


def test_document_reservation_deduplicates_identical_lexical_distractors(tmp_path):
    panel = _panel(_memory(tmp_path / 'memory.json'), config={'contained_startup': True})
    response = _tagged_upload(panel, _DOC_TEXT.encode(), _doc_approval(_DOC_TEXT.encode()))
    assert response.status_code == 200, response.get_json()
    target = response.get_json()['document']['source_id']
    library = DocumentLibrary(panel._runtime_memory_core())
    noise = 'Which coating did we decide on? Index card: unrelated reference.'
    for i in range(6):
        library.import_bytes(f'echo-{i}.txt', (noise + '\n' * i).encode())
    assert len(library.search(_DOC_QUERY)) == 6
    hits = library.search(_DOC_QUERY, context_distinct=True)
    assert len(hits) == 2
    assert hits[0]['text'] == noise and hits[1]['source_id'] == target
