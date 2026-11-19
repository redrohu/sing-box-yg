"""Exercise actual sidecar generators; installers/services run only with sandbox stubs."""
import hashlib
import json
import os
from pathlib import Path
import http.server
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from config_harness import ROOT, RECORDS, bashpath, function, run, save_records, shell


class XHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='xhttp-test-'))) / 'xhttp'
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.binary = os.environ.get('XRAY_TEST_BIN')

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / 'commands.json')

    def helpers(self, directory):
        src = self.source.replace('/etc/s-box', bashpath(directory))
        return ''.join(function(src, n) for n in [
            'node_suffix_valid', 'node_suffix_load', 'xhttp_server_config',
            'xhttp_client_config', 'xhttp_export'])

    def generate(self, name, server='192.0.2.1'):
        d = self.output / name
        d.mkdir(exist_ok=True)
        shell(self.helpers(d) + '''
mkdir -p xhttp
printf '%s\\n' 'SERVER' > server_ipcl.log
printf '%s\\n' '5XaAecMR7oqsy_0v-N7ZqYeepf-gPOJkncIsxN-NIgs' > xhttp/public.key
hostname=test-vps
xhttp_server_config xhttp 18443 www.microsoft.com 11111111-2222-3333-4444-555555555555 eC9YOSPvhGUHAU1KLrr0X3GBiiYubH1zubnb_yxyylQ aabbccdd /test-path
xhttp_export
'''.replace('SERVER', server), d)
        return d

    def test_server_and_client_real_core(self):
        if not self.binary:
            self.skipTest('Set XRAY_TEST_BIN to validate with a real Xray core')
        d = self.generate('core')
        for file in ['config.json', 'client.json']:
            p = run([self.binary, 'run', '-test', '-config', d / 'xhttp' / file])
            self.assertEqual(p.returncode, 0, RECORDS[-1])

    def test_share_matches_configs_ipv4_ipv6(self):
        for server in ['192.0.2.1', '2001:db8::1', '[2001:db8::2]']:
            d = self.generate('share-' + str(len(server)), server)
            link = urlsplit((d / 'xhttp.txt').read_text().strip())
            query = parse_qs(link.query)
            cfg = json.loads((d / 'xhttp/config.json').read_text())['inbounds'][0]
            client = json.loads((d / 'xhttp/client.json').read_text())
            self.assertEqual(link.hostname, server.strip('[]'))
            self.assertEqual(link.port, cfg['port'])
            self.assertEqual(link.username, cfg['settings']['clients'][0]['id'])
            self.assertEqual(query['path'], [cfg['streamSettings']['xhttpSettings']['path']])
            self.assertEqual(query['sid'], cfg['streamSettings']['realitySettings']['shortIds'])
            self.assertEqual(query['type'], ['xhttp'])
            self.assertNotIn('flow', query)
            self.assertNotIn('flow', cfg['settings']['clients'][0])
            self.assertEqual(client['outbounds'][0]['streamSettings']['realitySettings']['password'], query['pbk'][0])

    def test_transport_loopback(self):
        """Real TLS1.3/H2 target + Xray server/client + SOCKS + HTTP payload, no Internet."""
        openssl = shutil.which('openssl')
        if not openssl and os.name == 'nt':
            openssl = r'C:\Program Files\Git\usr\bin\openssl.exe'
        curl = shutil.which('curl.exe' if os.name == 'nt' else 'curl')
        if not self.binary or not openssl or not curl:
            self.skipTest('Requires Xray, openssl and curl')
        d = self.generate('transport', '127.0.0.1')

        def port():
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0))
                return s.getsockname()[1]

        target_port, server_port, socks_port = port(), port(), port()
        (d / 'openssl.cnf').write_text('[req]\ndistinguished_name=dn\n[dn]\n')
        result = run([openssl, 'req', '-config', d / 'openssl.cnf', '-x509', '-newkey', 'rsa:2048', '-nodes',
                      '-keyout', d / 'key.pem', '-out', d / 'cert.pem', '-days', '1',
                      '-subj', '/CN=www.microsoft.com'])
        self.assertEqual(result.returncode, 0, RECORDS[-1])
        server = json.loads((d / 'xhttp/config.json').read_text())
        server['inbounds'][0]['listen'] = '127.0.0.1'
        server['inbounds'][0]['port'] = server_port
        server['inbounds'][0]['streamSettings']['realitySettings']['target'] = f'127.0.0.1:{target_port}'
        # Xray blocks private destinations by default. Permit only loopback in this test,
        # leaving the deployed generator's default private-address protection intact.
        server['outbounds'][0]['settings'] = {'finalRules': [{'action': 'allow', 'ip': ['127.0.0.1']}]}
        client = json.loads((d / 'xhttp/client.json').read_text())
        client['inbounds'][0]['port'] = socks_port
        client['outbounds'][0]['settings']['vnext'][0]['port'] = server_port
        for name, config in [('server', server), ('client', client)]:
            (d / f'{name}.json').write_text(json.dumps(config))
        payload = b'xhttp-reality-functional-check\n' * 8192

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        commands = [
            [openssl, 's_server', '-accept', str(target_port), '-cert', str(d / 'cert.pem'),
             '-key', str(d / 'key.pem'), '-tls1_3', '-alpn', 'h2', '-www'],
            [self.binary, 'run', '-config', str(d / 'server.json')],
            [self.binary, 'run', '-config', str(d / 'client.json')],
        ]
        processes, logs = [], []
        try:
            for i, command in enumerate(commands):
                log = open(d / f'process-{i}.log', 'wb')
                logs.append(log)
                processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            time.sleep(2)
            for p in processes:
                self.assertIsNone(p.poll())
            download = run([curl, '--silent', '--show-error', '--fail', '--max-time', '15',
                '--noproxy', '', '--proxy', f'socks5h://127.0.0.1:{socks_port}',
                f'http://127.0.0.1:{httpd.server_port}/payload', '-o', d / 'payload.bin'])
            self.assertEqual(download.returncode, 0, RECORDS[-1])
            self.assertEqual((d / 'payload.bin').read_bytes(), payload)
            (d / 'payload-sha256.txt').write_text(hashlib.sha256(payload).hexdigest())
        finally:
            httpd.shutdown()
            httpd.server_close()
            for p, command, log in zip(processes, commands, logs):
                p.terminate()
                p.wait(timeout=10)
                log.close()
                RECORDS.append(dict(command=command, exit_code=p.returncode,
                    stdout=(d / f'process-{processes.index(p)}.log').read_text(errors='replace'),
                    stderr='', note='Long-running test process terminated after loopback transfer'))

    def test_names_and_refresh_do_not_change_server(self):
        d = self.generate('names')
        old = hashlib.sha256((d / 'xhttp/config.json').read_bytes()).hexdigest()
        shell(self.helpers(d) + '''
printf '%s\\n' '棣欐腐 #1 | VPS' > node_prefix.conf
printf '%s\\n' '娴嬭瘯 鑺傜偣' > node_suffix.conf
printf '%s\\n' 192.0.2.2 > server_ipcl.log
xhttp_export
''', d)
        link = urlsplit((d / 'xhttp.txt').read_text().strip())
        self.assertEqual(unquote(link.fragment), '棣欐腐 #1 | VPS vless-xhttp-reality 娴嬭瘯 鑺傜偣')
        self.assertEqual(link.hostname, '192.0.2.2')
        self.assertEqual(hashlib.sha256((d / 'xhttp/config.json').read_bytes()).hexdigest(), old)

    def test_absent_is_noop(self):
        d = self.output / 'absent'
        shell(self.helpers(d) + 'xhttp_export\n', d)
        self.assertFalse((d / 'xhttp.txt').exists())

    def test_menu_and_aggregate_integration(self):
        self.assertIn('xhttp_menu', function(self.source, 'changeserv'))
        share = function(self.source, 'sbshare')
        self.assertIn('xhttp_export || return 1', share)
        self.assertIn('cat /etc/s-box/xhttp.txt >> /etc/s-box/jhdy.txt', share)
        self.assertIn('xhttp_remove', function(self.source, 'unins'))
        self.assertNotIn('\"type\": \"xhttp\"', function(self.source, 'sb_client'))

    def test_install_download_failure_does_not_modify_existing_config(self):
        d = self.output / 'download-failure'
        d.mkdir(exist_ok=True)
        (d / 'sb.json').write_text('{"original":true}')
        original = (d / 'sb.json').read_bytes()
        src = self.source.replace('/etc/s-box', bashpath(d))
        script = self.helpers(d) + function(src, 'xhttp_install') + '''
red() { echo "$*"; }; yellow() { :; }
readp() { if [[ $2 == port ]]; then port=18443; else sni=www.microsoft.com; fi; }
ss() { :; }; curl() { echo 'simulated download failure' >&2; return 22; }
unzip() { echo 'must not extract' >&2; exit 98; }
sha256sum() { :; }
uname() { echo x86_64; }
if xhttp_install; then echo 'unexpected success'; exit 1; fi
'''
        shell(script, d)
        self.assertEqual((d / 'sb.json').read_bytes(), original)
        self.assertFalse((d / 'xhttp').exists())
        self.assertEqual(list(d.glob('.xhttp-install.*')), [])

    def test_install_and_service_failure_rollback_with_stubs(self):
        if not self.binary:
            self.skipTest('Requires real Xray key generator and config checker')
        for fail in [False, True]:
            d = self.output / ('service-failure' if fail else 'install-success')
            d.mkdir(exist_ok=True)
            (d / 'systemd').mkdir(exist_ok=True)
            (d / 'sb.json').write_text('{"original":true}')
            (d / 'server_ipcl.log').write_text('192.0.2.1')
            (d / 'payload').write_bytes(b'fake archive for installer control-flow test')
            digest = hashlib.sha256((d / 'payload').read_bytes()).hexdigest()
            (d / 'digest').write_text('SHA2-256= ' + digest + '\n')
            (d / 'wrapper').write_text('#!/bin/bash\nexec "' + bashpath(self.binary) + '" "$@"\n')
            src = self.source.replace('/etc/s-box', bashpath(d)).replace('/etc/systemd/system', bashpath(d / 'systemd')).replace('/etc/init.d', bashpath(d / 'init.d'))
            helpers = self.helpers(d) + ''.join(function(src, name) for name in ['xhttp_service', 'xhttp_remove', 'xhttp_install'])
            script = helpers + '''
hostname=test-vps
red() { echo "$*"; }; green() { echo "$*"; }; yellow() { :; }
readp() { if [[ $2 == port ]]; then port=18443; else sni=www.apple.com; fi; }
uname() { echo x86_64; }
ss() { if [[ -d xhttp ]]; then echo LISTEN; fi; return 0; }
curl() { if [[ $* == *zip.dgst* ]]; then cp digest "${@: -1}"; else cp payload "${@: -1}"; fi; }
unzip() { cp wrapper "$5/xray"; }
sleep() { :; }
systemctl() { echo "$*" >> service-commands; if [[ FAIL == yes && $1 == start ]]; then return 1; fi; }
sbshare() { echo refreshed > refreshed; }
if xhttp_install; then
test FAIL == no
test -f xhttp/client.json
test -f systemd/sbox-xhttp.service
test -f refreshed
xhttp_remove
else
test FAIL == yes
fi
test ! -d xhttp
test ! -e xhttp.txt
test ! -e systemd/sbox-xhttp.service
'''.replace('FAIL', 'yes' if fail else 'no')
            shell(script, d)
            self.assertEqual((d / 'sb.json').read_text(), '{"original":true}')
            self.assertEqual(list(d.glob('.xhttp-install.*')), [])


if __name__ == '__main__':
    unittest.main()
