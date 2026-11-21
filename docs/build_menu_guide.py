"""Build text tables and an offline viewer for the three retained menu artifacts."""
import argparse
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def outputs():
    data = json.loads((HERE / 'menu-guide.json').read_text(encoding='utf8'))
    result = {}
    md = ['# 菜单功能图与完整说明', '',
          f'对应本仓库 **{data["version"]}**；核对源为 `sb.sh` 与 `serv00.sh`。图中的 `→` 表示依次输入，不是一个连写命令。', '',
          '**范围：**涵盖本仓库拥有的菜单、条件子菜单、安装交互和破坏性操作；外部脚本 11/12/13 的内部菜单不由本仓库固定，故只画调用边界，不能当作已逐项审核或安全背书。', '',
          '[打开离线图册](MENU-GUIDE.html) · [机器可读菜单数据](menu-guide.json) · [重新生成脚本](build_menu_guide.py)', '',
          '仅保留三份图形产物：[可编辑XMind](MENU-ACTUAL-TREE.xmind)、[完整展开SVG](menu-maps/vps-actual-menu-full.svg)、[菜单速览PNG](menu-maps/vps-actual-menu-overview.png)。下方是按专题检索的文字详表，不是导图层级；真实菜单树请打开XMind或完整SVG。', '',
          '## 读图规则', '',
          '- VPS 与 Serv00 是两个独立的 `sb` 菜单，不能混用编号；图中 Serv00 路径用 `S→` 前缀区分，实际输入时不输入 S。',
          '- “表单”“证书”“端口”等文字路径表示交互步骤，不是隐藏的数字菜单。`0`、`3 返回`和 `y/n` 以各级实际提示为准。',
          '- Sing-box 五协议：VLESS REALITY / VMess WS / Hysteria2 / TUIC5 / AnyTLS；1.10 分支不含 AnyTLS。',
          '- 两种 XHTTP 是独立 Xray 服务，不受 Sing-box UUID、启停、端口、出站分流与内核切换控制；主菜单 2 完整卸载会移除。',
          '- Mihomo YAML / 通用 URI 含已部署 XHTTP；官方 Sing-box JSON 不写入 XHTTP。客户端必须支持所选模式；配置导出通过不等于公网连接成功。',
          '- 订阅/密钥/Token/管理令牌都视为敏感信息；本图只使用字段名和默认值，不含真实凭据。', '']
    for i, section in enumerate(data['sections'], 1):
        md += [f'## {i:02d} · {section["title"]}', '', section['subtitle'], '']
        for group in section['groups']:
            md += [f'### {group["title"]}', '', '| 输入路径 | 功能 | 说明与限制 |', '| --- | --- | --- |']
            for item in group['items']:
                md.append('| ' + ' | '.join(v.replace('|', '\\|') for v in [item['path'], item['title'], item['note']]) + ' |')
            md.append('')
        md += ['**本页提醒：**', ''] + ['- ' + note for note in section['notes']] + ['']
    md += ['## 核对、复用与维护', '',
           '```bash', 'python docs/build_menu_guide.py', 'python docs/build_menu_guide.py --check', '```', '',
           '本脚本仅生成文字详表和离线查看页，不生成旧专题图。实际菜单XMind由 `python docs/build_xmind_guide.py` 生成并用 `--check` 校验；完整SVG与速览PNG由 `python docs/render_actual_menu_tree.py` 生成（可选Pillow与Windows中文字体）。详见[导图维护说明](XMIND-GUIDE.md)。所有图形产物只保留上述三份，查看页不访问外网、不执行菜单、没有遥测。', '',
           '对于动态外部菜单、条件隐藏项、当前代码仍存在的限制，以实际提示和本图的说明栏为准；本图不会凭空增加功能。', '']
    result['MENU-GUIDE.md'] = '\n'.join(md)
    result['MENU-GUIDE.html'] = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sing-box-yg 实际菜单功能图</title>
<style>body{margin:24px auto;padding:0 20px;max-width:1400px;background:#f8fafc;color:#162b3c;font:16px/1.7 "Microsoft YaHei",sans-serif}a{color:#075b91}img{max-width:100%;height:auto}section{margin:32px 0}</style>
<h1>实际菜单功能图</h1>
<p>仅保留可编辑XMind、完整SVG、速览PNG三份图形产物；不再按专题拆图。</p>
<p><a href="MENU-ACTUAL-TREE.xmind">XMind：主菜单及全部子菜单、功能与注意事项</a> · <a href="MENU-GUIDE.md">文字详表</a> · <a href="XMIND-GUIDE.md">维护说明</a></p>
<section id="full"><h2>完整展开SVG</h2><p><a href="menu-maps/vps-actual-menu-full.svg">打开原图放大查看全部层级</a>；图较长，可直接打开XMind折叠阅读。</p><img src="menu-maps/vps-actual-menu-full.svg" alt="VPS实际菜单完整树，含功能和注意事项"></section>
<section id="overview"><h2>菜单速览PNG</h2><p>仅展示主菜单与直接子菜单；更深层选项请查看完整SVG或XMind。<a href="menu-maps/vps-actual-menu-overview.png">打开PNG</a></p><img src="menu-maps/vps-actual-menu-overview.png" alt="实际菜单主菜单和直接子菜单速览"></section>
</html>
"""
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = []
    for name, text in outputs().items():
        path = HERE / name
        if args.check:
            if not path.exists() or path.read_text(encoding='utf8') != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf8', newline='\n')
    if stale:
        raise SystemExit('Outdated menu guide: ' + ', '.join(stale))
    print('Menu guide ' + ('verified' if args.check else 'generated'))


if __name__ == '__main__':
    main()
