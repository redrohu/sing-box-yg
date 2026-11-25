"""Real transaction/publish functions with local files and failing command substitutes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.parse import parse_qs, quote, urlsplit

from config_harness import ROOT, BASH, CORE_ROOT, JQ, bashpath, function, generate_vps, parameters


class SubscriptionSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(os.environ.get('SB_UNDER_TEST', ROOT / 'sb.sh')).read_text(encoding='utf8')
        cls.output = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='subscription-safety-'))) / 'subscription-safety'
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        (cls.output / 'commands.json').write_text(json.dumps(cls.records, ensure_ascii=False, indent=2), encoding='utf8')

    def run_script(self, name, names, body, prepare=None):
        d = self.output / name
        d.mkdir(exist_ok=True)
        if prepare:
            prepare(d)
        source = self.source.replace('/etc/s-box', bashpath(d))
        helpers = ''.join(function(source, n) for n in names)
        f = d / 'run.sh'
        f.write_text('set +e\nred(){ echo "$*" >&2; }; green(){ :; }; white(){ :; }; yellow(){ :; }\n' + helpers + body, encoding='utf8', newline='\n')
        cmd = [BASH, bashpath(f)]
        p = subprocess.run(cmd, cwd=d, capture_output=True, timeout=90)
        self.records.append(dict(command=cmd, cwd=str(d), exit_code=p.returncode, stdout=p.stdout.decode('utf8', 'replace'), stderr=p.stderr.decode('utf8', 'replace')))
        return d, p

    def test_failed_renderer_keeps_previous_exports(self):
        def seed(d):
            for name in ['jhsub.txt', 'vl_reality.txt', 'clmi.yaml', 'sbox.json']:
                (d / name).write_text('old-' + name)
        d, p = self.run_script('renderer-fail', ['sbshare'], '''
node_suffix_load(){ :; }; result_vl_vm_hy_tu(){ return 1; }
sbshare
''', seed)
        self.assertNotEqual(p.returncode, 0)
        for name in ['jhsub.txt', 'vl_reality.txt', 'clmi.yaml', 'sbox.json']:
            self.assertEqual((d / name).read_text(), 'old-' + name)
        self.assertFalse(list(d.glob('share-stage.*')))

    def test_late_client_failure_does_not_publish_earlier_links(self):
        def seed(d):
            for name in ['jhsub.txt', 'vl_reality.txt', 'clmi.yaml']:
                (d / name).write_text('old-' + name)
        d, p = self.run_script('late-fail', ['sbshare'], '''
node_suffix_load(){ :; }; result_vl_vm_hy_tu(){ :; }
resvless(){ echo new > "$SB_EXPORT_DIR/vl_reality.txt"; }
resvmess(){ :; }; reshy2(){ :; }; restu5(){ :; }; resan(){ :; }
sb_client(){ return 1; }; sbnh=1.14
sbshare
''', seed)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual((d / 'vl_reality.txt').read_text(), 'old-vl_reality.txt')
        self.assertEqual((d / 'jhsub.txt').read_text(), 'old-jhsub.txt')

    def test_commit_failure_rolls_back_and_unlocks(self):
        def seed(d):
            (d / 'stage').mkdir()
            for name in ['sbox.json', 'clmi.yaml', 'obsolete.txt']:
                (d / name).write_text('old-' + name)
            for name in ['sbox.json', 'clmi.yaml']:
                (d / 'stage' / name).write_text('new-' + name)
        d, p = self.run_script('commit-fail', ['sb_exports_commit'], '''
mv(){ if [[ $* == *clmi.yaml* && ! -f injected ]]; then touch injected; return 1; fi; command mv "$@"; }
sb_exports_commit "$PWD/stage" obsolete.txt sbox.json clmi.yaml
''', seed)
        self.assertNotEqual(p.returncode, 0)
        for name in ['sbox.json', 'clmi.yaml', 'obsolete.txt']:
            self.assertEqual((d / name).read_text(), 'old-' + name)
        self.assertFalse((d / '.exports.lock').exists())

    def test_success_removes_only_managed_stale_outputs(self):
        def seed(d):
            (d / 'stage').mkdir()
            (d / 'stage/sbox.json').write_text('new')
            (d / 'obsolete.txt').write_text('old')
            (d / 'unrelated.txt').write_text('keep')
        d, p = self.run_script('commit-success', ['sb_exports_commit'], 'sb_exports_commit "$PWD/stage" sbox.json obsolete.txt\n', seed)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((d / 'sbox.json').read_text(), 'new')
        self.assertFalse((d / 'obsolete.txt').exists())
        self.assertEqual((d / 'unrelated.txt').read_text(), 'keep')

    def test_rejected_client_version_keeps_yaml_and_json(self):
        d = generate_vps(self.source, self.output / 'version-fail')
        before = {n: (d / n).read_bytes() for n in ['sbox.json', 'clmi.yaml']}
        (d / 'node_suffix.conf').write_text('new-name')
        names = ['sb_exports_commit', 'node_suffix_valid', 'node_suffix_load', 'sb_client_profile', 'sb_client']
        _, p = self.run_script('version-fail', names, parameters(d) + '''
SB_CLIENT_VERSION=1.10; sbnh=1.14; red(){ echo "$*" >&2; }
ps(){ :; }
sb_client
''')
        self.assertNotEqual(p.returncode, 0)
        for name, contents in before.items():
            self.assertEqual((d / name).read_bytes(), contents)

    def test_git_failure_never_announces_success(self):
        for failure in ['add', 'commit', 'push']:
            with self.subTest(failure=failure):
                def seed(d):
                    (d / '.git').mkdir(exist_ok=True)
                d, p = self.run_script('git-' + failure, ['gitlabsubgo'], '''
git(){
case "$1" in
add) [[ FAIL != add ]] ;;
diff) return 1 ;;
commit) [[ FAIL != commit ]] ;;
*) return 0 ;;
esac
}
gitlab_push(){ echo called > push-called; [[ FAIL != push ]]; }
clsbshow(){ echo success > success-announced; }
gitlabsubgo
'''.replace('FAIL', failure), seed)
                self.assertNotEqual(p.returncode, 0)
                self.assertFalse((d / 'success-announced').exists())
                if failure != 'push':
                    self.assertFalse((d / 'push-called').exists())

    def test_askpass_avoids_force_and_token_in_argv(self):
        def seed(d):
            (d / 'gitlabtoken.txt').write_text('TEST_TOKEN_NOT_REAL')
            (d / 'gitlab_ml_ml').write_text(':custom-branch')
        d, p = self.run_script('askpass', ['gitlab_push'], '''
git(){
case "$1 $2" in
"remote get-url") echo 'https://TEST_TOKEN_NOT_REAL@gitlab.com/user/project.git' ;;
"remote set-url") printf '%s\\n' "$*" >> argv ;;
"-c credential.helper=")
printf '%s\\n' "$*" >> argv
[[ $("$GIT_ASKPASS" Username) == oauth2 ]] || return 7
[[ $("$GIT_ASKPASS" Password) == TEST_TOKEN_NOT_REAL ]] || return 8 ;;
esac
}
gitlab_push
''', seed)
        self.assertEqual(p.returncode, 0, p.stderr)
        args = (d / 'argv').read_text()
        self.assertNotIn('TEST_TOKEN_NOT_REAL', args)
        self.assertNotIn('push -f', args)
        self.assertIn('HEAD:refs/heads/custom-branch', args)
        self.assertFalse(list(d.glob('git-askpass.*')))

    def test_failed_gitlab_setup_restores_old_credentials_and_repo(self):
        def seed(d):
            (d / '.git').mkdir()
            (d / '.git/old-marker').write_text('old-repo')
            (d / 'gitlabtoken.txt').write_text('OLD_TEST_TOKEN')
            (d / 'gitlab_ml_ml').write_text(':old-branch')
        d, p = self.run_script('setup-fail', ['gitlabsub'], '''
readp(){ case "$2" in
menu) menu=1;; email) email=test@example.org;; token) token=NEW_TEST_TOKEN;;
userid) userid=testuser;; project) project=testproject;; gitlabml) gitlabml=;; esac; }
sbshare(){ :; }
git(){ case "$1" in init) mkdir .git;; branch) echo main;; esac; return 0; }
gitlab_push(){ return 1; }
clsbshow(){ touch should-not-announce; }
gitlabsub
''', seed)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual((d / '.git/old-marker').read_text(), 'old-repo')
        self.assertEqual((d / 'gitlabtoken.txt').read_text(), 'OLD_TEST_TOKEN')
        self.assertEqual((d / 'gitlab_ml_ml').read_text(), ':old-branch')
        self.assertFalse((d / 'should-not-announce').exists())

    def test_local_configs_remain_viewable_without_gitlab_setup(self):
        def seed(d):
            (d / 'clmi.yaml').write_text('LOCAL_MIHOMO_CONFIG\n')
            (d / 'sbox.json').write_text('{"marker":"LOCAL_SINGBOX_CONFIG"}\n')
        d, p = self.run_script('local-without-gitlab', ['clash_sb_share'], '''
readp(){ menu=2; }; sleep(){ :; }; sbactive(){ :; }; sbshare(){ :; }
gitlabsubgo(){ touch unexpected-push-attempt; return 1; }
clash_sb_share
''', seed)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((d / 'unexpected-push-attempt').exists())
        self.assertIn('LOCAL_MIHOMO_CONFIG', p.stdout.decode('utf8', 'replace'))
        self.assertIn('LOCAL_SINGBOX_CONFIG', p.stdout.decode('utf8', 'replace'))

    def test_gitlab_url_encoding_keeps_token_out_of_jq_argv(self):
        token = 'FAKE+TOKEN&NAME#WITH=SYMBOLS'
        jq_command = '"' + bashpath(JQ or CORE_ROOT / 'jq.exe') + '" -b' if os.name == 'nt' else 'command jq'
        body = '''
readp(){ case "$2" in
menu) menu=1;; email) email=test@example.org;; token) token='FAKE+TOKEN&NAME#WITH=SYMBOLS';;
userid) userid=group/subgroup;; project) project=testproject;; gitlabml) gitlabml='release#one';; esac; }
sbshare(){ :; }
git(){ case "$1" in
init) mkdir .git;; branch) echo main;; check-ref-format) command git "$@";; esac; return 0; }
gitlab_push(){ :; }; clsbshow(){ :; }
jq(){ printf '<%s>' "$@" >> jq-argv; printf '\\n' >> jq-argv; __JQ__ "$@"; }
gitlabsub
'''.replace('__JQ__', jq_command)
        d, p = self.run_script('encoded-gitlab-url', ['gitlabsub'], body)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn(token, (d / 'jq-argv').read_text())
        self.assertNotIn(token, (p.stdout + p.stderr).decode('utf8', 'replace'))
        for name in ['sing_box_gitlab.txt', 'clash_meta_gitlab.txt', 'jh_sub_gitlab.txt']:
            url = urlsplit((d / name).read_text().strip())
            self.assertIn('/projects/' + quote('group/subgroup/testproject', safe='') + '/', url.path)
            self.assertEqual(url.fragment, '')
            query = parse_qs(url.query)
            self.assertEqual(query['ref'], ['release#one'])
            self.assertEqual(query['private_token'], [token])


if __name__ == '__main__':
    unittest.main()
