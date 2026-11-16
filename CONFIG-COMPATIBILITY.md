# 官方 sing-box 配置格式适配

## 基线和范围

先恢复初始 fork `b13f943`（恢复提交 `fcdc532`，文件树完全相同），再修改配置生成逻辑。
不再引用 qichiyuhub/rule 的模板，也不保留此前的十入站模块。

- **启动菜单横幅、文字、0–16 编号及入口保持初始 fork 原样**。
- VPS 保留 VLESS Reality、VMess WS/Argo、Hysteria2、TUIC、AnyTLS。旧版 1.10 服务端仍为四协议。
- 修正范围包括 `sb.sh`、`serv00.sh`、`serv00keep.sh` 生成的 sing-box 服务端与客户端 JSON。
- Mihomo YAML 模板和通用节点分享协议不按 sing-box schema 改写。
- 本 fork 的脚本下载/自更新地址指向 `redrohu/sing-box-yg`，避免更新时重新取回未修正的上游脚本。

## 官方依据

核对日期：2026-11-16；当日稳定版 1.14.4。没有把 1.15 alpha 专属选项混入 1.14。

- [Change Log](https://sing-box.sagernet.org/changelog/)
- [Migration](https://sing-box.sagernet.org/migration/)
- [DNS](https://sing-box.sagernet.org/configuration/dns/)
- [Dial Fields / domain_resolver](https://sing-box.sagernet.org/configuration/shared/dial/)
- [HTTP Client](https://sing-box.sagernet.org/configuration/shared/http-client/)
- [Rule Set](https://sing-box.sagernet.org/configuration/rule-set/)
- [Cache File](https://sing-box.sagernet.org/configuration/experimental/cache-file/)
- [Hysteria2 / Chrome QUIC](https://sing-box.sagernet.org/configuration/outbound/hysteria2/)

| 涉及项 | 新格式与实际处理 |
|---|---|
| DNS 服务器 | 使用 `type: udp/tls/https/fakeip/local`；移除 Serv00 旧 `address` URL 与 `dns.fakeip` |
| 内部域名解析 | `route.default_domain_resolver` 显式指定引导 DNS，移除 Serv00 的 `dns.rules[].outbound`；不使用旧 `domain_strategy` |
| 嗅探 / DNS 接管 | 客户端先执行 `action: sniff`，再用 DNS 协议或端口 53 接管；不再写入站 `sniff` 字段 |
| WireGuard | 现代服务端使用 `endpoints`、`address`、`peers`；Serv00 根据实际内核版本生成，新内核不写旧出站格式 |
| 远程规则下载 | 1.14 使用 `http_clients` + `route.default_http_client`；仅为旧内核输出 `download_detour` |
| 1.14 DNS 缓存 | `optimistic`、`timeout`、`cache_file.store_dns` 都是有效新字段，保留；额外开启 `store_fakeip` |
| 旧缓存字段 | Serv00 不再生成 1.14 已弃用的 `independent_cache`；没有加入旧地址过滤/`store_rdrc` |
| 证书 | 原来的外部 Acme / ECDSA 自签证书及 `certificate_path`/`key_path` 仍受官方支持，无需强改 certificate provider |

另外修正两处规则顺序：Direct/Global 模式先于普通分流；Serv00 的 FakeIP A/AAAA 规则先于同域名集的普通远端 DNS 规则，避免永远匹配不到。
保留原版服务端的分流策略，不额外引入 AI 分流或十协议模板。

## 文件与版本

| 输出 | 目标版本 |
|---|---|
| VPS `/etc/s-box/sb.json` | 由安装的服务端内核决定：1.10.x，或 1.12+ |
| VPS `/etc/s-box/sb10.json` | 仅用于旧 1.10 内核，保留旧写法是有意的兼容分支 |
| VPS `/etc/s-box/sb11.json` | 历史文件名；现在是 1.12+ 服务端配置，不代表支持 1.11 AnyTLS |
| VPS `/etc/s-box/sbox.json` | 默认 1.14 客户端；不跟随服务端版本降级 |
| Serv00 工作目录 `config.json` | 根据实际已安装内核，兼容 1.10 旧出站或现代 endpoint 格式；写入前运行内核 `check` |
| Serv00 工作目录 `sing_box.json` 及发布订阅 | 默认 1.14 客户端 |

客户端版本和服务端版本互相独立；1.10 服务端可以由 1.14 客户端连接。

## 节点名称后缀（VPS）

入口：**主菜单 3「变更配置」→ 10「设置节点名称后缀」**。主菜单 0–16 和原子菜单 1–9 不变。

- 默认仍使用服务器主机名，例如 `anytls-debian`。
- 可设为 `oracle-US`，生成 `anytls-oracle-US`、`vless-oracle-US` 等；支持中英文字母、数字及 `.`、`_`、`-`，1–48 个字符，不接受空格或引号等特殊符号。
- 单独持久化到 `/etc/s-box/node_suffix.conf`，不修改系统 hostname。该文件只作为数据读取，不作为脚本执行。
- Sing-box `tag` 与组内引用、Mihomo 节点名与组内引用、VMess `ps`、其他分享链接备注和聚合订阅统一更新。中文 URI 备注做百分号编码。
- 设置后自动刷新本地导出；本地 HTTP 订阅引用同一份文件。Gitlab 远端订阅需在菜单 **9→2** 刷新推送，客户端再重新拉取订阅。
- 选择「2：恢复使用服务器主机名」可恢复默认；输入空后缀或选择返回不会修改。
- 修改前将旧设置和已有导出文件保存到 `/etc/s-box/node-name.bak.XXXXXX/`。恢复时将其中的 `node_suffix.conf` 放回；若备份没有此文件，删除当前后缀文件即回到默认，再用菜单9刷新。也可直接用设置菜单切回原后缀。
- 不修改服务端入站 tag、地址、端口、UUID、密码、证书，不重启服务。修改节点名可能导致客户端的手动分组或已保存的节点选择需重新指定。
- 该入口只适用于 VPS `sb.sh`，不改变 Serv00 独立脚本的命名方式。

默认生成的客户端配置需要 **1.14+ 客户端内核**。若客户端还停留在 1.12/1.13，可在启动脚本前设置：

```bash
export SB_CLIENT_VERSION=1.12  # 或 1.13；默认 1.14
sb
```

脚本会去掉目标旧客户端不认识的 1.14 字段，并使用旧版规则下载字段；不输出已移除的旧 DNS 格式。
不支持导出 1.10/1.11 客户端配置。指定不支持版本或 JSON 格式错误时，不覆盖已有客户端 JSON。

## 现有安装注意事项

- 本次仓库修改**不会自动修改已经部署的 VPS 配置**，也没有远程执行卸载/重装。
- 新安装按新版逻辑生成服务端配置；更新脚本后，菜单 9 刷新客户端文件/订阅。
- 菜单 7 只更新脚本，不会把现有服务端转换成其他协议或强制重生成 UUID。
- VPS 安装/重启前增加真实 `sing-box check`，失败不启动/重启；不是所有旧菜单编辑都已改为事务式回滚，手动修改前仍应备份。
- Serv00 服务端写入前检查，已有配置先保存 `config.json.bak.<时间>.<PID>`；端口修改按入站类型更新，不依赖 JSON 行号。
- VPS 历史菜单仍依赖 `sb10/sb11` 的部分固定行位置，新增服务端 DNS 放在相关位置之后，并有专门回归测试。不要手工格式化这两个存档再使用旧菜单。
- Hysteria2 1.14 默认模拟 Chrome QUIC，不支持服务器 Ed25519 证书；项目原版使用 ECDSA，不必关闭该新特性。自带证书时请使用 ECDSA/RSA。

## 验证与边界

测试使用真实 1.10.7、1.12.25、1.13.21、1.14.4 内核；运行原脚本的配置生成函数和 heredoc，而不是另写示例 JSON 代替。

```bash
SB_TEST_CORES=/path/to/cores python -m unittest discover -s tests -v
```

核心目录格式为 `sing-box-<版本>-linux-amd64/sing-box`；Windows 为同版本 `windows-amd64/sing-box.exe`，测试使用 Git Bash。
GitHub Actions 自动下载上述官方核心并保存生成文件与 `commands.json`（真实命令、输出及退出码）。

覆盖：现代/旧版服务端、默认及 1.12/1.13 客户端、四种 Argo 分支、Hysteria2 跳跃、原菜单全文及编号、Mihomo 模板不变、旧菜单行位置、Serv00 端口编辑、校验失败不覆盖及备份。
生成器测试不会运行完整安装、修改防火墙或实际重启系统服务。`check` 通过不等于已完成跨网端到端、真实规则下载、WARP 可用性或 Acme 续期测试。

回退代码：对本轮配置适配提交执行 `git revert <提交号>`，即可返回恢复后的初始 fork；不要 `reset --hard` 改写远端历史。旧十入站方案已保存在先前提交中，不再是当前生成路径。
