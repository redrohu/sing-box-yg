#!/bin/bash
export LANG=en_US.UTF-8
red='\033[0;31m'
green='\033[0;32m'
yellow='\033[0;33m'
blue='\033[0;36m'
bblue='\033[0;34m'
plain='\033[0m'
red(){ echo -e "\033[31m\033[01m$1\033[0m";}
green(){ echo -e "\033[32m\033[01m$1\033[0m";}
yellow(){ echo -e "\033[33m\033[01m$1\033[0m";}
blue(){ echo -e "\033[36m\033[01m$1\033[0m";}
white(){ echo -e "\033[37m\033[01m$1\033[0m";}
readp(){ read -p "$(yellow "$1")" $2;}

# Client core version is independent of the VPS core. Default: current stable syntax.
# Keep this self-contained helper identical in sb.sh / serv00.sh / serv00keep.sh.
sb_client_profile(){
local source=$1 target=$2 version=${SB_CLIENT_VERSION:-1.14} minor tmp
if [[ ! $version =~ ^1\.([0-9]+)(\.[0-9]+)?$ ]] || (( 10#${BASH_REMATCH[1]:-0} < 12 )); then
echo "客户端配置要求 SB_CLIENT_VERSION=1.12、1.13 或 1.14（默认），不支持：$version" >&2
return 1
fi
minor=$((10#${BASH_REMATCH[1]}))
tmp=$(mktemp "${target}.tmp.XXXXXX") || return 1
if ! jq --argjson minor "$minor" '
  .experimental.cache_file.store_fakeip = true |
  if $minor < 14 then
    .http_clients[0].detour as $download |
    .route.rule_set |= map(.download_detour = ($download // "direct") | del(.http_client)) |
    del(.http_clients, .route.default_http_client, .dns.optimistic, .dns.timeout,
        .experimental.cache_file.store_dns)
  else . end
' "$source" > "$tmp"; then
rm -f "$tmp"
return 1
fi
mv -f "$tmp" "$target"
}

sb_config_check(){
/etc/s-box/sing-box check -c /etc/s-box/sb.json || {
red "配置检查失败，未启动/重启服务。请根据上面的内核错误修正配置。"
return 1
}
}

# Commit only a completed export set. Restore the snapshot on ordinary errors/signals.
# Individual renames are not a filesystem-wide transaction; serialize our writers.
sb_exports_commit(){
(
umask 077
local stage=$1 backup file committed=0 changing=0 restore_failed=0 lock_dir=
shift
if command -v flock >/dev/null 2>&1; then
exec 9>/etc/s-box/.exports.flock || exit 1
flock -n 9 || { red "另一个导出正在提交；请稍后重试。" >&2; exit 1; }
else
lock_dir=/etc/s-box/.exports.lock
mkdir "$lock_dir" 2>/dev/null || { red "另一个导出正在提交；请稍后重试。" >&2; exit 1; }
fi
backup=$(mktemp -d /etc/s-box/exports.bak.XXXXXX) || { [[ -z $lock_dir ]] || rmdir "$lock_dir"; exit 1; }
local -a files=("$@")
trap 'rc=$?; trap - EXIT; if [[ $changing == 1 && $committed == 0 ]]; then
for file in "${files[@]}"; do
if [[ -f $backup/$file ]]; then cp -p "$backup/$file" "/etc/s-box/$file" || restore_failed=1
else rm -f "/etc/s-box/$file" || restore_failed=1; fi
done
fi
if [[ $restore_failed == 0 ]]; then rm -rf "$backup"; else
echo "导出回滚不完整，请从此目录恢复：$backup" >&2; fi
[[ -z $lock_dir ]] || rmdir "$lock_dir"; exit "$rc"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
for file in "${files[@]}"; do
[[ $file != /* && $file != *..* ]] || exit 1
if [[ -e /etc/s-box/$file && ! -f /etc/s-box/$file ]]; then exit 1; fi
if [[ -f /etc/s-box/$file ]]; then
mkdir -p "$backup/$(dirname "$file")" && cp -p "/etc/s-box/$file" "$backup/$file" || exit 1
fi
done
changing=1
for file in "${files[@]}"; do
if [[ -f $stage/$file ]]; then
mkdir -p "/etc/s-box/$(dirname "$file")" && mv -f "$stage/$file" "/etc/s-box/$file" || exit 1
else rm -f "/etc/s-box/$file" || exit 1; fi
done
committed=1
)
}

node_suffix_valid(){
# Accept Unicode letters, combining marks, numbers, dashes, horizontal spaces, # and |.
# Reject all-space names, controls and quotes; URI names are encoded by node_suffix_load.
jq -en --arg suffix "$1" '$suffix | length >= 1 and length <= 48 and test("\\A[\\p{L}\\p{M}\\p{N}\\p{Pd}\\p{Zs}._#|]+\\z") and test("[^\\p{Zs}]")' >/dev/null
}

node_suffix_load(){
local saved
node_suffix=${hostname:-$(hostname)}
if [[ -f /etc/s-box/node_suffix.conf ]]; then
saved=$(cat /etc/s-box/node_suffix.conf) || return 1
if node_suffix_valid "$saved"; then
node_suffix=$saved
else
yellow "节点后缀文件无效，暂时使用主机名；可在菜单3-10重新设置。" >&2
fi
fi
if [[ -f /etc/s-box/node_suffix.disabled ]]; then node_suffix=; fi
node_suffix_label="${node_suffix:+ ${node_suffix}}"
node_prefix=
if [[ -f /etc/s-box/node_prefix.conf ]]; then
saved=$(cat /etc/s-box/node_prefix.conf) || return 1
if node_suffix_valid "$saved"; then
node_prefix=$saved
else
yellow "节点前缀文件无效，暂时不加前缀；可在菜单3-10重新设置。" >&2
fi
fi
node_prefix_label="${node_prefix:+${node_prefix} }"
node_prefix_uri_label=$(jq -nr --arg prefix "$node_prefix_label" '$prefix | @uri') || return 1
node_suffix_uri_label=$(jq -nr --arg suffix "$node_suffix_label" '$suffix | @uri')
}

change_node_suffix(){
local action input tmp backup file setting label
node_suffix_load || return 1
green "当前节点名称前缀：${node_prefix:-（无）}"
green "当前节点名称后缀：${node_suffix:-（无）}"
green "节点名称示例：${node_prefix_label}anytls${node_suffix_label}"
yellow "1：设置自定义后缀"
yellow "2：恢复使用服务器主机名"
yellow "3：设置自定义前缀（加在协议名前）"
yellow "4：清除前缀"
yellow "5：清除后缀（不显示主机名）"
yellow "0：返回上层"
readp "请选择【0-5】：" action
case "$action" in
1|3)
if [[ $action == 1 ]]; then setting=node_suffix.conf; label=后缀; else setting=node_prefix.conf; label=前缀; fi
IFS= read -r -p "$(yellow "请输入${label}（1–48个字，支持中英文字母、数字、空格、点、下划线、连字符、#、|，不能全空格；回车取消）：")" input || return 0
[[ -n $input ]] || { yellow "已取消，未修改。"; return 0; }
if ! node_suffix_valid "$input"; then
red "${label}格式无效，未修改。限1–48个字，支持空格、#、|，不能全空格，也不能含引号、反斜线、换行、制表符或其他未支持的符号。"
printf '实际收到的内容（JSON转义）：%s\n' "$(jq -nc --arg value "$input" '$value')"
printf '字符编码（十进制，可检查隐藏字符）：%s\n' "$(jq -nc --arg value "$input" '$value | explode')"
return 1
fi
;;
2) setting=node_suffix.conf ;;
4) setting=node_prefix.conf ;;
5) setting=node_suffix.disabled ;;
0) changeserv; return $? ;;
*) return 0 ;;
esac
# Back up only the setting and generated exports, not the running server config.
backup=$(mktemp -d /etc/s-box/node-name.bak.XXXXXX) || return 1
for file in node_prefix.conf node_suffix.conf node_suffix.disabled xhttp.txt xhttp-argo.txt sbox.json clmi.yaml jhsub.txt jhdy.txt vl_reality.txt vm_ws_argols.txt vm_ws_argogd.txt vm_ws.txt vm_ws_tls.txt hy2.txt tuic5.txt an.txt; do
if [[ -f /etc/s-box/$file ]]; then
cp -p "/etc/s-box/$file" "$backup/$file" || return 1
fi
done
if [[ $action == 5 ]]; then
(umask 077; printf 'disabled\n' > /etc/s-box/node_suffix.disabled) || return 1
elif [[ $action == 1 || $action == 3 ]]; then
tmp=$(mktemp "/etc/s-box/${setting}.tmp.XXXXXX") || return 1
printf '%s\n' "$input" > "$tmp" && mv -f "$tmp" "/etc/s-box/$setting" || { rm -f "$tmp"; return 1; }
else
rm -f "/etc/s-box/$setting" || return 1
fi
if [[ $action == 1 || $action == 2 ]]; then rm -f /etc/s-box/node_suffix.disabled || return 1; fi
node_suffix_load || return 1
green "节点名称前缀已设置为：${node_prefix:-（无）}"
green "节点名称后缀已设置为：${node_suffix:-（无）}"
green "节点名称示例：${node_prefix_label}anytls${node_suffix_label}"
green "旧设置和导出文件备份：$backup"
if sbshare > /dev/null; then
green "节点分享链接、聚合订阅及Sing-box/Mihomo客户端配置已刷新。"
yellow "本地订阅同步生效；Gitlab远端订阅请在菜单9-2刷新推送。客户端请重新拉取订阅。"
else
red "节点名称设置已保存，但导出刷新失败；请查看错误并用菜单9重试。备份目录：$backup"
return 1
fi
yellow "未修改服务器主机名、服务端配置、端口或凭据，也未重启服务。"
}

[[ $EUID -ne 0 ]] && yellow "请以root模式运行脚本" && exit
stty erase $'\b' 2>/dev/null || stty erase '^H' 2>/dev/null
#[[ -e /etc/hosts ]] && grep -qE '^ *172.65.251.78 gitlab.com' /etc/hosts || echo -e '\n172.65.251.78 gitlab.com' >> /etc/hosts
if [[ -f /etc/redhat-release ]]; then
release="Centos"
elif cat /etc/issue | grep -q -E -i "alpine"; then
release="alpine"
elif cat /etc/issue | grep -q -E -i "debian"; then
release="Debian"
elif cat /etc/issue | grep -q -E -i "ubuntu"; then
release="Ubuntu"
elif cat /etc/issue | grep -q -E -i "centos|red hat|redhat"; then
release="Centos"
elif cat /proc/version | grep -q -E -i "debian"; then
release="Debian"
elif cat /proc/version | grep -q -E -i "ubuntu"; then
release="Ubuntu"
elif cat /proc/version | grep -q -E -i "centos|red hat|redhat"; then
release="Centos"
else 
red "脚本不支持当前的系统，请选择使用Ubuntu,Debian,Centos系统。" && exit
fi
export sbfiles="/etc/s-box/sb10.json /etc/s-box/sb11.json /etc/s-box/sb.json"
export sbnh=$(/etc/s-box/sing-box version 2>/dev/null | awk '/version/{print $NF}' 2>/dev/null | cut -d '.' -f 1,2)
vsid=$(grep -i version_id /etc/os-release | cut -d \" -f2 | cut -d . -f1)
op=$(cat /etc/redhat-release 2>/dev/null || cat /etc/os-release 2>/dev/null | grep -i pretty_name | cut -d \" -f2)
#if [[ $(echo "$op" | grep -i -E "arch|alpine") ]]; then
if [[ $(echo "$op" | grep -i -E "arch") ]]; then
red "脚本不支持当前的 $op 系统，请选择使用Ubuntu,Debian,Centos系统。" && exit
fi
version=$(uname -r | cut -d "-" -f1)
[[ -z $(systemd-detect-virt 2>/dev/null) ]] && vi=$(virt-what 2>/dev/null) || vi=$(systemd-detect-virt 2>/dev/null)
case $(uname -m) in
armv7l) cpu=armv7;;
aarch64) cpu=arm64;;
x86_64) cpu=amd64;;
*) red "目前脚本不支持$(uname -m)架构" && exit;;
esac
if [[ -n $(sysctl net.ipv4.tcp_congestion_control 2>/dev/null | awk -F ' ' '{print $3}') ]]; then
bbr=`sysctl net.ipv4.tcp_congestion_control | awk -F ' ' '{print $3}'`
elif [[ -n $(ping 10.0.0.2 -c 2 | grep ttl) ]]; then
bbr="Openvz版bbr-plus"
else
bbr="Openvz/Lxc"
fi
hostname=$(hostname)

if [[ ! -f /etc/s-box/sbyg_update ]] || ! command -v jq >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
green "首次安装Sing-box-yg脚本必要的依赖……"
if command -v apk >/dev/null 2>&1; then
apk update
apk add bash libc6-compat curl wget jq openssl procps busybox-extras iproute2 iputils coreutils expect git socat iptables grep tar tzdata util-linux
apk add virt-what
else
if [[ $release = Centos && ${vsid} =~ 8 ]]; then
cd /etc/yum.repos.d/ && mkdir backup && mv *repo backup/ 
curl -o /etc/yum.repos.d/CentOS-Base.repo http://mirrors.aliyun.com/repo/Centos-8.repo
sed -i -e "s|mirrors.cloud.aliyuncs.com|mirrors.aliyun.com|g " /etc/yum.repos.d/CentOS-*
sed -i -e "s|releasever|releasever-stream|g" /etc/yum.repos.d/CentOS-*
yum clean all && yum makecache
cd
fi
if [ -x "$(command -v apt-get)" ]; then
apt update -y
apt install jq cron socat busybox iptables-persistent coreutils util-linux -y
elif [ -x "$(command -v yum)" ]; then
yum update -y && yum install epel-release -y
yum install jq socat busybox coreutils util-linux -y
elif [ -x "$(command -v dnf)" ]; then
dnf update -y
dnf install jq socat busybox coreutils util-linux -y
fi
if [ -x "$(command -v yum)" ] || [ -x "$(command -v dnf)" ]; then
if [ -x "$(command -v yum)" ]; then
yum install -y cronie iptables-services
elif [ -x "$(command -v dnf)" ]; then
dnf install -y cronie iptables-services
fi
systemctl enable iptables >/dev/null 2>&1
systemctl start iptables >/dev/null 2>&1
fi
if [[ -z $vi ]]; then
apt install iputils-ping iproute2 systemctl -y
fi

packages=("curl" "openssl" "iptables" "tar" "expect" "wget" "xxd" "python3" "qrencode" "git")
inspackages=("curl" "openssl" "iptables" "tar" "expect" "wget" "xxd" "python3" "qrencode" "git")
for i in "${!packages[@]}"; do
package="${packages[$i]}"
inspackage="${inspackages[$i]}"
if ! command -v "$package" &> /dev/null; then
if [ -x "$(command -v apt-get)" ]; then
apt-get install -y "$inspackage"
elif [ -x "$(command -v yum)" ]; then
yum install -y "$inspackage"
elif [ -x "$(command -v dnf)" ]; then
dnf install -y "$inspackage"
fi
fi
done
fi
for required in bash curl jq openssl tar git iptables; do
command -v "$required" >/dev/null 2>&1 || { red "依赖安装未完成：$required；未写入完成标记，请修复包管理器后重试。"; exit 1; }
done
mkdir -p /etc/s-box && touch /etc/s-box/sbyg_update || exit 1
fi

if [[ $vi = openvz ]]; then
TUN=$(cat /dev/net/tun 2>&1)
if [[ ! $TUN =~ 'in bad state' ]] && [[ ! $TUN =~ '处于错误状态' ]] && [[ ! $TUN =~ 'Die Dateizugriffsnummer ist in schlechter Verfassung' ]]; then 
red "检测到未开启TUN，现尝试添加TUN支持" && sleep 4
cd /dev && mkdir net && mknod net/tun c 10 200 && chmod 0666 net/tun
TUN=$(cat /dev/net/tun 2>&1)
if [[ ! $TUN =~ 'in bad state' ]] && [[ ! $TUN =~ '处于错误状态' ]] && [[ ! $TUN =~ 'Die Dateizugriffsnummer ist in schlechter Verfassung' ]]; then 
green "添加TUN支持失败，建议与VPS厂商沟通或后台设置开启" && exit
else
echo '#!/bin/bash' > /root/tun.sh && echo 'cd /dev && mkdir net && mknod net/tun c 10 200 && chmod 0666 net/tun' >> /root/tun.sh && chmod +x /root/tun.sh
grep -qE "^ *@reboot root bash /root/tun.sh >/dev/null 2>&1" /etc/crontab || echo "@reboot root bash /root/tun.sh >/dev/null 2>&1" >> /etc/crontab
green "TUN守护功能已启动"
fi
fi
fi
# Menu information only: never used to authenticate downloads or validate updates.
# SB_MENU_REFRESH=1 bypasses all TTLs; actions that change networking force refresh.
sb_info_valid(){
jq -e --arg key "$1" '
if $key == "network" then
 type=="object" and ([.ipv4,.ipv6,.region4,.region6]|all(type=="string")) and
 (.ipv4=="" or (.ipv4|test("^([0-9]{1,3}\\.){3}[0-9]{1,3}$") and (split(".")|all(tonumber<=255)))) and
 (.ipv6=="" or (.ipv6|length<=45 and contains(":") and test("^[a-fA-F0-9:.]+$"))) and
 ([.region4,.region6]|all(length<=200 and (test("[\\x00-\\x1f\\x7f]")|not)))
elif $key == "cores" then
 type=="object" and (.stable|type=="string" and test("^[0-9]+\\.[0-9]+\\.[0-9]+$")) and
 (.preview|type=="string" and test("^[0-9]+\\.[0-9]+\\.[0-9]+-(alpha|beta|rc)\\.[0-9]+$"))
elif $key == "script" then
 type=="string" and length<524288 and test("^v[0-9]+\\.[0-9]+\\.[0-9]+(-fork\\.[0-9]+)?更新内容")
else false end' >/dev/null
}

sb_info_cache_get(){
local key=$1 ttl=$2 file=/etc/s-box/cache/menu-$1.json now data
[[ ${SB_MENU_REFRESH:-0} != 1 && -f $file && ! -L $file ]] || return 1
now=$(date +%s) || return 1
[[ $now =~ ^[0-9]+$ ]] || return 1
data=$(jq -ec --argjson now "$now" --argjson ttl "$ttl" '
select(.saved|type=="number") | select(.saved <= $now and $now-.saved < $ttl) | .data' "$file" 2>/dev/null) || return 1
printf '%s\n' "$data" | sb_info_valid "$key" || return 1
printf '%s\n' "$data"
}

sb_info_cache_put(){
local key=$1 dir=/etc/s-box/cache tmp now
[[ $key == network || $key == cores || $key == script ]] || return 1
[[ ! -L $dir ]] || return 1
mkdir -p "$dir" && chmod 700 "$dir" || return 1
now=$(date +%s) || return 1
[[ $now =~ ^[0-9]+$ ]] || return 1
tmp=$(umask 077; mktemp "$dir/.menu-$key.XXXXXX") || return 1
if ! jq -c --argjson now "$now" '{saved:$now,data:.}' > "$tmp" ||
 ! jq -c '.data' "$tmp" | sb_info_valid "$key" ||
 ! mv -f "$tmp" "$dir/menu-$key.json"; then rm -f "$tmp"; return 1; fi
}

sb_script_version_info(){
local data text
if data=$(sb_info_cache_get script 300); then jq -r . <<< "$data"; return; fi
text=$(curl -fsSL --connect-timeout 5 --max-time 10 https://raw.githubusercontent.com/redrohu/sing-box-yg/main/version) || return 1
data=$(printf '%s' "$text" | jq -Rs .) || return 1
printf '%s\n' "$data" | sb_info_valid script || return 1
printf '%s\n' "$data" | sb_info_cache_put script || :
printf '%s\n' "$text"
}

v4v6(){
local data stage file failed=0 status=0 SB_MENU_REFRESH=${SB_MENU_REFRESH:-0}
[[ ${1:-} != refresh ]] || SB_MENU_REFRESH=1
if ! data=$(sb_info_cache_get network 60); then
stage=$(umask 077; mktemp -d /etc/s-box/.network-info.XXXXXX) || return 1
# Four independent requests are bounded and run in parallel (not 4x the timeout).
(if curl -fsS4 --connect-timeout 2 --max-time 5 https://icanhazip.com > "$stage/ipv4"; then echo 0; else echo $?; fi > "$stage/status4") & local p4=$!
(if curl -fsS6 --connect-timeout 2 --max-time 5 https://icanhazip.com > "$stage/ipv6"; then echo 0; else echo $?; fi > "$stage/status6") & local p6=$!
(if curl -fsS4 --connect-timeout 2 --max-time 5 https://ip.fm > "$stage/geo4"; then echo 0; else echo $?; fi > "$stage/statusg4") & local g4=$!
(if curl -fsS6 --connect-timeout 2 --max-time 5 https://ip.fm > "$stage/geo6"; then echo 0; else echo $?; fi > "$stage/statusg6") & local g6=$!
wait "$p4" "$p6" "$g4" "$g6"
for file in status4 status6 statusg4 statusg6; do [[ $(cat "$stage/$file") == 0 ]] || failed=1; done
# On single-stack hosts do not cache partial failures; retry the missing family next time.
data=$(jq -nc --arg ipv4 "$(tr -d '\r\n' < "$stage/ipv4")" --arg ipv6 "$(tr -d '\r\n' < "$stage/ipv6")" \
 --arg region4 "$(sed -n 's/.*Location: //p' "$stage/geo4" | head -n1)" \
 --arg region6 "$(sed -n 's/.*Location: //p' "$stage/geo6" | head -n1)" \
 '{ipv4:$ipv4,ipv6:$ipv6,region4:$region4,region6:$region6}') || status=1
rm -rf "$stage"
if [[ $status != 0 ]] || ! printf '%s\n' "$data" | sb_info_valid network; then v4=; v6=; v4dq=; v6dq=; return 1; fi
[[ $failed != 0 ]] || printf '%s\n' "$data" | sb_info_cache_put network || :
fi
local -a values
mapfile -t values < <(jq -r '.ipv4,.ipv6,.region4,.region6' <<< "$data")
v4=${values[0]}; v6=${values[1]}; v4dq=${values[2]}; v6dq=${values[3]}
}
warpcheck(){
wgcfv6=$(curl -s6m5 https://www.cloudflare.com/cdn-cgi/trace -k | grep warp | cut -d= -f2)
wgcfv4=$(curl -s4m5 https://www.cloudflare.com/cdn-cgi/trace -k | grep warp | cut -d= -f2)
}

v6(){
v4orv6(){
if [ -z "$(curl -s4m5 icanhazip.com -k)" ]; then
echo
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
yellow "检测到 纯IPV6 VPS，添加NAT64"
echo -e "nameserver 2a00:1098:2b::1\nnameserver 2a00:1098:2c::1" > /etc/resolv.conf
ipv=prefer_ipv6
else
ipv=prefer_ipv4
fi
if [ -n "$(curl -s6m5 icanhazip.com -k)" ]; then
endip="2606:4700:d0::a29f:c001"
else
endip="162.159.192.1"
fi
}
warpcheck
if [[ ! $wgcfv4 =~ on|plus && ! $wgcfv6 =~ on|plus ]]; then
v4orv6
else
systemctl stop wg-quick@wgcf >/dev/null 2>&1
kill -15 $(pgrep warp-go) >/dev/null 2>&1 && sleep 2
v4orv6
systemctl start wg-quick@wgcf >/dev/null 2>&1
systemctl restart warp-go >/dev/null 2>&1
systemctl enable warp-go >/dev/null 2>&1
systemctl start warp-go >/dev/null 2>&1
fi
}

close(){
systemctl stop firewalld.service >/dev/null 2>&1
systemctl disable firewalld.service >/dev/null 2>&1
setenforce 0 >/dev/null 2>&1
ufw disable >/dev/null 2>&1
iptables -P INPUT ACCEPT >/dev/null 2>&1
iptables -P FORWARD ACCEPT >/dev/null 2>&1
iptables -P OUTPUT ACCEPT >/dev/null 2>&1
iptables -t mangle -F >/dev/null 2>&1
iptables -F >/dev/null 2>&1
iptables -X >/dev/null 2>&1
netfilter-persistent save >/dev/null 2>&1
if [[ -n $(apachectl -v 2>/dev/null) ]]; then
systemctl stop httpd.service >/dev/null 2>&1
systemctl disable httpd.service >/dev/null 2>&1
service apache2 stop >/dev/null 2>&1
systemctl disable apache2 >/dev/null 2>&1
fi
sleep 1
green "执行开放端口，关闭防火墙完毕"
}

openyn(){
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
readp "是否开放端口，关闭防火墙？\n1、是，执行 (回车默认)\n2、否，跳过！自行处理\n请选择【1-2】：" action
if [[ -z $action ]] || [[ "$action" = "1" ]]; then
close
elif [[ "$action" = "2" ]]; then
echo
else
red "输入错误,请重新选择" && openyn
fi
}

inssb(){
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
green "使用哪个内核版本？"
yellow "1：使用目前最新正式版内核 (回车默认)"
yellow "2：使用之前1.10.7正式版内核 (支持geosite分流、IP优选级切换，无Anytls协议)"
readp "请选择【1-2】：" menu
if [ -z "$menu" ] || [ "$menu" = "1" ] ; then
sbcore=$(curl -Ls https://github.com/SagerNet/sing-box/releases/latest | grep -oP 'tag/v\K[0-9.]+' | head -n 1)
else
sbcore='1.10.7'
fi
sb_update_core "$sbcore" install || return 1
sbnh=$(printf '%s\n' "$sbcore" | cut -d '.' -f 1,2)
blue "成功安装 Sing-box 内核版本：$sbcore"
}

inscertificate(){
ymzs(){
ym_vl_re=apple.com
echo
blue "Vless-reality的SNI域名默认为 apple.com"
tlsyn=true
ym_vm_ws=$(cat /root/ygkkkca/ca.log 2>/dev/null)
certificatec_vmess_ws='/root/ygkkkca/cert.crt'
certificatep_vmess_ws='/root/ygkkkca/private.key'
certificatec_hy2='/root/ygkkkca/cert.crt'
certificatep_hy2='/root/ygkkkca/private.key'
certificatec_tuic='/root/ygkkkca/cert.crt'
certificatep_tuic='/root/ygkkkca/private.key'
certificatec_an='/root/ygkkkca/cert.crt'
certificatep_an='/root/ygkkkca/private.key'
}

zqzs(){
ym_vl_re=apple.com
echo
blue "Vless-reality的SNI域名默认为 apple.com"
tlsyn=false
ym_vm_ws=www.bing.com
certificatec_vmess_ws='/etc/s-box/cert.pem'
certificatep_vmess_ws='/etc/s-box/private.key'
certificatec_hy2='/etc/s-box/cert.pem'
certificatep_hy2='/etc/s-box/private.key'
certificatec_tuic='/etc/s-box/cert.pem'
certificatep_tuic='/etc/s-box/private.key'
certificatec_an='/etc/s-box/cert.pem'
certificatep_an='/etc/s-box/private.key'
}

red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
green "二、生成并设置相关证书"
echo
blue "自动生成bing自签证书中……" && sleep 2
openssl ecparam -genkey -name prime256v1 -out /etc/s-box/private.key
openssl req -new -x509 -days 36500 -key /etc/s-box/private.key -out /etc/s-box/cert.pem -subj "/CN=www.bing.com"
echo
if [[ -f /etc/s-box/cert.pem ]]; then
blue "生成bing自签证书成功"
else
red "生成bing自签证书失败" && exit
fi
echo
if [[ -f /root/ygkkkca/cert.crt && -f /root/ygkkkca/private.key && -s /root/ygkkkca/cert.crt && -s /root/ygkkkca/private.key ]]; then
yellow "经检测，之前已使用Acme-yg脚本申请过Acme域名IP证书：$(cat /root/ygkkkca/ca.log) "
green "是否使用 $(cat /root/ygkkkca/ca.log) 域名IP证书？"
yellow "1：否！使用自签的证书 (回车默认)"
yellow "2：是！使用 $(cat /root/ygkkkca/ca.log) 域名IP证书"
readp "请选择【1-2】：" menu
if [ -z "$menu" ] || [ "$menu" = "1" ] ; then
zqzs
else
ymzs
fi
else
green "是否申请一个Acme域名IP证书？"
yellow "1：否！继续使用自签的证书 (回车默认)"
yellow "2：是！使用Acme-yg脚本申请Acme证书 (支持80端口域名IP证书模式与Dns API域名模式)"
readp "请选择【1-2】：" menu
if [ -z "$menu" ] || [ "$menu" = "1" ] ; then
zqzs
else
bash <(curl -Ls https://raw.githubusercontent.com/yonggekkk/acme-yg/main/acme.sh)
if [[ ! -f /root/ygkkkca/cert.crt && ! -f /root/ygkkkca/private.key && ! -s /root/ygkkkca/cert.crt && ! -s /root/ygkkkca/private.key ]]; then
red "Acme证书申请失败，继续使用自签证书" 
zqzs
else
ymzs
fi
fi
fi
}

chooseport(){
if [[ -z $port ]]; then
port=$(shuf -i 10000-65535 -n 1)
until [[ -z $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") && -z $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]] 
do
[[ -n $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") || -n $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]] && yellow "\n端口被占用，请重新输入端口" && readp "自定义端口:" port
done
else
until [[ -z $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") && -z $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]]
do
[[ -n $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") || -n $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]] && yellow "\n端口被占用，请重新输入端口" && readp "自定义端口:" port
done
fi
blue "确认的端口：$port" && sleep 2
}

vlport(){
readp "\n设置Vless-reality端口 (回车跳过为10000-65535之间的随机端口)：" port
chooseport
port_vl_re=$port
}
vmport(){
readp "\n设置Vmess-ws端口 (回车跳过为10000-65535之间的随机端口)：" port
chooseport
port_vm_ws=$port
}
hy2port(){
readp "\n设置Hysteria2主端口 (回车跳过为10000-65535之间的随机端口)：" port
chooseport
port_hy2=$port
}
tu5port(){
readp "\n设置Tuic5主端口 (回车跳过为10000-65535之间的随机端口)：" port
chooseport
port_tu=$port
}
anport(){
readp "\n设置Anytls主端口，最新内核时可用 (回车跳过为10000-65535之间的随机端口)：" port
chooseport
port_an=$port
}

insport(){
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
green "三、设置各个协议端口"
yellow "1：自动生成每个协议的随机端口 (10000-65535范围内)，回车默认。请确保VPS后台已开放所有端口"
yellow "2：自定义每个协议端口。请确保VPS后台已开放指定的端口"
readp "请输入【1-2】：" port
if [ -z "$port" ] || [ "$port" = "1" ] ; then
ports=()
for i in {1..5}; do
while true; do
port=$(shuf -i 10000-65535 -n 1)
if ! [[ " ${ports[@]} " =~ " $port " ]] && \
[[ -z $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]] && \
[[ -z $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]]; then
ports+=($port)
break
fi
done
done
port_vm_ws=${ports[0]}
port_vl_re=${ports[1]}
port_hy2=${ports[2]}
port_tu=${ports[3]}
port_an=${ports[4]}
if [[ $tlsyn == "true" ]]; then
numbers=("2053" "2083" "2087" "2096" "8443")
else
numbers=("8080" "8880" "2052" "2082" "2086" "2095")
fi
port_vm_ws=${numbers[$RANDOM % ${#numbers[@]}]}
until [[ -z $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port_vm_ws") ]]
do
if [[ $tlsyn == "true" ]]; then
numbers=("2053" "2083" "2087" "2096" "8443")
else
numbers=("8080" "8880" "2052" "2082" "2086" "2095")
fi
port_vm_ws=${numbers[$RANDOM % ${#numbers[@]}]}
done
echo
blue "根据Vmess-ws协议是否启用TLS，随机指定支持CDN优选IP的标准端口：$port_vm_ws"
else
vlport && vmport && hy2port && tu5port
if [[ "$sbnh" != "1.10" ]]; then
anport
fi
fi
echo
blue "各协议端口确认如下"
blue "Vless-reality端口：$port_vl_re"
blue "Vmess-ws端口：$port_vm_ws"
blue "Hysteria-2端口：$port_hy2"
blue "Tuic-v5端口：$port_tu"
if [[ "$sbnh" != "1.10" ]]; then
blue "Anytls端口：$port_an"
fi
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
green "四、自动生成各个协议统一的uuid (密码)"
uuid=$(/etc/s-box/sing-box generate uuid)
blue "已确认uuid (密码)：${uuid}"
blue "已确认Vmess的path路径：${uuid}-vm"
}

inssbjsonser(){
if [[ "$sbnh" != "1.10" && ! "$sbnh" =~ ^1\.(1[2-9]|[2-9][0-9])$ ]]; then
red "配置支持 1.10.x（旧版）或 1.12+（新版），不支持当前内核：$sbnh"
return 1
fi
cat > /etc/s-box/sb10.json <<EOF
{
"log": {
    "disabled": false,
    "level": "info",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "vless",
      "sniff": true,
      "sniff_override_destination": true,
      "tag": "vless-sb",
      "listen": "::",
      "listen_port": ${port_vl_re},
      "users": [
        {
          "uuid": "${uuid}",
          "flow": "xtls-rprx-vision"
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "${ym_vl_re}",
          "reality": {
          "enabled": true,
          "handshake": {
            "server": "${ym_vl_re}",
            "server_port": 443
          },
          "private_key": "$private_key",
          "short_id": ["$short_id"]
        }
      }
    },
{
        "type": "vmess",
        "sniff": true,
        "sniff_override_destination": true,
        "tag": "vmess-sb",
        "listen": "::",
        "listen_port": ${port_vm_ws},
        "users": [
            {
                "uuid": "${uuid}",
                "alterId": 0
            }
        ],
        "transport": {
            "type": "ws",
            "path": "${uuid}-vm",
            "max_early_data":2048,
            "early_data_header_name": "Sec-WebSocket-Protocol"    
        },
        "tls":{
                "enabled": ${tlsyn},
                "server_name": "${ym_vm_ws}",
                "certificate_path": "$certificatec_vmess_ws",
                "key_path": "$certificatep_vmess_ws"
            }
    }, 
    {
        "type": "hysteria2",
        "sniff": true,
        "sniff_override_destination": true,
        "tag": "hy2-sb",
        "listen": "::",
        "listen_port": ${port_hy2},
        "users": [
            {
                "password": "${uuid}"
            }
        ],
        "ignore_client_bandwidth":false,
        "tls": {
            "enabled": true,
            "alpn": [
                "h3"
            ],
            "certificate_path": "$certificatec_hy2",
            "key_path": "$certificatep_hy2"
        }
    },
        {
            "type":"tuic",
            "sniff": true,
            "sniff_override_destination": true,
            "tag": "tuic5-sb",
            "listen": "::",
            "listen_port": ${port_tu},
            "users": [
                {
                    "uuid": "${uuid}",
                    "password": "${uuid}"
                }
            ],
            "congestion_control": "bbr",
            "tls":{
                "enabled": true,
                "alpn": [
                    "h3"
                ],
                "certificate_path": "$certificatec_tuic",
                "key_path": "$certificatep_tuic"
            }
        }
],
"outbounds": [
{
"type":"direct",
"tag":"direct",
"domain_strategy": "$ipv"
},
{
"type":"direct",
"tag": "vps-outbound-v4", 
"domain_strategy":"prefer_ipv4"
},
{
"type":"direct",
"tag": "vps-outbound-v6",
"domain_strategy":"prefer_ipv6"
},
{
"type": "socks",
"tag": "socks-out",
"server": "127.0.0.1",
"server_port": 40000,
"version": "5"
},
{
"type":"direct",
"tag":"socks-IPv4-out",
"detour":"socks-out",
"domain_strategy":"prefer_ipv4"
},
{
"type":"direct",
"tag":"socks-IPv6-out",
"detour":"socks-out",
"domain_strategy":"prefer_ipv6"
},
{
"type":"direct",
"tag":"warp-IPv4-out",
"detour":"wireguard-out",
"domain_strategy":"prefer_ipv4"
},
{
"type":"direct",
"tag":"warp-IPv6-out",
"detour":"wireguard-out",
"domain_strategy":"prefer_ipv6"
},
{
"type":"wireguard",
"tag":"wireguard-out",
"server":"$endip",
"server_port":2408,
"local_address":[
"172.16.0.2/32",
"${v6}/128"
],
"private_key":"$pvk",
"peer_public_key":"bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
"reserved":$res
},
{
"type": "block",
"tag": "block"
}
],
"route":{
"rules":[
{
"protocol": [
"quic",
"stun"
],
"outbound": "block"
},
{
"outbound":"warp-IPv4-out",
"domain_suffix": [
"yg_kkk"
]
,"geosite": [
"yg_kkk"
]
},
{
"outbound":"warp-IPv6-out",
"domain_suffix": [
"yg_kkk"
]
,"geosite": [
"yg_kkk"
]
},
{
"outbound":"socks-IPv4-out",
"domain_suffix": [
"yg_kkk"
]
,"geosite": [
"yg_kkk"
]
},
{
"outbound":"socks-IPv6-out",
"domain_suffix": [
"yg_kkk"
]
,"geosite": [
"yg_kkk"
]
},
{
"outbound":"vps-outbound-v4",
"domain_suffix": [
"yg_kkk"
]
,"geosite": [
"yg_kkk"
]
},
{
"outbound":"vps-outbound-v6",
"domain_suffix": [
"yg_kkk"
]
,"geosite": [
"yg_kkk"
]
},
{
"outbound": "direct",
"network": "udp,tcp"
}
]
}
}
EOF

cat > /etc/s-box/sb11.json <<EOF
{
"log": {
    "disabled": false,
    "level": "info",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "vless",

      
      "tag": "vless-sb",
      "listen": "::",
      "listen_port": ${port_vl_re},
      "users": [
        {
          "uuid": "${uuid}",
          "flow": "xtls-rprx-vision"
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "${ym_vl_re}",
          "reality": {
          "enabled": true,
          "handshake": {
            "server": "${ym_vl_re}",
            "server_port": 443
          },
          "private_key": "$private_key",
          "short_id": ["$short_id"]
        }
      }
    },
{
        "type": "vmess",

 
        "tag": "vmess-sb",
        "listen": "::",
        "listen_port": ${port_vm_ws},
        "users": [
            {
                "uuid": "${uuid}",
                "alterId": 0
            }
        ],
        "transport": {
            "type": "ws",
            "path": "${uuid}-vm",
            "max_early_data":2048,
            "early_data_header_name": "Sec-WebSocket-Protocol"    
        },
        "tls":{
                "enabled": ${tlsyn},
                "server_name": "${ym_vm_ws}",
                "certificate_path": "$certificatec_vmess_ws",
                "key_path": "$certificatep_vmess_ws"
            }
    }, 
    {
        "type": "hysteria2",

 
        "tag": "hy2-sb",
        "listen": "::",
        "listen_port": ${port_hy2},
        "users": [
            {
                "password": "${uuid}"
            }
        ],
        "ignore_client_bandwidth":false,
        "tls": {
            "enabled": true,
            "alpn": [
                "h3"
            ],
            "certificate_path": "$certificatec_hy2",
            "key_path": "$certificatep_hy2"
        }
    },
        {
            "type":"tuic",

     
            "tag": "tuic5-sb",
            "listen": "::",
            "listen_port": ${port_tu},
            "users": [
                {
                    "uuid": "${uuid}",
                    "password": "${uuid}"
                }
            ],
            "congestion_control": "bbr",
            "tls":{
                "enabled": true,
                "alpn": [
                    "h3"
                ],
                "certificate_path": "$certificatec_tuic",
                "key_path": "$certificatep_tuic"
            }
        },
        {
            "type":"anytls",
            "tag":"anytls-sb",
            "listen":"::",
            "listen_port":${port_an},
            "users":[
                {
                  "password":"${uuid}"
                }
            ],
            "padding_scheme":[],
            "tls":{
                "enabled": true,
                "certificate_path": "$certificatec_an",
                "key_path": "$certificatep_an"
            }
        }
],
"endpoints":[
{
"type":"wireguard",
"tag":"warp-out",
"address":[
"172.16.0.2/32",
"${v6}/128"
],
"private_key":"$pvk",
"peers": [
{
"address": "$endip",
"port":2408,
"public_key":"bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
"allowed_ips": [
"0.0.0.0/0",
"::/0"
],
"reserved":$res
}
]
}
],









"outbounds": [
{
"type":"direct",
"tag":"direct"
},
{
"type": "socks",
"tag": "socks-out",
"server": "127.0.0.1",
"server_port": 40000,
"version": "5"
}
],
"route":{
"rules":[
{
 "action": "sniff"
},
{
"action": "resolve",
"domain_suffix":[
"yg_kkk"
],
"strategy": "prefer_ipv4"
},
{
"action": "resolve",
"domain_suffix":[
"yg_kkk"
],
"strategy": "prefer_ipv6"
},
{
"domain_suffix":[
"yg_kkk"
],
"outbound":"socks-out"
},
{
"domain_suffix":[
"yg_kkk"
],
"outbound":"warp-out"
},
{
"outbound": "direct",
"network": "udp,tcp"
}
],
"default_domain_resolver": {"server": "dns-local", "strategy": "$ipv"}
},
"dns": {"servers": [{"type": "local", "tag": "dns-local"}]}
}
EOF
[[ "$sbnh" == "1.10" ]] && num=10 || num=11
cp /etc/s-box/sb${num}.json /etc/s-box/sb.json
}

sbservice(){
sb_config_check || return 1
if command -v apk >/dev/null 2>&1; then
echo '#!/sbin/openrc-run
description="sing-box service"
command="/etc/s-box/sing-box"
command_args="run -c /etc/s-box/sb.json"
command_background=true
pidfile="/var/run/sing-box.pid"' > /etc/init.d/sing-box
chmod +x /etc/init.d/sing-box
rc-update add sing-box default
rc-service sing-box start
else
cat > /etc/systemd/system/sing-box.service <<EOF
[Unit]
After=network.target nss-lookup.target
[Service]
User=root
WorkingDirectory=/root
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
ExecStart=/etc/s-box/sing-box run -c /etc/s-box/sb.json
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=10
LimitNOFILE=infinity
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable sing-box >/dev/null 2>&1
systemctl start sing-box
systemctl restart sing-box
fi
}

ipuuid(){
if command -v apk >/dev/null 2>&1; then
status_cmd="rc-service sing-box status"
status_pattern="started"
else
status_cmd="systemctl is-active sing-box"
status_pattern="active"
fi
if [[ -n $($status_cmd 2>/dev/null | grep -w "$status_pattern") && -f '/etc/s-box/sb.json' ]]; then
v4v6 refresh
if [[ -n $v4 && -n $v6 ]]; then
green "调整IPv4/IPV6配置输出"
yellow "1：刷新本地IP，使用IPV4配置输出 (回车默认) "
yellow "2：刷新本地IP，使用IPV6配置输出"
readp "请选择【1-2】：" menu
if [ -z "$menu" ] || [ "$menu" = "1" ]; then
server_ip="$v4"
echo "$server_ip" > /etc/s-box/server_ip.log
server_ipcl="$v4"
echo "$server_ipcl" > /etc/s-box/server_ipcl.log
else
server_ip="[$v6]"
echo "$server_ip" > /etc/s-box/server_ip.log
server_ipcl="$v6"
echo "$server_ipcl" > /etc/s-box/server_ipcl.log
fi
else
yellow "VPS并不是双栈VPS，不支持IP配置输出的切换"
serip=$(curl -s4m5 icanhazip.com -k || curl -s6m5 icanhazip.com -k)
if [[ "$serip" =~ : ]]; then
server_ip="[$serip]"
echo "$server_ip" > /etc/s-box/server_ip.log
server_ipcl="$serip"
echo "$server_ipcl" > /etc/s-box/server_ipcl.log
else
server_ip="$serip"
echo "$server_ip" > /etc/s-box/server_ip.log
server_ipcl="$serip"
echo "$server_ipcl" > /etc/s-box/server_ipcl.log
fi
fi
else
red "Sing-box服务未运行" && exit
fi
}

wgcfgo(){
warpcheck
if [[ ! $wgcfv4 =~ on|plus && ! $wgcfv6 =~ on|plus ]]; then
ipuuid
else
systemctl stop wg-quick@wgcf >/dev/null 2>&1
kill -15 $(pgrep warp-go) >/dev/null 2>&1 && sleep 2
ipuuid
systemctl start wg-quick@wgcf >/dev/null 2>&1
systemctl restart warp-go >/dev/null 2>&1
systemctl enable warp-go >/dev/null 2>&1
systemctl start warp-go >/dev/null 2>&1
fi
}

result_vl_vm_hy_tu(){
# One parse, stable tags (legacy index fallback), strict required fields.
# @sh escapes scalar data; assignment names below are fixed, never user-provided.
local parsed
parsed=$(jq -er '
def pick($tag; $i): ([.inbounds[] | select(.tag == $tag)][0] // .inbounds[$i]);
def port: type == "number" and . >= 1 and . <= 65535 and . == floor;
pick("vless-sb";0) as $v | pick("vmess-sb";1) as $w |
pick("hy2-sb";2) as $h | pick("tuic5-sb";3) as $t | pick("anytls-sb";4) as $a |
if $v.type != "vless" or $w.type != "vmess" or $h.type != "hysteria2" or $t.type != "tuic" or
   ([$v.listen_port,$w.listen_port,$h.listen_port,$t.listen_port] | all(port) | not) or
   ([$v.users[0].uuid,$v.tls.server_name,$v.tls.reality.short_id[0],$w.transport.path,$w.tls.server_name,$h.tls.key_path,$t.tls.key_path] | all(type == "string") | not) or
   ($v.users[0].uuid | length == 0) or ($w.tls.enabled | type != "boolean") or
   ($a != null and ($a.type != "anytls" or ($a.listen_port | port | not) or ($a.tls.key_path | type != "string")))
then error("missing/invalid server fields; exports kept unchanged") else . end |
{uuid:$v.users[0].uuid,vl_port:$v.listen_port,vl_name:$v.tls.server_name,short_id:$v.tls.reality.short_id[0],
 ws_path:$w.transport.path,vm_port:$w.listen_port,tls:$w.tls.enabled,vm_name_default:$w.tls.server_name,
 hy2_port:$h.listen_port,hy2_sniname:$h.tls.key_path,tu5_port:$t.listen_port,tu5_sniname:$t.tls.key_path,
 an_port:($a.listen_port // ""),an_sniname:($a.tls.key_path // "")} |
to_entries | map(.key + "=" + (.value | @sh)) | join("\n")
' /etc/s-box/sb.json) || { red "服务端字段校验失败，未生成新订阅。" >&2; return 1; }
eval "$parsed" || return 1
if [[ -f /root/ygkkkca/cert.crt && -f /root/ygkkkca/private.key && -s /root/ygkkkca/cert.crt && -s /root/ygkkkca/private.key ]]; then
ym=`bash ~/.acme.sh/acme.sh --list | tail -1 | awk '{print $1}'`
echo $ym > /root/ygkkkca/ca.log
fi
rm -rf "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_argo.txt" "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws.txt" "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_tls.txt"
server_ip=$(cat /etc/s-box/server_ip.log) || return 1
[[ -n $server_ip ]] || return 1
server_ipcl=$(cat /etc/s-box/server_ipcl.log) || return 1
[[ -n $server_ipcl ]] || return 1
public_key=$(cat /etc/s-box/public.key) || return 1
[[ -n $public_key ]] || return 1
argo=$(cat /etc/s-box/argo.log 2>/dev/null | grep -a trycloudflare.com | awk 'NR==2{print}' | awk -F// '{print $2}' | awk '{print $1}')
vm_name=$vm_name_default
if [[ "$tls" = "false" ]]; then
if [[ -f /etc/s-box/cfymjx.txt ]]; then
vm_name=$(cat /etc/s-box/cfymjx.txt 2>/dev/null)
else
vm_name=$vm_name_default
fi
vmadd_local=$server_ipcl
vmadd_are_local=$server_ip
else
vmadd_local=$vm_name
vmadd_are_local=$vm_name
fi
if [[ -f /etc/s-box/cfvmadd_local.txt ]]; then
vmadd_local=$(cat /etc/s-box/cfvmadd_local.txt 2>/dev/null)
vmadd_are_local=$(cat /etc/s-box/cfvmadd_local.txt 2>/dev/null)
else
if [[ "$tls" = "false" ]]; then
if [[ -f /etc/s-box/cfymjx.txt ]]; then
vm_name=$(cat /etc/s-box/cfymjx.txt 2>/dev/null)
else
vm_name=$vm_name_default
fi
vmadd_local=$server_ipcl
vmadd_are_local=$server_ip
else
vmadd_local=$vm_name
vmadd_are_local=$vm_name
fi
fi
if [[ -f /etc/s-box/cfvmadd_argo.txt ]]; then
vmadd_argo=$(cat /etc/s-box/cfvmadd_argo.txt 2>/dev/null)
else
vmadd_argo=cloudflare-ech.com
fi
hy2_ports=$(sb_port_hop_manage list "$hy2_port" | paste -sd, -)
if [[ -n $hy2_ports ]]; then
cmhy2pt=$(echo $hy2_ports | tr ':' '-')
hyps="&mport=$cmhy2pt"
sbhy2pt=$(echo "$hy2_ports" | grep -o '[0-9]\+:[0-9]\+' | sed 's/.*/"&"/' | paste -sd,)
else
hyps=
fi
ym=$(cat /root/ygkkkca/ca.log 2>/dev/null)
if [[ "$hy2_sniname" = '/etc/s-box/private.key' ]]; then
SHA256=$(openssl x509 -in /etc/s-box/cert.pem -outform DER | sha256sum | awk '{print $1}')
echo "$SHA256" > "${SB_EXPORT_DIR:-/etc/s-box}/SHA256.txt" || return 1
SHA256=$(cat "${SB_EXPORT_DIR:-/etc/s-box}/SHA256.txt")
hy2_name=www.bing.com
sb_hy2_ip=$server_ip
cl_hy2_ip=$server_ipcl
ins_hy2=1
hy2_ins=true
else
hy2_name=$ym
sb_hy2_ip=$ym
cl_hy2_ip=$ym
ins_hy2=0
hy2_ins=false
fi
ym=$(cat /root/ygkkkca/ca.log 2>/dev/null)
if [[ "$tu5_sniname" = '/etc/s-box/private.key' ]]; then
tu5_name=www.bing.com
sb_tu5_ip=$server_ip
cl_tu5_ip=$server_ipcl
ins=1
tu5_ins=true
else
tu5_name=$ym
sb_tu5_ip=$ym
cl_tu5_ip=$ym
ins=0
tu5_ins=false
fi
ym=$(cat /root/ygkkkca/ca.log 2>/dev/null)
if [[ "$an_sniname" = '/etc/s-box/private.key' ]]; then
an_name=www.bing.com
sb_an_ip=$server_ip
cl_an_ip=$server_ipcl
ins_an=1
an_ins=true
else
an_name=$ym
sb_an_ip=$ym
cl_an_ip=$ym
ins_an=0
an_ins=false
fi
}

resvless(){
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
vl_link="vless://$uuid@$server_ip:$vl_port?encryption=none&flow=xtls-rprx-vision&security=reality&sni=$vl_name&fp=chrome&pbk=$public_key&sid=$short_id&type=tcp&headerType=none#${node_prefix_uri_label}vl-reality${node_suffix_uri_label}"
echo "$vl_link" > "${SB_EXPORT_DIR:-/etc/s-box}/vl_reality.txt" || return 1
red "🚀【 vless-reality-vision 】节点信息如下：" && sleep 2
echo
echo "分享链接【v2ran(切换singbox内核)、nekobox、小火箭shadowrocket】"
echo -e "${yellow}$vl_link${plain}"
echo
echo "二维码【v2ran(切换singbox内核)、nekobox、小火箭shadowrocket】"
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/vl_reality.txt")"
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
}

resvmess(){
if [[ "$tls" = "false" ]]; then
if ps -ef 2>/dev/null | grep "[l]ocalhost:$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port')" >/dev/null 2>&1; then
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "🚀【 vmess-ws(tls)+Argo 】临时节点信息如下(可选择3-8-3，自定义CDN优选地址)：" && sleep 2
echo
echo "分享链接【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo -e "${yellow}vmess://$(echo '{"add":"'$vmadd_argo'","aid":"0","host":"'$argo'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"443","ps":"'"${node_prefix_label}vm-argo${node_suffix_label}"'","tls":"tls","sni":"'$argo'","fp":"chrome","type":"none","v":"2"}' | base64 -w 0)${plain}"
echo
echo "二维码【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo 'vmess://'$(echo '{"add":"'$vmadd_argo'","aid":"0","host":"'$argo'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"443","ps":"'"${node_prefix_label}vm-argo${node_suffix_label}"'","tls":"tls","sni":"'$argo'","fp":"chrome","type":"none","v":"2"}' | base64 -w 0) > "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_argols.txt" || return 1
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_argols.txt")"
fi
if ps -ef 2>/dev/null | grep -v '[x]http-argo/cloudflared' | grep -q '[c]loudflared.*run'; then
argogd=$(cat /etc/s-box/sbargoym.log 2>/dev/null)
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "🚀【 vmess-ws(tls)+Argo 】固定节点信息如下 (可选择3-8-3，自定义CDN优选地址)：" && sleep 2
echo
echo "分享链接【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo -e "${yellow}vmess://$(echo '{"add":"'$vmadd_argo'","aid":"0","host":"'$argogd'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"443","ps":"'"${node_prefix_label}vm-argo${node_suffix_label}"'","tls":"tls","sni":"'$argogd'","fp":"chrome","type":"none","v":"2"}' | base64 -w 0)${plain}"
echo
echo "二维码【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo 'vmess://'$(echo '{"add":"'$vmadd_argo'","aid":"0","host":"'$argogd'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"443","ps":"'"${node_prefix_label}vm-argo${node_suffix_label}"'","tls":"tls","sni":"'$argogd'","fp":"chrome","type":"none","v":"2"}' | base64 -w 0) > "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_argogd.txt" || return 1
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_argogd.txt")"
fi
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "🚀【 vmess-ws 】节点信息如下 (建议选择3-8-1，设置为CDN优选节点)：" && sleep 2
echo
echo "分享链接【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo -e "${yellow}vmess://$(echo '{"add":"'$vmadd_are_local'","aid":"0","host":"'$vm_name'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"'$vm_port'","ps":"'"${node_prefix_label}vm-ws${node_suffix_label}"'","tls":"","type":"none","v":"2"}' | base64 -w 0)${plain}"
echo
echo "二维码【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo 'vmess://'$(echo '{"add":"'$vmadd_are_local'","aid":"0","host":"'$vm_name'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"'$vm_port'","ps":"'"${node_prefix_label}vm-ws${node_suffix_label}"'","tls":"","type":"none","v":"2"}' | base64 -w 0) > "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws.txt" || return 1
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws.txt")"
else
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "🚀【 vmess-ws-tls 】节点信息如下 (建议选择3-8-1，设置为CDN优选节点)：" && sleep 2
echo
echo "分享链接【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo -e "${yellow}vmess://$(echo '{"add":"'$vmadd_are_local'","aid":"0","host":"'$vm_name'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"'$vm_port'","ps":"'"${node_prefix_label}vm-ws-tls${node_suffix_label}"'","tls":"tls","sni":"'$vm_name'","fp":"chrome","type":"none","v":"2"}' | base64 -w 0)${plain}"
echo
echo "二维码【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo 'vmess://'$(echo '{"add":"'$vmadd_are_local'","aid":"0","host":"'$vm_name'","id":"'$uuid'","net":"ws","path":"'$ws_path'","port":"'$vm_port'","ps":"'"${node_prefix_label}vm-ws-tls${node_suffix_label}"'","tls":"tls","sni":"'$vm_name'","fp":"chrome","type":"none","v":"2"}' | base64 -w 0) > "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_tls.txt" || return 1
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/vm_ws_tls.txt")"
fi
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
}

reshy2(){
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
hy2_link="hysteria2://$uuid@$sb_hy2_ip:$hy2_port?security=tls&alpn=h3&insecure=0&allowInsecure=0$hyps&sni=$hy2_name&pinSHA256=$SHA256#${node_prefix_uri_label}hy2${node_suffix_uri_label}"
#hy2_link="hysteria2://$uuid@$sb_hy2_ip:$hy2_port?security=tls&alpn=h3&insecure=$ins_hy2&allowInsecure=$ins_hy2$hyps&sni=$hy2_name#${node_prefix_uri_label}hy2${node_suffix_uri_label}"
echo "$hy2_link" > "${SB_EXPORT_DIR:-/etc/s-box}/hy2.txt" || return 1
red "🚀【 Hysteria-2 】节点信息如下：" && sleep 2
echo
echo "分享链接【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
echo -e "${yellow}$hy2_link${plain}"
echo
echo "二维码【v2rayn、v2rayng、nekobox、小火箭shadowrocket】"
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/hy2.txt")"
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
}

restu5(){
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
tuic5_link="tuic://$uuid:$uuid@$sb_tu5_ip:$tu5_port?congestion_control=bbr&udp_relay_mode=native&alpn=h3&sni=$tu5_name&insecure=$ins&allowInsecure=$ins&allow_insecure=$ins#${node_prefix_uri_label}tu5${node_suffix_uri_label}"
echo "$tuic5_link" > "${SB_EXPORT_DIR:-/etc/s-box}/tuic5.txt" || return 1
red "🚀【 Tuic-v5 】节点信息如下：" && sleep 2
echo
echo "分享链接【v2rayn、nekobox、小火箭shadowrocket】"
echo -e "${yellow}$tuic5_link${plain}"
echo
echo "二维码【v2rayn、nekobox、小火箭shadowrocket】"
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/tuic5.txt")"
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
}

resan(){
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
an_link="anytls://$uuid@$sb_an_ip:$an_port?&sni=$an_name&allowInsecure=$ins_an&insecure=$ins_an#${node_prefix_uri_label}anytls${node_suffix_uri_label}"
echo "$an_link" > "${SB_EXPORT_DIR:-/etc/s-box}/an.txt" || return 1
red "🚀【 Anytls】节点信息如下：" && sleep 2
echo
echo "分享链接【v2rayn、小火箭shadowrocket】"
echo -e "${yellow}$an_link${plain}"
echo
echo "二维码【v2rayn、nekobox、小火箭shadowrocket】"
qrencode -o - -t ANSIUTF8 "$(cat "${SB_EXPORT_DIR:-/etc/s-box}/an.txt")"
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
}

sb_client(){
(
umask 077
node_suffix_load || return 1
local xhttp_cl_node= xhttp_cl_name= xhttp_argo_cl_node= xhttp_argo_cl_name=
if [[ -f /etc/s-box/xhttp/config.json ]]; then
xhttp_mihomo_load || return 1
fi
if [[ -f /etc/s-box/xhttp-argo/config.json ]]; then
xhttp_argo_mihomo_load || return 1
fi
local client_stage client_raw
client_stage=$(mktemp -d /etc/s-box/client-stage.XXXXXX) || return 1
trap 'rm -rf "$client_stage"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
client_raw="$client_stage/raw.json"

sbhy2ports(){
if [[ -n $hy2_ports ]]; then
    cat <<EOF
  "server_ports": [ $sbhy2pt ],
EOF
fi
}

clxhttp2(){
[[ -z $xhttp_argo_cl_node ]] || printf '\n- %s' "$xhttp_argo_cl_node"
[[ -z $xhttp_cl_node ]] || printf '\n- %s' "$xhttp_cl_node"
}
sbany2(){
  if [[ "$sbnh" != "1.10" ]]; then
    cat <<EOF
         {
            "type": "anytls",
            "tag": "${node_prefix_label}anytls${node_suffix_label}",
            "server": "$sb_an_ip",
            "server_port": $an_port,
            "password": "$uuid",
            "idle_session_check_interval": "30s",
            "idle_session_timeout": "30s",
            "min_idle_session": 5,
            "tls": {
                "enabled": true,
                "insecure": $an_ins,
                "server_name": "$an_name"
            }
         },
EOF
  fi
}
clany2(){
  if [[ "$sbnh" != "1.10" ]]; then
    cat <<EOF
- name: "${node_prefix_label}anytls${node_suffix_label}"
  type: anytls
  server: $cl_an_ip
  port: $an_port
  password: $uuid
  client-fingerprint: chrome
  udp: true
  idle-session-check-interval: 30
  idle-session-timeout: 30
  sni: $an_name
  skip-cert-verify: $an_ins
EOF
  fi
}

sball(){
cat <<EOF
{
  "log": {
    "level": "info",
    "timestamp": true
  },
  "http_clients": [
    {
      "tag": "rule-set-direct",
      "domain_resolver": "dns-cn"
    }
  ],
  "dns": {
    "servers": [
      {
        "type": "fakeip",
        "tag": "fakeip",
        "inet4_range": "198.18.0.0/15",
        "inet6_range": "fc00::/18"
      },
      {
        "type": "udp",
        "tag": "dns-cn",
        "server": "223.5.5.5",
        "server_port": 53
      },
      {
        "type": "https",
        "tag": "dns-proxy",
        "server": "dns.google",
        "domain_resolver": "dns-cn",
        "detour": "proxy"
      }
    ],
    "rules": [
      {
        "clash_mode": "Direct",
        "action": "route",
        "server": "dns-cn"
      },
      {
        "clash_mode": "Global",
        "action": "route",
        "server": "dns-proxy"
      },
      {
        "rule_set": [
          "geosite-cn"
        ],
        "action": "route",
        "server": "dns-cn"
      },
      {
        "query_type": [
          "A",
          "AAAA"
        ],
        "action": "route",
        "server": "fakeip"
      }
    ],
    "final": "dns-proxy",
    "strategy": "prefer_ipv4",
    "cache_capacity": 8192,
    "optimistic": {
      "enabled": true,
      "timeout": "1h"
    },
    "timeout": "10s",
    "reverse_mapping": true
  },
  "inbounds": [
    {
      "type": "tun",
      "tag": "tun-in",
      "address": [
        "172.19.0.1/30",
        "fdfe:dcba:9876::1/126"
      ],
      "auto_route": true,
      "strict_route": true,
      "mtu": 1420
    }
  ],
  "route": {
    "default_http_client": "rule-set-direct",
    "default_domain_resolver": "dns-cn",
    "auto_detect_interface": true,
    "rule_set": [
      {
        "tag": "geosite-cn",
        "type": "remote",
        "format": "binary",
        "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/cn.srs"
      },
      {
        "tag": "geoip-cn",
        "type": "remote",
        "format": "binary",
        "url": "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs"
      }
    ],
    "rules": [
      {
        "inbound": "tun-in",
        "action": "sniff"
      },
      {
        "type": "logical",
        "mode": "or",
        "rules": [{"protocol": "dns"}, {"port": 53}],
        "action": "hijack-dns"
      },
      {
        "clash_mode": "Direct",
        "action": "route",
        "outbound": "direct"
      },
      {
        "clash_mode": "Global",
        "action": "route",
        "outbound": "proxy"
      },
      {
        "ip_is_private": true,
        "action": "route",
        "outbound": "direct"
      },
      {
        "rule_set": [
          "geosite-cn"
        ],
        "action": "route",
        "outbound": "direct"
      },
      {
        "rule_set": [
          "geoip-cn"
        ],
        "action": "route",
        "outbound": "direct"
      },
      {
        "network": [
          "tcp",
          "udp"
        ],
        "port": 853,
        "action": "reject"
      }
    ],
    "final": "proxy"
  },
  "experimental": {
    "cache_file": {
      "enabled": true,
      "store_dns": true
    },
    "clash_api": {
      "external_controller": "127.0.0.1:9090",
      "external_ui": "ui",
      "default_mode": "Rule"
    }
  },
  "outbounds": [
    {
      "type": "vless",
      "tag": "${node_prefix_label}vless${node_suffix_label}",
      "server": "$server_ipcl",
      "server_port": $vl_port,
      "uuid": "$uuid",
      "flow": "xtls-rprx-vision",
      "tls": {
        "enabled": true,
        "server_name": "$vl_name",
        "utls": {
          "enabled": true,
          "fingerprint": "chrome"
        },
      "reality": {
          "enabled": true,
          "public_key": "$public_key",
          "short_id": "$short_id"
        }
      }
    },
{
            "server": "$vmadd_local",
            "server_port": $vm_port,
            "tag": "${node_prefix_label}vmess${node_suffix_label}",
            "tls": {
                "enabled": $tls,
                "server_name": "$vm_name",
                "insecure": false,
                "utls": {
                    "enabled": true,
                    "fingerprint": "chrome"
                }
            },
            "transport": {
                "headers": {
                    "Host": [
                        "$vm_name"
                    ]
                },
                "path": "$ws_path",
                "type": "ws"
            },
            "type": "vmess",
            "security": "auto",
            "uuid": "$uuid"
        },

    {
        "type": "hysteria2",
        "tag": "${node_prefix_label}hy2${node_suffix_label}",
        "server": "$cl_hy2_ip",
        "server_port": $hy2_port,
$(sbhy2ports)
        "password": "$uuid",
        "tls": {
            "enabled": true,
            "server_name": "$hy2_name",
            "insecure": $hy2_ins,
            "alpn": [
                "h3"
            ]
        }
    },
        {
            "type":"tuic",
            "tag": "${node_prefix_label}tuic5${node_suffix_label}",
            "server": "$cl_tu5_ip",
            "server_port": $tu5_port,
            "uuid": "$uuid",
            "password": "$uuid",
            "congestion_control": "bbr",
            "udp_relay_mode": "native",
            "udp_over_stream": false,
            "zero_rtt_handshake": false,
            "heartbeat": "10s",
            "tls":{
                "enabled": true,
                "server_name": "$tu5_name",
                "insecure": $tu5_ins,
                "alpn": [
                    "h3"
                ]
            }
        },
EOF
}

clall(){
cat <<EOF
port: 7890
allow-lan: true
mode: rule
log-level: info
unified-delay: true
dns:
  enable: true 
  listen: "0.0.0.0:1053"
  ipv6: true
  prefer-h3: false
  respect-rules: true
  use-system-hosts: false
  cache-algorithm: "arc"
  enhanced-mode: "fake-ip"
  fake-ip-range: "198.18.0.1/16"
  fake-ip-filter:
    - "+.lan"
    - "+.local"
    - "+.msftconnecttest.com"
    - "+.msftncsi.com"
    - "localhost.ptlogin2.qq.com"
    - "localhost.sec.qq.com"
    - "+.in-addr.arpa"
    - "+.ip6.arpa"
    - "time.*.com"
    - "time.*.gov"
    - "pool.ntp.org"
    - "localhost.work.weixin.qq.com"
  default-nameserver: ["223.5.5.5", "119.29.29.29"]
  nameserver:
    - "https://1.1.1.1/dns-query"
    - "https://8.8.8.8/dns-query"
  proxy-server-nameserver:
    - "https://223.5.5.5/dns-query"
    - "https://doh.pub/dns-query"

proxies:
- name: "${node_prefix_label}vless-reality-vision${node_suffix_label}"
  type: vless
  server: $server_ipcl                           
  port: $vl_port                                
  uuid: $uuid   
  network: tcp
  udp: true
  tls: true
  flow: xtls-rprx-vision
  servername: $vl_name                 
  reality-opts: 
    public-key: $public_key    
    short-id: $short_id                      
  client-fingerprint: chrome                  

- name: "${node_prefix_label}vmess-ws${node_suffix_label}"
  type: vmess
  server: $vmadd_local                        
  port: $vm_port                                     
  uuid: $uuid       
  alterId: 0
  cipher: auto
  udp: true
  tls: $tls
  network: ws
  servername: $vm_name                    
  ws-opts:
    path: "$ws_path"                             
    headers:
      Host: $vm_name                     

- name: "${node_prefix_label}hysteria2${node_suffix_label}"
  type: hysteria2                                      
  server: $cl_hy2_ip                               
  port: $hy2_port
  ports: $cmhy2pt
  password: $uuid                          
  alpn:
    - h3
  sni: $hy2_name                               
  skip-cert-verify: $hy2_ins
  fast-open: true

- name: "${node_prefix_label}tuic5${node_suffix_label}"
  server: $cl_tu5_ip                      
  port: $tu5_port                                    
  type: tuic
  uuid: $uuid       
  password: $uuid   
  alpn: [h3]
  disable-sni: $tu5_ins
  reduce-rtt: true
  udp-relay-mode: native
  congestion-controller: bbr
  sni: $tu5_name                                
  skip-cert-verify: $tu5_ins
EOF
}

# A single ordered model drives both clients and every group reference.
# Fixed precedes temporary, and TLS precedes plaintext, matching existing exports.
local -a argo_labels=() argo_hosts=() argo_tls=() argo_ports=()
local processes has_fixed=0 has_temporary=0 kind host label i
processes=$(ps -ef 2>/dev/null)
tls=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.enabled')
if [[ $tls == false ]]; then
if printf '%s\n' "$processes" | grep -v '[x]http-argo/cloudflared' | grep -q '[c]loudflared.*run'; then has_fixed=1; fi
if printf '%s\n' "$processes" | grep "[l]ocalhost:$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port')" >/dev/null 2>&1; then has_temporary=1; fi
fi
for kind in fixed temporary; do
if [[ $kind == fixed ]]; then
[[ $has_fixed == 1 ]] || continue
host=$argogd; label=固定
else
[[ $has_temporary == 1 ]] || continue
host=$argo; label=临时
fi
argo_labels+=("vmess-tls-argo$label" "vmess-argo$label")
argo_hosts+=("$host" "$host")
argo_tls+=(true false)
argo_ports+=(443 8880)
done

sb_argo_nodes(){
local i
for i in "${!argo_labels[@]}"; do
cat <<EOF
        {
            "server": "$vmadd_argo",
            "server_port": ${argo_ports[i]},
            "tag": "${node_prefix_label}${argo_labels[i]}${node_suffix_label}",
            "tls": {
                "enabled": ${argo_tls[i]},
                "server_name": "${argo_hosts[i]}",
                "insecure": false,
                "utls": {"enabled": true, "fingerprint": "chrome"}
            },
            "transport": {
                "headers": {"Host": ["${argo_hosts[i]}"]},
                "path": "$ws_path",
                "type": "ws"
            },
            "type": "vmess",
            "security": "auto",
            "uuid": "$uuid"
        },
EOF
done
}

cl_argo_nodes(){
local i
for i in "${!argo_labels[@]}"; do
cat <<EOF
- name: "${node_prefix_label}${argo_labels[i]}${node_suffix_label}"
  type: vmess
  server: $vmadd_argo
  port: ${argo_ports[i]}
  uuid: $uuid
  alterId: 0
  cipher: auto
  udp: true
  tls: ${argo_tls[i]}
  network: ws
  servername: ${argo_hosts[i]}
  ws-opts:
    path: "$ws_path"
    headers:
      Host: ${argo_hosts[i]}
EOF
done
}

sb_node_refs(){
local label separator=
if [[ ${1:-} == selector ]]; then printf '"auto"'; separator=,; fi
local -a labels=(vless vmess hy2 tuic5)
if [[ $sbnh != 1.10 ]]; then
# Historical no-Argo selector puts AnyTLS immediately after VLESS.
if (( ${#argo_labels[@]} == 0 )); then labels=(vless anytls vmess hy2 tuic5)
else labels+=(anytls); fi
fi
labels+=("${argo_labels[@]}")
for label in "${labels[@]}"; do
printf '%s"%s%s%s"' "$separator" "$node_prefix_label" "$label" "$node_suffix_label"
separator=,
done
}

cl_node_refs(){
local label
local -a labels=(vless-reality-vision vmess-ws hysteria2 tuic5)
[[ $sbnh == 1.10 ]] || labels+=(anytls)
for label in "${labels[@]}"; do
printf '    - "%s%s%s"\n' "$node_prefix_label" "$label" "$node_suffix_label"
done
# XHTTP is Mihomo-only; its ordering in groups differs from its node placement.
[[ -z $xhttp_argo_cl_name ]] || printf '    - %s\n' "$xhttp_argo_cl_name"
[[ -z $xhttp_cl_name ]] || printf '    - %s\n' "$xhttp_cl_name"
for label in "${argo_labels[@]}"; do
printf '    - "%s%s%s"\n' "$node_prefix_label" "$label" "$node_suffix_label"
done
}

cat > "$client_raw" <<EOF || exit 1
$(sball)
$(sbany2)
$(sb_argo_nodes)
        {
            "tag": "proxy",
            "type": "selector",
            "default": "auto",
            "outbounds": [$(sb_node_refs selector)]
        },
        {
            "tag": "auto",
            "type": "urltest",
            "outbounds": [$(sb_node_refs)],
            "url": "http://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 30,
            "idle_timeout": "30m"
        },
        {"type": "direct", "tag": "direct"}
    ]
}
EOF

cat > "$client_stage/clmi.yaml" <<EOF || exit 1
$(clall)$(clxhttp2)

$(clany2)

$(cl_argo_nodes)
proxy-groups:
- name: 负载均衡
  type: load-balance
  url: https://www.gstatic.com/generate_204
  interval: 300
  strategy: round-robin
  proxies:
$(cl_node_refs)

- name: 自动选择
  type: url-test
  url: https://www.gstatic.com/generate_204
  interval: 300
  tolerance: 50
  proxies:
$(cl_node_refs)

- name: 🌍选择代理节点
  type: select
  proxies:
    - 负载均衡
    - 自动选择
    - DIRECT
$(cl_node_refs)
rules:
  - GEOIP,LAN,DIRECT
  - GEOSITE,CN,DIRECT
  - GEOIP,CN,DIRECT
  - MATCH,🌍选择代理节点
EOF
sb_client_profile "$client_raw" "$client_stage/sbox.json" || exit 1
[[ -s $client_stage/clmi.yaml ]] || exit 1
if [[ -n ${SB_EXPORT_DIR:-} ]]; then
mv -f "$client_stage/sbox.json" "$SB_EXPORT_DIR/sbox.json" && mv -f "$client_stage/clmi.yaml" "$SB_EXPORT_DIR/clmi.yaml" || exit 1
else
sb_exports_commit "$client_stage" sbox.json clmi.yaml || exit 1
fi
)
}

cfargo_ym(){
tls=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.enabled')
if [[ "$tls" = "false" ]]; then
echo
yellow "1：添加或者删除Argo临时隧道"
yellow "2：添加或者删除Argo固定隧道"
yellow "0：返回上层"
readp "请选择【0-2】：" menu
if [ "$menu" = "1" ]; then
cfargo
elif [ "$menu" = "2" ]; then
cfargoym
else
changeserv
fi
else
yellow "因vmess开启了tls，Argo隧道功能不可用" && sleep 2
fi
}

# Only remove resources this script owns; old installations are recognized by
# their complete command/rule signature, never by generic keywords.
sb_cron_update(){
local kind=$1 entry=${2-}
case "$kind" in restart|argo|subscription|warp|all) ;; *) return 1 ;; esac
(
umask 077
local raw filtered errors status
raw=$(mktemp /tmp/sbox-cron.raw.XXXXXX) || exit 1
filtered=$(mktemp /tmp/sbox-cron.new.XXXXXX) || { rm -f "$raw"; exit 1; }
errors=$(mktemp /tmp/sbox-cron.err.XXXXXX) || { rm -f "$raw" "$filtered"; exit 1; }
trap 'rm -f "$raw" "$filtered" "$errors"' EXIT
crontab -l > "$raw" 2> "$errors"; status=$?
if [[ $status != 0 ]]; then
# Both Vixie cron and BusyBox return nonzero for an absent user crontab.
if [[ $status == 1 && ! -s $raw ]] && grep -Eqi 'no crontab for|can.t open .*No such file or directory' "$errors"; then : > "$raw"
else cat "$errors" >&2; exit 1
fi
fi
awk -v kind="$kind" '
function path_token(text) { pos=index($0,text); return pos && substr($0,pos+length(text),1) ~ /[ \t]/ }
function owned(k) {
 if ($0 ~ "# sing-box-yg:" k "[ \t]*$") return 1
 if (k=="restart") return $0 ~ /^[ \t]*0[ \t]+1[ \t]+\*[ \t]+\*[ \t]+\*[ \t]+systemctl restart sing-box;rc-service sing-box restart[ \t]*$/
 if ($0 !~ /^[ \t]*@reboot[ \t]/) return 0
 if (k=="argo") return index($0,"nohup /etc/s-box/cloudflared tunnel --url http://localhost:") && index($0,"> /etc/s-box/argo.log")
 if (k=="subscription") return index($0,"busybox httpd -f -p $(cat /etc/s-box/subport.log 2>/dev/null)") && path_token("-h /root/websbox")
 if (k=="warp") return index($0,"nohup $(cat /etc/s-box/sbwpph.log 2>/dev/null)")
 return 0
}
{ if (kind=="all") { if (!owned("restart") && !owned("argo") && !owned("subscription") && !owned("warp")) print }
  else if (!owned(kind)) print }
' "$raw" > "$filtered" || exit 1
[[ -z $entry ]] || printf '%s # sing-box-yg:%s\n' "$entry" "$kind" >> "$filtered" || exit 1
cmp -s "$raw" "$filtered" || crontab "$filtered" || exit 1
)
}

argo_fixed_backend(){
if pidof systemd >/dev/null 2>&1; then printf '%s\n' systemd
elif command -v rc-service >/dev/null 2>&1; then printf '%s\n' openrc
else red "未找到受支持的服务管理器。" >&2; return 1
fi
}

argo_fixed_apply(){
local token=$1 domain=$2 backend unit backup file active=0 enabled=0
[[ -n $token && $token =~ ^[A-Za-z0-9+/=_-]+$ && -n $domain && $domain != *$'\n'* && $domain != *$'\r'* ]] || { red "Token或域名为空/格式无效。"; return 1; }
backend=$(argo_fixed_backend) || return 1
if [[ $backend == systemd ]]; then
unit=/etc/systemd/system/argo.service
systemctl is-active --quiet argo && active=1
systemctl is-enabled --quiet argo && enabled=1
else
unit=/etc/init.d/argo
rc-service argo status >/dev/null 2>&1 && active=1
rc-update show default 2>/dev/null | grep -Eq '(^|[[:space:]])argo([[:space:]]|$)' && enabled=1
fi
backup=$(umask 077; mktemp -d /etc/s-box/argo-fixed.bak.XXXXXX) || return 1
for file in "$unit" /etc/s-box/sbargotoken.log /etc/s-box/sbargoym.log; do
[[ ! -f $file ]] || cp -p "$file" "$backup/$(basename "$file")" || return 1
done
if ! (
umask 077
local done=0
trap 'if [[ $done == 0 ]]; then
 for file in "$unit" /etc/s-box/sbargotoken.log /etc/s-box/sbargoym.log; do
  if [[ -f $backup/$(basename "$file") ]]; then cp -p "$backup/$(basename "$file")" "$file"; else rm -f "$file"; fi
 done
 if [[ $backend == systemd ]]; then
  systemctl daemon-reload
  if [[ $active == 1 ]]; then systemctl restart argo; else systemctl stop argo; fi
  [[ $enabled == 1 ]] || systemctl disable argo
 else
  if [[ $active == 1 ]]; then rc-service argo restart; else rc-service argo stop; fi
  [[ $enabled == 1 ]] || rc-update del argo default
 fi
fi' EXIT
if [[ $backend == systemd ]]; then
cat > "$unit" <<EOF || exit 1
[Unit]
Description=sing-box-yg fixed Argo tunnel
After=network.target
[Service]
Type=simple
NoNewPrivileges=yes
TimeoutStartSec=0
ExecStart=/etc/s-box/cloudflared tunnel --no-autoupdate --edge-ip-version auto --protocol http2 run --token "${token}"
Restart=on-failure
RestartSec=5s
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl restart argo && systemctl is-active --quiet argo && systemctl enable argo || exit 1
else
cat > "$unit" <<EOF || exit 1
#!/sbin/openrc-run
description="sing-box-yg fixed Argo tunnel"
command="/etc/s-box/cloudflared"
command_args="tunnel --no-autoupdate --edge-ip-version auto --protocol http2 run --token ${token}"
pidfile="/run/argo.pid"
command_background="yes"
depend() { need net; }
EOF
chmod 755 "$unit" && rc-service argo restart && rc-service argo status && rc-update add argo default || exit 1
fi
printf '%s\n' "$domain" > /etc/s-box/sbargoym.log && printf '%s\n' "$token" > /etc/s-box/sbargotoken.log || exit 1
chmod 600 /etc/s-box/sbargoym.log /etc/s-box/sbargotoken.log || exit 1
done=1
); then red "固定Argo配置失败，已尝试恢复原配置。备份：$backup"; return 1; fi
}

argo_fixed_stop(){
local backend unit
backend=$(argo_fixed_backend) || return 1
if [[ $backend == systemd ]]; then
unit=/etc/systemd/system/argo.service
if [[ -e $unit ]]; then systemctl stop argo && systemctl disable argo || return 1; fi
rm -f "$unit" || return 1
systemctl daemon-reload || return 1
else
unit=/etc/init.d/argo
if [[ -e $unit ]]; then rc-service argo stop && rc-update del argo default || return 1; fi
rm -f "$unit" || return 1
fi
# Temporary and fixed VMess tunnels share this executable. Keep it until uninstall.
rm -f /etc/s-box/vm_ws_argogd.txt
}

argo_temporary_stop(){
local pid processes result=0
processes=$(ps -eo pid=,args=) || return 1
# Match the executable and --url argument, not every process mentioning localhost.
# Stop old temporary instances even if the VMess port has since been changed.
while IFS= read -r pid; do
[[ $pid =~ ^[0-9]+$ ]] || continue
kill -TERM "$pid" 2>/dev/null || { kill -0 "$pid" 2>/dev/null && result=1; }
done < <(awk '$1 ~ /^[0-9]+$/ && $2=="/etc/s-box/cloudflared" && $3=="tunnel" { for (i=4;i<NF;i++) if ($i=="--url" && $(i+1) ~ /^http:\/\/localhost:[0-9]+$/) { print $1; break } }' <<< "$processes")
return "$result"
}

# Parse only the exact UDP DNAT form emitted by our old/new port-hop generator.
# No eval: unknown matches/comments/options are deliberately left alone.
sb_port_hop_rule_match(){
local -a args=("$@")
local i=2 proto= jump= comment= source= target= udp_module= comment_module=
[[ ${args[0]-} == -A && ${args[1]-} == PREROUTING ]] || return 1
while (( i < ${#args[@]} )); do
case ${args[i]} in
-p) [[ -z $proto && ${args[i+1]-} == udp ]] || return 1; proto=udp; ((i+=2)) ;;
-m)
case ${args[i+1]-} in
udp) [[ -z $udp_module ]] || return 1; udp_module=1; ((i+=2)) ;;
comment) [[ -z $comment_module ]] || return 1; comment_module=1; ((i+=2)) ;;
*) return 1 ;;
esac ;;
--dport) [[ -z $source && ${args[i+1]-} =~ ^[0-9]+(:[0-9]+)?$ ]] || return 1; source=${args[i+1]}; ((i+=2)) ;;
--comment)
[[ -z $comment && ${args[i+1]-} =~ ^\"?sing-box-yg:port-hop\"?$ ]] || return 1
comment=1; ((i+=2)) ;;
-j) [[ -z $jump && ${args[i+1]-} == DNAT ]] || return 1; jump=DNAT; ((i+=2)) ;;
--to-destination) [[ -z $target && ${args[i+1]-} =~ ^:[0-9]+$ ]] || return 1; target=${args[i+1]#:}; ((i+=2)) ;;
*) return 1 ;;
esac
done
[[ $proto == udp && $jump == DNAT && -n $source && -n $target && $comment_module == "$comment" ]] || return 1
sb_hop_source=$source; sb_hop_target=$target; sb_hop_marked=$comment
}

sb_port_hop_manage(){
local action=$1; shift
local -a targets=("$@") binaries=(iptables ip6tables) spec
local binary rules rule target matched i result=0 all=0 sb_hop_source sb_hop_target sb_hop_marked ports
case "$action" in list) binaries=(iptables) ;; remove) ;; *) return 1 ;; esac
if [[ ${#targets[@]} == 0 ]]; then
all=1
if [[ -f /etc/s-box/sb.json ]]; then
ports=$(jq -r '[.inbounds[] | select(.type=="hysteria2" or .type=="tuic") | .listen_port | select(type=="number" and .>=1 and .<=65535)] | .[]' /etc/s-box/sb.json) || return 1
while IFS= read -r target; do [[ -z $target ]] || targets+=("$target"); done <<< "$ports"
fi
fi
for binary in "${binaries[@]}"; do
command -v "$binary" >/dev/null 2>&1 || continue
rules=$("$binary" -t nat -S PREROUTING) || return 1
while IFS= read -r rule; do
read -r -a spec <<< "$rule"
sb_port_hop_rule_match "${spec[@]}" || continue
matched=0
if [[ $all == 1 && -n $sb_hop_marked ]]; then matched=1
else for target in "${targets[@]}"; do [[ $target != "$sb_hop_target" ]] || matched=1; done
fi
[[ $matched == 1 ]] || continue
if [[ $action == list ]]; then printf '%s\n' "$sb_hop_source"
else
spec[0]=-D
# iptables -S may quote comment strings; our marker contains no whitespace.
for ((i=0;i<${#spec[@]};i++)); do [[ ${spec[i]} != '"sing-box-yg:port-hop"' ]] || spec[i]=sing-box-yg:port-hop; done
"$binary" -t nat "${spec[@]}" || result=1
fi
done <<< "$rules"
done
return "$result"
}

cloudflaredargo(){
if [[ ! -x /etc/s-box/cloudflared ]]; then
local cpu stage
case $(uname -m) in aarch64) cpu=arm64 ;; x86_64) cpu=amd64 ;; armv7l) cpu=arm ;; *) red "不支持的Argo架构。"; return 1 ;; esac
stage=$(mktemp /etc/s-box/.cloudflared.XXXXXX) || return 1
if ! curl -fL --retry 2 --connect-timeout 15 --max-time 300 "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$cpu" -o "$stage" || ! chmod 755 "$stage" || ! "$stage" version >/dev/null 2>&1; then
rm -f "$stage"; red "Argo下载/校验失败，未覆盖原文件。"; return 1
fi
mv -f "$stage" /etc/s-box/cloudflared || { rm -f "$stage"; return 1; }
fi
green "Argo版本：V$(/etc/s-box/cloudflared version 2>/dev/null | awk '{print $3}')"
}

cfargoym(){
echo
if [[ -f /etc/s-box/sbargoym.log ]]; then green "当前Argo固定隧道域名：$(cat /etc/s-box/sbargoym.log 2>/dev/null)"; fi
echo
green "请进入Cloudflare官网 --- Zero Trust --- 网络 --- 连接器，创建固定隧道"
yellow "1：重置/设置Argo固定隧道域名"
yellow "2：停止Argo固定隧道"
yellow "0：返回上层"
readp "请选择【0-2】：" menu
if [[ $menu == 1 ]]; then
cloudflaredargo || return 1
local argotoken argoym vm_port
readp "输入Argo固定隧道Token: " argotoken
readp "输入Argo固定隧道域名: " argoym
vm_port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port') || return 1
yellow "注意！Zero Trust设置固定隧道URL端口填写Vmess端口：localhost:$vm_port"
argo_fixed_apply "$argotoken" "$argoym" || return 1
unset argotoken
sbshare > /dev/null 2>&1 || { red "固定隧道已更新，但订阅刷新失败，请通过菜单9重试。"; return 1; }
blue "Argo固定隧道设置完成，固定域名：$argoym"
elif [[ $menu == 2 ]]; then
argo_fixed_stop || { red "停止固定隧道失败，未删除共享程序。"; return 1; }
sbshare > /dev/null 2>&1 || return 1
green "Argo固定隧道已停止"
else cfargo_ym
fi
}

cfargo(){
echo
yellow "1：重置Argo临时隧道域名"
yellow "2：停止Argo临时隧道"
yellow "0：返回上层"
readp "请选择【0-2】：" menu
if [ "$menu" = "1" ]; then
green "请稍等……"
cloudflaredargo || return 1
argo_temporary_stop || { red "停止旧临时隧道失败。"; return 1; }
nohup /etc/s-box/cloudflared tunnel --url http://localhost:$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port') --edge-ip-version auto --no-autoupdate --protocol http2 > /etc/s-box/argo.log 2>&1 &
sleep 20
if [[ -n $(curl -sL https://$(cat /etc/s-box/argo.log 2>/dev/null | grep -a trycloudflare.com | awk 'NR==2{print}' | awk -F// '{print $2}' | awk '{print $1}')/ -I | awk 'NR==1 && /404|400|503/') ]]; then
argo=$(cat /etc/s-box/argo.log 2>/dev/null | grep -a trycloudflare.com | awk 'NR==2{print}' | awk -F// '{print $2}' | awk '{print $1}')
sbshare > /dev/null 2>&1
blue "Argo临时隧道申请成功，域名验证有效：$argo" && sleep 2
if command -v apk >/dev/null 2>&1; then
cat > /etc/local.d/alpineargo.start <<'EOF'
#!/bin/bash
sleep 10
nohup /etc/s-box/cloudflared tunnel --url http://localhost:$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port') --edge-ip-version auto --no-autoupdate --protocol http2 > /etc/s-box/argo.log 2>&1 &
sleep 10
printf "9\n1\n" | bash /usr/bin/sb > /dev/null 2>&1
EOF
chmod +x /etc/local.d/alpineargo.start
rc-update add local default >/dev/null 2>&1
else
sb_cron_update argo '@reboot sleep 10 && /bin/bash -c "nohup /etc/s-box/cloudflared tunnel --url http://localhost:$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port') --edge-ip-version auto --no-autoupdate --protocol http2 > /etc/s-box/argo.log 2>&1 & sleep 10 && printf \"9\n1\n\" | bash /usr/bin/sb > /dev/null 2>&1"' || { red "更新临时隧道开机任务失败。"; return 1; }
fi
else
yellow "Argo临时域名验证暂不可用，请稍后再试"
fi
elif [ "$menu" = "2" ]; then
sb_cron_update argo || { red "清理临时隧道任务失败。"; return 1; }
argo_temporary_stop || { red "停止临时隧道失败，保留程序。"; return 1; }
rm -f /etc/s-box/vm_ws_argols.txt
rm -rf /etc/local.d/alpineargo.start
sbshare > /dev/null 2>&1 || return 1
green "Argo临时隧道已停止"
else
cfargo_ym
fi
}

instsllsingbox(){
if [[ -f '/etc/systemd/system/sing-box.service' ]]; then
red "已安装Sing-box服务，无法再次安装" && exit
fi
mkdir -p /etc/s-box
v6
openyn
inssb || return 1
inscertificate
insport
sleep 2
echo
blue "Vless-reality相关key与id将自动生成……"
key_pair=$(/etc/s-box/sing-box generate reality-keypair)
private_key=$(echo "$key_pair" | awk '/PrivateKey/ {print $2}' | tr -d '"')
public_key=$(echo "$key_pair" | awk '/PublicKey/ {print $2}' | tr -d '"')
echo "$public_key" > /etc/s-box/public.key
short_id=$(/etc/s-box/sing-box generate rand --hex 4)
wget -q -O /root/geoip.db https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.db
wget -q -O /root/geosite.db https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.db
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
green "五、自动生成warp-wireguard出站账户" && sleep 2
warpwg
inssbjsonser || return 1
sbservice || return 1
sbactive
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
lnsb || return 1
blue "Sing-box-yg脚本安装成功，脚本快捷方式：sb"
cronsb || return 1
echo
wgcfgo
sbshare
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
blue "可选择9，刷新并显示所有协议配置及分享链接"
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
}

changeym(){
[ -f /root/ygkkkca/ca.log ] && ymzs="$yellow切换为域名证书：$(cat /root/ygkkkca/ca.log 2>/dev/null)$plain" || ymzs="$yellow未申请域名证书，无法切换$plain"
vl_na="正在使用的域名：$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].tls.server_name')。$yellow更换符合reality要求的域名，不支持证书域名$plain"
tls=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.enabled')
[[ "$tls" = "false" ]] && vm_na="当前已关闭TLS。$ymzs ${yellow}将开启TLS，Argo隧道将不支持开启${plain}" || vm_na="正在使用的域名证书：$(cat /root/ygkkkca/ca.log 2>/dev/null)。$yellow切换为关闭TLS，Argo隧道将可用$plain"
hy2_sniname=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[2].tls.key_path')
[[ "$hy2_sniname" = '/etc/s-box/private.key' ]] && hy2_na="正在使用自签bing证书。$ymzs" || hy2_na="正在使用的域名证书：$(cat /root/ygkkkca/ca.log 2>/dev/null)。$yellow切换为自签bing证书$plain"
tu5_sniname=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[3].tls.key_path')
[[ "$tu5_sniname" = '/etc/s-box/private.key' ]] && tu5_na="正在使用自签bing证书。$ymzs" || tu5_na="正在使用的域名证书：$(cat /root/ygkkkca/ca.log 2>/dev/null)。$yellow切换为自签bing证书$plain"
an_sniname=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[4].tls.key_path')
[[ "$an_sniname" = '/etc/s-box/private.key' ]] && an_na="正在使用自签bing证书。$ymzs" || an_na="正在使用的域名证书：$(cat /root/ygkkkca/ca.log 2>/dev/null)。$yellow切换为自签bing证书$plain"
echo
green "请选择要切换证书模式的协议"
green "1：vless-reality协议，$vl_na"
if [[ -f /root/ygkkkca/ca.log ]]; then
green "2：vmess-ws协议，$vm_na"
green "3：Hysteria2协议，$hy2_na"
green "4：Tuic5协议，$tu5_na"
if [[ "$sbnh" != "1.10" ]]; then
green "5：Anytls协议，$an_na"
fi
else
red "仅支持选项1 (vless-reality)。因未申请域名证书，vmess-ws、Hysteria-2、Tuic-v5、Anytls的证书切换选项暂不予显示"
fi
green "0：返回上层"
readp "请选择：" menu
if [ "$menu" = "1" ]; then
readp "请输入vless-reality域名 (回车使用apple.com)：" menu
ym_vl_re=${menu:-apple.com}
a=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].tls.server_name')
b=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].tls.reality.handshake.server')
c=$(cat /etc/s-box/vl_reality.txt | cut -d'=' -f5 | cut -d'&' -f1)
echo $sbfiles | xargs -n1 sed -i "23s/$a/$ym_vl_re/"
echo $sbfiles | xargs -n1 sed -i "27s/$b/$ym_vl_re/"
restartsb && sbshare > /dev/null 2>&1
blue "Vless-reality域名证书更换完毕"
elif [ "$menu" = "2" ]; then
if [ -f /root/ygkkkca/ca.log ]; then
a=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.enabled')
[ "$a" = "true" ] && a_a=false || a_a=true
b=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.server_name')
[ "$b" = "www.bing.com" ] && b_b=$(cat /root/ygkkkca/ca.log) || b_b=$(cat /root/ygkkkca/ca.log)
c=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.certificate_path')
d=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.key_path')
if [ "$d" = '/etc/s-box/private.key' ]; then
c_c='/root/ygkkkca/cert.crt'
d_d='/root/ygkkkca/private.key'
else
c_c='/etc/s-box/cert.pem'
d_d='/etc/s-box/private.key'
fi
echo $sbfiles | xargs -n1 sed -i "55s#$a#$a_a#"
echo $sbfiles | xargs -n1 sed -i "56s#$b#$b_b#"
echo $sbfiles | xargs -n1 sed -i "57s#$c#$c_c#"
echo $sbfiles | xargs -n1 sed -i "58s#$d#$d_d#"
restartsb && sbshare > /dev/null 2>&1
blue "vmess-ws协议域名证书更换完毕"
echo
tls=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.enabled')
vm_port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port')
blue "当前Vmess-ws(tls)的端口：$vm_port"
[[ "$tls" = "false" ]] && blue "切记：可进入主菜单选项4-2，将Vmess-ws端口更改为任意7个80系端口(80、8080、8880、2052、2082、2086、2095)，可实现CDN优选IP" || blue "切记：可进入主菜单选项4-2，将Vmess-ws-tls端口更改为任意6个443系的端口(443、8443、2053、2083、2087、2096)，可实现CDN优选IP"
echo
else
red "当前未申请域名证书，不可切换。主菜单选择12，执行Acme证书申请" && sleep 2 && sb
fi
elif [ "$menu" = "3" ]; then
if [ -f /root/ygkkkca/ca.log ]; then
c=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[2].tls.certificate_path')
d=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[2].tls.key_path')
if [ "$d" = '/etc/s-box/private.key' ]; then
c_c='/root/ygkkkca/cert.crt'
d_d='/root/ygkkkca/private.key'
else
c_c='/etc/s-box/cert.pem'
d_d='/etc/s-box/private.key'
fi
echo $sbfiles | xargs -n1 sed -i "79s#$c#$c_c#"
echo $sbfiles | xargs -n1 sed -i "80s#$d#$d_d#"
restartsb && sbshare > /dev/null 2>&1
blue "Hysteria2协议域名证书更换完毕"
else
red "当前未申请域名证书，不可切换。主菜单选择12，执行Acme证书申请" && sleep 2 && sb
fi
elif [ "$menu" = "4" ]; then
if [ -f /root/ygkkkca/ca.log ]; then
c=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[3].tls.certificate_path')
d=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[3].tls.key_path')
if [ "$d" = '/etc/s-box/private.key' ]; then
c_c='/root/ygkkkca/cert.crt'
d_d='/root/ygkkkca/private.key'
else
c_c='/etc/s-box/cert.pem'
d_d='/etc/s-box/private.key'
fi
echo $sbfiles | xargs -n1 sed -i "102s#$c#$c_c#"
echo $sbfiles | xargs -n1 sed -i "103s#$d#$d_d#"
restartsb && sbshare > /dev/null 2>&1
blue "Tuic5协议域名证书更换完毕"
else
red "当前未申请域名证书，不可切换。主菜单选择12，执行Acme证书申请" && sleep 2 && sb
fi
elif [ "$menu" = "5" ]; then
if [ -f /root/ygkkkca/ca.log ]; then
c=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[4].tls.certificate_path')
d=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[4].tls.key_path')
if [ "$d" = '/etc/s-box/private.key' ]; then
c_c='/root/ygkkkca/cert.crt'
d_d='/root/ygkkkca/private.key'
else
c_c='/etc/s-box/cert.pem'
d_d='/etc/s-box/private.key'
fi
echo $sbfiles | xargs -n1 sed -i "119s#$c#$c_c#"
echo $sbfiles | xargs -n1 sed -i "120s#$d#$d_d#"
restartsb && sbshare > /dev/null 2>&1
blue "Anytls协议域名证书更换完毕"
else
red "当前未申请域名证书，不可切换。主菜单选择12，执行Acme证书申请" && sleep 2 && sb
fi
else
sb
fi
}

allports(){
vl_port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].listen_port')
vm_port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port')
hy2_port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[2].listen_port')
tu5_port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[3].listen_port')
an_port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[4].listen_port')
hy2_ports=$(sb_port_hop_manage list "$hy2_port" | paste -sd, -)
tu5_ports=$(sb_port_hop_manage list "$tu5_port" | paste -sd, -)
[[ -n $hy2_ports ]] && hy2zfport="$hy2_ports" || hy2zfport="未添加"
[[ -n $tu5_ports ]] && tu5zfport="$tu5_ports" || tu5zfport="未添加"
}

changeport(){
sbactive
allports
fports(){
readp "\n请输入转发的端口范围 (1000-65535范围内，格式为 小数字:大数字)：" rangeport
if [[ $rangeport =~ ^([1-9][0-9]{3,4}:[1-9][0-9]{3,4})$ ]]; then
b=${rangeport%%:*}
c=${rangeport##*:}
if [[ $b -ge 1000 && $b -le 65535 && $c -ge 1000 && $c -le 65535 && $b -lt $c ]]; then
iptables -t nat -A PREROUTING -p udp --dport $rangeport -m comment --comment sing-box-yg:port-hop -j DNAT --to-destination :$port
ip6tables -t nat -A PREROUTING -p udp --dport $rangeport -m comment --comment sing-box-yg:port-hop -j DNAT --to-destination :$port
netfilter-persistent save >/dev/null 2>&1
service iptables save >/dev/null 2>&1
blue "已确认转发的端口范围：$rangeport"
else
red "输入的端口范围不在有效范围内" && fports
fi
else
red "输入格式不正确。格式为 小数字:大数字" && fports
fi
echo
}
fport(){
readp "\n请输入一个转发的端口 (1000-65535范围内)：" onlyport
if [[ $onlyport -ge 1000 && $onlyport -le 65535 ]]; then
iptables -t nat -A PREROUTING -p udp --dport $onlyport -m comment --comment sing-box-yg:port-hop -j DNAT --to-destination :$port
ip6tables -t nat -A PREROUTING -p udp --dport $onlyport -m comment --comment sing-box-yg:port-hop -j DNAT --to-destination :$port
netfilter-persistent save >/dev/null 2>&1
service iptables save >/dev/null 2>&1
blue "已确认转发的端口：$onlyport"
else
blue "输入的端口不在有效范围内" && fport
fi
echo
}

hy2deports(){
allports
sb_port_hop_manage remove "$hy2_port" || return 1
netfilter-persistent save >/dev/null 2>&1
service iptables save >/dev/null 2>&1
}
tu5deports(){
allports
sb_port_hop_manage remove "$tu5_port" || return 1
netfilter-persistent save >/dev/null 2>&1
service iptables save >/dev/null 2>&1
}

allports
green "Vless-reality、Vmess-ws、Anytls仅能更改唯一的端口，vmess-ws注意Argo端口重置"
green "Hysteria2与Tuic5支持更改主端口，也支持增删多个转发端口"
green "Hysteria2支持端口跳跃，且与Tuic5都支持多端口复用"
echo
green "1：Vless-reality协议 ${yellow}端口:$vl_port${plain}"
green "2：Vmess-ws协议 ${yellow}端口:$vm_port${plain}"
green "3：Hysteria2协议 ${yellow}端口:$hy2_port  转发多端口: $hy2zfport${plain}"
green "4：Tuic5协议 ${yellow}端口:$tu5_port  转发多端口: $tu5zfport${plain}"
if [[ "$sbnh" != "1.10" ]]; then
green "5：Anytls协议 ${yellow}端口:$an_port${plain}"
fi
green "0：返回上层"
readp "请选择要变更端口的协议：" menu
if [ "$menu" = "1" ]; then
vlport
echo $sbfiles | xargs -n1 sed -i "14s/$vl_port/$port_vl_re/"
restartsb && sbshare > /dev/null 2>&1
blue "Vless-reality端口更改完成"
echo
elif [ "$menu" = "5" ]; then
anport
echo $sbfiles | xargs -n1 sed -i "110s/$an_port/$port_an/"
restartsb && sbshare > /dev/null 2>&1
blue "Anytls端口更改完成"
echo
elif [ "$menu" = "2" ]; then
vmport
echo $sbfiles | xargs -n1 sed -i "41s/$vm_port/$port_vm_ws/"
restartsb && sbshare > /dev/null 2>&1
blue "Vmess-ws端口更改完成"
tls=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.enabled')
if [[ "$tls" = "false" ]]; then
blue "切记：如果Argo使用中，临时隧道必须重置，固定隧道的CF设置界面端口必须修改为$port_vm_ws"
else
blue "因TLS已开启，当前Argo隧道已不支持开启"
fi
echo
elif [ "$menu" = "3" ]; then
green "1：更换Hysteria2主端口 (原多端口自动重置删除)"
green "2：添加Hysteria2多端口"
green "3：重置删除Hysteria2多端口"
green "0：返回上层"
readp "请选择【0-3】：" menu
if [ "$menu" = "1" ]; then
if [ -n "$hy2_ports" ]; then
hy2deports
hy2port
echo $sbfiles | xargs -n1 sed -i "67s/$hy2_port/$port_hy2/"
restartsb && sbshare > /dev/null 2>&1
else
hy2port
echo $sbfiles | xargs -n1 sed -i "67s/$hy2_port/$port_hy2/"
restartsb && sbshare > /dev/null 2>&1
fi
blue "Hysteria2端口更改完成"
elif [ "$menu" = "2" ]; then
green "1：添加Hysteria2范围端口"
green "2：添加Hysteria2单端口"
green "0：返回上层"
readp "请选择【0-2】：" menu
port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[2].listen_port')
if [ "$menu" = "1" ]; then
fports && sbshare > /dev/null 2>&1 && changeport
elif [ "$menu" = "2" ]; then
fport && sbshare > /dev/null 2>&1 && changeport
else
changeport
fi
elif [ "$menu" = "3" ]; then
if [ -n "$hy2_ports" ]; then
hy2deports && sbshare > /dev/null 2>&1 yellow "Hysteria2多端口已删除" && changeport
else
sbshare > /dev/null 2>&1 && yellow "Hysteria2未设置多端口" && changeport
fi
else
changeport
fi

elif [ "$menu" = "4" ]; then
green "1：更换Tuic5主端口 (原多端口自动重置删除)"
green "2：添加Tuic5多端口"
green "3：重置删除Tuic5多端口"
green "0：返回上层"
readp "请选择【0-3】：" menu
if [ "$menu" = "1" ]; then
if [ -n "$tu5_ports" ]; then
tu5deports
tu5port
echo $sbfiles | xargs -n1 sed -i "89s/$tu5_port/$port_tu/"
restartsb && sbshare > /dev/null 2>&1
else
tu5port
echo $sbfiles | xargs -n1 sed -i "89s/$tu5_port/$port_tu/"
restartsb && sbshare > /dev/null 2>&1
fi
blue "Tuic5端口更改完成"
elif [ "$menu" = "2" ]; then
green "1：添加Tuic5范围端口"
green "2：添加Tuic5单端口"
green "0：返回上层"
readp "请选择【0-2】：" menu
port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[3].listen_port')
if [ "$menu" = "1" ]; then
fports && sbshare > /dev/null 2>&1 && changeport
elif [ "$menu" = "2" ]; then
fport && sbshare > /dev/null 2>&1 && changeport
else
changeport
fi
elif [ "$menu" = "3" ]; then
if [ -n "$tu5_ports" ]; then
tu5deports && sbshare > /dev/null 2>&1 yellow "Tuic5多端口已删除" && changeport
else
sbshare > /dev/null 2>&1 && yellow "Tuic5未设置多端口" && changeport
fi
else
changeport
fi
else
sb
fi
}

changeuuid(){
echo
olduuid=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].users[0].uuid')
oldvmpath=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].transport.path')
green "全协议的uuid (密码)：$olduuid"
green "Vmess的path路径：$oldvmpath"
echo
yellow "1：自定义全协议的uuid (密码)"
yellow "2：自定义Vmess的path路径"
yellow "0：返回上层"
readp "请选择【0-2】：" menu
if [ "$menu" = "1" ]; then
readp "输入uuid，必须是uuid格式，不懂就回车(重置并随机生成uuid)：" menu
if [ -z "$menu" ]; then
uuid=$(/etc/s-box/sing-box generate uuid)
else
uuid=$menu
fi
echo $sbfiles | xargs -n1 sed -i "s/$olduuid/$uuid/g"
restartsb && sbshare > /dev/null 2>&1
blue "已确认uuid (密码)：${uuid}" 
blue "已确认Vmess的path路径：$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].transport.path')"
elif [ "$menu" = "2" ]; then
readp "输入Vmess的path路径，回车表示不变：" menu
if [ -z "$menu" ]; then
echo
else
vmpath=$menu
echo $sbfiles | xargs -n1 sed -i "50s#$oldvmpath#$vmpath#g"
restartsb && sbshare > /dev/null 2>&1
fi
blue "已确认Vmess的path路径：$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].transport.path')"
else
changeserv
fi
}

changeip(){
if [[ "$sbnh" == "1.10" ]]; then
v4v6 refresh
chip(){
rpip=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.outbounds[0].domain_strategy')
sed -i "111s/$rpip/$rrpip/g" /etc/s-box/sb10.json
cp /etc/s-box/sb10.json /etc/s-box/sb.json
restartsb
}
readp "1. IPV4优先\n2. IPV6优先\n3. 仅IPV4\n4. 仅IPV6\n请选择：" choose
if [[ $choose == "1" && -n $v4 ]]; then
rrpip="prefer_ipv4" && chip && v4_6="IPV4优先($v4)"
elif [[ $choose == "2" && -n $v6 ]]; then
rrpip="prefer_ipv6" && chip && v4_6="IPV6优先($v6)"
elif [[ $choose == "3" && -n $v4 ]]; then
rrpip="ipv4_only" && chip && v4_6="仅IPV4($v4)"
elif [[ $choose == "4" && -n $v6 ]]; then
rrpip="ipv6_only" && chip && v4_6="仅IPV6($v6)"
else 
red "当前不存在你选择的IPV4/IPV6地址，或者输入错误" && changeip
fi
blue "当前已更换的IP优先级：${v4_6}" && sb
else
red "仅支持1.10.7内核可用" && exit
fi
}

tgsbshow(){
echo
yellow "1：重置/设置Telegram机器人的Token、用户ID"
yellow "0：返回上层"
readp "请选择【0-1】：" menu
if [ "$menu" = "1" ]; then
rm -rf /etc/s-box/sbtg.sh
readp "输入Telegram机器人Token: " token
telegram_token=$token
readp "输入Telegram机器人用户ID: " userid
telegram_id=$userid
echo '#!/bin/bash
export LANG=en_US.UTF-8
sbnh=$(/etc/s-box/sing-box version 2>/dev/null | awk '/version/{print $NF}' 2>/dev/null | cut -d '.' -f 1,2)
total_lines=$(wc -l < /etc/s-box/clmi.yaml)
half=$((total_lines / 2))
head -n $half /etc/s-box/clmi.yaml > /etc/s-box/clash_meta_client1.txt
tail -n +$((half + 1)) /etc/s-box/clmi.yaml > /etc/s-box/clash_meta_client2.txt

total_lines=$(wc -l < /etc/s-box/sbox.json)
quarter=$((total_lines / 4))
head -n $quarter /etc/s-box/sbox.json > /etc/s-box/sing_box_client1.txt
tail -n +$((quarter + 1)) /etc/s-box/sbox.json | head -n $quarter > /etc/s-box/sing_box_client2.txt
tail -n +$((2 * quarter + 1)) /etc/s-box/sbox.json | head -n $quarter > /etc/s-box/sing_box_client3.txt
tail -n +$((3 * quarter + 1)) /etc/s-box/sbox.json > /etc/s-box/sing_box_client4.txt

m1=$(cat /etc/s-box/vl_reality.txt 2>/dev/null)
m2=$(cat /etc/s-box/vm_ws.txt 2>/dev/null)
m3=$(cat /etc/s-box/vm_ws_argols.txt 2>/dev/null)
m3_5=$(cat /etc/s-box/vm_ws_argogd.txt 2>/dev/null)
m4=$(cat /etc/s-box/vm_ws_tls.txt 2>/dev/null)
m5=$(cat /etc/s-box/hy2.txt 2>/dev/null)
m6=$(cat /etc/s-box/tuic5.txt 2>/dev/null)
m7=$(cat /etc/s-box/sing_box_client1.txt 2>/dev/null)
m7_5=$(cat /etc/s-box/sing_box_client2.txt 2>/dev/null)
m7_5_5=$(cat /etc/s-box/sing_box_client3.txt 2>/dev/null)
m7_5_5_5=$(cat /etc/s-box/sing_box_client4.txt 2>/dev/null)
m8=$(cat /etc/s-box/clash_meta_client1.txt 2>/dev/null)
m8_5=$(cat /etc/s-box/clash_meta_client2.txt 2>/dev/null)
m9=$(cat /etc/s-box/sing_box_gitlab.txt 2>/dev/null)
m10=$(cat /etc/s-box/clash_meta_gitlab.txt 2>/dev/null)
m11=$(cat /etc/s-box/jhsub.txt 2>/dev/null)
m12=$(cat /etc/s-box/an.txt 2>/dev/null)
message_text_m1=$(echo "$m1")
message_text_m2=$(echo "$m2")
message_text_m3=$(echo "$m3")
message_text_m3_5=$(echo "$m3_5")
message_text_m4=$(echo "$m4")
message_text_m5=$(echo "$m5")
message_text_m6=$(echo "$m6")
message_text_m7=$(echo "$m7")
message_text_m7_5=$(echo "$m7_5")
message_text_m7_5_5=$(echo "$m7_5_5")
message_text_m7_5_5_5=$(echo "$m7_5_5_5")
message_text_m8=$(echo "$m8")
message_text_m8_5=$(echo "$m8_5")
message_text_m9=$(echo "$m9")
message_text_m10=$(echo "$m10")
message_text_m11=$(echo "$m11")
message_text_m12=$(echo "$m12")
MODE=HTML
URL="https://api.telegram.org/bottelegram_token/sendMessage"
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Vless-reality-vision 分享链接 】：支持v2rayng、nekobox "$'"'"'\n\n'"'"'"${message_text_m1}")
if [[ -f /etc/s-box/vm_ws.txt ]]; then
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Vmess-ws 分享链接 】：支持v2rayng、nekobox "$'"'"'\n\n'"'"'"${message_text_m2}")
fi
if [[ -f /etc/s-box/vm_ws_argols.txt ]]; then
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Vmess-ws(tls)+Argo临时域名分享链接 】：支持v2rayng、nekobox "$'"'"'\n\n'"'"'"${message_text_m3}")
fi
if [[ -f /etc/s-box/vm_ws_argogd.txt ]]; then
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Vmess-ws(tls)+Argo固定域名分享链接 】：支持v2rayng、nekobox "$'"'"'\n\n'"'"'"${message_text_m3_5}")
fi
if [[ -f /etc/s-box/vm_ws_tls.txt ]]; then
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Vmess-ws-tls 分享链接 】：支持v2rayng、nekobox "$'"'"'\n\n'"'"'"${message_text_m4}")
fi
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Hysteria-2 分享链接 】：支持v2rayng、nekobox "$'"'"'\n\n'"'"'"${message_text_m5}")
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Tuic-v5 分享链接 】：支持nekobox "$'"'"'\n\n'"'"'"${message_text_m6}")
if [[ "$sbnh" != "1.10" ]]; then
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Anytls 分享链接 】：仅最新内核可用 "$'"'"'\n\n'"'"'"${message_text_m12}")
fi
if [[ -f /etc/s-box/sing_box_gitlab.txt ]]; then
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Sing-box 订阅链接 】：支持SFA、SFW、SFI "$'"'"'\n\n'"'"'"${message_text_m9}")
else
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Sing-box 配置文件(4段) 】：支持SFA、SFW、SFI "$'"'"'\n\n'"'"'"${message_text_m7}")
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=${message_text_m7_5}")
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=${message_text_m7_5_5}")
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=${message_text_m7_5_5_5}")
fi

if [[ -f /etc/s-box/clash_meta_gitlab.txt ]]; then
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Mihomo 订阅链接 】：支持Mihomo相关客户端 "$'"'"'\n\n'"'"'"${message_text_m10}")
else
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 Mihomo 配置文件(2段) 】：支持Mihomo相关客户端 "$'"'"'\n\n'"'"'"${message_text_m8}")
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=${message_text_m8_5}")
fi
res=$(timeout 20s curl -s -X POST $URL -d chat_id=telegram_id  -d parse_mode=${MODE} --data-urlencode "text=🚀【 聚合节点 】：支持nekobox "$'"'"'\n\n'"'"'"${message_text_m11}")

if [ $? == 124 ];then
echo TG_api请求超时,请检查网络是否重启完成并是否能够访问TG
fi
resSuccess=$(echo "$res" | jq -r ".ok")
if [[ $resSuccess = "true" ]]; then
echo "TG推送成功";
else
echo "TG推送失败，请检查TG机器人Token和ID";
fi
' > /etc/s-box/sbtg.sh
sed -i "s/telegram_token/$telegram_token/g" /etc/s-box/sbtg.sh
sed -i "s/telegram_id/$telegram_id/g" /etc/s-box/sbtg.sh
green "设置完成！请确保TG机器人已处于激活状态！"
tgnotice
else
changeserv
fi
}

tgnotice(){
if [[ -f /etc/s-box/sbtg.sh ]]; then
green "请稍等5秒，TG机器人准备推送……"
sbshare > /dev/null 2>&1
bash /etc/s-box/sbtg.sh
else
yellow "未设置TG通知功能"
fi
exit
}

# Optional Xray sidecar. Kept in sb.sh so curl/bash installation stays self-contained.
xhttp_mihomo_load(){
# JSON flow mappings and quoted scalars are valid YAML; jq escapes names/paths safely.
# Called only when the sidecar exists. Never emit privateKey/decryption secrets.
# Xray v26.11.9 requires the hybrid key-share in ClientHello; Mihomo defaults it off.
local dir=/etc/s-box/xhttp server public encryption=none
server=$(cat /etc/s-box/server_ipcl.log) || return 1
server=${server#[}; server=${server%]}
[[ -n $server ]] || return 1
public=$(cat "$dir/public.key") || return 1
if [[ $(jq -r '.inbounds[0].settings.decryption // "none"' "$dir/config.json") != none ]]; then
encryption=$(cat "$dir/encryption.key") || return 1
[[ $encryption == mlkem768x25519plus.* ]] || return 1
fi
# --rawfile is not available in Debian 10's jq 1.5; --arg preserves the key as data.
xhttp_cl_node=$(jq -ecn --slurpfile cfg "$dir/config.json" --arg public "$public" \
--arg encryption "$encryption" --arg server "$server" --arg name "${node_prefix_label}vless-xhttp-reality${node_suffix_label}" '
 $cfg[0].inbounds[0] as $in |
 ($public | rtrimstr("\n") | rtrimstr("\r")) as $key |
 if $in.protocol != "vless" or $in.streamSettings.network != "xhttp" or $in.streamSettings.security != "reality"
 then error("invalid XHTTP sidecar config") else . end |
 {name:$name, type:"vless", server:$server, port:$in.port,
  uuid:$in.settings.clients[0].id, network:"xhttp", udp:true, tls:true,
  servername:$in.streamSettings.realitySettings.serverNames[0],
  "client-fingerprint":"chrome", "skip-cert-verify":false,
  "reality-opts":{"public-key":$key,"short-id":$in.streamSettings.realitySettings.shortIds[0],"support-x25519mlkem768":true},
  "xhttp-opts":{path:$in.streamSettings.xhttpSettings.path,mode:"auto"}} |
 if (.port|type) != "number" or .port < 1 or .port > 65535 or
    (.uuid|type) != "string" or (.servername|type) != "string" or
    (."xhttp-opts".path|type) != "string" or
    (."reality-opts"."short-id"|type) != "string" or
    ($key|test("^[A-Za-z0-9_-]{43}$")|not)
 then error("missing/invalid XHTTP export fields") else . end |
 if $encryption != "none" then .encryption=$encryption else . end |
 if ($in.settings.clients[0].flow // "") != "" then .flow=$in.settings.clients[0].flow else . end
') || return 1
xhttp_cl_name=$(jq -cr '.name|@json' <<< "$xhttp_cl_node")
}

xhttp_server_config(){
local dir=$1 port=$2 sni=$3 id=$4 private=$5 sid=$6 path=$7 flow=${8:-} decryption=${9:-none}
jq -n --arg flow "$flow" --arg decryption "$decryption" --argjson port "$port" --arg sni "$sni" --arg id "$id" --arg key "$private" --arg sid "$sid" --arg path "$path" '{
 log:{loglevel:"warning"},
 inbounds:[{tag:"xhttp-reality",listen:"::",port:$port,protocol:"vless",
 settings:{clients:[({id:$id}|if $flow != "" then .flow=$flow else . end)],decryption:$decryption},
 streamSettings:{network:"xhttp",security:"reality",
 realitySettings:{show:false,target:($sni+":443"),xver:0,serverNames:[$sni],privateKey:$key,shortIds:[$sid]},
 xhttpSettings:{path:$path,mode:"auto"}}}],
 outbounds:[{protocol:"freedom",tag:"direct"}]
}' > "$dir/config.json"
}

xhttp_client_config(){
local dir=$1 server=$2 port=$3 sni=$4 id=$5 public=$6 sid=$7 path=$8 name=$9 flow=${10:-} encryption=${11:-none}
jq -n --arg flow "$flow" --arg encryption "$encryption" --arg server "$server" --argjson port "$port" --arg sni "$sni" --arg id "$id" --arg key "$public" --arg sid "$sid" --arg path "$path" --arg name "$name" '{
 log:{loglevel:"warning"},
 inbounds:[{listen:"127.0.0.1",port:10808,protocol:"socks",settings:{auth:"noauth",udp:true}}],
 outbounds:[{tag:$name,protocol:"vless",settings:{vnext:[{address:$server,port:$port,users:[({id:$id,encryption:$encryption}|if $flow != "" then .flow=$flow else . end)]}]},
 streamSettings:{network:"xhttp",security:"reality",realitySettings:{fingerprint:"chrome",serverName:$sni,password:$key,shortId:$sid},
 xhttpSettings:{path:$path,mode:"auto"}}}]
}' > "$dir/client.json" || return 1
local authority=$server encoded_path encoded_name encoded_encryption flow_query=
[[ $authority == *:* ]] && authority="[$authority]"
encoded_path=$(jq -nr --arg v "$path" '$v|@uri') || return 1
encoded_name=$(jq -nr --arg v "$name" '$v|@uri') || return 1
encoded_encryption=$(jq -nr --arg v "$encryption" '$v|@uri') || return 1
[[ -z $flow ]] || flow_query="&flow=$flow"
printf 'vless://%s@%s:%s?encryption=%s%s&security=reality&sni=%s&fp=chrome&pbk=%s&sid=%s&type=xhttp&path=%s&mode=auto#%s\n' "$id" "$authority" "$port" "$encoded_encryption" "$flow_query" "$sni" "$public" "$sid" "$encoded_path" "$encoded_name" > "$dir/share.txt"
}

xhttp_export(){
local dir=/etc/s-box/xhttp server port sni id public sid path flow encryption=none
[[ -f $dir/config.json && -f $dir/public.key ]] || return 0
server=$(cat /etc/s-box/server_ipcl.log) || return 1
server=${server#[}; server=${server%]}
[[ -n $server ]] || return 1
port=$(jq -er '.inbounds[0].port' "$dir/config.json") || return 1
sni=$(jq -er '.inbounds[0].streamSettings.realitySettings.serverNames[0]' "$dir/config.json") || return 1
id=$(jq -er '.inbounds[0].settings.clients[0].id' "$dir/config.json") || return 1
sid=$(jq -er '.inbounds[0].streamSettings.realitySettings.shortIds[0]' "$dir/config.json") || return 1
path=$(jq -er '.inbounds[0].streamSettings.xhttpSettings.path' "$dir/config.json") || return 1
public=$(cat "$dir/public.key") || return 1
flow=$(jq -r '.inbounds[0].settings.clients[0].flow // ""' "$dir/config.json") || return 1
if [[ $(jq -r '.inbounds[0].settings.decryption // "none"' "$dir/config.json") != none ]]; then
encryption=$(cat "$dir/encryption.key") || return 1
[[ $encryption == mlkem768x25519plus.* ]] || return 1
fi
node_suffix_load || return 1
local out="${SB_EXPORT_DIR:-/etc/s-box}/xhttp"
mkdir -p "$out" || return 1
(umask 077; xhttp_client_config "$out" "$server" "$port" "$sni" "$id" "$public" "$sid" "$path" "${node_prefix_label}vless-xhttp-reality${node_suffix_label}" "$flow" "$encryption") || return 1
cp "$out/share.txt" "${SB_EXPORT_DIR:-/etc/s-box}/xhttp.txt"
}

xhttp_service(){
local action=$1
if command -v apk >/dev/null 2>&1; then
case "$action" in
enable) rc-update add sbox-xhttp default ;;
disable) rc-update del sbox-xhttp default ;;
*) rc-service sbox-xhttp "$action" ;;
esac
else
if [[ $action == status ]]; then
systemctl --no-pager --full status sbox-xhttp
return $?
fi
systemctl "$action" sbox-xhttp
fi
}

