#!/usr/bin/env python3
"""Exercise the packaged HTTPS probe using the router's curl and loopback TLS/SOCKS."""
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import select
import socket
from socketserver import BaseRequestHandler, ThreadingTCPServer
import ssl
import struct
import subprocess
import tempfile
from threading import Thread
import time
import warnings

assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
assert all(not subprocess.check_output(['ip', fam, 'route', 'show', 'default']).strip() for fam in ('-4','-6'))
STATE = Path('/var/run/proxy-guard')
BODY = 'ネットは広大だわ'.encode()
WORKER = r'''
package.path='/usr/lib/?.lua;'..package.path
local ext=require 'proxy-guard.extensions'
local worker=require 'proxy-guard.worker'
local core=require 'proxy-guard.core'
local json=require 'luci.jsonc'
local mode,port,timeout=arg[1],tonumber(arg[2]),tonumber(arg[3])
local config=core.config({socks_port=tostring(port),public_hb_timeout=tostring(timeout)})
local result
if mode=='ordinary' then
    result=worker.https_probe(config,{url='https://web-one.test/'},arg[4])
else
    result=ext.public_probe(config,{full=mode=='diagnostic'})
end
print(json.stringify(result))
'''


class Service(ThreadingHTTPServer):
    daemon_threads = True

    def get_request(self):
        raw, addr = self.socket.accept()
        raw.settimeout(5)
        self.attempts += 1
        try:
            return self.context.wrap_socket(raw, server_side=True), addr
        except OSError:
            raw.close()
            raise


class Request(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        tls = self.connection.version()
        nonce = self.headers.get('X-PGHB-Nonce')
        self.server.requests.append((tls, self.path, nonce))
        if self.server.delay:
            time.sleep(self.server.delay)
        payload = self.server.payload
        try:
            self.send_response(self.server.code)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('X-PGHB-IP', '203.0.113.7')
            self.send_header('X-PGHB-TLS', tls)
            if nonce:
                self.send_header('X-PGHB-Nonce', nonce)
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            pass


class SOCKS(ThreadingTCPServer):
    daemon_threads = True


class Relay(BaseRequestHandler):
    def handle(self):
        client = self.request
        client.settimeout(5)

        def exact(count):
            data = bytearray()
            while len(data) < count:
                chunk = client.recv(count - len(data))
                if not chunk:
                    raise EOFError
                data.extend(chunk)
            return bytes(data)

        try:
            version, count = exact(2)
            assert version == 5 and b'\0' in exact(count)
            client.sendall(b'\5\0')
            assert exact(4) == b'\5\1\0\3'
            host = exact(exact(1)[0]).decode()
            assert host in {'hb.pghb.app', 'web-one.test'} and struct.unpack('!H', exact(2))[0] == 443
            with socket.create_connection(('127.0.0.1', self.server.target), timeout=5) as server:
                client.sendall(b'\5\0\0\1\x7f\0\0\1\0\0')
                while True:
                    ready, _, _ = select.select((client, server), (), (), 5)
                    if not ready:
                        return
                    for side in ready:
                        data = side.recv(16384)
                        if not data:
                            return
                        (server if side is client else client).sendall(data)
        except (OSError, EOFError):
            pass


def start(stack, server):
    stack.callback(server.server_close)
    Thread(target=server.serve_forever, kwargs={'poll_interval':0.05}, daemon=True).start()
    stack.callback(server.shutdown)
    return server


def certificate(tmp):
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(tmp/'key'),
                    '-out',str(tmp/'crt'),'-days','1','-subj','/CN=hb.pghb.app','-addext',
                    'subjectAltName=DNS:hb.pghb.app,DNS:web-one.test'], check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def case(tmp, name, version, mode='official', trusted=True, code=200, payload=BODY, delay=0):
    with ExitStack() as stack:
        service = Service(('127.0.0.1',0), Request)
        service.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            if version==ssl.TLSVersion.TLSv1_1:
                service.context.set_ciphers('DEFAULT:@SECLEVEL=0')
            service.context.minimum_version = service.context.maximum_version = version
        service.context.load_cert_chain(tmp/'crt',tmp/'key')
        service.attempts, service.requests = 0, []
        service.delay,service.code,service.payload = delay,code,payload
        start(stack,service)
        socks = SOCKS(('127.0.0.1',0),Relay)
        socks.target = service.server_address[1]
        start(stack,socks)
        env = dict(os.environ)
        for key in ('CURL_CA_BUNDLE','SSL_CERT_FILE','SSL_CERT_DIR'):
            env.pop(key,None)
        if trusted:
            env['CURL_CA_BUNDLE'] = str(tmp/'crt')
        p = subprocess.run(['lua',str(tmp/'probe.lua'),mode,str(socks.server_address[1]),'2',str(tmp/'body')],
                           check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=8,env=env)
        result = json.loads(p.stdout)
        if name=='official13':
            assert result['ok'] and result['tls_version']=='1.3' and service.attempts==1
        elif name in {'official12','diagnostic12'}:
            assert result['ok'] and result['tls_version']=='1.2' and service.attempts==2
            assert service.requests[0][0]=='TLSv1.2'
            if name=='diagnostic12':
                _, path, nonce=service.requests[0]
                assert path=='/f' and nonce and result['nonce_verified']
        elif name=='ordinary12':
            assert result['code']==200 and result['rc']==0 and service.attempts==1
        elif name=='ordinary13':
            assert result['code']==200 and result['rc']==0 and service.attempts==1
            assert service.requests[0][0]=='TLSv1.3'
        elif name in {'official11','ordinary11'}:
            assert result['code']==0 and result['rc']!=0 and not service.requests
            assert service.attempts <= (2 if name=='official11' else 1)
        elif name=='untrusted':
            assert not result['ok'] and result['rc']==60 and service.attempts==1
        elif name=='forbidden':
            assert not result['ok'] and result['code']==403 and service.attempts==1
        elif name=='wrong_body':
            assert not result['ok'] and result['reason']=='body_mismatch' and service.attempts==1
        elif name=='timeout':
            assert not result['ok'] and result['rc']==28 and service.attempts==1
        elif name=='fallback_budget':
            assert not result['ok'] and result['rc']==28 and service.attempts==2 and result['milliseconds']<2700
        else:
            raise AssertionError(name)
        print(f'PASS {name}: HTTP {result["code"]}, curl {result["rc"]}, {service.attempts} TLS connection(s)',flush=True)
        return result


