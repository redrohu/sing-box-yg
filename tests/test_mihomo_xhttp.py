"""Verify optional sidecar export using real generators and, when provided, Mihomo."""
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

import yaml
import test_node_suffix as suffix_tests
from urllib.parse import unquote, urlsplit

from config_harness import (ROOT, RECORDS, bashpath, check, function, generate_vps,
                            run, save_records, shell)


class MihomoXHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='mihomo-xhttp-'))) / 'mihomo-xhttp'
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.mihomo = os.environ.get('MIHOMO_TEST_BIN')
        cls.xray = os.environ.get('XRAY_TEST_BIN')

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / 'commands.json')

    def generate(self, name, argo='none', version='1.14', server='192.0.2.1',
                 prefix=None, suffix=None, path='/xhttp-test'):
        d = self.output / name
        (d / 'xhttp').mkdir(parents=True, exist_ok=True)
        # Fixture deliberately differs from the existing sing-box inbound credentials.
        cfg = {'log': {'loglevel': 'warning'}, 'inbounds': [{
            'tag': 'xhttp-reality', 'listen': '::', 'port': 18443, 'protocol': 'vless',
            'settings': {'clients': [{'id': '22222222-3333-4444-5555-666666666666'}], 'decryption': 'none'},
            'streamSettings': {'network': 'xhttp', 'security': 'reality',
                'realitySettings': {'target': 'www.cloudflare.com:443', 'xver': 0,
                    'serverNames': ['www.cloudflare.com'],
                    'privateKey': 'eC9YOSPvhGUHAU1KLrr0X3GBiiYubH1zubnb_yxyylQ',
                    'shortIds': ['aabbccdd']}, 'xhttpSettings': {'path': path, 'mode': 'auto'}}}],
            'outbounds': [{'protocol': 'freedom', 'tag': 'direct'}]}
        (d / 'xhttp/config.json').write_text(json.dumps(cfg), encoding='utf8')
        (d / 'xhttp/public.key').write_text('5XaAecMR7oqsy_0v-N7ZqYeepf-gPOJkncIsxN-NIgs\n')
        (d / 'server_ipcl.log').write_text(server + '\n')
        generate_vps(self.source, d, version=version, argo=argo, prefix=prefix, suffix=suffix)
        return d, yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))

    def assertNode(self, d, cfg, server, name, path):
        nodes = [x for x in cfg['proxies'] if x.get('network') == 'xhttp']
        self.assertEqual(len(nodes), 1)
        node = nodes[0]
        self.assertEqual(node['name'], name)
        self.assertEqual(node['server'], server.strip('[]'))
        self.assertEqual(node['port'], 18443)
        self.assertEqual(node['uuid'], '22222222-3333-4444-5555-666666666666')
        self.assertEqual(node['xhttp-opts'], {'mode': 'auto', 'path': path})
        self.assertEqual(node['reality-opts']['short-id'], 'aabbccdd')
        self.assertTrue(node['reality-opts']['support-x25519mlkem768'])
        self.assertEqual(node['reality-opts']['public-key'], (d / 'xhttp/public.key').read_text().strip())
        self.assertEqual(node['servername'], 'www.cloudflare.com')
        self.assertTrue(node['tls'])
        self.assertFalse(node['skip-cert-verify'])
        self.assertNotIn('flow', node)
        self.assertNotIn('privateKey', json.dumps(node))
        self.assertNotIn('eC9YOSP', json.dumps(node))
        for group in cfg['proxy-groups']:
            self.assertEqual(group['proxies'].count(name), 1)
        singbox = json.loads((d / 'sbox.json').read_text(encoding='utf8'))
        self.assertFalse(any(x.get('transport', {}).get('type') == 'xhttp' for x in singbox['outbounds']))
        return node

    def test_all_argo_and_legacy_branches(self):
        for version in ['1.10', '1.14']:
            for argo in ['none', 'fixed', 'temporary', 'both']:
                with self.subTest(version=version, argo=argo):
                    d, cfg = self.generate(version + '-' + argo, argo=argo, version=version)
                    self.assertNode(d, cfg, '192.0.2.1', 'vless-xhttp-reality test-vps', '/xhttp-test')
                    self.assertEqual(check('1.14.4', d / 'sbox.json').returncode, 0, RECORDS[-1])

    def test_ipv6_names_path_and_repeat_refresh(self):
        for i, server in enumerate(['2001:db8::1', '[2001:db8::2]']):
            d, cfg = self.generate('ipv6-' + str(i), server=server, prefix='香港 #1 | VPS',
                suffix='测试 节点', path='/path#fragment|x?key="quoted"')
            name = '香港 #1 | VPS vless-xhttp-reality 测试 节点'
            self.assertNode(d, cfg, server, name, '/path#fragment|x?key="quoted"')
            before = (d / 'clmi.yaml').read_bytes()
            generate_vps(self.source, d, prefix='香港 #1 | VPS', suffix='测试 节点')
            self.assertEqual(before, (d / 'clmi.yaml').read_bytes())

    def test_removal_restores_exact_previous_outputs(self):
        for argo in ['none', 'fixed', 'temporary', 'both']:
            d = generate_vps(self.source, self.output / ('removal-' + argo), argo=argo)
            before = {n: (d / n).read_bytes() for n in ['clmi.yaml', 'sbox.json']}
            self.generate('removal-' + argo, argo=argo)
            self.assertNotEqual(before['clmi.yaml'], (d / 'clmi.yaml').read_bytes())
            self.assertEqual(before['sbox.json'], (d / 'sbox.json').read_bytes())
            shutil.rmtree(d / 'xhttp')
            generate_vps(self.source, d, argo=argo)
            for n in before:
                self.assertEqual(before[n], (d / n).read_bytes())

    def test_malformed_sidecar_does_not_overwrite_existing_exports(self):
        d, _ = self.generate('invalid')
        before = {n: (d / n).read_bytes() for n in ['clmi.yaml', 'sbox.json']}
        (d / 'xhttp/public.key').unlink()
        src = self.source.replace('/etc/s-box', bashpath(d))
        helpers = ''.join(function(src, name) for name in ['node_suffix_valid', 'node_suffix_load', 'xhttp_mihomo_load', 'sb_client'])
        shell(helpers + '\nif sb_client; then exit 1; fi\n', d)
        for n in before:
            self.assertEqual(before[n], (d / n).read_bytes())

    def test_real_mihomo_config_check(self):
        if not self.mihomo:
            self.skipTest('Set MIHOMO_TEST_BIN to a real Mihomo core')
        d, cfg = self.generate('core-check')
        # Only replace remote geodata-dependent rules; all generated proxies/groups are unchanged.
        cfg['rules'] = ['MATCH,🌍选择代理节点']
        cfg['external-controller'] = ''
        file = d / 'check.yaml'
        file.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf8')
        result = run([self.mihomo, '-t', '-d', d, '-f', file], timeout=60)
        self.assertEqual(result.returncode, 0, RECORDS[-1])

    def test_share_refresh_and_name_changes(self):
        d, _ = self.generate('share-refresh')
        before = (d / 'xhttp/config.json').read_bytes()
        helpers = suffix_tests.NodeSuffix.share_helpers(self, d)
        shell(helpers + '''
change_node_suffix <<'INPUT'
3
香港 #1 | VPS
INPUT
''', d)
        cfg = yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))
        name = '香港 #1 | VPS vless-xhttp-reality test-vps'
        self.assertNode(d, cfg, '192.0.2.1', name, '/xhttp-test')
        self.assertEqual(unquote(urlsplit((d / 'xhttp.txt').read_text().strip()).fragment), name)
        self.assertEqual((d / 'xhttp/config.json').read_bytes(), before)
        shutil.rmtree(d / 'xhttp')
        # Like change_node_suffix, call the legacy share assembler in a tested context:
        # optional absent protocol files intentionally return nonzero from cat.
        shell(helpers + '\nsbshare || exit 1\n', d)
        cfg = yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))
        self.assertFalse(any(x.get('network') == 'xhttp' for x in cfg['proxies']))
        self.assertNotIn('type=xhttp', (d / 'jhsub.txt').read_text())

    def test_real_mihomo_to_xray_transfer(self):
        openssl = shutil.which('openssl')
        curl = shutil.which('curl.exe' if os.name == 'nt' else 'curl')
        if not self.mihomo or not self.xray or not openssl or not curl:
            self.skipTest('Requires Mihomo, Xray, OpenSSL and curl')
        d, cfg = self.generate('transport', server='127.0.0.1')
        node = self.assertNode(d, cfg, '127.0.0.1', 'vless-xhttp-reality test-vps', '/xhttp-test')
        sockets = [socket.socket() for _ in range(3)]
        for s in sockets:
            s.bind(('127.0.0.1', 0))
        target_port, server_port, socks_port = [s.getsockname()[1] for s in sockets]
        for s in sockets:
            s.close()
        (d / 'openssl.cnf').write_text('[req]\ndistinguished_name=dn\n[dn]\n')
        result = run([openssl, 'req', '-config', d / 'openssl.cnf', '-x509', '-newkey', 'rsa:2048',
            '-nodes', '-keyout', d / 'key.pem', '-out', d / 'cert.pem', '-days', '1', '-subj', '/CN=www.cloudflare.com'])
        self.assertEqual(result.returncode, 0, RECORDS[-1])
        server = json.loads((d / 'xhttp/config.json').read_text())
        server['log']['loglevel'] = 'debug'
        server['inbounds'][0]['streamSettings']['realitySettings']['show'] = True
        server['inbounds'][0]['listen'] = '127.0.0.1'
        server['inbounds'][0]['port'] = server_port
        server['inbounds'][0]['streamSettings']['realitySettings']['target'] = f'127.0.0.1:{target_port}'
        server['outbounds'][0]['settings'] = {'finalRules': [{'action': 'allow', 'ip': ['127.0.0.1']}]}
        (d / 'server.json').write_text(json.dumps(server))
        node['port'] = server_port
        client = {'mixed-port': socks_port, 'bind-address': '127.0.0.1', 'mode': 'rule',
            'proxies': [node], 'rules': ['MATCH,' + node['name']]}
        (d / 'client.yaml').write_text(yaml.safe_dump(client, allow_unicode=True), encoding='utf8')
        payload = b'mihomo-xhttp-reality-test\n' * 8192

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
            [self.xray, 'run', '-config', str(d / 'server.json')],
            [self.mihomo, '-d', str(d), '-f', str(d / 'client.yaml')]]
        processes, logs = [], []
        try:
            for i, command in enumerate(commands):
                log = open(d / f'process-{i}.log', 'wb')
                logs.append(log)
                processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            time.sleep(2)
            for process in processes:
                self.assertIsNone(process.poll())
            result = run([curl, '-fsS', '--max-time', '20', '--noproxy', '', '--proxy',
                f'socks5h://127.0.0.1:{socks_port}', f'http://127.0.0.1:{httpd.server_port}/payload',
                '-o', d / 'payload.bin'])
            self.assertEqual(result.returncode, 0, RECORDS[-1])
            self.assertEqual((d / 'payload.bin').read_bytes(), payload)
            (d / 'payload-sha256.txt').write_text(hashlib.sha256(payload).hexdigest())
        finally:
            httpd.shutdown()
            httpd.server_close()
            for i, (process, command, log) in enumerate(zip(processes, commands, logs)):
                process.terminate()
                process.wait(timeout=10)
                log.close()
                RECORDS.append(dict(command=command, exit_code=process.returncode,
                    stdout=(d / f'process-{i}.log').read_text(errors='replace'), stderr='',
                    note='Long-running test service terminated after loopback transfer'))
