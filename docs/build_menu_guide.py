"""Build offline menu diagrams and text from menu-guide.json (standard library only)."""
import argparse
import html
import json
from pathlib import Path
import unicodedata

HERE = Path(__file__).resolve().parent


def width(text):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in text)


def wrap(text, limit):
    lines, line = [], ''
    for char in text:
        if width(line + char) > limit:
            lines.append(line)
            line = ''
        line += char
    return lines + ([line] if line else [])


def render_svg(section, index, version):
    w, margin, gap, cw = 1800, 60, 40, 820
    colors = {'core': '#0e7490', 'xhttp': '#6d28d9', 'serv00': '#b45309'}
    accent = colors[section['domain']]
    columns = [[], []]
    heights = [0, 0]
    for group in section['groups']:
        gh = 94
        for item in group['items']:
            level = item['path'].count('→') - group['root'].count('→')
            item['_level'] = max(0, level)
            item['_title_lines'] = wrap(item['title'], 48 - item['_level'] * 2)
            item['_note_lines'] = wrap(item['note'], 62 - item['_level'] * 2)
            item['_height'] = len(item['_title_lines']) * 31 + len(item['_note_lines']) * 27 + 27
            gh += item['_height']
        col = 0 if heights[0] <= heights[1] else 1
        columns[col].append((group, gh))
        heights[col] += gh + gap
    notes = [line for note in section['notes'] for line in wrap('• ' + note, 132)]
    footer_y = 195 + max(heights)
    height = footer_y + 88 + len(notes) * 31 + 65
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{height}" viewBox="0 0 {w} {height}" role="img" aria-labelledby="title desc">',
           f'<title id="title">{html.escape(section["title"])}</title>',
           '<desc id="desc">按实际输入路径列出菜单、子菜单、功能与影响范围。可配合MENU-GUIDE.md读取完整文字。</desc>',
           '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;fill:#162b3c}.h{font-size:42px;font-weight:700}.sub{font-size:22px;fill:#526878}.group{font-size:27px;font-weight:700}.label{font-size:23px;font-weight:600}.note{font-size:20px;fill:#42596b}.foot{font-size:23px;fill:#42596b}.path{font-family:Consolas,"Microsoft YaHei",monospace;fill:#526878;font-size:18px}</style>',
           f'<rect width="{w}" height="{height}" fill="#f2f6fa"/>',
           f'<rect x="60" y="44" width="8" height="65" rx="4" fill="{accent}"/>',
           f'<text x="90" y="84" class="h">{index:02d} / {html.escape(section["title"])}</text>',
           f'<text x="90" y="127" class="sub">{html.escape(section["subtitle"])}</text>',
           f'<text x="90" y="164" class="path">{html.escape(version)} · 路径数字对应实际输入顺序 · 非远程控制界面</text>']
    for col, groups in enumerate(columns):
        x, y = margin + col * (cw + gap), 195
        for group, gh in groups:
            out.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{gh}" rx="18" fill="#fff" stroke="#d5e0e9"/>')
            out.append(f'<rect x="{x}" y="{y}" width="8" height="64" rx="4" fill="{accent}"/>')
            out.append(f'<text x="{x+30}" y="{y+44}" class="group">{html.escape(group["title"])}</text>')
            yy = y + 94
            for item in group['items']:
                indent = item['_level'] * 22
                xx = x + 30 + indent
                out.append(f'<text x="{xx}" y="{yy}" class="path">{html.escape(item["path"])}</text>')
                if item['_level']:
                    out.append(f'<path d="M {xx-12} {yy-12} v 20 h 8" fill="none" stroke="#b6c7d3" stroke-width="1.5"/>')
                yy += 30
                for line in item['_title_lines']:
                    out.append(f'<text x="{xx}" y="{yy}" class="label">{html.escape(line)}</text>'); yy += 31
                for line in item['_note_lines']:
                    out.append(f'<text x="{xx}" y="{yy-1}" class="note">{html.escape(line)}</text>'); yy += 27
                yy += -3
            y += gh + gap
    out.append(f'<line x1="60" x2="1740" y1="{footer_y}" y2="{footer_y}" stroke="#c6d6e2"/>')
    yy = footer_y + 44
    for line in notes:
        out.append(f'<text x="60" y="{yy}" class="foot">{html.escape(line)}</text>'); yy += 31
    out.append(f'<text x="60" y="{height-28}" class="path">sing-box-yg / redrohu fork · {index:02d} / 07 · 2026-11-21 · 源码与文字详表：docs/MENU-GUIDE.md</text>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def outputs():
    data = json.loads((HERE / 'menu-guide.json').read_text(encoding='utf8'))
    result = {}
    md = ['# 菜单功能图与完整说明', '',
          f'对应本仓库 **{data["version"]}**；核对源为 `sb.sh` 与 `serv00.sh`。图中的 `→` 表示依次输入，不是一个连写命令。', '',
          '**范围：**涵盖本仓库拥有的菜单、条件子菜单、安装交互和破坏性操作；外部脚本 11/12/13 的内部菜单不由本仓库固定，故只画调用边界，不能当作已逐项审核或安全背书。', '',
          '[打开离线图册](MENU-GUIDE.html) · [机器可读菜单数据](menu-guide.json) · [重新生成脚本](build_menu_guide.py)', '',
          '图册共 7 张，每张均有 SVG（可无损缩放）与 PNG。下方文字表与图由同一份数据生成；协议参数、服务与菜单分发不因图册而改变。', '',
          '## 读图规则', '',
          '- VPS 与 Serv00 是两个独立的 `sb` 菜单，不能混用编号；图中 Serv00 路径用 `S→` 前缀区分，实际输入时不输入 S。',
          '- “表单”“证书”“端口”等文字路径表示交互步骤，不是隐藏的数字菜单。`0`、`3 返回`和 `y/n` 以各级实际提示为准。',
          '- Sing-box 五协议：VLESS REALITY / VMess WS / Hysteria2 / TUIC5 / AnyTLS；1.10 分支不含 AnyTLS。',
          '- 两种 XHTTP 是独立 Xray 服务，不受 Sing-box UUID、启停、端口、出站分流与内核切换控制；主菜单 2 完整卸载会移除。',
          '- Mihomo YAML / 通用 URI 含已部署 XHTTP；官方 Sing-box JSON 不写入 XHTTP。客户端必须支持所选模式；配置导出通过不等于公网连接成功。',
          '- 订阅/密钥/Token/管理令牌都视为敏感信息；本图只使用字段名和默认值，不含真实凭据。', '']
    pages = []
    for i, section in enumerate(data['sections'], 1):
        filename = section['id'] + '.svg'
        result['menu-maps/' + filename] = render_svg(section, i, data['version'])
        md += [f'## {i:02d} · {section["title"]}', '', section['subtitle'], '',
               f'![{section["title"]}](menu-maps/{filename})', '',
               f'[SVG 原图](menu-maps/{filename}) · [PNG 图片](menu-maps/{section["id"]}.png)', '']
        for group in section['groups']:
            md += [f'### {group["title"]}', '', '| 输入路径 | 功能 | 说明与限制 |', '| --- | --- | --- |']
            for item in group['items']:
                md.append('| ' + ' | '.join(v.replace('|', '\\|') for v in [item['path'], item['title'], item['note']]) + ' |')
            md.append('')
        md += ['**本页提醒：**', ''] + ['- ' + note for note in section['notes']] + ['']
        pages.append(f'<section id="{section["id"]}"><h2>{i:02d} · {html.escape(section["title"])}</h2><a href="menu-maps/{filename}">打开可缩放原图</a> · <a href="menu-maps/{section["id"]}.png">PNG</a><img src="menu-maps/{filename}" alt="{html.escape(section["title"])}菜单层级与功能说明"></section>')
    md += ['## 核对、复用与维护', '',
           '```bash', 'python docs/build_menu_guide.py', 'python docs/build_menu_guide.py --check', '```', '',
           '仅使用 Python 标准库生成 SVG、文字详表及离线图册。PNG 用可选工具 `python docs/render_menu_maps.py --browser <本机Chromium绝对路径>` 生成，需要 Playwright 与已有浏览器，不自动下载；中文字体需预先安装。`png-manifest.json` 绑定 SVG/PNG 哈希，防止仅改文字后沿用旧图片。图册不访问外网、不执行菜单、没有遥测。修改菜单后请同步数据并重新生成；`--check` 检查生成物是否过期，相关回归测试检查编号与分发。', '',
           '对于动态外部菜单、条件隐藏项、当前代码仍存在的限制，以实际提示和本图的说明栏为准；本图不会凭空增加功能。', '']
    result['MENU-GUIDE.md'] = '\n'.join(md)
    links = ' · '.join(f'<a href="#{s["id"]}">{i:02d} {html.escape(s["title"])}</a>' for i, s in enumerate(data['sections'], 1))
    result['MENU-GUIDE.html'] = '<!doctype html>\n<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>sing-box-yg 菜单功能图册</title><style>body{margin:0;background:#f2f6fa;color:#162b3c;font:16px/1.7 "Microsoft YaHei",sans-serif}header,main{max-width:1200px;margin:auto;padding:24px}nav{line-height:2.4}a{color:#075b91}section{margin:40px 0}img{display:block;width:100%;height:auto;margin-top:16px}h1{margin:0}p{max-width:85ch}@media print{header{page-break-after:always}section{break-after:page;margin:0}img{max-height:94vh;object-fit:contain}section h2,section>a{display:none}}</style><header><h1>菜单功能图与完整说明</h1><p>' + html.escape(data['version']) + ' · 共7张 · SVG可缩放，PNG可直接保存。所有页面离线可用；不同平台菜单互不混用。</p><p>紫色为独立XHTTP，蓝色为VPS/Sing-box，棕色为Serv00。路径表示逐层输入；外部脚本只标注调用边界。</p><nav>' + links + '</nav><p><a href="MENU-GUIDE.md">完整文字详表</a> · <a href="../README.md">项目说明</a></p></header><main>' + '\n'.join(pages) + '</main></html>\n'
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