xhttp_remove(){
if [[ -e /etc/init.d/sbox-xhttp || -e /etc/systemd/system/sbox-xhttp.service ]]; then
xhttp_service stop || { red "停止XHTTP服务失败，保留配置以便排查。"; return 1; }
xhttp_service disable || return 1
fi
rm -f /etc/init.d/sbox-xhttp /etc/systemd/system/sbox-xhttp.service || return 1
if ! command -v apk >/dev/null 2>&1; then systemctl daemon-reload || return 1; fi
rm -rf /etc/s-box/xhttp || return 1
rm -f /etc/s-box/xhttp.txt
}

xhttp_dependencies(){
local tool manager package
local -a missing=() packages=()
for tool in curl jq unzip openssl sha256sum ss; do
command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
(( ${#missing[@]} )) || return 0
for manager in apk apt-get dnf yum; do
command -v "$manager" >/dev/null 2>&1 && break
done
if ! command -v "$manager" >/dev/null 2>&1; then
red "缺少依赖：${missing[*]}；未找到支持的包管理器，请手动安装后重试。"
return 1
fi
for tool in "${missing[@]}"; do
case "$tool" in
sha256sum) package=coreutils ;;
ss) if [[ $manager == dnf || $manager == yum ]]; then package=iproute; else package=iproute2; fi ;;
*) package=$tool ;;
esac
packages+=("$package")
done
yellow "正在安装XHTTP缺失依赖：${packages[*]}（$manager）"
if [[ $manager == apt-get ]]; then
apt-get update || { red "刷新软件源失败，尚未部署XHTTP；请修复软件源后重试。"; return 1; }
fi
case "$manager" in
apk) apk add --no-cache "${packages[@]}" ;;
*) "$manager" install -y "${packages[@]}" ;;
esac || { red "依赖安装失败，尚未部署XHTTP；请检查上方包管理器错误后重试。"; return 1; }
for tool in "${missing[@]}"; do
command -v "$tool" >/dev/null 2>&1 || { red "安装后仍缺少依赖：$tool，尚未部署XHTTP。"; return 1; }
done
}

