"""Execute only real configuration generators, never the installer/menu/system commands."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("BASH_BIN") or shutil.which("bash")
if os.name == "nt":
    BASH = os.environ.get("BASH_BIN", r"C:\Program Files\Git\bin\bash.exe")
CORE_ROOT = Path(os.environ.get("SB_TEST_CORES", str(Path(os.environ.get("TEMP", "/tmp")) / "sbcheck")))
RECORDS = []


def run(args, cwd=None, **kwargs):
    p = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, **kwargs)
    RECORDS.append(dict(command=[str(a) for a in args], cwd=str(cwd or ROOT),
                        exit_code=p.returncode, stdout=p.stdout.decode("utf8", "replace"),
                        stderr=p.stderr.decode("utf8", "replace")))
    return p


def bashpath(path):
    path = str(Path(path).resolve()).replace("\\", "/")
    return "/" + path[0].lower() + path[2:] if os.name == "nt" else path


def function(source, name):
    # Heredoc bodies and quoted JSON/braces must not be parsed as shell braces.
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(r"^" + re.escape(name) + r"\(\)\s*\{", line))
    depth, heredoc, result = 0, None, []
    for line in lines[start:]:
        result.append(line)
        if heredoc:
            if line.strip() == heredoc:
                heredoc = None
            continue
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)", line)
        if m and not line.lstrip().startswith("#"):
            heredoc = m[1]
        stripped = re.sub(r"'[^']*'|\"[^\"]*\"", "", line)
        depth += stripped.count("{") - stripped.count("}")
        if depth == 0:
            return "\n".join(result) + "\n"
    raise ValueError("unterminated function " + name)


def core(version):
    override = os.environ.get("SB_TEST_BIN_" + version.replace(".", "_"))
    if override:
        return Path(override)
    suffix = "windows-amd64/sing-box.exe" if os.name == "nt" else "linux-amd64/sing-box"
    return CORE_ROOT / ("sing-box-" + version + "-" + suffix)


def shell(script, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    jq = CORE_ROOT / "jq.exe"
    prelude = "set -e\n"
    if os.name == "nt":
        prelude += f'jq() {{ "{bashpath(jq)}" -b "$@"; }}\n'
    file = directory / "generate.sh"
    file.write_text(prelude + script, encoding="utf8", newline="\n")
    p = run([BASH, bashpath(file)], cwd=directory)
    if p.returncode:
        raise AssertionError(RECORDS[-1])
    return p


def parameters(directory):
    d = Path(directory).resolve().as_posix()
    return f'''
port_vl_re=11443; port_vm_ws=21443; port_hy2=31443; port_tu=41443; port_an=51443
uuid=11111111-2222-3333-4444-555555555555
ym_vl_re=www.apple.com; ym_vm_ws=example.org
private_key=eC9YOSPvhGUHAU1KLrr0X3GBiiYubH1zubnb_yxyylQ; short_id=aabbccdd
public_key=5XaAecMR7oqsy_0v-N7ZqYeepf-gPOJkncIsxN-NIgs
certificatec_vmess_ws="{d}/cert.pem"; certificatep_vmess_ws="{d}/key.pem"
certificatec_hy2=$certificatec_vmess_ws; certificatep_hy2=$certificatep_vmess_ws
certificatec_tuic=$certificatec_vmess_ws; certificatep_tuic=$certificatep_vmess_ws
certificatec_an=$certificatec_vmess_ws; certificatep_an=$certificatep_vmess_ws
tlsyn=true; ipv=prefer_ipv4
endip=162.159.192.1; pvk=8KaJxAfVlD76LnfAdKWaw8DdOMdOfqAQZzLs1ORsaXE=; v6=2606:4700::1; res="[1,2,3]"
hostname=test-vps; server_ipcl=192.0.2.1
sb_an_ip=$server_ipcl; cl_an_ip=$server_ipcl; an_port=51443; an_ins=true; an_name=www.bing.com
vl_port=11443; vl_name=$ym_vl_re; vm_port=21443; vm_name=example.org
vmadd_local=cdn.example.org; vmadd_argo=argo.example.org; ws_path=$uuid-vm
cl_hy2_ip=$server_ipcl; cl_tu5_ip=$server_ipcl; hy2_port=31443; tu5_port=41443
hy2_name=www.bing.com; tu5_name=www.bing.com; hy2_ins=true; tu5_ins=true
hy2_ports=; sbhy2pt='"32000:32010"'; cmhy2pt=32000-32010
argo=temporary.example.org; argogd=fixed.example.org
UUID=$uuid; IP=$server_ipcl; USERNAME=test; snb=s14; nb=14; hona=serv00
HOSTNAME=s14.serv00.com; address=serv00.net; vless_port=$vl_port; vmess_port=$vm_port
reym=$ym_vl_re; argodomain=$argo
openssl ecparam -genkey -name prime256v1 -out key.pem 2>/dev/null
MSYS_NO_PATHCONV=1 openssl req -new -x509 -days 1 -key key.pem -out cert.pem -subj /CN=www.bing.com 2>/dev/null
cp key.pem private.key
'''


def generate_vps(source, directory, version="1.14", argo="none", client_version=None, hopping=False, suffix=None, prefix=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    src = source.replace("/etc/s-box", bashpath(directory))
    functions = function(src, "inssbjsonser") + function(src, "sb_client")
    for name in ["sb_client_profile", "sb_config_check", "node_suffix_valid", "node_suffix_load"]:
        if name + "(){" in src:
            functions = function(src, name) + functions
    ps = ""
    if argo in ["fixed", "both"]:
        ps += "cloudflared tunnel run fixed\n"
    if argo in ["temporary", "both"]:
        ps += "cloudflared --url localhost:21443\n"
    script = parameters(directory) + functions + f'''
sbnh={version}
SB_CLIENT_VERSION={client_version or '1.14'}
red() {{ echo "$*" >&2; }}
yellow() {{ echo "$*" >&2; }}
inssbjsonser
'''
    if suffix is not None:
        script += "printf '%s\\n' " + "'" + suffix.replace("'", "'\"'\"'") + "' > node_suffix.conf\n"
    if prefix is not None:
        script += "printf '%s\\n' " + "'" + prefix.replace("'", "'\"'\"'") + "' > node_prefix.conf\n"
    if argo != "none":
        script += "jq '.inbounds[1].tls.enabled=false' sb.json > sb.tmp; mv sb.tmp sb.json\n"
    if hopping:
        script += "hy2_ports=32000:32010\n"
    script += f"ps() {{ printf '%s' '{ps}'; }}\nsb_client\n"
    shell(script, directory)
    return directory


def generate_serv00(source, directory, version="1.14.4", client_version=None, nb=14):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Extract complete real heredoc assembly; exclude downloads/process management.
    marker = 'server_raw=$(mktemp' if 'server_raw=$(mktemp' in source else '  cat > config.json << EOF'
    start = source.index(marker)
    end = source.index("\nif ! ps aux", start)
    server = source[start:end]
    marker = 'client_raw=$(mktemp' if 'client_raw=$(mktemp' in source else 'cat > sing_box.json <<EOF'
    start = source.index(marker)
    end = source.index("\ncat > clash_meta.yaml", start)
    client = source[start:end]
    helpers = ""
    for name in ["sb_client_profile", "serv00_server_profile"]:
        if name + "(){" in source:
            helpers += function(source, name)
    script = parameters(directory) + helpers + f'''
nb={nb}
SB_CLIENT_VERSION={client_version or '1.14'}
declare -A FILE_MAP
FILE_MAP[web]=test-core
printf '%s\\n' test-core > sb.txt
printf '%s\\n' '#!/bin/bash' 'exec "{bashpath(core(version))}" "$@"' > test-core
chmod +x test-core
dig() {{ echo 127.0.0.1; }}
''' + server + client
    shell(script, directory)
    return directory


def check(version, path):
    return run([core(version), "check", "-c", path], cwd=Path(path).parent)


def save_records(path):
    Path(path).write_text(json.dumps(RECORDS, ensure_ascii=False, indent=2), encoding="utf8")
