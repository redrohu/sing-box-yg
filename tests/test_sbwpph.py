"""WARP-plus-Socks5 (menu 14) helpers. Local mocks only: no download, process start or service change."""
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from config_harness import ROOT, bashpath, function, generate_vps, shell

HELPERS = ['sb_port_valid', 'sbwpph_arch', 'sbwpph_expected_sha256', 'sbwpph_file_sha256', 'sbwpph_country_valid',
           'sbwpph_install_binary', 'sbwpph_pids', 'sbwpph_kill', 'sb_json_update', 'sb_server_change',
           'sbwpph_set_outbound_port', 'sbwpph_port_edit', 'sbwpph_apply_port',
           'sbwpph_write_start', 'sbwpph_boot_enable', 'sbwpph_stop', 'sbwpph_boot_migrate', 'sb_cron_update']
STUBS = r'''
red() { printf 'RED %s\n' "$1" >> messages; }
yellow() { printf 'YELLOW %s\n' "$1" >> messages; }
green() { printf 'GREEN %s\n' "$1" >> messages; }
blue() { :; }
sleep() { :; }
'''


class Sbwpph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.out = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='sbwpph-'))) / 'sbwpph'

    def sandbox(self):
        d = self.out / self._testMethodName
        for sub in ('box', 'local'):
            (d / sub).mkdir(parents=True, exist_ok=True)
        return d

    def helpers(self, d, *names):
        src = (self.source.replace('/etc/s-box', bashpath(d / 'box')).replace('/etc/local.d', bashpath(d / 'local'))
               .replace('/tmp/sbox-cron.', bashpath(d / 'sbox-cron.')))
        return ''.join(function(src, n) for n in (names or HELPERS))

    def run_sh(self, d, body, *names):
        return shell(self.helpers(d, *names) + STUBS + f"BOX='{bashpath(d / 'box')}'\n" + body, d)

    # ---- binary verification ----
    def test_embedded_hashes_match_repository_binaries(self):
        body = function(self.source, 'sbwpph_expected_sha256')
        for arch in ('amd64', 'arm64'):
            actual = hashlib.sha256((ROOT / ('sbwpph_' + arch)).read_bytes()).hexdigest()
            self.assertIn(f'{arch}) echo {actual} ;;', body, 'update sbwpph_expected_sha256 together with sbwpph_' + arch)
        self.assertNotIn('--insecure', function(self.source, 'sbwpph_install_binary'))

    def test_architecture_mapping(self):
        d = self.sandbox()
        self.run_sh(d, r'''
for pair in x86_64:amd64 amd64:amd64 aarch64:arm64 arm64:arm64 armv8l:arm64; do
  uname() { echo "${pair%%:*}"; }
  [ "$(sbwpph_arch)" = "${pair#*:}" ]
done
for machine in armv7l armv6l i686 mips s390x; do
  uname() { echo "$machine"; }
  if sbwpph_arch >/dev/null; then echo "accepted $machine"; exit 1; fi
done
''', 'sbwpph_arch')

    def install_script(self, scenario):
        # The real expected-hash function is replaced by the hash of a known fake payload.
        return r'''
uname() { echo x86_64; }
printf '#!/bin/sh\n# GOOD-BINARY\n' > good.bin
sbwpph_expected_sha256() { [ "$1" = amd64 ] && sha256sum good.bin | awk '{print $1}'; }
curl() {
  local out= url= a
  echo "$*" >> curl.calls
  while (( $# )); do a=$1; shift; case $a in -o) out=$1; shift;; https://*) url=$a;; esac; done
  [ "$url" = https://raw.githubusercontent.com/redrohu/sing-box-yg/main/sbwpph_amd64 ] || return 99
  case ''' + scenario + r''' in
    fail) printf 'partial' > "$out"; return 28;;
    bad) printf '<html>404</html>' > "$out";;
    *) cp good.bin "$out";;
  esac
}
'''

    def test_download_failure_and_bad_hash_keep_existing_program(self):
        for scenario in ('fail', 'bad'):
            with self.subTest(scenario=scenario):
                d = self.sandbox() / scenario
                (d / 'box').mkdir(parents=True, exist_ok=True)
                (d / 'box' / 'sbwpph').write_bytes(b'OLD-PROGRAM\n')
                self.run_sh(d, self.install_script(scenario) + r'''
if sbwpph_install_binary; then echo 'failure reported as success'; exit 1; fi
[ "$(cat box/sbwpph)" = OLD-PROGRAM ]
[ -z "$(ls -A box | grep -v '^sbwpph$')" ]
grep -q -- '-f' curl.calls
''')

    def test_successful_download_replaces_and_matching_program_is_reused(self):
        d = self.sandbox()
        (d / 'box' / 'sbwpph').write_bytes(b'OLD-PROGRAM\n')
        self.run_sh(d, self.install_script('ok') + r'''
sbwpph_install_binary
cmp -s box/sbwpph good.bin
[ -x box/sbwpph ]
[ "$(wc -l < curl.calls)" -eq 1 ]
sbwpph_install_binary
[ "$(wc -l < curl.calls)" -eq 1 ]
uname() { echo armv7l; }
rm box/sbwpph
if sbwpph_install_binary; then exit 1; fi
[ "$(wc -l < curl.calls)" -eq 1 ]
grep -q '不支持' messages
''')

    # ---- input validation and launcher ----
    def test_country_and_launcher_reject_injection(self):
        d = self.sandbox()
        self.run_sh(d, r'''
fail() {
  echo "FAIL: $*" >&2
  if [ -f box/sbwpph.log ]; then echo '--- sbwpph.log' >&2; cat box/sbwpph.log >&2; fi
  if [ -f box/sbwpph-start.sh ]; then echo '--- sbwpph-start.sh' >&2; cat box/sbwpph-start.sh >&2; fi
  ls -la box >&2
  exit 1
}
for c in US GB SG JP; do sbwpph_country_valid "$c" || fail "valid country rejected: $c"; done
for c in us XX USA "" "US;touch PWNED" "US --tun" '$(touch PWNED)' "U*"; do
  if sbwpph_country_valid "$c"; then fail "accepted country [$c]"; fi
done
for bad in "0 4" "65536 4" "40000 5" "40000 4 XX" "40000 4 US;touch PWNED" '40000 4 $(touch PWNED)'; do
  set -- $bad
  if sbwpph_write_start "$1" "$2" "${3-}"; then fail "accepted [$bad]"; fi
done
[ ! -e PWNED ] || fail 'PWNED was created'
[ ! -e box/sbwpph-start.sh ] || fail 'launcher written for invalid input'
[ ! -e box/sbwpph.log ] || fail 'state file written for invalid input'
sbwpph_write_start 40001 4 US || fail "valid arguments rejected (rc=$?)"
want="exec $BOX/sbwpph -b 127.0.0.1:40001 --cfon --country US -4 --endpoint 162.159.192.1:2408 >/dev/null 2>&1"
got=$(sed -n 3p box/sbwpph-start.sh)
[ "$got" = "$want" ] || fail "launcher line 3 [$got] != [$want]"
# Status display parses fields 3 and 6 of sbwpph.log; keep that format.
got=$(awk '{print $3}' box/sbwpph.log | awk -F: '{print $NF}'); [ "$got" = 40001 ] || fail "log port [$got]"
got=$(awk '{print $6}' box/sbwpph.log); [ "$got" = US ] || fail "log country [$got]"
grep -q -- ' --country US ' box/sbwpph.log || fail 'log has no --country option'
sbwpph_write_start 40002 6 || fail "second valid start rejected (rc=$?)"
got=$(awk '{print $3}' box/sbwpph.log | awk -F: '{print $NF}'); [ "$got" = 40002 ] || fail "rewritten log port [$got]"
if grep -q -- ' --country ' box/sbwpph.log; then fail '--country left after rewrite'; fi
if grep -q '>' box/sbwpph.log; then fail 'redirection stored in display file'; fi
''')
        launcher = (d / 'box' / 'sbwpph-start.sh').read_text(encoding='utf8')
        self.assertTrue(launcher.startswith('#!/bin/bash\n'))
        self.assertNotIn('$(', launcher)

    # ---- sing-box config edit ----
    def test_outbound_port_changes_only_socks_port_in_real_templates(self):
        d = self.sandbox()
        generate_vps(self.source, d / 'box', '1.14')
        before = {n: json.loads((d / 'box' / n).read_text(encoding='utf8')) for n in ('sb10.json', 'sb11.json')}
        self.run_sh(d, 'sbwpph_set_outbound_port 41234\n')
        for name, old in before.items():
            new = json.loads((d / 'box' / name).read_text(encoding='utf8'))
            socks = [o for o in old['outbounds'] if o.get('tag') == 'socks-out']
            self.assertEqual(len(socks), 1, name)
            self.assertEqual(socks[0]['server_port'], 40000)
            socks[0]['server_port'] = 41234
            self.assertEqual(new, old, name)  # nothing else changed
        self.assertFalse([p for p in (d / 'box').iterdir() if re.search(r'\.json\.\w{6}$', p.name)])

    def test_outbound_port_refuses_ambiguous_files_without_partial_change(self):
        d = self.sandbox()
        good = {'outbounds': [{'type': 'wireguard', 'tag': 'wireguard-out', 'server_port': 2408},
                              {'type': 'socks', 'tag': 'socks-out', 'server': '127.0.0.1', 'server_port': 40000}]}
        (d / 'box' / 'sb10.json').write_text(json.dumps(good, indent=2), encoding='utf8')
        (d / 'box' / 'sb11.json').write_text(json.dumps({'outbounds': [{'tag': 'direct'}]}, indent=2), encoding='utf8')
        before = {n: (d / 'box' / n).read_bytes() for n in ('sb10.json', 'sb11.json')}
        self.run_sh(d, r'''
if sbwpph_set_outbound_port 41234; then exit 1; fi
if sbwpph_set_outbound_port 0443; then exit 1; fi
''')
        for name, data in before.items():
            self.assertEqual((d / 'box' / name).read_bytes(), data, name)

    def test_apply_port_rolls_back_when_restart_fails(self):
        d = self.sandbox()
        cfg = lambda port: json.dumps({'outbounds': [{'type': 'socks', 'tag': 'socks-out', 'server_port': port}]}, indent=2)
        for name in ('sb10.json', 'sb11.json'):
            (d / 'box' / name).write_text(cfg(40000), encoding='utf8')
        (d / 'box' / 'sb.json').write_text('LIVE', encoding='utf8')
        before = {n: (d / 'box' / n).read_bytes() for n in ('sb.json', 'sb10.json', 'sb11.json')}
        self.run_sh(d, r'''
sbnh=1.14
restartsb() { echo restart >> restarts; [ "$(cat box/sb.json)" = LIVE ]; }
if sbwpph_apply_port 41234; then exit 1; fi
[ "$(wc -l < restarts)" -eq 2 ]
grep -q '恢复' messages
''')
        for name, data in before.items():
            self.assertEqual((d / 'box' / name).read_bytes(), data, name)
        self.assertFalse([p for p in (d / 'box').iterdir() if p.name.startswith('.config-backup')])
        self.run_sh(d, r'''
sbnh=1.14
restartsb() { :; }
sbwpph_apply_port 41234
''')
        self.assertEqual(json.loads((d / 'box' / 'sb.json').read_text())['outbounds'][0]['server_port'], 41234)

    # ---- process, boot and stop ----
    def test_kill_matches_only_project_binary(self):
        d = self.sandbox()
        self.run_sh(d, r'''
P=$BOX/sbwpph
ps() { cat ps.out; }
printf '%s\n' "101 $P -b 127.0.0.1:40000 -4" "102 vim $P.log" "103 /opt/other/sbwpph -b 0.0.0.0:1" "104 grep sbwpph" "105 $P --cfon" > ps.out
kill() { echo "$*" >> kill.calls; [ "$1" = -TERM ] && grep -v -e "^${2} " ps.out > ps.new && mv ps.new ps.out; return 0; }
sbwpph_kill
[ "$(cat kill.calls)" = "$(printf '%s\n' '-TERM 101' '-TERM 105')" ]
''')

    def test_boot_entry_and_stop_do_not_evaluate_state_file(self):
        d = self.sandbox()
        project = bashpath(d / 'box')
        legacy = '@reboot sleep 10 && /bin/bash -c "nohup $(cat ' + project + '/sbwpph.log 2>/dev/null) &"'
        (d / 'cron.current').write_text('0 * * * * keep-me\n' + legacy + '\n', encoding='utf8')
        self.run_sh(d, r'''
command() { if [ "$1" = -v ] && [ "$2" = apk ]; then return 1; fi; builtin command "$@"; }
crontab() { if [ "$1" = -l ]; then cat cron.current; else cp "$1" cron.current; fi; }
sbwpph_boot_enable
[ "$(grep -c sing-box-yg:warp cron.current)" -eq 1 ]
grep -qx '0 \* \* \* \* keep-me' cron.current
if grep -q 'sbwpph.log' cron.current; then echo 'legacy evaluated entry kept'; exit 1; fi
grep -q 'nohup /bin/bash .*/sbwpph-start.sh >/dev/null 2>&1 &' cron.current
: > box/sbwpph.log; : > box/sbwpph-start.sh; : > local/alpinews5.start
ps() { :; }
sbwpph_stop
[ "$(cat cron.current)" = '0 * * * * keep-me' ]
[ ! -e box/sbwpph.log ] && [ ! -e box/sbwpph-start.sh ] && [ ! -e local/alpinews5.start ]
''')
        # Alpine boot script: backgrounded launcher, not `nohup $(cat …)` in the foreground.
        d2 = self.sandbox() / 'alpine'
        (d2 / 'box').mkdir(parents=True, exist_ok=True); (d2 / 'local').mkdir(exist_ok=True)
        self.run_sh(d2, r'''
command() { if [ "$1" = -v ] && [ "$2" = apk ]; then return 0; fi; builtin command "$@"; }
rc-update() { echo "$*" >> rc.calls; }
sbwpph_boot_enable
grep -qx 'add local default' rc.calls
''')
        text = (d2 / 'local' / 'alpinews5.start').read_text(encoding='utf8')
        self.assertIn('sbwpph-start.sh >/dev/null 2>&1 &', text)
        self.assertNotIn('$(cat', text)

    # ---- menu flow ----
    def menu(self, d, inputs, extra='', start_fail=0):
        return self.run_sh(d, f'START_FAIL={start_fail}\n' + r'''
sbactive() { :; }; sb() { echo MAIN-MENU >> calls; }
inputs=(''' + ' '.join(repr(i) for i in inputs) + r''')
readp() { [ ${#inputs[@]} -gt 0 ] || return 1; printf -v "$2" '%s' "${inputs[0]}"; inputs=("${inputs[@]:1}"); }
sbwpph_prepare() { port=40001; sw46=4; echo prepare >> calls; }
sbwpph_switch() { echo "switch $*" >> calls; [ "${START_FAIL:-0}" = 0 ]; }
sbwpph_stop() { echo stop >> calls; }
rc=0; inssbwpph > /dev/null || rc=$?
''' + extra, 'sbwpph_country_valid', 'inssbwpph')

    def test_menu_validates_country_and_reports_switch_failure(self):
        self.menu(self.sandbox(), ['2', 'XX', 'us ', 'never-read'], r'''
[ "$rc" -eq 0 ]
[ "$(cat calls)" = "$(printf '%s
' prepare 'switch 40001 4 US')" ]
grep -q '国家代码无效' messages
''')
        d = self.sandbox() / 'fail'
        (d / 'box').mkdir(parents=True, exist_ok=True)
        self.menu(d, ['1'], r'''
[ "$rc" -eq 1 ]
[ "$(cat calls)" = "$(printf '%s
' prepare 'switch 40001 4 ')" ]
''', start_fail=1)

    def test_switch_restores_running_proxy_and_files_on_failure(self):
        for stage in ('write', 'start', 'edit', 'restart', 'boot'):
            with self.subTest(stage=stage):
                self.run_sh(self.sandbox(), 'stage=' + stage + r'''
printf old-bin > box/sbwpph
chmod +x box/sbwpph
printf old-launcher > box/sbwpph-start.sh
printf old-config > box/sb.json
touch running
sbwpph_pids() { if [ -f running ]; then echo 123; fi; }
sbwpph_install_binary() { printf new-bin > box/sbwpph; }
sbwpph_kill() { rm -f running; }
sbwpph_write_start() { printf new-launcher > box/sbwpph-start.sh; [ "$stage" != write ]; }
sbwpph_start() { touch running; [ "$stage" != start ]; }
sbwpph_port_edit() { printf new-config > box/sb.json; [ "$stage" != edit ]; }
restartsb() { [ "$stage" != restart ] || [ "$(cat box/sb.json)" = old-config ]; }
sbwpph_boot_enable() { [ "$stage" != boot ]; }
nohup() { [ "$(cat "$2")" = old-launcher ] && touch running; }
sleep() { wait; }
if sbwpph_switch 40001 4 US; then exit 1; fi
[ -f running ]
[ "$(cat box/sbwpph)" = old-bin ]
[ "$(cat box/sbwpph-start.sh)" = old-launcher ]
[ "$(cat box/sb.json)" = old-config ]
''', 'sbwpph_switch')

    def test_menu_eof_on_country_prompt_does_not_loop(self):
        d = self.sandbox()
        self.menu(d, ['2'], r'''
[ "$rc" -eq 1 ]
[ "$(cat calls)" = prepare ]
''')

    def test_menu_stop_and_return(self):
        d = self.sandbox()
        self.menu(d, ['3'], '[ "$rc" -eq 0 ]\n[ "$(cat calls)" = stop ]\n')
        d = self.sandbox() / 'back'
        (d / 'box').mkdir(parents=True, exist_ok=True)
        self.menu(d, ['0'], '[ "$(cat calls)" = MAIN-MENU ]\n')

    def test_menu_text_and_uninstall_contract(self):
        body = function(self.source, 'inssbwpph')
        for label in ['1：重置启用WARP-plus-Socks5本地Warp代理模式', '2：重置启用WARP-plus-Socks5多地区Psiphon代理模式',
                      '3：停止WARP-plus-Socks5代理模式', '0：返回上层']:
            self.assertIn(label, body)
        self.assertNotRegex(body, r'\bunins\b')
        self.assertEqual(len(re.findall(r'(?m)^unins\(\)\s*\{', self.source)), 1)
        self.assertIn('chooseport 40000', function(self.source, 'sbwpph_prepare'))
        unins = function(self.source, 'unins')
        self.assertNotIn("grep '[s]bwpph'", unins)
        self.assertIn('$2 == "/etc/s-box/sbwpph"', unins)
        for line in self.source.splitlines():
            self.assertNotRegex(line, r'sed -i "1(27|65)s/\$s5port')
        self.assertIn('sbwpph_port_edit', function(self.source, 'sbwpph_switch'))

    # ---- one-time migration of pre-fork.19 boot entries ----
    CRON = r'''
command() { if [ "$1" = -v ] && [ "$2" = apk ]; then [ "${ALPINE:-0}" = 1 ]; return; fi; builtin command "$@"; }
crontab() { echo "$1" >> crontab.calls; if [ "$1" = -l ]; then cat cron.current; else cp "$1" cron.current; fi; }
rc-update() { echo "$*" >> rc.calls; }
'''

    def legacy(self, d, log_line, alpine=False):
        box = bashpath(d / 'box')
        (d / 'box' / 'sbwpph.log').write_text(log_line.replace('{BOX}', box) + '\n', encoding='utf8', newline='\n')
        old_cron = '@reboot sleep 10 && /bin/bash -c "nohup $(cat ' + box + '/sbwpph.log 2>/dev/null) &"'
        (d / 'cron.current').write_text('0 * * * * keep-me\n' + ('' if alpine else old_cron + '\n'),
                                        encoding='utf8', newline='\n')
        if alpine:
            (d / 'local' / 'alpinews5.start').write_text(
                '#!/bin/bash\nsleep 10\nnohup $(cat ' + box + '/sbwpph.log 2>/dev/null)\n', encoding='utf8', newline='\n')
        return box

    def test_migration_rebuilds_known_formats_once(self):
        cases = [
            ('{BOX}/sbwpph -b 127.0.0.1:40001 --cfon --country US -4 --endpoint 162.159.192.1:2408 >/dev/null 2>&1',
             '-b 127.0.0.1:40001 --cfon --country US -4 --endpoint 162.159.192.1:2408'),
            ('{BOX}/sbwpph -b 127.0.0.1:40002 -6 --endpoint 162.159.192.1:2408 >/dev/null 2>&1',
             '-b 127.0.0.1:40002 -6 --endpoint 162.159.192.1:2408'),
        ]
        for index, (log_line, args) in enumerate(cases):
            with self.subTest(args=args):
                d = self.sandbox() / str(index)
                for sub in ('box', 'local'):
                    (d / sub).mkdir(parents=True, exist_ok=True)
                box = self.legacy(d, log_line)
                self.run_sh(d, self.CRON + r'''
sbwpph_boot_migrate
[ -x box/sbwpph-start.sh ]
[ "$(grep -c 'sing-box-yg:warp' cron.current)" -eq 1 ]
grep -qx '0 \* \* \* \* keep-me' cron.current
if grep -q 'sbwpph.log' cron.current; then echo 'old evaluated entry kept'; exit 1; fi
grep -q '^GREEN 已将WARP-plus-Socks5开机任务迁移' messages
calls=$(wc -l < crontab.calls)
sbwpph_boot_migrate
[ "$(wc -l < crontab.calls)" -eq "$calls" ]
''')
                launcher = (d / 'box' / 'sbwpph-start.sh').read_text(encoding='utf8').splitlines()
                self.assertEqual(launcher[2], f'exec {box}/sbwpph {args} >/dev/null 2>&1')
                self.assertEqual((d / 'box' / 'sbwpph.log').read_text(encoding='utf8'), f'{box}/sbwpph {args}\n')

    def test_migration_disables_unrecognized_content_without_executing_it(self):
        payloads = [
            '{BOX}/sbwpph -b 127.0.0.1:40000 --cfon --country US;touch PWNED -4 --endpoint 162.159.192.1:2408 >/dev/null 2>&1',
            '{BOX}/sbwpph -b 127.0.0.1:40000 -4 --endpoint 162.159.192.1:2408 >/dev/null 2>&1; touch PWNED',
            '$(touch PWNED)',
            '{BOX}/sbwpph -b 127.0.0.1:99999 -4 --endpoint 162.159.192.1:2408',
            '{BOX}/sbwpph -b 127.0.0.1:40000 --cfon --country XX -4 --endpoint 162.159.192.1:2408',
        ]
        for index, payload in enumerate(payloads):
            with self.subTest(payload=payload):
                d = self.sandbox() / str(index)
                for sub in ('box', 'local'):
                    (d / sub).mkdir(parents=True, exist_ok=True)
                self.legacy(d, payload)
                self.run_sh(d, self.CRON + r'''
sbwpph_boot_migrate
[ ! -e PWNED ] && [ ! -e box/PWNED ]
[ ! -e box/sbwpph-start.sh ]
[ -e box/.sbwpph-boot-disabled ]
[ "$(cat cron.current)" = '0 * * * * keep-me' ]
grep -q '^RED WARP-plus-Socks5旧开机任务内容无法识别' messages
calls=$(wc -l < crontab.calls)
sbwpph_boot_migrate
[ "$(wc -l < crontab.calls)" -eq "$calls" ]
# Re-running menu 14 writes a valid launcher and clears the reminder.
sbwpph_write_start 40003 4
[ ! -e box/.sbwpph-boot-disabled ]
''')

    def test_migration_alpine_and_noop_cases(self):
        d = self.sandbox()
        box = self.legacy(d, '{BOX}/sbwpph -b 127.0.0.1:40004 -4 --endpoint 162.159.192.1:2408 >/dev/null 2>&1', alpine=True)
        self.run_sh(d, self.CRON + r'''
ALPINE=1
sbwpph_boot_migrate
[ ! -e crontab.calls ]
grep -qx 'add local default' rc.calls
''')
        text = (d / 'local' / 'alpinews5.start').read_text(encoding='utf8')
        self.assertIn('sbwpph-start.sh >/dev/null 2>&1 &', text)
        self.assertNotIn('$(cat', text)
        d2 = self.sandbox() / 'alpine-bad'
        for sub in ('box', 'local'):
            (d2 / sub).mkdir(parents=True, exist_ok=True)
        self.legacy(d2, '$(touch PWNED)', alpine=True)
        self.run_sh(d2, self.CRON + 'ALPINE=1\nsbwpph_boot_migrate\n[ ! -e local/alpinews5.start ]\n[ ! -e PWNED ]\n')
        # Nothing to do: no state file, or already migrated.
        d3 = self.sandbox() / 'noop'
        for sub in ('box', 'local'):
            (d3 / sub).mkdir(parents=True, exist_ok=True)
        self.run_sh(d3, self.CRON + r'''
sbwpph_boot_migrate
: > box/sbwpph.log; : > box/sbwpph-start.sh
sbwpph_boot_migrate
[ ! -e crontab.calls ] && [ ! -e messages ]
''')

    def test_migration_runs_from_main_menu_after_definitions(self):
        src = self.source
        # Outside the frozen menu header (clear..insV=) and the update-notice block (insV=..lapre), both pinned by
        # test_config_generation / test_update_log; runs once per menu start, after every function is defined.
        call = src.index('\nlapre\n# Below the frozen menu header and the update-notice block (both pinned by tests).\nsbwpph_boot_migrate\n')
        self.assertGreater(call, src.index('\nsb_update_notice "$insV"\n'))
        self.assertGreater(call, src.index('\nsbsm(){'))
        self.assertGreater(call, src.index('\nclear\n'))
        self.assertIn('.sbwpph-boot-disabled', function(src, 'showprotocol'))
        self.assertIn('.sbwpph-boot-disabled', function(src, 'sbwpph_stop'))


if __name__ == '__main__':
    unittest.main()
