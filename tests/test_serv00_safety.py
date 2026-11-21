"""Local-only failure injection; HTTP, process, package and service operations are mocked."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from config_harness import ROOT, BASH, function

NODE = os.environ.get('NODE_BIN') or shutil.which('node')
HARNESS = r"""
const assert=require('assert'),{createApp}=require(process.argv[2]);
const TOKEN='a'.repeat(64),UUID='11111111-2222-3333-4444-555555555555';
function setup(overrides={},env={}){
 const layers=[],calls=[],pending=[],logs=[];
 const app={use(fn){layers.push({fn})},post(route,fn){layers.push({method:'POST',route,fn})},get(route,fn){layers.push({method:'GET',route,fn})}};
 const files={'.serv00-management-token':TOKEN,'UUID.txt':UUID,'sb.txt':'fakecore','ag.txt':'fakeargo','list.txt':'SUBSCRIPTION',...overrides};
 const originalError=console.error;console.error=(...args)=>logs.push(args.join(' '));
 createApp({express:()=>app,env,home:'/virtual',username:'test',
  fs:{readFileSync(file){const key=String(file).split(/[\\/]/).pop();if(!(key in files))throw Error('missing');return files[key]}},
  execFile(cmd,args,options,cb){calls.push({cmd,args,options});if(cmd==='bash')pending.push(cb);else if(cmd==='pgrep'||cmd==='pkill')cb(null,'SENSITIVE_TOKEN');else throw Error(cmd)}});
 function dispatch(method,path,authorization=''){
  const req={method,path,params:{},get:()=>authorization};
  const res={code:200,body:undefined,headers:{},status(c){this.code=c;return this},set(k,v){this.headers[k]=v;return this},type(){return this},send(b){this.body=b;return this},json(b){this.body=b;return this}};
  let i=0;function next(){while(i<layers.length){const l=layers[i++];if(!l.method)return l.fn(req,res,next);if(l.method!==method)continue;
   if(l.route==='/list/:key'){const m=path.match(/^\/list\/([^/]+)\/?$/i);if(!m)continue;req.params.key=m[1]}
   else if(l.route.toLowerCase()!==path.replace(/\/+$/,'').toLowerCase())continue;
   return l.fn(req,res,next)}}next();return res;
 }
 return{calls,pending,logs,dispatch,restore(){console.error=originalError}};
}
"""


class Serv00Safety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ.get('SB_TEST_OUTPUT', tempfile.mkdtemp(prefix='serv00-safety-'))) / 'serv00-safety'
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.records = []
        cls.sources = {name: (ROOT / name).read_text(encoding='utf8') for name in ('serv00.sh', 'serv00keep.sh')}

    @classmethod
    def tearDownClass(cls):
        (cls.output / 'commands.json').write_text(json.dumps(cls.records, ensure_ascii=False, indent=2), encoding='utf8')

    def execute(self, command, stdin, cwd=None):
        p = subprocess.run(command, input=stdin, text=True, encoding='utf8', errors='replace', capture_output=True, cwd=cwd or ROOT)
        self.records.append(dict(command=command, cwd=str(cwd or ROOT), stdin=stdin, exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr))
        self.assertEqual(p.returncode, 0, self.records[-1])
        return p

    def node(self, body, app_path=None):
        if not NODE:
            self.skipTest('Node.js unavailable')
        return self.execute([NODE, '-', str(app_path or ROOT / 'app.js')], HARNESS + '\n' + body)

    def shell(self, body):
        if not BASH or not (Path(BASH).exists() or shutil.which(BASH)):
            self.skipTest('Bash unavailable')
        with tempfile.TemporaryDirectory(prefix='serv00-fixture-') as directory:
            return self.execute([BASH, '--noprofile', '--norc', '-s'], 'set -e\n' + body, Path(directory))

    def test_unauthenticated_and_unconfigured_have_no_side_effects(self):
        self.node(r"""
