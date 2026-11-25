#!/bin/bash
# 定时设置：*/10 * * * * /bin/bash /root/kp.sh 每10分钟运行一次
# 如果你已安装了Serv00本地SSH脚本，不要再运行此脚本部署了，这样会造成进程爆满，必须二选一！
# serv00变量添加规则：
# 如使用保活网页，请不要启用cron，以防止cron与网页保活重复运行造成进程爆满
# RES(必填)：n表示每次不重置部署，y表示每次重置部署。REP(必填)：n表示不重置随机端口(三个端口留空)，y表示重置端口(三个端口留空)。SSH_USER(必填)表示serv00账号名。SSH_PASS(必填)表示serv00密码。REALITY表示reality域名(留空表示serv00官方域名：你serv00账号名.serv00.net)。SUUID表示uuid(留空表示随机uuid)。TCP1_PORT表示vless的tcp端口(留空表示随机tcp端口)。TCP2_PORT表示vmess的tcp端口(留空表示随机tcp端口)。UDP_PORT表示hy2的udp端口(留空表示随机udp端口)。HOST(必填)表示登录serv00服务器域名。ARGO_DOMAIN表示argo固定域名(留空表示临时域名)。ARGO_AUTH表示argo固定域名token(留空表示临时域名)。
# 必填变量：RES、REP、SSH_USER、SSH_PASS、HOST
# 注意[]"",:这些符号不要乱删，按规律对齐
# 每行一个{serv00服务器}，一个服务也可，末尾用,间隔，最后一个服务器末尾无需用,间隔
ACCOUNTS='[
{"RES":"n", "REP":"n", "SSH_USER":"你的serv00账号名", "SSH_PASS":"你的serv00账号密码", "REALITY":"你serv00账号名.serv00.net", "SUUID":"自设UUID", "TCP1_PORT":"vless的tcp端口", "TCP2_PORT":"vmess的tcp端口", "UDP_PORT":"hy2的udp端口", "HOST":"s1.serv00.com", "ARGO_DOMAIN":"", "ARGO_AUTH":""},
{"RES":"y", "REP":"y", "SSH_USER":"123456", "SSH_PASS":"7890000", "REALITY":"time.is", "SUUID":"73203ee6-b3fa-4a3d-b5df-6bb2f55073ad", "TCP1_PORT":"", "TCP2_PORT":"", "UDP_PORT":"", "HOST":"s16.serv00.com", "ARGO_DOMAIN":"你的argo固定域名", "ARGO_AUTH":"你的argo固定域名token"}
]'
# Install only missing dependencies, synchronously, then verify before processing accounts.
ensure_dependencies() {
    local missing=() dependency
    for dependency in sshpass curl jq ssh; do
        command -v "$dependency" >/dev/null 2>&1 || missing+=("$dependency")
    done
    [ "${#missing[@]}" -gt 0 ] || return 0
    if command -v opkg >/dev/null 2>&1; then
        opkg update && opkg install sshpass curl jq openssh-client || return 1
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get update && apt-get install -y sshpass curl jq openssh-client || return 1
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y sshpass curl jq openssh-clients || return 1
    elif command -v yum >/dev/null 2>&1; then
        yum install -y sshpass curl jq openssh-clients || return 1
    elif command -v apk >/dev/null 2>&1; then
        apk add sshpass curl jq openssh-client || return 1
    else
        echo "缺少依赖：${missing[*]}；请先安装" >&2; return 1
    fi
    for dependency in sshpass curl jq ssh; do command -v "$dependency" >/dev/null 2>&1 || return 1; done
}

