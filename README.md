### 一、Sing-box-yg精装桶一键五协议共存脚本（VPS专用）
### 二、Serv00/Hostuno-sb-yg多平台一键三协议共存脚本（Serv00/Hostuno专用）

> 本 fork 已从初始版本重新适配官方 sing-box 新配置格式，默认导出 1.14 客户端配置；保留原菜单和协议，不使用第三方十入站模板。版本兼容、更新说明及验证范围见 [CONFIG-COMPATIBILITY.md](CONFIG-COMPATIBILITY.md)。

### 仓库结构（本 fork）

| 路径 | 内容 |
| --- | --- |
| `sb.sh` | VPS 一键脚本（快捷命令 `sb`） |
| `serv00.sh`、`serv00keep.sh`、`app.js`、`index.html` | Serv00/Hostuno 安装、保活与认证网页管理 |
| `kp.sh`、`serv00.yml`、`SSH.yml`、`workers_keep.js` | 自建保活/远程部署模板；账号与令牌只放 Secrets，见[迁移说明](docs/SERV00-MANAGEMENT-MIGRATION.md) |
| `version`、`sversion` | VPS / Serv00 脚本更新日志（脚本在线读取，勿改格式） |
| `sbwpph_amd64`、`sbwpph_arm64` | WARP-plus Socks5 预编译程序，由菜单 14 下载 |
| `docs/` | 菜单功能图与说明、Serv00 迁移说明 |
| `docs/validation/` | XHTTP / Mihomo / 实机验证与问题诊断记录 |
| `docs/history/` | 2026-11-21 代码审查、修复与重构交付记录 |
| `tests/` | 本地回归测试（真实 Sing-box / Xray / Mihomo 内核校验），`python -m unittest discover -s tests -v` |
| `.github/workflows/` | CI：`config-tests.yml` 完整回归，`lint.yml` 语法与仓库卫生检查；`main.yml` 为手动认证保活 |

本地审查证据（`review-artifacts/`）与个人工作目录不纳入 Git。

### 当前菜单导航（VPS）

**实际菜单功能图：**[可编辑XMind](docs/MENU-ACTUAL-TREE.xmind) · [完整展开SVG](docs/menu-maps/vps-actual-menu-full.svg) · [菜单速览PNG](docs/menu-maps/vps-actual-menu-overview.png)。按实际主菜单及子菜单展示作用和注意事项；另有[文字详表](docs/MENU-GUIDE.md)和[离线查看页](docs/MENU-GUIDE.html)。终端菜单 **16** 也提供入口。

菜单编号保持不变，**16** 提供本 fork 帮助与上游教程。两种 XHTTP 都是可选的独立 Xray 服务，并非 Sing-box 的新增入站。

| 入口 | 实际作用与范围 |
| --- | --- |
| 2 | 完整卸载本脚本，包含已部署的独立 XHTTP、隧道服务及本机配置/密钥；不删除 Cloudflare 云端隧道或路由 |
| 3 → 2；主菜单 4、6、8 | 分别管理 Sing-box 五协议 UUID / 端口 / 启停 / 内核，不更改独立 XHTTP |
| 3 → 3 | VMess 的临时/固定 Argo，不管理 XHTTP Argo |
| 3 → 9 | 手动设置 VMess 主节点/Argo 连接地址，不自动测速、不保证提速 |
| 3 → 10 | 设置或清除节点名称前后缀，包含已部署的 XHTTP |
| 3 → 11 → 1–8 | 管理直连 XHTTP + REALITY；选项 7 只卸载此直连节点 |
| 3 → 11 → 9 | 管理独立 XHTTP + 固定 Argo（不叠加 REALITY）；其选项 8 设置独立连接地址 |
| 9 → 1 | 刷新本地订阅、查看节点，不推送 Gitlab |
| 9 → 2 | 刷新/查看配置；已配置 Gitlab 时同时推送远端；客户端还需重新拉取 |

XHTTP 写入 Mihomo YAML 和通用分享订阅，不写入官方 Sing-box JSON。菜单 IP/地区查询缓存 60 秒，版本信息缓存 5 分钟；`SB_MENU_REFRESH=1 sb` 可强制刷新查询，不代表更新脚本或内核。

