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

def test_document_preview_selection_change_fences_stale_queue():
    """Execute the actual embedded browser queue code in a minimal DOM."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.fail("Node.js is required for the embedded browser queue regression")
    source = (_ROOT / "project_guardian" / "ui_control_panel.py").read_text(encoding="utf-8")
    start = source.index("        window._documentPreviewQueue = [];")
    end = source.index("        window.searchImportedDocuments = function()", start)
    browser_code = source[start:end]
    harness = r"""const assert=(v,m)=>{if(!v)throw Error(m)};global.window=global;const e={'document-files':{files:[],disabled:false,addEventListener:(n,f)=>global.changeHandler=f},'document-import-button':{disabled:true},'document-preview-button':{disabled:false},'document-import-status':{textContent:''},'document-preview':{textContent:''}};global.document={getElementById:id=>e[id]||{}};global.FormData=class{append(k,v){if(k==='file')this.file=v}};global.restrictedUploadHeaders=()=>({});window.refreshDocumentLibrary=()=>{};let pending,mode='pending',saved=[];global.fetch=(url,opt)=>{const f=opt.body.file;if(url==='/api/documents/preview'){if(mode==='pending')return new Promise(r=>pending=()=>r({ok:true,status:200,json:async()=>({success:true,preview:{filename:f.name,source_id:'src-'+f.name,chunk_count:1,page_count:1,chunk_settings:{},preview_text:'text'}})}));return Promise.resolve({ok:true,status:200,json:async()=>({success:true,preview:{filename:f.name,source_id:'src-'+f.name,chunk_count:1,page_count:1,chunk_settings:{},preview_text:'text'}})});}if(url==='/api/documents'){saved.push(f.name);return Promise.resolve({ok:true,status:200,json:async()=>({success:true,document:{duplicate:false,source_id:'src-'+f.name,chunk_count:1}})});}throw Error('unexpected')};""" + browser_code + r"""(async()=>{const A={name:'A.txt'},B={name:'B.txt'};assert(typeof changeHandler==='function','BASELINE_RED missing change listener');e['document-files'].files=[A];changeHandler();const p=previewSelectedDocuments();assert(typeof pending==='function','A preview not started');e['document-files'].files=[B];changeHandler();assert(e['document-import-button'].disabled,'Save enabled after selection change');pending();await p;assert(_documentPreviewQueue.length===0,'stale A repopulated queue');mode='immediate';await previewSelectedDocuments();assert(_documentPreviewQueue.length===1&&_documentPreviewQueue[0].file.name==='B.txt','B not pinned');assert(!e['document-import-button'].disabled,'Save not enabled for B');assert(saved.length===0,'chooser cancel mutated storage');await savePreviewedDocuments();assert(JSON.stringify(saved)==='["B.txt"]','wrong saved files '+JSON.stringify(saved));assert(_documentPreviewQueue.length===0,'queue not cleared');console.log('PASS selection fence');})().catch(x=>{console.error(x.message);process.exit(1)});"""
    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS selection fence" in result.stdout

