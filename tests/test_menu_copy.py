"""Menu copy contracts. Execute only isolated display/menu functions with stubs."""
import os
from pathlib import Path
import re
import tempfile
import unittest

from config_harness import ROOT, function, shell, save_records


class MenuCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.out = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='menu-copy-'))) / 'menu-copy'

    @classmethod
    def tearDownClass(cls):
        save_records(cls.out / 'commands.json')

    def display(self, name, extra=''):
        prelude = '''
green() { printf '%s\\n' "$*"; }
yellow() { printf '%s\\n' "$*"; }
blue() { printf '%s\\n' "$*"; }
red() { printf '%s\\n' "$*"; }
sbactive() { :; }
sb() { :; }
readp() { printf '%b\\n' "$1"; printf -v "$2" '%s' 0; }
'''
        return shell(function(self.source, name) + prelude + extra + '\n' + name + '\n',
                     self.out / self._testMethodName).stdout.decode('utf8')

    def test_config_menu_scope_and_dispatch(self):
        text = self.display('changeserv')
        for token in ['不含XHTTP', 'VMess的Argo', '清除节点名称', '11：管理独立XHTTP', '0-11']:
            self.assertIn(token, text)
        source = function(self.source, 'changeserv')
        for choice, target in [('9', 'vmesscfadd'), ('10', 'change_node_suffix'), ('11', 'xhttp_menu')]:
            self.assertRegex(source, r'\$menu" = "' + choice + r'".*?\n' + target)

    def test_xhttp_direct_and_argo_scope(self):
        text = self.display('xhttp_menu')
        self.assertIn('1–8为直连REALITY，9为固定Argo', text)
        self.assertIn('仅卸载直连XHTTP', text)
        self.assertIn('Gitlab另用9→2推送', text)
        text = self.display('xhttp_argo_menu')
        self.assertIn('不叠加REALITY', text)
        self.assertIn('8：独立设置优选域名/IP', text)

    def test_subscription_copy_distinguishes_exports_and_push(self):
        text = self.display('clash_sb_share')
        self.assertIn('不推送Gitlab', text)
        self.assertIn('已配置Gitlab时同时推送远端', text)
        self.assertIn('Sing-box JSON不含XHTTP', text)

    def test_help_matches_fork_and_cache(self):
        text = self.display('sbsm')
        for token in ['redrohu/sing-box-yg', '3→11→9', 'SB_MENU_REFRESH=1 sb',
                      '60秒', '5分钟', '旧GET保活链接需迁移', '上游项目/原作者']:
            self.assertIn(token, text)

    def test_main_dispatch_and_ids_unchanged(self):
        block = self.source[self.source.rindex('case "$Input" in'):]
        expected = ['instsllsingbox', 'unins', 'changeserv', 'changeport', 'changefl',
                    'stclre', 'upsbyg', 'upsbcroe', 'clash_sb_share', 'sblog', 'bbr',
                    'acme', 'cfwarp', 'inssbwpph', 'wgcfgo', 'sbsm']
        for choice, target in enumerate(expected, 1):
            self.assertRegex(block, rf'(?m)^\s*{choice}\s*\)\s*{target}\b')

    def test_old_paths_and_overbroad_claims_removed(self):
        self.assertNotIn('3-8-3', self.source)
        self.assertNotIn('3-8-1', self.source)
        self.assertNotIn('更换全协议UUID', self.source)
        self.assertIn('3→11→9→8', function(self.source, 'vmesscfadd'))

    def test_serv00_routes_and_auth_help(self):
        for name in ['serv00.sh', 'serv00keep.sh']:
            source = (ROOT / name).read_text(encoding='utf8')
            self.assertIn('选择7（选项6查看订阅链接）', source)
            self.assertNotIn('请进入主菜单选择4', source)
            self.assertNotIn('CF不死IP', source)
            self.assertIn('管理请求须使用可信HTTPS + POST/Bearer', source)
        source = (ROOT / 'serv00.sh').read_text(encoding='utf8')
        self.assertIn('非交互式控制页', source)
        self.assertIn('~/.serv00-management-token', function(source, 'menu'))
        self.assertRegex(source, r'7\) showsbclash')


if __name__ == '__main__':
    unittest.main()
