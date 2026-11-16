# 严格使用指定的 1.14 服务端模板

默认入口 `sb.sh` 现在使用独立的 `server14.sh`，不再调用五协议生成器。

模板唯一来源：[qichiyuhub/rule/config/singbox/1.14X/VPS/server.json](https://github.com/qichiyuhub/rule/blob/main/config/singbox/1.14X/VPS/server.json)。
已固定该文件版本 `b8923a7351ea516f87599a8889f99aaeb70e989f`；原始快照在 `tests/fixtures/server14.upstream.json`，也嵌入在 `server14.sh` 中。
运行时不会随上游 `main` 静默改变配置。更新模板必须重新审核和测试。

## 生成内容

顶层**只有 `certificate_providers` 和 `inbounds`**，与指定模板相同。
保留全部标签、入站顺序和选项：

| 入站 tag | 协议 | 默认端口 |
|---|---|---|
| VLESS-Vision-Reality-in | VLESS Vision Reality | TCP 443 |
| anytls-reality-in | AnyTLS Reality | TCP 1443 |
| shadowtls-in | ShadowTLS v3 | TCP 2443 |
| shadowtls-ss-in | ShadowTLS 内部 Shadowsocks | 仅 detour，不新增监听端口 |
| naive-in | Naive | TCP 3443 |
| anytls-in | AnyTLS TLS | TCP 4443 |
| trojan-in | Trojan | TCP 5443 |
| hysteria-in | Hysteria2 + Salamander | UDP 6443 |
| tuic-in | TUIC | UDP 7443 |
| shadowsocks2022-in | Shadowsocks 2022 | TCP/UDP 8080 |

只填入部署相关值：证书域名、邮箱、Cloudflare Token、Reality/ShadowTLS 握手域名、UUID、32 字节随机密码、Reality 私钥/short_id、可选自定义端口。
用户名、AnyTLS padding、multiplex、ShadowTLS detour、HY2 obfs、TUIC congestion control 等均保留原模板。

**没有混入 1.12 DNS、AI 域名、WARP、SOCKS 出站或 QUIC/STUN 拒绝规则。**
使用内置 ACME 和 Cloudflare DNS-01，保留原模板的 `/etc/sing-box/acme` 存储路径，不降级为自签证书。

## 前提

- root（只读模板和本地 render 不要求 root）、bash、jq、curl、tar。
- sing-box **>=1.14**，内核必须包含所需协议和 ACME 功能；所有写入前执行真实 `sing-box check`。
- 自己控制的证书域名、有效邮箱、可操作对应 DNS zone 的 Cloudflare API Token。
- 服务器能访问 ACME、Cloudflare API 和 Reality/ShadowTLS 握手目标；自行开放所选入站端口。
- 端口若已被 nginx、其他代理等占用，先解决冲突；`check` 通过不代表端口能绑定或证书能签发。

本次代码验证没有发起真实 ACME 申请，未声称全部协议已通过客户端端到端测试。

## 获取与生成候选文件

```bash
git clone https://github.com/redrohu/sing-box-yg.git
cd sing-box-yg
apt install -y jq curl tar
cp server14.parameters.example.json parameters.json
chmod 600 parameters.json
# 编辑 parameters.json：填写真实 domain / email / cloudflare_api_token，按需改 ports。
# 不接受示例 Token，不会默默回退到模板里的示例密钥。

# 没有合适内核时安装；默认 1.14.4，不会重启服务或改配置。
bash sb.sh install-core 1.14.4

# 只生成新文件，不覆盖已有文件、不改运行中的服务。
bash sb.sh render parameters.json /root/sb14.candidate.json
bash sb.sh check /root/sb14.candidate.json
bash sb.sh summary /root/sb14.candidate.json
```

也可以 `bash sb.sh` 使用交互菜单。CF Token 隐藏输入，不会作为交互提示打印。
生成文件及备份权限均为 0600；参数文件和配置包含秘密，不要提交到 Git 或公开粘贴。

## 新安装

```bash
bash sb.sh install parameters.json 1.14.4
journalctl -u sing-box -n 80 --no-pager
```

`install` 拒绝覆盖已有 `/etc/s-box/sb.json`。它安装内核、配置、systemd/OpenRC 服务和 `sb` 快捷入口，然后启动服务。
真正可用仍需核对证书签发日志和客户端连接；申请失败时不会自动换回自签证书。

## 从旧五协议配置迁移（必须有计划地操作）

**这不是无损更新！**指定模板没有 VMess-WS/Argo；新增协议、端口和全部凭据都要在客户端重新配置。
原 `sbox.json`、`clmi.yaml`、分享链接不会自动升级，也不会被新流程覆写或当作新配置继续生成。
本次只改服务端生成，十入站模板的客户端导出器不在交付范围内。

```bash
# 已有合适内核时，不必重复安装。
bash sb.sh apply parameters.json
# apply 内部再次生成新随机凭据；如果之前 render 过，最终凭据以 /etc/s-box/sb.json 为准。
# 自动备份旧配置和 SHA256，然后写入 sb.json；不重启服务。
# 为避免旧菜单破坏新配置，会备份旧 /usr/bin/sb，并切换快捷入口到新流程。
bash sb.sh check
# 确认端口、域名和客户端准备完毕后显式重启。
bash sb.sh restart
```

不再生成或从 `sb10.json` / `sb11.json` 拷贝覆盖 `sb.json`；旧文件保留但不再使用。
五协议菜单仍可通过仓库中的 `bash sb.sh --legacy` 维护**旧配置**，但发现新模板的 tag 就拒绝运行，防止数组下标/行号操作损坏新配置。
`--legacy` 保持最初 fork 的旧行为及上游 URL，不用于新模板的安装或更新。

## 后续修改（均先校验、备份，不自动重启）

```bash
sb set-port trojan-in 18443
sb set-reality www.apple.com
sb rotate-credentials
sb set-certificate parameters.json  # 只更新 ACME/证书域名，保留端口、UUID、密码
sb restart
```

不提供旧版 Argo、WARP 分流、旧协议证书切换或 1.10 降级功能；这些都不是指定模板的一部分。
SSH、DNS、证书文件等不应从服务器配置复制到客户端；按各协议要求使用公钥/账号信息。

## 恢复

```bash
sb restore /etc/s-box/sb.json.bak.实际备份名
```

先由当前内核校验，再恢复；另存恢复前副本，不自动重启。
恢复成旧五协议配置后，使用原配置对应的内核、脚本及客户端；新模式 `restart` 只接受指定模板，旧配置可在再次 `check` 后手动 `systemctl restart sing-box`。
旧快捷入口备份是 `/etc/s-box/sb.launcher.bak.*`，按需手动恢复；不要将其恢复到仍使用新模板的安装。

仓库历史中的 `ceff58e`、`e42cdd7` 已分别回退此前错误的模板适配和自更新 URL 修改；`e42cdd7` 的文件树与最初 fork 的 `b13f943` 相同。

## 测试

```bash
SB14_TEST_BIN=/path/to/sing-box python3 tests/test_server14.py -v
```

测试核对原始模板相等、只改部署参数、十入站真实内核校验、参数拒绝、菜单改写、失败不覆盖、恢复副本等。
事务测试仅对测试目录操作，并替代 root/服务调用；不会请求 ACME 或重启真实服务。
