"""Validate the real server-field reader with isolated files and no services/network."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from config_harness import BASH, CORE_ROOT, ROOT, bashpath, function


def server_fields(anytls=True):
    inbounds = [
        dict(type="vless", tag="vless-sb", listen_port=11443,
             users=[dict(uuid="11111111-2222-3333-4444-555555555555")],
             tls=dict(server_name="www.apple.com", reality=dict(short_id=["aabbccdd"]))),
        dict(type="vmess", tag="vmess-sb", listen_port=21443,
             transport=dict(path="/websocket//upload"),
             tls=dict(enabled=False, server_name="example.org")),
        dict(type="hysteria2", tag="hy2-sb", listen_port=31443, tls=dict(key_path="/external/key.pem")),
        dict(type="tuic", tag="tuic5-sb", listen_port=41443, tls=dict(key_path="/external/key.pem")),
    ]
    if anytls:
        inbounds.append(dict(type="anytls", tag="anytls-sb", listen_port=51443,
                             tls=dict(key_path="/external/key.pem")))
    return dict(inbounds=inbounds)


class ExportFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path = Path(os.environ.get("SB_UNDER_TEST", ROOT / "sb.sh"))
        cls.source = cls.source_path.read_text(encoding="utf8")
        cls.output = Path(os.environ.get("SB_TEST_OUTPUT", tempfile.mkdtemp(prefix="export-fields-"))) / "export-fields"
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        (cls.output / "commands.json").write_text(json.dumps(cls.records, ensure_ascii=False, indent=2), encoding="utf8")

    def read_fields(self, name, config=None, raw=None):
        directory = self.output / name
        directory.mkdir(exist_ok=True)
        for file, contents in {"server_ip.log": "192.0.2.1\n", "server_ipcl.log": "192.0.2.1\n",
                               "public.key": "TEST_PUBLIC_KEY\n", "vm_ws.txt": "OLD_VM_EXPORT\n"}.items():
            (directory / file).write_text(contents, encoding="utf8")
        (directory / "sb.json").write_text(raw if raw is not None else json.dumps(config), encoding="utf8")
        source = self.source.replace("/etc/s-box", bashpath(directory)).replace("/root/ygkkkca", bashpath(directory / "ca"))
        jq = '"' + bashpath(CORE_ROOT / "jq.exe") + '" -b' if os.name == "nt" else "command jq"
        script = "set +e\n" + function(source, "result_vl_vm_hy_tu") + '''
red(){ echo "$*" >&2; }
sb_port_hop_manage(){ :; }
jq(){ printf 'jq\\n' >> jq-calls; __JQ__ "$@"; }
result_vl_vm_hy_tu
result=$?
# Dump shell values as JSON through arguments, never interpolated JSON/source text.
jq -n --arg uuid "$uuid" --arg vl "$vl_port" --arg vm "$vm_port" --arg hy "$hy2_port" \\
 --arg tu "$tu5_port" --arg an "$an_port" --arg path "$ws_path" --arg tls "$tls" \\
 '{uuid:$uuid,ports:[$vl,$vm,$hy,$tu,$an],path:$path,tls:$tls}' > values.json
exit "$result"
'''.replace("__JQ__", jq)
        file = directory / "read-fields.sh"
        file.write_text(script, encoding="utf8", newline="\n")
        command = [BASH, bashpath(file)]
        p = subprocess.run(command, cwd=directory, capture_output=True, timeout=30)
        values = json.loads((directory / "values.json").read_text(encoding="utf8"))
        self.records.append(dict(command=command, cwd=str(directory), shell_input=script,
                                 source_sha256=hashlib.sha256(self.source.encode()).hexdigest(),
                                 input=raw if raw is not None else config, values=values,
                                 exit_code=p.returncode, stdout=p.stdout.decode("utf8", "replace"),
                                 stderr=p.stderr.decode("utf8", "replace")))
        return directory, p, values

    def rejected(self, name, config=None, raw=None):
        d, p, values = self.read_fields(name, config, raw)
        self.assertNotEqual(p.returncode, 0, self.records[-1])
        self.assertEqual((d / "vm_ws.txt").read_text(), "OLD_VM_EXPORT\n")
        self.assertEqual(values["ports"], ["", "", "", "", ""])

    def test_valid_fields_are_parsed_once(self):
        d, p, values = self.read_fields("valid", server_fields())
        self.assertEqual(p.returncode, 0, self.records[-1])
        self.assertEqual(values["ports"], ["11443", "21443", "31443", "41443", "51443"])
        self.assertEqual(values["tls"], "false")
        self.assertEqual((d / "jq-calls").read_text().splitlines(), ["jq", "jq"])

    def test_null_ports_rejected_for_each_protocol(self):
        for index in range(5):
            with self.subTest(protocol=index):
                config = server_fields()
                config["inbounds"][index]["listen_port"] = None
                self.rejected("null-port-" + str(index), config)

    def test_non_integer_and_non_numeric_ports_rejected(self):
        for index, value in enumerate([1.5, "443", True]):
            with self.subTest(value=value):
                config = server_fields()
                config["inbounds"][0]["listen_port"] = value
                self.rejected("port-type-" + str(index), config)

    def test_out_of_range_ports_rejected(self):
        for value in [-1, 0, 65536]:
            with self.subTest(value=value):
                config = server_fields()
                config["inbounds"][1]["listen_port"] = value
                self.rejected("port-range-" + str(value), config)

    def test_tags_take_precedence_over_positions(self):
        config = server_fields()
        config["inbounds"] = list(reversed(config["inbounds"]))
        _, p, values = self.read_fields("reordered-tags", config)
        self.assertEqual(p.returncode, 0, self.records[-1])
        self.assertEqual(values["ports"], ["11443", "21443", "31443", "41443", "51443"])

    def test_path_shell_characters_preserved_and_not_executed(self):
        path = '/upload//a\'b";$(touch PWNED_DOLLAR);`touch PWNED_TICK`;${HOME}\nnext'
        config = server_fields()
        config["inbounds"][1]["transport"]["path"] = path
        d, p, values = self.read_fields("escaped-path", config)
        self.assertEqual(p.returncode, 0, self.records[-1])
        self.assertEqual(values["path"], path)
        self.assertFalse((d / "PWNED_DOLLAR").exists())
        self.assertFalse((d / "PWNED_TICK").exists())

    def test_malformed_json_rejected(self):
        self.rejected("bad-json", raw='{"inbounds":[')

    def test_legacy_110_without_anytls_is_supported(self):
        config = server_fields(anytls=False)
        _, p, values = self.read_fields("legacy-110", config)
        self.assertEqual(p.returncode, 0, self.records[-1])
        self.assertEqual(values["ports"], ["11443", "21443", "31443", "41443", ""])

    def test_legacy_untagged_positions_are_supported(self):
        config = server_fields(anytls=False)
        for inbound in config["inbounds"]:
            del inbound["tag"]
        _, p, values = self.read_fields("legacy-untagged", config)
        self.assertEqual(p.returncode, 0, self.records[-1])
        self.assertEqual(values["ports"], ["11443", "21443", "31443", "41443", ""])

    def test_missing_required_scalar_fields_rejected(self):
        for label, mutate in [
            ("uuid", lambda c: c["inbounds"][0]["users"][0].update(uuid=None)),
            ("tls", lambda c: c["inbounds"][1]["tls"].update(enabled="false")),
            ("path", lambda c: c["inbounds"][1]["transport"].pop("path")),
        ]:
            with self.subTest(field=label):
                config = server_fields()
                mutate(config)
                self.rejected("missing-" + label, config)


if __name__ == "__main__":
    unittest.main(verbosity=2)