xhttp_encryption_pair(){
local dir=$1 output decryption encryption
output=$("$dir/xray" vlessenc) || return 1
# First authentication block is X25519, matching the article. Never mix the PQ pair.
decryption=$(printf '%s\n' "$output" | awk -F '"' '/^"decryption":/{print $4; exit}')
encryption=$(printf '%s\n' "$output" | awk -F '"' '/^"encryption":/{print $4; exit}')
[[ $decryption =~ ^mlkem768x25519plus\.native\.[0-9]+s\.[A-Za-z0-9_-]{43}$ && $encryption =~ ^mlkem768x25519plus\.native\.(0rtt|1rtt)\.[A-Za-z0-9_-]{43}$ ]] || return 1
(umask 077; printf '%s\n' "$decryption" > "$dir/decryption.key" && printf '%s\n' "$encryption" > "$dir/encryption.key")
}

xhttp_article_enable(){
local dir=/etc/s-box/xhttp backup file
[[ -f $dir/config.json ]] || { red "请先部署XHTTP。"; return 1; }
if [[ $(jq -r '.inbounds[0].settings.clients[0].flow // ""' "$dir/config.json") == xtls-rprx-vision && $(jq -r '.inbounds[0].settings.decryption' "$dir/config.json") != none ]]; then
green "已启用Encryption + Vision，不重新生成密钥。"
sbshare > /dev/null
return $?
fi
backup=$(mktemp -d /etc/s-box/xhttp-article.bak.XXXXXX) || return 1
chmod 700 "$backup" || return 1
cp -a "$dir" "$backup/xhttp" || return 1
for file in clmi.yaml sbox.json jhsub.txt jhdy.txt xhttp.txt; do
[[ ! -f /etc/s-box/$file ]] || cp -p "/etc/s-box/$file" "$backup/$file" || return 1
done
if ! (
umask 077
local done=0
trap 'if [[ $done == 0 ]]; then rm -f "$dir/encryption.key" "$dir/decryption.key" "$dir/config.new.json"; cp -a "$backup/xhttp/." "$dir/"; for file in clmi.yaml sbox.json jhsub.txt jhdy.txt xhttp.txt; do [[ ! -f $backup/$file ]] || cp -p "$backup/$file" "/etc/s-box/$file"; done; xhttp_service restart; fi' EXIT
xhttp_encryption_pair "$dir" || exit 1
jq --arg decryption "$(cat "$dir/decryption.key")" '.inbounds[0].settings.decryption=$decryption | .inbounds[0].settings.clients[0].flow="xtls-rprx-vision" | .inbounds[0].streamSettings.xhttpSettings.path="/"' "$dir/config.json" > "$dir/config.new.json" || exit 1
"$dir/xray" run -test -config "$dir/config.new.json" || exit 1
mv "$dir/config.new.json" "$dir/config.json" || exit 1
xhttp_export || exit 1
"$dir/xray" run -test -config "$dir/client.json" || exit 1
xhttp_service restart || exit 1
sleep 2
xhttp_service status || exit 1
sbshare > /dev/null || exit 1
done=1
); then
red "升级失败，已尝试恢复原XHTTP；备份：$backup"
return 1
fi
green "已启用文章同款XHTTP + REALITY + VLESS Encryption（X25519认证）+ Vision；更新客户端订阅后使用。备份：$backup"
}

