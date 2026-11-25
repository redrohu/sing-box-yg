# [Bug] VLESS XHTTP + REALITY + Encryption + Vision 导入后丢失 encryption，Mihomo 无法连接

## 问题概述

Open-box 导入包含 `encryption` 的 Clash/Mihomo 订阅后，该字段没有保留到内部节点数据，也没有出现在实际生成的 Mihomo 配置中。对于服务端启用了 **VLESS Encryption + XHTTP + REALITY + Vision** 的节点，结果是 REALITY 认证成功，但 Vision 建立连接失败。

刷新订阅、重新导入均无法解决。使用设备上同一个 Mihomo 二进制，在独立配置中仅补齐对应的 `encryption` 后，可以访问同一服务端。

> 本报告已脱敏。示例中的地址、UUID和密钥为占位数据，不能直接用于连接。没有附带 SSH 密码、真实节点凭据、订阅地址或数据库文件。

## 环境

| 项目 | 版本 / 信息 |
|---|---|
| 验证日期 | 2026-11-19 |
| Open-box | `v0.1.459` |
| Open-box sourceCommit（安装包 meta.json） | `4a519a5b6a144323c362c370e6b01c95ff9e3f57` |
| 路由器系统 | ImmortalWrt `24.10.4` |
| 内核 / 架构 | Linux `6.18.18.c1191-trim` / aarch64 |
| Open-box 当前代理内核 | Mihomo `v1.19.34-openbox.17`，linux arm64，Go `1.26.11` |
| 面板 Node.js | `24.18.0` |
| 服务端内核 | Xray `26.11.9` |
| 导入方式 | Clash/Mihomo YAML 订阅 |
| 服务端组合 | VLESS + XHTTP + REALITY + VLESS Encryption + `xtls-rprx-vision` |
| XHTTP | `path: /`，`mode: auto` |

## 复现步骤

1. 准备一个已启用 VLESS Encryption、Vision、XHTTP 和 REALITY 的 Xray 服务端。
2. 确认对应的原始 Mihomo 节点配置可以独立连接，并包含有效的 `encryption` 和 `flow`。
3. 将该节点的 Clash/Mihomo YAML 订阅导入 Open-box，使用 Mihomo 内核。
4. 对该节点进行延迟测试或 HTTPS 请求，连接失败。
5. 查看实际生成的 `/opt/open-box/etc/mihomo.yaml`：节点保留了 `flow`、REALITY 和 XHTTP 参数，但缺少 `encryption`。
6. 刷新或重新导入订阅，问题仍然存在。

### 脱敏输入示例

以下展示字段结构；`encryption` 必须使用与服务端 `decryption` 配对的真实客户端值。

```yaml
proxies:
  - name: xhttp-encryption-vision-test
    type: vless
    server: 192.0.2.1  # 文档地址，非真实服务端
    port: 6443
    uuid: 00000000-0000-4000-8000-000000000001
    network: xhttp
    udp: true
    tls: true
    servername: www.cloudflare.com
    client-fingerprint: chrome
    skip-cert-verify: false
    reality-opts:
      public-key: "<REDACTED_REALITY_PUBLIC_KEY>"
      short-id: "<REDACTED_SHORT_ID>"
      support-x25519mlkem768: true
    xhttp-opts:
      path: /
      mode: auto
    encryption: "mlkem768x25519plus.native.1rtt.<REDACTED_CLIENT_VALUE>"
    flow: xtls-rprx-vision
```

### 实际字段变化

```text
原始订阅 YAML：
  encryption: 有
  flow: xtls-rprx-vision
  network: xhttp
  xhttp-opts.path: /

Open-box 内部节点 fields：
  uuid、flow、transport、tls
  缺少 encryption

Open-box 生成的 Mihomo 节点：
  flow、network、tls、reality-opts、xhttp-opts 均保留
  缺少 encryption
```

已将生成配置的 UUID、REALITY 公钥、Short ID、SNI、端口和路径与服务端逐项核对；这些参数一致，`support-x25519mlkem768` 也为 `true`。

## 预期行为

- 在订阅导入、内部存储和 Mihomo 配置生成过程中保留客户端 `encryption`，使其与服务端配置对应。
- 实际运行配置、节点探测使用的临时配置以及订阅再导出保持参数一致。
- 对无法支持的组合给出明确提示，不静默丢弃连接所必需的字段。
- 普通 `encryption: none` 或未配置 Encryption 的节点继续按原行为处理。

**这里需要透传的是客户端 `encryption`，不是服务端 `decryption`，也不是 REALITY 私钥。**

## 实际错误日志

以下来自同机实际测试，已移除时间、实际地址和无关连接信息：

