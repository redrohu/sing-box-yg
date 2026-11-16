#!/bin/bash
# Dedicated server configuration workflow. Never source the legacy five-protocol menus.
# Reference: qichiyuhub/rule, config/singbox/1.14X/VPS/server.json
# Upstream file revision: b8923a7351ea516f87599a8889f99aaeb70e989f

sb14_template() {
cat <<'SB14_TEMPLATE_JSON'
{
  "certificate_providers": [
    {
      "type": "acme",
      "tag": "cert",
      "domain": "test.com",
      "data_directory": "/etc/sing-box/acme",
      "email": "your-email@example.com",
      "dns01_challenge": {
        "provider": "cloudflare",
        "api_token": "YOUR_CLOUDFLARE_API_TOKEN"
      }
    }
  ],
  "inbounds": [
    {
      "tag": "VLESS-Vision-Reality-in",
      "type": "vless",
      "listen": "::",
      "listen_port": 443,
      "users": [
        {
          "uuid": "e9ee8ee0-dc73-4106-bee1-ce0d07b27eda",
          "flow": "xtls-rprx-vision"
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "one-piece.com",
        "reality": {
          "enabled": true,
          "handshake": {
            "server": "one-piece.com",
            "server_port": 443
          },
          "private_key": "gFIEpNaRizK1jGXcJfuCFIHnvgVS-DdG3XSnPJGKZ3U",
          "short_id": [
            "6ce0993f6735eaa0"
          ]
        }
      },
      "multiplex": {
        "enabled": true,
        "padding": true
      }
    },
    {
      "tag": "anytls-reality-in",
      "type": "anytls",
      "listen": "::",
      "listen_port": 1443,
      "users": [
        {
          "name": "anything",
          "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
        }
      ],
      "padding_scheme": [
        "stop=8",
        "0=34-34",
        "1=100-400",
        "2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000",
        "3=10-10,500-1000",
        "4=500-1000",
        "5=500-1000",
        "6=500-1000",
        "7=500-1000"
      ],
      "tls": {
        "enabled": true,
        "server_name": "one-piece.com",
        "reality": {
          "enabled": true,
          "handshake": {
            "server": "one-piece.com",
            "server_port": 443
          },
          "private_key": "gFIEpNaRizK1jGXcJfuCFIHnvgVS-DdG3XSnPJGKZ3U",
          "short_id": [
            "6ce0993f6735eaa0"
          ]
        }
      }
    },
    {
      "tag": "shadowtls-in",
      "type": "shadowtls",
      "listen": "::",
      "listen_port": 2443,
      "version": 3,
      "users": [
        {
          "name": "stlswin",
          "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
        }
      ],
      "handshake": {
        "server": "one-piece.com",
        "server_port": 443
      },
      "strict_mode": true,
      "detour": "shadowtls-ss-in"
    },
    {
      "tag": "shadowtls-ss-in",
      "type": "shadowsocks",
      "listen": "127.0.0.1",
      "network": "tcp",
      "method": "2022-blake3-aes-256-gcm",
      "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw=",
      "multiplex": {
        "enabled": true,
        "padding": true
      }
    },
    {
      "tag": "naive-in",
      "type": "naive",
      "listen": "::",
      "listen_port": 3443,
      "users": [
        {
          "username": "naivewin",
          "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "test.com",
        "certificate_provider": "cert"
      }
    },
    {
      "tag": "anytls-in",
      "type": "anytls",
      "listen": "::",
      "listen_port": 4443,
      "users": [
        {
          "name": "anything",
          "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
        }
      ],
      "padding_scheme": [
        "stop=8",
        "0=34-34",
        "1=100-400",
        "2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000",
        "3=10-10,500-1000",
        "4=500-1000",
        "5=500-1000",
        "6=500-1000",
        "7=500-1000"
      ],
      "tls": {
        "enabled": true,
        "server_name": "test.com",
        "certificate_provider": "cert"
      }
    },
    {
      "tag": "trojan-in",
      "type": "trojan",
      "listen": "::",
      "listen_port": 5443,
      "users": [
        {
          "name": "trojanwin",
          "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "test.com",
        "certificate_provider": "cert"
      }
    },
    {
      "tag": "hysteria-in",
      "type": "hysteria2",
      "listen": "::",
      "listen_port": 6443,
      "obfs": {
        "type": "salamander",
        "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
      },
      "users": [
        {
          "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "test.com",
        "certificate_provider": "cert"
      }
    },
    {
      "tag": "tuic-in",
      "type": "tuic",
      "listen": "::",
      "listen_port": 7443,
      "users": [
        {
          "name": "tuicwin",
          "uuid": "e9ee8ee0-dc73-4106-bee1-ce0d07b27eda",
          "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw="
        }
      ],
      "congestion_control": "bbr",
      "tls": {
        "enabled": true,
        "server_name": "test.com",
        "alpn": [
          "h3"
        ],
        "certificate_provider": "cert"
      }
    },
    {
      "tag": "shadowsocks2022-in",
      "type": "shadowsocks",
      "listen": "::",
      "listen_port": 8080,
      "method": "2022-blake3-aes-256-gcm",
      "password": "VhyQor7jFLuLRul4+Q0aXxqME8AMB1jBXXcroTo2JDw=",
      "multiplex": {
        "enabled": true,
        "padding": true
      }
    }
  ]
}
SB14_TEMPLATE_JSON
}

sb14_error() { printf '错误：%s\n' "$*" >&2; }
sb14_dir() { printf '%s\n' "${SB14_DIR:-/etc/s-box}"; }
sb14_bin() { printf '%s\n' "${SB14_BIN:-$(sb14_dir)/sing-box}"; }
sb14_root() { [[ $EUID -eq 0 ]] || { sb14_error '此操作需要 root'; return 1; }; }
sb14_jq() { command -v jq >/dev/null || { sb14_error '请先安装 jq (Debian/Ubuntu: apt install jq curl tar)'; return 1; }; }

sb14_core() {
    local bin="${1:-$(sb14_bin)}" version major minor
    [[ -x "$bin" ]] || { sb14_error "找不到内核：$bin；先执行 install-core"; return 1; }
    version=$("$bin" version | awk '/^sing-box version /{print $3}') || return 1
    [[ $version =~ ^([0-9]+)\.([0-9]+)\. ]] || { sb14_error '无法读取内核版本'; return 1; }
    major=${BASH_REMATCH[1]}; minor=${BASH_REMATCH[2]}
    (( major > 1 || (major == 1 && minor >= 14) )) || { sb14_error '指定模板要求 sing-box >= 1.14，不提供 1.10/1.11 混合模板'; return 1; }
}

sb14_parameters() {
    # No silent sample credentials, domain fallback or arbitrary JSON merge.
    sb14_jq || return 1
    jq -e '
      type == "object" and
      (.domain | type == "string" and test("^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\\.[A-Za-z]{2,}$") and . != "test.com") and
      (.email | type == "string" and test("^[^ @]+@[^ @]+\\.[^ @]+$") and . != "your-email@example.com") and
      (.cloudflare_api_token | type == "string" and length > 0 and . != "YOUR_CLOUDFLARE_API_TOKEN") and
      ((.reality_server // "one-piece.com") | type == "string" and test("^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$")) and
      ((.ports // {}) | type == "object" and all(to_entries[];
        (.key as $k | ["VLESS-Vision-Reality-in","anytls-reality-in","shadowtls-in","naive-in","anytls-in","trojan-in","hysteria-in","tuic-in","shadowsocks2022-in"] | index($k) != null) and
        (.value | type == "number" and floor == . and . >= 1 and . <= 65535))) and
      (keys - ["domain","email","cloudflare_api_token","reality_server","ports"] | length == 0)
    ' "$1" >/dev/null 2>&1 || { sb14_error '参数无效：需要真实 domain/email/cloudflare_api_token；端口必须为已知 tag 对应的 1..65535 整数；不接受未知字段'; return 1; }
}

sb14_credentials() {
    local bin="$(sb14_bin)" pair private uuid password sid
    pair=$("$bin" generate reality-keypair) || return 1
    private=$(printf '%s\n' "$pair" | awk '/PrivateKey/{gsub(/"/, "", $2); print $2}')
    uuid=$("$bin" generate uuid) || return 1
    password=$("$bin" generate rand --base64 32) || return 1
    sid=$("$bin" generate rand --hex 8) || return 1
    [[ -n $private && -n $uuid && -n $password && -n $sid ]] || return 1
    # Pipe secrets instead of putting them in process-list-visible jq arguments.
    printf '%s\0' "$private" "$uuid" "$password" "$sid" |
        jq -Rs 'split("\u0000") | {private_key:.[0],uuid:.[1],password:.[2],short_id:.[3]}'
}

sb14_fill_credentials() {
    # Used for both initial rendering and credential rotation; preserves all other fields.
    jq --slurpfile g "$1" '
      ($g[0]) as $g |
      .inbounds |= map(
        (if has("users") then .users |= map(
          (if has("uuid") then .uuid=$g.uuid else . end) |
          (if has("password") then .password=$g.password else . end)) else . end) |
        (if has("password") then .password=$g.password else . end) |
        (if .obfs? then .obfs.password=$g.password else . end) |
        (if .tls.reality? then .tls.reality.private_key=$g.private_key | .tls.reality.short_id=[$g.short_id] else . end))
    ' "$2"
}

sb14_render() (
    umask 077
    local params="$1" output="$2" tmp
    sb14_parameters "$params" && sb14_core || return 1
    [[ ! -e "$output" ]] || { sb14_error '输出已存在；render 不覆盖文件，请使用新的输出路径或 apply'; return 1; }
    [[ -d $(dirname "$output") ]] || { sb14_error '输出目录不存在'; return 1; }
    tmp=$(mktemp -d "$(dirname "$output")/.sb14-render.XXXXXXXX") || return 1
    trap 'rm -rf -- "$tmp"' EXIT
    sb14_template > "$tmp/template.json"
    sb14_credentials > "$tmp/credentials.json" || return 1
    sb14_fill_credentials "$tmp/credentials.json" "$tmp/template.json" > "$tmp/filled.json" || return 1
    jq --slurpfile p "$params" '
      $p[0] as $p |
      .certificate_providers[0] |= (.domain=$p.domain | .email=$p.email | .dns01_challenge.api_token=$p.cloudflare_api_token) |
      .inbounds |= map(
        (if has("listen_port") then .listen_port=($p.ports[.tag] // .listen_port) else . end) |
        (if .tls.reality? then .tls.server_name=($p.reality_server // "one-piece.com") |
          .tls.reality.handshake.server=($p.reality_server // "one-piece.com")
         elif .tls.certificate_provider? then .tls.server_name=$p.domain else . end) |
        (if .type == "shadowtls" then .handshake.server=($p.reality_server // "one-piece.com") else . end))
    ' "$tmp/filled.json" > "$tmp/config.json" || return 1
    sb14_layout "$tmp/config.json" || return 1
    mv -- "$tmp/config.json" "$output"
)

sb14_layout() {
    # Reject malformed ports, unexpected protocols and accidental legacy/hybrid configs.
    jq -e '
      (keys == ["certificate_providers","inbounds"]) and
      ([.inbounds[].tag] == ["VLESS-Vision-Reality-in","anytls-reality-in","shadowtls-in","shadowtls-ss-in","naive-in","anytls-in","trojan-in","hysteria-in","tuic-in","shadowsocks2022-in"]) and
      ([.inbounds[] | select(has("listen_port")) | .listen_port] as $p |
        ($p|length)==9 and ($p|unique|length)==9 and all($p[];type=="number" and floor==. and .>=1 and .<=65535)) and
      (.inbounds[] | select(.tag=="shadowtls-in") | .detour=="shadowtls-ss-in") and
      (.inbounds[] | select(.tag=="shadowtls-ss-in") | has("listen_port")|not)
    ' "$1" >/dev/null 2>&1 || { sb14_error '配置结构不符合指定 1.14 模板，或有重复/无效端口'; return 1; }
}

sb14_check() {
    sb14_jq && sb14_core && sb14_layout "$1" || return 1
    "$(sb14_bin)" check -c "$1"
}

sb14_commit() (
    umask 077
    local candidate="$1" dir="$(sb14_dir)" backup
    sb14_check "$candidate" || { sb14_error '校验失败，原配置未改动'; return 1; }
    if [[ -f "$dir/sb.json" ]]; then
        backup=$(mktemp "$dir/sb.json.bak.$(date +%Y%m%d-%H%M%S).XXXXXXXX") || return 1
        cp -- "$dir/sb.json" "$backup" || return 1
        chmod 600 "$backup" || return 1
        sha256sum "$backup" > "$backup.sha256" || return 1
        printf '原配置备份：%s\n' "$backup"
    fi
    chmod 600 "$candidate" && mv -f -- "$candidate" "$dir/sb.json" || return 1
    printf '已保存 %s/sb.json；尚未重启服务。\n' "$dir"
)

sb14_apply() (
    umask 077
    sb14_root || return 1
    local dir="$(sb14_dir)" tmp
    mkdir -p -- "$dir" || return 1
    tmp=$(mktemp -d "$dir/.sb14-apply.XXXXXXXX") || return 1
    trap 'rm -rf -- "$tmp"' EXIT
    sb14_render "$1" "$tmp/sb.json" && sb14_commit "$tmp/sb.json" && sb14_register
)

sb14_register() (
    # Prevent the already-installed legacy /usr/bin/sb from corrupting a migrated config.
    # Alternate directories are for offline rendering/testing, never system registration.
    [[ $(sb14_dir) == /etc/s-box ]] || return 0
    umask 077
    local helper launcher backup
    helper=$(mktemp /etc/s-box/.sb14-helper.XXXXXXXX) || return 1
    launcher=$(mktemp /usr/bin/.sb14-launcher.XXXXXXXX) || { rm -f -- "$helper"; return 1; }
    trap 'rm -f -- "$helper" "$launcher"' EXIT
    cp -- "${BASH_SOURCE[0]}" "$helper" && chmod 700 "$helper" || return 1
    printf '#!/bin/bash\nexec /bin/bash /etc/s-box/server14.sh "$@"\n' > "$launcher" || return 1
    chmod 700 "$launcher" || return 1
    if [[ -f /usr/bin/sb ]]; then
        backup=$(mktemp /etc/s-box/sb.launcher.bak.XXXXXXXX) || return 1
        cp -L -- /usr/bin/sb "$backup" && chmod 600 "$backup" || return 1
        printf '旧快捷脚本备份：%s\n' "$backup"
    fi
    mv -f -- "$helper" /etc/s-box/server14.sh && mv -f -- "$launcher" /usr/bin/sb
)

sb14_edit() (
    umask 077
    sb14_root && sb14_jq || return 1
    local dir="$(sb14_dir)" tmp action="$1"; shift
    sb14_layout "$dir/sb.json" || return 1
    tmp=$(mktemp -d "$dir/.sb14-edit.XXXXXXXX") || return 1
    trap 'rm -rf -- "$tmp"' EXIT
    case "$action" in
      port)
        [[ ${2:-} =~ ^[0-9]{1,5}$ ]] && ((10#$2 >= 1 && 10#$2 <= 65535)) || { sb14_error '无效端口'; return 1; }
        jq -e --arg tag "$1" 'any(.inbounds[]; .tag==$tag and has("listen_port"))' "$dir/sb.json" >/dev/null || { sb14_error '未知 tag，或该入站仅用于内部 detour'; return 1; }
        jq --arg tag "$1" --argjson port "$((10#$2))" '(.inbounds[] | select(.tag==$tag) | .listen_port)=$port' "$dir/sb.json" > "$tmp/sb.json" || return 1
        ;;
      reality)
        [[ ${1:-} =~ ^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$ ]] || { sb14_error '无效 Reality 域名'; return 1; }
        jq --arg domain "$1" '.inbounds |= map(if .tls.reality? then .tls.server_name=$domain | .tls.reality.handshake.server=$domain elif .type=="shadowtls" then .handshake.server=$domain else . end)' "$dir/sb.json" > "$tmp/sb.json" || return 1
        ;;
      credentials)
        sb14_core && sb14_credentials > "$tmp/credentials.json" || return 1
        sb14_fill_credentials "$tmp/credentials.json" "$dir/sb.json" > "$tmp/sb.json" || return 1
        ;;
      certificate)
        sb14_parameters "$1" || return 1
        jq --slurpfile p "$1" '$p[0] as $p | .certificate_providers[0] |= (.domain=$p.domain | .email=$p.email | .dns01_challenge.api_token=$p.cloudflare_api_token) | .inbounds |= map(if .tls.certificate_provider? then .tls.server_name=$p.domain else . end)' "$dir/sb.json" > "$tmp/sb.json" || return 1
        ;;
      *) return 1;;
    esac
    sb14_commit "$tmp/sb.json"
)

sb14_restore() (
    umask 077
    sb14_root || return 1
    local dir="$(sb14_dir)" backup="$1" tmp
    [[ -f "$backup" ]] || { sb14_error '备份不存在'; return 1; }
    # Restoration can include a pre-migration legacy config: core check, not template-layout check.
    sb14_core && "$(sb14_bin)" check -c "$backup" || { sb14_error '当前内核不能读取该备份'; return 1; }
    tmp=$(mktemp "$dir/.sb14-restore.XXXXXXXX") || return 1
    trap 'rm -f -- "$tmp"' EXIT
    cp -- "$backup" "$tmp" || return 1
    backup=$(mktemp "$dir/sb.json.before-restore.XXXXXXXX") || return 1
    cp -- "$dir/sb.json" "$backup" && chmod 600 "$backup" "$tmp" && mv -f -- "$tmp" "$dir/sb.json" || return 1
    printf '已恢复配置；恢复前副本：%s。尚未重启服务。\n' "$backup"
)

sb14_summary() {
    sb14_jq || return 1
    local config="${1:-$(sb14_dir)/sb.json}"
    sb14_layout "$config" || return 1
    jq -r '.inbounds[] | [.tag,.type,(.listen_port // "内部 detour")]|@tsv' "$config"
    printf '\n证书：内置 ACME + Cloudflare DNS-01；未添加 DNS/route/WARP。\n'
    printf '旧版五协议客户端/订阅生成器不适用于本模板，本模式不调用它们。\n'
}

sb14_install_core() (
    umask 077
    sb14_root || return 1
    local version="${1:-1.14.4}" cpu dir="$(sb14_dir)" tmp name backup
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { sb14_error '需要正式版版本号，例如 1.14.4'; return 1; }
    case $(uname -m) in x86_64) cpu=amd64;; aarch64) cpu=arm64;; armv7l) cpu=armv7;; *) sb14_error '不支持此 CPU'; return 1;; esac
    mkdir -p -- "$dir" || return 1
    tmp=$(mktemp -d "$dir/.sb14-core.XXXXXXXX") || return 1
    trap 'rm -rf -- "$tmp"' EXIT
    name="sing-box-$version-linux-$cpu"
    curl -fLS --retry 2 -o "$tmp/core.tar.gz" "https://github.com/SagerNet/sing-box/releases/download/v$version/$name.tar.gz" || return 1
    tar -xzf "$tmp/core.tar.gz" -C "$tmp" "$name/sing-box" || return 1
    chmod 700 "$tmp/$name/sing-box" && sb14_core "$tmp/$name/sing-box" || return 1
    if [[ -f "$dir/sb.json" ]]; then
        "$tmp/$name/sing-box" check -c "$dir/sb.json" || { sb14_error '新内核不兼容当前配置，未替换'; return 1; }
    fi
    if [[ -f "$dir/sing-box" ]]; then
        backup=$(mktemp "$dir/sing-box.bak.XXXXXXXX") || return 1
        cp -- "$dir/sing-box" "$backup" || return 1
        chmod 700 "$backup"
        printf '内核备份：%s\n' "$backup"
    fi
    mv -f -- "$tmp/$name/sing-box" "$dir/sing-box" || return 1
    printf '内核已安装；未重启现有服务。\n'
)

sb14_restart() {
    sb14_root && sb14_check "$(sb14_dir)/sb.json" || return 1
    if command -v rc-service >/dev/null; then rc-service sing-box restart; else systemctl restart sing-box; fi
}

sb14_service() {
    sb14_root || return 1
    [[ $(sb14_dir) == /etc/s-box && $(sb14_bin) == /etc/s-box/sing-box ]] || { sb14_error '服务安装只允许标准 /etc/s-box 路径'; return 1; }
    sb14_check /etc/s-box/sb.json || return 1
    if command -v rc-service >/dev/null; then
        cat > /etc/init.d/sing-box <<'OPENRC'
#!/sbin/openrc-run
description="sing-box 1.14 template server"
command="/etc/s-box/sing-box"
command_args="run -c /etc/s-box/sb.json"
command_background=true
pidfile="/var/run/sing-box.pid"
OPENRC
        chmod +x /etc/init.d/sing-box
        rc-update add sing-box default && rc-service sing-box start
    else
        cat > /etc/systemd/system/sing-box.service <<'SYSTEMD'
[Unit]
Description=sing-box 1.14 template server
After=network-online.target
Wants=network-online.target
[Service]
User=root
ExecStart=/etc/s-box/sing-box run -c /etc/s-box/sb.json
Restart=on-failure
RestartSec=10
LimitNOFILE=1048576
UMask=0077
[Install]
WantedBy=multi-user.target
SYSTEMD
        systemctl daemon-reload && systemctl enable sing-box && systemctl start sing-box
    fi
}

sb14_install() {
    sb14_root && sb14_parameters "$1" || return 1
    [[ ! -e "$(sb14_dir)/sb.json" ]] || { sb14_error '已有配置；请备份并用 apply 显式迁移，然后 restart。不会覆盖运行中的旧配置'; return 1; }
    sb14_install_core "${2:-1.14.4}" && sb14_apply "$1" || return 1
    sb14_service || { sb14_error '配置已保存但服务安装/启动未成功，请查看日志；未宣称部署成功'; return 1; }
    sb14_summary
}

sb14_prompt_parameters() (
    umask 077
    local file="$1" domain email token reality
    read -r -p '证书域名（必须有 Cloudflare DNS 管理权限）: ' domain
    read -r -p 'ACME 邮箱: ' email
    read -r -s -p 'Cloudflare API Token（隐藏输入）: ' token; printf '\n'
    read -r -p 'Reality/ShadowTLS 握手域名 [one-piece.com]: ' reality
    printf '%s\0' "$domain" "$email" "$token" "${reality:-one-piece.com}" |
      jq -Rs 'split("\u0000") | {domain:.[0],email:.[1],cloudflare_api_token:.[2],reality_server:.[3]}' > "$file" || return 1
    sb14_parameters "$file"
)

sb14_menu() (
    umask 077
    local action tmp tag port backup result
    sb14_jq || return 1
    printf '指定 1.14X/VPS/server.json 模板：10 入站 + 内置 ACME，默认端口 443/1443/2443/3443/4443/5443/6443/7443/8080\n'
    printf '1 安装（需要域名和 Cloudflare Token）\n2 按模板重新生成/迁移（所有凭据会重新生成，原配置备份，不自动重启）\n3 校验\n4 查看协议端口\n5 修改单个入站端口\n6 修改 Reality/ShadowTLS 域名\n7 轮换凭据\n8 更新 ACME 参数\n9 校验并重启\n10 日志\n11 从备份恢复（不重启）\n0 退出\n'
    read -r -p '选择: ' action
    case "$action" in
      1|2|8)
        sb14_root || return 1
        tmp=$(mktemp -d) || return 1
        trap 'rm -rf -- "$tmp"' EXIT
        sb14_prompt_parameters "$tmp/parameters.json" || return 1
        if [[ $action == 1 ]]; then sb14_install "$tmp/parameters.json"
        elif [[ $action == 8 ]]; then sb14_edit certificate "$tmp/parameters.json"
        else
            read -r -p '迁移会更换协议和全部凭据，客户端须重新配置。输入 MIGRATE 确认: ' result
            [[ $result == MIGRATE ]] || return 1
            sb14_apply "$tmp/parameters.json"
        fi;;
      3) sb14_check "$(sb14_dir)/sb.json";;
      4) sb14_summary;;
      5) read -r -p '完整 inbound tag: ' tag; read -r -p '新端口: ' port; sb14_edit port "$tag" "$port";;
      6) read -r -p '新域名: ' tag; sb14_edit reality "$tag";;
      7) read -r -p '所有客户端须同步新凭据。输入 ROTATE 确认: ' result; [[ $result == ROTATE ]] && sb14_edit credentials;;
      9) sb14_restart;;
      10) if command -v journalctl >/dev/null; then journalctl -u sing-box -n 80 --no-pager; else tail -80 /var/log/messages; fi;;
      11) read -r -p '备份绝对路径: ' backup; sb14_restore "$backup";;
      0) return 0;;
      *) sb14_error '未知选项'; return 1;;
    esac
)

