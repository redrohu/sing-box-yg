# XHTTP + REALITY 接入验证（2026-11-19）

> 本文记录首次 XHTTP 接入时的历史验证。后续已补充 Mihomo YAML 导出及真实 Mihomo 传输验证，当前结果见 [MIHOMO-XHTTP-VALIDATION.md](MIHOMO-XHTTP-VALIDATION.md)。

## 改动

- `sb.sh` 新增独立 Xray sidecar，入口 **3→11**。已有主菜单0–16和五协议入站保持不变。
- 生成 VLESS/XHTTP/REALITY（无 Vision flow）、独立密钥、UUID、路径；导出 Xray JSON 和 URI，并合入通用聚合订阅。
- 提供 systemd / OpenRC 服务模板、SHA256下载校验、启动前配置检查、失败清理和卸载；不向 sing-box/Mihomo JSON/YAML 写入 XHTTP。
- 更新 README、兼容说明和 CI；新增8项测试，并将原菜单测试的范围断言由0–10更新为0–11。

## 已执行

环境：Windows，Git Bash，Python 3.12；真实 Xray v26.11.9 Windows amd64。

1. 修改前执行 `python -m unittest discover -s tests -v`：49项通过，耗时264.556秒。
2. 完整回归初次执行57项，其中56项通过、1项因原测试仍要求子菜单范围0–10而失败；同步更新为新增功能后的0–11。最终按模块独立进程并发执行全部57项：全部通过，耗时116.438秒，详见`final-run.json`。
3. 新增测试执行 `python -m unittest discover -s tests -p test_xhttp.py -v`：8项通过（最终独立运行18.188秒）。
4. 真实 Xray `run -test -config`：生成的服务端和客户端配置均退出0。
5. 真实传输：本地 OpenSSL TLS1.3/H2目标 + Xray服务端 + Xray客户端 + SOCKS5 + HTTP，下载253952字节，与原始负载逐字节一致。SHA256：`38138069b95846cef596fecd047b0668570e6ba917548389bf662305d4f95294`。只在测试配置中放行127.0.0.1目标，不关闭部署配置的默认私网保护。
6. 安装流程使用真实Xray密钥生成/配置检查、模拟下载/解压和服务管理，验证成功、下载失败、服务启动失败回滚；这些不是Linux实机部署测试。
7. Git Bash对3个原有脚本执行`bash -n`，CI YAML解析、`git diff --check`通过。
8. 官方Windows Xray下载包SHA256与同release摘要匹配：`1262522266337b824f07beb8e1375786b437683b3890105469088f8e17e0a69d`。

## 验证记录位置

本次本机日志根目录：`C:\Users\17289\AppData\Local\Temp\sbox-xhttp-validation`。

- `baseline.log`：修改前测试输出。
- `xhttp-final.log`、`updated-tests/xhttp/commands.json`：最终新增测试、逐项命令/原始输出/退出码；所运行的生成脚本与配置保存在同目录各用例子目录。
- `full.log`、`full-results/`：首次完整回归输出（含过期断言失败）；`final-run.json`、`test_*.final.log`、`final-results/`：最终57项全部通过的逐模块命令、退出码、输出和生成配置。
- `original-sha256.json`、`*.original`：原始摘要及备份。
- `changes.patch`：本次完整代码、测试、说明文件差异。
- `restoration-check.json`：在额外副本上复制原始备份恢复后，5个修改前已有文件SHA256均与备份一致；未覆盖最终修改文件。

## 恢复

源码：查看`changes.patch`并反向应用本次改动，或将备份中的`sb.sh.original`、`README.md.original`和`CONFIG-COMPATIBILITY.md.original`复制回对应文件。CI及原节点后缀测试分别有`config-tests.yml.original`、`test_node_suffix.py.original`备份，也可按Git差异撤销；删除新增测试及本说明。仅在没有后续新改动时整文件恢复，避免覆盖其他工作。

部署：**3→11→7**仅移除独立XHTTP服务，保留原五协议。恢复已卸载节点的密钥/配置方法见README；此处未执行真实VPS卸载恢复。

## 尚未验证

没有连接用户VPS，未验证Linux systemd/OpenRC实机启停、自启、云防火墙、目标域名可达性、公网握手或公网吞吐。CI配置已更新但未在GitHub运行。不保证新增协议一定比现有节点更快。没有修改Serv00脚本，没有提交或推送Git。

最终脚本SHA256：`34fe67ffb0a07d49d513df8cb2066def2ed35c185489c9c175a9d8fda17efd1f`。
