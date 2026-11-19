# Mihomo XHTTP + REALITY YAML 导出验证

## 本次范围

- 从当前独立 Xray 入站配置、公钥和 `server_ipcl.log` 读取参数，加入 `clmi.yaml` 的节点列表及负载均衡、自动选择、手动选择三个组。
- 四种 Argo 状态（无/固定/临时/同时存在）和 sing-box 1.10/现代服务端分支均支持；节点仍直连独立 Xray，不经过 Argo。
- JSON 流式对象作为合法 YAML 节点，名称和路径由 jq 转义；IPv6去掉地址方括号；不混用原五协议的 UUID，不导出私钥，不添加 Vision flow。
- 未部署或卸载后刷新时，不生成该节点及组内引用；不向 sing-box `sbox.json` 加入 XHTTP。
- 更新 README、兼容说明、CI 与测试；不修改原五协议服务端配置，不重启服务，不修改 Serv00 脚本。

## 实际观察及修复

修改前生成四种 Argo 状态的 YAML：独立 Xray 配置已存在，但 YAML 没有 XHTTP 节点。

初次接入后的 Mihomo 配置检查成功，但实际握手失败：`x509: certificate signed by unknown authority`。Xray日志显示连接被转发到伪装目标，未完成 REALITY 认证。

核对官方源码后，导出中显式设置 `reality-opts.support-x25519mlkem768: true`。Mihomo 默认会移除此密钥交换信息，而本脚本固定的 Xray v26.11.9 要求该信息。设置后同一本地测试完成 REALITY 握手和实际数据传输。没有降低 `skip-cert-verify`、没有修改服务端密钥/协议来掩盖失败。

依据：[Mihomo TLS选项](https://wiki.metacubex.one/config/proxies/tls/)、[Mihomo XHTTP选项](https://wiki.metacubex.one/config/proxies/transport/)、[Mihomo v1.19.34 REALITY客户端](https://github.com/MetaCubeX/mihomo/blob/v1.19.34/component/tls/reality.go)。

## 已验证

完整回归按模块独立进程执行：**64项全部通过**，耗时148.266秒，无跳过；新增Mihomo专项7项均执行成功。

- 真实 Mihomo **v1.19.34 Windows amd64 compatible**；下载包 SHA256 与 GitHub release API 的 digest 一致：`cd6738d4648cc1a5f48049a1343b697ab510889d648f045c5c780fc1ab443a79`。
- Mihomo `-t` 检查成功。测试为避免下载远端 geodata，仅将已有分流规则替换为 MATCH 并关闭控制器，保留全部生成节点和代理组；不是整个原始规则集的在线下载测试。
- 本地 OpenSSL TLS1.3/H2伪装目标 + Xray **v26.11.9** 服务端 + Mihomo 客户端 + SOCKS5 + HTTP：下载 **212992字节**，与源数据逐字节一致；SHA256：`9c1e6d3aef004209fa02b7db20efab8e41f164484b20247ff353f7ea6f591669`。仅测试配置放行127.0.0.1，不改变生产出站私网保护。
- 覆盖四种 Argo 状态、两个服务端版本分支、IPv6、中文/#/|名称、特殊路径、重复刷新、卸载后移除引用、前缀变更后的聚合订阅刷新、缺失公钥时不覆盖已有导出。
- 与本次修改前源码比较：未部署XHTTP时，8个分支的 `clmi.yaml` 和 `sbox.json` 均逐字节一致。
- Bash语法检查、CI YAML解析、`git diff --check`通过。

## 可复查记录

本次日志/备份根目录：`C:\Users\17289\AppData\Local\Temp\sbox-mihomo-xhttp-20261119-143053`。

- `original/`、`original-sha256.json`：本次开始时已有文件的完整备份及SHA256，包含上一次已增加的XHTTP功能，恢复不会退回到未接入XHTTP的初始版本。
- `baseline-commands.json`、`baseline/`：修改前行为记录。
- `new-tests.log`、`debug-transport.log`：初次握手失败的实际输出；`fixed-transport.log`：修复后单独传输测试。
- `new-final.log`：新增测试首轮完整运行；其中聚合订阅卸载刷新用例因测试框架开启`set -e`、旧分享函数读取可选不存在文件而退出。改为与实际调用方一致的条件调用后，`refresh-retest.log`确认通过；未改动旧分享函数行为来隐藏测试错误。
- `unchanged-output-checks.json`、`unchanged-commands.json`：无XHTTP时的字节一致性验证。
- `run_all.py`、`final-run.json`、`final-summary.json`、`test_*.final.log`、`final-results/`：最终完整测试、命令、原始输出、退出码、实际运行配置和负载文件。
- `changes.patch`：仅本次请求的代码/文档/测试差异。
- `restoration-check.json`：在额外副本反向应用补丁、恢复到本次开始版本的校验；最终工作文件保留。

## 使用与恢复

在VPS使用更新后的 `sb.sh`，主菜单 **9** 刷新，再在Mihomo客户端更新订阅；Gitlab远端订阅使用 **9→2** 刷新推送。推荐使用已验证的Mihomo v1.19.34或更新且支持这些选项的内核。

撤销本次代码改动：确认没有后续新编辑后，先用 `git -c core.autocrlf=false apply --reverse --check changes.patch` 检查，再用相同 `core.autocrlf=false` 选项反向应用补丁（保留LF换行）；也可只恢复 `original/` 中相应文件并删除本次新增测试/说明。不要用整仓 `git reset` 丢弃上一次XHTTP接入或用户其他改动。

未连接用户VPS，未做公网网速/云防火墙测试；Linux CI已配置但未在GitHub执行。此结果不代表公网速度提升。

本次最终 `sb.sh` SHA256：`de18ac4069529e7fe880ef3350d50004a14c6f626f17e8ba40ef2fc9e5de338d`。
