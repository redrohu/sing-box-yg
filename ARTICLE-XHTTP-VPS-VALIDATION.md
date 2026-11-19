# 文章同款 XHTTP 实机验证（2026-11-19）

## 目标与实现

按用户指定的 [文章](https://www.cunzhangblog.com/vlessxhttp)，在本项目脚本中实现 **VLESS + XHTTP + REALITY + VLESS Encryption（X25519认证）+ Vision**，不安装面板。文章正文已实际下载核对：选择第一个 X25519 认证选项、XHTTP 默认路径、REALITY 和客户端 `xtls-rprx-vision`。

- 新部署默认文章模式，也可选择普通 XHTTP + REALITY。
- 已有普通节点通过 **3→11→8** 升级，先备份，配置及服务验证失败时尝试恢复。
- Xray `vlessenc` 第一组产生独立的 Encryption 凭据；不混用 REALITY 密钥。服务端 `decryption` 仅留在服务器，客户端导出对应 `encryption`。
- 升级保留端口、UUID、REALITY 凭据，添加 Vision 并将路径改为 `/`；旧客户端配置必须更新订阅。

## VPS 实际结果

通过用户指定 SSH 密钥的受限副本执行真实菜单 **3→11→8**，未重新安装现有五协议。远端升级前备份为 `/root/sbox-article-backup-20261119T081846Z`，菜单内部备份为 `/etc/s-box/xhttp-article.bak.OhNg3M`；均含敏感信息，不可公开。

- 独立 Xray v26.11.9：`sbox-xhttp` 为 `active/enabled`，监听 TCP **6443**。部署 SSH 已退出，后续重新连接仍运行。
- 服务端启用非 `none` 的 VLESS Encryption、`flow: xtls-rprx-vision`、XHTTP `path: /`、`mode: auto`、外层 REALITY。
- 服务端、Xray 客户端 `run -test` 均为 `Configuration OK`；现有 sing-box 服务端 `check` 退出0。
- `sb.json`、`sb10.json`、`sb11.json` 的 SHA256 与升级前记录完全一致；独立 XHTTP UUID 和 REALITY 参数也保持不变。
- 实际 `clmi.yaml` 包含1个 XHTTP 节点，三个组各引用一次；`encryption`、`flow`、路径与 Xray 客户端逐项一致。聚合 `jhsub.txt` 包含当前链接；没有将 XHTTP 写入官方 sing-box 客户端配置。
- 服务端 `decryption` 和 REALITY 私钥未出现在 Mihomo YAML；新增密钥文件权限为600。
- 使用真实导出的节点启动本地 Mihomo v1.19.34，经该公网节点请求 Cloudflare HTTPS trace：curl退出0，TLS1.3，出口IPv6与VPS一致。没有进行吞吐测速、长期稳定性或VPS重启测试，不承诺比普通模式更快。

## 本地验证与记录

本次完整测试共 **73项通过**：配置16、Mihomo8、前缀7、空格4、后缀8、符号4、更新11、XHTTP15。包括真实 Xray 和 Mihomo 的文章模式回环传输、既有节点升级保留参数、失败回滚、导出一致性。Bash语法和git差异检查通过。

本地完整测试、原始文件及SHA256记录：`C:\Users\17289\AppData\Local\Temp\sbox-article-xhttp-20261119-161334`，其中 `final-results.json` 保存实际命令、原始输出和退出码，`summary.json` 为计数；`restoration-check.json` 记录在额外副本反向应用补丁后的恢复校验。

远端部署和公网测试日志在受限目录 `C:\Users\17289\AppData\Local\Temp\sbox-vps-check-2b7a1199d01d4b899d61a5ea4cb87321`：`article-upgrade.log`、`article-verify-remote.json`、`article-public-result.json`、`article-mihomo.log`。其中客户端导出含认证信息，不加入Git。验证脚本曾因Windows换行和默认GBK解码失败，修正为LF输入和UTF-8后完成上述验证；这两次失败不是远端服务故障。

## 恢复

升级失败时菜单会尝试从内部备份恢复；此次成功升级的备份继续保留。若要恢复普通模式，应先停止 `sbox-xhttp`，从内部备份 `xhttp/` 恢复整个原目录并移除新增的 `encryption.key`、`decryption.key`，使用原脚本检查配置并重启，再刷新订阅；不能只恢复旧订阅文件而不恢复服务端。原五协议没有修改，无需恢复。

本次源码改动另保存二进制差异补丁，并在额外副本反向应用、比较原文件SHA256。恢复源代码不等于恢复VPS节点，应分别处理。指定原始SSH私钥未改动；受限临时身份副本仍需在不再需要时清理，未将密钥或含凭据日志提交。
