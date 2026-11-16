import json
import hashlib
import os
from pathlib import Path
import re
import tempfile
import unittest

from config_harness import (BASH, ROOT, RECORDS, bashpath, check, core, function,
                            generate_serv00, generate_vps, parameters, run,
                            save_records, shell)


class ConfigGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get("SB_TEST_OUTPUT", tempfile.mkdtemp(prefix="sing-box-config-test-")))
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.sources = {name: (ROOT / name).read_text(encoding="utf8")
                       for name in ["sb.sh", "serv00.sh", "serv00keep.sh"]}
        for version in ["1.10.7", "1.12.25", "1.13.21", "1.14.4"]:
            if not core(version).is_file():
                raise RuntimeError("Missing real test core: " + str(core(version)))

    @classmethod
    def tearDownClass(cls):
        save_records(cls.output / "commands.json")

    def assertCore(self, version, path):
        result = check(version, path)
        self.assertEqual(result.returncode, 0, RECORDS[-1])
        # No schema deprecation warnings are allowed on the new 1.14 path.
        if version == "1.14.4":
            self.assertNotIn("deprecated", (result.stdout + result.stderr).decode("utf8", "replace").lower())

    def load(self, path):
        return json.loads(Path(path).read_text(encoding="utf8"))

    def assertModern(self, cfg, http14=True):
        for inbound in cfg["inbounds"]:
            for field in ["sniff", "sniff_override_destination", "domain_strategy", "inet4_address", "inet6_address"]:
                self.assertNotIn(field, inbound)
        for outbound in cfg["outbounds"]:
            self.assertNotIn(outbound["type"], ["wireguard", "block", "dns"])
            self.assertNotIn("domain_strategy", outbound)
        for server in cfg.get("dns", {}).get("servers", []):
            self.assertIn("type", server)
            self.assertNotIn("address", server)
        self.assertNotIn("fakeip", cfg.get("dns", {}))
        self.assertNotIn("independent_cache", cfg.get("dns", {}))
        for rule in cfg.get("dns", {}).get("rules", []):
            self.assertNotIn("outbound", rule)
            self.assertNotIn("strategy", rule)
        if http14:
            for rule_set in cfg["route"].get("rule_set", []):
                self.assertNotIn("download_detour", rule_set)
        self.assertIn("default_domain_resolver", cfg["route"])

    def test_shell_syntax(self):
        for name in ["sb.sh", "serv00.sh", "serv00keep.sh", "kp.sh"]:
            with self.subTest(file=name):
                self.assertEqual(run([BASH, "-n", bashpath(ROOT / name)]).returncode, 0, RECORDS[-1])

    def test_vps_modern_server_matrix_and_client(self):
        for version in ["1.12.25", "1.13.21", "1.14.4"]:
            with self.subTest(version=version):
                d = generate_vps(self.sources["sb.sh"], self.output / ("vps-" + version),
                                 version=".".join(version.split(".")[:2]))
                self.assertCore(version, d / "sb.json")
                self.assertCore("1.14.4", d / "sbox.json")
                cfg = self.load(d / "sb.json")
                self.assertModern(cfg)
                self.assertEqual([x["tag"] for x in cfg["inbounds"]],
                                 ["vless-sb", "vmess-sb", "hy2-sb", "tuic5-sb", "anytls-sb"])
                self.assertEqual([x["listen_port"] for x in cfg["inbounds"]],
                                 [11443, 21443, 31443, 41443, 51443])
                self.assertNotIn("certificate_providers", cfg)
                self.assertEqual(cfg["endpoints"][0]["peers"][0]["reserved"], [1, 2, 3])
                self.assertModern(self.load(d / "sbox.json"))

    def test_legacy_server_uses_modern_independent_client(self):
        d = generate_vps(self.sources["sb.sh"], self.output / "vps-legacy", version="1.10")
        self.assertCore("1.10.7", d / "sb.json")
        self.assertCore("1.14.4", d / "sbox.json")
        self.assertEqual(len(self.load(d / "sb.json")["inbounds"]), 4)
        self.assertNotIn("anytls", [x["type"] for x in self.load(d / "sbox.json")["outbounds"]])

    def test_all_argo_client_branches_and_hopping(self):
        for argo, extra_nodes in [("none", 0), ("fixed", 2), ("temporary", 2), ("both", 4)]:
            with self.subTest(argo=argo):
                d = generate_vps(self.sources["sb.sh"], self.output / ("argo-" + argo), argo=argo, hopping=True)
                self.assertCore("1.14.4", d / "sbox.json")
                cfg = self.load(d / "sbox.json")
                nodes = [x for x in cfg["outbounds"] if x["type"] in ["vless", "vmess", "hysteria2", "tuic", "anytls"]]
                self.assertEqual(len(nodes), 5 + extra_nodes)
                self.assertEqual(next(x for x in nodes if x["type"] == "hysteria2")["server_ports"], ["32000:32010"])
                tags = {x["tag"] for x in cfg["outbounds"]}
                for group in [x for x in cfg["outbounds"] if "outbounds" in x]:
                    self.assertTrue(set(group["outbounds"]) <= tags)

    def test_vps_dns_and_route_order(self):
        d = generate_vps(self.sources["sb.sh"], self.output / "vps-order")
        cfg = self.load(d / "sbox.json")
        rules = cfg["route"]["rules"]
        self.assertEqual([x.get("action") for x in rules[:2]], ["sniff", "hijack-dns"])
        self.assertEqual(rules[1]["rules"], [{"protocol": "dns"}, {"port": 53}])
        self.assertEqual([x.get("clash_mode") for x in rules[2:4]], ["Direct", "Global"])
        self.assertEqual([x.get("clash_mode") for x in cfg["dns"]["rules"][:2]], ["Direct", "Global"])
        self.assertTrue(cfg["experimental"]["cache_file"]["store_fakeip"])
        self.assertTrue(cfg["experimental"]["cache_file"]["store_dns"])

    def test_optional_older_client_profiles(self):
        for version in ["1.12.25", "1.13.21"]:
            for name, source in self.sources.items():
                with self.subTest(version=version, script=name):
                    d = self.output / (name + "-client-" + version)
                    profile = ".".join(version.split(".")[:2])
                    if name == "sb.sh":
                        generate_vps(source, d, client_version=profile)
                        path = d / "sbox.json"
                    else:
                        generate_serv00(source, d, client_version=profile)
                        path = d / "sing_box.json"
                    self.assertCore(version, path)
                    cfg = self.load(path)
                    self.assertNotIn("http_clients", cfg)
                    self.assertNotIn("optimistic", cfg["dns"])
                    self.assertNotIn("store_dns", cfg["experimental"]["cache_file"])
                    self.assertTrue(cfg["experimental"]["cache_file"]["store_fakeip"])

    def test_serv00_server_matrix(self):
        for name in ["serv00.sh", "serv00keep.sh"]:
            for version in ["1.10.7", "1.12.25", "1.13.21", "1.14.4"]:
                for nb in [13, 14]:
                    with self.subTest(script=name, version=version, host=nb):
                        d = generate_serv00(self.sources[name], self.output / (name + version + "-" + str(nb)),
                                            version=version, nb=nb)
                        self.assertCore(version, d / "config.json")
                        self.assertCore("1.14.4", d / "sing_box.json")
                        cfg = self.load(d / "config.json")
                        self.assertEqual(len(cfg["inbounds"]), 5)
                        wg = cfg.get("endpoints", [None])[0]
                        if version != "1.10.7":
                            self.assertModern(cfg, http14=(version == "1.14.4"))
                            self.assertEqual(wg["tag"], "wg")
                            self.assertEqual(wg["peers"][0]["port"], 4500)
                        else:
                            self.assertNotIn("endpoints", cfg)
                            self.assertIn("wireguard", [x["type"] for x in cfg["outbounds"]])
                        self.assertEqual(cfg["route"].get("rules", [{}])[0].get("outbound"), "wg" if nb == 14 else None)

    def test_serv00_dns_fakeip_rule_is_reachable(self):
        for name in ["serv00.sh", "serv00keep.sh"]:
            d = generate_serv00(self.sources[name], self.output / (name + "-dns"))
            cfg = self.load(d / "sing_box.json")
            self.assertModern(cfg)
            rules = cfg["dns"]["rules"]
            fake = next(i for i, x in enumerate(rules) if x.get("server") == "dns_fakeip")
            fallback = next(i for i, x in enumerate(rules) if x.get("rule_set") == "geosite-geolocation-!cn" and "query_type" not in x)
            self.assertLess(fake, fallback)
            self.assertEqual(cfg["route"]["rules"][0]["action"], "sniff")
            self.assertEqual(cfg["http_clients"][0]["detour"], "select")

    def test_client_profile_failure_does_not_overwrite(self):
        d = self.output / "client-atomic"
        d.mkdir(exist_ok=True)
        (d / "existing.json").write_text("previous", encoding="utf8")
        script = function(self.sources["sb.sh"], "sb_client_profile") + '''
printf '{invalid' > raw.json
if sb_client_profile raw.json existing.json; then exit 1; fi
printf '{}' > raw.json
SB_CLIENT_VERSION=1.10
if sb_client_profile raw.json existing.json; then exit 1; fi
'''
        shell(script, d)
        self.assertEqual((d / "existing.json").read_text(encoding="utf8"), "previous")
        self.assertEqual(list(d.glob("existing.json.tmp.*")), [])

    def test_serv00_server_failure_and_backup(self):
        source = self.sources["serv00.sh"]
        d = generate_serv00(source, self.output / "serv00-atomic")
        before = (d / "config.json").read_bytes()
        (d / "bad.json").write_text('{"inbounds":[{"type":"not-real"}]}', encoding="utf8")
        shell(function(source, "serv00_server_profile") + '''
red() { echo "$*" >&2; }
if serv00_server_profile bad.json config.json ./test-core; then exit 1; fi
serv00_server_profile config.json config.json ./test-core
''', d)
        self.assertEqual((d / "config.json").read_bytes(), before)
        backups = list(d.glob("config.json.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)

    def test_helpers_identical_and_keep_parameters_stable(self):
        helpers = [function(s, "sb_client_profile") for s in self.sources.values()]
        self.assertEqual(len(set(helpers)), 1)
        keep = self.sources["serv00keep.sh"].splitlines()
        for line, field in [(14, "UUID"), (15, "ARGO_DOMAIN"), (16, "ARGO_AUTH"),
                            (17, "vless_port"), (18, "vmess_port"), (19, "hy2_port")]:
            self.assertTrue(keep[line - 1].startswith("export " + field + "="))

    def test_original_menu_labels_and_no_template_dispatch(self):
        fixture = json.loads((ROOT / "tests/fixtures/original-menu-labels.json").read_text(encoding="utf8"))
        source = self.sources["sb.sh"]
        labels = re.findall(r'^(?:green|yellow|white|red) "[^"\n]*"', source[source.rindex('sbsm(){'):], re.M)
        labels = [x for x in labels if re.match(r'\w+ "\s*\d+\.', x)]
        self.assertEqual(labels, fixture["labels"])
        self.assertNotIn("server14.sh", source)
        self.assertNotIn("sb14_", source)
        start = source.rindex("\nclear\n") + 1
        header = source[start:source.index("insV=", start)]
        self.assertEqual(header, json.loads((ROOT / "tests/fixtures/original-menu-header.json").read_text(encoding="utf8"))["header"])

    def test_clash_templates_original_except_names_quoting_and_whitespace(self):
        fixture = json.loads((ROOT / "tests/fixtures/original-clash-sha256.json").read_text(encoding="utf8"))
        for name, expected in fixture.items():
            template = function(self.sources["sb.sh"], name).replace("$node_suffix", "$hostname")
            template = template.replace("${node_prefix_label}", "")
            template = re.sub(r'^(\s*- (?:name: )?)"([^"\n]*\$hostname)"$', r'\1\2', template, flags=re.M)
            template = template.replace(r'\"anytls-$hostname\"', 'anytls-$hostname')
            template = "\n".join(line.rstrip() for line in template.splitlines()) + "\n"
            self.assertEqual(hashlib.sha256(template.encode()).hexdigest(), expected)

    def test_serv00_port_edits_after_reformatting(self):
        for name in ["serv00.sh", "serv00keep.sh"]:
            source = self.sources[name]
            d = generate_serv00(source, self.output / (name + "-port-edit"))
            start = source.index('port_tmp=$(mktemp')
            end = source.index('\n', source.index('exit 1; }', start))
            script = f'WORKDIR="{bashpath(d)}"\nhy2_port=31001; vless_port=31002; vmess_port=31003\n'
            shell(script + source[start:end] + "\n", d)
            self.assertCore("1.14.4", d / "config.json")
            ports = [x["listen_port"] for x in self.load(d / "config.json")["inbounds"]]
            self.assertEqual(ports, [31001, 31001, 31001, 31002, 31003])

    def test_vps_fixed_line_edit_contract(self):
        d = generate_vps(self.sources["sb.sh"], self.output / "line-contract")
        lines = (d / "sb11.json").read_text(encoding="utf8").splitlines()
        # Existing submenus still use these positions; additions belong AFTER them.
        fields = {130: "2606:4700::1", 132: '"private_key"', 142: '"reserved"',
                  165: '"server_port"', 177: '"yg_kkk"', 184: '"yg_kkk"',
                  190: '"yg_kkk"', 196: '"yg_kkk"'}
        for line, expected in fields.items():
            self.assertIn(expected, lines[line - 1], (line, lines[line - 1]))

    def test_failed_core_check_prevents_service_commands(self):
        d = self.output / "check-gate"
        d.mkdir(exist_ok=True)
        for name in ["restartsb", "sbservice"]:
            script = function(self.sources["sb.sh"], name) + '''
sb_config_check() { return 1; }
systemctl() { echo forbidden >> called; }
rc-service() { echo forbidden >> called; }
'''
            script += f'if {name}; then exit 1; fi\n'
            shell(script, d)
            self.assertFalse((d / "called").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