# Shared pinned Xray profile for both independent sidecar installers.
# Outputs use caller-local scope; neither helper mutates an existing installation.
xhttp_core_profile(){
xhttp_xray_version=v26.11.9
case $(uname -m) in
x86_64) xhttp_xray_arch=64; xhttp_cloudflared_arch=amd64 ;;
aarch64) xhttp_xray_arch=arm64-v8a; xhttp_cloudflared_arch=arm64 ;;
armv7l) xhttp_xray_arch=arm32-v7a; xhttp_cloudflared_arch=arm ;;
*) red "XHTTP 暂不支持该架构。"; return 1 ;;
esac
}

xhttp_core_prepare(){
local stage=$1 existing=${2-} expected actual reported xhttp_xray_version xhttp_xray_arch xhttp_cloudflared_arch
xhttp_core_profile || return 1
if [[ -n $existing && -x $existing ]]; then
reported=$("$existing" version 2>/dev/null) || reported=
reported=$(printf '%s\n' "$reported" | awk 'NR==1 && $1=="Xray" {print $2}')
fi
if [[ $reported == "${xhttp_xray_version#v}" ]]; then
cp "$existing" "$stage/xray" || return 1
else
curl -fL --retry 3 --connect-timeout 15 --max-time 300 "https://github.com/XTLS/Xray-core/releases/download/$xhttp_xray_version/Xray-linux-$xhttp_xray_arch.zip" -o "$stage/core.zip" || return 1
curl -fL --retry 3 --connect-timeout 15 --max-time 60 "https://github.com/XTLS/Xray-core/releases/download/$xhttp_xray_version/Xray-linux-$xhttp_xray_arch.zip.dgst" -o "$stage/core.dgst" || return 1
expected=$(awk -F '= *' '/^SHA2-256=/{gsub(/\r/,"",$2); print $2}' "$stage/core.dgst") || return 1
actual=$(sha256sum "$stage/core.zip" | awk '{print $1}') || return 1
[[ $expected =~ ^[a-fA-F0-9]{64}$ && ${actual,,} == ${expected,,} ]] || { echo "Xray SHA256校验失败" >&2; return 1; }
unzip -q "$stage/core.zip" xray -d "$stage" || return 1
rm "$stage/core.zip" "$stage/core.dgst" || return 1
fi
chmod 700 "$stage/xray" || return 1
printf '%s\n' "$xhttp_xray_version" > "$stage/version"
}

