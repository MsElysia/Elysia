"""Disposable real HTTP application/transport probe. The Ollama peer is a FIXTURE.

Run in a child process: existing browser tests install process-wide network denial.
This does not establish genuine model inference or native Windows operation.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import elysia_restricted_browser as browser
from elysia_local_memory_chat import LocalOllama
from werkzeug.serving import make_server


def main():
    requests = []
    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path == '/slow':
                self.send_response(200)
                self.send_header('Content-Length', '65536')
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b' '); self.wfile.flush(); time.sleep(.02)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            assert self.path == '/api/tags'
            self.reply({'models':[{'name':'synthetic:local'}]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(self.path)
            if self.path == '/api/show':
                self.reply({'model_info':{'general.architecture':'fixture'}})
                return
            assert self.path == '/api/chat'
            context = json.loads(body['messages'][1]['content'])
            source = context['context_bundle']['evidence'][0]['source_id']
            proposal = {'tool':'calculator.labor', 'arguments':{
                'rate_source_id':source,'painters':2,'days':3,'hours_per_day':8}}
            self.reply({'model':'synthetic:local','done':True,'message':{'content':json.dumps(proposal)}})
        def reply(self, body):
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
    peer = ThreadingHTTPServer(('127.0.0.1',0), Fixture)
    peer_thread = threading.Thread(target=peer.serve_forever, daemon=True); peer_thread.start()
    original = LocalOllama.__init__
    def fixture_endpoint(self, model):
        original(self, model, f'http://127.0.0.1:{peer.server_port}')
    LocalOllama.__init__ = fixture_endpoint
    server = None
    thread = None
    try:
        with tempfile.TemporaryDirectory(prefix='elysia-http-') as d:
            code = Path(d)/'app'; code.mkdir()
            files = runpy.run_path(str(ROOT/'tests/test_canonical_windows_app.py'))['FILES']
            for name in (*files, 'elysia_browser_worker.py'):
                dest=code/name; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/name,dest)
            browser.CODE = code
            # Bind first to obtain a disposable port, then construct the exact app boundary.
            server = make_server('127.0.0.1',0,lambda e,s: [])
            port = server.server_port
            server.app = browser.create_app(password='synthetic-http-password',port=port,store='http',local_model='synthetic:local')
            thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            cookie=''; csrf=''
            def request(path, body=None):
                c=http.client.HTTPConnection('127.0.0.1',port,timeout=8)
                headers={'Origin':f'http://127.0.0.1:{port}','Content-Type':'application/json','Cookie':cookie,'X-Elysia-CSRF':csrf}
                c.request('POST' if body is not None else 'GET',path,
                          json.dumps(body) if body is not None else None,headers)
                r=c.getresponse(); status=r.status; cookies=r.getheader('Set-Cookie'); data=json.loads(r.read()); c.close()
                return status,data,cookies
            assert request('/api/chat',{'query':'labor rate','allow_calculator':True})[0]==401
            status,_,header=request('/session',{'password':'synthetic-http-password'})
            assert status==200; cookie=header.split(';')[0]
            csrf=request('/api/session')[1]['csrf']
            assert request('/api/teach',{'key':'rate','text':'Fictional labor rate is USD 35 per hour.'})[0]==200
            assert request('/api/models')[1]['models']==['synthetic:local']
            status,answer,_=request('/api/chat',{'query':'labor rate for two painters three eight-hour days','allow_calculator':True})
            assert status==200,answer
            assert answer['tools_executed'][0]['result']=='1680'
            assert requests==['/api/show','/api/chat']
            import elysia_local_memory_chat as transport
            transport.REQUEST_DEADLINE_SECONDS = .15
            start = time.monotonic()
            try:
                LocalOllama('synthetic:local')._request('GET', '/slow')
                raise AssertionError('trickling response escaped deadline')
            except transport.ChatBoundaryError:
                assert time.monotonic() - start < 2
            finally:
                transport.REQUEST_DEADLINE_SECONDS = 35
            peer.shutdown(); peer.server_close(); peer_thread.join(3)
            status,failure,_=request('/api/chat',{'query':'labor rate','allow_calculator':True})
            assert status==503 and 'unavailable' in failure['error'], failure
            assert request('/api/recall',{'query':'labor rate'})[0]==200
            print(json.dumps({'platform':sys.platform,'model_peer':'synthetic HTTP fixture, NOT actual Ollama inference',
                'authorized_application_result':answer,'stopped_peer_result':failure,
                'unauthorized_http_status':401,'recall_after_peer_stop':200}))
    finally:
        if server is not None:
            if thread is not None:
                server.shutdown()
                thread.join(3)
            server.server_close()
        peer.shutdown(); peer.server_close()
        LocalOllama.__init__=original


if __name__ == '__main__': main()
