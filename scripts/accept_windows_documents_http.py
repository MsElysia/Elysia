"""Exercise a running disposable candidate over HTTP; never use an operational root.

Requires requests and reportlab in the acceptance environment. Tokens remain in
process and are never included in evidence output. Does not start any provider.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re


def fixtures(root):
    from reportlab.pdfgen.canvas import Canvas
    root.mkdir(parents=True, exist_ok=True)
    if not (root / 'expedition.txt').exists():
        (root / 'expedition.txt').write_text('The Veridia expedition stores its cobalt compass in the Lumenport observatory.', encoding='utf-8')
    if (root / 'expedition.pdf').exists():
        return
    canvas = Canvas(str(root / 'expedition.pdf'))
    canvas.drawString(40, 750, 'The Veridia expedition departure date is 19 November 2026.')
    canvas.drawString(40, 720, 'Its scheduled departure port is Glasshaven.')
    canvas.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5080')
    parser.add_argument('--evidence-root', required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    parser.add_argument('--verify-restart', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'http://127\.0\.0\.1:\d{1,5}', args.url):
        raise SystemExit('literal loopback URL required')
    root = Path(args.evidence_root).resolve()
    fixtures(root / 'fixtures')
    if args.fixtures_only:
        print('Synthetic fixtures ready')
        return
    import requests
    session = requests.Session()
    session.trust_env = False
    page = session.get(args.url, timeout=10)
    page.raise_for_status()
    token = re.search(r'var RESTRICTED_TOKEN = ("[^"\n]+");', page.text)
    assert token, 'Dashboard operator token missing'
    headers = {'X-Elysia-Identity': 'dashboard-operator', 'X-Elysia-Token': json.loads(token[1])}
    def api(method, path, **kwargs):
        response = session.request(method, args.url + path, headers=headers, timeout=100, **kwargs)
        if not response.ok:
            try:
                detail = response.json().get('error', 'Request failed')
            except ValueError:
                detail = 'Non-JSON failure response'
            raise RuntimeError(f'{path}: HTTP {response.status_code}: {detail}')
        data = response.json()
        assert data.get('success', True), data.get('error')
        return data
    record = root / 'http-acceptance.json'
    if args.verify_restart:
        prior = json.loads(record.read_text())
        rows = api('GET', '/api/documents')['documents']
        assert all(any(r['source_id'] == source and r['status'] == 'completed' for r in rows) for source in prior['source_ids'])
        history = api('GET', '/api/conversations/' + prior['conversation_id'])['conversation']['messages']
        assert len(history) >= 2 and history[-1]['role'] == 'assistant'
        assert history[-1].get('source_references'), 'Grounding provenance must survive restart'
        for query in ['Veridia compass', 'Veridia departure']:
            assert api('POST', '/api/documents/search', json={'query': query})['matches']
        prior['restart_persistence'] = True
        record.write_text(json.dumps(prior, indent=2))
        print('HTTP restart: documents, chunks and both conversation roles recovered')
        return
    sources = []
    for name in ['expedition.txt', 'expedition.pdf']:
        path = root / 'fixtures' / name
        raw = path.read_bytes()
        preview = api('POST', '/api/documents/preview', files={'file': (name, raw)})['preview']
        assert preview['chunk_count'] > 0
        receipt = api('POST', '/api/documents', files={'file': (name, raw)})['document']
        assert receipt['status'] == 'completed'
        assert receipt['sha256'] == hashlib.sha256(raw).hexdigest()
        sources.append(receipt['source_id'])
        assert api('POST', '/api/documents', files={'file': (name, raw)})['document']['duplicate']
    matches = api('POST', '/api/documents/search', json={'query': 'Veridia departure'})['matches']
    assert any(m['source_id'] == sources[1] for m in matches)
    answer = api('POST', '/api/chat', json={'message': 'What date does the Veridia expedition leave, according to the imported document? Cite the source.', 'use_local_model': True})
    assert answer['reply'] and answer['provider'] == 'local-ollama'
    assert '19' in answer['reply'] and '2026' in answer['reply'] and 'november' in answer['reply'].lower()
    assert any(e['source_id'] == sources[1] for e in answer['evidence_supplied'])
    # The UI renders host-supplied source/chunk references separately from model
    # prose, so source identity never depends on a model copying a hash exactly.
    assert any(e.get('filename') == 'expedition.pdf' and e.get('page') == 1 and e.get('chunk_id') for e in answer['evidence_supplied'])
    assert not answer['tools_executed']
    assert api('GET', '/api/conversations/' + answer['conversation_id'])['conversation']['messages'][-1]['role'] == 'assistant'
    failed = session.post(args.url + '/api/documents', headers=headers, files={'file': ('broken.pdf', b'%PDF-invalid')}, timeout=40)
    assert failed.status_code == 400 and not failed.json()['success']
    denied = session.post(args.url + '/api/documents', files={'file': ('guide.txt', b'Unauthorized test')}, timeout=10)
    assert denied.status_code == 401
    status = api('GET', '/api/documents')
    result = {'source_ids': sources, 'conversation_id': answer['conversation_id'],
              'formats': ['txt', 'pdf'], 'grounded_real_model_reply': answer['reply'],
              'duplicate_verified': True, 'malformed_rejected': True, 'unauthenticated_rejected': True,
              'indexed_chunks': status['indexed_chunks'], 'restart_persistence': False}
    record.write_text(json.dumps(result, indent=2))
    print('HTTP acceptance: real TXT/PDF extraction, durable chunks, dedupe, cited Ollama reply and error paths passed')


if __name__ == '__main__':
    main()
