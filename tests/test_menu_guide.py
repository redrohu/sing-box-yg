"""Guide coverage, deterministic generated output and offline artifact contracts."""
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

from config_harness import ROOT, function


class MenuGuide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = ROOT / 'docs'
        cls.data = json.loads((cls.docs / 'menu-guide.json').read_text(encoding='utf8'))
        cls.items = [i for s in cls.data['sections'] for g in s['groups'] for i in g['items']]
        cls.paths = {i['path'] for i in cls.items}
        # Parent menus are represented by group headings / descendant paths.
        cls.paths |= {'→'.join(p.split('→')[:n]) for p in list(cls.paths)
                      for n in range(1, len(p.split('→')))}
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')

    def test_all_main_platform_choices_covered(self):
        self.assertEqual(len(self.data['sections']), 7)
        self.assertGreaterEqual(len(self.items), 160)
        self.assertTrue({str(i) for i in range(17)} <= self.paths)
        self.assertTrue({'S→' + str(i) for i in range(10)} <= self.paths)

    def test_all_config_and_xhttp_choices_covered(self):
        for root, maximum in [('3', 11), ('3→10', 5), ('3→11', 9),
                              ('3→11→9', 8), ('3→11→9→8', 2), ('9', 3)]:
            for i in range(1, maximum + 1):
                self.assertIn(root + '→' + str(i), self.paths)
        for key in ['3→3→1→1', '3→3→1→2', '3→3→2→1', '3→3→2→2',
                    '4→4→1', '4→4→2→1', '4→4→2→2', '4→4→3']:
            self.assertIn(key, self.paths)

    def test_paths_match_local_dispatch(self):
        for helper, target in [('changeserv', 'xhttp_menu'), ('xhttp_menu', 'xhttp_argo_menu'),
                               ('xhttp_argo_menu', 'xhttp_argo_address_menu')]:
            self.assertIn(target, function(self.source, helper))
        menu = function((ROOT / 'serv00.sh').read_text(encoding='utf8'), 'menu')
        self.assertRegex(menu, r'7\) showsbclash')
        self.assertIn('3→11→9→8', (self.docs / 'MENU-GUIDE.md').read_text(encoding='utf8'))

    def test_generator_outputs_current(self):
        p = subprocess.run([sys.executable, str(self.docs / 'build_menu_guide.py'), '--check'],
                           cwd=ROOT, capture_output=True)
        self.assertEqual(p.returncode, 0, (p.stdout + p.stderr).decode('utf8', 'replace'))

    def test_only_three_requested_diagrams_remain(self):
        maps = self.docs / 'menu-maps'
        self.assertEqual({p.name for p in maps.iterdir()},
                         {'vps-actual-menu-full.svg', 'vps-actual-menu-overview.png'})
        self.assertEqual({p.name for p in self.docs.glob('*.xmind')}, {'MENU-ACTUAL-TREE.xmind'})
        root = ET.fromstring((maps / 'vps-actual-menu-full.svg').read_text(encoding='utf8'))
        self.assertGreater(int(root.attrib['height']), 1000)
        words = ''.join(root.itertext())
        for title in ['配置管理', '独立XHTTP', '【注意】', '【作用 / 说明】']:
            self.assertIn(title, words)
        raw = (maps / 'vps-actual-menu-overview.png').read_bytes()
        self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
        self.assertGreater(min(struct.unpack('>II', raw[16:24])), 1000)

    def test_all_local_document_links_resolve(self):
        for file in ['MENU-GUIDE.md', 'MENU-GUIDE.html', 'XMIND-GUIDE.md']:
            text = (self.docs / file).read_text(encoding='utf8')
            links = re.findall(r'(?:src|href)="([^"]+)"', text) if file.endswith('.html') else re.findall(r'\]\(([^)]+)\)', text)
            for target in links:
                if target.startswith('#') or '://' in target:
                    continue
                self.assertTrue((self.docs / target).exists(), target)
        self.assertIn('docs/MENU-GUIDE.md', (ROOT / 'README.md').read_text(encoding='utf8'))
        self.assertIn('MENU-GUIDE.md', function(self.source, 'sbsm'))

    def test_risks_and_external_boundaries_are_explicit(self):
        text = (self.docs / 'MENU-GUIDE.md').read_text(encoding='utf8')
        for token in ['外部脚本', '不由本仓库固定', '不写入', '可能仍显示',
                      '递归删除账户家目录', 'POST', 'Bearer', '不保证', 'blog.cloudflare.com']:
            self.assertIn(token, text)
        self.assertNotIn('s使用apple.com', text)

    def test_browser_document_is_offline_and_has_no_actions(self):
        text = (self.docs / 'MENU-GUIDE.html').read_text(encoding='utf8')
        self.assertNotRegex(text, r'<script|<iframe|<form|https?://|fetch\(')
        self.assertEqual(text.count('<section id='), 2)
        self.assertIn('MENU-ACTUAL-TREE.xmind', text)
        self.assertNotIn('7张', text)


if __name__ == '__main__':
    unittest.main()
