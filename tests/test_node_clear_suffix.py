"""Explicitly clear suffixes without changing defaults, credentials or whitespace."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

import yaml
from config_harness import ROOT, bashpath, check, function, generate_vps, save_records, shell
import test_node_suffix as suffix_tests


class ClearSuffix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.output = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp())) / 'clear-suffix'
        cls.output.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / 'commands.json')

    def test_generators_all_argo_modes_no_trailing_space(self):
        for version in ['1.10', '1.14']:
            for argo in ['none', 'fixed', 'temporary', 'both']:
                d = generate_vps(self.source, self.output / (version + argo), version=version, argo=argo,
                                 prefix='RN 美国 |', suffix='custom-suffix')
                before = json.loads((d / 'sbox.json').read_text(encoding='utf8'))
                old_yaml = yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))
                origin = (d / 'sb.json').read_bytes()
                (d / 'node_suffix.disabled').write_text('disabled\n')
                generate_vps(self.source, d, version=version, argo=argo)
                cfg = json.loads((d / 'sbox.json').read_text(encoding='utf8'))
                expected = json.loads(json.dumps(before).replace(' custom-suffix', ''))
                self.assertEqual(cfg, expected)
                expected_yaml = yaml.safe_load(yaml.safe_dump(old_yaml, allow_unicode=True).replace(' custom-suffix', ''))
                clash = yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))
                self.assertEqual(clash, expected_yaml)
                for node in clash['proxies']:
                    self.assertFalse(node['name'].endswith(' '))
                self.assertEqual((d / 'sb.json').read_bytes(), origin)
                self.assertEqual(check('1.14.4', d / 'sbox.json').returncode, 0)

    def test_menu_clear_persist_prefix_independence_and_restore(self):
        d = generate_vps(self.source, self.output / 'menu', argo='both', prefix='RN 美国 |', suffix='custom')
        helpers = suffix_tests.NodeSuffix.share_helpers(self, d)
        server = (d / 'sb.json').read_bytes()
        shell(helpers + "change_node_suffix <<'INPUT'\n5\nINPUT\n", d)
        self.assertTrue((d / 'node_suffix.disabled').exists())
        self.assertEqual((d / 'node_prefix.conf').read_text(encoding='utf8'), 'RN 美国 |\n')
        self.assertEqual((d / 'node_suffix.conf').read_text(), 'custom\n')
        shell(helpers + 'sbshare || exit $?\n', d)
        for link in (d / 'jhsub.txt').read_text(encoding='utf8').splitlines():
            name = json.loads(base64.b64decode(link[8:]))['ps'] if link.startswith('vmess://') else unquote(urlsplit(link).fragment)
            self.assertTrue(name.startswith('RN 美国 | '), name)
            self.assertFalse(name.endswith(' '), name)
            self.assertNotIn('custom', name)
            self.assertNotIn('test-vps', name)
        shell(helpers + "change_node_suffix <<'INPUT'\n4\nINPUT\n", d)
        self.assertTrue((d / 'node_suffix.disabled').exists())
        clash = yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))
        self.assertIn('anytls', [n['name'] for n in clash['proxies']])
        shell(helpers + "change_node_suffix <<'INPUT'\n2\nINPUT\n", d)
        self.assertFalse((d / 'node_suffix.disabled').exists())
        self.assertFalse((d / 'node_suffix.conf').exists())
        self.assertIn('anytls test-vps', [n['name'] for n in yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))['proxies']])
        shell(helpers + "change_node_suffix <<'INPUT'\n5\nINPUT\nchange_node_suffix <<'INPUT'\n1\nnew-suffix\nINPUT\n", d)
        self.assertFalse((d / 'node_suffix.disabled').exists())
        self.assertIn('anytls new-suffix', [n['name'] for n in yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))['proxies']])
        self.assertEqual((d / 'sb.json').read_bytes(), server)
        self.assertFalse((d / 'forbidden').exists())
        self.assertTrue(any((p / 'node_suffix.disabled').exists() for p in d.glob('node-name.bak.*')))

    def test_both_xhttp_exports_without_suffix(self):
        d = self.output / 'sidecars'
        (d / 'xhttp').mkdir(parents=True, exist_ok=True)
        (d / 'xhttp-argo').mkdir(exist_ok=True)
        source = self.source.replace('/etc/s-box', bashpath(d))
        names = ['node_suffix_valid', 'node_suffix_load', 'xhttp_server_config', 'xhttp_client_config',
                 'xhttp_export', 'xhttp_argo_server_config', 'xhttp_argo_address_valid', 'xhttp_argo_mihomo_load', 'xhttp_argo_export']
        helpers = ''.join(function(source, n) for n in names)
        script = helpers + '''
hostname=test-vps
printf '%s\n' 192.0.2.1 > server_ipcl.log
printf '%s\n' RN > node_prefix.conf
printf '%s\n' disabled > node_suffix.disabled
printf '%s\n' 5XaAecMR7oqsy_0v-N7ZqYeepf-gPOJkncIsxN-NIgs > xhttp/public.key
xhttp_server_config xhttp 18443 www.cloudflare.com 11111111-2222-3333-4444-555555555555 eC9YOSPvhGUHAU1KLrr0X3GBiiYubH1zubnb_yxyylQ aabbccdd /test-path
printf '%s\n' xhttp.example.org > xhttp-argo/domain
printf '%s\n' mlkem768x25519plus.native.0rtt.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA > xhttp-argo/encryption.key
xhttp_argo_server_config xhttp-argo 18080 22222222-3333-4444-5555-666666666666 /test/ mlkem768x25519plus.native.300s.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
xhttp_export
xhttp_argo_export
'''
        shell(script, d)
        for filename, name in [('xhttp.txt', 'RN vless-xhttp-reality'), ('xhttp-argo.txt', 'RN vless-xhttp-argo')]:
            self.assertEqual(unquote(urlsplit((d / filename).read_text().strip()).fragment), name)
        generate_vps(self.source, d, argo='both')
        clash = yaml.safe_load((d / 'clmi.yaml').read_text(encoding='utf8'))
        for name in ['RN vless-xhttp-reality', 'RN vless-xhttp-argo']:
            self.assertIn(name, [n['name'] for n in clash['proxies']])
            for group in clash['proxy-groups']:
                self.assertEqual(group['proxies'].count(name), 1)


if __name__ == '__main__':
    unittest.main()
