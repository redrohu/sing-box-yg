import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

import yaml
import test_node_suffix as suffix_tests
from config_harness import ROOT, RECORDS, check, function, generate_vps, save_records, shell


class NodeSymbols(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get("SB_TEST_OUTPUT", tempfile.mkdtemp(prefix="node-symbols-test-"))) / "node-symbols"
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.source = (ROOT / "sb.sh").read_text(encoding="utf8")

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / "commands.json")

    def share_helpers(self, directory):
        return suffix_tests.NodeSuffix.share_helpers(self, directory)

    def assertNames(self, directory, prefix, suffix, count):
        label = prefix + " " if prefix else ""
        cfg = json.loads((directory / "sbox.json").read_text(encoding="utf8"))
        nodes = [x["tag"] for x in cfg["outbounds"] if x["type"] in ["vless", "vmess", "hysteria2", "tuic", "anytls"]]
        self.assertEqual(len(nodes), count)
        self.assertIn(label + "anytls " + suffix, nodes)
        self.assertTrue(all(n.startswith(label) and n.endswith(" " + suffix) for n in nodes))
        tags = {x["tag"] for x in cfg["outbounds"]}
        self.assertTrue({"proxy", "auto", "direct"} <= tags)
        for group in cfg["outbounds"]:
            self.assertTrue(set(group.get("outbounds", [])) <= tags)
        clash = yaml.safe_load((directory / "clmi.yaml").read_text(encoding="utf8"))
        names = {x["name"] for x in clash["proxies"]}
        self.assertEqual(len(names), count)
        self.assertIn(label + "anytls " + suffix, names)
        self.assertTrue(all(n.startswith(label) and n.endswith(" " + suffix) for n in names))
        groups = {x["name"] for x in clash["proxy-groups"]}
        for group in clash["proxy-groups"]:
            self.assertTrue(set(group["proxies"]) <= names | groups | {"DIRECT"})
        result = check("1.14.4", directory / "sbox.json")
        self.assertEqual(result.returncode, 0, RECORDS[-1])
        return cfg

    def test_hash_and_pipe_validation_for_prefix_and_suffix(self):
        script = function(self.source, "node_suffix_valid")
        for value in ["Oracle #157 | 韩国", "#", "|", " # | ", "A||B##C", "韩国 # 首尔 | 01", "#" * 48, "|" * 48]:
            encoded = base64.b64encode(value.encode()).decode()
            script += f'value=$(printf "%s" "{encoded}" | base64 -d)\nnode_suffix_valid "$value"\n'
        for value in ['x"y', "x'y", "x\\y", "x\ty", "x\ny", "x:y", "x/y", "$(touch pwned)", "#" * 49, "   "]:
            encoded = base64.b64encode(value.encode()).decode()
            script += f'value=$(printf "%s" "{encoded}" | base64 -d)\nif node_suffix_valid "$value"; then exit 1; fi\n'
        shell(script + "true\n", self.output / "validation")

    def test_json_yaml_and_references_all_argo_branches(self):
        for argo, count in [("none", 5), ("fixed", 7), ("temporary", 7), ("both", 9)]:
            for index, (prefix, suffix) in enumerate([
                ("Oracle #157 | 韩国", "首尔 | 节点 #01"),
                ("#", "|"),
                ("|", "#"),
                (" # | ", " | # "),
            ]):
                with self.subTest(argo=argo, prefix=prefix, suffix=suffix):
                    d = generate_vps(self.source, self.output / (argo + str(index)), argo=argo, prefix=prefix, suffix=suffix)
                    self.assertNames(d, prefix, suffix, count)

    def test_set_reload_reset_and_uri_encoding(self):
        d = generate_vps(self.source, self.output / "settings", argo="both")
        before = {name: (d / name).read_bytes() for name in ["sb.json", "sb10.json", "sb11.json"]}
        prefix, suffix = "Oracle #157 | 韩国", "首尔 | 节点 #01"
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n3\n" + prefix + "\nINPUT\n", d)
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n1\n" + suffix + "\nINPUT\n", d)
        self.assertEqual((d / "node_prefix.conf").read_text(encoding="utf8"), prefix + "\n")
        self.assertEqual((d / "node_suffix.conf").read_text(encoding="utf8"), suffix + "\n")
        shell(self.share_helpers(d) + "sbshare || exit $?\n", d)
        self.assertNames(d, prefix, suffix, 9)
        links = (d / "jhsub.txt").read_text(encoding="utf8").splitlines()
        self.assertEqual(len(links), 7)
        for link in links:
            if link.startswith("vmess://"):
                name = json.loads(base64.b64decode(link[8:]))["ps"]
            else:
                self.assertEqual(link.count("#"), 1)
                self.assertNotIn("|", link)
                self.assertNotIn(" ", link)
                self.assertIn("%23", link)
                self.assertIn("%7C", link)
                self.assertIn("%20", link)
                name = unquote(urlsplit(link).fragment)
            self.assertTrue(name.startswith(prefix + " "), repr(name))
            self.assertTrue(name.endswith(" " + suffix), repr(name))
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n4\nINPUT\n", d)
        self.assertNames(d, "", suffix, 9)
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n2\nINPUT\n", d)
        self.assertNames(d, "", "test-vps", 9)
        for name, data in before.items():
            self.assertEqual((d / name).read_bytes(), data)
        self.assertFalse((d / "forbidden").exists())
        self.assertFalse((d / "node_prefix.conf").exists())
        self.assertFalse((d / "node_suffix.conf").exists())
        self.assertEqual(len(list(d.glob("node-name.bak.*"))), 4)

    def test_protocol_hyphens_and_only_name_changes(self):
        d = generate_vps(self.source, self.output / "names-only", argo="both", prefix="base", suffix="node")
        before = json.loads((d / "sbox.json").read_text(encoding="utf8"))
        old_yaml = yaml.safe_load((d / "clmi.yaml").read_text(encoding="utf8"))
        server = (d / "sb.json").read_bytes()
        prefix, suffix = "Oracle #157 | 韩国", "首尔 | #01"

        def rename(obj):
            if isinstance(obj, dict):
                return {k: rename(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [rename(v) for v in obj]
            if isinstance(obj, str) and obj.startswith("base ") and obj.endswith(" node"):
                return prefix + " " + obj[len("base "):-len(" node")] + " " + suffix
            return obj

        generate_vps(self.source, d, argo="both", prefix=prefix, suffix=suffix)
        after = self.assertNames(d, prefix, suffix, 9)
        self.assertEqual(after, rename(before))
        self.assertEqual(yaml.safe_load((d / "clmi.yaml").read_text(encoding="utf8")), rename(old_yaml))
        self.assertIn(prefix + " vmess-tls-argo固定 " + suffix, [x["tag"] for x in after["outbounds"]])
        self.assertEqual((d / "sb.json").read_bytes(), server)


if __name__ == "__main__":
    unittest.main(verbosity=2)
