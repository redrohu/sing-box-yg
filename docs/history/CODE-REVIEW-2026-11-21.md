# 代码与逻辑审查（2026-11-21）

> 归档说明（2026-11-25）：本文已从仓库根目录移至 `docs/history/`。文中 `D:/Desktop/sing-box-yg/review-artifacts/...` 是维护者本机的审查证据与恢复工具，未纳入 Git；文中 `sb.sh` 行号对应当时版本。

## 范围与结论

- 审查基线：Git `44d47be`（完整提交号、源码 SHA256 见文末证据目录的 `manifest.json`）。下列行号对应这一版本。
- 覆盖：`sb.sh` 的配置生成、订阅发布、更新、卸载、旧 Argo 和新增 XHTTP；Serv00 安装/保活脚本、Node 管理服务、Worker 和 GitHub Actions。
- 方法：静态阅读 + 抽取真实函数的本地失败注入。网络、服务管理、进程终止和系统 crontab 均使用替身或路径隔离；没有连接 VPS/路由器，没有修改源码或线上服务。
- **应先修复失败处理和服务边界，再做去重复重构。** 目前最突出的风险是“失败仍显示成功”“未校验就覆盖可用文件”“操作范围超出本项目”。
- 新增独立 XHTTP / XHTTP + Argo 部分，本轮未发现可确认的协议配置错误；这不代表已经重新验证公网路由、在线节点或测速结果。

优先级：P1 = 可能导致不可用、错误发布、无关业务受影响或敏感信息泄露；P2 = 特定分支的功能/可靠性问题。复现结果不等于已经在用户服务器上发生。

## 一、优先修复的问题

### 1. [P1] 脚本更新先删旧文件，下载失败仍报成功

