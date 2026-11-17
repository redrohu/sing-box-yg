import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

import test_node_suffix as suffix_tests
from config_harness import ROOT, RECORDS, check, generate_vps, save_records, shell


class NodePrefix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get("SB_TEST_OUTPUT", tempfile.mkdtemp(prefix="node-prefix-test-"))) / "node-prefix"
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.source = (ROOT / "sb.sh").read_text(encoding="utf8")

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / "commands.json")

    def share_helpers(self, d):
        return suffix_tests.NodeSuffix.share_helpers(self, d)

    def assertCore(self, path, version="1.14.4"):
        self.assertEqual(check(version, path).returncode, 0, RECORDS[-1])

    def assertNames(self, d, prefix, suffix):
        cfg = json.loads((d / "sbox.json").read_text(encoding="utf8"))
        label = prefix + " " if prefix else ""
        nodes = [x for x in cfg["outbounds"] if x["type"] in ["vless", "vmess", "hysteria2", "tuic", "anytls"]]
        for node in nodes:
            name = label + node["type"].replace("hysteria2", "hy2").replace("tuic", "tuic5")
            self.assertTrue(node["tag"].startswith(name), node)
            rest = node["tag"][len(name):]
            self.assertTrue(rest.startswith(" ") or rest.startswith("-"), node)
            self.assertTrue(node["tag"].endswith(" " + suffix), node)
        tags = {x["tag"] for x in cfg["outbounds"]}
        for outbound in cfg["outbounds"]:
            self.assertTrue(set(outbound.get("outbounds", [])) <= tags)
        self.assertIn("proxy", tags)
        self.assertIn("auto", tags)
        self.assertIn("direct", tags)
        yaml = (d / "clmi.yaml").read_text(encoding="utf8")
        self.assertIn('- name: "' + label + 'vless-reality-vision ' + suffix + '"\n', yaml)
        self.assertIn('    - "' + label + 'vless-reality-vision ' + suffix + '"\n', yaml)
        return cfg

    def test_prefix_all_argo_branches_and_unicode(self):
        for argo in ["none", "fixed", "temporary", "both"]:
            for prefix in ["HK_01.test", "香港1"]:
                with self.subTest(argo=argo, prefix=prefix):
                    d = generate_vps(self.source, self.output / (argo + "-" + prefix), argo=argo, suffix="oracle-US", prefix=prefix)
                    self.assertNames(d, prefix, "oracle-US")
                    self.assertCore(d / "sbox.json")
                    self.assertCore(d / "sb.json")

    def test_prefix_changes_names_not_connection_parameters(self):
        d = generate_vps(self.source, self.output / "names-only", argo="both", suffix="oracle-US")
        before = json.loads((d / "sbox.json").read_text(encoding="utf8"))
        yaml = (d / "clmi.yaml").read_text(encoding="utf8")
        server = (d / "sb.json").read_bytes()
        names = {x["tag"] for x in before["outbounds"] if x["type"] not in ["direct", "selector", "urltest"]}

        def renamed(obj):
            if isinstance(obj, dict):
                return {k: renamed(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [renamed(v) for v in obj]
            return "HK " + obj if isinstance(obj, str) and obj in names else obj

        generate_vps(self.source, d, argo="both", suffix="oracle-US", prefix="HK")
        after = self.assertNames(d, "HK", "oracle-US")
        self.assertEqual(after, renamed(before))
        self.assertEqual((d / "clmi.yaml").read_text(encoding="utf8").replace("HK ", ""), yaml)
        self.assertEqual((d / "sb.json").read_bytes(), server)

    def test_set_persist_suffix_independence_clear_and_backup(self):
        d = generate_vps(self.source, self.output / "set-clear", suffix="oracle-US")
        server = {f: (d / f).read_bytes() for f in ["sb.json", "sb10.json", "sb11.json"]}
        old_client = (d / "sbox.json").read_bytes()
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n3\n香港1\nINPUT\n", d)
        self.assertEqual((d / "node_prefix.conf").read_text(encoding="utf8"), "香港1\n")
        self.assertEqual((d / "node_suffix.conf").read_text(encoding="utf8"), "oracle-US\n")
        self.assertNames(d, "香港1", "oracle-US")
        self.assertCore(d / "sbox.json")
        links = (d / "jhsub.txt").read_text(encoding="utf8").splitlines()
        self.assertEqual(len(links), 7)
        for link in links:
            if link.startswith("vmess://"):
                name = json.loads(base64.b64decode(link[8:]))["ps"]
            else:
                name = unquote(urlsplit(link).fragment)
                self.assertNotIn("香港", link)
            self.assertTrue(name.startswith("香港1 "), name)
            self.assertTrue(name.endswith(" oracle-US"), name)
        backups = list(d.glob("node-name.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "sbox.json").read_bytes(), old_client)
        self.assertFalse((backups[0] / "node_prefix.conf").exists())
        self.assertEqual((backups[0] / "node_suffix.conf").read_text(encoding="utf8"), "oracle-US\n")
        # New processes reload both settings independently.
        shell(self.share_helpers(d) + 'sbshare || exit $?\n', d)
        self.assertNames(d, "香港1", "oracle-US")
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n2\nINPUT\n", d)
        self.assertNames(d, "香港1", "test-vps")
        self.assertTrue((d / "node_prefix.conf").exists())
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n1\nnew-suffix\nINPUT\n", d)
        self.assertNames(d, "香港1", "new-suffix")
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n4\nINPUT\n", d)
        self.assertFalse((d / "node_prefix.conf").exists())
        self.assertNames(d, "", "new-suffix")
        self.assertCore(d / "sbox.json")
        self.assertTrue(any((b / "node_prefix.conf").is_file() for b in d.glob("node-name.bak.*")))
        for name, data in server.items():
            self.assertEqual((d / name).read_bytes(), data)
        self.assertFalse((d / "forbidden").exists())

    def test_invalid_and_cancel_leave_prefix_suffix_and_exports_unchanged(self):
        d = generate_vps(self.source, self.output / "reject", prefix="existing-prefix", suffix="existing-suffix")
        before = {f: (d / f).read_bytes() for f in ["node_prefix.conf", "node_suffix.conf", "sbox.json", "clmi.yaml", "sb.json"]}
        for value in ['   ', 'bad"quote', "bad'quote", 'bad\\slash', '$(touch pwned)', 'bad@uri', 'x:y', 'bad/name', 'x' * 49, '😃']:
            shell(self.share_helpers(d) + "if change_node_suffix <<'INPUT'\n3\n" + value + "\nINPUT\nthen exit 1; fi\n", d)
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n3\n\nINPUT\n", d)
        self.assertEqual(list(d.glob("node-name.bak.*")), [])
        self.assertFalse((d / "pwned").exists())
        for name, data in before.items():
            self.assertEqual((d / name).read_bytes(), data)

    def test_corrupt_prefix_falls_back_without_execution(self):
        d = generate_vps(self.source, self.output / "corrupt", prefix="$(touch pwned)", suffix="oracle-US")
        self.assertNames(d, "", "oracle-US")
        self.assertFalse((d / "pwned").exists())
        self.assertCore(d / "sbox.json")

    def test_failed_refresh_reports_prefix_saved(self):
        d = generate_vps(self.source, self.output / "refresh-fail", suffix="oracle-US")
        result = shell(self.share_helpers(d) + '''
sbshare() { return 1; }
if change_node_suffix <<'INPUT'
3
saved-prefix
INPUT
then exit 1; fi
''', d)
        self.assertIn("导出刷新失败", result.stderr.decode("utf8"))
        self.assertEqual((d / "node_prefix.conf").read_text(encoding="utf8").strip(), "saved-prefix")
        self.assertNames(d, "", "oracle-US")

    def test_legacy_and_older_client_prefix_profiles(self):
        for version, client in [("1.10", "1.14"), ("1.12", "1.12"), ("1.13", "1.13")]:
            with self.subTest(version=version, client=client):
                d = generate_vps(self.source, self.output / ("legacy-" + version), version=version,
                                 client_version=client, prefix="HK", suffix="oracle-US")
                cfg = self.assertNames(d, "HK", "oracle-US")
                self.assertCore(d / "sbox.json", {"1.12": "1.12.25", "1.13": "1.13.21"}.get(client, "1.14.4"))
                if version == "1.10":
                    self.assertNotIn("anytls", [x["type"] for x in cfg["outbounds"]])
                    self.assertCore(d / "sb.json", "1.10.7")


if __name__ == "__main__":
    unittest.main(verbosity=2)
