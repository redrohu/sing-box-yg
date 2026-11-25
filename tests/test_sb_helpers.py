"""Shared sb.sh helpers: port checks, inbound field reads and WARP-plus helper names (local mocks only)."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from config_harness import ROOT, bashpath, function, shell

SS_OUTPUT = r'''
ss() { cat <<'SS_EOF'
Netid State  Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
udp   UNCONN 0      0      0.0.0.0:443         0.0.0.0:*
tcp   LISTEN 0      4096   [::]:8443           [::]:*
tcp   LISTEN 0      4096   127.0.0.1:18080     0.0.0.0:*
tcp   LISTEN 0      4096   0.0.0.0%lo:53       0.0.0.0:*
tcp   LISTEN 0      4096   0.0.0.0:40000       0.0.0.0:*
SS_EOF
}
'''

# Functions whose inline `sed | jq '.inbounds[N]...'` reads were migrated to sb_inbound_get.
MIGRATED = ['changeym', 'allports', 'tu5deports', 'changeuuid', 'subtokenipsub',
            'cfargoym', 'cfargo', 'cfargo_ym', 'showprotocol']
OLD_READ = re.compile(r"sed 's://\.\*::g' /etc/s-box/sb\.json \| jq -r '\.inbounds\[\d\]")


class SbHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.tmp = Path(tempfile.mkdtemp(prefix='sb-helpers-'))

    def helpers(self, d, *names):
        src = self.source.replace('/etc/s-box', bashpath(d)).replace('/etc/local.d', bashpath(d / 'local.d'))
        return ''.join(function(src, n) for n in names)

    def run_sh(self, name, body, *names):
        d = self.tmp / name
        d.mkdir(parents=True, exist_ok=True)
        return shell(self.helpers(d, *names) + body, d), d

    def test_port_valid(self):
        self.run_sh('port-valid', r'''
for p in 1 443 8443 65535; do sb_port_valid "$p" || { echo "rejected $p"; exit 1; }; done
for p in "" 0 0443 65536 99999 44a -1 " 443" 1e3; do
  if sb_port_valid "$p"; then echo "accepted $p"; exit 1; fi
done
''', 'sb_port_valid')

    def test_port_in_use_matches_whole_port_and_protocol(self):
        self.run_sh('port-in-use', SS_OUTPUT + r'''
sb_port_in_use 443; sb_port_in_use 443 udp
if sb_port_in_use 443 tcp; then exit 1; fi
sb_port_in_use 8443 tcp; sb_port_in_use 18080; sb_port_in_use 53
for p in 44 844 84433 1808 20000; do if sb_port_in_use "$p"; then echo "false match $p"; exit 1; fi; done
''', 'sb_port_in_use')

    def test_chooseport_rerolls_random_and_validates_input(self):
        # Note: under set -e only the last command of an && list aborts, so each assertion is its own command.
        self.run_sh('chooseport', SS_OUTPUT + r'''
yellow() { printf '%s\n' "$1" >> messages; }; blue() { :; }; sleep() { :; }
inputs=()
readp() { printf -v "$2" '%s' "${inputs[0]}"; inputs=("${inputs[@]:1}"); echo read >> reads; }
# shuf runs inside $(...): keep its counter in a file, not a shell variable.
rolls=(443 8443 20000)
shuf() { local n; n=$(cat rolls.n 2>/dev/null || echo 0); echo $((n + 1)) > rolls.n; echo "${rolls[$n]}"; }
# Random port: occupied values are re-rolled without prompting the user.
port=
chooseport
[ "$port" = 20000 ]
[ ! -e reads ]
# Fallback port in use, then invalid entries, then a free port.
port=; inputs=(abc 0443 40001)
chooseport 40000
[ "$port" = 40001 ]
[ "$(wc -l < reads)" -eq 3 ]
[ "$(grep -c '端口被占用' messages)" -eq 1 ]
[ "$(grep -c '端口无效' messages)" -eq 2 ]
# Explicit free port is accepted unchanged.
rm -f reads; port=30000; chooseport
[ "$port" = 30000 ]
[ ! -e reads ]
''', 'sb_port_valid', 'sb_port_in_use', 'chooseport')

    def write_json(self, d, name, data):
        (d / name).write_text(json.dumps(data), encoding='utf8')

    def test_inbound_get_prefers_tag_then_index_and_reads_valid_json_as_is(self):
        d = self.tmp / 'inbound'
        d.mkdir(parents=True, exist_ok=True)
        # Tagged inbounds in a non-default order; a URL with // must not be truncated.
        self.write_json(d, 'tagged.json', {'route': {'rule_set': [{'url': 'https://example.org/x.srs'}]}, 'inbounds': [
            {'tag': 'vmess-sb', 'type': 'vmess', 'listen_port': 21443, 'transport': {'path': '/vm'}},
            {'tag': 'vless-sb', 'type': 'vless', 'listen_port': 11443, 'users': [{'uuid': 'U-1'}],
             'tls': {'server_name': 'www.apple.com', 'reality': {'handshake': {'server': 'www.apple.com'}}}},
            {'tag': 'hy2-sb', 'type': 'hysteria2', 'listen_port': 31443, 'tls': {'key_path': '/k/hy2'}},
            {'tag': 'tuic5-sb', 'type': 'tuic', 'listen_port': 41443}]})
        # Legacy untagged file: index order.
        self.write_json(d, 'legacy.json', {'inbounds': [
            {'listen_port': 1}, {'listen_port': 2, 'tls': {'enabled': True}}, {'listen_port': 3}, {'listen_port': 4}, {'listen_port': 5}]})
        # Legacy file with // comments: only this case uses comment stripping.
        (d / 'commented.json').write_text('{\n"inbounds": [ // comment\n{"tag": "vless-sb", "listen_port": 7} // x\n]\n}\n', encoding='utf8')
        shell(self.helpers(d, 'sb_inbound_get') + r'''
use() { cp "$1" sb.json; }
use tagged.json
[ "$(sb_inbound_get vless .listen_port)" = 11443 ]
[ "$(sb_inbound_get vless .users[0].uuid)" = U-1 ]
[ "$(sb_inbound_get vless .tls.reality.handshake.server)" = www.apple.com ]
[ "$(sb_inbound_get vmess .transport.path)" = /vm ]
[ "$(sb_inbound_get hy2 .tls.key_path)" = /k/hy2 ]
[ "$(sb_inbound_get tuic5 .listen_port)" = 41443 ]
[ "$(sb_inbound_get anytls .listen_port)" = null ]
use legacy.json
[ "$(sb_inbound_get vmess .tls.enabled)" = true ]
[ "$(sb_inbound_get anytls .listen_port)" = 5 ]
use commented.json
[ "$(sb_inbound_get vless .listen_port)" = 7 ]
use tagged.json
for bad in "vless .listen_port|del(.)" "vless listen_port" "vless .a;b" "trojan .listen_port"; do
  set -- $bad
  rc=0; out=$(sb_inbound_get "$1" "$2") || rc=$?
  [ "$rc" -eq 2 ] && [ -z "$out" ] || { echo "accepted $bad"; exit 1; }
done
''', d)

    def test_old_patterns_removed_from_migrated_code(self):
        self.assertNotIn('ss -tunlp | grep -w', self.source)
        for name in MIGRATED:
            body = function(self.source, name)
            for line in body.splitlines():
                if OLD_READ.search(line):
                    # Only comments and boot-time command text (run without this script's functions) remain.
                    self.assertTrue(line.lstrip().startswith('#') or (name == 'cfargo' and 'cloudflared tunnel --url' in line),
                                    (name, line))
        self.assertIn('sb_inbound_get vmess .listen_port', function(self.source, 'cfargoym'))

    def test_warp_plus_helpers_do_not_replace_global_uninstaller(self):
        self.assertEqual(len(re.findall(r'(?m)^unins\(\)\s*\{', self.source)), 1)
        self.assertEqual(len(re.findall(r'(?m)^ins\(\)\s*\{', self.source)), 0)
        self.assertIn('sb_port_hop_manage remove', function(self.source, 'unins'))
        body = function(self.source, 'inssbwpph')
        self.assertNotRegex(body, r'\bunins\b')
        self.assertIn('chooseport 40000', function(self.source, 'sbwpph_prepare'))
        self.run_sh('sbwpph-stop', r'''
unins() { echo GLOBAL-UNINSTALLER; }
sbactive() { :; }; ps() { :; }; xargs() { :; }; echo() { :; }
yellow() { :; }; green() { printf '%s\n' "$1" > stopped; }
sb_cron_update() { printf '%s\n' "$*" >> cron.calls; }
readp() { printf -v "$2" '%s' 3; }
: > sbwpph.log
inssbwpph
[ ! -e sbwpph.log ]
grep -qx warp cron.calls
grep -q '已停止' stopped
unset -f echo
[ "$(unins)" = GLOBAL-UNINSTALLER ]
''', 'sbwpph_pids', 'sbwpph_kill', 'sbwpph_stop', 'inssbwpph')

    def test_jq_as_binding_never_follows_a_binary_operator(self):
        # jq 1.8 parses "A and B as $x | C" as "(A and B) as $x | C"; jq <= 1.7 as "A and (B as $x | C)".
        # Such bindings must be parenthesized so both versions agree (xhttp_argo_address_valid broke on 1.8).
        op = re.compile(r'(\band|\bor|==|!=|<=|>=|[<>+\-*/,])\s*$')
        for name in ('sb.sh', 'serv00.sh', 'serv00keep.sh', 'kp.sh'):
            lines = (ROOT / name).read_text(encoding='utf8').split('\n')
            for i, line in enumerate(lines):
                if line.lstrip().startswith('#'):
                    continue
                for m in re.finditer(r'\bas \$[A-Za-z_]\w*\s*\|', line):
                    before = line[:m.start()].rstrip()
                    if before.endswith(')'):
                        depth, j = 0, len(before)
                        while j > 0:
                            c = before[j - 1]
                            j -= 1
                            if c == ')':
                                depth += 1
                            elif c == '(':
                                depth -= 1
                                if depth == 0:
                                    break
                        prefix = before[:j]
                    else:
                        prefix = re.sub(r'\S+$', '', before)
                    k = i
                    while not prefix.strip() and k > 0:
                        k -= 1
                        prefix = lines[k]
                    self.assertIsNone(op.search(prefix.rstrip()), f'{name}:{i + 1}: {line.strip()}')

    def test_return_to_main_menu_replaces_process(self):
        # A fake `sb` command on PATH stands in for /usr/bin/sb; the real menu is never run.
        same_pid = '' if os.name == 'nt' else '[ "$(sed -n "s/^MENU //p" out)" = "$(sed -n "s/^PARENT //p" out)" ]'
        body = function(self.source, 'sb')
        self.assertIn('exec "$menu_cmd"', body)
        self.assertIn('type -P sb', body)
        self.run_sh('menu-return', f"""