Serv00/Hostuno 菜单独立：**6** 查看节点与订阅链接，**7** 查看配置文件。网页管理是认证 API，不是交互控制面板；管理/保活需可信 HTTPS、POST 和独立 Bearer 令牌，详见 [迁移说明](docs/SERV00-MANAGEMENT-MIGRATION.md)。

### 节点名称前缀 / 后缀（VPS）

菜单 **3 → 10**：1 设置后缀、2 恢复主机名后缀、3 设置前缀、4 清除前缀、**5 清除后缀（不显示主机名）**。清除前后缀互不影响；例如清除后缀后 `RN 美国 | anytls racknerd-54213c7` 变为 `RN 美国 | anytls`，不残留尾随空格。

无后缀模式由 `/etc/s-box/node_suffix.disabled` 标记，设置新后缀或恢复主机名时自动取消；原自定义后缀文件可以保留，但标记存在时不显示。仅刷新客户端名称、分组引用及分享链接，含两种 XHTTP 节点；不修改服务器主机名、连接参数或重启服务。变更前备份设置及导出；Gitlab 用 **9 → 2** 推送，客户端再更新订阅。

### 可选：VLESS + XHTTP + REALITY（VPS）

安装现有 Sing-box 后，运行本版本 `sb.sh`，选择 **3 → 11 → 1** 部署独立 Xray 服务。
原五协议保持不变，XHTTP 不经过 Argo/CDN，不保证比现有节点更快。

