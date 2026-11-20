# XHTTP 固定隧道验证（2026-11-20）

## 实际部署

- 域名：`xhttp-rn.172892111.xyz`；Cloudflare 已发布应用回源 `http://127.0.0.1:18080`，路径留空。
- 协议：VLESS Encryption（X25519 认证）+ Vision + XHTTP `packet-up` + 边缘 TLS 443，不使用 REALITY。
- 服务：`sbox-xhttp-argo`、`sbox-xhttp-argo-tunnel`，均 active/enabled；源站仅监听 `127.0.0.1:18080`。
- 核心：Xray 26.11.9、cloudflared 2026.11.1；路由器实测 Mihomo `v1.19.34-openbox.20`。
- Token 仅在服务器受限文件中，权限 `600`；通过 `--token-file` 使用，不写入命令参数、订阅或本报告。

## 发现并修正的问题

1. 最初 Cloudflare 下发配置仍回源 8080，连接器日志显示 connection refused，客户端收到 502。用户改为 18080 后，连接器已收到新配置 version 2。
2. 初版源站 `noSSEHeader: true` 导致 cloudflared 缓冲流式响应，客户端超时。改为 `false`、保留 SSE 响应头后，同一客户端、同一节点真实 HTTPS 请求成功。[Xray 源码](https://github.com/XTLS/Xray-core/blob/main/transport/internet/splithttp/hub.go)明确将该响应头用于关闭 HTTP 中间层缓冲。脚本生成器已同步修正。
3. 隔离原 VMess Argo 的固定隧道进程检测和停止选择器，排除新目录中的 cloudflared，避免误判或停止新节点。

## 真实传输结果

通过 SSH 连接当前路由器，启动独立临时 Mihomo，仅加载从 VPS 实际导出的新节点；Windows curl 的 SOCKS 请求经 SSH 转发到这个路由器实例。不是本机直连目标，也未通过原代理组绕过测试节点。

| 测试 | 结果 |
|---|---|
| Cloudflare HTTPS trace | curl 退出 0，HTTP 200，出口为该 VPS 的 IPv6，`warp=off` |
| Google generate_204 | curl 退出 0，HTTP 204 |
| Vision | 路由器 debug 日志确认 TLS 1.3 识别及 Vision direct read/write |
| 本地协议传输 | 实际 Xray 源站 + Mihomo HTTP/1.1 packet-up + Encryption/Vision，128 KiB 随机数据 SHA256 一致 |
| 公网较大下载 | 经路由器新节点下载 1,048,576 字节，HTTP 200、curl 退出 0，单次耗时约 5.47 秒（含握手，不代表带宽上限） |
| 配置导出 | Mihomo YAML 新节点及三个代理组引用一致；聚合 URI 已加入；官方 sing-box JSON 不添加 XHTTP |
| Gitlab 订阅 | 已推送，并重新下载私有 Mihomo 订阅，确认新节点全部字段与 VPS 生成值一致 |

测试完成后停止临时路由器 Mihomo；未覆盖 Open-box 主配置、未替用户切换主代理组。用户在 Open-box 更新原订阅后，选择名称包含 `vless-xhttp-argo` 的节点即可。

**重复测试存在超时，不能标为稳定通过。** 首轮上述两个 HTTPS 目标均成功，后续重复时出现 Cloudflare 连接阶段 5–6 秒超时，以及个别已握手请求下载超时。单独测试域名解析出的两个 IPv4 和另一 Cloudflare 地址，未获得稳定改善，因此没有将猜测的“优选 IP”写入订阅。VPS 本机用实际 Xray 客户端经同一公开域名访问 generate_204 成功，耗时约 0.40 秒。这说明源站/隧道可用，当前路由器到 Cloudflare 的路径仍需进一步排查，不能简单归因于协议字段错误。

以上证明测试时连接可用，不是网速、长期稳定性或所有网站可用性的保证；不隐去后续失败结果。

## 原服务保持不变

部署前后原 Sing-box / 直连 XHTTP 服务 PID 一致，配置 SHA256 一致：

```text
/etc/s-box/sb.json
5758ce315c04e1eca83f620d64d6905e0f8024d4555d144bf1fca6d050d6ebc7
/etc/s-box/xhttp/config.json
242058bd6377de9db9a1d7df8a2d5faadec9fd94bdec7509e0ba21f10afb9128
```

原 `/usr/bin/sb` SHA256：`03c57b13d36799366b191a4db8b275b44904fd93184f0a4ea95ad5c27da85993`。新脚本 SHA256：`cc2d165ca73c37c53e0c849b7ecce8e8d1d8768c37d3d37d7075dd883e4d0668`。

## 回归及恢复

- Bash 语法检查、Git whitespace 检查通过。
- 最终全量 **77 项通过**（约403秒），包括 HTTP/1.1 真实传输、所有 Argo 导出分支、进程隔离、额外副本恢复/卸载隔离验证。该回归不等同于公网稳定性测试。
- VPS 备份目录：`/root/sbox-xhttp-argo-20261120/`，含原脚本、原配置压缩备份及 SHA256。备份包含凭据，不应公开。
- 只撤销新节点：脚本 **3 → 11 → 9 → 7**，不会删除旧 REALITY 或原五协议；刷新并推送订阅 **9 → 2**。Cloudflare 控制台的隧道和 DNS 需用户另行删除。
- 还原旧脚本：`install -m 755 /root/sbox-xhttp-argo-20261120/sb.original /usr/bin/sb`。不要直接覆盖整个 `/etc/s-box/`，以免抹去部署后的其他变更。
- 原备份中的配置已解压到额外目录并逐字节验证，未覆盖运行配置。服务器还保留 `rollback-new-node.sh`，只撤销新节点并还原旧脚本/版本标记；已在本机额外副本中重定向路径及模拟服务管理验证，未对线上执行回滚。回滚后仍需 **9 → 2** 更新远端订阅。新节点完整备份 `xhttp-argo.final.private.tar.gz` 含 Token，权限受限。
- 本地原件、逐条命令及原始 stdout/stderr/退出状态：`C:\Users\17289\AppData\Local\Temp\sbox-xhttp-argo-20261120-145657\`。该目录含敏感测试配置，仅供本机检查，未加入 Git。

## 独立优选地址更新（fork.13）

- 采用独立设置，不跟随 VMess 优选地址，入口 **3 → 11 → 9 → 8**；支持手动指定域名、IPv4、IPv6或恢复默认。设置文件 `/etc/s-box/xhttp-argo/server.conf`，不自动测速。
- 仅更改客户端连接地址；Mihomo `servername` / `xhttp-opts.host`、Xray `tlsSettings.serverName` / `xhttpSettings.host`、URI `sni` / `host` 始终使用原隧道域名。IPv6 URI 使用方括号。
- 本地生成器验证覆盖四个 VMess Argo 分支，逐项比较设置前后其他协议节点；同时验证新节点三个代理组引用、重复刷新、恢复默认、错误地址和刷新失败后的设置/导出回滚。
- VPS 已使用实际菜单完成“设置为当前隧道域名 → 恢复默认”验证，没有试填未知优选 IP。前后客户端导出逐字节相同，原五协议、直连 XHTTP、Argo 源站配置及四个服务 PID 均不变。当前仍使用原隧道域名。
- 本次没有更改 Cloudflare 路由、回源 HTTP 版本或客户端协议模式，不宣称解决此前公网抖动。
- VPS 原脚本/版本标记和节点备份：`/root/sbox-xhttp-argo-address-20261120/`；变更菜单也会单独备份受影响设置及导出。仅撤销优选地址可在同一菜单选择 **2：恢复默认隧道域名**。需要回退脚本时，使用该目录的 `sb.original` 和 `v.original`，不要覆盖整套服务器配置。
- 本次脚本原 SHA256：`cc2d165ca73c37c53e0c849b7ecce8e8d1d8768c37d3d37d7075dd883e4d0668`；新 SHA256：`e73056748098140b03ff98829f7ef22557bff46628269de3e1bbab5944f07221`，本地与 VPS 一致。
- 本次验证记录和原件：`C:\Users\17289\AppData\Local\Temp\sbox-xhttp-argo-address-g9_l7ojd\`；配置备份含客户端凭据，不加入 Git。
- 最终全量 **81 项测试通过**（约528秒），包括实际 Xray/Mihomo 传输、IPv4/IPv6/域名导出、独立设置、恢复默认及刷新失败回滚；Bash 语法及 Git whitespace 检查通过。这些结果不等于新优选地址的公网测速。

## 后缀清除功能（fork.14）

- 菜单 **3 → 10 → 5** 新增“清除后缀（不显示主机名）”。原 **1–4** 编号和含义保持不变；前缀仍可独立保留。
- 通过 `/etc/s-box/node_suffix.disabled` 标记无后缀模式。设置自定义后缀（1）或恢复主机名（2）会自动退出该模式；原 `node_suffix.conf` 不会被误删。
- 实际验证覆盖服务端版本 1.10/1.14、Argo none/fixed/temporary/both、Sing-box/Mihomo、两种 XHTTP 节点和分享 URI；确认无尾随空格、配置检查通过、服务端参数不变。新增专项 3 项及原有测试，最终测试记录在本机临时目录。
- VPS 已部署 fork.14；四个现有服务均 active，原配置 SHA256 校验通过，PID 未变化。部署没有清除当前用户已有后缀；需要使用时进入菜单操作即可。
- 原脚本/版本备份：`/root/sbox-clear-suffix-20261120/`；本地备份和命令记录：`C:\Users\17289\AppData\Local\Temp\sbox-clear-suffix-dyn1vtgh\`。备份含订阅/客户端凭据，不加入 Git。