const s=setup();for(const path of ['/up','/re','/rp','/jc','/UP','/up/'])for(const method of ['GET','POST']){
 assert.strictEqual(s.dispatch(method,path).code,401);assert.strictEqual(s.dispatch(method,path,'Bearer '+UUID).code,401)}
assert.strictEqual(s.calls.length,0);s.restore();
const u=setup({'.serv00-management-token':''});assert.strictEqual(u.dispatch('POST','/up','Bearer '+TOKEN).code,503);assert.strictEqual(u.calls.length,0);u.restore();
console.log('Wrong/missing authentication and subscription UUID rejected with zero commands.');
""")

    def test_authenticated_get_rejected_and_health_read_only(self):
        self.node(r"""
const s=setup();for(const path of ['/up','/re','/rp','/jc','/UP','/up/'])assert.strictEqual(s.dispatch('GET',path,'Bearer '+TOKEN).code,405);
assert.strictEqual(s.dispatch('GET','/healthz').body,'ok');assert.strictEqual(s.calls.length,0);s.restore();
console.log('Authenticated GET rejected; healthz has zero command side effects.');
""")

    def test_reset_waits_serializes_and_redacts_failures(self):
        self.node(r"""
const s=setup(),r=s.dispatch('POST','/rp','Bearer '+TOKEN);assert.strictEqual(r.body,undefined);
assert.strictEqual(s.dispatch('POST','/up','Bearer '+TOKEN).code,409);assert.strictEqual(s.calls.length,1);assert.ok(s.calls[0].args[0].endsWith('webport.sh'));
s.pending.shift()(null,'SENSITIVE_TOKEN','');assert.strictEqual(r.code,200);assert.strictEqual(r.body.ok,true);
const f=s.dispatch('POST','/rp','Bearer '+TOKEN);s.pending.shift()(Error('SENSITIVE_TOKEN'),'SENSITIVE_TOKEN','SENSITIVE_TOKEN');
assert.strictEqual(f.code,500);assert.ok(!JSON.stringify(f).includes('SENSITIVE_TOKEN'));assert.ok(!s.logs.join('').includes('SENSITIVE_TOKEN'));s.restore();
console.log('POST reset waits, serializes actions, and redacts child output on failure.');
""")

    def test_restart_status_and_subscription(self):
        self.node(r"""
const s=setup(),r=s.dispatch('POST','/re','Bearer '+TOKEN);assert.deepStrictEqual(s.calls[0].args,['-x','fakecore']);assert.strictEqual(s.calls[0].cmd,'pkill');
s.pending.shift()(null,'','');assert.strictEqual(r.body.ok,true);
assert.deepStrictEqual(s.dispatch('POST','/jc','Bearer '+TOKEN).body,{sing_box:'running',argo:'running'});assert.ok(s.calls.every(c=>c.cmd!=='ps'));
assert.strictEqual(s.dispatch('GET','/list/'+UUID).body,'SUBSCRIPTION');assert.strictEqual(s.dispatch('GET','/list/wrong').code,404);s.restore();
console.log('Exact process restart, redacted status, and UUID subscription compatibility verified.');
""")

    def test_old_installer_sed_remains_harmless(self):
        # Already deployed keepers download main/app.js every run and still perform
        # these exact positional substitutions. Exercise them, not a rewritten mock.
        source = (ROOT / 'app.js').read_text(encoding='utf8')
        lines = source.splitlines()
        for number in (15, 59, 90):
            self.assertTrue(lines[number - 1].lstrip().startswith('// LEGACY_SED_GUARD_' + str(number)))
        if not BASH or not (Path(BASH).exists() or shutil.which(BASH)):
            self.skipTest('Bash unavailable')
        with tempfile.TemporaryDirectory(prefix='serv00-old-installer-') as directory:
            directory = Path(directory)
            (directory / 'app.original.js').write_text(source, encoding='utf8')
            self.execute([BASH, '--noprofile', '--norc', '-s'], r"""
