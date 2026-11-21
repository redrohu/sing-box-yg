#!/usr/bin/env python3
"""Render actual XMind tree as a full SVG and an explicitly limited overview PNG.

Optional preview dependency: Pillow. The .xmind generator itself remains stdlib.
"""
import html
import json
from pathlib import Path
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = Path('C:/Windows/Fonts/msyh.ttc')
BODY = ImageFont.truetype(str(FONT), 19)
LINE, GAP, WIDTH, DX = 28, 18, 430, 500
COLORS = ['#0f766e', '#2563eb', '#7c3aed', '#b45309', '#be123c', '#0369a1']


def wrap(text, width=WIDTH - 32):
    # XMind's soft line breaks must not cause double wrapping/orphan fragments.
    text = text.replace('\n', '')
    text = re.sub(r'(?=【(?:作用 / 说明|注意)】)', '\n', text).strip('\n')
    lines = []
    for part in text.split('\n'):
        line = ''
        for char in re.findall(r'[A-Za-z0-9][A-Za-z0-9.+_/-]*|[\s\S]', part):
            if line and BODY.getlength(line + char) > width:
                lines.append(line)
                line = ''
            line += char
        lines.append(line)
    return lines


def layout(topic, depth=0, color='#334155'):
    lines = wrap(topic['title'])
    own = len(lines) * LINE + 26
    children = [layout(c, depth + 1, COLORS[i % len(COLORS)] if depth == 0 else color)
                for i, c in enumerate(topic.get('children', {}).get('attached', []))]
    span = max(own, sum(c['span'] for c in children) + GAP * max(0, len(children) - 1))
    return dict(lines=lines, own=own, children=children, span=span, depth=depth, color=color)


def place(node, top=94):
    node['x'] = 30 + node['depth'] * DX
    node['y'] = top + (node['span'] - node['own']) / 2
    offset = top + (node['span'] - sum(c['span'] for c in node['children']) -
                    GAP * max(0, len(node['children']) - 1)) / 2
    for child in node['children']:
        place(child, offset)
        offset += child['span'] + GAP


def nodes(root):
    yield root
    for child in root['children']:
        yield from nodes(child)


def svg(root, title):
    items = list(nodes(root))
    w = max(n['x'] for n in items) + WIDTH + 30
    h = root['span'] + 140
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<rect width="100%" height="100%" fill="#f8fafc"/>',
             f'<text x="30" y="42" font-family="Microsoft YaHei,sans-serif" font-size="26" font-weight="bold">{html.escape(title)}</text>']
    for n in items:
        x, y = n['x'], n['y']
        for c in n['children']:
            ax, ay, bx, by = x + WIDTH, y + n['own'] / 2, c['x'], c['y'] + c['own'] / 2
            parts.append(f'<path d="M {ax},{ay} C {ax+35},{ay} {bx-35},{by} {bx},{by}" fill="none" stroke="{c["color"]}" stroke-width="2"/>')
        danger = n['lines'][0].startswith('【注意】')
        fill = '#fff7ed' if danger else '#ffffff'
        parts.append(f'<rect x="{x}" y="{y}" width="{WIDTH}" height="{n["own"]}" rx="9" fill="{fill}" stroke="{n["color"]}" stroke-width="2"/>')
        for i, line in enumerate(n['lines']):
            parts.append(f'<text x="{x+16}" y="{y+29+i*LINE}" font-family="Microsoft YaHei,sans-serif" font-size="19" fill="#0f172a">{html.escape(line)}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)


def overview(root):
    """Show real main choices + their direct submenus, never substitute categories."""
    result = {'title': root['title'], 'children': {'attached': []}}
    for main in root['children']['attached']:
        children = main.get('children', {}).get('attached', [])
        desc = [c['title'].replace('\n', '') for c in children if c['title'].startswith('【作用')]
        warn = [c['title'].replace('\n', '') for c in children if c['title'].startswith('【注意')]
        label = main['title']
        if desc:
            label += '\n' + desc[0]
        if warn:
            label += '\n' + warn[0]
        direct = [{'title': c['title']} for c in children
                  if not c['title'].startswith(('【作用', '【注意'))]
        result['children']['attached'].append({'title': label, 'children': {'attached': direct}})
    return result


def png(root, path):
    items = list(nodes(root))
    width = int(max(n['x'] for n in items) + WIDTH + 30)
    height = int(root['span'] + 140)
    image = Image.new('RGB', (width, height), '#f8fafc')
    draw = ImageDraw.Draw(image)
    draw.text((30, 18), '实际菜单结构速览（主菜单＋直接子菜单；更深层见 XMind / 完整 SVG）', font=BODY, fill='#0f172a')
    for n in items:
        x, y = n['x'], n['y']
        for c in n['children']:
            ay, by = y + n['own'] / 2, c['y'] + c['own'] / 2
            draw.line([(x + WIDTH, ay), (x + WIDTH + 35, ay),
                       (c['x'] - 35, by), (c['x'], by)], fill=c['color'], width=2)
        draw.rounded_rectangle((x, y, x + WIDTH, y + n['own']), radius=9,
                               fill='white', outline=n['color'], width=2)
        for i, line in enumerate(n['lines']):
            draw.text((x + 16, y + 10 + i * LINE), line, font=BODY, fill='#0f172a')
    image.save(path)


def main():
    target = HERE / 'menu-maps'
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(HERE / 'MENU-ACTUAL-TREE.xmind') as archive:
        root = json.loads(archive.read('content.json'))[0]['rootTopic']
    full = layout(root)
    place(full)
    (target / 'vps-actual-menu-full.svg').write_text(svg(full, 'VPS实际菜单完整树：菜单、功能及注意事项'), encoding='utf8')
    preview = layout(overview(root))
    place(preview)
    png(preview, target / 'vps-actual-menu-overview.png')
    print('Full SVG:', int(full['span']), 'px high;', len(list(nodes(full))), 'topics')
    print('Overview PNG:', int(preview['span']), 'px high')


if __name__ == '__main__':
    main()