mkdir -p bin empty
printf '%s\\n' '#!/bin/bash' 'echo "MENU $$"' > bin/sb
chmod +x bin/sb
cat > scenario.sh <<'SCENARIO_EOF'
red() {{ printf '%s\\n' "$1"; }}
{body}
submenu() {{ echo SUBMENU; sb; echo AFTER-SUBMENU; }}
echo "PARENT $$"
submenu
echo AFTER
SCENARIO_EOF
PATH="$PWD/bin:$PATH" bash scenario.sh > out
grep -qx SUBMENU out
grep -q '^MENU ' out
if grep -q AFTER out; then echo 'code after the menu call still ran'; exit 1; fi
{same_pid}
# Without an installed sb command: clear message and non-zero exit, nothing after it runs.
rc=0; PATH="$PWD/empty" "$BASH" scenario.sh > missing || rc=$?
[ "$rc" -eq 1 ]
grep -q '未找到sb快捷命令' missing
if grep -q -e AFTER -e '^MENU ' missing; then exit 1; fi
""")

    def test_menu_return_definition_and_call_sites(self):
        src = self.source
        self.assertEqual(len(re.findall(r'(?m)^sb\(\)\s*\{', src)), 1)
        first_call = re.search(r'(?m)(&& sb$|^sb$)', src)
        self.assertLess(src.index('\nsb(){'), first_call.start())
        # Menu returns go through the function; only boot-time strings run the command directly.
        for line in src.splitlines():
            if 'bash /usr/bin/sb' in line:
                self.assertTrue('printf "9\\n1\\n"' in line or "printf \\\"9\\n1\\n\\\"" in line, line)
        # exec skips EXIT traps: every EXIT trap must live inside a ( ... ) subshell function.
        lines = src.splitlines()
        closing = 0
        for i, line in enumerate(lines):
            # The line that ends a trap string with EXIT (one-line or multi-line trap).
            if re.search(r"'\s*EXIT\s*$", line) and not line.lstrip().startswith('#'):
                closing += 1
                opening = max(j for j in range(i + 1) if re.match(r"^\s*trap '", lines[j]))
                start = max(j for j in range(opening + 1) if re.match(r'^[A-Za-z_]\w*\(\)\s*\{', lines[j]))
                head = '\n'.join(lines[start:opening])
                self.assertRegex(head, r'(?m)^\s*(if ! )?\(\s*$', (lines[start], line))
        self.assertGreaterEqual(closing, 12)


if __name__ == '__main__':
    unittest.main()