with tempfile.TemporaryDirectory(prefix='pg-native-tls-') as path:
    tmp=Path(path)
    certificate(tmp)
    (tmp/'probe.lua').write_text(WORKER)
    v13,v12,v11 = ssl.TLSVersion.TLSv1_3,ssl.TLSVersion.TLSv1_2,ssl.TLSVersion.TLSv1_1
    case(tmp,'official13',v13)
    fallback=case(tmp,'official12',v12)
    case(tmp,'diagnostic12',v12,'diagnostic')
    case(tmp,'ordinary12',v12,'ordinary')
    case(tmp,'ordinary13',v13,'ordinary')
    case(tmp,'official11',v11)
    case(tmp,'ordinary11',v11,'ordinary')
    case(tmp,'untrusted',v13,trusted=False)
    case(tmp,'forbidden',v13,code=403)
    case(tmp,'wrong_body',v13,payload=BODY+b'\n')
    case(tmp,'timeout',v13,delay=3)
    case(tmp,'fallback_budget',v12,delay=3)
    observation = STATE/'public-observation.json'
    backup = observation.read_bytes() if observation.exists() else None
    try:
        body = r'''
package.path='/usr/lib/?.lua;'..package.path
local json=require 'luci.jsonc'
local ext=require 'proxy-guard.extensions'
local response=json.parse(io.read('*a'))
assert(ext.record_public({},'test-native-tls',response))
assert(not ext.record_public({},'test-native-tls',response))
assert(not ext.record_public({},'test-native-tls',{ok=false}))
assert(not ext.record_public({},'test-native-tls',response))
assert(not ext.record_public({},'test-native-tls',{tls_version='1.3'}))
assert(ext.record_public({},'test-native-tls',response))
assert(ext.tls_fallback_message:find('TLS 1.3',1,true))
'''
        subprocess.run(['lua','-e',body],input=json.dumps(fallback),text=True,check=True,timeout=10)
    finally:
        if backup is None:
            observation.unlink(missing_ok=True)
        else:
            observation.write_bytes(backup)
    print('PASS fallback logs once per transition and can warn again after TLS 1.3 returns',flush=True)
