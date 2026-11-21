"""Shared Xray preparation: mocked downloads, real digest, isolated files."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from config_harness import ROOT, BASH, bashpath, function


class XrayDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=Path(os.environ.get('SB_UNDER_TEST', ROOT/'sb.sh')).read_text(encoding='utf8')
        cls.out=Path(os.environ.get('SB_TEST_OUTPUT',tempfile.mkdtemp(prefix='xray-helper-')))/'xray-helper'
        cls.out.mkdir(parents=True,exist_ok=True);cls.records=[]
    @classmethod
    def tearDownClass(cls):
        (cls.out/'commands.json').write_text(json.dumps(cls.records,ensure_ascii=False,indent=2),encoding='utf8')
    def run_case(self,name,body,arch='x86_64',mode='success'):
        d=self.out/name;d.mkdir(exist_ok=True);(d/'stage').mkdir(exist_ok=True)
        (d/'payload').write_bytes(b'MOCK_ARCHIVE')
        (d/'digest').write_text('SHA2-256= '+hashlib.sha256(b'MOCK_ARCHIVE').hexdigest()+'\n')
        if mode=='bad_digest': (d/'digest').write_text('SHA2-256= '+'0'*64+'\n')
        script='set +e\n'+''.join(function(self.src,n) for n in ['xhttp_core_profile','xhttp_core_prepare'])+r'''
red(){ echo "$*" >&2; }
uname(){ echo ARCH; }
curl(){
printf '%s\n' "$*" >> calls
[[ MODE != timeout ]] || return 28
local out url; while (($#)); do case "$1" in -o) shift;out=$1;; https:*) url=$1;; esac;shift;done
if [[ $url == *.dgst ]]; then cp digest "$out"; else cp payload "$out";fi
}
unzip(){
[[ MODE != unzip_fail ]] || return 9
printf '#!/bin/bash\necho "Xray 26.11.9 (Xray, Penetrates Everything.)"\n' > stage/xray
}
'''.replace('ARCH',arch).replace('MODE',mode)+body
        f=d/'run.sh';f.write_text(script,encoding='utf8',newline='\n');cmd=[BASH,bashpath(f)];p=subprocess.run(cmd,cwd=d,capture_output=True,timeout=30)
        self.records.append(dict(command=cmd,cwd=str(d),input=script,exit_code=p.returncode,stdout=p.stdout.decode('utf8','replace'),stderr=p.stderr.decode('utf8','replace')));return d,p
    def test_architecture_matrix(self):
        for arch,label in [('x86_64','64'),('aarch64','arm64-v8a'),('armv7l','arm32-v7a')]:
            d,p=self.run_case(arch,'xhttp_core_prepare stage\n',arch)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('Xray-linux-'+label+'.zip',(d/'calls').read_text())
            self.assertEqual((d/'stage/version').read_text().strip(),'v26.11.9');self.assertFalse((d/'stage/core.zip').exists())
    def test_unsupported_arch_no_download(self):
        d,p=self.run_case('unsupported','xhttp_core_prepare stage\n','unknown')
        self.assertNotEqual(p.returncode,0);self.assertFalse((d/'calls').exists())
    def test_failures_do_not_mark_complete(self):
        for mode in ['timeout','bad_digest','unzip_fail']:
            d,p=self.run_case(mode,'xhttp_core_prepare stage\n',mode=mode)
            self.assertNotEqual(p.returncode,0);self.assertFalse((d/'stage/version').exists())
    def test_same_version_is_copied_without_network(self):
        d,p=self.run_case('reuse',r'''
printf '#!/bin/bash\necho "Xray 26.11.9 (Xray)"\n' > existing;chmod +x existing
xhttp_core_prepare stage "$PWD/existing" || exit 1
cmp existing stage/xray
''')
        self.assertEqual(p.returncode,0,p.stderr);self.assertFalse((d/'calls').exists());self.assertTrue((d/'existing').exists())
    def test_different_version_downloads(self):
        d,p=self.run_case('wrong-version',r'''
printf '#!/bin/bash\necho "Xray 26.11.8 (Xray)"\n' > existing;chmod +x existing
xhttp_core_prepare stage "$PWD/existing"
''')
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue((d/'calls').exists())
    def test_version_prefix_is_not_a_version_match(self):
        d,p=self.run_case('prefix-version',r'''
printf '#!/bin/bash\necho "Xray 26.11.90 (Xray)"\n' > existing;chmod +x existing
xhttp_core_prepare stage "$PWD/existing"
''')
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue((d/'calls').exists())
    def test_both_installers_use_helper_and_single_pin(self):
        self.assertEqual(self.src.count('xhttp_xray_version=v26.11.9'),1)
        for n in ['xhttp_install','xhttp_argo_install']:
            f=function(self.src,n);self.assertIn('xhttp_core_prepare "$stage"',f)
            self.assertNotIn('XTLS/Xray-core/releases/download',f)


if __name__=='__main__':unittest.main()
