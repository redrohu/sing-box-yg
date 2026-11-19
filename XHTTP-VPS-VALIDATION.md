# XHTTP 实机重新部署验证（2026-11-19）

> 这是 fork.10 普通模式的历史记录。随后已按用户要求升级到 Encryption + Vision，当前验证见 [ARTICLE-XHTTP-VPS-VALIDATION.md](ARTICLE-XHTTP-VPS-VALIDATION.md)。

## 原因和修复

1. 旧安装流程在回滚trap仍生效时调用`systemctl status`，交互终端下可能打开分页器。用户关闭终端时安装流程尚未提交，可能触发trap，停止服务并删除配置；此次远程日志中的停止/文件消失与该风险一致，但没有完整的用户终端进程审计，不能认定为唯一原因。
2. 状态查看改为`systemctl --no-pager --full status sbox-xhttp`，防止安装卡在分页器。
3. VPS使用Debian10的jq1.5，真实导出报错`jq: Unknown option --rawfile`，使Mihomo YAML未刷新。改为先读取公钥，再用`--arg`传给jq；不升级系统jq，不导出服务端私钥。
4. 版本文件更新为`v26.11.19-fork.10`，包含上述修复说明。

## 授权和操作

用户明确允许修复后在VPS重新部署TCP6443、刷新订阅并验证。使用指定密钥的ACL受限副本连接SSH端口2022。原始密钥没有修改。未下载服务端私钥。

先备份`/usr/bin/sb`、三份服务端配置、客户端导出及版本标记到远端目录`/root/sbox-check-backup-20261119T073140Z`。只替换脚本并使用真实菜单3→11→1部署、3→11→2刷新。独立节点密钥为新生成，客户端应更新订阅；旧节点不可继续使用。

## 实际结果

- VPS Xray v26.11.9：systemd `active/enabled`，监听TCP6443；部署命令完成并退出SSH后，再次连接状态仍正常。
- Xray服务端和客户端`run -test`均显示`Configuration OK`；现有sing-box服务端`check`成功。
- 三份原五协议服务端配置`sb.json`、`sb10.json`、`sb11.json`的SHA256与远端备份一致。
- 真实`clmi.yaml`含1个XHTTP节点，三个代理组各引用一次；端口、独立UUID、SNI、公钥、Short ID、路径逐项与服务端核对一致；显式启用混合密钥交换，不关闭证书校验，不配置Vision flow。
- 聚合`jhsub.txt`含当前新节点链接；官方sing-box `sbox.json`没有写入XHTTP（符合不支持该传输的限制）。
- 本地Mihomo v1.19.34使用该公网节点访问Cloudflare HTTPS trace成功，curl退出0、TLS1.3，报告的出口IPv6与VPS地址一致。没有进行大流量测速或重启VPS测试。
- 本地相关测试共31项通过：XHTTP13、Mihomo7、更新提示11；本次未重复与修复无关的全套矩阵。Bash语法、git差异检查通过。

## 记录和恢复

本地测试根目录：`C:\Users\17289\AppData\Local\Temp\sbox-pager-fix-20261119-153046`；`test-results.json`含实际命令、原始输出和退出码，生成脚本/配置在`final-tests/`。

远程操作日志在受限目录`C:\Users\17289\AppData\Local\Temp\sbox-vps-check-2b7a1199d01d4b899d61a5ea4cb87321`：`remote-before.log`、`deploy.log`（初次部署成功但旧jq刷新失败）、`refresh.log`（修复后退出0）、`verify-remote.log`、`public-request-result.json`。其中部分文件含节点认证信息，不能公开。

远端备份目录保存恢复所需旧脚本及配置。原五协议没有改动，无需恢复。若不需要新XHTTP可用3→11→7卸载；不得恢复旧聚合订阅来冒充仍存在的旧节点。脚本源代码可反向应用本次补丁；测试额外副本恢复SHA256记录见本地`restoration-check.json`。

本地临时身份副本在受限日志目录中。清理请求被运行环境策略拒绝，未绕过限制；原始密钥完整保留。用户可在结束后删除该目录里的`identity`，以及不再需要的客户端测试文件。没有把密钥或含凭据日志加入Git。
