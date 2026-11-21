"""Full parsed-output equivalence against the saved pre-refactor renderer."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import yaml
from config_harness import ROOT, RECORDS, function, generate_vps, check, save_records, bashpath, shell, run


class ClientTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = (ROOT / 'review-artifacts/2026-11-21/refactor/before/sb.sh').read_text(encoding='utf8')
        cls.after = Path(os.environ.get('SB_UNDER_TEST', ROOT / 'sb.sh')).read_text(encoding='utf8')
        cls.out = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='client-template-'))) / 'client-templates'
        cls.out.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        save_records(cls.out / 'commands.json')

    def compare(self, argo, version, hopping=False, named=False, sidecars=False):
        d = self.out / f'{argo}-{version}-{hopping}-{named}-{sidecars}'
        if sidecars:
            (d/'xhttp').mkdir(parents=True,exist_ok=True);(d/'xhttp-argo').mkdir(exist_ok=True)
            (d/'server_ipcl.log').write_text('192.0.2.1\n')
            src=self.before.replace('/etc/s-box',bashpath(d))
            helpers=''.join(function(src,n) for n in ['xhttp_server_config','xhttp_argo_server_config'])
            shell(helpers+'''
xhttp_server_config xhttp 18443 www.cloudflare.com 11111111-2222-3333-4444-555555555555 eC9YOSPvhGUHAU1KLrr0X3GBiiYubH1zubnb_yxyylQ aabbccdd /test-path
printf '%s\\n' 5XaAecMR7oqsy_0v-N7ZqYeepf-gPOJkncIsxN-NIgs > xhttp/public.key
printf '%s\\n' xhttp.example.org > xhttp-argo/domain
printf '%s\\n' mlkem768x25519plus.native.0rtt.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA > xhttp-argo/encryption.key
xhttp_argo_server_config xhttp-argo 18080 22222222-3333-4444-5555-666666666666 /test/ mlkem768x25519plus.native.300s.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
''',d)
        kw = dict(version=version, argo=argo, hopping=hopping,
                  prefix='RN 美国 # |' if named else None, suffix='测试 VPS | 后缀' if named else None)
        generate_vps(self.before, d, **kw)
        old = (json.loads((d/'sbox.json').read_text(encoding='utf8')), yaml.safe_load((d/'clmi.yaml').read_text(encoding='utf8')))
        generate_vps(self.after, d, **kw)
        new = (json.loads((d/'sbox.json').read_text(encoding='utf8')), yaml.safe_load((d/'clmi.yaml').read_text(encoding='utf8')))
        self.assertEqual(old, new)
        self.assertEqual(check('1.14.4', d/'sbox.json').returncode, 0, RECORDS[-1])
        if os.environ.get('MIHOMO_TEST_BIN'):
            # Test proxies/groups without downloading changing remote GeoIP/GeoSite data.
            cfg=new[1].copy();cfg['rules']=['MATCH,🌍选择代理节点'];cfg['external-controller']=''
            (d/'check.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf8')
            p=run([os.environ['MIHOMO_TEST_BIN'],'-t','-d',d,'-f',d/'check.yaml'],timeout=60)
            self.assertEqual(p.returncode,0,RECORDS[-1])

    def test_branch_matrix(self):
        for argo in ['none','fixed','temporary','both']:
            for version in ['1.10','1.14']:
                with self.subTest(argo=argo,version=version): self.compare(argo,version)

    def test_names_and_hopping(self):
        for argo in ['none','fixed','temporary','both']:
            with self.subTest(argo=argo): self.compare(argo,'1.14',True,True)

    def test_base_templates_unchanged_and_redundancy_removed(self):
        for n in ['sball','clall']:
            self.assertEqual(function(self.before,n),function(self.after,n))
        self.assertLess(len(function(self.after,'sb_client').splitlines()),700)

    def test_both_sidecars_all_argo_modes(self):
        for argo in ['none','fixed','temporary','both']:
            with self.subTest(argo=argo): self.compare(argo,'1.14',True,True,True)


if __name__ == '__main__': unittest.main()
