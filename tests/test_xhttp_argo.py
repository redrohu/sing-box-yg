"""Fixed tunnel generators and real HTTP/1.1 packet-up + Encryption/Vision transfer."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit

import yaml
from config_harness import ROOT, RECORDS, bashpath, function, generate_vps, run, save_records, shell


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class XHTTPArgo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='argo-test-'))) / 'xhttp-argo'
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.xray = os.environ.get('XRAY_TEST_BIN')
        cls.mihomo = os.environ.get('MIHOMO_TEST_BIN')

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / 'commands.json')

    def generate(self, name):
        d = self.output / name
        origin = d / 'xhttp-argo'
        origin.mkdir(parents=True, exist_ok=True)
        src = self.source.replace('/etc/s-box', bashpath(d))
        helpers = ''.join(function(src, n) for n in ['node_suffix_valid', 'node_suffix_load',
            'xhttp_argo_server_config', 'xhttp_argo_mihomo_load', 'xhttp_argo_export'])
        shell(helpers + '''
hostname=test-vps
printf '%s\\n' xhttp.example.org > xhttp-argo/domain
printf '%s\\n' mlkem768x25519plus.native.0rtt.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA > xhttp-argo/encryption.key
xhttp_argo_server_config xhttp-argo 18080 22222222-3333-4444-5555-666666666666 /xhttp/test/ mlkem768x25519plus.native.300s.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
xhttp_argo_export
''', d)
        return d

    def test_exports_and_all_branches(self):
        for argo in ['none', 'fixed', 'temporary', 'both']:
            d = self.generate(argo)
            generate_vps(self.source, d, argo=argo, prefix='RN | 美国', suffix='测试')
            cfg = yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))
            node = next(x for x in cfg['proxies'] if x.get('network') == 'xhttp')
            self.assertEqual(node['name'], 'RN | 美国 vless-xhttp-argo 测试')
            self.assertEqual(node['server'], 'xhttp.example.org')
            self.assertEqual(node['port'], 443)
            self.assertTrue(node['tls'])
            self.assertFalse(node['skip-cert-verify'])
            self.assertEqual(node['flow'], 'xtls-rprx-vision')
            self.assertEqual(node['xhttp-opts']['mode'], 'packet-up')
            self.assertNotIn('reality-opts', node)
            for group in cfg['proxy-groups']:
                self.assertEqual(group['proxies'].count(node['name']), 1)
            self.assertFalse(json.loads((d / 'xhttp-argo/config.json').read_text())['inbounds'][0]['streamSettings']['xhttpSettings']['noSSEHeader'])
            query = parse_qs(urlsplit((d / 'xhttp-argo.txt').read_text()).query)
            self.assertEqual(query['mode'], ['packet-up'])
            self.assertEqual(query['security'], ['tls'])
            self.assertEqual(query['flow'], ['xtls-rprx-vision'])
            self.assertNotIn('300s', json.dumps(node))
            self.assertNotIn('xhttp', (d / 'sbox.json').read_text())
            if self.xray:
                for name in ['config.json', 'client.json']:
                    p = run([self.xray, 'run', '-test', '-config', d / 'xhttp-argo' / name])
                    self.assertEqual(p.returncode, 0, RECORDS[-1])

    def test_real_packet_up_encryption_vision(self):
        curl = shutil.which('curl.exe' if os.name == 'nt' else 'curl')
        if not self.xray or not self.mihomo or not curl:
            self.skipTest('requires XRAY_TEST_BIN, MIHOMO_TEST_BIN and curl')
        d = self.generate('transfer')
        origin = d / 'xhttp-argo'
        shutil.copy2(self.xray, origin / ('xray.exe' if os.name == 'nt' else 'xray'))
        src = self.source.replace('/etc/s-box', bashpath(d))
        helpers = ''.join(function(src, n) for n in ['xhttp_encryption_pair', 'xhttp_argo_server_config',
            'node_suffix_valid', 'node_suffix_load', 'xhttp_argo_mihomo_load', 'xhttp_argo_export'])
        binary = bashpath(origin / ('xray.exe' if os.name == 'nt' else 'xray'))
        # The production helper uses the Linux executable name; a shell wrapper isolates that difference.
        if os.name == 'nt':
            (origin / 'xray').write_text('#!/bin/bash\nexec "' + binary + '" "$@"\n', encoding='utf8')
        origin_port, socks_port = port(), port()
        shell(helpers + f'''
hostname=test-vps
xhttp_encryption_pair xhttp-argo
xhttp_argo_server_config xhttp-argo {origin_port} 22222222-3333-4444-5555-666666666666 /xhttp/test/ "$(cat xhttp-argo/decryption.key)"
xhttp_argo_export
''', d)
        # Xray's default freedom finalrule blocks private destinations. Test-only opt-out.
        server_cfg = json.loads((origin / 'config.json').read_text())
        server_cfg['outbounds'][0]['settings'] = {'finalRules': [{'action': 'allow', 'ip': ['127.0.0.1']}]}
        (origin / 'config.json').write_text(json.dumps(server_cfg))
        payload = os.urandom(131072)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_):
                pass

        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        node = json.loads((origin / 'mihomo.json').read_text())
        # Emulate cloudflared -> origin HTTP/1.1, not the public TLS edge in this local test.
        node.update(server='127.0.0.1', port=origin_port, tls=False)
        config = {'mixed-port': socks_port, 'mode': 'rule', 'log-level': 'debug',
                  'proxies': [node], 'rules': ['MATCH,' + node['name']]}
        (d / 'mihomo.json').write_text(json.dumps(config), encoding='utf8')
        processes = []
        try:
            for command, logfile in [([self.xray, 'run', '-config', str(origin / 'config.json')], 'xray.log'),
                ([self.mihomo, '-d', str(d), '-f', str(d / 'mihomo.json')], 'mihomo.log')]:
                with (d / logfile).open('wb') as f:
                    processes.append(subprocess.Popen(command, stdout=f, stderr=subprocess.STDOUT))
            time.sleep(2)
            p = run([curl, '--fail', '--max-time', '20', '--noproxy', '', '--socks5-hostname',
                     f'127.0.0.1:{socks_port}', f'http://127.0.0.1:{httpd.server_port}/', '-o', d / 'received.bin'])
            self.assertEqual(p.returncode, 0, RECORDS[-1])
            self.assertEqual(hashlib.sha256(payload).digest(), hashlib.sha256((d / 'received.bin').read_bytes()).digest())
        finally:
            for process in processes:
                process.terminate()
                process.wait(timeout=10)
            httpd.shutdown()
            httpd.server_close()

    def test_restore_copy_and_remove_keeps_existing_services(self):
        d = self.generate('restore-remove')
        # Restore in an extra copy, leaving the generated final output available.
        copy = self.output / 'restore-extra-copy'
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(d, copy)
        originals = {str(p.relative_to(copy)): p.read_bytes() for p in (copy / 'xhttp-argo').iterdir()}
        backup = copy / 'backup'
        shutil.copytree(copy / 'xhttp-argo', backup)
        (copy / 'xhttp-argo/config.json').write_text('{}')
        shutil.rmtree(copy / 'xhttp-argo')
        shutil.copytree(backup, copy / 'xhttp-argo')
        for name, data in originals.items():
            self.assertEqual((copy / name).read_bytes(), data)
        units = copy / 'units'
        units.mkdir(exist_ok=True)
        for name in ['sbox-xhttp-argo', 'sbox-xhttp-argo-tunnel', 'sbox-xhttp', 'sing-box', 'argo']:
            (units / (name + '.service')).write_text(name)
        (copy / 'xhttp').mkdir(exist_ok=True)
        (copy / 'xhttp/config.json').write_text('existing direct node')
        (copy / 'sb.json').write_text('original five protocols')
        src = self.source.replace('/etc/s-box', bashpath(copy)).replace('/etc/systemd/system', bashpath(units))
        shell(function(src, 'xhttp_argo_remove') + '''
command() { if [[ $1 == -v && $2 == apk ]]; then return 1; else builtin command "$@"; fi; }
systemctl() { printf '%s\\n' "$*" >> services.log; }
xhttp_argo_remove
''', copy)
        self.assertFalse((copy / 'xhttp-argo').exists())
        self.assertFalse((copy / 'xhttp-argo.txt').exists())
        self.assertEqual((copy / 'xhttp/config.json').read_text(), 'existing direct node')
        self.assertEqual((copy / 'sb.json').read_text(), 'original five protocols')
        for name in ['sbox-xhttp', 'sing-box', 'argo']:
            self.assertEqual((units / (name + '.service')).read_text(), name)
        calls = (copy / 'services.log').read_text().splitlines()
        self.assertEqual(calls, ['stop sbox-xhttp-argo-tunnel', 'disable sbox-xhttp-argo-tunnel',
                                'stop sbox-xhttp-argo', 'disable sbox-xhttp-argo', 'daemon-reload'])

    def test_new_tunnel_not_detected_as_legacy_fixed_tunnel(self):
        for name in ['result_vl_vm_hy_tu', 'sb_client', 'cfargo_ym', 'showprotocol']:
            # Check every actual process selector, including fixed-tunnel stop.
            if name + '(){' not in self.source:
                continue
            for line in function(self.source, name).splitlines():
                if "grep -q '[c]loudflared.*run'" in line:
                    self.assertIn("grep -v '[x]http-argo/cloudflared'", line)
        self.assertIn("/[c]loudflared.*run/ && !/xhttp-argo\\/cloudflared/", self.source)
        d = self.output / 'process-isolation'
        shell('''
printf '%s\\n' 'root 111 /etc/s-box/xhttp-argo/cloudflared tunnel run --token-file /safe/file' | grep -v '[x]http-argo/cloudflared' | grep -q '[c]loudflared.*run' && exit 1
printf '%s\\n' 'root 222 /etc/s-box/cloudflared tunnel run --token-file /safe/file' | grep -v '[x]http-argo/cloudflared' | grep -q '[c]loudflared.*run'
''', d)


if __name__ == '__main__':
    unittest.main()