set -e
sed -e '15s/name/s14/g' \
    -e '59s/key/11111111-2222-3333-4444-555555555555/g' \
    -e '90s/name/testuser/g' -e '90s/where/s14/g' app.original.js > app.legacy.js
""", directory)
            self.node(r"""
const s=setup();
for(const route of ['/up','/re','/rp','/jc'])assert.strictEqual(s.dispatch('GET',route).code,401);
assert.strictEqual(s.dispatch('GET','/healthz').body,'ok');
assert.strictEqual(s.dispatch('GET','/list/'+UUID).body,'SUBSCRIPTION');
assert.strictEqual(s.calls.length,0);
const r=s.dispatch('POST','/up','Bearer '+TOKEN);assert.strictEqual(r.body,undefined);
s.pending.shift()(null,'','');assert.strictEqual(r.body.ok,true);s.restore();
const unconfigured=setup({'.serv00-management-token':''});
assert.strictEqual(unconfigured.dispatch('GET','/up').code,503);
assert.strictEqual(unconfigured.dispatch('POST','/rp','Bearer '+UUID).code,503);
assert.strictEqual(unconfigured.calls.length,0);unconfigured.restore();
console.log('Actual legacy sed changes comments only: routes work and management stays fail-closed.');
""", directory / 'app.legacy.js')

    def test_passenger_and_direct_start_but_plain_import_has_no_side_effects(self):
        if not NODE:
            self.skipTest('Node.js unavailable')
        self.execute([NODE, '-', str(ROOT / 'app.js')], r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2],'utf8');
function simulate(main,passenger){
 const listeners=[],timers=[],commands=[],loaded={exports:{}};
 const app={use(){},get(){},post(){},listen(port,callback){listeners.push({port,callback})}};
 function fakeRequire(name){
  if(name==='express')return ()=>app;
  if(name==='os')return {homedir:()=>'/virtual',userInfo:()=>({username:'test'})};
  if(name==='child_process')return {execFile(...args){commands.push(args)}};
  if(name==='fs')return {readFileSync(){throw Error('No configured files')}};
  return require(name);
 }
 fakeRequire.main=main?loaded:{};
 const context={require:fakeRequire,module:loaded,Buffer,process:{env:{}},
  console:{log(){},error(){}},setInterval(callback,delay){timers.push({callback,delay})}};
 if(passenger)context.PhusionPassenger={};
 vm.runInNewContext(source,context);
 assert.strictEqual(typeof loaded.exports.createApp,'function');
 const starts=main||passenger;
 assert.strictEqual(listeners.length,starts?1:0);
 assert.strictEqual(timers.length,starts?1:0);
 assert.strictEqual(commands.length,0);
 if(starts){
  assert.strictEqual(listeners[0].port,3000);assert.strictEqual(timers[0].delay,135*60*1000);
  listeners[0].callback();assert.strictEqual(commands.length,1);
  assert.strictEqual(commands[0][0],'bash');assert.ok(commands[0][1][0].endsWith('serv00keep.sh'));
 }
}
simulate(false,false);simulate(true,false);simulate(false,true);
console.log('Direct Node and Passenger require register listen/timer; plain import stays inert. No real listen/exec.');
""")

    def test_download_timeout_preserves_original(self):
        for name, source in self.sources.items():
            with self.subTest(script=name):
                self.shell(function(source, 'download_with_fallback') + r"""
curl(){ local out;while [ "$#" -gt 0 ];do if [ "$1" = -o ];then shift;out=$1;fi;shift;done;printf '\177ELFpartial' > "$out";return 28; }
wget(){ return 1; }
printf ORIGINAL > core
if download_with_fallback https://example.invalid/mocked core;then exit 1;fi
[ "$(cat core)" = ORIGINAL ];[ "$(find . -name '*.download.*' | wc -l)" -eq 0 ]
echo 'Timed-out partial rejected; original preserved.'
""")

    def test_download_fallback_and_error_page(self):
        for source in self.sources.values():
            self.shell(function(source, 'download_with_fallback') + r"""
curl(){ return 28; }
wget(){ local out;while [ "$#" -gt 0 ];do if [ "$1" = -O ];then shift;out=$1;fi;shift;done;printf '\177ELFtest_payload' > "$out"; }
download_with_fallback https://example.invalid/mocked core
[ "$(od -An -tx1 -N4 core | tr -d ' \n')" = 7f454c46 ]
curl(){ local out;while [ "$#" -gt 0 ];do if [ "$1" = -o ];then shift;out=$1;fi;shift;done;printf '<html>Error</html>' > "$out"; }
if download_with_fallback https://example.invalid/mocked core;then exit 1;fi
[ "$(od -An -tx1 -N4 core | tr -d ' \n')" = 7f454c46 ]
echo 'Fallback atomic success; error page rejected.'
""")

    def test_fixed_healthy_tunnel_avoids_http_and_restart(self):
        for source in self.sources.values():
            self.shell(function(source, 'serv00_argo_needs_restart') + r"""
WORKDIR=$PWD;ARGO_DOMAIN=fixed.example.test;printf fakeargo > ag.txt
pgrep(){ return 0; };curl(){ echo UNEXPECTED_HTTP >&2;return 99; }
if serv00_argo_needs_restart;then exit 1;fi
pgrep(){ return 1; };serv00_argo_needs_restart
echo 'Healthy fixed tunnel preserved without HTTP; absent process needs restart.'
""")

    def test_argo_retry_argument_boundaries_and_failure(self):
        for source in self.sources.values():
            self.shell(function(source, 'cfgo') + r"""
declare -A FILE_MAP
printf fakeargo > ag.txt;printf '#!/bin/sh\nexit 1\n' > fakeargo;chmod +x fakeargo
ARGO_AUTH='MOCK TOKEN WITH SPACES';vmess_port=18080
red(){ echo "$*"; };green(){ echo "$*"; };pkill(){ :; }
nohup(){ printf '%s\0' "$@" >> argv.bin; };sleep(){ command sleep 0.03; }
pgrep(){ if [ -e retried ];then return 0;else touch retried;return 1;fi; }
cfgo;wait
[ "$(tr '\0' '\n' < argv.bin | grep -c '^MOCK TOKEN WITH SPACES$')" -eq 2 ]
pgrep(){ return 1; };if cfgo;then exit 1;fi;wait
echo 'Retry argv preserved; repeated startup failure returns nonzero.'
""")

    def test_token_persistence_and_no_line_number_substitution(self):
        for source in self.sources.values():
            self.shell(function(source, 'serv00_management_setup') + r"""
HOME=$PWD;red(){ echo "$*" >&2; };openssl(){ printf '%064d\n' 0; }
serv00_management_setup;cp .serv00-management-token expected
openssl(){ return 99; };serv00_management_setup
cmp expected .serv00-management-token
[ "$(wc -c < .serv00-management-token)" -eq 65 ]
echo 'Independent management token created once and preserved.'
""")
            self.assertNotRegex(source, r'sed -i[^\n]*"(?:15|59|90)s/')
            self.assertNotIn('net/up"', source)

    def test_app_download_and_syntax_failure_preserve_previous(self):
        for source in self.sources.values():
            self.shell(function(source, 'serv00_install_management_app') + r"""
keep_path=$PWD;red(){ :; };green(){ :; };serv00_management_setup(){ :; }
printf ORIGINAL > app.js;curl(){ return 22; }
if serv00_install_management_app;then exit 1;fi
[ "$(cat app.js)" = ORIGINAL ]
curl(){ local out;while [ "$#" -gt 0 ];do if [ "$1" = -o ];then shift;out=$1;fi;shift;done;printf 'invalid syntax' > "$out"; }
node(){ return 1; };if serv00_install_management_app;then exit 1;fi
[ "$(cat app.js)" = ORIGINAL ]
echo 'HTTP and syntax errors preserve installed management app.'
""")

    def test_workers_http_failure_and_authenticated_success(self):
        if not NODE:
            self.skipTest('Node.js unavailable')
        self.execute([NODE, '-', str(ROOT / 'workers_keep.js')], r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),source=fs.readFileSync(process.argv[2],'utf8');
