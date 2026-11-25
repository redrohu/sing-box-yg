"""Real update functions with isolated paths and mocked network/service boundaries.

SB_UNDER_TEST may point at a candidate sb.sh. No real services or network are used.
SB_UPDATE_TEST_LOG saves exact commands, output, exit status and file assertions.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import tarfile
import tempfile
import unittest

from config_harness import BASH, ROOT, CORE_ROOT, JQ, bashpath, function, run, RECORDS, save_records


SOURCE_PATH = Path(os.environ.get("SB_UNDER_TEST", ROOT / "sb.sh"))
SOURCE = SOURCE_PATH.read_text(encoding="utf8")


def core_script(version, invalid=False):
    return f'''#!/bin/bash
if [[ $1 == version ]]; then echo 'sing-box version {version}'; exit 0; fi
if [[ $1 == check ]]; then
  echo 'CHECK {version}' >&2
  {'echo "invalid candidate config" >&2; exit 1' if invalid else 'exit 0'}
fi
exit 1
'''


class UpdateSafety(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if os.environ.get("SB_UPDATE_TEST_LOG"):
            save_records(os.environ["SB_UPDATE_TEST_LOG"])

    def case(self, scenario, entry="upsbcroe", target="1.15.0", invalid=False):
        temp = tempfile.TemporaryDirectory(prefix="sb-update-test-")
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        box = directory / "s-box"
        bindir = directory / "usrbin"
        box.mkdir()
        bindir.mkdir()
        old = core_script("1.14.4")
        (box / "sing-box").write_text(old, encoding="utf8", newline="\n")
        (box / "sing-box").chmod(0o755)
        for name, data in {"sb.json": '{"marker":"CURRENT_CONFIG"}\n',
                           "sb10.json": '{"marker":"TEMPLATE10_CONFIG"}\n',
                           "sb11.json": '{"marker":"TEMPLATE11_CONFIG"}\n',
                           "v": "v26.11.17-fork.14\n"}.items():
            (box / name).write_text(data, encoding="utf8", newline="\n")
        (bindir / "sb").write_text("#!/bin/bash\necho OLD_SCRIPT\n", encoding="utf8", newline="\n")
        (bindir / "sb").chmod(0o755)
        version = "1.99.0" if scenario == "wrong_version" else target
        archive = directory / "asset.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            data = core_script(version, invalid).encode()
            info = tarfile.TarInfo(f"sing-box-{target}-linux-amd64/sing-box")
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
        if scenario == "corrupt":
            archive.write_bytes(b"not a tarball")
        if scenario == "traversal":
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("../../escape")
                info.size = 3
                tar.addfile(info, io.BytesIO(b"bad"))
        payload = directory / "script-payload"
        payload.write_text("#!/bin/bash\necho NEW_SCRIPT\n", encoding="utf8", newline="\n")
        if scenario in ("first_install", "script_first_install"):
            for file in list(box.iterdir()) + list(bindir.iterdir()):
                file.unlink()
        if scenario == "script_invalid":
            payload.write_text("#!/bin/bash\nif then\n", encoding="utf8", newline="\n")
        if scenario == "script_html":
            payload.write_text("<!doctype html>error\n", encoding="utf8", newline="\n")
        initial = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in list(box.iterdir()) + list(bindir.iterdir())}
        src = SOURCE.replace("/etc/s-box", bashpath(box)).replace("/usr/bin/sb", bashpath(bindir / "sb"))
        # Isolate all actual update helpers, including the real restart/check path.
        names = ["lnsb", "upsbyg", "upsbcroe", "inssb", "restartsb", "sb_config_check"]
        names += re.findall(r"^(sb_update_[A-Za-z0-9_]+)\(\)\s*\{", src, re.M)
        definitions = "\n".join(function(src, name) for name in dict.fromkeys(names))
        script = f'''#!/bin/bash
export LANG=C.UTF-8 LC_ALL=C.UTF-8
{('jq() { "' + bashpath(JQ or CORE_ROOT / 'jq.exe') + '" -b "$@"; }') if os.name == 'nt' else ''}
{('apk() { :; }; rc-service() { systemctl "$2" "$1"; }') if scenario == 'openrc' else ''}
# Deliberately no `set -e`: production menus also run without errexit.
{definitions}
red() {{ printf 'ERROR %s\\n' "$*" >&2; }}
green() {{ printf 'GREEN %s\\n' "$*"; }}
blue() {{ printf 'BLUE %s\\n' "$*"; }}
yellow() {{ :; }}
sleep() {{ :; }}
sb() {{ echo MENU; }}
sbactive() {{ :; }}
lapre() {{ inscore=1.14.4; latcore=1.15.0; precore=1.15.0-alpha.1; }}
cpu=amd64; sbnh=1.14; ANSWER=0
readp() {{
  ANSWER=$((ANSWER + 1))
  if (( ANSWER == 1 )); then printf -v "$2" '%s' {2 if entry == "inssb" else 3}; else printf -v "$2" '%s' {shlex.quote(target)}; fi
}}
sbshare() {{ echo SHARE >> commands.log; [[ {shlex.quote(scenario)} != share_fail ]]; }}
chown() {{ echo "CHOWN $*" >> commands.log; }}
mv() {{
  local args=("$@") count=$# src dst
  src=${{args[count-2]}}; dst=${{args[count-1]}}
  if [[ {shlex.quote(scenario)} == script_marker_commit_fail && $src == *'.version-update.'* ]]; then
    echo 'INJECT marker rename failure' >&2; return 1
  fi
  if [[ {shlex.quote(scenario)} == config_commit_fail && $src == *'.core-update.'*/sb.json ]]; then
    echo 'INJECT config rename failure' >&2; return 1
  fi
  command mv "$@"
}}
systemctl() {{
  echo "SYSTEMCTL $*" >> commands.log
  if [[ $1 == restart || $1 == is-active ]]; then
    version=$("{bashpath(box / 'sing-box')}" version)
    if [[ {shlex.quote(scenario)} == restart_fail && $version == *{target} ]]; then return 1; fi
    if [[ {shlex.quote(scenario)} == status_fail && $1 == is-active && $version == *{target} ]]; then return 1; fi
  fi
  return 0
}}
curl() {{
  printf 'CURL' >> commands.log; printf ' <%s>' "$@" >> commands.log; echo >> commands.log
  local out= url= arg
  while (( $# )); do
    arg=$1; shift
    case "$arg" in -o|--output) out=$1; shift;; https://*) url=$arg;; esac
  done
  if [[ $url == https://api.github.com/*/git/ref/heads/main ]]; then
    printf '%s\\n' '{{"object":{{"sha":"0123456789abcdef0123456789abcdef01234567"}}}}' > "$out"
    return 0
  fi
  if [[ $url == */version ]]; then
    [[ {shlex.quote(scenario)} == version_fail ]] && return 28
    if [[ -n $out ]]; then printf 'v26.11.21-fork.15更新内容\\ntest\\n' > "$out";
    else printf 'v26.11.21-fork.15更新内容\\ntest\\n'; fi
    return 0
  fi
  if [[ $url == */sb.sh ]]; then
    if [[ {shlex.quote(scenario)} == script_download_fail ]]; then : > "$out"; return 28; fi
    cp '{bashpath(payload)}' "$out"; return 0
  fi
  if [[ $url == *.tar.gz ]]; then
    if [[ {shlex.quote(scenario)} == download_fail ]]; then : > "$out"; return 28; fi
    cp '{bashpath(archive)}' "$out"; return 0
  fi
  echo 'UNEXPECTED NETWORK' >&2; return 99
}}
{entry}
rc=$?
printf 'RESULT_RC=%s SB_NH=%s\\n' "$rc" "$sbnh"
exit "$rc"
'''
        file = directory / "scenario.sh"
        file.write_text(script, encoding="utf8", newline="\n")
        p = run([BASH, bashpath(file)], cwd=directory)
        output = (p.stdout + p.stderr).decode("utf8", "replace")
        RECORDS[-1].update(scenario=scenario, entry=entry, source=str(SOURCE_PATH),
                           source_sha256=hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(), shell_input=script,
                           stdout_base64=base64.b64encode(p.stdout).decode(),
                           stderr_base64=base64.b64encode(p.stderr).decode(), initial_sha256=initial,
                           final_sha256={p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in list(box.iterdir()) + list(bindir.iterdir()) if p.is_file()},
                           mock_commands=(directory / "commands.log").read_text(encoding="utf8")
                           if (directory / "commands.log").exists() else "")
        return directory, p, output, initial

    def assert_preserved(self, directory, initial):
        for name, digest in initial.items():
            self.assertTrue((directory / name).is_file(), name)
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), digest, name)

    def test_script_download_failure_preserves_installed(self):
        d, p, _, before = self.case("script_download_fail", "lnsb")
        self.assertNotEqual(p.returncode, 0)
        self.assert_preserved(d, before)

    def test_script_syntax_failure_preserves_installed(self):
        d, p, _, before = self.case("script_invalid", "lnsb")
        self.assertNotEqual(p.returncode, 0)
        self.assert_preserved(d, before)

    def test_script_version_failure_does_not_commit(self):
        d, p, out, before = self.case("version_fail", "upsbyg")
        self.assertNotEqual(p.returncode, 0)
        self.assert_preserved(d, before)
        self.assertNotIn("升级成功", out)

    def test_script_success_and_tls_flags(self):
        d, p, out, _ = self.case("success", "upsbyg")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("NEW_SCRIPT", (d / "usrbin/sb").read_text())
        self.assertEqual((d / "s-box/v").read_text().strip(), "v26.11.21-fork.15")
        commands = (d / "commands.log").read_text()
        self.assertNotIn("insecure", commands)
        self.assertIn("<--fail>", commands)
        self.assertIn("<--proto> <=https>", commands)
        self.assertTrue(list((d / "s-box/backups").glob("*/SHA256SUMS")))

    def test_failed_core_download_preserves_binary_and_configs(self):
        d, p, out, before = self.case("download_fail")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)
        self.assertNotIn("成功升级/切换", out)

    def test_corrupt_core_archive_preserves_binary_and_configs(self):
        d, p, out, before = self.case("corrupt")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)

    def test_wrong_core_version_is_rejected(self):
        d, p, out, before = self.case("wrong_version")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)

    def test_candidate_config_check_before_commit(self):
        d, p, out, before = self.case("config_fail", invalid=True)
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)
        self.assertNotIn("SYSTEMCTL", (d / "commands.log").read_text())

    def test_restart_failure_rolls_back_and_restarts_old_core(self):
        d, p, out, before = self.case("restart_fail")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)
        commands = (d / "commands.log").read_text()
        self.assertGreaterEqual(commands.count("SYSTEMCTL restart sing-box"), 2)
        self.assertNotIn("SHARE", commands)
        self.assertNotIn("成功升级/切换", out)

    def test_status_failure_also_rolls_back(self):
        d, p, out, before = self.case("status_fail")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)

    def test_success_keeps_current_config_on_same_template_track(self):
        d, p, out, before = self.case("success")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("version 1.15.0", (d / "s-box/sing-box").read_text())
        self.assertEqual(hashlib.sha256((d / "s-box/sb.json").read_bytes()).hexdigest(), before["s-box/sb.json"])
        self.assertIn("SB_NH=1.15", out)
        self.assertIn("SHARE", (d / "commands.log").read_text())
        self.assertTrue(list((d / "s-box/backups").glob("*/SHA256SUMS")))

    def test_legacy_core_switch_uses_sb10_template(self):
        d, p, out, _ = self.case("success", target="1.10.7")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("TEMPLATE10_CONFIG", (d / "s-box/sb.json").read_text())
        self.assertIn("SB_NH=1.10", out)

    def test_failed_cross_track_switch_restores_current_config(self):
        d, p, out, before = self.case("restart_fail", target="1.10.7")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)
        self.assertIn("SB_NH=1.14", out)

    def test_subscription_failure_is_not_reported_as_full_success(self):
        d, p, out, _ = self.case("share_fail")
        self.assertNotEqual(p.returncode, 0, out)
        self.assertIn("version 1.15.0", (d / "s-box/sing-box").read_text())
        self.assertNotIn("成功升级/切换", out)
        self.assertIn("订阅", out)

    def test_script_html_is_rejected(self):
        d, p, _, before = self.case("script_html", "lnsb")
        self.assertNotEqual(p.returncode, 0)
        self.assert_preserved(d, before)

    def test_script_and_marker_pin_one_revision(self):
        d, p, out, _ = self.case("success", "lnsb")
        self.assertEqual(p.returncode, 0, out)
        commands = (d / "commands.log").read_text()
        self.assertIn("/0123456789abcdef0123456789abcdef01234567/sb.sh", commands)
        self.assertIn("/0123456789abcdef0123456789abcdef01234567/version", commands)

    def test_script_first_install_compatible(self):
        d, p, out, _ = self.case("script_first_install", "lnsb")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("NEW_SCRIPT", (d / "usrbin/sb").read_text())
        self.assertTrue((d / "s-box/v").is_file())

    def test_core_first_install_uses_verified_binary(self):
        d, p, out, _ = self.case("first_install", "inssb", target="1.10.7")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("version 1.10.7", (d / "s-box/sing-box").read_text())
        self.assertFalse((d / "s-box/sb.json").exists())

    def test_openrc_success(self):
        d, p, out, _ = self.case("openrc")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("SYSTEMCTL status sing-box", (d / "commands.log").read_text())

    def test_core_https_and_http_failure_check_flags(self):
        d, p, out, _ = self.case("success")
        self.assertEqual(p.returncode, 0, out)
        commands = (d / "commands.log").read_text()
        self.assertIn("<--fail>", commands)
        self.assertIn("<--proto> <=https>", commands)
        self.assertIn("<--proto-redir> <=https>", commands)
        self.assertNotIn("insecure", commands)

    def test_script_marker_commit_failure_restores_both_files(self):
        d, p, out, before = self.case("script_marker_commit_fail", "lnsb")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)
        self.assertNotIn("升级成功", out)

    def test_core_config_commit_failure_restores_old_binary(self):
        d, p, out, before = self.case("config_commit_fail")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)
        self.assertIn("SYSTEMCTL restart sing-box", (d / "commands.log").read_text())
        self.assertNotIn("SHARE", (d / "commands.log").read_text())

    def test_archive_path_traversal_rejected(self):
        d, p, out, before = self.case("traversal")
        self.assertNotEqual(p.returncode, 0, out)
        self.assert_preserved(d, before)
        self.assertFalse((d / "escape").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
