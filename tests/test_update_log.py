import os
from pathlib import Path
import re
import shlex
import tempfile
import unittest

from config_harness import ROOT, bashpath, function, save_records, shell


HISTORY = '''v26.11.17-fork.6更新内容：
最新日志 # | 空格

历史版本：
v26.11.17-fork.5更新内容：
中间日志

历史版本：
v26.11.16-fork.4更新内容：
当前版本的日志

历史版本：
v26.11.16-fork.3更新内容：
更早日志

历史版本：
v26.4.11更新内容：
旧版注意事项

更新内容：
旧版详情
'''


class UpdateLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'sb.sh').read_text(encoding='utf8')
        cls.output = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='update-log-'))) / 'update-log'
        cls.output.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / 'commands.json')

    def headings(self, text):
        return re.findall(r'^(v[^\s]+)更新内容', text, re.M)

    def filter(self, installed, latest='v26.11.17-fork.6', text=HISTORY, case='filter'):
        d = self.output / self._testMethodName / case
        d.mkdir(parents=True, exist_ok=True)
        (d / 'remote.txt').write_bytes(text.encode('utf8'))
        script = function(self.source, 'sb_update_log')
        script += f'sb_update_log {shlex.quote(installed)} {shlex.quote(latest)} < remote.txt\n'
        return shell(script, d).stdout.decode('utf8')

    def notice(self, installed, text=HISTORY, failure=False, case='notice'):
        d = self.output / self._testMethodName / case
        d.mkdir(parents=True, exist_ok=True)
        if installed is not None:
            (d / 'v').write_text(installed + '\n', encoding='utf8')
        (d / 'remote.txt').write_bytes(text.encode('utf8'))
        source = self.source.replace('/etc/s-box', bashpath(d))
        helpers = ''.join(function(source, n) for n in ['sb_info_valid', 'sb_info_cache_get', 'sb_info_cache_put', 'sb_script_version_info', 'sb_update_log', 'sb_update_notice'])
        start = source.index('insV=$(cat ')
        block = source[start:source.index('\nlapre\n', start)]
        self.assertTrue(block.rstrip().endswith('sb_update_notice "$insV"'))
        script = helpers + '''
yellow=; bblue=; plain=
yellow() { printf '%s\\n' "$*"; }
curl() {
    printf '%s\\n' "$*" >> curl-calls.txt
'''
        script += 'return 22\n' if failure else 'cat remote.txt\n'
        # The real top-level script does not enable errexit (missing v is normal).
        script += '}\nset +e\n' + block + '\n'
        output = shell(script, d).stdout.decode('utf8')
        self.assertEqual(len((d / 'curl-calls.txt').read_text().splitlines()), 1)
        return output

    def test_reported_fork4_to_fork6_only_displays_fork6_and_fork5(self):
        text = self.notice('v26.11.16-fork.4')
        self.assertEqual(self.headings(text), ['v26.11.17-fork.6', 'v26.11.17-fork.5'])
        for excluded in ['当前版本的日志', '更早日志', '旧版详情', '历史版本：']:
            self.assertNotIn(excluded, text)
        self.assertIn('最新日志 # | 空格', text)
        self.assertFalse(text.endswith('\n\n'))

    def test_actual_repository_release_history(self):
        text = (ROOT / 'version').read_text(encoding='utf8')
        latest = self.headings(text)[0]
        output = self.filter('v26.11.16-fork.4', latest, text)
        headers = self.headings(text)
        self.assertEqual(self.headings(output), headers[:headers.index('v26.11.16-fork.4')])

    def test_fork7_detects_xhttp_release_and_latest_is_installed(self):
        history = (ROOT / 'version').read_text(encoding='utf8')
        latest = self.headings(history)[0]
        self.assertNotEqual(latest, 'v26.11.17-fork.7')
        output = self.notice('v26.11.17-fork.7', history)
        self.assertIn('可选择7进行更新', output)
        headers = self.headings(history)
        self.assertEqual(self.headings(output), headers[:headers.index('v26.11.17-fork.7')])
        self.assertIn('XHTTP', output)
        self.assertIn('Mihomo', output)
        self.assertIn('主菜单9', output)
        self.assertNotIn('更新提示仅显示当前版本之后', output)
        current = self.notice(latest, history, case='after-update')
        self.assertIn('(已安装)', current)
        self.assertNotIn('可选择7进行更新', current)

    def test_numeric_fork_comparison_and_latest_upper_bound(self):
        text = '\n历史版本：\n'.join(f'v26.11.17-fork.{n}更新内容：\n日志{n}' for n in [11, 10, 9, 8, 2])
        self.assertEqual(self.headings(self.filter('v26.11.17-fork.8', 'v26.11.17-fork.10', text)),
                         ['v26.11.17-fork.10', 'v26.11.17-fork.9'])

    def test_dates_legacy_release_and_missing_installed_entry(self):
        text = 'v27.1.1更新内容：\nnew\n历史版本：\nv26.12.1更新内容：\nmonth\n历史版本：\nv26.9.30更新内容：\nold\n'
        self.assertEqual(self.headings(self.filter('v26.10.1', 'v27.1.1', text)), ['v27.1.1', 'v26.12.1'])
        self.assertEqual(self.headings(self.filter('v26.4.11', case='legacy')),
                         ['v26.11.17-fork.6', 'v26.11.17-fork.5', 'v26.11.16-fork.4', 'v26.11.16-fork.3'])
        text = HISTORY.replace('v26.11.16-fork.4更新内容：\n当前版本的日志\n\n历史版本：\n', '')
        self.assertEqual(self.headings(self.filter('v26.11.16-fork.4', text=text, case='missing')),
                         ['v26.11.17-fork.6', 'v26.11.17-fork.5'])

    def test_same_or_newer_local_version_shows_no_update_log(self):
        for installed in ['v26.11.17-fork.6', 'v26.11.17-fork.10', 'v27.1.1']:
            with self.subTest(installed=installed):
                self.assertEqual(self.filter(installed, case=installed), '')
                text = self.notice(installed, case=installed + '-notice')
                self.assertEqual(self.headings(text), [])
                self.assertNotIn('可选择7进行更新', text)

    def test_unknown_or_empty_local_version_only_shows_latest(self):
        for index, installed in enumerate(['', 'unknown', '$(touch pwned)']):
            text = self.notice(installed, case=str(index))
            self.assertEqual(self.headings(text), ['v26.11.17-fork.6'])
            self.assertIn('无法识别当前脚本版本', text)
            self.assertFalse((self.output / self._testMethodName / str(index) / 'pwned').exists())

    def test_uninstalled_server_does_not_show_release_notes(self):
        text = self.notice(None)
        self.assertIn('未安装', text)
        self.assertEqual(self.headings(text), [])

    def test_failed_empty_or_invalid_download_does_not_report_update(self):
        for index, (text, failure) in enumerate([(HISTORY, True), ('', False), ('404: Not Found', False), ('<html>error</html>', False)]):
            output = self.notice('v26.11.16-fork.4', text, failure, case=str(index))
            self.assertIn('暂时无法检查脚本更新', output)
            self.assertNotIn('可选择7进行更新', output)
            self.assertEqual(self.headings(output), [])

    def test_crlf_and_installed_version_whitespace(self):
        text = self.filter(' v26.11.16-fork.4\r ', text=HISTORY.replace('\n', '\r\n'))
        self.assertEqual(self.headings(text), ['v26.11.17-fork.6', 'v26.11.17-fork.5'])
        self.assertNotIn('\r', text)

    def test_release_text_is_not_interpreted_as_shell_or_printf_escapes(self):
        literal = r'详情 \n \033[31m $(touch pwned) # |'
        text = self.notice('v26.11.16-fork.4', 'v26.11.17-fork.6更新内容：\n' + literal + '\n')
        self.assertIn(literal, text)
        self.assertFalse((self.output / self._testMethodName / 'notice/pwned').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
