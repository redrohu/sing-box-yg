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


class NodeSpaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get("SB_TEST_OUTPUT", tempfile.mkdtemp(prefix="node-spaces-test-"))) / "node-spaces"
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.source = (ROOT / "sb.sh").read_text(encoding="utf8")

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / "commands.json")

    def share_helpers(self, directory):
        return suffix_tests.NodeSuffix.share_helpers(self, directory)

    def assertNames(self, directory, prefix, suffix):
        cfg = json.loads((directory / "sbox.json").read_text(encoding="utf8"))
        label = prefix + " " if prefix else ""
        nodes = [x["tag"] for x in cfg["outbounds"] if x["type"] in ["vless", "vmess", "hysteria2", "tuic", "anytls"]]
        self.assertTrue(all(n.startswith(label) and n.endswith(" " + suffix) for n in nodes))
        self.assertIn(label + "anytls " + suffix, nodes)
        tags = {x["tag"] for x in cfg["outbounds"]}
        for group in cfg["outbounds"]:
            self.assertTrue(set(group.get("outbounds", [])) <= tags)
        clash = yaml.safe_load((directory / "clmi.yaml").read_text(encoding="utf8"))
        names = {x["name"] for x in clash["proxies"]}
        self.assertIn(label + "anytls " + suffix, names)
        self.assertTrue(all(n.startswith(label) and n.endswith(" " + suffix) for n in names))
        groups = {x["name"] for x in clash["proxy-groups"]}
        for group in clash["proxy-groups"]:
            self.assertTrue(set(group["proxies"]) <= names | groups | {"DIRECT"})
        result = check("1.14.4", directory / "sbox.json")
        self.assertEqual(result.returncode, 0, RECORDS[-1])

    def test_exact_reported_name_and_horizontal_spaces_are_valid(self):
        script = function(self.source, "node_suffix_valid")
        for value in ["Oracle-157-韩国", "Oracle 157 韩国", "Oracle  157 韩国", " 韩国 01 ",
                      "Oracle\u00a0157\u3000韩国", "Oracle–157–韩国", "한글 노드 01", "x" * 48]:
            encoded = base64.b64encode(value.encode()).decode()
            script += f'value=$(printf "%s" "{encoded}" | base64 -d)\nnode_suffix_valid "$value"\n'
        for value in ["", " ", "   ", "\u00a0\u3000", "x" * 49, "x\ty", "x\ny", "x\ry", 'x"y',
                      "x'y", "x\\y", "x@y", "x:y", "x/y", "Oracle-157-韩国\u200b", "$(touch pwned)"]:
            encoded = base64.b64encode(value.encode()).decode()
            script += f'value=$(printf "%s" "{encoded}" | base64 -d)\nif node_suffix_valid "$value"; then exit 1; fi\n'
        shell(script, self.output / "validation")

    def test_json_yaml_and_group_references_with_spaces_all_argo_branches(self):
        for argo in ["none", "fixed", "temporary", "both"]:
            for index, (prefix, suffix) in enumerate([
                ("Oracle  157 韩国", "韩国 01"),
                (" Oracle-157-韩国 ", " 首尔 节点 "),
                ("Oracle\u00a0157\u3000韩国", "韩国\u3000节点"),
            ]):
                with self.subTest(argo=argo, prefix=prefix, suffix=suffix):
                    d = generate_vps(self.source, self.output / (argo + str(index)), argo=argo, prefix=prefix, suffix=suffix)
                    self.assertNames(d, prefix, suffix)

    def test_settings_persist_spaces_and_vmess_names_do_not_collapse(self):
        d = generate_vps(self.source, self.output / "settings")
        before = {name: (d / name).read_bytes() for name in ["sb.json", "sb10.json", "sb11.json"]}
        prefix, suffix = "Oracle  157 韩国", " 韩国  01 "
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n3\n" + prefix + "\nINPUT\n", d)
        shell(self.share_helpers(d) + "change_node_suffix <<'INPUT'\n1\n" + suffix + "\nINPUT\n", d)
        self.assertEqual((d / "node_prefix.conf").read_text(encoding="utf8"), prefix + "\n")
        self.assertEqual((d / "node_suffix.conf").read_text(encoding="utf8"), suffix + "\n")
        shell(self.share_helpers(d) + "sbshare || exit $?\n", d)
        self.assertNames(d, prefix, suffix)
        links = (d / "jhsub.txt").read_text(encoding="utf8").splitlines()
        self.assertEqual(len(links), 7)
        for link in links:
            if link.startswith("vmess://"):
                name = json.loads(base64.b64decode(link[8:]))["ps"]
            else:
                self.assertNotIn(" ", link)
                self.assertNotIn("韩国", link)
                self.assertIn("%20", link)
                name = unquote(urlsplit(link).fragment)
            self.assertTrue(name.startswith(prefix + " "), repr(name))
            self.assertTrue(name.endswith(" " + suffix), repr(name))
        for name, data in before.items():
            self.assertEqual((d / name).read_bytes(), data)
        self.assertFalse((d / "forbidden").exists())
        self.assertEqual(len(list(d.glob("node-name.bak.*"))), 2)

    def test_invalid_hidden_character_prints_actual_input_without_changes(self):
        d = generate_vps(self.source, self.output / "hidden", prefix="existing prefix", suffix="existing suffix")
        before = {name: (d / name).read_bytes() for name in ["node_prefix.conf", "node_suffix.conf", "sbox.json", "clmi.yaml"]}
        result = shell(self.share_helpers(d) + "if change_node_suffix <<'INPUT'\n3\nOracle-157-韩国\u200b\nINPUT\nthen exit 1; fi\n", d)
        self.assertIn("8203", result.stdout.decode("utf8"))
        self.assertIn("格式无效", result.stderr.decode("utf8"))
        self.assertEqual(list(d.glob("node-name.bak.*")), [])
        for name, data in before.items():
            self.assertEqual((d / name).read_bytes(), data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
