"""Field-based server config edits (menus 3→1, 3→2, 3→6, 4, 5, 15). Real generated sb10/sb11/sb.json, local only."""
import copy
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from config_harness import ROOT, bashpath, check, core, function, generate_vps, shell

HELPERS = ['sb_port_valid', 'sb_json_update', 'sb_inbound_set', 'sb_server_change', 'sb_uuid_replace',
           'sb_ip_strategy_apply', 'sb_warp_account_apply', 'sb_route_list', 'sb_route_filter', 'sbfl_apply', 'sbfl_set']
STUBS = r'''
red() { printf 'RED %s\n' "$1" >> messages; }
yellow() { :; }; green() { :; }; blue() { :; }; sleep() { :; }
restartsb() { echo restart >> restarts; [ "${RESTART_FAIL:-0}" = 0 ]; }
'''
FILES = ('sb.json', 'sb10.json', 'sb11.json')
INBOUND = {'vless': 'vless-sb', 'vmess': 'vmess-sb', 'hy2': 'hy2-sb', 'tuic5': 'tuic5-sb', 'anytls': 'anytls-sb'}
UUID = '11111111-2222-3333-4444-555555555555'


def inbound(cfg, tag):
    found = [i for i in cfg['inbounds'] if i.get('tag') == tag]
    return found[0] if len(found) == 1 else None