xhttp_install(){
[[ -f /etc/s-box/sb.json ]] || { red "请先安装 Sing-box。"; return 1; }
[[ ! -e /etc/s-box/xhttp && ! -e /etc/systemd/system/sbox-xhttp.service && ! -e /etc/init.d/sbox-xhttp ]] || { red "XHTTP 已存在。请先备份并通过本菜单卸载，再重新部署。"; return 1; }
local port sni profile xhttp_xray_version xhttp_xray_arch xhttp_cloudflared_arch
xhttp_dependencies || return 1
xhttp_core_profile || return 1
readp "XHTTP方案：1=文章同款Encryption + Vision（默认）；2=普通XHTTP + REALITY：" profile
profile=${profile:-1}
[[ $profile == 1 || $profile == 2 ]] || { red "请选择1或2。"; return 1; }
readp "XHTTP + REALITY 独立 TCP 端口（默认443，不能与现有服务重复）：" port
port=${port:-443}
if [[ ! $port =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
red "端口必须为1–65535。"; return 1
fi
port=$((10#$port))
if [[ -n $(ss -H -ltn "sport = :$port") ]]; then red "TCP 端口 $port 已被占用。"; return 1; fi
readp "REALITY 目标域名（需支持TLS1.3/H2，默认www.cloudflare.com）：" sni
sni=${sni:-www.cloudflare.com}
if [[ ${#sni} -gt 253 || ! $sni =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$ ]]; then
red "请输入不带协议、端口、路径的有效域名。"; return 1
fi
# All changes are confined to a new sidecar. Failure never restarts sing-box.
if ! (
umask 077
local stage committed=0 keypair private public id sid path flow= decryption=none
stage=$(mktemp -d /etc/s-box/.xhttp-install.XXXXXX) || exit 1
trap 'rm -rf "$stage"; if [[ $committed == 1 ]]; then xhttp_remove; fi' EXIT
xhttp_core_prepare "$stage" || exit 1
keypair=$("$stage/xray" x25519) || exit 1
private=$(printf '%s\n' "$keypair" | awk '/^PrivateKey:/{print $2}') || exit 1
public=$(printf '%s\n' "$keypair" | awk '/^Password \(PublicKey\):/{print $3} /^PublicKey:/{print $2}') || exit 1
[[ $private =~ ^[A-Za-z0-9_-]{43}$ && $public =~ ^[A-Za-z0-9_-]{43}$ ]] || exit 1
id=$("$stage/xray" uuid) || exit 1
sid=$(openssl rand -hex 8) || exit 1
path="/$(openssl rand -hex 16)" || exit 1
if [[ $profile == 1 ]]; then
xhttp_encryption_pair "$stage" || exit 1
flow=xtls-rprx-vision
decryption=$(cat "$stage/decryption.key") || exit 1
path=/
fi
xhttp_server_config "$stage" "$port" "$sni" "$id" "$private" "$sid" "$path" "$flow" "$decryption" || exit 1
printf '%s\n' "$public" > "$stage/public.key" || exit 1
"$stage/xray" run -test -config "$stage/config.json" || exit 1
mv "$stage" /etc/s-box/xhttp || exit 1
committed=1
xhttp_export || exit 1
/etc/s-box/xhttp/xray run -test -config /etc/s-box/xhttp/client.json || exit 1
if command -v apk >/dev/null 2>&1; then
cat > /etc/init.d/sbox-xhttp <<'XHTTP_OPENRC' || exit 1
#!/sbin/openrc-run
description="sing-box-yg XHTTP REALITY sidecar"
command=/etc/s-box/xhttp/xray
command_args="run -config /etc/s-box/xhttp/config.json"
command_background=true
pidfile=/run/sbox-xhttp.pid
output_log=/etc/s-box/xhttp/service.log
error_log=/etc/s-box/xhttp/service.log
depend() { need net; }
XHTTP_OPENRC
chmod 755 /etc/init.d/sbox-xhttp || exit 1
else
cat > /etc/systemd/system/sbox-xhttp.service <<'XHTTP_SYSTEMD' || exit 1
[Unit]
Description=sing-box-yg XHTTP REALITY sidecar
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=/etc/s-box/xhttp/xray run -config /etc/s-box/xhttp/config.json
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
UMask=0077
[Install]
WantedBy=multi-user.target
XHTTP_SYSTEMD
systemctl daemon-reload || exit 1
fi
xhttp_service enable || exit 1
xhttp_service start || exit 1
sleep 2
xhttp_service status || exit 1
[[ -n $(ss -H -ltn "sport = :$port") ]] || exit 1
committed=0
); then
red "XHTTP部署失败，已尝试清理本次部署；若上方提示停止失败，请先处理残留服务。现有Sing-box配置未修改。"
return 1
fi
green "XHTTP + REALITY 已部署。请在云防火墙/安全组及系统防火墙放行 TCP $port。"
yellow "此节点直连VPS，不经Argo/CDN；需要支持XHTTP的Xray客户端。"
cat /etc/s-box/xhttp/share.txt
sbshare > /dev/null || { red "节点已部署，但聚合订阅刷新失败，请通过菜单9重试。"; return 1; }
}

# Independent HTTP origin: Cloudflare terminates TLS; VLESS Encryption protects the payload.
# Keep the SSE response header: cloudflared otherwise buffers the streaming download.
xhttp_argo_server_config(){
local dir=$1 port=$2 id=$3 path=$4 decryption=$5
jq -n --argjson port "$port" --arg id "$id" --arg path "$path" --arg decryption "$decryption" '{
 log:{loglevel:"warning"},inbounds:[{tag:"xhttp-argo",listen:"127.0.0.1",port:$port,protocol:"vless",
 settings:{clients:[{id:$id,flow:"xtls-rprx-vision"}],decryption:$decryption},
 streamSettings:{network:"xhttp",security:"none",xhttpSettings:{path:$path,mode:"auto",noSSEHeader:false}}}],
 outbounds:[{protocol:"freedom",tag:"direct"}]
}' > "$dir/config.json"
}

xhttp_argo_address_valid(){
# Syntax validation only: no DNS lookup, automatic scanning or speed guarantee.
jq -en --arg address "$1" '
 def ipv4:
  split(".") as $p | ($p|length)==4 and
  all($p[]; test("^(0|[1-9][0-9]{0,2})$") and (tonumber <= 255));
 def groups: if .=="" then [] else split(":") end;
 def ipv6:
  test("^[0-9A-Fa-f:]+$") and
  (if contains("::") then
    split("::") as $p | ($p|length)==2 and
    (($p[0]|groups)+($p[1]|groups)) as $g |
    ($g|length)<8 and all($g[]; test("^[0-9A-Fa-f]{1,4}$"))
   else split(":") as $g | ($g|length)==8 and all($g[]; test("^[0-9A-Fa-f]{1,4}$")) end);
 $address | length>=1 and length<=253 and
 (if contains(":") then
   (if contains(".") then . as $original | split(":")[-1] as $last |
     if ($last|ipv4) then $original|sub("[^:]+$";"0:0") else "" end
    else . end) | ipv6
  elif test("^[0-9.]+$") then ipv4
  else split(".") as $labels | ($labels|length)>=2 and
   all($labels[]; length>=1 and length<=63 and test("^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")) end)
' >/dev/null 2>&1
}

xhttp_argo_mihomo_load(){
local dir=/etc/s-box/xhttp-argo domain encryption server
domain=$(cat "$dir/domain") || return 1
encryption=$(cat "$dir/encryption.key") || return 1
[[ $domain =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$ && $encryption =~ ^mlkem768x25519plus\.native\.(0rtt|1rtt)\.[A-Za-z0-9_-]{43}$ ]] || return 1
server=$domain
if [[ -f $dir/server.conf ]]; then server=$(cat "$dir/server.conf") || return 1; fi
if [[ $server == \[*\] && $server == *:* ]]; then server=${server:1:${#server}-2}; fi
xhttp_argo_address_valid "$server" || { red "XHTTP Argo 优选地址无效，未生成配置。"; return 1; }
xhttp_argo_cl_node=$(jq -ecn --slurpfile cfg "$dir/config.json" --arg domain "$domain" --arg server "$server" --arg encryption "$encryption" --arg name "${node_prefix_label}vless-xhttp-argo${node_suffix_label}" '
 $cfg[0].inbounds[0] as $in |
 if $in.listen != "127.0.0.1" or $in.protocol != "vless" or $in.streamSettings.network != "xhttp" or $in.streamSettings.security != "none" or
 ($in.port|type) != "number" or $in.port < 1 or $in.port > 65535 or
 ($in.settings.clients[0].id|type) != "string" or $in.settings.clients[0].flow != "xtls-rprx-vision" or
 ($in.streamSettings.xhttpSettings.path|type) != "string" or
 (($in.settings.decryption // "")|test("^mlkem768x25519plus\\.native\\.[0-9]+s\\.[A-Za-z0-9_-]{43}$")|not)
 then error("invalid XHTTP Argo origin") else . end |
 {name:$name,type:"vless",server:$server,port:443,uuid:$in.settings.clients[0].id,
 encryption:$encryption,flow:$in.settings.clients[0].flow,network:"xhttp",udp:true,tls:true,
 servername:$domain,"client-fingerprint":"chrome","skip-cert-verify":false,
 "xhttp-opts":{host:$domain,path:$in.streamSettings.xhttpSettings.path,mode:"packet-up"}}
') || return 1
xhttp_argo_cl_name=$(jq -cr '.name|@json' <<< "$xhttp_argo_cl_node")
}

xhttp_argo_export(){
local dir=/etc/s-box/xhttp-argo xhttp_argo_cl_node xhttp_argo_cl_name
[[ -f $dir/config.json ]] || return 0
node_suffix_load && xhttp_argo_mihomo_load || return 1
local out="${SB_EXPORT_DIR:-/etc/s-box}/xhttp-argo"
mkdir -p "$out" || return 1
(umask 077
printf '%s\n' "$xhttp_argo_cl_node" > "$out/mihomo.json" || exit 1
jq -n --argjson node "$xhttp_argo_cl_node" '{
 log:{loglevel:"warning"},inbounds:[{listen:"127.0.0.1",port:10808,protocol:"socks",settings:{auth:"noauth",udp:true}}],
 outbounds:[{tag:$node.name,protocol:"vless",settings:{vnext:[{address:$node.server,port:$node.port,users:[{id:$node.uuid,encryption:$node.encryption,flow:$node.flow}]}]},
 streamSettings:{network:"xhttp",security:"tls",tlsSettings:{serverName:$node.servername,fingerprint:"chrome",alpn:["h2","http/1.1"]},
 xhttpSettings:{host:$node["xhttp-opts"].host,path:$node["xhttp-opts"].path,mode:"packet-up",noSSEHeader:false}}}]
}' > "$out/client.json" || exit 1
jq -r '"vless://"+.uuid+"@"+(if (.server|contains(":")) then "["+.server+"]" else .server end)+":443?encryption="+(.encryption|@uri)+"&flow="+.flow+"&security=tls&sni="+.servername+"&fp=chrome&alpn=h2%2Chttp%2F1.1&type=xhttp&host="+."xhttp-opts".host+"&path="+(."xhttp-opts".path|@uri)+"&mode=packet-up#"+(.name|@uri)' "$out/mihomo.json" > "$out/share.txt" || exit 1
cp "$out/share.txt" "${SB_EXPORT_DIR:-/etc/s-box}/xhttp-argo.txt"
)
}

xhttp_argo_address_update(){
local action=$1 server=${2-} dir=/etc/s-box/xhttp-argo backup file tmp result=0
[[ -f $dir/config.json ]] || { red "请先部署 XHTTP + 固定Argo。"; return 1; }
case "$action" in
set)
if [[ $server == \[*\] && $server == *:* ]]; then server=${server:1:${#server}-2}; fi
xhttp_argo_address_valid "$server" || { red "请输入有效的域名、IPv4或IPv6；不含协议、端口、路径或空格。"; return 1; }
;;
reset) ;;
*) return 1 ;;
esac
# Back up all affected generated exports. No origin config, token or service changes.
local -a files=(xhttp-argo/server.conf xhttp-argo/mihomo.json xhttp-argo/client.json xhttp-argo/share.txt
xhttp-argo.txt xhttp.txt clmi.yaml sbox.json jhsub.txt jhdy.txt vl_reality.txt vm_ws_argols.txt
vm_ws_argogd.txt vm_ws.txt vm_ws_tls.txt vm_ws_argo.txt hy2.txt tuic5.txt an.txt SHA256.txt)
backup=$(umask 077; mktemp -d /etc/s-box/xhttp-argo-address.bak.XXXXXX) || return 1
for file in "${files[@]}"; do
if [[ -f /etc/s-box/$file ]]; then
(umask 077; mkdir -p "$backup/$(dirname "$file")" && cp -p "/etc/s-box/$file" "$backup/$file") || return 1
fi
done
if [[ $action == set ]]; then
tmp=$(umask 077; mktemp "$dir/.server.XXXXXX") || return 1
printf '%s\n' "$server" > "$tmp" && mv -f "$tmp" "$dir/server.conf" || { rm -f "$tmp"; return 1; }
else rm -f "$dir/server.conf" || return 1
fi
if ! (umask 077; sbshare > "$backup/refresh.private.log" 2>&1); then
for file in "${files[@]}"; do
if [[ -f $backup/$file ]]; then cp -p "$backup/$file" "/etc/s-box/$file" || result=1
else rm -f "/etc/s-box/$file" || result=1
fi
done
red "刷新失败，已尝试还原优选地址和原导出。备份及私有日志：$backup"
[[ $result == 0 ]] || red "部分文件还原失败，请从备份手动恢复。"
return 1
fi
green "XHTTP Argo 客户端连接地址已更新：${server:-$(cat "$dir/domain")}"
green "旧设置及导出备份：$backup"
yellow "仅修改本节点客户端地址；SNI/Host仍为隧道域名，未重启服务，不影响VMess。"
yellow "这是手动指定优选地址，不自动测速；地址须能接入Cloudflare。Gitlab用9→2推送，客户端更新订阅。"
}

xhttp_argo_address_menu(){
local action input
[[ -f /etc/s-box/xhttp-argo/config.json ]] || { red "请先部署 XHTTP + 固定Argo。"; return 1; }
green "当前XHTTP Argo连接地址：$(cat /etc/s-box/xhttp-argo/server.conf 2>/dev/null || cat /etc/s-box/xhttp-argo/domain)"
readp "1：设置本节点优选域名/IP\n2：恢复默认隧道域名\n0：返回\n请选择【0-2】：" action
case "$action" in
1) IFS= read -r -p "$(yellow '输入优选域名、IPv4或IPv6（回车取消）：')" input || return 0
[[ -n $input ]] || return 0
xhttp_argo_address_update set "$input" ;;
2) xhttp_argo_address_update reset ;;
esac
}

xhttp_argo_service(){
local action=$1 svc result=0
for svc in sbox-xhttp-argo sbox-xhttp-argo-tunnel; do
if command -v apk >/dev/null 2>&1; then
case "$action" in
enable) rc-update add "$svc" default ;;
disable) rc-update del "$svc" default ;;
*) rc-service "$svc" "$action" ;;
esac
elif [[ $action == status ]]; then systemctl --no-pager --full status "$svc"
else systemctl "$action" "$svc"
fi || result=1
done
return "$result"
}

xhttp_argo_remove(){
local svc
for svc in sbox-xhttp-argo-tunnel sbox-xhttp-argo; do
if [[ -e /etc/init.d/$svc || -e /etc/systemd/system/$svc.service ]]; then
if command -v apk >/dev/null 2>&1; then
rc-service "$svc" stop && rc-update del "$svc" default || return 1
else systemctl stop "$svc" && systemctl disable "$svc" || return 1
fi
fi
rm -f "/etc/init.d/$svc" "/etc/systemd/system/$svc.service" || return 1
done
if ! command -v apk >/dev/null 2>&1; then systemctl daemon-reload || return 1; fi
rm -rf /etc/s-box/xhttp-argo || return 1
rm -f /etc/s-box/xhttp-argo.txt
}

xhttp_argo_units(){
local svc binary args
for svc in sbox-xhttp-argo sbox-xhttp-argo-tunnel; do
if [[ $svc == sbox-xhttp-argo ]]; then
binary=xray; args="run -config /etc/s-box/xhttp-argo/config.json"
else
binary=cloudflared; args="tunnel --no-autoupdate --edge-ip-version auto --protocol http2 run --token-file /etc/s-box/xhttp-argo/tunnel.token"
fi
if command -v apk >/dev/null 2>&1; then
cat > "/etc/init.d/$svc" <<XARGO_OPENRC || return 1
#!/sbin/openrc-run
description="sing-box-yg XHTTP fixed tunnel"
command=/etc/s-box/xhttp-argo/$binary
command_args="$args"
command_background=true
pidfile=/run/$svc.pid
output_log=/etc/s-box/xhttp-argo/$svc.log
error_log=/etc/s-box/xhttp-argo/$svc.log
depend() { need net; }
XARGO_OPENRC
chmod 755 "/etc/init.d/$svc" || return 1
else
cat > "/etc/systemd/system/$svc.service" <<XARGO_SYSTEMD || return 1
[Unit]
Description=sing-box-yg XHTTP fixed tunnel ($binary)
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=/etc/s-box/xhttp-argo/$binary $args
Restart=on-failure
RestartSec=5
LimitNOFILE=1048576
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
UMask=0077
[Install]
WantedBy=multi-user.target
XARGO_SYSTEMD
fi
done
if ! command -v apk >/dev/null 2>&1; then systemctl daemon-reload || return 1; fi
}

xhttp_argo_install(){
[[ -f /etc/s-box/sb.json ]] || { red "请先安装 Sing-box。"; return 1; }
[[ ! -e /etc/s-box/xhttp-argo && ! -e /etc/init.d/sbox-xhttp-argo && ! -e /etc/systemd/system/sbox-xhttp-argo.service && ! -e /etc/init.d/sbox-xhttp-argo-tunnel && ! -e /etc/systemd/system/sbox-xhttp-argo-tunnel.service ]] || { red "固定隧道节点已存在，请先备份后卸载。"; return 1; }
xhttp_dependencies || return 1
local domain port tokenfile xhttp_xray_version xhttp_xray_arch xhttp_cloudflared_arch
readp "固定隧道完整域名（例如 xhttp.example.com）：" domain
[[ ${#domain} -le 253 && $domain =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$ ]] || { red "域名格式错误。"; return 1; }
readp "本机 HTTP 回源端口（默认18080；Cloudflare路由需一致）：" port
port=${port:-18080}
[[ $port =~ ^[0-9]{1,5}$ ]] && (( 10#$port >= 1 && 10#$port <= 65535 )) || { red "端口错误。"; return 1; }
port=$((10#$port))
[[ -z $(ss -H -ltn "sport = :$port") ]] || { red "端口已占用。"; return 1; }
readp "Tunnel Token 文件的绝对路径（本服务器文件，不输入Token本身）：" tokenfile
[[ $tokenfile == /* && -s $tokenfile && -f $tokenfile ]] || { red "Token文件不存在或为空。"; return 1; }
# Parse as data only; neither print nor interpolate a token into a command line.
local token
token=$(tr -d '\r\n' < "$tokenfile") || return 1
printf '%s' "$token" | base64 -d 2>/dev/null | jq -e 'type=="object" and (.a|type=="string") and (.t|type=="string") and (.s|type=="string")' >/dev/null 2>&1 || { red "Tunnel Token格式错误。"; return 1; }
xhttp_core_profile || return 1
if ! (
umask 077
local stage committed=0 expected actual id path
stage=$(mktemp -d /etc/s-box/.xhttp-argo-install.XXXXXX) || exit 1
trap 'rm -rf "$stage"; if [[ $committed == 1 ]]; then xhttp_argo_remove; fi' EXIT
xhttp_core_prepare "$stage" /etc/s-box/xhttp/xray || exit 1
if [[ -x /etc/s-box/cloudflared ]]; then cp /etc/s-box/cloudflared "$stage/cloudflared" || exit 1
else
curl -fL --retry 3 --connect-timeout 15 --max-time 300 "https://github.com/cloudflare/cloudflared/releases/download/2026.11.1/cloudflared-linux-$xhttp_cloudflared_arch" -o "$stage/cloudflared" || exit 1
curl -fL --retry 3 --connect-timeout 15 --max-time 60 "https://api.github.com/repos/cloudflare/cloudflared/releases/tags/2026.11.1" -o "$stage/cloudflared.release.json" || exit 1
expected=$(jq -er --arg name "cloudflared-linux-$xhttp_cloudflared_arch" '.assets[]|select(.name==$name)|.digest|select(startswith("sha256:"))|ltrimstr("sha256:")' "$stage/cloudflared.release.json") || exit 1
actual=$(sha256sum "$stage/cloudflared" | awk '{print $1}') || exit 1
[[ $expected =~ ^[a-fA-F0-9]{64}$ && ${actual,,} == ${expected,,} ]] || { echo "cloudflared SHA256校验失败" >&2; exit 1; }
rm "$stage/cloudflared.release.json" || exit 1
fi
chmod 700 "$stage/cloudflared" || exit 1
"$stage/cloudflared" tunnel run --help 2>&1 | grep -q -- '--token-file' || exit 1
printf '%s\n' "$token" > "$stage/tunnel.token" || exit 1
printf '%s\n' "$domain" > "$stage/domain" || exit 1
id=$("$stage/xray" uuid) || exit 1
path="/xhttp/$(openssl rand -hex 16)/" || exit 1
xhttp_encryption_pair "$stage" || exit 1
xhttp_argo_server_config "$stage" "$port" "$id" "$path" "$(cat "$stage/decryption.key")" || exit 1
"$stage/xray" run -test -config "$stage/config.json" || exit 1
mv "$stage" /etc/s-box/xhttp-argo || exit 1
committed=1
xhttp_argo_export || exit 1
/etc/s-box/xhttp-argo/xray run -test -config /etc/s-box/xhttp-argo/client.json || exit 1
xhttp_argo_units && xhttp_argo_service enable && xhttp_argo_service start || exit 1
sleep 3
xhttp_argo_service status || exit 1
[[ -n $(ss -H -ltn "sport = :$port") ]] || exit 1
committed=0
); then red "部署失败，已尝试回滚新节点。现有服务未修改。"; return 1; fi
unset token
green "固定隧道节点已启动。Cloudflare路由必须为 HTTP 127.0.0.1:$port，路径留空。"
yellow "TLS由Cloudflare终止；内层为VLESS Encryption + Vision，不经过REALITY。启动成功不等于外网连通，请用客户端验证。"
sbshare > /dev/null || { red "节点已部署，但订阅刷新失败，请通过菜单9重试。"; return 1; }
}

xhttp_argo_menu(){
local action confirm
readp "XHTTP + 固定Argo（独立节点，保留现有REALITY）\n1：部署\n2：查看节点及刷新订阅\n3：重启\n4：停止\n5：状态\n6：日志\n7：卸载固定Argo节点\n8：独立设置优选域名/IP、恢复默认\n0：返回\n请选择【0-8】：" action
case "$action" in
1) xhttp_argo_install ;;
2) [[ -f /etc/s-box/xhttp-argo/config.json ]] || return 1
xhttp_argo_export && cat /etc/s-box/xhttp-argo/share.txt && sbshare > /dev/null ;;
3) /etc/s-box/xhttp-argo/xray run -test -config /etc/s-box/xhttp-argo/config.json && xhttp_argo_service restart ;;
4) xhttp_argo_service stop ;;
5) xhttp_argo_service status ;;
6) if command -v apk >/dev/null 2>&1; then tail -n 100 /etc/s-box/xhttp-argo/*.log; else journalctl -u sbox-xhttp-argo -u sbox-xhttp-argo-tunnel -n 100 --no-pager; fi ;;
7) readp "会删除固定隧道节点配置和Token，输入 yes 确认：" confirm
[[ $confirm == yes ]] || return 0
xhttp_argo_remove && sbshare > /dev/null ;;
8) xhttp_argo_address_menu ;;
esac
}


xhttp_menu(){
local action confirm
yellow "XHTTP + REALITY（独立Xray，不影响现有五协议；不跟随Sing-box的启停/UUID/端口设置）"
readp "1：部署\n2：查看节点及刷新订阅\n3：重启\n4：停止\n5：查看状态\n6：查看日志\n7：卸载XHTTP\n8：已有节点启用文章同款Encryption + Vision（备份后升级）\n9：XHTTP + 固定Argo（独立隧道节点）\n0：返回\n请选择【0-9】：" action
case "$action" in
1) xhttp_install ;;
2) [[ -f /etc/s-box/xhttp/config.json ]] || { red "尚未部署XHTTP。"; return 1; }
xhttp_export && cat /etc/s-box/xhttp/share.txt && sbshare > /dev/null ;;
3) /etc/s-box/xhttp/xray run -test -config /etc/s-box/xhttp/config.json && xhttp_service restart ;;
4) xhttp_service stop ;;
5) xhttp_service status ;;
6) if command -v apk >/dev/null 2>&1; then tail -n 100 /etc/s-box/xhttp/service.log; else journalctl -u sbox-xhttp -n 100 --no-pager; fi ;;
7) readp "将删除XHTTP配置和密钥；输入 yes 确认：" confirm
[[ $confirm == yes ]] || return 0
xhttp_remove && sbshare > /dev/null ;;
8) xhttp_article_enable ;;
9) xhttp_argo_menu ;;
esac
}


changeserv(){
sbactive
echo
green "Sing-box配置变更选择如下:"
readp "1：更换Reality域名伪装地址、切换自签证书与Acme域名证书、开关TLS\n2：更换全协议UUID(密码)、Vmess-Path路径\n3：设置Argo临时隧道、固定隧道\n4：切换IPV4或IPV6的代理优先级 (仅 1.10.7 内核可用)\n5：设置Telegram推送节点通知\n6：更换Warp-wireguard出站账户\n7：设置Gitlab订阅分享链接\n8：设置本地IP订阅分享链接\n9：设置所有Vmess节点的CDN优选地址\n10：设置节点名称前缀/后缀（默认无前缀、后缀为主机名）\n11：部署/管理 XHTTP + REALITY（独立Xray）\n0：返回上层\n请选择【0-11】：" menu
if [ "$menu" = "1" ];then
changeym
elif [ "$menu" = "2" ];then
changeuuid
elif [ "$menu" = "3" ];then
cfargo_ym
elif [ "$menu" = "4" ];then
changeip
elif [ "$menu" = "5" ];then
tgsbshow
elif [ "$menu" = "6" ];then
changewg
elif [ "$menu" = "7" ];then
gitlabsub
elif [ "$menu" = "8" ];then
ipsub
elif [ "$menu" = "9" ];then
vmesscfadd
elif [ "$menu" = "10" ];then
change_node_suffix
elif [ "$menu" = "11" ];then
xhttp_menu
else 
sb
fi
}

ipsub(){
subtokenipsub(){
echo
readp "输入订阅链接路径密码（回车表示使用当前UUID）：" menu
if [ -z "$menu" ]; then
subtoken="$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].users[0].uuid')"
else
subtoken="$menu"
fi
rm -rf /root/websbox/"$(cat /etc/s-box/subtoken.log 2>/dev/null)"
echo $subtoken > /etc/s-box/subtoken.log
green "订阅链接路径密码：$(cat /etc/s-box/subtoken.log 2>/dev/null)"
}
subportipsub(){
echo
readp "输入未被占用且可用的订阅链接端口（回车表示随机端口）：" menu
if [ -z "$menu" ]; then
subport=$(shuf -i 10000-65535 -n 1)
else
subport="$menu"
fi
echo $subport > /etc/s-box/subport.log
green "订阅链接端口：$(cat /etc/s-box/subport.log 2>/dev/null)"
}
echo
yellow "1：重置安装本地IP订阅链接"
yellow "2：更换订阅链接路径密码"
yellow "3：更换订阅链接端口"
yellow "4：卸载本地IP订阅链接"
yellow "0：返回上层"
readp "请选择【0-4】：" menu
if [ "$menu" = "1" ]; then
subtokenipsub && subportipsub
elif [ "$menu" = "2" ];then
subtokenipsub
elif [ "$menu" = "3" ];then
subportipsub
elif [ "$menu" = "4" ];then
kill -15 $(pgrep -f 'websbox' 2>/dev/null) >/dev/null 2>&1
sb_cron_update subscription || return 1
rm -rf /root/websbox
rm -rf /etc/local.d/alpinesub.start
green "本地IP订阅链接已卸载完成" && sleep 3 && exit
else
changeserv
fi
echo
green "请稍后…………"
kill -15 $(pgrep -f 'websbox' 2>/dev/null) >/dev/null 2>&1
mkdir -p /root/websbox/"$(cat /etc/s-box/subtoken.log 2>/dev/null)"
ln -sf /etc/s-box/clmi.yaml /root/websbox/"$(cat /etc/s-box/subtoken.log 2>/dev/null)"/clmi.yaml
ln -sf /etc/s-box/sbox.json /root/websbox/"$(cat /etc/s-box/subtoken.log 2>/dev/null)"/sbox.json
ln -sf /etc/s-box/jhsub.txt /root/websbox/"$(cat /etc/s-box/subtoken.log 2>/dev/null)"/jhsub.txt
if command -v apk >/dev/null 2>&1; then
busybox-extras httpd -f -p "$(cat /etc/s-box/subport.log 2>/dev/null)" -h /root/websbox > /dev/null 2>&1 &
else
busybox httpd -f -p "$(cat /etc/s-box/subport.log 2>/dev/null)" -h /root/websbox > /dev/null 2>&1 &
fi
sleep 5
if command -v apk >/dev/null 2>&1; then
cat > /etc/local.d/alpinesub.start <<'EOF'
#!/bin/bash
sleep 10
busybox-extras httpd -f -p $(cat /etc/s-box/subport.log 2>/dev/null) -h /root/websbox > /dev/null 2>&1 &
EOF
chmod +x /etc/local.d/alpinesub.start
rc-update add local default >/dev/null 2>&1
else
sb_cron_update subscription '@reboot sleep 10 && /bin/bash -c "busybox httpd -f -p $(cat /etc/s-box/subport.log 2>/dev/null) -h /root/websbox > /dev/null 2>&1 &"' || return 1
fi
sbshare > /dev/null 2>&1
sleep 1 && green "本地IP订阅链接已更新完成" && sleep 3 && sb
}

vmesscfadd(){
echo
green "推荐使用稳定的世界大厂或组织的官方CDN域名作为CDN优选地址："
blue "cloudflare-ech.com"
blue "www.visa.com.sg"
blue "www.wto.org"
blue "www.shopify.com"
blue "yg1.ygkkk.dpdns.org (yg1中的1，可换为1-13中任意数字)"
echo
yellow "恢复默认操作：选项1设置为VPS的IP或者解析的域名，选项2设置为www.bing.com或者解析的域名"
echo
yellow "1：自定义Vmess-ws(tls)主协议节点的CDN优选地址"
yellow "2：针对选项1，重置客户端host/sni域名(IP解析到CF上的域名)"
yellow "3：自定义Vmess-ws(tls)-Argo节点的CDN优选地址"
yellow "0：返回上层"
readp "请选择【0-3】：" menu
if [ "$menu" = "1" ]; then
echo
green "请确保VPS的IP已解析到Cloudflare的域名上"
if [[ ! -f /etc/s-box/cfymjx.txt ]] 2>/dev/null; then
readp "输入客户端host/sni域名(IP解析到CF上的域名)：" menu
echo "$menu" > /etc/s-box/cfymjx.txt
fi
echo
readp "输入自定义的优选IP/域名：" menu
echo "$menu" > /etc/s-box/cfvmadd_local.txt
sbshare > /dev/null 2>&1
green "设置成功，选择主菜单9进行节点配置更新" && sleep 2 && vmesscfadd
elif  [ "$menu" = "2" ]; then
rm -rf /etc/s-box/cfymjx.txt
sbshare > /dev/null 2>&1
green "重置成功，可选择1重新设置" && sleep 2 && vmesscfadd
elif  [ "$menu" = "3" ]; then
readp "输入自定义的优选IP/域名：" menu
echo "$menu" > /etc/s-box/cfvmadd_argo.txt
sbshare > /dev/null 2>&1
green "设置成功，选择主菜单9进行节点配置更新" && sleep 2 && vmesscfadd
else
changeserv
fi
}

gitlabsub(){
(
umask 077
echo
green "请确保Gitlab官网上已建立项目，已开启推送功能，已获取访问令牌"
yellow "1：重置/设置Gitlab订阅链接"
yellow "0：返回上层"
readp "请选择【0-1】：" menu
if [ "$menu" = "1" ]; then
sbshare > /dev/null || { red "导出刷新失败，未设置远端订阅。"; return 1; }
cd /etc/s-box || return 1
readp "输入登录邮箱: " email
readp "输入访问令牌: " token
readp "输入用户名: " userid
readp "输入项目名: " project
echo
green "多台VPS共用一个令牌及项目名，可创建多个分支订阅链接"
green "回车跳过表示不新建，仅使用主分支main订阅链接(首台VPS建议回车跳过)"
readp "新建分支名称: " gitlabml
local backup file setup_done=0 setup_changing=0
local -a setup_files=(.git gitlab_ml_ml gitlabtoken.txt gitpush.sh sing_box_gitlab.txt clash_meta_gitlab.txt jh_sub_gitlab.txt)
backup=$(mktemp -d /etc/s-box/gitlab-setup.bak.XXXXXX) || return 1
for file in "${setup_files[@]}"; do
[[ ! -e /etc/s-box/$file ]] || cp -a "/etc/s-box/$file" "$backup/$file" || return 1
done
trap 'if [[ $setup_changing == 1 && $setup_done == 0 ]]; then
for file in "${setup_files[@]}"; do
rm -rf "/etc/s-box/$file"
[[ ! -e $backup/$file ]] || cp -a "$backup/$file" "/etc/s-box/$file" || echo "Gitlab设置恢复失败：$file；备份：$backup" >&2
done
fi' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
setup_changing=1
echo
if [[ -z "$gitlabml" ]]; then
gitlab_ml=''
git_sk=main
rm -rf /etc/s-box/gitlab_ml_ml
else
gitlab_ml=":${gitlabml}"
git_sk="${gitlabml}"
echo "${gitlab_ml}" > /etc/s-box/gitlab_ml_ml
fi
[[ $userid =~ ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$ && $project =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]] || { red "用户名/项目名格式无效。"; return 1; }
git check-ref-format "refs/heads/$git_sk" >/dev/null || { red "分支名称无效。"; return 1; }
(umask 077; printf '%s\n' "$token" > /etc/s-box/gitlabtoken.txt) && chmod 600 /etc/s-box/gitlabtoken.txt || return 1
rm -rf /etc/s-box/.git
git init >/dev/null 2>&1 || return 1
git add sbox.json clmi.yaml jhsub.txt >/dev/null 2>&1 || return 1
git config user.email "${email}" >/dev/null 2>&1 || return 1
git config user.name "${userid}" >/dev/null 2>&1 || return 1
git commit -m "commit_add_$(date +"%F %T")" >/dev/null 2>&1 || return 1
branches=$(git branch)
if [[ $branches == *master* ]]; then
git branch -m master main >/dev/null 2>&1 || return 1
fi
git remote add origin "https://gitlab.com/${userid}/${project}.git" >/dev/null 2>&1 || return 1
if [[ $(ls -a | grep '^\.git$') ]]; then
gitlab_push || { red "Gitlab推送失败，未完成订阅设置。已有远端分支不会被强制覆盖，请检查权限或改用新分支。"; return 1; }
rm -f /etc/s-box/gitpush.sh
local encoded_project encoded_ref encoded_token
encoded_project=$(jq -nr --arg v "$userid/$project" '$v|@uri') || return 1
encoded_ref=$(jq -nr --arg v "$git_sk" '$v|@uri') || return 1
encoded_token=$(set -o pipefail; printf '%s' "$token" | jq -sRr @uri) || return 1
echo "https://gitlab.com/api/v4/projects/${encoded_project}/repository/files/sbox.json/raw?ref=${encoded_ref}&private_token=${encoded_token}" > /etc/s-box/sing_box_gitlab.txt || return 1
echo "https://gitlab.com/api/v4/projects/${encoded_project}/repository/files/clmi.yaml/raw?ref=${encoded_ref}&private_token=${encoded_token}" > /etc/s-box/clash_meta_gitlab.txt || return 1
echo "https://gitlab.com/api/v4/projects/${encoded_project}/repository/files/jhsub.txt/raw?ref=${encoded_ref}&private_token=${encoded_token}" > /etc/s-box/jh_sub_gitlab.txt || return 1
setup_done=1
green "旧Gitlab设置备份：$backup"
clsbshow
else
yellow "设置Gitlab订阅链接失败，请反馈"
fi
cd
else
changeserv
fi
)
}

gitlab_push(){
(
umask 077
local branch=main askpass remote
if [[ -f /etc/s-box/gitlab_ml_ml ]]; then branch=$(cat /etc/s-box/gitlab_ml_ml) || exit 1; branch=${branch#:}; fi
git check-ref-format "refs/heads/$branch" >/dev/null || exit 1
[[ -s /etc/s-box/gitlabtoken.txt ]] || { red "缺少Gitlab令牌文件。" >&2; exit 1; }
chmod 600 /etc/s-box/gitlabtoken.txt || exit 1
remote=$(git remote get-url origin) || exit 1
# Migrate old URLs containing the token; do not send credentials to arbitrary hosts.
[[ $remote == https://gitlab.com/* || $remote == https://*@gitlab.com/* ]] || { red "只允许HTTPS Gitlab远端。" >&2; exit 1; }
git remote set-url origin "https://gitlab.com/${remote#*gitlab.com/}" || exit 1
askpass=$(mktemp /etc/s-box/git-askpass.XXXXXX) || exit 1
trap 'rm -f "$askpass"' EXIT
cat > "$askpass" <<'GITLAB_ASKPASS' || exit 1
#!/bin/sh
case "$1" in
*sername*) printf '%s\n' oauth2 ;;
*assword*) cat "$SB_GIT_TOKEN_FILE" ;;
*) exit 1 ;;
esac
GITLAB_ASKPASS
chmod 700 "$askpass" || exit 1
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="$askpass" SB_GIT_TOKEN_FILE=/etc/s-box/gitlabtoken.txt \
git -c credential.helper= push origin "HEAD:refs/heads/$branch"
)
}

gitlabsubgo(){
(
cd /etc/s-box || exit 1
[[ -d .git ]] || { yellow "未设置Gitlab订阅链接"; exit 1; }
git add -- sbox.json clmi.yaml jhsub.txt || { red "Git暂存失败，未推送。"; exit 1; }
git diff --cached --quiet --exit-code
local changed=$?
if [[ $changed == 1 ]]; then
git commit -m "update_nodes_$(date +"%F %T")" || { red "Git提交失败，未推送。"; exit 1; }
elif [[ $changed != 0 ]]; then red "Git差异检查失败，未推送。"; exit 1; fi
gitlab_push || { red "Gitlab推送失败，远端未确认更新；请检查网络、权限或分支冲突后重试。"; exit 1; }
clsbshow
)
}

clsbshow(){
green "当前Sing-box节点已更新并推送"
green "Sing-box订阅链接如下："
blue "$(cat /etc/s-box/sing_box_gitlab.txt 2>/dev/null)"
echo
green "Sing-box订阅链接二维码如下："
qrencode -o - -t ANSIUTF8 < /etc/s-box/sing_box_gitlab.txt
echo
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
green "当前Mihomo节点配置已更新并推送"
green "Mihomo订阅链接如下："
blue "$(cat /etc/s-box/clash_meta_gitlab.txt 2>/dev/null)"
echo
green "Mihomo订阅链接二维码如下："
qrencode -o - -t ANSIUTF8 < /etc/s-box/clash_meta_gitlab.txt
echo
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
green "当前聚合节点配置已更新并推送"
green "订阅链接如下："
blue "$(cat /etc/s-box/jh_sub_gitlab.txt 2>/dev/null)"
echo
yellow "可以在网页上输入订阅链接查看配置内容，如果无配置内容，请自检Gitlab相关设置并重置"
echo
}

warpwg(){
warpcode(){
reg(){
keypair=$(openssl genpkey -algorithm X25519 | openssl pkey -text -noout)
private_key=$(echo "$keypair" | awk '/priv:/{flag=1; next} /pub:/{flag=0} flag' | tr -d '[:space:]' | xxd -r -p | base64)
public_key=$(echo "$keypair" | awk '/pub:/{flag=1} flag' | tr -d '[:space:]' | xxd -r -p | base64)
response=$(curl -sL --tlsv1.3 --connect-timeout 3 --max-time 5 \
-X POST 'https://api.cloudflareclient.com/v0a2158/reg' \
-H 'CF-Client-Version: a-7.21-0721' \
-H 'Content-Type: application/json' \
-d '{
"key": "'"$public_key"'",
"tos": "'"$(date -u +'%Y-%m-%dT%H:%M:%S.000Z')"'"
}')
if [ -z "$response" ]; then
return 1
fi
echo "$response" | python3 -m json.tool 2>/dev/null | sed "/\"account_type\"/i\         \"private_key\": \"$private_key\","
}
reserved(){
reserved_str=$(echo "$warp_info" | grep 'client_id' | cut -d\" -f4)
reserved_hex=$(echo "$reserved_str" | base64 -d | xxd -p)
reserved_dec=$(echo "$reserved_hex" | fold -w2 | while read HEX; do printf '%d ' "0x${HEX}"; done | awk '{print "["$1", "$2", "$3"]"}')
echo -e "{\n    \"reserved_dec\": $reserved_dec,"
echo -e "    \"reserved_hex\": \"0x$reserved_hex\","
echo -e "    \"reserved_str\": \"$reserved_str\"\n}"
}
result() {
echo "$warp_reserved" | grep -P "reserved" | sed "s/ //g" | sed 's/:"/: "/g' | sed 's/:\[/: \[/g' | sed 's/\([0-9]\+\),\([0-9]\+\),\([0-9]\+\)/\1, \2, \3/' | sed 's/^"/    "/g' | sed 's/"$/",/g'
echo "$warp_info" | grep -P "(private_key|public_key|\"v4\": \"172.16.0.2\"|\"v6\": \"2)" | sed "s/ //g" | sed 's/:"/: "/g' | sed 's/^"/    "/g'
echo "}"
}
warp_info=$(reg) 
warp_reserved=$(reserved) 
result
}
output=$(warpcode)
if ! echo "$output" 2>/dev/null | grep -w "private_key" > /dev/null; then
v6=2606:4700:110:860e:738f:b37:f15:d38d
pvk=g9I2sgUH6OCbIBTehkEfVEnuvInHYZvPOFhWchMLSc4=
res=[33,217,129]
else
pvk=$(echo "$output" | sed -n 4p | awk '{print $2}' | tr -d ' "' | sed 's/.$//')
v6=$(echo "$output" | sed -n 7p | awk '{print $2}' | tr -d ' "')
res=$(echo "$output" | sed -n 1p | awk -F":" '{print $NF}' | tr -d ' ' | sed 's/.$//')
fi
blue "Private_key私钥：$pvk"
blue "IPV6地址：$v6"
blue "reserved值：$res"
}

changewg(){
[[ "$sbnh" == "1.10" ]] && num=10 || num=11
if [[ "$sbnh" == "1.10" ]]; then
wgipv6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.outbounds[] | select(.type == "wireguard") | .local_address[1] | split("/")[0]')
wgprkey=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.outbounds[] | select(.type == "wireguard") | .private_key')
wgres=$(sed -n '165s/.*\[\(.*\)\].*/\1/p' /etc/s-box/sb.json)
wgip=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.outbounds[] | select(.type == "wireguard") | .server')
wgpo=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.outbounds[] | select(.type == "wireguard") | .server_port')
else
wgipv6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.endpoints[] | .address[1] | split("/")[0]')
wgprkey=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.endpoints[] | .private_key')
wgres=$(sed -n '142s/.*\[\(.*\)\].*/\1/p' /etc/s-box/sb.json)
wgip=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.endpoints[] | .peers[].address')
wgpo=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.endpoints[] | .peers[].port')
fi
echo
green "当前warp-wireguard可更换的参数如下："
green "Private_key私钥：$wgprkey"
green "IPV6地址：$wgipv6"
green "Reserved值：$wgres"
green "对端IP：$wgip:$wgpo"
echo
yellow "1：更换warp-wireguard账户"
yellow "0：返回上层"
readp "请选择【0-1】：" menu
if [ "$menu" = "1" ]; then
green "最新随机生成普通warp-wireguard账户如下"
warpwg
echo
readp "输入自定义Private_key：" menu
sed -i "163s#$wgprkey#$menu#g" /etc/s-box/sb10.json
sed -i "132s#$wgprkey#$menu#g" /etc/s-box/sb11.json
readp "输入自定义IPV6地址：" menu
sed -i "161s/$wgipv6/$menu/g" /etc/s-box/sb10.json
sed -i "130s/$wgipv6/$menu/g" /etc/s-box/sb11.json
readp "输入自定义Reserved值 (格式：数字,数字,数字)，如无值则回车跳过：" menu
if [ -z "$menu" ]; then
menu=0,0,0
fi
sed -i "165s/$wgres/$menu/g" /etc/s-box/sb10.json
sed -i "142s/$wgres/$menu/g" /etc/s-box/sb11.json
rm -rf /etc/s-box/sb.json
cp /etc/s-box/sb${num}.json /etc/s-box/sb.json
restartsb
green "设置结束"
else
changeserv
fi
}

sbymfl(){
sbport=$(cat /etc/s-box/sbwpph.log 2>/dev/null | awk '{print $3}' | awk -F":" '{print $NF}') 
sbport=${sbport:-'40000'}
resv1=$(curl -sm3 --socks5 localhost:$sbport icanhazip.com)
resv2=$(curl -sm3 -x socks5h://localhost:$sbport icanhazip.com)
if [[ -z $resv1 && -z $resv2 ]]; then
warp_s4_ip='Socks5-IPV4未启动，黑名单模式'
warp_s6_ip='Socks5-IPV6未启动，黑名单模式'
else
warp_s4_ip='Socks5-IPV4可用'
warp_s6_ip='Socks5-IPV6自测'
fi
v4v6
if [[ -z $v4 ]]; then
vps_ipv4='无本地IPV4，黑名单模式'      
vps_ipv6="当前IP：$v6"
elif [[ -n $v4 &&  -n $v6 ]]; then
vps_ipv4="当前IP：$v4"    
vps_ipv6="当前IP：$v6"
else
vps_ipv4="当前IP：$v4"    
vps_ipv6='无本地IPV6，黑名单模式'
fi
unset swg4 swd4 swd6 swg6 ssd4 ssg4 ssd6 ssg6 sad4 sag4 sad6 sag6
wd4=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[1].domain_suffix | join(" ")')
wg4=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[1].geosite | join(" ")' 2>/dev/null)
if [[ "$wd4" == "yg_kkk" && ("$wg4" == "yg_kkk" || -z "$wg4") ]]; then
wfl4="${yellow}【warp出站IPV4可用】未分流${plain}"
else
if [[ "$wd4" != "yg_kkk" ]]; then
swd4="$wd4 "
fi
if [[ "$wg4" != "yg_kkk" ]]; then
swg4=$wg4
fi
wfl4="${yellow}【warp出站IPV4可用】已分流：$swd4$swg4${plain} "
fi

wd6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[2].domain_suffix | join(" ")')
wg6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[2].geosite | join(" ")' 2>/dev/null)
if [[ "$wd6" == "yg_kkk" && ("$wg6" == "yg_kkk"|| -z "$wg6") ]]; then
wfl6="${yellow}【warp出站IPV6自测】未分流${plain}"
else
if [[ "$wd6" != "yg_kkk" ]]; then
swd6="$wd6 "
fi
if [[ "$wg6" != "yg_kkk" ]]; then
swg6=$wg6
fi
wfl6="${yellow}【warp出站IPV6自测】已分流：$swd6$swg6${plain} "
fi

sd4=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[3].domain_suffix | join(" ")')
sg4=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[3].geosite | join(" ")' 2>/dev/null)
if [[ "$sd4" == "yg_kkk" && ("$sg4" == "yg_kkk" || -z "$sg4") ]]; then
sfl4="${yellow}【$warp_s4_ip】未分流${plain}"
else
if [[ "$sd4" != "yg_kkk" ]]; then
ssd4="$sd4 "
fi
if [[ "$sg4" != "yg_kkk" ]]; then
ssg4=$sg4
fi
sfl4="${yellow}【$warp_s4_ip】已分流：$ssd4$ssg4${plain} "
fi

sd6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[4].domain_suffix | join(" ")')
sg6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[4].geosite | join(" ")' 2>/dev/null)
if [[ "$sd6" == "yg_kkk" && ("$sg6" == "yg_kkk" || -z "$sg6") ]]; then
sfl6="${yellow}【$warp_s6_ip】未分流${plain}"
else
if [[ "$sd6" != "yg_kkk" ]]; then
ssd6="$sd6 "
fi
if [[ "$sg6" != "yg_kkk" ]]; then
ssg6=$sg6
fi
sfl6="${yellow}【$warp_s6_ip】已分流：$ssd6$ssg6${plain} "
fi

ad4=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[5].domain_suffix | join(" ")' 2>/dev/null)
ag4=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[5].geosite | join(" ")' 2>/dev/null)
if [[ ("$ad4" == "yg_kkk" || -z "$ad4") && ("$ag4" == "yg_kkk" || -z "$ag4") ]]; then
adfl4="${yellow}【$vps_ipv4】未分流${plain}" 
else
if [[ "$ad4" != "yg_kkk" ]]; then
sad4="$ad4 "
fi
if [[ "$ag4" != "yg_kkk" ]]; then
sag4=$ag4
fi
adfl4="${yellow}【$vps_ipv4】已分流：$sad4$sag4${plain} "
fi

ad6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[6].domain_suffix | join(" ")' 2>/dev/null)
ag6=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.route.rules[6].geosite | join(" ")' 2>/dev/null)
if [[ ("$ad6" == "yg_kkk" || -z "$ad6") && ("$ag6" == "yg_kkk" || -z "$ag6") ]]; then
adfl6="${yellow}【$vps_ipv6】未分流${plain}" 
else
if [[ "$ad6" != "yg_kkk" ]]; then
sad6="$ad6 "
fi
if [[ "$ag6" != "yg_kkk" ]]; then
sag6=$ag6
fi
adfl6="${yellow}【$vps_ipv6】已分流：$sad6$sag6${plain} "
fi
}

changefl(){
sbactive
blue "对所有协议进行统一的域名分流"
blue "为确保分流可用，双栈IP（IPV4/IPV6）分流模式为优先模式"
blue "warp-wireguard默认开启 (选项1与2)"
blue "socks5需要在VPS安装warp官方客户端或者WARP-plus-Socks5-赛风VPN (选项3与4)"
blue "VPS本地出站分流(选项5与6)"
echo
[[ "$sbnh" == "1.10" ]] && blue "当前Sing-box内核支持geosite分流方式" || blue "当前Sing-box内核不支持geosite分流方式，仅支持分流2、3、5、6选项"
echo
yellow "注意："
yellow "一、后缀域名方式只能填域名 (例：谷歌网站填写：google.com googleapis.com)"
yellow "二、geosite方式须填写geosite规则名 (例：奈飞填写netflix ；迪士尼填写disney ；ChatGPT填写openai ；全局且绕过中国填写geolocation-!cn)"
yellow "三、同一个完整域名或者geosite切勿重复分流"
yellow "四、如分流通道中有个别通道无网络，所填分流为黑名单模式，即屏蔽该网站访问"
changef
}

changef(){
[[ "$sbnh" == "1.10" ]] && num=10 || num=11
sbymfl
echo
[[ "$sbnh" != "1.10" ]] && wfl4='暂不支持' sfl6='暂不支持' adfl4='暂不支持' adfl6='暂不支持'
green "1：重置warp-wireguard-ipv4优先分流域名 $wfl4"
green "2：重置warp-wireguard-ipv6优先分流域名 $wfl6"
green "3：重置warp-socks5-ipv4优先分流域名 $sfl4"
green "4：重置warp-socks5-ipv6优先分流域名 $sfl6"
green "5：重置VPS本地ipv4优先分流域名 $adfl4"
green "6：重置VPS本地ipv6优先分流域名 $adfl6"
green "0：返回上层"
echo
readp "请选择：" menu

if [ "$menu" = "1" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "1：使用后缀域名方式\n2：使用geosite方式\n3：返回上层\n请选择：" menu
if [ "$menu" = "1" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-wireguard-ipv4的后缀域名方式的分流通道)：" w4flym
if [ -z "$w4flym" ]; then
w4flym='"yg_kkk"'
else
w4flym="$(echo "$w4flym" | sed 's/ /","/g')"
w4flym="\"$w4flym\""
fi
sed -i "184s/.*/$w4flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
elif [ "$menu" = "2" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-wireguard-ipv4的geosite方式的分流通道)：" w4flym
if [ -z "$w4flym" ]; then
w4flym='"yg_kkk"'
else
w4flym="$(echo "$w4flym" | sed 's/ /","/g')"
w4flym="\"$w4flym\""
fi
sed -i "187s/.*/$w4flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
else
changef
fi
else
yellow "遗憾！当前暂时只支持warp-wireguard-ipv6，如需要warp-wireguard-ipv4，请切换1.10系列内核" && exit
fi

elif [ "$menu" = "2" ]; then
readp "1：使用后缀域名方式\n2：使用geosite方式\n3：返回上层\n请选择：" menu
if [ "$menu" = "1" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-wireguard-ipv6的后缀域名方式的分流通道：" w6flym
if [ -z "$w6flym" ]; then
w6flym='"yg_kkk"'
else
w6flym="$(echo "$w6flym" | sed 's/ /","/g')"
w6flym="\"$w6flym\""
fi
sed -i "193s/.*/$w6flym/" /etc/s-box/sb10.json
sed -i "184s/.*/$w6flym/" /etc/s-box/sb11.json
sed -i "196s/.*/$w6flym/" /etc/s-box/sb11.json
cp /etc/s-box/sb${num}.json /etc/s-box/sb.json
restartsb
changef
elif [ "$menu" = "2" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-wireguard-ipv6的geosite方式的分流通道：" w6flym
if [ -z "$w6flym" ]; then
w6flym='"yg_kkk"'
else
w6flym="$(echo "$w6flym" | sed 's/ /","/g')"
w6flym="\"$w6flym\""
fi
sed -i "196s/.*/$w6flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
else
yellow "遗憾！当前Sing-box内核不支持geosite分流方式。如要支持，请切换1.10系列内核" && exit
fi
else
changef
fi

elif [ "$menu" = "3" ]; then
readp "1：使用后缀域名方式\n2：使用geosite方式\n3：返回上层\n请选择：" menu
if [ "$menu" = "1" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-socks5-ipv4的后缀域名方式的分流通道：" s4flym
if [ -z "$s4flym" ]; then
s4flym='"yg_kkk"'
else
s4flym="$(echo "$s4flym" | sed 's/ /","/g')"
s4flym="\"$s4flym\""
fi
sed -i "202s/.*/$s4flym/" /etc/s-box/sb10.json
sed -i "177s/.*/$s4flym/" /etc/s-box/sb11.json
sed -i "190s/.*/$s4flym/" /etc/s-box/sb11.json
cp /etc/s-box/sb${num}.json /etc/s-box/sb.json
restartsb
changef
elif [ "$menu" = "2" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-socks5-ipv4的geosite方式的分流通道：" s4flym
if [ -z "$s4flym" ]; then
s4flym='"yg_kkk"'
else
s4flym="$(echo "$s4flym" | sed 's/ /","/g')"
s4flym="\"$s4flym\""
fi
sed -i "205s/.*/$s4flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
else
yellow "遗憾！当前Sing-box内核不支持geosite分流方式。如要支持，请切换1.10系列内核" && exit
fi
else
changef
fi

elif [ "$menu" = "4" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "1：使用后缀域名方式\n2：使用geosite方式\n3：返回上层\n请选择：" menu
if [ "$menu" = "1" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-socks5-ipv6的后缀域名方式的分流通道：" s6flym
if [ -z "$s6flym" ]; then
s6flym='"yg_kkk"'
else
s6flym="$(echo "$s6flym" | sed 's/ /","/g')"
s6flym="\"$s6flym\""
fi
sed -i "211s/.*/$s6flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
elif [ "$menu" = "2" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空warp-socks5-ipv6的geosite方式的分流通道：" s6flym
if [ -z "$s6flym" ]; then
s6flym='"yg_kkk"'
else
s6flym="$(echo "$s6flym" | sed 's/ /","/g')"
s6flym="\"$s6flym\""
fi
sed -i "214s/.*/$s6flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
else
changef
fi
else
yellow "遗憾！当前暂时只支持warp-socks5-ipv4，如需要warp-socks5-ipv6，请切换1.10系列内核" && exit
fi

elif [ "$menu" = "5" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "1：使用后缀域名方式\n2：使用geosite方式\n3：返回上层\n请选择：" menu
if [ "$menu" = "1" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空VPS本地ipv4的后缀域名方式的分流通道：" ad4flym
if [ -z "$ad4flym" ]; then
ad4flym='"yg_kkk"'
else
ad4flym="$(echo "$ad4flym" | sed 's/ /","/g')"
ad4flym="\"$ad4flym\""
fi
sed -i "220s/.*/$ad4flym/" /etc/s-box/sb10.json /etc/s-box/sb.json
restartsb
changef
elif [ "$menu" = "2" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "每个域名之间留空格，回车跳过表示重置清空VPS本地ipv4的geosite方式的分流通道：" ad4flym
if [ -z "$ad4flym" ]; then
ad4flym='"yg_kkk"'
else
ad4flym="$(echo "$ad4flym" | sed 's/ /","/g')"
ad4flym="\"$ad4flym\""
fi
sed -i "223s/.*/$ad4flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
else
yellow "遗憾！当前Sing-box内核不支持geosite分流方式。如要支持，请切换1.10系列内核" && exit
fi
else
changef
fi
else
yellow "遗憾！如需要VPS本地ipv4分流，请切换1.10系列内核" && exit
fi

elif [ "$menu" = "6" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "1：使用后缀域名方式\n2：使用geosite方式\n3：返回上层\n请选择：" menu
if [ "$menu" = "1" ]; then
readp "每个域名之间留空格，回车跳过表示重置清空VPS本地ipv6的后缀域名方式的分流通道：" ad6flym
if [ -z "$ad6flym" ]; then
ad6flym='"yg_kkk"'
else
ad6flym="$(echo "$ad6flym" | sed 's/ /","/g')"
ad6flym="\"$ad6flym\""
fi
sed -i "229s/.*/$ad6flym/" /etc/s-box/sb10.json /etc/s-box/sb.json
restartsb
changef
elif [ "$menu" = "2" ]; then
if [[ "$sbnh" == "1.10" ]]; then
readp "每个域名之间留空格，回车跳过表示重置清空VPS本地ipv6的geosite方式的分流通道：" ad6flym
if [ -z "$ad6flym" ]; then
ad6flym='"yg_kkk"'
else
ad6flym="$(echo "$ad6flym" | sed 's/ /","/g')"
ad6flym="\"$ad6flym\""
fi
sed -i "232s/.*/$ad6flym/" /etc/s-box/sb.json /etc/s-box/sb10.json
restartsb
changef
else
yellow "遗憾！当前Sing-box内核不支持geosite分流方式。如要支持，请切换1.10系列内核" && exit
fi
else
changef
fi
else
yellow "遗憾！如需要VPS本地ipv6分流，请切换1.10系列内核" && exit
fi
else
sb
fi
}

restartsb(){
sb_config_check || return 1
if command -v apk >/dev/null 2>&1; then
rc-service sing-box restart || return 1
else
systemctl restart sing-box || return 1
fi
sleep 1
sb_update_service_active || { red "Sing-box服务未运行，请查看日志。" >&2; return 1; }
}

stclre(){
if [[ ! -f '/etc/s-box/sb.json' ]]; then
red "未正常安装Sing-box" && exit
fi
readp "1：重启\n2：关闭\n请选择：" menu
if [ "$menu" = "1" ]; then
restartsb || { red "重启失败，未确认服务运行；请查看日志。"; return 1; }
sbactive
green "Sing-box服务已重启\n" && sleep 3 && sb
elif [ "$menu" = "2" ]; then
if command -v apk >/dev/null 2>&1; then
rc-service sing-box stop || return 1
else
systemctl stop sing-box && systemctl disable sing-box || return 1
fi
green "Sing-box服务已关闭\n" && sleep 3 && sb
else
stclre
fi
}

cronsb(){
sb_cron_update restart '0 1 * * * systemctl restart sing-box;rc-service sing-box restart'
}
uncronsb(){
sb_cron_update all
}

# Read newest-first release sections; display only (installed, latest].
sb_update_log(){
awk -v installed="$1" -v latest="$2" '
function clean(v) {
    sub(/^[ \t\r\n]+/, "", v)
    sub(/[ \t\r\n]+$/, "", v)
    return v
}
function valid(v) {
    return v ~ /^v[0-9]+\.[0-9]+\.[0-9]+(-fork\.[0-9]+)?$/
}
function newer(a, b, left, right, i) {
    sub(/^v/, "", a); sub(/-fork\./, ".", a)
    sub(/^v/, "", b); sub(/-fork\./, ".", b)
    split(a, left, "."); split(b, right, ".")
    for (i = 1; i <= 4; i++) {
        if (left[i] + 0 != right[i] + 0) return left[i] + 0 > right[i] + 0
    }
    return 0
}
BEGIN {
    installed = clean(installed); latest = clean(latest)
    if (!valid(latest)) exit
    known = valid(installed)
    if (!known) {
        print "无法识别当前脚本版本，仅显示最新版本更新日志。"
        printed = 1; blank = 1
    }
}
{
    sub(/\r$/, "")
    if ($0 ~ /^v[^ \t\r\n]+更新内容/) {
        entry = $0; sub(/更新内容.*/, "", entry)
        show = valid(entry) && !newer(entry, latest) && (known ? newer(entry, installed) : entry == latest)
        if (show && printed) blank = 1
    }
    if (!show || $0 ~ /^历史版本(：|:)[ \t\r\n]*$/) next
    if ($0 ~ /^[ \t\r\n]*$/) { if (printed) blank = 1; next }
    if (printed && blank) print ""
    print
    printed = 1; blank = 0
}'
}

# Compare versions independently of release-note parsing (including old awk).
# Output: 1 = left newer, 0 = equal, -1 = left older; invalid input fails.
sb_version_compare(){
local value i j
local -a left right
for j in 0 1; do
if (( j == 0 )); then value=$1; else value=$2; fi
[[ $value =~ ^[[:space:]]*v([0-9]+)\.([0-9]+)\.([0-9]+)(-fork\.([0-9]+))?[[:space:]]*$ ]] || return 1
local -a parts=("${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[5]:-0}")
# Bound arithmetic input; release components are small decimal integers.
for value in "${parts[@]}"; do [[ ${#value} -le 9 ]] || return 1; done
if (( j == 0 )); then left=("${parts[@]}"); else right=("${parts[@]}"); fi
done
for i in 0 1 2 3; do
if (( 10#${left[i]} > 10#${right[i]} )); then printf '1\n'; return 0; fi
if (( 10#${left[i]} < 10#${right[i]} )); then printf '%s\n' -1; return 0; fi
done
printf '0\n'
}

sb_update_notice(){
local insV=${1:-} latestV version_info updates comparison
# One response supplies both the version and its notes, avoiding mixed revisions.
version_info=$(sb_script_version_info 2>/dev/null) || version_info=
latestV=
if [[ $version_info =~ ^(v[0-9]+\.[0-9]+\.[0-9]+(-fork\.[0-9]+)?)更新内容 ]]; then
latestV=${BASH_REMATCH[1]}
fi
if [[ ! -f /etc/s-box/v ]]; then
echo -e "当前 Sing-box-yg 脚本版本号：${bblue}${latestV:-（暂时无法获取）}${plain}"
yellow "未安装 Sing-box-yg 脚本！请先选择 1 安装"
elif [[ -z $latestV ]]; then
echo -e "当前 Sing-box-yg 脚本版本号：${bblue}${insV}${plain}"
yellow "暂时无法检查脚本更新，请稍后重试。"
elif [[ $(sb_version_compare "$insV" "$latestV") == 0 ]]; then
echo -e "当前 Sing-box-yg 脚本最新版：${bblue}${insV}${plain} (已安装)"
else
updates=$(printf '%s\n' "$version_info" | sb_update_log "$insV" "$latestV")
echo -e "当前 Sing-box-yg 脚本版本号：${bblue}${insV}${plain}"
comparison=$(sb_version_compare "$insV" "$latestV") || comparison=unknown
if [[ $comparison == -1 || $comparison == unknown ]]; then
echo -e "检测到最新 Sing-box-yg 脚本版本号：${yellow}${latestV}${plain} (可选择7进行更新)"
if [[ -n $updates ]]; then
printf '%b%s%b\n' "$yellow" "$updates" "$plain"
else
yellow "更新日志暂时无法解析；版本比较独立生效，可选择7更新。"
fi
else
echo -e "线上最新 Sing-box-yg 脚本版本号：${bblue}${latestV}${plain} (当前版本不低于线上版本，无可用更新)"
fi
fi
}

# Updates never download over the live file. SHA256 records detect local damage;
# they are not a publisher signature (old upstream releases have no digest asset).
sb_update_download(){
curl --fail --show-error --silent --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
--connect-timeout 10 --max-time 180 --retry 2 --output "$2" "$1" && [[ -s $2 ]]
}

sb_update_backup(){
local kind=$1 backup path name
shift
mkdir -p /etc/s-box/backups || return 1
backup=$(mktemp -d "/etc/s-box/backups/${kind}.$(date +%Y%m%d-%H%M%S).XXXXXX") || return 1
chmod 700 "$backup" || return 1
: > "$backup/SHA256SUMS" || return 1
for path in "$@"; do
name=${path##*/}
if [[ -f $path ]]; then
cp -p -- "$path" "$backup/$name" || return 1
(cd "$backup" && sha256sum -- "$name") >> "$backup/SHA256SUMS" || return 1
fi
done
printf '%s\n' "$backup"
}

sb_update_restore(){
local backup=$1 path name tmp failed=0
shift
[[ -f $backup/SHA256SUMS ]] || return 1
if [[ -s $backup/SHA256SUMS ]]; then
(cd "$backup" && sha256sum -c SHA256SUMS) >&2 || return 1
fi
for path in "$@"; do
name=${path##*/}
if [[ -f $backup/$name ]]; then
tmp=$(mktemp "${path}.restore.XXXXXX") || { failed=1; continue; }
if ! cp -p -- "$backup/$name" "$tmp" || ! mv -f -- "$tmp" "$path"; then
rm -f -- "$tmp"
failed=1
fi
else
rm -f -- "$path" || failed=1
fi
done
return "$failed"
}

sb_update_service_active(){
if command -v apk >/dev/null 2>&1; then
rc-service sing-box status >/dev/null 2>&1
else
systemctl is-active --quiet sing-box
fi
}

sb_update_core_stage(){
local version=$1 stage=$2 name="sing-box-$1-linux-$cpu" actual listing
if [[ ! $version =~ ^1\.([0-9]+)\.[0-9]+(-(alpha|beta|rc)\.[0-9]+)?$ ]] || (( 10#${BASH_REMATCH[1]:-0} < 10 )); then
red "无效或不支持的内核版本：$version（要求1.10及以上）" >&2
return 1
fi
sb_update_download "https://github.com/SagerNet/sing-box/releases/download/v$version/$name.tar.gz" "$stage/core.tar.gz" || {
red "内核下载失败，保留现有内核及配置。" >&2; return 1;
}
# Extract only the exact regular-file member to stdout, never archive paths to disk.
listing=$(tar -tvzf "$stage/core.tar.gz" "$name/sing-box") || return 1
[[ $listing == -* ]] || { red "内核压缩包缺少常规二进制文件。" >&2; return 1; }
tar -xOzf "$stage/core.tar.gz" "$name/sing-box" > "$stage/sing-box" || return 1
[[ -s $stage/sing-box ]] && chmod 755 "$stage/sing-box" || return 1
actual=$("$stage/sing-box" version) || { red "新内核无法执行。" >&2; return 1; }
actual=$(printf '%s\n' "$actual" | awk '$1 == "sing-box" && $2 == "version" {print $3; exit}')
[[ $actual == "$version" ]] || { red "内核版本不匹配：要求 $version，实际 ${actual:-未知}。" >&2; return 1; }
(cd "$stage" && sha256sum core.tar.gz sing-box > NEW-SHA256SUMS) || return 1
}

sb_update_core(){
(
umask 077
local version=$1 mode=${2:-update} stage backup current oldtrack=11 newtrack=11 changed=0 complete=0
stage=$(mktemp -d /etc/s-box/.core-update.XXXXXX) || return 1
trap 'if [[ $changed == 1 && $complete == 0 ]]; then
  if sb_update_restore "$backup" /etc/s-box/sing-box /etc/s-box/sb.json /etc/s-box/sb10.json /etc/s-box/sb11.json; then
    if [[ $mode == update ]] && ! restartsb; then red "旧文件已恢复，但旧服务重启失败，请查看日志；备份：$backup" >&2;
    else red "更新失败，已恢复旧内核及配置；备份：$backup" >&2; fi
  else red "自动恢复失败，请保留现场并从备份恢复：$backup" >&2; fi
fi
rm -rf -- "$stage"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
sb_update_core_stage "$version" "$stage" || return 1
if [[ $mode == update ]]; then
[[ -f /etc/s-box/sb.json ]] || return 1
current=$(/etc/s-box/sing-box version) || return 1
current=$(printf '%s\n' "$current" | awk '$1 == "sing-box" && $2 == "version" {print $3; exit}')
[[ $current == 1.10.* ]] && oldtrack=10
[[ $version == 1.10.* ]] && newtrack=10
# Preserve the active configuration within one syntax family. A cross-family switch
# uses the existing maintained template; never regenerate/erase it on download failure.
if [[ $oldtrack == "$newtrack" ]]; then
cp -p /etc/s-box/sb.json "$stage/sb.json" || return 1
else
cp -p "/etc/s-box/sb${newtrack}.json" "$stage/sb.json" || return 1
fi
"$stage/sing-box" check -c "$stage/sb.json" || { red "新内核配置预检失败，未更改现有文件。" >&2; return 1; }
fi
backup=$(sb_update_backup core /etc/s-box/sing-box /etc/s-box/sb.json /etc/s-box/sb10.json /etc/s-box/sb11.json) || return 1
cp "$stage/NEW-SHA256SUMS" "$backup/NEW-SHA256SUMS" || return 1
# mv uses the same filesystem, so a running binary is never overwritten in place.
chown root:root "$stage/sing-box" || return 1
changed=1
mv -f -- "$stage/sing-box" /etc/s-box/sing-box || return 1
if [[ $mode == update ]]; then
mv -f -- "$stage/sb.json" /etc/s-box/sb.json || return 1
restartsb || { red "新内核启动验证失败，正在回滚。" >&2; return 1; }
fi
complete=1
blue "内核原版与配置备份（含SHA256）：$backup" >&2
)
}

lnsb(){
(
umask 077
local target=/usr/bin/sb staged version_file marker ref_file backup version revision changed=0 complete=0
staged=$(mktemp "${target}.update.XXXXXX") || return 1
version_file=$(mktemp /etc/s-box/.version-download.XXXXXX) || { rm -f "$staged"; return 1; }
marker=$(mktemp /etc/s-box/.version-update.XXXXXX) || { rm -f "$staged" "$version_file"; return 1; }
ref_file=$(mktemp /etc/s-box/.revision-download.XXXXXX) || { rm -f "$staged" "$version_file" "$marker"; return 1; }
trap 'if [[ $changed == 1 && $complete == 0 ]]; then
  sb_update_restore "$backup" "$target" /etc/s-box/v || red "脚本恢复失败，请从备份恢复：$backup" >&2
fi
rm -f -- "$staged" "$version_file" "$marker" "$ref_file"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
# Pin script and marker to one commit, so a concurrent upstream release cannot
# label an older downloaded script with a newer version.
sb_update_download https://api.github.com/repos/redrohu/sing-box-yg/git/ref/heads/main "$ref_file" || return 1
revision=$(jq -er '.object.sha | select(test("^[0-9a-f]{40}$"))' "$ref_file") || return 1
sb_update_download "https://raw.githubusercontent.com/redrohu/sing-box-yg/$revision/sb.sh" "$staged" || {
red "脚本下载失败，保留原脚本及版本标记。" >&2; return 1;
}
sb_update_download "https://raw.githubusercontent.com/redrohu/sing-box-yg/$revision/version" "$version_file" || {
red "版本信息下载失败，未替换脚本。" >&2; return 1;
}
[[ $(head -n 1 "$staged") == '#!/bin/bash' ]] && bash -n "$staged" || {
red "下载的脚本格式或语法校验失败，保留原脚本。" >&2; return 1;
}
IFS= read -r version < "$version_file" || return 1
if [[ $version =~ ^(v[0-9]+\.[0-9]+\.[0-9]+(-fork\.[0-9]+)?)更新内容 ]]; then
version=${BASH_REMATCH[1]}
else
red "下载的版本标记无效，未替换脚本。" >&2; return 1
fi
printf '%s\n' "$version" > "$marker" || return 1
chmod 755 "$staged" && chmod 644 "$marker" || return 1
backup=$(sb_update_backup script "$target" /etc/s-box/v) || return 1
sha256sum "$staged" "$marker" > "$backup/NEW-SHA256SUMS" || return 1
printf '%s\n' "$revision" > "$backup/NEW-REVISION" || return 1
changed=1
mv -f -- "$staged" "$target" && mv -f -- "$marker" /etc/s-box/v || return 1
complete=1
blue "脚本原版备份（含SHA256）：$backup" >&2
)
}

upsbyg(){
if [[ ! -f '/usr/bin/sb' ]]; then
red "未正常安装Sing-box-yg" >&2
return 1
fi
lnsb || return 1
green "Sing-box-yg安装脚本升级成功" && sleep 5 && sb
}

lapre(){
local data json page stable preview SB_MENU_REFRESH=${SB_MENU_REFRESH:-0}
[[ ${1:-} != refresh ]] || SB_MENU_REFRESH=1
if ! data=$(sb_info_cache_get cores 300); then
json=$(curl -fsSL --connect-timeout 2 --max-time 3 https://data.jsdelivr.com/v1/package/gh/SagerNet/sing-box)
stable=$(jq -r '[.versions[]?|select(test("^[0-9]+\\.[0-9]+\\.[0-9]+$"))][0] // empty' <<< "$json" 2>/dev/null)
preview=$(jq -r '[.versions[]?|select(test("^[0-9]+\\.[0-9]+\\.[0-9]+-(alpha|beta|rc)\\.[0-9]+$"))][0] // empty' <<< "$json" 2>/dev/null)
if [[ -z $stable || -z $preview ]]; then
page=$(curl -fsSL --connect-timeout 2 --max-time 3 https://github.com/SagerNet/sing-box/releases)
stable=$(printf '%s\n' "$page" | grep -oE 'tag/v[0-9.]+' | head -n1 | cut -d'v' -f2)
preview=$(printf '%s\n' "$page" | grep -oE '/tag/v[0-9.]+-(alpha|beta|rc)\.[0-9]+' | head -n1 | cut -d'v' -f2)
fi
data=$(jq -nc --arg stable "$stable" --arg preview "$preview" '{stable:$stable,preview:$preview}')
if printf '%s\n' "$data" | sb_info_valid cores; then printf '%s\n' "$data" | sb_info_cache_put cores || :
else data='{"stable":"","preview":""}'; fi
fi
latcore=$(jq -r .stable <<< "$data"); precore=$(jq -r .preview <<< "$data")
# Installed binary is always read live, never cached.
inscore=$(/etc/s-box/sing-box version 2>/dev/null | awk '/version/{print $NF}')
}

upsbcroe(){
local upcore menu lat= pre=
sbactive
lapre refresh
[[ $inscore =~ ^[0-9.]+$ ]] && lat="【已安装v$inscore】" || pre="【已安装v$inscore】"
green "1：升级/切换Sing-box最新正式版 v$latcore  ${bblue}${lat}${plain}"
green "2：升级/切换Sing-box最新测试版 v$precore  ${bblue}${pre}${plain}"
green "3：切换Sing-box某个正式版或测试版，需指定版本号 (建议1.10.0以上版本)"
green "0：返回上层"
readp "请选择【0-3】：" menu
if [ "$menu" = "1" ]; then
upcore=$latcore
elif [ "$menu" = "2" ]; then
upcore=$precore
elif [ "$menu" = "3" ]; then
echo
red "注意: 版本号在 https://github.com/SagerNet/sing-box/tags 可查，且有Downloads字样 (必须1.10及以上版本)"
green "正式版版本号格式：数字.数字.数字 (例：1.10.7   注意，1.10系列内核支持geosite分流，1.10以上内核不支持geosite分流"
green "测试版版本号格式：数字.数字.数字-alpha或rc或beta.数字 (例：1.13.0-alpha或rc或beta.1)"
readp "请输入Sing-box版本号：" upcore
else
sb
return
fi
if [[ -z $upcore ]]; then
red "版本号检测出错，请稍后重试。" >&2
return 1
fi
green "开始下载并核验Sing-box内核……请稍等"
sb_update_core "$upcore" update || return 1
sbnh=$(printf '%s\n' "$upcore" | cut -d '.' -f 1,2)
if ! sbshare; then
red "内核已更新并启动，但订阅刷新失败；请先修复配置后使用菜单9刷新。" >&2
return 1
fi
blue "成功升级/切换 Sing-box 内核版本：$upcore" && sleep 3 && sb
}

unins(){
# Preserve other applications' NAT/cron resources; abort on cleanup failure.
sb_port_hop_manage remove || { red "清理本项目端口转发失败，保留安装以便排查。"; return 1; }
uncronsb || return 1
argo_temporary_stop || return 1
if [[ -d /etc/s-box/xhttp-argo ]]; then xhttp_argo_remove || return 1; fi
if [[ -d /etc/s-box/xhttp ]]; then xhttp_remove || return 1; fi
if command -v apk >/dev/null 2>&1; then
for svc in sing-box argo; do
rc-service "$svc" stop >/dev/null 2>&1
rc-update del "$svc" default >/dev/null 2>&1
done
rm -rf /etc/init.d/{sing-box,argo}
else
for svc in sing-box argo; do
systemctl stop "$svc" >/dev/null 2>&1
systemctl disable "$svc" >/dev/null 2>&1
done
rm -rf /etc/systemd/system/{sing-box.service,argo.service}
fi
ps -ef | grep '[s]bwpph' | awk '{print $2}' | xargs kill 2>/dev/null
kill -15 $(pgrep -f 'websbox' 2>/dev/null) >/dev/null 2>&1
rm -rf /etc/s-box sbyg_update /usr/bin/sb /root/geoip.db /root/geosite.db /root/warpapi /root/warpip /root/websbox
rm -f /etc/local.d/alpineargo.start /etc/local.d/alpinesub.start /etc/local.d/alpinews5.start
netfilter-persistent save >/dev/null 2>&1
service iptables save >/dev/null 2>&1
green "Sing-box卸载完成！"
blue "欢迎继续使用Sing-box-yg脚本：bash <(curl -Ls https://raw.githubusercontent.com/redrohu/sing-box-yg/main/sb.sh)"
echo
}

sblog(){
red "退出日志 Ctrl+c"
if command -v apk >/dev/null 2>&1; then
yellow "暂不支持alpine查看日志"
else
#systemctl status sing-box
journalctl -u sing-box.service -o cat -f
fi
}

sbactive(){
if [[ ! -f /etc/s-box/sb.json ]]; then
red "未正常启动Sing-box，请卸载重装或者选择10查看运行日志反馈" && exit
fi
}

sbshare(){
(
umask 077
local SB_EXPORT_DIR file
SB_EXPORT_DIR=$(mktemp -d /etc/s-box/share-stage.XXXXXX) || exit 1
trap 'rm -rf "$SB_EXPORT_DIR"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
node_suffix_load || exit 1
# No live output changes before every renderer succeeds.
{
result_vl_vm_hy_tu && resvless && resvmess && reshy2 && restu5 || exit 1
if [[ "$sbnh" != "1.10" ]]; then resan || exit 1; fi
if [[ -f /etc/s-box/xhttp/config.json ]]; then xhttp_export || return 1; fi
if [[ -f /etc/s-box/xhttp-argo/config.json ]]; then xhttp_argo_export || return 1; fi
sb_client || exit 1
} > "$SB_EXPORT_DIR/display.txt" || exit 1
: > "$SB_EXPORT_DIR/jhdy.txt" || exit 1
for file in vl_reality.txt vm_ws_argols.txt vm_ws_argogd.txt vm_ws.txt vm_ws_tls.txt hy2.txt tuic5.txt an.txt xhttp.txt xhttp-argo.txt; do
[[ ! -f $SB_EXPORT_DIR/$file ]] || cat "$SB_EXPORT_DIR/$file" >> "$SB_EXPORT_DIR/jhdy.txt" || exit 1
done
[[ -s $SB_EXPORT_DIR/jhdy.txt ]] || { red "聚合订阅为空，保留旧导出。" >&2; exit 1; }
cp "$SB_EXPORT_DIR/jhdy.txt" "$SB_EXPORT_DIR/jhsub.txt" || exit 1
sb_exports_commit "$SB_EXPORT_DIR" sbox.json clmi.yaml jhsub.txt jhdy.txt vl_reality.txt vm_ws_argols.txt vm_ws_argogd.txt vm_ws.txt vm_ws_tls.txt vm_ws_argo.txt hy2.txt tuic5.txt an.txt SHA256.txt xhttp.txt xhttp/client.json xhttp/share.txt xhttp-argo.txt xhttp-argo/mihomo.json xhttp-argo/client.json xhttp-argo/share.txt || exit 1
cat "$SB_EXPORT_DIR/display.txt"
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "🚀【 聚合节点 】节点信息如下："
cat /etc/s-box/jhsub.txt
)
}

clash_sb_share(){
sbactive
echo
yellow "1：刷新并查看各协议分享链接、二维码、聚合节点"
yellow "2：刷新并查看Mihomo、Sing-box客户端SFA/SFI/SFW三合一配置、Gitlab私有订阅链接"
yellow "3：推送最新节点配置信息(选项1+选项2)到Telegram通知"
yellow "0：返回上层"
readp "请选择【0-3】：" menu
if [ "$menu" = "1" ]; then
sbshare
elif  [ "$menu" = "2" ]; then
green "请稍等……"
sbshare > /dev/null || { red "刷新失败，未推送；旧订阅保持不变。"; return 1; }
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "Gitlab订阅链接如下："
if [[ -d /etc/s-box/.git ]]; then
gitlabsubgo || return 1
else
yellow "未设置Gitlab订阅，以下显示已刷新的本地配置。"
fi
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "🚀Mihomo配置文件显示如下："
red "文件目录 /etc/s-box/clmi.yaml ，复制自建以yaml文件格式为准" && sleep 2
echo
cat /etc/s-box/clmi.yaml
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
red "🚀SFA/SFI/SFW配置文件显示如下："
red "安卓SFA、苹果SFI，win电脑官方文件包SFW请到甬哥Github项目自行下载，"
red "文件目录 /etc/s-box/sbox.json ，复制自建以json文件格式为准" && sleep 2
echo
cat /etc/s-box/sbox.json
echo
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
elif [ "$menu" = "3" ]; then
tgnotice
else
sb
fi
}

acme(){
#bash <(curl -Ls https://gitlab.com/rwkgyg/acme-script/raw/main/acme.sh)
bash <(curl -Ls https://raw.githubusercontent.com/yonggekkk/acme-yg/main/acme.sh)
}
cfwarp(){
#bash <(curl -Ls https://gitlab.com/rwkgyg/CFwarp/raw/main/CFwarp.sh)
bash <(curl -Ls https://raw.githubusercontent.com/yonggekkk/warp-yg/main/CFwarp.sh)
}
bbr(){
if [[ $vi =~ lxc|openvz ]]; then
yellow "当前VPS的架构为 $vi，不支持开启原版BBR加速" && sleep 2 && exit 
else
green "点击任意键，即可开启BBR加速，ctrl+c退出"
bash <(curl -Ls https://raw.githubusercontent.com/teddysun/across/master/bbr.sh)
fi
}

showprotocol(){
allports
sbymfl
tls=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].tls.enabled')
if [[ "$tls" = "false" ]]; then
if ps -ef 2>/dev/null | grep -v '[x]http-argo/cloudflared' | grep -q '[c]loudflared.*run' || ps -ef 2>/dev/null | grep "[l]ocalhost:$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port')" >/dev/null 2>&1; then
vm_zs="TLS关闭"
argoym="已开启"
else
vm_zs="TLS关闭"
argoym="未开启"
fi
else
vm_zs="TLS开启"
argoym="不支持开启"
fi
hy2_sniname=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[2].tls.key_path')
[[ "$hy2_sniname" = '/etc/s-box/private.key' ]] && hy2_zs="自签证书" || hy2_zs="域名证书"
tu5_sniname=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[3].tls.key_path')
[[ "$tu5_sniname" = '/etc/s-box/private.key' ]] && tu5_zs="自签证书" || tu5_zs="域名证书"
an_sniname=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[4].tls.key_path')
[[ "$an_sniname" = '/etc/s-box/private.key' ]] && an_zs="自签证书" || an_zs="域名证书"
echo -e "Sing-box节点关键信息、已分流域名情况如下："
echo -e "🚀【 Vless-reality 】${yellow}端口:$vl_port  Reality域名证书伪装地址：$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].tls.server_name')${plain}"
if [[ "$tls" = "false" ]]; then
echo -e "🚀【   Vmess-ws    】${yellow}端口:$vm_port   证书形式:$vm_zs   Argo状态:$argoym${plain}"
else
echo -e "🚀【 Vmess-ws-tls  】${yellow}端口:$vm_port   证书形式:$vm_zs   Argo状态:$argoym${plain}"
fi
echo -e "🚀【  Hysteria-2   】${yellow}端口:$hy2_port  证书形式:$hy2_zs  转发多端口: $hy2zfport${plain}"
echo -e "🚀【    Tuic-v5    】${yellow}端口:$tu5_port  证书形式:$tu5_zs  转发多端口: $tu5zfport${plain}"
if [[ "$sbnh" != "1.10" ]]; then
echo -e "🚀【    Anytls     】${yellow}端口:$an_port  证书形式:$an_zs${plain}"
fi
if [ -s /etc/s-box/subport.log ]; then
showsubport=$(cat /etc/s-box/subport.log)
if ps -ef 2>/dev/null | grep "$showsubport" | grep -v grep >/dev/null; then
showsubtoken=$(cat /etc/s-box/subtoken.log 2>/dev/null)
subip=$(cat /etc/s-box/server_ip.log 2>/dev/null)
suburl="$subip:$showsubport/$showsubtoken"
echo "Clash/Mihomo本地IP订阅地址：http://$suburl/clmi.yaml"
echo "Sing-box本地IP订阅地址：http://$suburl/sbox.json"
echo "聚合协议本地IP订阅地址：http://$suburl/jhsub.txt"
fi
fi
if [ "$argoym" = "已开启" ]; then
#echo -e "Vmess-UUID：${yellow}$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[0].users[0].uuid')${plain}"
#echo -e "Vmess-Path：${yellow}$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].transport.path')${plain}"
if ps -ef 2>/dev/null | grep "[l]ocalhost:$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.inbounds[1].listen_port')" >/dev/null 2>&1; then
echo -e "Argo临时域名：${yellow}$(cat /etc/s-box/argo.log 2>/dev/null | grep -a trycloudflare.com | awk 'NR==2{print}' | awk -F// '{print $2}' | awk '{print $1}')${plain}"
fi
if ps -ef 2>/dev/null | grep -v '[x]http-argo/cloudflared' | grep -q '[c]loudflared.*run'; then
echo -e "Argo固定域名：${yellow}$(cat /etc/s-box/sbargoym.log 2>/dev/null)${plain}"
fi
fi
echo "------------------------------------------------------------------------------------"
if [[ -n $(ps -e | grep sbwpph) ]]; then
s5port=$(cat /etc/s-box/sbwpph.log 2>/dev/null | awk '{print $3}'| awk -F":" '{print $NF}')
s5gj=$(cat /etc/s-box/sbwpph.log 2>/dev/null | awk '{print $6}')
case "$s5gj" in
AT) showgj="奥地利" ;;
AU) showgj="澳大利亚" ;;
BE) showgj="比利时" ;;
BG) showgj="保加利亚" ;;
CA) showgj="加拿大" ;;
CH) showgj="瑞士" ;;
CZ) showgj="捷克" ;;
DE) showgj="德国" ;;
DK) showgj="丹麦" ;;
EE) showgj="爱沙尼亚" ;;
ES) showgj="西班牙" ;;
FI) showgj="芬兰" ;;
FR) showgj="法国" ;;
GB) showgj="英国" ;;
HR) showgj="克罗地亚" ;;
HU) showgj="匈牙利" ;;
IE) showgj="爱尔兰" ;;
IN) showgj="印度" ;;
IT) showgj="意大利" ;;
JP) showgj="日本" ;;
LT) showgj="立陶宛" ;;
LV) showgj="拉脱维亚" ;;
NL) showgj="荷兰" ;;
NO) showgj="挪威" ;;
PL) showgj="波兰" ;;
PT) showgj="葡萄牙" ;;
RO) showgj="罗马尼亚" ;;
RS) showgj="塞尔维亚" ;;
SE) showgj="瑞典" ;;
SG) showgj="新加坡" ;;
SK) showgj="斯洛伐克" ;;
US) showgj="美国" ;;
esac
grep -q "country" /etc/s-box/sbwpph.log 2>/dev/null && s5ms="多地区Psiphon代理模式 (端口:$s5port  国家:$showgj)" || s5ms="本地Warp代理模式 (端口:$s5port)"
echo -e "WARP-plus-Socks5状态：$yellow已启动 $s5ms$plain"
else
echo -e "WARP-plus-Socks5状态：$yellow未启动$plain"
fi
echo "------------------------------------------------------------------------------------"
ww4="warp-wireguard-ipv4优先分流域名：$wfl4"
ww6="warp-wireguard-ipv6优先分流域名：$wfl6"
ws4="warp-socks5-ipv4优先分流域名：$sfl4"
ws6="warp-socks5-ipv6优先分流域名：$sfl6"
l4="VPS本地ipv4优先分流域名：$adfl4"
l6="VPS本地ipv6优先分流域名：$adfl6"
[[ "$sbnh" == "1.10" ]] && ymflzu=("ww4" "ww6" "ws4" "ws6" "l4" "l6") || ymflzu=("ww6" "ws4" "l4" "l6")
for ymfl in "${ymflzu[@]}"; do
if [[ ${!ymfl} != *"未"* ]]; then
echo -e "${!ymfl}"
fi
done
if [[ $ww4 = *"未"* && $ww6 = *"未"* && $ws4 = *"未"* && $ws6 = *"未"* && $l4 = *"未"* && $l6 = *"未"* ]] ; then
echo -e "未设置域名分流"
fi
}

inssbwpph(){
sbactive
ins(){
if [ ! -e /etc/s-box/sbwpph ]; then
case $(uname -m) in
aarch64) cpu=arm64;;
x86_64) cpu=amd64;;
esac
curl -L -o /etc/s-box/sbwpph -# --retry 2 --insecure https://raw.githubusercontent.com/redrohu/sing-box-yg/main/sbwpph_$cpu
chmod +x /etc/s-box/sbwpph
fi
ps -ef | grep '[s]bwpph' | awk '{print $2}' | xargs kill 2>/dev/null
v4v6 refresh
if [[ -n $v4 ]]; then
sw46=4
else
red "IPV4不存在，确保安装过WARP-IPV4模式"
sw46=6
fi
echo
readp "设置WARP-plus-Socks5端口（回车跳过端口默认40000）：" port
if [[ -z $port ]]; then
port=40000
until [[ -z $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") && -z $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]] 
do
[[ -n $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") || -n $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]] && yellow "\n端口被占用，请重新输入端口" && readp "自定义端口:" port
done
else
until [[ -z $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") && -z $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]]
do
[[ -n $(ss -tunlp | grep -w udp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") || -n $(ss -tunlp | grep -w tcp | awk '{print $5}' | sed 's/.*://g' | grep -w "$port") ]] && yellow "\n端口被占用，请重新输入端口" && readp "自定义端口:" port
done
fi
s5port=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.outbounds[] | select(.type == "socks") | .server_port')
[[ "$sbnh" == "1.10" ]] && num=10 || num=11
sed -i "127s/$s5port/$port/g" /etc/s-box/sb10.json
sed -i "165s/$s5port/$port/g" /etc/s-box/sb11.json
cp /etc/s-box/sb${num}.json /etc/s-box/sb.json
restartsb
}
unins(){
ps -ef | grep '[s]bwpph' | awk '{print $2}' | xargs kill 2>/dev/null
rm -rf /etc/s-box/sbwpph.log
sb_cron_update warp || return 1
rm -rf /etc/local.d/alpinews5.start
}
aplws5(){
if command -v apk >/dev/null 2>&1; then
cat > /etc/local.d/alpinews5.start <<'EOF'
#!/bin/bash
sleep 10
nohup $(cat /etc/s-box/sbwpph.log 2>/dev/null)
EOF
chmod +x /etc/local.d/alpinews5.start
rc-update add local default >/dev/null 2>&1
else
sb_cron_update warp '@reboot sleep 10 && /bin/bash -c "nohup $(cat /etc/s-box/sbwpph.log 2>/dev/null) &"' || return 1
fi
}
echo
yellow "1：重置启用WARP-plus-Socks5本地Warp代理模式"
yellow "2：重置启用WARP-plus-Socks5多地区Psiphon代理模式"
yellow "3：停止WARP-plus-Socks5代理模式"
yellow "0：返回上层"
readp "请选择【0-3】：" menu
if [ "$menu" = "1" ]; then
ins
nohup /etc/s-box/sbwpph -b 127.0.0.1:$port -$sw46 --endpoint 162.159.192.1:2408 >/dev/null 2>&1 &
green "申请IP中……请稍等……" && sleep 20
resv1=$(curl -sm3 --socks5 localhost:$port icanhazip.com)
resv2=$(curl -sm3 -x socks5h://localhost:$port icanhazip.com)
if [[ -z $resv1 && -z $resv2 ]]; then
red "WARP-plus-Socks5的IP获取失败" && unins && exit
else
echo "/etc/s-box/sbwpph -b 127.0.0.1:$port -$sw46 --endpoint 162.159.192.1:2408 >/dev/null 2>&1" > /etc/s-box/sbwpph.log
aplws5
green "WARP-plus-Socks5的IP获取成功，可进行Socks5代理分流"
fi
elif [ "$menu" = "2" ]; then
ins
echo '
奥地利（AT）
澳大利亚（AU）
比利时（BE）
保加利亚（BG）
加拿大（CA）
瑞士（CH）
捷克 (CZ)
德国（DE）
丹麦（DK）
爱沙尼亚（EE）
西班牙（ES）
芬兰（FI）
法国（FR）
英国（GB）
克罗地亚（HR）
匈牙利 (HU)
爱尔兰（IE）
印度（IN）
意大利 (IT)
日本（JP）
立陶宛（LT）
拉脱维亚（LV）
荷兰（NL）
挪威 (NO)
波兰（PL）
葡萄牙（PT）
罗马尼亚 (RO)
塞尔维亚（RS）
瑞典（SE）
新加坡 (SG)
斯洛伐克（SK）
美国（US）
'
readp "可选择国家地区（输入末尾两个大写字母，如美国，则输入US）：" guojia
nohup /etc/s-box/sbwpph -b 127.0.0.1:$port --cfon --country $guojia -$sw46 --endpoint 162.159.192.1:2408 >/dev/null 2>&1 &
green "申请IP中……请稍等……" && sleep 20
resv1=$(curl -sm3 --socks5 localhost:$port icanhazip.com)
resv2=$(curl -sm3 -x socks5h://localhost:$port icanhazip.com)
if [[ -z $resv1 && -z $resv2 ]]; then
red "WARP-plus-Socks5的IP获取失败，尝试换个国家地区吧" && unins && exit
else
echo "/etc/s-box/sbwpph -b 127.0.0.1:$port --cfon --country $guojia -$sw46 --endpoint 162.159.192.1:2408 >/dev/null 2>&1" > /etc/s-box/sbwpph.log
aplws5
green "WARP-plus-Socks5的IP获取成功，可进行Socks5代理分流"
fi
elif [ "$menu" = "3" ]; then
unins && green "已停止WARP-plus-Socks5代理功能"
else
sb
fi
}

sbsm(){
echo
green "关注甬哥YouTube频道：https://youtube.com/@ygkkk?sub_confirmation=1 了解最新代理协议与翻墙动态"
echo
blue "sing-box-yg脚本视频教程：https://www.youtube.com/playlist?list=PLMgly2AulGG_Affv6skQXWnVqw7XWiPwJ"
echo
blue "sing-box-yg脚本博客说明：http://ygkkk.blogspot.com/2023/10/sing-box-yg.html"
echo
blue "sing-box-yg脚本项目地址：https://github.com/yonggekkk/sing-box-yg"
echo
blue "推荐甬哥新品：ArgoSBX一键无交互小钢炮脚本"
blue "ArgoSBX项目地址：https://github.com/yonggekkk/argosbx"
echo
}

clear
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~" 
echo -e "${bblue} ░██     ░██      ░██ ██ ██         ░█${plain}█   ░██     ░██   ░██     ░█${red}█   ░██${plain}  "
echo -e "${bblue}  ░██   ░██      ░██    ░░██${plain}        ░██  ░██      ░██  ░██${red}      ░██  ░██${plain}   "
echo -e "${bblue}   ░██ ░██      ░██ ${plain}                ░██ ██        ░██ █${red}█        ░██ ██  ${plain}   "
echo -e "${bblue}     ░██        ░${plain}██    ░██ ██       ░██ ██        ░█${red}█ ██        ░██ ██  ${plain}  "
echo -e "${bblue}     ░██ ${plain}        ░██    ░░██        ░██ ░██       ░${red}██ ░██       ░██ ░██ ${plain}  "
echo -e "${bblue}     ░█${plain}█          ░██ ██ ██         ░██  ░░${red}██     ░██  ░░██     ░██  ░░██ ${plain}  "
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~" 
white "甬哥Github项目  ：github.com/yonggekkk"
white "甬哥Blogger博客 ：ygkkk.blogspot.com"
white "甬哥YouTube频道 ：www.youtube.com/@ygkkk"
white "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~" 
white "Vless-reality-vision、Vmess-ws(tls)+Argo、Hy2、Tuic、Anytls 五协议共存脚本"
white "脚本快捷方式：sb"
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
green " 1. 一键安装 Sing-box" 
green " 2. 删除卸载 Sing-box"
white "----------------------------------------------------------------------------------"
green " 3. 变更配置 【双证书TLS/UUID路径/Argo/IP优先/TG通知/Warp/订阅/CDN优选】" 
green " 4. 更改主端口/添加多端口跳跃复用" 
green " 5. 三通道域名分流"
green " 6. 关闭/重启 Sing-box"   
green " 7. 更新 Sing-box-yg 脚本"
green " 8. 更新/切换/指定 Sing-box 内核版本"
white "----------------------------------------------------------------------------------"
green " 9. 刷新并查看节点 【Mihomo/SFA+SFI+SFW三合一配置/订阅链接/推送TG通知】"
green "10. 查看 Sing-box 运行日志"
green "11. 一键原版BBR+FQ加速"
green "12. 管理 Acme 申请域名IP证书"
green "13. 管理 Warp 查看Netflix/ChatGPT解锁情况"
green "14. 添加 WARP-plus-Socks5 代理模式 【本地Warp/多地区Psiphon-VPN】"
green "15. 更换IP刷新本地IP、调整IPV4/IPV6配置输出"
white "----------------------------------------------------------------------------------"
green "16. Sing-box-yg脚本使用说明书"
white "----------------------------------------------------------------------------------"
green " 0. 退出脚本"
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
insV=$(cat /etc/s-box/v 2>/dev/null)
sb_update_notice "$insV"

lapre
if [ -f '/etc/s-box/sb.json' ]; then
if [[ $inscore =~ ^[0-9.]+$ ]]; then
if [ "${inscore}" = "${latcore}" ]; then
echo
echo -e "当前 Sing-box 最新正式版内核：${bblue}${inscore}${plain} (已安装)"
echo
echo -e "当前 Sing-box 最新测试版内核：${bblue}${precore}${plain} (可切换)"
else
echo
echo -e "当前 Sing-box 已安装正式版内核：${bblue}${inscore}${plain}"
echo -e "检测到最新 Sing-box 正式版内核：${yellow}${latcore}${plain} (可选择8进行更新)"
echo
echo -e "当前 Sing-box 最新测试版内核：${bblue}${precore}${plain} (可切换)"
fi
else
if [ "${inscore}" = "${precore}" ]; then
echo
echo -e "当前 Sing-box 最新测试版内核：${bblue}${inscore}${plain} (已安装)"
echo
echo -e "当前 Sing-box 最新正式版内核：${bblue}${latcore}${plain} (可切换)"
else
echo
echo -e "当前 Sing-box 已安装测试版内核：${bblue}${inscore}${plain}"
echo -e "检测到最新 Sing-box 测试版内核：${yellow}${precore}${plain} (可选择8进行更新)"
echo
echo -e "当前 Sing-box 最新正式版内核：${bblue}${latcore}${plain} (可切换)"
fi
fi
else
echo
echo -e "当前 Sing-box 最新正式版内核：${bblue}${latcore}${plain}"
echo -e "当前 Sing-box 最新测试版内核：${bblue}${precore}${plain}"
fi
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo -e "VPS状态如下："
echo -e "系统:$blue$op$plain  \c";echo -e "内核:$blue$version$plain  \c";echo -e "处理器:$blue$cpu$plain  \c";echo -e "虚拟化:$blue$vi$plain  \c";echo -e "BBR算法:$blue$bbr$plain"
v4v6
if [[ "$v6" == "2a09"* ]]; then
w6="【WARP】"
fi
if [[ "$v4" == "104.28"* ]]; then
w4="【WARP】"
fi
[[ -z $v4 ]] && showv4='IPV4地址丢失，请切换至IPV6或者重装Sing-box' || showv4=$v4$w4
[[ -z $v6 ]] && showv6='IPV6地址丢失，请切换至IPV4或者重装Sing-box' || showv6=$v6$w6
if [[ -z $v4 ]]; then
vps_ipv4='无IPV4'      
vps_ipv6="$v6"
location="$v6dq"
elif [[ -n $v4 &&  -n $v6 ]]; then
vps_ipv4="$v4"    
vps_ipv6="$v6"
location="$v4dq"
else
vps_ipv4="$v4"    
vps_ipv6='无IPV6'
location="$v4dq"
fi
echo -e "本地IPV4地址：$blue$vps_ipv4$w4$plain   本地IPV6地址：$blue$vps_ipv6$w6$plain"
echo -e "服务器地区：$blue$location$plain"
if [[ "$sbnh" == "1.10" ]]; then
rpip=$(sed 's://.*::g' /etc/s-box/sb.json | jq -r '.outbounds[0].domain_strategy') 2>/dev/null
if [[ $rpip = 'prefer_ipv6' ]]; then
v4_6="IPV6优先出站($showv6)"
elif [[ $rpip = 'prefer_ipv4' ]]; then
v4_6="IPV4优先出站($showv4)"
elif [[ $rpip = 'ipv4_only' ]]; then
v4_6="仅IPV4出站($showv4)"
elif [[ $rpip = 'ipv6_only' ]]; then
v4_6="仅IPV6出站($showv6)"
fi
echo -e "代理IP优先级：$blue$v4_6$plain"
fi
if command -v apk >/dev/null 2>&1; then
status_cmd="rc-service sing-box status"
status_pattern="started"
else
status_cmd="systemctl is-active sing-box"
status_pattern="active"
fi
if [[ -n $($status_cmd 2>/dev/null | grep -w "$status_pattern") && -f '/etc/s-box/sb.json' ]]; then
echo -e "Sing-box状态：$blue运行中$plain"
elif [[ -z $($status_cmd 2>/dev/null | grep -w "$status_pattern") && -f '/etc/s-box/sb.json' ]]; then
echo -e "Sing-box状态：$yellow未启动，选择10查看日志并反馈，建议切换正式版内核或卸载重装脚本$plain"
else
echo -e "Sing-box状态：$red未安装$plain"
fi
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
if [ -f '/etc/s-box/sb.json' ]; then
showprotocol
fi
red "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo
readp "请输入数字【0-16】:" Input
case "$Input" in  
 1 ) instsllsingbox;;
 2 ) unins;;
 3 ) changeserv;;
 4 ) changeport;;
 5 ) changefl;;
 6 ) stclre;;
 7 ) upsbyg;; 
 8 ) upsbcroe;;
 9 ) clash_sb_share;;
10 ) sblog;;
11 ) bbr;;
12 ) acme;;
13 ) cfwarp;;
14 ) inssbwpph;;
15 ) wgcfgo && sbshare;;
16 ) sbsm;;
 * ) exit 
esac