async function test(ok){let handler,promise;const calls=[],logs=[];
 const context={URL,AbortController,setTimeout,clearTimeout,SERV00_TARGETS:JSON.stringify([{url:'https://example.invalid/up',token:'a'.repeat(64)}]),
 addEventListener(_,fn){handler=fn},console:{log(x){logs.push(x)},warn(x){logs.push(x)}},
 fetch:async(url,options)=>{calls.push({url,options});return{ok,status:ok?200:500,json:async()=>({ok:true})}}};
 vm.runInNewContext(source,context);handler({waitUntil(p){promise=p}});if(ok)await promise;else await assert.rejects(promise);
 assert.strictEqual(calls[0].options.method,'POST');assert.strictEqual(calls[0].options.redirect,'error');assert.strictEqual(calls[0].options.headers.Authorization,'Bearer '+'a'.repeat(64));
 assert.ok(!logs.join('').includes('a'.repeat(64)));if(!ok)assert.ok(!logs.some(x=>x.includes('✅')));
}
(async()=>{await test(false);await test(true);console.log('HTTP500 fails; successful POST authenticated and logs redacted.')})().catch(e=>{console.error(e);process.exitCode=1});
""")

    def test_kp_dependencies_are_synchronous(self):
        source = (ROOT / 'kp.sh').read_text(encoding='utf8')
        self.shell(function(source, 'ensure_dependencies') + r"""
