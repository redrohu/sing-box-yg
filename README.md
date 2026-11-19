### 一、Sing-box-yg精装桶一键五协议共存脚本（VPS专用）
### 二、Serv00/Hostuno-sb-yg多平台一键三协议共存脚本（Serv00/Hostuno专用）

> 本 fork 已从初始版本重新适配官方 sing-box 新配置格式，默认导出 1.14 客户端配置；保留原菜单和协议，不使用第三方十入站模板。版本兼容、更新说明及验证范围见 [CONFIG-COMPATIBILITY.md](CONFIG-COMPATIBILITY.md)。

### 可选：VLESS + XHTTP + REALITY（VPS）

安装现有 Sing-box 后，运行本版本 `sb.sh`，选择 **3 → 11 → 1** 部署独立 Xray 服务。
原五协议保持不变，XHTTP 不经过 Argo/CDN，不保证比现有节点更快。

- 独立 TCP 端口默认 443；已占用则换端口，并在云安全组及系统防火墙放行。不要占用已有 Reality/HTTPS 端口。
- 目标域名应从 VPS 可达、支持 TLS 1.3 和 H2；默认 `www.cloudflare.com` 不是可用性保证，部署后应实测。
- 下载官方 Xray **v26.11.9**（固定版本），核对同一官方 release 的 SHA256 摘要，服务端和客户端配置均通过内核检查后启动；失败清理本次安装，不修改现有 Sing-box 入站。
- 支持 Linux amd64、arm64、armv7，systemd/OpenRC；需要 `curl jq unzip openssl sha256sum ss`。Alpine 缺少 `ss` 时安装 `iproute2`，缺少 `sha256sum` 时安装 `coreutils`。
- 服务名 `sbox-xhttp`；配置和密钥在 `/etc/s-box/xhttp/`。`client.json` 是 Xray 客户端配置（本地 SOCKS5 `127.0.0.1:10808`），`share.txt` 是导入链接。请勿公开服务端配置、密钥或订阅链接。
- 分享链接自动加入通用聚合订阅 `jhsub.txt`；已部署时也自动写入 **Mihomo `clmi.yaml`**，并加入负载均衡、自动选择和手动选择三个代理组。支持 XHTTP 的新版 Mihomo 可直接使用（验证版本 **v1.19.34**）。未部署或卸载后刷新，不生成该节点及组内引用。
- 官方 sing-box 当前不支持 XHTTP，因此 **不会写入 `sbox.json`**。Mihomo 节点使用独立 Xray 服务的 UUID、端口、公钥、Short ID、路径及 REALITY SNI，支持 IPv4/IPv6 和节点名称前后缀，不使用 Vision `flow`，不导出私钥。
- 为兼容本脚本固定的 Xray v26.11.9，导出时显式启用 `reality-opts.support-x25519mlkem768: true`；否则 Mihomo 默认移除该密钥交换信息，可能导致 REALITY 握手失败。不要通过关闭证书校验来绕过。
- 更新本版本脚本后，通过主菜单 **9** 刷新本地节点/订阅，再在客户端更新订阅；Gitlab 远端订阅需 **9→2** 刷新推送。
- 通过 **3 → 11** 查看节点、重启、停止、状态、日志或卸载。独立 UUID、路径和密钥，不跟随原五协议的 UUID/端口/证书/启停菜单；使用独立直连出站，不继承 Sing-box 的 Warp/域名分流策略。主菜单2完整卸载时一并移除。
- 卸载前可用 `umask 077; tar -czf /root/sbox-xhttp-backup.tar.gz -C /etc/s-box xhttp` 备份。恢复时先通过本菜单重新部署服务、停止它，再将备份中的 `xhttp/` 解回 `/etc/s-box/`，用 **3 → 11 → 3** 检查并启动，随后 **3 → 11 → 2** 刷新节点。备份含私钥，须妥善保管；恢复原端口前检查冲突。

配置依据：[Xray 传输配置](https://xtls.github.io/config/transport.html)、[XHTTP](https://xtls.github.io/config/transports/splithttp.html)。本功能仅接入 VPS `sb.sh`，未修改 Serv00 脚本。

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
