# 两条 RN 节点连接检查（2026-11-20）

## 范围与环境

检查截图中的 `vless-reality-vision racknerd-54213c7` 与 `vmess-argo临时 racknerd-54213c7`。路由器当前为 Open-box v0.1.462、Mihomo v1.19.34-openbox.20。没有修改路由器正式配置、节点选择、VPS配置或防火墙；临时诊断实例及SSH转发均已停止。

## 结果

| 节点 | 实际结果 |
|---|---|
| VLESS Reality Vision / TCP52784 | TCP连接超时，尚未进入REALITY握手 |
| VMess Argo明文 / CDN TCP8880 | CDN解析的两个IPv4地址均TCP连接超时 |
| VMess TLS Argo / CDN TCP443 | Open-box实际HTTPS节点探测成功，单次约420–448ms |
| XHTTP + REALITY + Encryption + Vision / TCP6443 | 原生直连探测成功，单次约647–1496ms；升级后Encryption字段已保留 |

这些延迟是各次测试的观测值，不是测速或长期稳定性承诺。

## VLESS Reality Vision

- VPS的sing-box服务正常，TCP52784在监听，本机可以建立TCP连接。系统IPv4的legacy/nft iptables均为ACCEPT，UFW未启用；没有发现该端口的本机过滤规则。
- 路由器导出的UUID、REALITY公钥、Short ID与VPS当前导出一致，`flow`为`xtls-rprx-vision`，SNI与服务端一致。`network`省略与`tcp`的差别不是此次TCP超时原因。
- 在VPS进行双向、仅记录包元数据的被动观察，同时从路由器重新探测：52784收到13个SYN、发出23个SYN-ACK，路由器仍报告TCP连接超时；同时间6443有正常SYN/SYN-ACK及后续连接结束流量。
- 使用同一VLESS节点凭据，通过已授权的SSH本地转发连接VPS loopback:52784，再发起代理HTTPS请求，curl退出0并返回VPS出口。这是协议可用性对照，不代表公网52784已可达；转发已关闭。

**判断：**52784的公网TCP握手未完成，证据指向回程链路、上游过滤或中间设备/NAT处理，而不是当前VLESS凭据错误或服务未启动。没有路由器WAN侧抓包，不能进一步断言具体是哪家运营商、GFW、上游设备或云平台导致。更换端口可能改善，但需要实际试验，不能保证。

## VMess Argo明文

- cloudflared进程存在，临时域名与客户端Host一致，origin VMess WS端口正常。
- 相同隧道的TLS443节点成功，说明不能将失败直接归因为整个Argo隧道失效或UUID错误。
- 明文原入口TCP8880超时。独立临时实例尝试不同入口（不改正式配置）：
  - 原优选域名:80：WebSocket握手收到`301 Moved Permanently`，未成功建立代理。
  - 临时隧道域名:80：此次TCP超时。
  - 临时隧道域名:8880：收到`301 Moved Permanently`，未成功建立代理。
  - TLS443对照：成功。

**判断：**原明文入口8880存在当前链路可达性问题；其他明文入口又出现重定向，不能只把端口改为80就认定修复。当前已验证可用的选择是`vmess-tls-argo临时`的TLS443版本。

## 建议

1. 当前优先使用已验证的`vmess-tls-argo临时`或原生XHTTP节点，不需要旧的本机XHTTP兼容中转。
2. 若要恢复独立VLESS Reality Vision，可在备份后更换一个未占用TCP端口、同步订阅并验证；本次没有执行端口修改。
3. 明文Argo节点可暂不使用。若要继续使用明文入口，需要另选实际可达且不会重定向的CDN入口，并验证完整WebSocket代理请求。

本次没有进行整机重启、吞吐测试或大流量测试，也没有更改当前可用节点选择。