```text
REALITY Authentication: true, AEAD: *gcm.GCM
vision: not a valid supported TLS connection: *xhttp.Conn
connect error: failed to use vision, maybe "tls" is not enable and "encryption" is empty
curl: (35) TLS connect error: error:00000000:lib(0)::reason(0)
```

Open-box 正在运行的 Mihomo 控制接口节点探测也返回：

```json
{
  "message": "<SERVER>:6443 connect error: failed to use vision, maybe \"tls\" is not enable and \"encryption\" is empty"
}
```

## 同机对照测试（已实际运行）

为了排除服务端不可达或内核不支持，使用路由器上原有的 `/opt/open-box/bin/mihomo`，在独立临时目录启动只含测试节点的本地 SOCKS 代理。没有替换主内核或修改服务端。两组配置仅有 `encryption` 的有无不同。

| 测试 | 原配置：缺少 encryption | 补上对应 encryption |
|---|---|---|
| Mihomo 配置检查 | 成功 | 成功 |
| REALITY 认证 | 成功 | 成功 |
| Vision 连接 | 失败，出现上述日志 | 成功，出现 Vision 收发日志 |
| 经 SOCKS 请求 Cloudflare HTTPS trace | curl 退出 `35` | curl 退出 `0` |
| HTTPS / 出口验证 | 请求失败 | TLS 1.3，出口为 VPS IPv6 |

测试请求命令结构如下：

```sh
curl --noproxy '' \
  --proxy socks5h://127.0.0.1:47791 \
  --connect-timeout 8 --max-time 20 -fsS \
  https://www.cloudflare.com/cdn-cgi/trace
```

注意 `--noproxy ''` 用于确保请求经过显式 SOCKS 代理。早期一次使用 `--noproxy '*'` 的直连结果已排除，不作为节点可用性证据。上述表格只采用修正后的实际代理测试结果。

成功组日志节选：

```text
REALITY Authentication: true, AEAD: *gcm.GCM
XTLS Vision write padding: command=0, ...
[TCP] ... --> www.cloudflare.com:443 match Match using xhttp-diagnostic
XTLS Vision found TLS 1.3, ...
XTLS Vision direct write start
XTLS Vision direct read start
```

这说明设备上已有的 Mihomo 内核能处理该组合，直接失败与字段在 Open-box 配置链路中丢失一致，而不是仅凭版本号推测支持。

## 建议排查位置（安装包观察，供维护者定位）

在 `v0.1.459` 安装包的 `panel/server/index.mjs` 中观察到：

1. Clash VLESS 转换函数（压缩后的名称 `TO.vless`）构造内部 `fields` 时保留了 `uuid`、`flow`、`transport`、`tls`，但未见透传 `encryption`。
2. VLESS 分享 URI 转换函数（`wO`）未见读取 query 中的 `encryption`。本次用户真实导入方式是 YAML；URI 情况是安装包代码观察，不是已完成的独立端到端复现。
3. Clash 再导出函数（`Eh`）的通用字段列表不含 `encryption`；有再次丢字段的风险。
4. Mihomo 正式配置及探测配置依赖原生核心的 `mihomoGroups` / `mihomoProxies`。建议维护者在修复导入后验证这两处也能透传字段；本报告没有在补齐内部数据后单独证明原生生成器是否仍会丢失字段。

上述符号是当前发行包的压缩名称，后续版本可能变化。建议同时增加回归测试：YAML/URI 导入、内部存储、正式配置、探测配置、再导出，以及刷新和重新部署后的参数一致性。

## 当前临时解决方式及限制

目前通过一个**独立、仅监听 127.0.0.1 的 Mihomo 客户端实例**加载完整节点，Open-box 通过本机 SOCKS5 节点接入。VPS 保留完整协议，不降级为普通 XHTTP。

已验证 HTTPS 请求、兼容服务重启、面板重启，以及刷新兼容订阅和原始远端订阅后仍可连接。这只是绕开当前字段转换问题的临时方案，不代表 Open-box 原有导入链路已修复；也没有进行整机重启、UDP 功能、吞吐量或长期稳定性测试。

本地曾尝试补齐导入和输出透传逻辑，但安装包完整性校验拒绝启动。该尝试已撤回，原入口、Mihomo 二进制和原生核心的 SHA256 均与备份一致，面板恢复正常；未绕过完整性或授权检查。因此希望由维护者在正式构建中修复。

## 影响范围说明

本次已确认影响的是 **VLESS + XHTTP + REALITY + VLESS Encryption + Vision** 的 YAML 订阅导入链路。没有据此判断普通无内层 Encryption 的 XHTTP、其他传输或所有 VLESS 节点都不可用。

如需补充信息，可以提供进一步脱敏的字段比较和日志；出于安全考虑，不在公开 Issue 中提供真实订阅、客户端认证值或服务端私钥。
