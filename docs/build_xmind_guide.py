#!/usr/bin/env python3
"""Build an editable, offline XMind workbook from the shared menu data.

Only the Python standard library is required. No installed XMind templates,
account identifiers, credentials, or network resources are copied into it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import zipfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "menu-guide.json"
OUTPUT = HERE / "MENU-ACTUAL-TREE.xmind"


def identifier(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def topic(key: str, title: str, children=None, note=None) -> dict:
    result = {"id": identifier(key), "class": "topic", "title": title}
    if children:
        result["children"] = {"attached": children}
    if note:
        result["notes"] = {"plain": {"content": note}}
    return result


def sheet(key: str, title: str, root: dict) -> dict:
    root["structureClass"] = "org.xmind.ui.logic.right"
    return {
        "id": identifier("sheet:" + key),
        "class": "sheet",
        "title": title,
        "rootTopic": root,
        "topicOverlapping": "overlap",
        "extensions": [{
            "provider": "org.xmind.ui.skeleton.structure.style",
            "content": {"centralTopic": "org.xmind.ui.logic.right"},
        }],
    }


def wrapped(text: str) -> str:
    # Keep Latin protocol names intact; count CJK glyphs as two display units.
    lines, line, width = [], '', 0
    for token in re.findall(r'[A-Za-z0-9][A-Za-z0-9.+_/-]*|[\s\S]', text):
        if token == '\n':
            lines.append(line)
            line, width = '', 0
            continue
        size = sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in token)
        if line and width + size > 60:
            lines.append(line)
            line, width = '', 0
        line += token
        width += size
    lines.append(line)
    return '\n'.join(lines)


def load_menu_model(data: dict) -> list[dict]:
    # Import by absolute location as tests may load this module through importlib.
    import importlib.util
    spec = importlib.util.spec_from_file_location("menu_tree", HERE / "menu_tree.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.model(data)


def menu_topic(node: dict, version: str) -> dict:
    kind = node["kind"]
    title = node["title"]
    if kind == "menu":
        title = node["path"].split("→")[-1] + ". " + title
    title = wrapped(title)
    children = [menu_topic(child, version) for child in node["children"]]
    # Explanation branches are visibly labelled, never masquerading as choices.
    for i, text in enumerate(node["info"]):
        children.append(topic(node["key"] + f":info:{i}", "【作用 / 说明】\n" + wrapped(text)))
    for i, text in enumerate(node["warnings"]):
        children.append(topic(node["key"] + f":warning:{i}", "【注意】\n" + wrapped(text)))
    notes = [version]
    if node["path"]:
        notes.append("实际菜单路径：" + node["path"] if kind == "menu" else "交互流程 / 说明（不是新增菜单编号）")
    notes.extend(node["info"])
    notes.extend("注意：" + text for text in node["warnings"])
    result = topic(node["key"], title, children, "\n".join(notes))
    return result


def build_content(data: dict) -> list[dict]:
    titles = ["VPS · 主菜单及全部子菜单", "Serv00 · 主菜单及交互流程", "Serv00 · API（非数字菜单）"]
    return [sheet(root["key"], title, menu_topic(root, data["version"]))
            for root, title in zip(load_menu_model(data), titles)]


def archive_bytes(data: dict) -> dict[str, bytes]:
    entries = {
        "content.json": build_content(data),
        "metadata.json": {"dataStructureVersion": "2",
                          "creator": {"name": "Sing-box-yg menu guide", "version": "2.0"},
                          "layoutEngineVersion": "3"},
        "manifest.json": {"file-entries": {"content.json": {}, "metadata.json": {}}},
    }
    return {name: (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            for name, value in entries.items()}


def write_workbook(path: Path, data: dict) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in archive_bytes(data).items():
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)


def semantic_content(pages: list[dict]) -> list[dict]:
    """Allow XMind's saved themes/layout/thumbnail without losing guide checks."""
    def node(topic):
        return {
            'id': topic['id'], 'title': topic['title'],
            'notes': topic.get('notes', {}).get('plain', {}).get('content', ''),
            'children': [node(child) for child in topic.get('children', {}).get('attached', [])],
        }
    return [{'id': page['id'], 'title': page['title'], 'root': node(page['rootTopic'])}
            for page in pages]


def check_workbook(path: Path, data: dict) -> None:
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, "Damaged XMind archive"
        assert {'content.json', 'metadata.json', 'manifest.json'} <= set(archive.namelist())
        actual = json.loads(archive.read('content.json'))
        assert semantic_content(actual) == semantic_content(build_content(data)), 'Stale menu content or parentage'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if args.check:
        check_workbook(args.output, data)
        count = sum(len(g["items"]) for s in data["sections"] for g in s["groups"])
        print(f"XMind: 3 actual-menu sheets; {count} source records covered; menu content matches source (native styles preserved).")
    else:
        write_workbook(args.output, data)
        print(args.output)


if __name__ == "__main__":
    main()
