"""Menu cache clocks/network mocked; no production files or external requests."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from config_harness import ROOT, CORE_ROOT, JQ, BASH, bashpath, function


class MenuCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=Path(os.environ.get('SB_UNDER_TEST',ROOT/'sb.sh')).read_text(encoding='utf8')
        cls.out=Path(os.environ.get('SB_TEST_OUTPUT',tempfile.mkdtemp(prefix='menu-cache-')))/'menu-cache'
        cls.out.mkdir(parents=True,exist_ok=True);cls.records=[]
    @classmethod
    def tearDownClass(cls):
        (cls.out/'commands.json').write_text(json.dumps(cls.records,ensure_ascii=False,indent=2),encoding='utf8')
    def run_case(self,name,body):
        d=self.out/name;d.mkdir(exist_ok=True);src=self.src.replace('/etc/s-box',bashpath(d))
        helpers=''.join(function(src,n) for n in ['sb_info_valid','sb_info_cache_get','sb_info_cache_put','sb_script_version_info','v4v6','lapre','sb_menu_ip_probe_hint'])
        jq='"'+bashpath(JQ or CORE_ROOT/'jq.exe')+'" -b' if os.name=='nt' else 'command jq'
        script='set +e\n'+helpers+r'''
red(){ echo "$*" >&2; }
jq(){ __JQ__ "$@"; }
date(){ echo "${NOW:-1000}"; }
curl(){
printf '%s\n' "$*" >> calls
[[ ${FAIL:-0} != 1 ]] || return 28
case "$*" in
*icanhazip*) if [[ $* == *-fsS4* ]]; then echo 192.0.2.1; else echo 2001:db8::1; fi ;;
*ip.fm*) echo 'Location: United States, California' ;;
*data.jsdelivr*) echo '{"versions":["1.15.0-alpha.13","1.14.4"]}' ;;
*raw.githubusercontent*) printf 'v26.11.21-fork.16更新内容：\nMock notes\n' ;;
*) return 22 ;;
esac
}
'''.replace('__JQ__',jq)+body
        f=d/'run.sh';f.write_text(script,encoding='utf8',newline='\n');cmd=[BASH,bashpath(f)];p=subprocess.run(cmd,cwd=d,capture_output=True,timeout=30)
        self.records.append(dict(command=cmd,cwd=str(d),input=script,exit_code=p.returncode,stdout=p.stdout.decode('utf8','replace'),stderr=p.stderr.decode('utf8','replace')))
        self.assertEqual(p.returncode,0,self.records[-1]);return d
    def test_warm_network_uses_no_new_requests(self):
        self.run_case('warm-network',r'''
v4v6 || exit 1
[[ $v4 == 192.0.2.1 && $v6 == 2001:db8::1 ]] || exit 2
v4v6 || exit 3
[[ $(wc -l < calls) == 4 ]] || exit 4
''')
    def test_network_expiry_and_force_refresh(self):
        self.run_case('force',r'''
v4v6; NOW=1060; v4v6; v4v6 refresh
[[ $(wc -l < calls) == 12 ]] || exit 1
''')
    def test_failure_not_cached_or_reported_as_previous(self):
        self.run_case('fail',r'''
v4v6; NOW=1200; FAIL=1; v4v6
[[ -z $v4 && -z $v6 ]] || exit 1
FAIL=0;v4v6
[[ $(wc -l < calls) == 12 ]] || exit 2
''')
    def test_ipv4_only_network_does_not_print_ipv6_probe_errors(self):
        self.run_case('ipv4-only', r'''
curl(){
case "$*" in
*-fsS6*) echo 'curl: (7) Failed to connect' >&2; return 7 ;;
*icanhazip*) echo 192.0.2.1 ;;
*ip.fm*) echo 'Location: South Korea' ;;
esac
}
v4v6 || exit 1
[[ $v4 == 192.0.2.1 && $v4dq == 'South Korea' && -z $v6 && -z $v6dq ]] || exit 2
[[ ! -e cache/menu-network.json ]] || exit 3
''')
        self.assertEqual(self.records[-1]['stderr'], '')

    def test_ip_probe_hint_reports_missing_route_only_when_confirmed(self):
        self.run_case('probe-hint', r'''
ip(){ [[ $* == '-6 route show table all default' ]]; }
[[ $(sb_menu_ip_probe_hint 6) == *'没有 IPv6 默认路由'* ]] || exit 1
[[ $(sb_menu_ip_probe_hint 4) == *'请检查对应的出站网络、DNS 或探测站点'* ]] || exit 2
ip(){ echo 'default via fe80::1 dev eth0'; }
[[ $(sb_menu_ip_probe_hint 6) == *'请检查对应的出站网络、DNS 或探测站点'* ]] || exit 3
''')

    def test_versions_cached_but_installed_version_is_live(self):
        self.run_case('cores',r'''
printf '#!/bin/bash\necho "sing-box version 1.14.3"\n' > sing-box;chmod +x sing-box
lapre
[[ $latcore == 1.14.4 && $precore == 1.15.0-alpha.13 && $inscore == 1.14.3 ]] || exit 1
printf '#!/bin/bash\necho "sing-box version 1.14.4"\n' > sing-box
lapre
[[ $inscore == 1.14.4 && $(wc -l < calls) == 1 ]] || exit 2
lapre refresh
[[ $(wc -l < calls) == 2 ]] || exit 3
''')
    def test_script_cache_expiry(self):
        self.run_case('script',r'''
sb_script_version_info > first;sb_script_version_info > second;cmp first second || exit 1
[[ $(wc -l < calls) == 1 ]] || exit 2
NOW=1300;sb_script_version_info >/dev/null
[[ $(wc -l < calls) == 2 ]] || exit 3
''')
    def test_corrupt_or_future_cache_refetched_without_execution(self):
        self.run_case('corrupt',r'''
mkdir -p cache;printf '%s' '{"saved":999999,"data":{"ipv4":"$(touch PWNED)"}}' > cache/menu-network.json
v4v6 || exit 1
[[ ! -f PWNED && $v4 == 192.0.2.1 ]] || exit 2
''')
    def test_update_downloads_do_not_use_menu_cache(self):
        for n in ['lnsb','sb_update_core_stage','sb_update_download']:
            self.assertNotIn('sb_info_cache',function(self.src,n))
        self.assertIn('lapre refresh',function(self.src,'upsbcroe'))

    def test_network_requests_overlap(self):
        self.run_case('parallel',r'''
curl(){
local marker
case "$*" in *icanhazip*) marker=ip;; *) marker=geo;; esac
[[ $* != *-fsS4* ]] || marker=${marker}4
[[ $* != *-fsS6* ]] || marker=${marker}6
touch "started-$marker"
local i
for i in {1..100}; do [[ $(find . -maxdepth 1 -name 'started-*' | wc -l) == 4 ]] && break; sleep .01; done
[[ $(find . -maxdepth 1 -name 'started-*' | wc -l) == 4 ]] || return 28
case "$marker" in ip4) echo 192.0.2.1;;ip6) echo 2001:db8::1;;*) echo 'Location: test';;esac
}
v4v6 || exit 1
[[ -n $v4 && -n $v6 && -s cache/menu-network.json ]] || exit 2
''')

    def test_expired_script_cache_not_presented_as_current_on_error(self):
        self.run_case('stale-script',r'''
sb_script_version_info > first
NOW=2000;FAIL=1
if sb_script_version_info > second; then exit 1; fi
[[ ! -s second ]] || exit 2
''')


if __name__=='__main__':unittest.main()