run_remote_command() {
    local RES=$1 REP=$2 SSH_USER=$3 SSH_PASS=$4 REALITY=$5 SUUID=$6
    local TCP1_PORT=$7 TCP2_PORT=$8 UDP_PORT=$9 HOST=${10} ARGO_DOMAIN=${11} ARGO_AUTH=${12}
    # Export shell-quoted values over stdin to bash, not in a command string or logs.
    {
        printf 'export reym=%q UUID=%q vless_port=%q vmess_port=%q hy2_port=%q reset=%q resport=%q ARGO_DOMAIN=%q ARGO_AUTH=%q\n' \
            "$REALITY" "$SUUID" "$TCP1_PORT" "$TCP2_PORT" "$UDP_PORT" "$RES" "$REP" "$ARGO_DOMAIN" "$ARGO_AUTH"
        cat <<'REMOTE'
script=$(mktemp "$HOME/.serv00keep.XXXXXX") || exit 1
trap 'rm -f "$script"' EXIT
curl -fsSL --connect-timeout 10 --max-time 120 https://raw.githubusercontent.com/redrohu/sing-box-yg/main/serv00keep.sh -o "$script" &&
    bash -n "$script" && bash "$script"
REMOTE
    } | SSHPASS="$SSH_PASS" sshpass -e ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$HOST" bash -s
}

ensure_dependencies || { echo "依赖安装失败，未连接任何服务器" >&2; exit 1; }
jq -e 'type == "array" and all(.[]; type == "object")' >/dev/null <<< "$ACCOUNTS" || exit 1
SSH_OPTIONS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ServerAliveInterval=15 -o ServerAliveCountMax=2)
count=0
# Accounts are read from fd 3 so ssh cannot consume the remaining accounts from stdin.
while IFS= read -r account <&3; do
    count=$((count + 1))
    RES=$(jq -r '.RES // "n"' <<< "$account")
    REP=$(jq -r '.REP // "n"' <<< "$account")
    SSH_USER=$(jq -r '.SSH_USER // empty' <<< "$account")
    SSH_PASS=$(jq -r '.SSH_PASS // empty' <<< "$account")
    REALITY=$(jq -r '.REALITY // empty' <<< "$account")
    SUUID=$(jq -r '.SUUID // empty' <<< "$account")
    TCP1_PORT=$(jq -r '.TCP1_PORT // empty' <<< "$account")
    TCP2_PORT=$(jq -r '.TCP2_PORT // empty' <<< "$account")
    UDP_PORT=$(jq -r '.UDP_PORT // empty' <<< "$account")
    HOST=$(jq -r '.HOST // empty' <<< "$account")
    ARGO_DOMAIN=$(jq -r '.ARGO_DOMAIN // empty' <<< "$account")
    ARGO_AUTH=$(jq -r '.ARGO_AUTH // empty' <<< "$account")
    if [[ ! "$SSH_USER" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ || ! "$HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ || -z "$SSH_PASS" ]]; then
        echo "第 $count 个账户的连接参数无效，已跳过" >&2; continue
    fi
    if ! SSHPASS="$SSH_PASS" sshpass -e ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$HOST" -q exit; then
        echo "第 $count 台服务器连接失败" >&2; continue
    fi
    check_process='workdir="$HOME/domains/$(whoami | tr "[:upper:]" "[:lower:]").serv00.net/logs"; for file in sb.txt ag.txt; do name=$(cat "$workdir/$file") || exit 1; case "$name" in ""|-*|*[!a-zA-Z0-9_.-]*) exit 1;; esac; pgrep -x "$name" >/dev/null || exit 1; done'
    if [[ "$RES" =~ ^[Yy]$ ]] || ! SSHPASS="$SSH_PASS" sshpass -e ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$HOST" "$check_process"; then
        echo "第 $count 台服务器开始修复或重置部署"
        if run_remote_command "$RES" "$REP" "$SSH_USER" "$SSH_PASS" "$REALITY" "$SUUID" "$TCP1_PORT" "$TCP2_PORT" "$UDP_PORT" "$HOST" "$ARGO_DOMAIN" "$ARGO_AUTH" >/dev/null; then
            echo "第 $count 台服务器部署命令已完成"
        else
            echo "第 $count 台服务器部署失败" >&2
        fi
    else
        echo "第 $count 台服务器进程正常"
    fi
done 3< <(jq -c '.[]' <<< "$ACCOUNTS")
