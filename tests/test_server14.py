"""Run with Python stdlib; requires bash, jq and a real sing-box >=1.14 binary.

SB14_TEST_BIN=/path/to/sing-box python -m unittest discover -s tests -v
No ACME requests or service restarts are made. Mutation tests stub root/service only.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOG = []


def unix(path):
    value = str(Path(path).resolve()).replace("\\", "/")
    return "/" + value[0].lower() + value[2:] if re.match(r"^[A-Za-z]:/", value) else value


class Server14Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = os.environ.get("SB14_TEST_BASH") or (
            r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash")
        )
        cls.bin = os.environ.get("SB14_TEST_BIN")
        if not cls.bin:
            raise RuntimeError("Set SB14_TEST_BIN to a real >=1.14 sing-box binary")
        cls.reference = json.loads((ROOT / "tests/fixtures/server14.upstream.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sb14-test-")
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.env = dict(os.environ, SB14_DIR=unix(self.dir), SB14_BIN=unix(self.bin))
        self.params = {
            "domain": "audit.example.org", "email": "audit@example.org",
            "cloudflare_api_token": "offline-only-token", "reality_server": "www.apple.com",
        }
        self.parameters = self.write("parameters.json", self.params)

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def call(self, *args, expected=0, extra="", env=None):
        # Test only: root is stubbed so transactional edits can be exercised on Windows.
        # Service helpers are tripwires; tests must not restart/replace any real service.
        code = f"source {shlex.quote(unix(ROOT / 'server14.sh'))}; "
        code += "sb14_root(){ :; }; systemctl(){ echo UNEXPECTED_SERVICE >&2; return 98; }; "
        code += "rc-service(){ echo UNEXPECTED_SERVICE >&2; return 98; }; "
        code += extra + "; " if extra else ""
        code += "sb14_main " + " ".join(shlex.quote(unix(x) if isinstance(x, Path) else str(x)) for x in args)
        proc = subprocess.run([self.bash, "-c", code], env=env or self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        # Logs use only offline fixture credentials, never production server credentials.
        LOG.append({"command": [str(x) for x in args], "test": self.id(), "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
        self.assertNotIn("UNEXPECTED_SERVICE", proc.stderr)
        if expected is not None:
            self.assertEqual(proc.returncode, expected, proc.stderr + proc.stdout)
        return proc

    def render(self):
        dest = self.dir / "rendered.json"
        self.call("render", self.parameters, dest)
        return dest, json.loads(dest.read_text(encoding="utf-8"))

    def apply(self):
        self.call("apply", self.parameters)
        return self.dir / "sb.json"

    def test_embedded_template_is_exact_reference(self):
        self.assertEqual(json.loads(self.call("template").stdout), self.reference)
        self.assertEqual(set(self.reference), {"certificate_providers", "inbounds"})

    def test_bootstrap_hash_and_help(self):
        script = (ROOT / "sb.sh").read_text(encoding="utf-8")
        self.assertIn(hashlib.sha256((ROOT / "server14.sh").read_bytes()).hexdigest(), script)
        p = subprocess.run([self.bash, unix(ROOT / "sb.sh"), "--help"], env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("render PARAMETERS.json", p.stdout)

    def test_render_changes_only_deployment_parameters(self):
        path, config = self.render()
        expected = copy.deepcopy(self.reference)
        provider = expected["certificate_providers"][0]
        provider["domain"] = self.params["domain"]
        provider["email"] = self.params["email"]
        provider["dns01_challenge"]["api_token"] = self.params["cloudflare_api_token"]
        generated = {i["tag"]: i for i in config["inbounds"]}
        for inbound in expected["inbounds"]:
            actual = generated[inbound["tag"]]
            for user, new_user in zip(inbound.get("users", []), actual.get("users", [])):
                for field in ("uuid", "password"):
                    if field in user:
                        user[field] = new_user[field]
            if "password" in inbound:
                inbound["password"] = actual["password"]
            if "obfs" in inbound:
                inbound["obfs"]["password"] = actual["obfs"]["password"]
            tls = inbound.get("tls", {})
            if "reality" in tls:
                tls["server_name"] = self.params["reality_server"]
                tls["reality"]["handshake"]["server"] = self.params["reality_server"]
                for field in ("private_key", "short_id"):
                    tls["reality"][field] = actual["tls"]["reality"][field]
            elif "certificate_provider" in tls:
                tls["server_name"] = self.params["domain"]
            if inbound["type"] == "shadowtls":
                inbound["handshake"]["server"] = self.params["reality_server"]
        self.assertEqual(config, expected)
        self.assertEqual(len(base64.b64decode(config["inbounds"][-1]["password"])), 32)
        self.assertNotEqual(config["inbounds"][0]["users"][0]["uuid"], self.reference["inbounds"][0]["users"][0]["uuid"])
        self.assertEqual(len(config["inbounds"]), 10)
        self.call("check", path)  # Real core validates all ten protocol types and the provider.

    def test_overrides_and_json_escaping(self):
        self.params["ports"] = {"trojan-in": 18443}
        self.params["cloudflare_api_token"] = 'offline-"token\\with-escapes'
        self.write("parameters.json", self.params)
        _, c = self.render()
        self.assertEqual(c["certificate_providers"][0]["dns01_challenge"]["api_token"], self.params["cloudflare_api_token"])
        self.assertEqual(next(x for x in c["inbounds"] if x["tag"] == "trojan-in")["listen_port"], 18443)

    def test_invalid_parameters_never_write_output(self):
        cases = [
            {"cloudflare_api_token": "YOUR_CLOUDFLARE_API_TOKEN"}, {"domain": "test.com"},
            {"ports": {"unknown": 443}}, {"ports": {"trojan-in": "444"}},
            {"ports": {"trojan-in": 0}}, {"ports": {"trojan-in": 65536}},
            {"ports": {"trojan-in": 443}}, {"dns": {}},
        ]
        for patch in cases:
            with self.subTest(patch=patch):
                self.write("parameters.json", dict(self.params, **patch))
                dest = self.dir / "invalid.json"
                result = self.call("render", self.parameters, dest, expected=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(dest.exists())

    def test_render_never_overwrites_output(self):
        dest, _ = self.render()
        before = dest.read_bytes()
        self.call("render", self.parameters, dest, expected=1)
        self.assertEqual(dest.read_bytes(), before)

    def test_reject_old_core(self):
        result = self.call("template")
        self.assertTrue(result.stdout)
        # Stub only version output to verify the minimum-version gate, not validation success.
        fake = self.dir / "old-core"
        fake.write_text('#!/bin/bash\necho "sing-box version 1.13.21"\n', encoding="utf-8")
        fake.chmod(0o700)
        env = dict(self.env, SB14_BIN=unix(fake))
        result = self.call("render", self.parameters, self.dir / "x.json", expected=1, env=env)
        self.assertIn(">= 1.14", result.stderr)

    def test_apply_backups_and_failed_check_preserves_config(self):
        config = self.apply()
        before = config.read_bytes()
        self.call("apply", self.parameters, expected=1, extra="sb14_check(){ return 42; }")
        self.assertEqual(config.read_bytes(), before)
        self.call("set-port", "trojan-in", "18443")
        backups = list(self.dir.glob("sb.json.bak.*"))
        self.assertTrue(any(p.read_bytes() == before for p in backups if not p.name.endswith(".sha256")))
        self.assertNotEqual(config.read_bytes(), before)
        self.call("check")

    def test_port_edits_no_internal_detour_or_duplicate(self):
        config = self.apply()
        before = config.read_bytes()
        for tag, port in [("shadowtls-ss-in", "10001"), ("unknown", "10002"), ("trojan-in", "443"), ("trojan-in", "65536"), ("trojan-in", "no")]:
            with self.subTest(tag=tag, port=port):
                self.call("set-port", tag, port, expected=1)
                self.assertEqual(config.read_bytes(), before)
        self.call("set-port", "trojan-in", "05443")
        self.call("check")

    def test_reality_certificate_and_rotation(self):
        config = self.apply()
        before = json.loads(config.read_text())
        self.call("set-reality", "www.microsoft.com")
        after = json.loads(config.read_text())
        for i in after["inbounds"]:
            if "reality" in i.get("tls", {}):
                self.assertEqual(i["tls"]["reality"]["handshake"]["server"], "www.microsoft.com")
        self.assertEqual(after["inbounds"][2]["handshake"]["server"], "www.microsoft.com")
        self.call("rotate-credentials")
        rotated = json.loads(config.read_text())
        self.assertNotEqual(rotated["inbounds"][0]["users"], before["inbounds"][0]["users"])
        self.assertEqual(rotated["inbounds"][0]["tls"]["server_name"], "www.microsoft.com")
        self.params["domain"] = "new.example.org"
        self.write("parameters.json", self.params)
        self.call("set-certificate", self.parameters)
        c = json.loads(config.read_text())
        self.assertEqual(c["inbounds"][0]["users"], rotated["inbounds"][0]["users"])
        self.assertEqual(c["certificate_providers"][0]["domain"], "new.example.org")
        self.assertTrue(all(i["tls"]["server_name"] == "new.example.org" for i in c["inbounds"] if "certificate_provider" in i.get("tls", {})))
        self.call("check")

    def test_restore_in_separate_copy(self):
        config = self.apply()
        original = config.read_bytes()
        self.call("set-port", "trojan-in", "18443")
        modified = config.read_bytes()
        backup = next(p for p in self.dir.glob("sb.json.bak.*") if not p.name.endswith(".sha256"))
        recovery = self.dir / "recovery"
        recovery.mkdir()
        (recovery / "sb.json").write_bytes(modified)
        env = dict(self.env, SB14_DIR=unix(recovery))
        self.call("restore", backup, env=env)
        self.assertEqual((recovery / "sb.json").read_bytes(), original)
        self.assertEqual(config.read_bytes(), modified)  # Keep the final modified config intact.

    def test_summary_does_not_disclose_credentials(self):
        self.apply()
        result = self.call("summary")
        self.assertIn("naive-in", result.stdout)
        self.assertNotIn("offline-only-token", result.stdout)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        if os.environ.get("SB14_TEST_LOG"):
            Path(os.environ["SB14_TEST_LOG"]).write_text(json.dumps(LOG, ensure_ascii=False, indent=2), encoding="utf-8")