**位置：** [sb.sh:4711–4723](D:/Desktop/sing-box-yg/sb.sh#L4711)

`lnsb()` 先删除 `/usr/bin/sb`，随后下载到正式路径；没有检查 curl 返回值、HTTP 状态、脚本语法。更新时还使用 `--insecure`。`upsbyg()` 不检查更新结果，继续写版本文件并提示升级成功。

**本地复现：** 模拟 curl 写入空文件后返回 28（超时），最终脚本、版本标记均变为 0 字节，函数退出码仍为 0，并输出“Sing-box-yg安装脚本升级成功”。

**建议：** 同目录临时文件下载，启用 TLS 校验和 `curl -f`、合理超时，执行 `bash -n`，必要时校验发布摘要；全部成功后原子替换，最后更新版本标记。失败保留旧脚本。

### 2. [P1] 内核更新失败会沿用旧二进制、覆盖配置并宣称成功

**位置：** [sb.sh:4764–4777](D:/Desktop/sing-box-yg/sb.sh#L4764)

下载、解压、移动均未检查结果。之后仅检查正式路径是否有 `sing-box`，已有旧内核也能通过；随后删除现用 `sb.json` 并从模板重建。即使重启失败，仍会输出升级成功。

**本地复现：** 下载返回 28 且留下损坏压缩包，tar/mv 失败；旧内核仍为 `1.14.4`，现用配置却由 `CURRENT_CONFIG` 变为 `TEMPLATE_CONFIG`。模拟重启失败后，仍输出“成功升级/切换”，最终退出码 0。

**建议：** 在暂存目录下载、验摘要、解压、核对实际版本，使用新内核预检配置；保留旧二进制及配置，验证服务启动后再完成提交，失败自动回滚。不能用“正式路径中有文件”判断本次下载成功。

### 3. [P1] 订阅刷新不是事务，失败可能留下空订阅或新旧混合产物

**位置：** [sb.sh:4835–4859](D:/Desktop/sing-box-yg/sb.sh#L4835)、[sb.sh:1924](D:/Desktop/sing-box-yg/sb.sh#L1924)、[sb.sh:2513–2516](D:/Desktop/sing-box-yg/sb.sh#L2513)

- `sbshare()` 先删除旧链接，生成链失败后未立即退出，仍会聚合、覆盖 `jhsub.txt`。
- `sb_client()` 的四个分支直接写正式 `clmi.yaml`（1924、2145、2334、2465 行），晚于此时才进行 Sing-box 客户端转换/检查。
- 菜单 `9 → 2` 在 [4883–4886 行](D:/Desktop/sing-box-yg/sb.sh#L4883) 隐藏刷新错误、不检查退出码，随后继续推送，可能发布旧文件或半成品。

**本地复现：** 让生成器失败后，旧链接被删除、聚合订阅只剩空行，返回值仍是 0。另用不支持的客户端目标版本 `1.10` 注入转换失败：JSON 保持旧内容，YAML 却已换成新后缀，产物不一致。这是失败路径复现，不是说默认版本一定失败。

**建议：** 在独立临时目录完整生成 URI、YAML、JSON，全部校验通过后再提交；保留一套可恢复的旧产物。菜单必须传播失败，失败不能继续推送。多文件需要提交/回滚机制，单独对每个文件 `mv` 并不能自动提供整体事务。

### 4. [P1] GitLab 推送失败仍提示“已更新并推送”

**位置：** [sb.sh:4090–4106](D:/Desktop/sing-box-yg/sb.sh#L4090)

`git rm/commit/add` 和 `gitpush.sh` 退出码全部被忽略，随后无条件执行 `clsbshow()`。末尾 `cd` 又把函数退出状态覆盖成成功。

**本地复现：** 模拟 git 返回 128、推送返回 1，依然调用成功提示，函数退出码 0。

**建议：** 只对有差异的产物执行一次 `git add → commit → push`，逐步检查错误，推送成功后才报成功；不要每次“删缓存提交一次、重新添加再提交一次”。去除默认强推，确需覆盖远端时另行提供明确操作。

### 5. [P1] 清理操作可能破坏本项目之外的防火墙和定时任务

**位置：** [sb.sh:4811](D:/Desktop/sing-box-yg/sb.sh#L4811)、[sb.sh:4629–4635](D:/Desktop/sing-box-yg/sb.sh#L4629)

- 卸载直接执行 `iptables -t nat -F PREROUTING`，会清空整个链，而不是只删除本项目端口跳跃规则；其他业务 DNAT/转发规则可能一起消失。该项是源码可确认的操作范围风险，未执行真实 iptables。
- `uncronsb()` 按 `sing-box`、`url http` 等宽泛字符串删除任务。安装/重建本项目定时任务时也会调用它，不仅仅是卸载时调用。

**本地复现：** 给替身 crontab 放入其他项目的 `curl https://status.example.org/ping` 和 `sing-box-backup` 任务，两者均被删除；无关名称的备份任务保留。

**建议：** 使用项目专属 NAT 链/规则标记、crontab 标记块或单独 cron 文件，仅删除自己创建的资源。临时文件使用 `mktemp`，避免多个操作共享 `/tmp/crontab.tmp`。

### 6. [P2] 停止旧 Argo 的一种隧道会删除另一种使用的二进制

**位置：** [sb.sh:2626](D:/Desktop/sing-box-yg/sb.sh#L2626)、[sb.sh:2676](D:/Desktop/sing-box-yg/sb.sh#L2676)

旧 VMess 固定、临时隧道共用 `/etc/s-box/cloudflared`，但任意一方的停止操作都会删除它。另一方当前进程可能暂时继续运行，但服务/机器重启后无法启动。

**本地复现：** 抽取真实 `cfargo()` 停止分支，在隔离目录执行后，固定 `argo.service` 仍保留，共享二进制已删除。没有终止真实进程。

**建议：** 停止只管理对应隧道，不删除共享程序；最后一个依赖移除后才能清理二进制。新增 XHTTP + Argo 使用独立副本，不属于此处共享文件冲突。

### 7. [P2] 旧固定 Argo 的进程匹配过宽，多 PID 时反而无法终止

**位置：** [sb.sh:2572–2573](D:/Desktop/sing-box-yg/sb.sh#L2572)、[sb.sh:2593](D:/Desktop/sing-box-yg/sb.sh#L2593)

匹配所有 `cloudflared.*run`，只排除新 XHTTP 路径，可能选到其他项目。多个 PID 被 `kill -9 "$pid"` 合成一个带换行的参数，错误又被隐藏。之后仅 `systemctl start argo`，不会重启仍存活的旧进程，Token 可能没有实际更新。

**本地复现：** 替身 `ps` 提供两个 PID，替身 kill 收到 `<-9>` 和 `<1111\n2222>` 两个参数，而非两个独立 PID；单个其他项目进程也能被选择器命中。

**建议：** 用 `systemctl restart argo` / `rc-service argo restart` 精确管理，校验结果；不要用全局进程扫描替代本项目服务管理。

## 二、Serv00 可选分支的问题

这些问题属于项目的 Serv00 网页/保活分支，不意味着当前 VPS 的独立 XHTTP 正在暴露这些接口；是否在线启用，本轮未检查。

### 8. [P1] 管理接口无鉴权，公开进程信息可能暴露 Tunnel Token

**位置：** [app.js:13–17](D:/Desktop/sing-box-yg/app.js#L13)、[app.js:55–57](D:/Desktop/sing-box-yg/app.js#L55)、[app.js:75–86](D:/Desktop/sing-box-yg/app.js#L75)、[serv00keep.sh:693](D:/Desktop/sing-box-yg/serv00keep.sh#L693)

`/up`、`/re`、`/rp`、`/jc` 没有应用层认证。安装器只把 `/list/key` 替换成带 UUID 的地址，其他接口仍固定。`/jc` 直接返回 `ps aux`，而旧固定隧道通过命令行 `--token` 传递凭据：部署环境若允许该进程参数可见，就可能泄露 Token。

**建议：** 所有管理操作增加独立认证、使用 POST、限制请求频率及并发；移除公开的完整进程输出，只返回必要且脱敏的状态。Token 迁移至权限受限的文件。若该网页已公开启用，这项应优先处理。

### 9. [P1] `/rp` 异步回调引用未定义的 `res`

**位置：** [app.js:40–57](D:/Desktop/sing-box-yg/app.js#L40)

`runportCommand()` 没有接收 `res`，回调成功、失败分支却都引用它；路由还在命令完成前返回“重置完成”。

**本地复现：** Node VM 中以假的 `child_process` 执行实际路由代码，成功、失败回调均出现 `ReferenceError: res is not defined`。复现器捕获了异常；生产代码没有相应捕获，可能导致 Node 进程退出。

**建议：** 显式传入响应对象，在操作完成并验证后只响应一次；不要将所有 stderr 自动等同于操作失败。

### 10. [P2] Serv00 下载超时后仍接受截断二进制

**位置：** [serv00keep.sh:410–424](D:/Desktop/sing-box-yg/serv00keep.sh#L410)、[serv00.sh:386–400](D:/Desktop/sing-box-yg/serv00.sh#L386)

curl 总超时仅 2 秒。检测到文件增长后，仅 `wait`，不检查返回值，随后直接 echo 成功；wget 分支也没检查成功状态。后续会使用这个文件作为内核。

**本地复现：** 替身 curl 写入 14 字节后返回 28，函数仍显示由 curl 下载完成且返回 0。

**建议：** 合理区分连接/总体超时，检查下载退出码、摘要及二进制版本，成功后原子替换，失败才回退另一个下载器。

### 11. [P2] 健康固定隧道也会被每轮保活重启

**位置：** [serv00keep.sh:733–742](D:/Desktop/sing-box-yg/serv00keep.sh#L733)

固定隧道通常没有临时域名的 `boot.log`，`checkhttp` 未赋值；但 `|| [[ "$checkhttp" != 404 ]]` 依然成立，进入 `cfgo()`，已有安装的分支会先杀掉隧道进程。

**本地复现：** 固定域名、健康进程、未设置 `checkhttp` 的条件组合，仍进入重启分支。该复现验证了分支判断，没有真实重启隧道。

**建议：** 先区分固定/临时隧道，再执行各自健康检查；临时域名的 HTTP 状态不能决定固定隧道生命周期。

### 12. [P2] Argo 重试把全部参数合成一个参数

**位置：** [serv00keep.sh:705、726](D:/Desktop/sing-box-yg/serv00keep.sh#L705)、[serv00.sh:666、687、1582](D:/Desktop/sing-box-yg/serv00.sh#L666)

首次启动用 `$args`，重试用 `"${args}"`，cloudflared 收到的是一个完整长字符串，而非命令及独立选项；之后还会提示已重启。

**本地复现：** 同一组模拟参数，首次 `argc=5`，重试 `argc=1`。

**建议：** 使用 Bash 数组 `args=(...); command "${args[@]}"`，重试后验证实际状态再报告结果。

## 三、去冗余及性能优化

| 项目 | 证据/位置 | 建议 |
| --- | --- | --- |
| 配置模板重复 | [sb.sh:1342–2518](D:/Desktop/sing-box-yg/sb.sh#L1342)，`sb_client()` 共 1176 行，四个 Argo 分支重复大量 JSON/YAML | 先建立统一节点数据模型，再按目标客户端渲染；固定/临时 Argo 仅追加节点。先保留快照和真实内核校验，不一次性重写协议配置。 |
| 重复解析同一配置 | [sb.sh:1111](D:/Desktop/sing-box-yg/sb.sh#L1111)，`result_vl_vm_hy_tu()` 有 16 次 `sed + jq` 读取 | 一次 jq 提取所需字段；按 tag 查找而非固定数组下标。先处理配置中的注释格式，不把全局删除 `//` 当成可靠的 JSON 解析器。 |
| Xray 下载逻辑重复 | [sb.sh:3465](D:/Desktop/sing-box-yg/sb.sh#L3465)、[sb.sh:3784](D:/Desktop/sing-box-yg/sb.sh#L3784) | 抽取统一的架构映射、固定版本、下载及校验 helper，避免两处升级漏改。 |
| 菜单同步外部请求 | [sb.sh:263](D:/Desktop/sing-box-yg/sb.sh#L263)、[sb.sh:4726](D:/Desktop/sing-box-yg/sb.sh#L4726) | 外网 IP/版本信息短期缓存、按需刷新；v4/v6 查询可并发。改善的是菜单等待时间，不是节点数据传输速度。 |
| 依赖标记跟随当前目录 | [sb.sh:191、245](D:/Desktop/sing-box-yg/sb.sh#L191) | `sbyg_update` 改为固定状态路径，或直接检查所需命令；依赖失败不应写“已完成”标记。 |
| 固定行号修改 JS | [serv00.sh:1499–1502](D:/Desktop/sing-box-yg/serv00.sh#L1499)、[serv00keep.sh:76–79](D:/Desktop/sing-box-yg/serv00keep.sh#L76) | 通过环境变量或唯一占位符配置，避免普通插入/删除 JS 行后悄悄替换错位置。 |
| 安装依赖存在竞态 | [kp.sh:50、62](D:/Desktop/sing-box-yg/kp.sh#L50) | 依赖在后台安装，主逻辑立刻调用 jq/sshpass；应同步安装并验证命令存在。此项为静态风险，未在干净系统安装复现。 |
| HTTP 错误被 Worker 当成功 | [workers_keep.js:11–12](D:/Desktop/sing-box-yg/workers_keep.js#L11) | 检查 `response.ok`，必要时验证业务响应。本地 mock HTTP 500，确实仍输出“✅ 成功”。 |
| Actions 实际串行且无超时 | [.github/workflows/main.yml:30–40](D:/Desktop/sing-box-yg/.github/workflows/main.yml#L30) | curl 增加连接和总体超时；需要并发时使用有上限的并发，而不是仅在串行循环末尾 `wait`。 |
| 无用状态 | [sb.sh:78](D:/Desktop/sing-box-yg/sb.sh#L78) | `node_suffix_uri` 当前未被渲染器使用，实际用的是 `node_suffix_uri_label`；确认外部无依赖后可移除。 |

模块化应保持当前 `bash <(curl ...)` 单脚本安装方式：优先在脚本内抽函数，或在构建期打包；不要贸然改成运行时 `source` 一组未下载的相邻文件。

## 四、建议实施顺序

1. 先修脚本/内核更新、订阅生成及推送的错误传播和回滚；同时补失败注入测试。如果启用了公开 Serv00 网页，先关闭或鉴权管理接口。
2. 精确限定服务、共享二进制、cron 和防火墙资源的所有权，修复 Argo 停止/重置及保活误重启。
3. 修复 Serv00 下载与参数数组，再统一下载校验 helper。
4. 最后重构重复客户端模板、合并 jq 读取及缓存菜单请求；保持当前协议与导出字段不变。

优先增加的测试：curl 超时/404、损坏压缩包、服务重启失败、生成一半失败、git 拒绝推送、两个旧 Argo 同时存在、系统存在其他 cron/NAT、健康固定隧道保活不重启、管理接口未授权访问。现有生成类测试不能替代这些生命周期失败路径测试。

## 五、验证记录与产物

- 四个 Shell 文件 `bash -n` 均通过：`sb.sh`、`serv00.sh`、`serv00keep.sh`、`kp.sh`。语法通过不代表功能正确。
- `app.js`、`workers_keep.js` 的 `node --check` 均通过；`res` 作用域错误是在异步回调运行时复现的，不是语法错误。
- 本轮另外运行了 4 项现有 XHTTP + Argo 测试，全部通过：地址语法、独立优选地址导出/恢复、地址更新失败回滚、独立隧道不被识别为旧固定隧道。耗时 108.770 秒，没有跳过；这不是完整历史测试集，也不是公网连通性验证。原始结果见 [regression-results.json](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21/regression-results.json)，内部生成命令见 `xhttp-regression-commands.json`。
- 原始命令、输入、stdout/stderr、退出状态及沙箱路径保存在 [证据目录](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21)。复现脚本使用隔离路径及替身，不是线上修复脚本；部分脚本引用本次临时沙箱路径。
- [main-commands.json](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21/main-commands.json)：脚本/内核更新失败及 Shell 语法检查。
- [config-results.json](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21/config-results.json)：推送假成功、空订阅、新旧混合导出；配套 `config-commands.json` 保存调用记录。
- [cron-commands.json](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21/cron-commands.json)：其他任务被误清理。
- [argo-results.json](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21/argo-results.json)：共享二进制删除及多 PID/误匹配；配套 `argo-commands.json` 保存原始输出。
- [serv00-results.json](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21/serv00-results.json)：JS 回调、健康判断、argv、截断下载及 HTTP 500；配套 `serv00-commands.json` 保存完整输入和输出。
- [manifest.json](D:/Desktop/sing-box-yg/review-artifacts/2026-11-21/manifest.json)：源码版本、SHA256 与证据来源。

本轮仅新增审查报告和证据，不包含修复提交，也没有推送。无需恢复线上配置；原有未跟踪文件未动。完整历史测试集、公网端到端连通性和节点测速不属于本轮验证结果。
