"""Actual interactive menu topology, with documentation attached to its entry.

Unlike the thematic SVG guide, this model has no invented category menus.
Numeric paths are merged into one VPS tree; prompts and API routes are typed
separately so a documentation step cannot become a fake numbered submenu.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main_labels(script: str, serv00=False) -> dict[str, str]:
    if serv00:
        script = script[script.index('menu() {'):]
        pattern = r'^\s*(?:green|yellow|red)\s+"(\d+)\. (.*?)"\s*$'
    else:
        script = script[script.index('green " 1. 一键安装 Sing-box"'):]
        pattern = r'^green "\s*(\d+)\. (.*?)"\s*$'
    return dict(re.findall(pattern, script, re.M))


def config_labels(script: str) -> dict[str, str]:
    line = next(line for line in script.splitlines()
                if line.startswith('readp "1：更换Reality域名'))
    return {
        match.group(1): match.group(2)
        for part in line.split('"', 2)[1].split('\\n')
        if (match := re.fullmatch(r'(\d+)：(.+)', part))
    }


def model(data: dict) -> list[dict]:
    nodes = {}
    records = [item for s in data['sections'] for g in s['groups'] for item in g['items']]

    def ensure(platform, path, title=None, kind='menu'):
        key = f'{platform}:{path}'
        if key not in nodes:
            nodes[key] = dict(key=key, path=path, title=title or path.split('→')[-1],
                              kind=kind, children=[], info=[], warnings=[], sources=[])
        if title:
            nodes[key]['title'] = title
        return nodes[key]

    def add(parent, child):
        if child not in parent['children']:
            parent['children'].append(child)

    def attach_record(node, item):
        note = item['note']
        if item['path'] == '10':
            note = '跟随systemd的Sing-box journal日志；Ctrl+C退出。Alpine下本菜单暂不支持；独立XHTTP日志见3→11→6或3→11→9→6。'
        if note not in node['info']:
            node['info'].append(note)
        ref = {'path': item['path'], 'title': item['title'], 'note': item['note']}
        if note != item['note']:
            ref['rendered_note'] = note
        if ref not in node['sources']:
            node['sources'].append(ref)

    def warning(path, text, platform='vps'):
        node = ensure(platform, path)
        if text not in node['warnings']:
            node['warnings'].append(text)

    def info(path, text, platform='vps'):
        node = ensure(platform, path)
        if text not in node['info']:
            node['info'].append(text)

    # Real, digit-only choices form the tree, regardless of their former section.
    for item in records:
        path = item['path']
        platform = 'serv00' if path.startswith('S→') else 'vps'
        numeric = path[2:] if platform == 'serv00' else path
        if not re.fullmatch(r'\d+(?:→\d+)*', numeric):
            continue
        parts = path.split('→')
        start = 2 if platform == 'serv00' else 1
        parent = None
        for depth in range(start, len(parts) + 1):
            node = ensure(platform, '→'.join(parts[:depth]))
            if parent:
                add(parent, node)
            parent = node
        if not parent['sources']:
            parent['title'] = item['title']
        attach_record(parent, item)

    sb = (ROOT / 'sb.sh').read_text(encoding='utf-8')
    serv = (ROOT / 'serv00.sh').read_text(encoding='utf-8')
    for choice, title in main_labels(sb).items():
        ensure('vps', choice, title)
    for choice, title in config_labels(sb).items():
        node = ensure('vps', '3→' + choice, title)
        add(nodes['vps:3'], node)
    for path, text in {
        '3→1': '选择协议，更换REALITY目标或切换已有Acme / 自签证书、VMess TLS。',
        '3→2': '选择修改Sing-box共用UUID / 密码，或只修改VMess WS路径。',
        '3→3': '选择管理VMess临时隧道或固定隧道，再进入各自的重置 / 停止子菜单。',
        '3→4': '设置Sing-box出站域名解析的IPv4 / IPv6优先或仅用某地址族。',
        '3→5': '配置Telegram机器人与接收用户，供节点通知使用。',
        '3→6': '更新Sing-box的Warp WireGuard出站账户参数。',
        '3→7': '首次设置 / 重置Gitlab订阅远端及访问凭据。',
        '3→8': '通过本地HTTP文件服务发布配置 / 聚合订阅，管理路径和端口。',
        '3→9': '手动设置VMess客户端的连接地址、主节点Host/SNI或Argo共用地址。',
        '3→10': '设置或清除节点名称前缀、后缀，支持恢复主机名后缀。',
        '3→11': '管理独立Xray的XHTTP直连节点；选9进入XHTTP固定Argo管理。',
        '3→0': '返回VPS主菜单。',
    }.items():
        info(path, text)
    for choice, title in main_labels(serv, True).items():
        ensure('serv00', 'S→' + choice, title)

    # Missing return choices are real prompts in sb.sh, not thematic headings.
    for path, title in {
        '3→3→1→0': '返回Argo类型选择', '3→3→2→0': '返回Argo类型选择',
        '4→3→0': '返回协议端口选择', '4→4→0': '返回协议端口选择',
        '4→3→2→0': '返回协议端口选择', '4→4→2→0': '返回协议端口选择',
    }.items():
        child = ensure('vps', path, title)
        add(nodes['vps:' + path.rsplit('→', 1)[0]], child)
        child['info'].append('按脚本实际调用返回，不修改现有设置。')

    # A channel is a real choice 1..6; its own 1/2/3 menu is repeated per channel.
    common = {i['path'].split('→')[-1]: i for i in records if i['path'].startswith('5→通道→')}
    for channel in range(1, 7):
        for choice, item in common.items():
            path = f'5→{channel}→{choice}'
            child = ensure('vps', path, item['title'])
            attach_record(child, item)
            add(nodes[f'vps:5→{channel}'], child)
        restriction = ('仅1.10系列可进入此通道的匹配方式子菜单；现代核心会拒绝。'
                       if channel in (1, 4, 5, 6) else
                       '现代核心可进入；选项2 geosite仍会显示，但仅1.10系列执行成功。')
        warning(f'5→{channel}', restriction)

    # Non-numeric paths describe a prompt/process, never a new numbered menu.
    def flow(parent_path, slug, title, items, platform='vps'):
        node = ensure(platform, parent_path + '::' + slug, title, 'flow')
        for item in items:
            attach_record(node, item)
        add(nodes[f'{platform}:{parent_path}'], node)
        return node

    lookup = {i['path']: i for i in records}
    for slug, title in [('IP环境', '步骤① 检查IP / Warp / IPv6环境'),
                        ('防火墙', '步骤② 是否开放端口、关闭防火墙'),
                        ('内核', '步骤③ 选择Sing-box内核'),
                        ('证书', '步骤④ 选择自签或Acme证书'),
                        ('端口', '步骤⑤ 自动 / 自定义协议端口'),
                        ('完成', '步骤⑥ 生成密钥、安装服务并导出节点')]:
        items = [i for i in records if i['path'] == f'1→{slug}' or i['path'].startswith(f'1→{slug}→')]
        node = flow('1', slug, title, [])
        for item in items:
            if item['path'].count('→') == 2:
                choice = item['path'].rsplit('→', 1)[1]
                option = ensure('vps', node['path'] + ':' + choice, f'{choice}. {item["title"]}', 'prompt')
                attach_record(option, item)
                add(node, option)
            else:
                attach_record(node, item)
    warning('1::防火墙', '选1（默认）会关闭/清理整机防火墙规则，并可能停用Web服务；有其他业务建议选2自行放行。')
    warning('1::证书', '自签模式默认关闭VMess入站TLS，REALITY仍保留；Acme证书影响相关TLS入站，不等于给REALITY伪装域名申请证书。')

    modes = flow('3→11→1', 'mode', '部署时输入：协议模式（不是XHTTP管理菜单）', [])
    for choice in ('1', '2'):
        item = lookup['3→11→1→模式' + choice]
        option = ensure('vps', modes['path'] + ':' + choice, f'{choice}. {item["title"]}', 'prompt')
        attach_record(option, item)
        add(modes, option)
    flow('3→11→9→1', 'cloudflare', '部署前准备：Cloudflare固定隧道与路由',
         [lookup['3→11→9→1→Cloudflare准备']])
    for slug in ('单栈', '影响范围'):
        flow('15', slug, '条件 / 说明：' + lookup['15→' + slug]['title'], [lookup['15→' + slug]])

    for slug in ('IP', 'REALITY', 'UUID', '端口'):
        item = lookup['S→1→' + slug]
        flow('S→1', slug, '安装步骤：' + item['title'], [item], 'serv00')
    for parent in ('S→1', 'S→4'):
        flow(parent, 'temporary', '隧道交互：回车 → 临时隧道', [lookup['S→1/4→回车']], 'serv00')
        flow(parent, 'fixed', '隧道交互：g → 固定隧道',
             [lookup['S→1/4→g'], lookup['S→固定→回源']], 'serv00')

    api = []
    for item in records:
        if item['path'].startswith('API→'):
            node = ensure('api', item['path'], item['path'][4:] + '：' + item['title'], 'api')
            attach_record(node, item)
            api.append(node)

    # Attach limits where the user encounters them, not on a separate index page.
    for path, text in {
        '2': '危险：完整卸载包含Sing-box、独立XHTTP、XHTTP固定Argo及本机配置和密钥；先离线备份。',
        '3': '选项1–9主要作用于Sing-box；XHTTP单独在11管理。名称设置10会同步已部署XHTTP。',
        '3→1': '条件：只有已申请Acme证书才显示2–5；1.10系列没有AnyTLS选项5。',
        '3→2': '会改变Sing-box共享凭据或VMess路径；更新后客户端重新拉取订阅；不改独立XHTTP。',
        '3→3': '条件：VMess入站TLS必须关闭；与3→11→9的XHTTP固定Argo不是同一隧道。',
        '3→4': '仅Sing-box 1.10系列可用，需要相应IP存在；没有0返回选项，不影响独立XHTTP。',
        '3→5': '设置过程中会发送Telegram通知；不要公开机器人Token、用户ID和节点凭据。',
        '3→6': '会显示WireGuard私钥等参数，不要公开截图；只影响Sing-box出站。',
        '3→7': 'Gitlab访问令牌和含令牌订阅URL均属敏感信息；日常远端发布另走9→2。',
        '3→8': 'HTTP文件服务不加密，路径密码不是HTTPS；变更路径/端口后客户端要换链接，并检查防火墙。',
        '3→9': '只改VMess，手动填地址，不测速、不保证提速。server连接地址与Host/SNI路由身份不同。',
        '3→10': '只改节点显示名称及分组引用，不改变协议、端口、UUID；含XHTTP，改后刷新客户端。',
        '3→11': '独立Xray服务：直连和固定Argo的服务/凭据分离；主Sing-box启停/端口/UUID/核心更新不自动同步。',
        '3→11→1': '直连：REALITY + XHTTP；默认额外使用Encryption + Vision，mode:auto；先安装Sing-box，TCP端口需空闲和放行。',
        '3→11→9': '独立固定Argo节点：TLS + XHTTP packet-up + Encryption/Vision；不叠加REALITY，保留直连节点。',
        '3→11→9→8': '只改变该节点的server/address；必须保留固定隧道域名的Host/SNI。与3→9的VMess优选地址相互独立。',
        '4': '只改Sing-box端口；HY2/TUIC主端口变更会清理原多端口。AnyTLS仅非1.10显示；XHTTP端口不变。',
        '4→2': 'VMess端口变更后：临时Argo需重置；固定Argo需同步Cloudflare回源端口。',
        '5': '只作用于Sing-box出站；无网络的分流通道可能阻断目标网站。现代核心只支持这里的通道2、3。',
        '6': '仅Sing-box主服务；不会同时重启/停止独立XHTTP或XHTTP Argo。',
        '7': '仅更新脚本，不等于更新Sing-box内核或Xray；网络失败不应显示已更新。',
        '8': '仅Sing-box；目标版本需通过现有配置检查，否则回滚。不更新Xray；1.10系列没有AnyTLS。',
        '9': '本地刷新、Gitlab发布、客户端拉取是三个动作。Mihomo导出含XHTTP，官方Sing-box JSON不含XHTTP。',
        '10': '日志跟随需Ctrl+C退出；Alpine下本菜单暂不支持查看，不代表无日志。',
        '11': '外部在线脚本；不保证提速，LXC/OpenVZ不支持这里的原版BBR；执行前检查来源和系统影响。',
        '12': '外部Acme脚本，子菜单以实时下载的外部脚本为准；本项目不固定其菜单。证书切换在3→1。',
        '13': '外部Warp脚本，子菜单以实时脚本为准；可能改出站/路由，并非部署新入站协议。',
        '14': '辅助本地SOCKS5进程，不是新增客户端协议；修改它会影响依赖该SOCKS5的分流。',
        '15': '需Sing-box在运行；双栈才出现1/2选择，单栈自动处理。直连XHTTP导出地址随公共地址刷新，XHTTP Argo自定义server不受覆盖；不修改系统网卡IP。',
        '16': '显示本fork说明与上游教程链接，无数字子菜单。',
        '0': '仅退出脚本界面，不主动停止后台代理、隧道服务。',
    }.items():
        warning(path, text)
    # Preserve each earlier guide warning, now anchored to the relevant menu.
    section_targets = {
        '01-overview': ['0', '2'], '02-connection': ['3→1', '3→2'],
        '03-subscriptions': ['3→8', '3→11→9→8'],
        '04-xhttp': ['3→11→1', '3→11→9', '9'],
        '05-install-routing': ['1', '5', '5'],
        '06-maintenance': ['7', '11'],
        '07-serv00': ['S→2', 'S→9', None],
    }
    for section in data['sections']:
        for target, text in zip(section_targets[section['id']], section['notes']):
            if target:
                warning(target, text, 'serv00' if target.startswith('S') else 'vps')
            else:
                for node in api:
                    node['warnings'].append(text)
    for choice in (11, 12, 13):
        info(str(choice), '本仓库仅提供外部脚本入口，不编造外部程序的子菜单。')
    warning('6→2', 'systemd环境下不仅停止Sing-box，还禁用该服务的开机自启；Alpine分支仅停止服务。')
    warning('15', '检测到Warp运行时，会尝试先停止、刷新后再启动Warp相关服务；可能短暂影响网络。')
    for parent in ('14→1', '14→2'):
        flow(parent, 'port', '输入步骤：设置本地SOCKS5端口', [])['info'].append('回车默认40000；检测端口占用，随后重启辅助进程并写入开机任务。')
    flow('14→2', 'country', '输入步骤：选择Psiphon国家代码', [])['info'].append('按终端列出的国家代码选择；能否获得可用IP取决于实际连通性。')
    for path in ('S→2', 'S→9'):
        warning(path, '危险：作用于账户资源而非只删节点；必须先备份，有其他业务的账户勿随意操作。', 'serv00')
    warning('S→1', '平台风险：免费Serv00使用代理脚本存在封号风险；以平台政策为准。', 'serv00')

    def numeric_order(node):
        tail = node['path'].split('→')[-1]
        return (0, 999 if tail == '0' else int(tail)) if node['kind'] == 'menu' else (1, 0)

    def sort_tree(node):
        node['children'].sort(key=numeric_order)
        for child in node['children']:
            sort_tree(child)

    roots = []
    for platform, title, choices in [('vps', 'Sing-box-yg · VPS实际菜单', list(range(1, 17)) + [0]),
                                     ('serv00', 'Serv00 / Hostuno · 实际菜单', list(range(1, 10)) + [0])]:
        root = dict(key=platform, path='', title=title, kind='root', info=[], warnings=[], sources=[], children=[])
        for choice in choices:
            path = ('S→' if platform == 'serv00' else '') + str(choice)
            add(root, nodes[f'{platform}:{path}'])
        for child in root['children']:
            sort_tree(child)
        roots.append(root)
    roots.append(dict(key='api', path='', title='Serv00管理API（非SSH数字菜单）', kind='root',
                      info=[], warnings=[], sources=[], children=api))
    return roots