sb14_usage() {
    cat <<'HELP'
用法：bash sb.sh [命令]
  menu                              新模板菜单（默认）
  template                          输出未填参的原始参考模板
  render PARAMETERS.json OUTPUT     生成候选配置；不覆盖已有文件、不修改服务
  apply PARAMETERS.json             校验、备份、写入 /etc/s-box/sb.json；不重启
  check [CONFIG]                    模板结构及 sing-box check
  summary [CONFIG]                  协议和端口摘要（不显示凭据）
  set-port TAG PORT                 tag 定位改端口，校验、备份、不重启
  set-reality DOMAIN                同步两种 Reality 和 ShadowTLS 握手域名
  rotate-credentials                轮换 UUID/密码/Reality 密钥和 short_id
  set-certificate PARAMETERS.json   只更新 ACME/证书域名，保留凭据与端口
  restore BACKUP.json               校验并恢复备份，不重启
  restart                           校验后重启
  install PARAMETERS.json [VERSION] 安装内核、配置和服务（默认 1.14.4）
  install-core [VERSION]            安装 >=1.14 内核，保留配置、不重启
参数文件含 Token，请 chmod 600。申请证书需要有效域名、DNS API 权限和网络。
旧版客户端生成器不适用于此模板；旧配置的维护入口：bash sb.sh --legacy。
HELP
}

sb14_main() {
    local cmd="${1:-menu}"; [[ $# -eq 0 ]] || shift
    case "$cmd:$#" in
      menu:0) sb14_menu;;
      template:0) sb14_template;;
      render:2) sb14_render "$@";;
      apply:1) sb14_apply "$@";;
      check:0|check:1) sb14_check "${1:-$(sb14_dir)/sb.json}";;
      summary:0|summary:1) sb14_summary "$@";;
      set-port:2) sb14_edit port "$@";;
      set-reality:1) sb14_edit reality "$@";;
      rotate-credentials:0) sb14_edit credentials;;
      set-certificate:1) sb14_edit certificate "$@";;
      restore:1) sb14_restore "$@";;
      restart:0) sb14_restart;;
      install:1|install:2) sb14_install "$@";;
      install-core:0|install-core:1) sb14_install_core "$@";;
      --help:0|help:0) sb14_usage;;
      *) sb14_usage >&2; return 2;;
    esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    sb14_main "$@"
fi
