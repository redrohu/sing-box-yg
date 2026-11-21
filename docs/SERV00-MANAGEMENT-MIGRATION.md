# Serv00 网页管理与保活迁移

本次修改只涉及本仓库代码；不会自动升级已经部署的服务器，也不会自动修改已有 Worker 或 GitHub Secrets。

## 管理接口的兼容性变化

| 入口 | 新行为 |
| --- | --- |
| `/up`、`/re`、`/rp`、`/jc` | 必须使用 `POST` 和 `Authorization: Bearer <管理令牌>` |
| 原来的公开 GET 保活、重启链接 | 不再执行管理操作；未认证返回 401，认证后的 GET 返回 405 |
| `/list/<原 UUID>` | 保留订阅查看方式，不需要迁移 UUID |
| `/healthz` | 只返回 `ok`，不检查或重启代理、不重置端口、不返回凭据 |

`/jc` 仅返回 Sing-box/Argo 的运行状态，不再公开 `ps aux` 或命令行。同一 Node 管理进程内的管理操作同一时刻只执行一个；冲突返回 409。成功响应在子命令结束并检查进程之后返回，失败不会把 UUID、密钥、订阅或子命令原始输出返回网页。进程检查不等于客户端端到端连通性测试。

安装/升级的脚本会在当前 Serv00 账户下生成独立管理凭据：`~/.serv00-management-token`，权限为 `600`。此文件与订阅 UUID、Cloudflare Tunnel Token 完全不同，不会写入 `app.js` 或仓库。已有有效管理令牌会保留；没有有效令牌时网页管理默认拒绝执行。

## 升级已有部署

**旧 keeper 自动下载兼容**：已部署的旧 `serv00keep.sh` 会继续自动拉取 `main/app.js` 并修改第 15、59、90 行。新版 `app.js` 在这三行保留专用无害注释，旧替换只会改注释，不会破坏变量、路由或认证逻辑；此兼容不要求用户先手动更新 keeper。回归测试会实际执行旧的四条 sed 替换并加载替换后的程序。以后维护 `app.js` 时必须保留这三行注释的位置，直到所有旧 keeper 完成迁移。

旧 keeper 本身不会生成独立管理令牌，因此自动拉取新应用后，如果本机没有有效令牌，管理入口会安全地返回 503，而不是重新开放旧 GET；`/healthz` 和原 UUID 订阅入口仍正常。要恢复经过认证的网页管理和定时保活，请完成以下升级与 Secret 迁移。

旧安装器还会按固定行号修改下载的 `serv00keep.sh` 的参数区，因此保留其第 14–19 行 UUID、Argo、三个端口的导出行兼容合同；新增辅助函数放在参数区之后。新版安装器不再依赖这些行号进行修改。

**Passenger 启动兼容**：根据 [Passenger 官方反向端口绑定说明](https://www.phusionpassenger.com/library/indepth/nodejs/reverse_port_binding.html)，`app.js` 同时支持直接 Node 启动和存在全局 `PhusionPassenger` 时由 loader `require` 启动。普通 `require` 仅导出测试工厂，不自动监听或执行保活。本次仅使用本地 VM 模拟这三种启动方式，未在真实 Serv00/Passenger 环境实测监听与回源。

1. 用现有单文件安装方式取得本次版本的 `serv00.sh` / `serv00keep.sh`，执行正常升级流程，不要选择系统重置。原来的 UUID、固定隧道信息从本地数据文件继续读取，不再修改脚本或 JS 的固定行号。
2. 确认 `~/.serv00-management-token` 存在、权限为 `600`，Node 管理应用已重启加载新 `app.js`。管理页须通过可信的 **HTTPS** 地址访问；不要把 Bearer 令牌经明文 HTTP 发送。
3. 通过可信的 SSH/本地文件渠道读取管理令牌，仅粘贴到 Worker/GitHub 的 Secret 管理界面；不要提交到仓库、URL、聊天、公开日志或截图。
4. 将原来的 GET 定时保活配置迁移成下述认证配置。不要继续把 `/healthz` 当作保活成功依据；它只证明网页可访问。

如果下载失败或语法检查不通过，新脚本会保留旧文件并报错；这**不代表旧线上版本已经修复**。此时应先停用公开旧管理入口，再修复下载/升级问题。

## Cloudflare Worker

使用更新后的 `workers_keep.js`，设置 Worker 的 Secret **`SERV00_TARGETS`** 为 JSON 数组。每台服务器可用不同的令牌，例如：

```json
[
  {"url": "https://YOUR_MANAGEMENT_HOST/up", "token": "YOUR_64_HEX_MANAGEMENT_TOKEN"}
]
```

示例是占位文本，不是真实有效凭据。目标只允许 HTTPS 的 `/up` 或 `/re`；不跟随重定向。HTTP 错误或未确认健康状态会让该轮保活失败，不再把 HTTP 500 记录成成功。请求超时为 250 秒，最多四个并发任务。

## GitHub Actions

现有 Secret 名称 **`http`** 保留，但内容必须从“空格分隔的旧 GET URL”迁移为同样的 JSON 数组。工作流通过环境变量读取该 Secret，不把其内容直接拼入 Shell 源码。请求使用 POST/Bearer、HTTPS 校验、260 秒请求超时、最多四个并发；任一目标失败会让工作流失败。

本次没有开启定时计划；原有 `schedule` 注释仍保留。管理命令可能下载或检查内核，响应耗时会比旧的“立刻返回成功”更长。

## 手动操作与令牌轮换

手动调用时，在可信客户端中使用 HTTPS、POST 和 Authorization 请求头；不要把令牌放进查询字符串。`/rp` 会改变三个节点端口，应手动使用，不要添加到定时保活任务。使用固定 Argo 隧道时，还需按新 VMess 端口调整 Cloudflare 的回源服务地址。

轮换令牌时，在服务器本地以 `umask 077` 创建临时文件，用 `openssl rand -hex 32` 生成新值，设置 `600` 后原子替换 `~/.serv00-management-token`，同步更新所有客户端 Secret。应用每次请求读取令牌文件，无需恢复公开 GET；旧令牌将立即失效。如果设置了环境变量 `SERV00_MANAGEMENT_TOKEN`，它优先于文件，也须同步更新或移除。

`kp.sh` 首次连接采用 SSH `accept-new`：仅信任首次见到的主机密钥，已知密钥变化会失败。依赖不再后台安装；带空格的账户字段通过逐行 JSON 解析保留，远程变量通过 shell 安全引用的 stdin 传给 Bash，部署令牌不再写入命令日志。

`kp.sh` 的存活检查现在按生成的进程名称进行，不再把 Argo 凭据拼到进程查询命令里。因此只修改 `ACCOUNTS` 中的 Argo Token、但旧进程仍然存活时，不会自动触发凭据变更；请通过正常的 Argo 配置菜单单独更新。不要为了轮换凭据启用 `RES=y`，该选项会重置账户环境。

## 本地验证与恢复

运行 `python -m unittest discover -s tests -p test_serv00_safety.py -v`；测试仅使用本地 mock，不执行真实 SSH、包安装、服务管理或公网请求。设置 `SB_TEST_OUTPUT` 可指定命令/输入/输出/退出状态记录位置。

如需回退代码，应先保存本地修改，再使用本次备份或 Git 恢复相关文件；保留服务器上的 UUID、节点配置、管理令牌和 Tunnel Token 数据文件。回退旧管理程序会重新引入公开管理风险，不建议把旧版本重新暴露公网。
