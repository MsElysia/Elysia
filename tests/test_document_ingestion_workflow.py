"""Real local extraction/persistence; no model or network required."""
import io
import json
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
    assert len(status['events']) == 2
    assert FACT not in json.dumps(status['events'])
    assert 'blank_console_note' in status
    assert client.get('/api/documents', headers=_auth(panel), environ_overrides={'REMOTE_ADDR': '203.0.113.3'}).status_code == 403


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
