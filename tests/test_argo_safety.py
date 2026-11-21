"""Local-only regression tests for exact Argo/cron/NAT resource ownership.

All process, service, cron, and firewall operations are sandbox stubs. Set
SB_UNDER_TEST to test a candidate sb.sh without changing the workspace script.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from config_harness import BASH, ROOT, bashpath, function


class ArgoSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = Path(os.environ.get('SB_UNDER_TEST', ROOT / 'sb.sh')).resolve()
        cls.source = cls.target.read_text(encoding='utf8')
        base = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='argo-safety-'))) / 'argo-safety'
        base.mkdir(parents=True, exist_ok=True)
        cls.output = Path(tempfile.mkdtemp(prefix='run-', dir=base))
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        (cls.output / 'commands.json').write_text(json.dumps(cls.records, ensure_ascii=False, indent=2), encoding='utf8')

    def sandbox(self):
        d = self.output / self._testMethodName
        d.mkdir(parents=True, exist_ok=True)
        (d / 'project').mkdir(exist_ok=True)
        (d / 'units').mkdir(exist_ok=True)
        (d / 'init').mkdir(exist_ok=True)
        (d / 'local').mkdir(exist_ok=True)
        return d

    def translated(self, d):
        # Redirect every filesystem target before extracting any real function.
        return (self.source.replace('/etc/s-box', bashpath(d / 'project'))
                .replace('/etc/systemd/system', bashpath(d / 'units'))
                .replace('/etc/init.d', bashpath(d / 'init'))
                .replace('/etc/local.d', bashpath(d / 'local'))
                .replace('/root/', bashpath(d / 'root') + '/')
                .replace('/usr/bin/sb', bashpath(d / 'sb-command'))
                .replace('/tmp/sbox-cron.', bashpath(d / 'sbox-cron.')))

    def helpers(self, d, *names):
        src = self.translated(d)
        return ''.join(function(src, name) for name in names)

    def run_shell(self, d, script):
        path = d / 'run.sh'
        # Production does not enable errexit. Assertions explicitly inspect results.
        path.write_text('set +e\nfail() { echo "ASSERTION: $*" >&2; exit 90; }\n'
                        'red() { printf "%s\\n" "$*" >&2; }; green() { :; }; yellow() { :; }; blue() { :; }\n'
                        + script, encoding='utf8', newline='\n')
        cmd = [str(BASH), bashpath(path)]
        p = subprocess.run(cmd, cwd=d, capture_output=True)
        record = dict(command=cmd, cwd=str(d), target=str(self.target), exit_code=p.returncode,
                      stdout=p.stdout.decode('utf8', 'replace'), stderr=p.stderr.decode('utf8', 'replace'))
        self.records.append(record)
        self.assertEqual(p.returncode, 0, record)
        return record

    def cron_stub(self):
        return r'''
crontab() {
 if [[ $1 == -l ]]; then
  if [[ ${CRON_READ_FAIL:-0} == 1 ]]; then echo 'permission denied' >&2; return 1; fi
  if [[ ${CRON_ABSENT:-0} == 1 ]]; then echo 'no crontab for root' >&2; return 1; fi
  cat cron.current
 else
  printf '%s\n' "$1" >> cron.writes
  [[ ${CRON_WRITE_FAIL:-0} != 1 ]] || return 1
  cp "$1" cron.current
 fi
}
'''

    def legacy_crons(self, d):
        source = self.translated(d)
        project = bashpath(d / 'project')
        root = bashpath(d / 'root')
        return {
            'restart': '0 1 * * * systemctl restart sing-box;rc-service sing-box restart',
            'argo': '@reboot sleep 10 && /bin/bash -c "nohup ' + project + '/cloudflared tunnel --url http://localhost:$(sed x ' + project + '/sb.json) --protocol http2 > ' + project + '/argo.log 2>&1 &"',
            'subscription': '@reboot sleep 10 && /bin/bash -c "busybox httpd -f -p $(cat ' + project + '/subport.log 2>/dev/null) -h ' + root + '/websbox > /dev/null 2>&1 &"',
            'warp': '@reboot sleep 10 && /bin/bash -c "nohup $(cat ' + project + '/sbwpph.log 2>/dev/null) &"',
        }

    def test_cron_removes_only_owned_legacy_and_tagged_entries(self):
        d = self.sandbox()
        project = bashpath(d / 'project')
        root = bashpath(d / 'root')
        keep = [
            '# preserve sing-box / sbwpph / websbox documentation',
            '0 * * * * curl http://example.org/backup',
            '@reboot /opt/other/cloudflared tunnel --url http://localhost:2052',
            '0 3 * * * systemctl restart sing-box-other.service',
            '@reboot /opt/backup-websbox',
            '@reboot busybox httpd -f -p $(cat ' + project + '/subport.log 2>/dev/null) -h ' + root + '/websbox-other > /dev/null',
            '@reboot /bin/bash -c "nohup $(cat ' + project + '/sbwpph.log.other 2>/dev/null) &"',
        ]
        owned = list(self.legacy_crons(d).values()) + ['@reboot harmless # sing-box-yg:argo']
        (d / 'cron.current').write_text('\n'.join(keep + owned) + '\n')
        self.run_shell(d, self.helpers(d, 'sb_cron_update') + self.cron_stub() + '''
sb_cron_update all || fail cleanup
''')
        self.assertEqual((d / 'cron.current').read_text().splitlines(), keep)
        self.assertFalse(list(d.glob('sbox-cron.*')))

    def test_restart_schedule_preserves_other_project_crons_and_migrates(self):
        d = self.sandbox()
        old = self.legacy_crons(d)
        (d / 'cron.current').write_text('\n'.join(old.values()) + '\n')
        self.run_shell(d, self.helpers(d, 'sb_cron_update', 'cronsb') + self.cron_stub() + '''
cronsb || fail first
cronsb || fail second
''')
        lines = (d / 'cron.current').read_text().splitlines()
        self.assertEqual(lines.count(old['restart'] + ' # sing-box-yg:restart'), 1)
        self.assertNotIn(old['restart'], lines)
        for kind in ['argo', 'subscription', 'warp']:
            self.assertIn(old[kind], lines)

    def test_cron_failures_preserve_existing_crontab_and_clean_temporary_files(self):
        d = self.sandbox()
        before = '0 * * * * curl http://example.org/sing-box-backup\n'
        (d / 'cron.current').write_text(before)
        self.run_shell(d, self.helpers(d, 'sb_cron_update') + self.cron_stub() + '''
CRON_READ_FAIL=1
if sb_cron_update all; then fail read-failure-hidden; fi
[[ ! -e cron.writes ]] || fail wrote-after-read-failure
CRON_READ_FAIL=0; CRON_WRITE_FAIL=1
if sb_cron_update argo '@reboot true'; then fail write-failure-hidden; fi
''')
        self.assertEqual((d / 'cron.current').read_text(), before)
        self.assertFalse(list(d.glob('sbox-cron.*')))

    def test_cron_initializes_absent_user_crontab(self):
        d = self.sandbox()
        self.run_shell(d, self.helpers(d, 'sb_cron_update') + self.cron_stub() + '''
CRON_ABSENT=1
sb_cron_update restart '0 1 * * * true' || fail initialize
''')
        self.assertEqual((d / 'cron.current').read_text(), '0 1 * * * true # sing-box-yg:restart\n')

    def test_temporary_stop_matches_only_project_executable_and_stops_each_pid(self):
        d = self.sandbox()
        p = bashpath(d / 'project')
        processes = '\n'.join([
            '101 ' + p + '/cloudflared tunnel --url http://localhost:2052 --protocol http2',
            '102 ' + p + '/cloudflared tunnel --url http://localhost:2053 --protocol http2',
            '201 /opt/other/cloudflared tunnel --url http://localhost:2052',
            '202 ' + p + '/cloudflared tunnel run --token TEST_ONLY',
            '203 ' + p + '/xhttp-argo/cloudflared tunnel run --token-file test',
            '204 python app.py http://localhost:2052',
        ])
        (d / 'processes').write_text(processes + '\n')
        self.run_shell(d, self.helpers(d, 'argo_temporary_stop') + '''
ps() { cat processes; }
kill() { printf '%s\n' "$*" >> kills; return 0; }
argo_temporary_stop || fail stop
''')
        self.assertEqual((d / 'kills').read_text().splitlines(), ['-TERM 101', '-TERM 102'])

    def test_temporary_stop_propagates_process_and_signal_failures(self):
        d = self.sandbox()
        p = bashpath(d / 'project')
        self.run_shell(d, self.helpers(d, 'argo_temporary_stop') + '''
ps() { return 1; }
kill() { fail unexpected-kill; }
if argo_temporary_stop; then fail ps-failure-hidden; fi
ps() { printf '%s\n' '101 PROJECT/cloudflared tunnel --url http://localhost:2052'; }
kill() { [[ $1 == -0 ]]; }
if argo_temporary_stop; then fail signal-failure-hidden; fi
'''.replace('PROJECT', p))

    def systemd_stub(self):
        return r'''
pidof() { [[ $1 == systemd ]]; }
systemctl() {
 printf '%s\n' "$*" >> services.log
 case $1 in
  restart) [[ ${RESTART_FAIL:-0} != 1 ]] ;;
  is-active|is-enabled) return 0 ;;
  *) return 0 ;;
 esac
}
kill() { fail unexpected-real-process-selection; }
'''

    def test_fixed_reset_restarts_only_argo_and_does_not_call_kill(self):
        d = self.sandbox()
        (d / 'units/argo.service').write_text('old service')
        self.run_shell(d, self.helpers(d, 'argo_fixed_backend', 'argo_fixed_apply') + self.systemd_stub() + '''
argo_fixed_apply TEST_ONLY_TOKEN fixed.example.org || fail fixed-reset
''')
        calls = (d / 'services.log').read_text().splitlines()
        self.assertIn('restart argo', calls)
        self.assertNotIn('start argo', calls)
        self.assertTrue(all(line.endswith('argo') or line == 'daemon-reload' for line in calls))
        self.assertEqual((d / 'project/sbargoym.log').read_text(), 'fixed.example.org\n')

    def test_fixed_reset_failure_restores_unit_and_settings(self):
        d = self.sandbox()
        originals = {'units/argo.service': 'old service', 'project/sbargoym.log': 'old.example.org\n',
                     'project/sbargotoken.log': 'OLD_TEST_TOKEN\n'}
        for path, text in originals.items():
            (d / path).write_text(text)
        record = self.run_shell(d, self.helpers(d, 'argo_fixed_backend', 'argo_fixed_apply') + self.systemd_stub() + '''
RESTART_FAIL=1
if argo_fixed_apply NEW_TEST_TOKEN new.example.org; then fail reset-failure-hidden; fi
''')
        for path, text in originals.items():
            self.assertEqual((d / path).read_text(), text)
        self.assertNotIn('NEW_TEST_TOKEN', record['stdout'] + record['stderr'])

    def test_fixed_first_deployment_failure_removes_new_unit_and_settings(self):
        d = self.sandbox()
        self.run_shell(d, self.helpers(d, 'argo_fixed_backend', 'argo_fixed_apply') + self.systemd_stub() + '''
RESTART_FAIL=1
if argo_fixed_apply NEW_TEST_TOKEN new.example.org; then fail first-deployment-failure-hidden; fi
[[ ! -e units/argo.service && ! -e project/sbargoym.log && ! -e project/sbargotoken.log ]] || fail residual-new-settings
''')

    def test_stopping_either_tunnel_keeps_shared_binary_and_other_tunnel(self):
        d = self.sandbox()
        (d / 'project/cloudflared').write_text('shared binary')
        (d / 'units/argo.service').write_text('fixed service')
        (d / 'cron.current').write_text(self.legacy_crons(d)['argo'] + '\n')
        self.run_shell(d, self.helpers(d, 'sb_cron_update', 'argo_fixed_backend', 'argo_fixed_stop', 'argo_temporary_stop', 'cfargo')
                       + self.cron_stub() + self.systemd_stub() + '''
argo_fixed_stop || fail fixed-stop
[[ -f project/cloudflared && -s cron.current ]] || fail damaged-temporary-tunnel
printf fixed > units/argo.service
readp() { menu=2; }
ps() { :; }
sbshare() { return 0; }
cfargo || fail temporary-stop
[[ -f project/cloudflared && -f units/argo.service ]] || fail damaged-fixed-tunnel
''')
        self.assertEqual((d / 'project/cloudflared').read_text(), 'shared binary')
        self.assertEqual((d / 'cron.current').read_text(), '')

    def firewall_stub(self):
        return r'''
fw() {
 local binary=$1; shift
 if [[ $3 == -S ]]; then
  [[ ${FW_READ_FAIL:-0} != 1 ]] || return 1
  cat "$binary.rules"
 elif [[ $3 == -D ]]; then
  printf '%s %s\n' "$binary" "$*" >> firewall.calls
  [[ ${FW_DELETE_FAIL:-0} != 1 ]] || return 1
  shift 2
  local expected="$*"
  expected=${expected/#-D /-A }
  awk -v expected="$expected" '{ original=$0; gsub(/"/,"",$0); if($0!=expected) print original }' "$binary.rules" > "$binary.new" && mv "$binary.new" "$binary.rules"
 else fail unsafe-firewall-operation
 fi
}
iptables() { fw iptables "$@"; }
ip6tables() { fw ip6tables "$@"; }
jq() { printf '%s\n' 55312 39034; }
'''

    def firewall_fixtures(self, d):
        own = [
            '-A PREROUTING -p udp -m udp --dport 50000:50100 -j DNAT --to-destination :55312',
            '-A PREROUTING -p udp --dport 50200 -j DNAT --to-destination :39034',
            '-A PREROUTING -p udp -m udp --dport 50300 -m comment --comment "sing-box-yg:port-hop" -j DNAT --to-destination :11111',
        ]
        keep = [
            '-A PREROUTING -p tcp --dport 50000 -j DNAT --to-destination :55312',
            '-A PREROUTING -p udp --dport 50400 -j DNAT --to-destination :9999',
            '-A PREROUTING -s 192.0.2.1/32 -p udp --dport 50500 -j DNAT --to-destination :55312',
            '-A PREROUTING -p udp --dport 50600 -m comment --comment "another-project" -j DNAT --to-destination :55312',
            '-A PREROUTING -p udp --dport 50700 -j REDIRECT --to-ports 55312',
        ]
        for binary in ['iptables', 'ip6tables']:
            (d / (binary + '.rules')).write_text('\n'.join(own + keep) + '\n', newline='\n')
        (d / 'project/sb.json').write_text('{}')
        return own, keep

    def test_nat_uninstall_preserves_unrelated_rules_and_removes_old_and_marked_ipv4_ipv6(self):
        d = self.sandbox()
        own, keep = self.firewall_fixtures(d)
        self.run_shell(d, self.helpers(d, 'sb_port_hop_rule_match', 'sb_port_hop_manage') + self.firewall_stub() + '''
sb_port_hop_manage remove || fail cleanup
''')
        for binary in ['iptables', 'ip6tables']:
            self.assertEqual((d / (binary + '.rules')).read_text().splitlines(), keep)
        calls = (d / 'firewall.calls').read_text()
        self.assertNotIn(' -F ', calls)
        self.assertEqual(len(calls.splitlines()), len(own) * 2)

    def test_nat_specific_port_cleanup_and_list_do_not_remove_other_protocol(self):
        d = self.sandbox()
        own, keep = self.firewall_fixtures(d)
        self.run_shell(d, self.helpers(d, 'sb_port_hop_rule_match', 'sb_port_hop_manage') + self.firewall_stub() + '''
ports=$(sb_port_hop_manage list 55312) || fail list
[[ $ports == 50000:50100 ]] || fail wrong-port-list
sb_port_hop_manage remove 55312 || fail remove
''')
        for binary in ['iptables', 'ip6tables']:
            self.assertEqual((d / (binary + '.rules')).read_text().splitlines(), own[1:] + keep)

    def test_nat_failures_are_not_reported_as_success(self):
        d = self.sandbox()
        own, keep = self.firewall_fixtures(d)
        self.run_shell(d, self.helpers(d, 'sb_port_hop_rule_match', 'sb_port_hop_manage') + self.firewall_stub() + '''
FW_READ_FAIL=1
if sb_port_hop_manage remove; then fail listing-failure-hidden; fi
[[ ! -e firewall.calls ]] || fail deleted-after-read-failure
FW_READ_FAIL=0; FW_DELETE_FAIL=1
if sb_port_hop_manage remove; then fail delete-failure-hidden; fi
''')
        for binary in ['iptables', 'ip6tables']:
            self.assertEqual((d / (binary + '.rules')).read_text().splitlines(), own + keep)

    def uninstall_stubs(self):
        return r'''
command() { if [[ $1 == -v && $2 == apk ]]; then return 1; else builtin command "$@"; fi; }
ps() { :; }; pgrep() { return 1; }; xargs() { :; }
kill() { printf '%s\n' "$*" >> process.calls; return 0; }
systemctl() { printf '%s\n' "$*" >> services.log; return 0; }
service() { :; }; netfilter-persistent() { :; }
'''

    def test_complete_uninstall_keeps_unrelated_nat_and_cron_in_sandbox(self):
        d = self.sandbox()
        own, keep = self.firewall_fixtures(d)
        (d / 'cron.current').write_text(self.legacy_crons(d)['argo'] + '\n0 * * * * curl http://example.org/sing-box-backup\n')
        self.run_shell(d, self.helpers(d, 'sb_cron_update', 'uncronsb', 'argo_temporary_stop',
                                      'sb_port_hop_rule_match', 'sb_port_hop_manage', 'unins')
                       + self.firewall_stub() + self.cron_stub() + self.uninstall_stubs() + '''
unins || fail uninstall
[[ ! -e project ]] || fail installation-not-removed
''')
        self.assertEqual((d / 'cron.current').read_text(), '0 * * * * curl http://example.org/sing-box-backup\n')
        for binary in ['iptables', 'ip6tables']:
            self.assertEqual((d / (binary + '.rules')).read_text().splitlines(), keep)

    def test_complete_uninstall_aborts_on_nat_cleanup_failure(self):
        d = self.sandbox()
        own, keep = self.firewall_fixtures(d)
        before = (d / 'project/sb.json').read_bytes()
        (d / 'cron.current').write_text('0 * * * * true\n')
        self.run_shell(d, self.helpers(d, 'sb_cron_update', 'uncronsb', 'argo_temporary_stop',
                                      'sb_port_hop_rule_match', 'sb_port_hop_manage', 'unins')
                       + self.firewall_stub() + self.cron_stub() + self.uninstall_stubs() + '''
FW_READ_FAIL=1
if unins; then fail uninstall-failure-hidden; fi
[[ ! -e services.log && ! -e cron.writes ]] || fail modified-after-nat-read-failure
''')
        self.assertEqual((d / 'project/sb.json').read_bytes(), before)
        for binary in ['iptables', 'ip6tables']:
            self.assertEqual((d / (binary + '.rules')).read_text().splitlines(), own + keep)

    def test_uninstall_inspects_nat_and_cron_before_deleting_configuration(self):
        # Inspect actual integration in addition to executing each cleanup helper.
        body = function(self.source, 'unins')
        self.assertLess(body.index('sb_port_hop_manage remove'), body.index('rm -rf /etc/s-box'))
        self.assertLess(body.index('uncronsb || return 1'), body.index('rm -rf /etc/s-box'))
        self.assertNotIn('-F PREROUTING', body)
        self.assertNotIn('/tmp/crontab.tmp', self.source)
        self.assertIn('--comment sing-box-yg:port-hop', function(self.source, 'changeport'))


if __name__ == '__main__':
    unittest.main()