class ConfigEdits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.out = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='config-edits-'))) / 'config-edits'
        cls.base = {}
        for version in ('1.10', '1.14'):
            d = cls.out / ('base-' + version)
            if d.exists():
                shutil.rmtree(d)
            generate_vps(cls.source, d, version)
            cls.base[version] = d

    def case(self, version, name=None):
        d = self.out / (name or self._testMethodName) / version
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for f in FILES:
            shutil.copyfile(self.base[version] / f, d / f)
        return d

    def load(self, d):
        return {f: json.loads((d / f).read_text(encoding='utf8')) for f in FILES}

    def run_sh(self, d, version, body):
        src = self.source.replace('/etc/s-box', bashpath(d))
        helpers = ''.join(function(src, n) for n in HELPERS)
        return shell(helpers + STUBS + f'sbnh={version}\n' + body, d)

    def edit(self, version, body, mutate, name=None):
        """Run `body`, then require the files to equal the originals changed only by `mutate`."""
        d = self.case(version, name)
        expected = self.load(d)
        mutate(expected)
        self.run_sh(d, version, body)
        actual = self.load(d)
        for f in FILES:
            self.assertEqual(actual[f], expected[f], f'{version} {f}')
        self.assertFalse([p.name for p in d.iterdir() if re.search(r'\.json\.\w{6}$|^\.config-backup', p.name)])
        return d

    def unchanged_on_failure(self, version, body, name=None):
        d = self.case(version, name)
        before = {f: (d / f).read_bytes() for f in FILES}
        self.run_sh(d, version, 'rc=0; ' + body + ' || rc=$?\n[ "$rc" -ne 0 ]\n')
        for f in FILES:
            self.assertEqual((d / f).read_bytes(), before[f], f'{version} {f}')
        return d

    def test_update_requires_exactly_one_input_and_output_object(self):
        for payload in ('', '{} {}'):
            with self.subTest(payload=payload):
                d = self.case('1.14')
                source = d / 'sb11.json'
                source.write_text(payload, encoding='utf8')
                before = {f: (d / f).read_bytes() for f in FILES}
                self.run_sh(d, '1.14', "if sb_json_update '.' -- sb10.json sb11.json; then exit 1; fi")
                self.assertEqual({f: (d / f).read_bytes() for f in FILES}, before)
        self.unchanged_on_failure('1.14', "sb_json_update '., .' -- sb.json")

    # ---- inbound fields ----
    def test_ports_change_only_that_inbound(self):
        for version in ('1.10', '1.14'):
            for proto, port in (('vless', 1443), ('vmess', 2053), ('hy2', 3443), ('tuic5', 4443), ('anytls', 5443)):
                if proto == 'anytls' and version == '1.10':
                    continue
                with self.subTest(version=version, proto=proto):
                    def mutate(cfgs, proto=proto, port=port):
                        for f, cfg in cfgs.items():
                            target = inbound(cfg, INBOUND[proto])
                            if target is None:
                                self.assertEqual(proto, 'anytls')
                                continue
                            target['listen_port'] = port
                    self.edit(version, f'sb_server_change sb_inbound_set {proto} .listen_port port {port}\n'
                              '[ "$(wc -l < restarts)" -eq 1 ]\n', mutate, f'port-{proto}')

    def test_anytls_on_110_changes_only_sb11(self):
        def mutate(cfgs):
            self.assertIsNone(inbound(cfgs['sb10.json'], 'anytls-sb'))
            inbound(cfgs['sb11.json'], 'anytls-sb')['listen_port'] = 5443
        self.edit('1.10', 'sb_inbound_set anytls .listen_port port 5443\n', mutate)

    def test_tls_and_domain_fields(self):
        for version in ('1.10', '1.14'):
            with self.subTest(version=version):
                def mutate(cfgs):
                    for cfg in cfgs.values():
                        vl, vm = inbound(cfg, 'vless-sb'), inbound(cfg, 'vmess-sb')
                        vl['tls']['server_name'] = vl['tls']['reality']['handshake']['server'] = 'www.example.com'
                        vm['tls'].update(enabled=True, server_name='cdn.example.org',
                                         certificate_path='/root/ygkkkca/cert.crt', key_path='/root/ygkkkca/private.key')
                        for tag in ('hy2-sb', 'tuic5-sb'):
                            inbound(cfg, tag)['tls'].update(certificate_path='/root/ygkkkca/cert.crt',
                                                            key_path='/root/ygkkkca/private.key')
                        vm['transport']['path'] = '/new path&#|'
                self.edit(version, r'''
sb_inbound_set vless .tls.server_name str www.example.com .tls.reality.handshake.server str www.example.com
sb_inbound_set vmess .tls.enabled bool true .tls.server_name str cdn.example.org .tls.certificate_path str /root/ygkkkca/cert.crt .tls.key_path str /root/ygkkkca/private.key
for p in hy2 tuic5; do sb_inbound_set "$p" .tls.certificate_path str /root/ygkkkca/cert.crt .tls.key_path str /root/ygkkkca/private.key; done
sb_inbound_set vmess .transport.path str '/new path&#|'
''', mutate, 'tls-' + version)

    def test_inbound_rejects_bad_input_and_missing_fields_without_partial_change(self):
        for version in ('1.10', '1.14'):
            for body in ('sb_inbound_set vless .listen_port port 0443', 'sb_inbound_set vless .listen_port port 65536',
                         'sb_inbound_set vless .tls.server_name str ""', 'sb_inbound_set vless .no_such_field str x',
                         'sb_inbound_set trojan .listen_port port 443', "sb_inbound_set vless '.a|del(.)' str x"):
                with self.subTest(version=version, body=body):
                    self.unchanged_on_failure(version, body, 'reject')
        # One file without the field: no file changes (all-or-nothing).
        d = self.case('1.14', 'partial')
        cfg = json.loads((d / 'sb11.json').read_text(encoding='utf8'))
        del inbound(cfg, 'vmess-sb')['transport']
        (d / 'sb11.json').write_text(json.dumps(cfg), encoding='utf8')
        before = {f: (d / f).read_bytes() for f in FILES}
        self.run_sh(d, '1.14', 'if sb_inbound_set vmess .transport.path str /x; then exit 1; fi\n')
        for f in FILES:
            self.assertEqual((d / f).read_bytes(), before[f], f)

    def test_legacy_untagged_inbounds_use_index_fallback(self):
        d = self.case('1.14', 'legacy')
        for f in FILES:
            cfg = json.loads((d / f).read_text(encoding='utf8'))
            for i in cfg['inbounds']:
                i.pop('tag', None)
            (d / f).write_text(json.dumps(cfg), encoding='utf8')
        self.run_sh(d, '1.14', 'sb_inbound_set hy2 .listen_port port 3443\n')
        for f in FILES:
            cfg = json.loads((d / f).read_text(encoding='utf8'))
            self.assertEqual(cfg['inbounds'][2]['type'], 'hysteria2')
            self.assertEqual(cfg['inbounds'][2]['listen_port'], 3443, f)

    def test_uuid_replace_validates_both_values(self):
        new = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
        def mutate(cfgs):
            for f in FILES:
                text = json.dumps(cfgs[f]).replace(UUID, new)
                cfgs[f] = json.loads(text)
        self.edit('1.14', f'sb_uuid_replace {UUID} {new}\n', mutate)
        for bad in ('not-a-uuid', f'{UUID}/x', "11111111-2222-3333-4444-55555555555g"):
            with self.subTest(bad=bad):
                self.unchanged_on_failure('1.14', f"sb_uuid_replace {UUID} '{bad}'", 'uuid-bad')

    # ---- menu 15 / 3→6 ----
    def test_ip_strategy_110(self):
        def mutate(cfgs):
            for f in ('sb10.json', 'sb.json'):
                [o for o in cfgs[f]['outbounds'] if o['tag'] == 'direct'][0]['domain_strategy'] = 'ipv6_only'
        self.edit('1.10', 'sb_ip_strategy_apply ipv6_only\n', mutate)
        self.unchanged_on_failure('1.10', 'sb_ip_strategy_apply "prefer_ipv4;x"', 'ip-bad')

    def test_warp_account_both_layouts_and_reader(self):
        key = 'A' * 42 + 'E='
        for version, num in (('1.10', '10'), ('1.14', '11')):
            with self.subTest(version=version):
                def mutate(cfgs, num=num):
                    for f in ('sb10.json', 'sb11.json'):
                        for o in cfgs[f].get('outbounds', []):
                            if o.get('type') == 'wireguard':
                                o.update(private_key=key, reserved=[1, 2, 255])
                                o['local_address'][1] = '2606:4700:110::1/128'
                        for e in cfgs[f].get('endpoints', []):
                            if e.get('type') == 'wireguard':
                                e['private_key'] = key
                                e['address'][1] = '2606:4700:110::1/128'
                                e['peers'][0]['reserved'] = [1, 2, 255]
                    cfgs['sb.json'] = copy.deepcopy(cfgs[f'sb{num}.json'])
                d = self.edit(version, f"sb_warp_account_apply '{key}' 2606:4700:110::1 ' 1, 2,255'\n", mutate, 'warp-' + version)
                # Status reader (changewg) no longer depends on line numbers.
                reader = re.search(r"wgres=\$\((jq -r '\[\.%s.*?/etc/s-box/sb\.json) 2>/dev/null\)" %
                                   ('outbounds' if version == '1.10' else 'endpoints'), self.source).group(1)
                out = self.run_sh(d, version, reader.replace('/etc/s-box', bashpath(d)) + '\n').stdout.decode().strip()
                self.assertEqual(out, '1,2,255')
        for bad in ("'short' ::1 0,0,0", f"'{key}' 1.2.3.4 0,0,0", f"'{key}' ::1 1,2", f"'{key}' ::1 1,2,256"):
            with self.subTest(bad=bad):
                self.unchanged_on_failure('1.14', 'sb_warp_account_apply ' + bad, 'warp-bad')

    # ---- menu 5 domain routing ----
    CHANNELS = {'warp4': 'warp-IPv4-out', 'warp6': 'warp-IPv6-out', 'socks4': 'socks-IPv4-out',
                'socks6': 'socks-IPv6-out', 'vps4': 'vps-outbound-v4', 'vps6': 'vps-outbound-v6'}

    def test_routing_all_channels_on_110(self):
        for channel, tag in self.CHANNELS.items():
            for key in ('domain_suffix', 'geosite'):
                with self.subTest(channel=channel, key=key):
                    items = ['google.com', 'googleapis.com'] if key == 'domain_suffix' else ['netflix', 'geolocation-!cn']
                    def mutate(cfgs, channel=channel, tag=tag, key=key, items=items):
                        for f in ('sb10.json', 'sb.json'):
                            [r for r in cfgs[f]['route']['rules'] if r.get('outbound') == tag][0][key] = items
                        if key == 'domain_suffix' and channel in ('warp6', 'socks4'):
                            strategy, out = ('prefer_ipv6', 'warp-out') if channel == 'warp6' else ('prefer_ipv4', 'socks-out')
                            for r in cfgs['sb11.json']['route']['rules']:
                                if (r.get('action') == 'resolve' and r.get('strategy') == strategy) or r.get('outbound') == out:
                                    r[key] = items
                    d = self.edit('1.10', f'sbfl_set {channel} {key} "  {"   ".join(items)} "\n', mutate, f'route-{channel}-{key}')
        # The status readers (sbymfl) index rules[1..6] in sb.json: still the right channels.
        cfg = json.loads((self.out / 'route-warp4-domain_suffix' / '1.10' / 'sb.json').read_text(encoding='utf8'))
        self.assertEqual(cfg['route']['rules'][1]['domain_suffix'], ['google.com', 'googleapis.com'])

    def test_routing_modern_suffix_channels_and_reset(self):
        for channel, strategy, out in (('warp6', 'prefer_ipv6', 'warp-out'), ('socks4', 'prefer_ipv4', 'socks-out')):
            with self.subTest(channel=channel):
                def mutate(cfgs, channel=channel, strategy=strategy, out=out):
                    [r for r in cfgs['sb10.json']['route']['rules'] if r.get('outbound') == self.CHANNELS[channel]][0]['domain_suffix'] = ['openai.com']
                    for r in cfgs['sb11.json']['route']['rules']:
                        if (r.get('action') == 'resolve' and r.get('strategy') == strategy) or r.get('outbound') == out:
                            r['domain_suffix'] = ['openai.com']
                    cfgs['sb.json'] = copy.deepcopy(cfgs['sb11.json'])
                self.edit('1.14', f'sbfl_set {channel} domain_suffix openai.com\n', mutate, 'route-modern-' + channel)
        # Empty input restores the placeholder that switches the channel off.
        d = self.case('1.10', 'route-reset')
        self.run_sh(d, '1.10', 'sbfl_set vps6 geosite netflix\nsbfl_set vps6 geosite ""\n')
        rule = [r for r in json.loads((d / 'sb.json').read_text(encoding='utf8'))['route']['rules'] if r.get('outbound') == 'vps-outbound-v6'][0]
        self.assertEqual(rule['geosite'], ['yg_kkk'])

    def test_routing_rejects_injection(self):
        for value in ('a.com/b', 'a.com","evil', '$(touch PWNED)', 'a.com;b.com', '*.com'):
            with self.subTest(value=value):
                d = self.unchanged_on_failure('1.10', f"sbfl_set warp4 domain_suffix '{value}'", 'route-bad')
                self.assertFalse((d / 'PWNED').exists())
                self.assertFalse((d / 'restarts').exists())

    # ---- rollback ----
    def test_server_change_restores_on_restart_failure_and_on_edit_failure(self):
        d = self.case('1.14', 'rollback')
        before = {f: (d / f).read_bytes() for f in FILES}
        self.run_sh(d, '1.14', r'''
# The restart with the new config fails; the restart after restoring succeeds.
restartsb() { echo restart >> restarts; [ "$(wc -l < restarts)" -ne 1 ]; }
if sb_server_change sb_inbound_set vless .listen_port port 1443; then exit 1; fi
[ "$(wc -l < restarts)" -eq 2 ]
grep -q '恢复' messages
rm restarts
if sb_server_change sb_inbound_set vless .listen_port port 0; then exit 1; fi
[ ! -e restarts ]
# Restart keeps failing: config restored, backup kept and reported.
restartsb() { echo restart >> restarts; false; }
if sb_server_change sb_inbound_set vless .listen_port port 1443; then exit 1; fi
grep -q '备份保留在' messages
ls -d .config-backup.* > /dev/null
rm -rf .config-backup.*
''')
        for f in FILES:
            self.assertEqual((d / f).read_bytes(), before[f], f)
        self.assertFalse([p for p in d.iterdir() if p.name.startswith('.config-backup')])

    # ---- the edited files still load in real Sing-box cores ----
    def test_edited_configs_pass_real_core_check(self):
        cores = {'1.10': '1.10.7', '1.14': '1.14.4'}
        if not all(core(v).exists() for v in cores.values()):
            self.skipTest('real Sing-box test cores unavailable')
        key = 'A' * 42 + 'E='
        for version, real in cores.items():
            with self.subTest(version=version):
                d = self.case(version, 'core-check')
                body = (f'sb_inbound_set vless .listen_port port 1443\nsb_inbound_set vmess .transport.path str /p\n'
                        f"sb_warp_account_apply '{key}' 2606:4700:110::1 1,2,3\n"
                        'sbfl_set warp6 domain_suffix openai.com\nsbfl_set socks4 domain_suffix example.com\n')
                if version == '1.10':
                    body += 'sbfl_set vps4 geosite netflix\nsb_ip_strategy_apply prefer_ipv6\n'
                self.run_sh(d, version, body)
                result = check(real, d / 'sb.json')
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf8', 'replace'))

    def test_no_fixed_line_number_edits_or_reads_remain(self):
        self.assertFalse(re.findall(r'''(?m)^.*sed -[in] ["'][0-9]+[sdp].*$''', self.source))
        self.assertNotIn('xargs -n1 sed -i', self.source)


if __name__ == '__main__':
    unittest.main()
