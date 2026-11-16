import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from config_harness import (ROOT, RECORDS, bashpath, check, function, generate_vps,
                            parameters, save_records, shell)


class NodeSuffix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get("SB_TEST_OUTPUT", tempfile.mkdtemp(prefix="node-suffix-test-"))) / "node-suffix"
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.source = (ROOT / "sb.sh").read_text(encoding="utf8")

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / "commands.json")

    def assertCore(self, path):
        self.assertEqual(check("1.14.4", path).returncode, 0, RECORDS[-1])

    def assertNames(self, d, suffix):
        cfg = json.loads((d / "sbox.json").read_text(encoding="utf8"))
        names = [x["tag"] for x in cfg["outbounds"] if x["type"] in ["vless", "vmess", "hysteria2", "tuic", "anytls"]]
        self.assertTrue(all(x.endswith("-" + suffix) for x in names), names)
        tags = {x["tag"] for x in cfg["outbounds"]}
        for outbound in cfg["outbounds"]:
            self.assertTrue(set(outbound.get("outbounds", [])) <= tags)
        yaml = (d / "clmi.yaml").read_text(encoding="utf8")
        self.assertIn("- name: anytls-" + suffix + "\n", yaml)
        self.assertIn("- anytls-" + suffix + "\n", yaml)
        return cfg

    def share_helpers(self, d):
        source = self.source.replace("/etc/s-box", bashpath(d))
        helpers = "".join(function(source, name) for name in [
            "node_suffix_valid", "node_suffix_load", "change_node_suffix", "sb_client_profile",
            "sb_client", "resvless", "resvmess", "reshy2", "restu5", "resan", "sbshare", "readp"])
        # Suppress only external side effects; use real renderers and share assembly.
        return parameters(d) + helpers + '''
red() { echo "$*" >&2; }
yellow() { echo "$*"; }
green() { echo "$*"; }
white() { :; }
sleep() { :; }
qrencode() { :; }
systemctl() { echo unexpected-service-command >> forbidden; return 1; }
hostname() { echo unexpected-hostname-command >> forbidden; return 1; }
result_vl_vm_hy_tu() { :; }
changeserv() { echo returned-to-config-menu > menu-returned; }
sbnh=1.14
server_ip=$server_ipcl; sb_hy2_ip=$server_ipcl; sb_tu5_ip=$server_ipcl
vmadd_are_local=$vmadd_local; tls=false; ins_an=1; ins=1; SHA256=test-fingerprint
ps() { printf '%s\\n' 'cloudflared tunnel run fixed' 'cloudflared --url localhost:21443'; }
printf '%s\\n' fixed.example.org > sbargoym.log
'''

    def test_default_is_still_hostname(self):
        d = generate_vps(self.source, self.output / "default")
        self.assertNames(d, "test-vps")
        self.assertFalse((d / "node_suffix.conf").exists())
        self.assertCore(d / "sbox.json")

    def test_suffix_changes_names_not_connection_parameters(self):
        d = generate_vps(self.source, self.output / "names-only", argo="both")
        before = json.loads((d / "sbox.json").read_text(encoding="utf8"))
        yaml = (d / "clmi.yaml").read_text(encoding="utf8")
        server = (d / "sb.json").read_bytes()
        generate_vps(self.source, d, argo="both", suffix="oracle-new")
        after = json.loads((d / "sbox.json").read_text(encoding="utf8"))
        self.assertEqual(after, json.loads(json.dumps(before).replace("-test-vps", "-oracle-new")))
        self.assertEqual((d / "clmi.yaml").read_text(encoding="utf8"), yaml.replace("-test-vps", "-oracle-new"))
        self.assertEqual((d / "sb.json").read_bytes(), server)

    def test_custom_suffix_all_argo_branches_and_unicode(self):
        for argo in ["none", "fixed", "temporary", "both"]:
            for suffix in ["oracle-US_01.test", "甲骨文-美国1"]:
                with self.subTest(argo=argo, suffix=suffix):
                    d = generate_vps(self.source, self.output / (argo + "-" + suffix), argo=argo, suffix=suffix)
                    self.assertNames(d, suffix)
                    self.assertCore(d / "sbox.json")
                    self.assertCore(d / "sb.json")

    def test_set_persist_reset_and_server_unchanged(self):
        d = generate_vps(self.source, self.output / "set-reset")
        server = {f: (d / f).read_bytes() for f in ["sb.json", "sb10.json", "sb11.json"]}
        old_client = (d / "sbox.json").read_bytes()
        p = shell(self.share_helpers(d) + '''
change_node_suffix <<'INPUT'
1
甲骨文-US_1
INPUT
''', d)
        self.assertIn("已刷新", p.stdout.decode("utf8"))
        self.assertEqual((d / "node_suffix.conf").read_text(encoding="utf8"), "甲骨文-US_1\n")
        self.assertNames(d, "甲骨文-US_1")
        self.assertCore(d / "sbox.json")
        backups = list(d.glob("node-name.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "sbox.json").read_bytes(), old_client)
        self.assertFalse((backups[0] / "node_suffix.conf").exists())
        links = (d / "jhsub.txt").read_text(encoding="utf8").splitlines()
        self.assertEqual(len(links), 7)
        for link in links:
            if link.startswith("vmess://"):
                name = json.loads(base64.b64decode(link[8:]))["ps"]
            else:
                name = unquote(urlsplit(link).fragment)
                self.assertNotIn("甲骨文", link)  # URI fragment is percent-encoded.
            self.assertTrue(name.endswith("-甲骨文-US_1"), name)
        # A fresh process reads the persisted value, rather than inheriting globals.
        # Production does not enable errexit; optional absent share files are normal.
        shell(self.share_helpers(d) + 'sbshare || exit $?\n', d)
        self.assertNames(d, "甲骨文-US_1")
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n2\nINPUT\n", d)
        self.assertFalse((d / "node_suffix.conf").exists())
        self.assertNames(d, "test-vps")
        self.assertCore(d / "sbox.json")
        for name, data in server.items():
            self.assertEqual((d / name).read_bytes(), data)
        backups = list(d.glob("node-name.bak.*"))
        self.assertEqual(len(backups), 2)
        self.assertTrue(any((b / "node_suffix.conf").is_file() for b in backups))
        self.assertFalse((d / "forbidden").exists())

    def test_invalid_and_cancel_dont_change_exports(self):
        d = generate_vps(self.source, self.output / "reject", suffix="existing")
        before = {f: (d / f).read_bytes() for f in ["node_suffix.conf", "sbox.json", "clmi.yaml", "sb.json"]}
        for value in ['bad name', 'bad"quote', "bad'quote", 'bad\\slash', '$(touch pwned)',
                      'bad#uri', 'x:y', 'bad/name', 'x' * 49, '😃', '\tbad']:
            script = self.share_helpers(d) + "if change_node_suffix <<'INPUT'\n1\n" + value + "\nINPUT\nthen exit 1; fi\n"
            shell(script, d)
            for name, data in before.items():
                self.assertEqual((d / name).read_bytes(), data)
        for text in ['1\n\n', '0\n']:
            shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n" + text + "INPUT\n", d)
        self.assertTrue((d / "menu-returned").is_file())
        self.assertEqual(list(d.glob("node-name.bak.*")), [])
        self.assertFalse((d / "pwned").exists())
        for name, data in before.items():
            self.assertEqual((d / name).read_bytes(), data)

    def test_corrupt_file_falls_back_without_execution(self):
        d = generate_vps(self.source, self.output / "corrupt", suffix="$(touch pwned)")
        self.assertNames(d, "test-vps")
        self.assertFalse((d / "pwned").exists())
        self.assertCore(d / "sbox.json")

    def test_failed_refresh_reports_saved_setting(self):
        d = generate_vps(self.source, self.output / "refresh-fail")
        script = self.share_helpers(d) + '''
sbshare() { return 1; }
if change_node_suffix <<'INPUT'
1
saved-but-not-refreshed
INPUT
then exit 1; fi
'''
        result = shell(script, d)
        self.assertIn("导出刷新失败", result.stderr.decode("utf8"))
        self.assertEqual((d / "node_suffix.conf").read_text(encoding="utf8").strip(), "saved-but-not-refreshed")
        self.assertNames(d, "test-vps")

    def test_menu_dispatch_uses_new_submenu_number(self):
        d = self.output / "menu"
        d.mkdir(exist_ok=True)
        source = self.source.replace("/etc/s-box", bashpath(d))
        result = shell(function(source, "changeserv") + '''
sbactive() { :; }
green() { :; }
readp() { printf '%s\\n' "$1" > prompt; menu=10; }
change_node_suffix() { echo called > dispatched; }
changeserv
''', d)
        self.assertEqual((d / "dispatched").read_text().strip(), "called")
        self.assertIn("10：设置节点名称前缀/后缀", (d / "prompt").read_text(encoding="utf8"))
        self.assertIn("请选择【0-10】", (d / "prompt").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