installed=no
command(){ if [ "$1" = -v ];then if [ "$2" = apt-get ] || [ "$installed" = yes ];then return 0;fi;return 1;fi;builtin command "$@"; }
apt-get(){ echo "$1" >> steps;if [ "$1" = install ];then installed=yes;fi; }
ensure_dependencies;[ "$installed" = yes ];[ "$(wc -l < steps)" -eq 2 ]
echo 'Dependencies installed synchronously before account processing.'
""")
        self.assertIn('while IFS= read -r account', source)
        self.assertNotIn('with command: $remote_command', source)
        self.assertNotIn('StrictHostKeyChecking=no', source)

    def test_kp_remote_values_are_quoted_and_not_logged(self):
        source = (ROOT / 'kp.sh').read_text(encoding='utf8')
        self.shell(function(source, 'run_remote_command') + r"""
SSH_OPTIONS=()
sshpass(){ cat > remote-input; }
run_remote_command n n test 'PASSWORD WITH SPACES' 'example.test;touch INJECTED' UUID 1 2 3 example.test fixed.test 'MOCK TOKEN WITH SPACES' > output
! grep -q 'MOCK TOKEN' output
# Evaluate only the generated export line, not its downloaded-script body.
head -n 1 remote-input > exports-only
bash -c '. ./exports-only; [ "$reym" = "example.test;touch INJECTED" ] && [ "$ARGO_AUTH" = "MOCK TOKEN WITH SPACES" ]'
[ ! -e INJECTED ]
echo 'Whitespace and shell metacharacters preserved as data; token not logged.'
""")

    def test_workflow_secret_is_data_not_shell_code(self):
        source = (ROOT / '.github/workflows/main.yml').read_text(encoding='utf8')
        script = source.split('run: |', 1)[1]
        self.assertNotIn('${{', script)
        self.assertIn('SERV00_TARGETS: ${{ secrets.http }}', source)
        self.assertIn('timeout=260', script)
        self.assertIn('max_workers=4', script)
        lines = script.splitlines()[2:-1]
        compile('\n'.join(line[10:] for line in lines), 'workflow-keepalive', 'exec')


if __name__ == '__main__':
    unittest.main()