新部署可选两种模式，默认采用[文章](https://www.cunzhangblog.com/vlessxhttp)中的 **VLESS + XHTTP + REALITY + VLESS Encryption（X25519认证）+ Vision**，路径为 `/`、`mode: auto`；也可选普通 XHTTP + REALITY。文章中的 X25519 是 VLESS Encryption 的认证选项，与外层 REALITY 密钥是两套独立凭据，不应混用。

已部署普通 XHTTP 的服务器可用 **3 → 11 → 8** 升级：先备份服务和导出，保留原端口、UUID及REALITY密钥，生成独立 Encryption 凭据、启用 `xtls-rprx-vision`，路径改为 `/`，配置检查后重启独立 Xray 并刷新订阅。旧客户端配置将不再兼容，必须更新订阅；失败尝试从提示的备份目录恢复。操作前请确认客户端足够新（已验证 Xray v26.11.9、Mihomo v1.19.34），原五协议无需更改。

- 独立 TCP 端口默认 443；已占用则换端口，并在云安全组及系统防火墙放行。不要占用已有 Reality/HTTPS 端口。
- 目标域名应从 VPS 可达、支持 TLS 1.3 和 H2；默认 `www.cloudflare.com` 不是可用性保证，部署后应实测。
- 下载官方 Xray **v26.11.9**（固定版本），核对同一官方 release 的 SHA256 摘要，服务端和客户端配置均通过内核检查后启动；失败清理本次安装，不修改现有 Sing-box 入站。
- 支持 Linux amd64、arm64、armv7，systemd/OpenRC；部署时检查 `curl jq unzip openssl sha256sum ss`，仅通过 apt-get/apk/dnf/yum 安装缺失依赖。`ss` 对应 Debian/Alpine 的 `iproute2` 或 RPM 系的 `iproute`，`sha256sum` 对应 `coreutils`。软件源或安装失败时停止部署，不自动更改软件源，也不升级现有五协议。
- 服务名 `sbox-xhttp`；配置和密钥在 `/etc/s-box/xhttp/`。`client.json` 是 Xray 客户端配置（本地 SOCKS5 `127.0.0.1:10808`），`share.txt` 是导入链接。请勿公开服务端配置、密钥或订阅链接。
- 分享链接自动加入通用聚合订阅 `jhsub.txt`；已部署时也自动写入 **Mihomo `clmi.yaml`**，并加入负载均衡、自动选择和手动选择三个代理组。支持 XHTTP 的新版 Mihomo 可直接使用（验证版本 **v1.19.34**）。未部署或卸载后刷新，不生成该节点及组内引用。
- 官方 sing-box 当前不支持 XHTTP，因此 **不会写入 `sbox.json`**。Mihomo 节点使用独立 Xray 服务的 UUID、端口、公钥、Short ID、路径及 REALITY SNI，支持 IPv4/IPv6 和节点名称前后缀；文章模式额外导出 `encryption` 与 Vision `flow`，普通模式不添加；不导出私钥或服务端 `decryption`。
- 为兼容本脚本固定的 Xray v26.11.9，导出时显式启用 `reality-opts.support-x25519mlkem768: true`；否则 Mihomo 默认移除该密钥交换信息，可能导致 REALITY 握手失败。不要通过关闭证书校验来绕过。
- 更新本版本脚本后，通过主菜单 **9** 刷新本地节点/订阅，再在客户端更新订阅；Gitlab 远端订阅需 **9→2** 刷新推送。
- 通过 **3 → 11** 查看节点、重启、停止、状态、日志或卸载。独立 UUID、路径和密钥，不跟随原五协议的 UUID/端口/证书/启停菜单；使用独立直连出站，不继承 Sing-box 的 Warp/域名分流策略。主菜单2完整卸载时一并移除。
- 卸载前可用 `umask 077; tar -czf /root/sbox-xhttp-backup.tar.gz -C /etc/s-box xhttp` 备份。恢复时先通过本菜单重新部署服务、停止它，再将备份中的 `xhttp/` 解回 `/etc/s-box/`，用 **3 → 11 → 3** 检查并启动，随后 **3 → 11 → 2** 刷新节点。备份含私钥，须妥善保管；恢复原端口前检查冲突。

配置依据：[Xray 传输配置](https://xtls.github.io/config/transport.html)、[XHTTP](https://xtls.github.io/config/transports/splithttp.html)。本功能仅接入 VPS `sb.sh`，未修改 Serv00 脚本。

### 可选：XHTTP + 固定 Cloudflare Tunnel（VPS）

入口 **3 → 11 → 9 → 1**，与上述直连 REALITY 节点并存，不修改原五协议。

1. 在 Cloudflare 创建一个独立的 cloudflared 固定隧道，保存 Tunnel Token 到服务器上的受保护文件（例如 `/root/xhttp-token.txt`，权限 `600`）。不要发送或公开 Token。
2. 为该隧道添加已发布应用：使用自己的完整子域名，路径留空，服务 **HTTP `127.0.0.1:18080`**。若修改回源端口，脚本与 Cloudflare 路由必须一致。该主机名不应启用需要浏览器交互的 Access 验证/挑战，不缓存 XHTTP 请求。
3. 脚本输入完整域名、回源端口、**服务器上的 Token 文件路径**。Token 保存于独立目录、仅通过 `--token-file` 读取，不出现在服务命令行或订阅里。部署成功后可删除最初的 Token 临时文件，保留服务目录中的副本。
4. 客户端为 **VLESS Encryption + Vision + XHTTP `packet-up` + TLS**，边缘端口 `443`；Cloudflare 终止外层 TLS，隧道回源为本机 HTTP，**不叠加 REALITY**。与直连节点使用不同的 UUID、Encryption 凭据和路径；这不是端到端的 REALITY。支持新版 Xray/Mihomo，不向官方 sing-box 导出 XHTTP。
5. 两个服务为 `sbox-xhttp-argo` / `sbox-xhttp-argo-tunnel`，配置、Token、导出在 `/etc/s-box/xhttp-argo/`；HTTP 源站只监听回环地址，不需开放公网回源端口。已有 VMess Argo 使用自己的进程和目录，互不启停。
6. 自动加入 `clmi.yaml` 三个代理组及 `jhsub.txt` 聚合订阅；Gitlab 远端订阅仍需 **9 → 2** 推送，客户端更新订阅后使用。源站保留 SSE 响应头（`noSSEHeader: false`）以避免 cloudflared 缓冲下载流。服务启动不等于域名路由可用，必须验证真实客户端传输。

**3 → 11 → 9** 可查看节点、重启、停止、查看状态/日志、卸载新节点。完整卸载也会移除它，不会自动删除 Cloudflare 控制台的隧道或 DNS 路由。备份时保存 `/etc/s-box/xhttp-argo/` 和两个同名服务定义，均含敏感凭据；恢复前停服务、检查端口，然后恢复文件和服务、检查 Xray 配置并启动、刷新订阅。不要将备份或 Token 放入 Git。

**优选连接地址：3 → 11 → 9 → 8**，可手动设置 XHTTP＋Argo 专用的域名、IPv4 或 IPv6，或恢复使用隧道域名。此设置与 **3 → 9** 的 VMess 优选设置相互独立，不自动跟随、不自动测速。域名使用 ASCII/punycode；不接受协议前缀、端口、路径、空格或 IPv6 zone ID。IPv6 可输入裸地址或完整方括号地址，内部统一保存为裸地址，分享 URI 自动加方括号。

设置保存在 `/etc/s-box/xhttp-argo/server.conf`。仅修改 Mihomo `server`、Xray 客户端 `address`、分享链接连接地址；TLS SNI 和 XHTTP Host 始终保留原隧道域名，仍校验证书。自动刷新本地 YAML/JSON/聚合 URI，Gitlab 用 **9 → 2** 推送，客户端随后更新订阅。不会修改源站、Token、UUID、Encryption、端口或重启服务。变更前备份受影响导出，刷新失败尝试还原设置和原导出；备份中的客户端配置含凭据，须妥善保存。优选地址必须实际可接入 Cloudflare，格式通过不代表连通或提速。

### 注：本项目分享订阅节点都为本地化生成，不使用节点转换、订阅器等第三方外链引用，无需担心节点订阅被外链作者查看

### 交流平台：[甬哥博客地址](https://ygkkk.blogspot.com)、[甬哥YouTube频道](https://www.youtube.com/@ygkkk)、[甬哥TG电报群组](https://t.me/+jZHc6-A-1QQ5ZGVl)、[甬哥TG电报频道](https://t.me/+DkC9ZZUgEFQzMTZl)

----------------------------------------------------------------
#### 推荐推广：极简 + 轻量 + 快速的多协议的ArgoSBX脚本，请移步到[ArgoSBX脚本项目](https://github.com/yonggekkk/argosbx)

--------------------------------------------------------------

### 一、Sing-box-yg精装桶小白专享一键五协议共存脚本（VPS专用）

* 支持人气最高的五大协议：Vless-reality-vision、Vmess-ws(tls)/Argo、Hysteria-2、Tuic-v5、Anytls

* 支持纯IPV6、纯IPV4、双栈VPS，支持amd与arm架构，支持alpine系统，推荐使用最新的Ubuntu系统

* 小白简单模式：无需域名证书，回车三次就安装完成，复制、扫描你要的节点配置

#### 相关说明及注意点请查看[甬哥博客说明与Sing-box视频教程](https://ygkkk.blogspot.com/2023/10/sing-box-yg.html)

#### 视频教程：
[SSH连不上？使用VPS内置SSH，配合一键功能化脚本命令，小白也能快速搭节点！（Racknerd等所有VPS通用）](https://youtu.be/vhqPG9h8PB4)

[Racknerd VPS：小白自建最强翻墙代理协议组合方案；高速、稳定、无视IP被封；解决Google gemini无法使用问题](https://youtu.be/aGEmCu503V8)

[🥇搭建代理9大问题排行榜：第4名全网99%的人被误导！第1名每个人都被折腾到爆！](https://youtu.be/pJwJBqBkcfw)

[🥇2025年度代理协议"拉到夯"综合排名](https://youtu.be/IoFtykGXDao)

[Sing-box精装桶小白一键脚本（一）：配置文件通吃SFA/SFI/SFW三平台客户端，Argo隧道、双证书切换、域名分流](https://youtu.be/QwTapeVPeB0)

[Sing-box精装桶小白一键脚本（二）：纯IPV6 VPS搭建，CDN优选IP设置汇总，全平台多种客户端一个脚本全套带走](https://youtu.be/kmTgj1DundU)

[Sing-box精装桶小白一键脚本（三）：自建gitlab私有订阅链接一键同步推送全平台，WARP分流ChatGPT，SFW电脑客户端支持订阅链接](https://youtu.be/by7C2HU6-fU)

[Sing-box精装桶小白一键脚本（四）：vmess协议CDN优选IP多形态设置(详见说明图)](https://youtu.be/Qfm8DbLeb6w)

[Sing-box精装桶小白一键脚本（五）：集成oblivion warp免费vpn功能，本地WARP+赛风VPN切换分流(30个国家IP)](https://youtu.be/5Y6NPsYPws0)

[Sing-box精装桶五合一脚本重磅更新（六）：新增AnyTLS协议；本地IP订阅自动同步更新，通吃Clash/Mihomo、Sing-box与聚合节点](https://youtu.be/LF0-n6-Z6kI)

### VPS专用一键脚本如下：快捷方式：```sb```

```
bash <(wget -qO- https://raw.githubusercontent.com/redrohu/sing-box-yg/main/sb.sh)
```
或者
```
bash <(curl -Ls https://raw.githubusercontent.com/redrohu/sing-box-yg/main/sb.sh)
```

一键快捷命令现实本地IP订阅：```printf '3\n8\n1\n订阅密码' | sb```

一键快捷命令现实Argo临时隧道：```printf '3\n3\n1\n1' | sb```

一键快捷命令现实Argo固定隧道：```printf '3\n3\n2\n1\n固定密钥\n固定域名' | sb```

一键快捷命令现实域名分流：```printf '5\n2\n1\n后缀域名1 后缀域名2' | sb```


### Sing-box-yg脚本界面预览图（注：相关参数随意填写，仅供围观）

![1d5425c093618313888fe41a55f493f](https://github.com/user-attachments/assets/2b4b04a6-2de4-499a-afa1-ed78bccc50a8)

-----------------------------------------------------

### 二、Serv00/Hostuno一键三协议共存脚本（Serv00/Hostuno专用）：

* 目前免费Serv00使用代理脚本有被封账号的风险，收费版Hostuno不受影响，可正常使用

* 切勿与其他Serv00脚本混用！！！

* 引用[老王eooce](https://github.com/eooce/Sing-box/blob/test/sb_00.sh)、[frankiejun](https://github.com/frankiejun/serv00-play/blob/main/start.sh)相关功能，支持一键三协议：vless-reality、vmess-ws(argo)、hysteria2

* 主要增加reality协议默认支持 CF vless/trojan 节点的proxyip以及非标端口的优选反代IP功能

* 聚合通用节点分享，支持到22个节点：三协议各自三个IP，argo全覆盖13个端口节点，已添加不死优选IP

#### 相关说明及注意点请查看[甬哥博客说明与Serv00视频教程](https://ygkkk.blogspot.com/2025/01/serv00.html)

#### 视频教程：

[Serv00免费代理脚本最终教程（一）：独家支持三个IP自定义安装，支持Proxyip+反代IP、支持Argo临时/固定隧道+CDN回源；支持五个节点的Sing-box与Clash订阅配置输出](https://youtu.be/2VF9D6z2z7w)

[Serv00免费代理脚本最终教程（二）：Serv00不必再登录SSH了，部署保活融为一体，独家支持Github、VPS、软路由多平台多账户通用部署，四大方案总有一款适合你](https://youtu.be/rYeX1iU_iZ0)

[Serv00免费代理脚本最终教程（三）：多功能网页生成【保活+重启+重置端口+查看订阅节点】、随意重置端口功能；Github+Workers自动执行保活功能任你选！](https://youtu.be/9uCfFNnjNc0)

[Serv00免费代理脚本最终教程（四）：重大更新！支持Argo临时/固定隧道相互切换，实时更新节点信息；完美适配Serv00收费版Hostuno.com](https://youtu.be/XN6_vpz1NhE)

[Serv00免费代理脚本最终教程（五）：Github、VPS、软路由多平台脚本大更新！支持多功能网页，Cron内射保活+网页外射保活，任你选](https://youtu.be/tKaBdbU4G4s)

### Serv00/Hostuno-sb-yg一键脚本 

* Argo高度自定义：可以重置临时隧道; 可以继续使用上回的固定隧道; 也可以更换固定隧道的域名或token

```
bash <(curl -Ls https://raw.githubusercontent.com/redrohu/sing-box-yg/main/serv00.sh)
```

#### Serv00/Hostuno-sb-yg脚本界面预览图，仅限方案一的SSH端安装脚本（注：仅供围观）
![a6b776a094566ab14e88fdcd70ba9e9](https://github.com/user-attachments/assets/90a918ed-aec7-4a1f-8159-97f3acfd0092)


-----------------------------------------------------
### 感谢支持！微信打赏甬哥侃侃侃ygkkk
![41440820a366deeb8109db5610313a1](https://github.com/user-attachments/assets/5cd2d891-ae54-4397-8211-ac4c6d1099c9)

---------------------------------------
### 感谢你右上角的star🌟
[![Stargazers over time](https://starchart.cc/yonggekkk/sing-box-yg.svg)](https://starchart.cc/yonggekkk/sing-box-yg)

---------------------------------------
#### 声明：所有代码来源于Github社区与ChatGPT的整合
