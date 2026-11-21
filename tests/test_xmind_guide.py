"""Check actual menu parentage, source coverage, export and repeatability."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_xmind_guide', ROOT / 'docs/build_xmind_guide.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def walk_model(node):
    yield node
    for child in node['children']:
        yield from walk_model(child)


def walk_topic(node):
    yield node
    for child in node.get('children', {}).get('attached', []):
        yield from walk_topic(child)


class XMindGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(BUILDER.SOURCE.read_text(encoding='utf-8'))
        cls.model = BUILDER.load_menu_model(cls.data)
        cls.nodes = {n['key']: n for r in cls.model for n in walk_model(r)}
        with zipfile.ZipFile(BUILDER.OUTPUT) as archive:
            cls.content = json.loads(archive.read('content.json'))

    def choices(self, path):
        return [c['path'].split('→')[-1] for c in self.nodes['vps:' + path]['children']
                if c['kind'] == 'menu']

    def test_first_canvas_is_actual_vps_menu_not_thematic_index(self):
        self.assertEqual(len(self.content), 3)
        self.assertEqual([c['path'] for c in self.model[0]['children']],
                         [str(i) for i in range(1, 17)] + ['0'])
        children = self.content[0]['rootTopic']['children']['attached']
        self.assertEqual(len(children), 17)
        for i, child in zip(list(range(1, 17)) + [0], children):
            self.assertTrue(child['title'].startswith(str(i) + '. '))
            self.assertEqual(child['id'], BUILDER.identifier('vps:' + str(i)))

    def test_main_labels_come_from_current_scripts(self):
        for root, filename in zip(self.model[:2], ['sb.sh', 'serv00.sh']):
            text = (ROOT / filename).read_text(encoding='utf8')
            for node in root['children']:
                self.assertIn(node['title'], text)

    def test_config_xhttp_and_argo_have_true_parentage(self):
        self.assertEqual(self.choices('3'), [str(i) for i in range(1, 12)] + ['0'])
        self.assertEqual(self.choices('3→11'), [str(i) for i in range(1, 10)] + ['0'])
        self.assertEqual(self.choices('3→11→9'), [str(i) for i in range(1, 9)] + ['0'])
        self.assertEqual(self.choices('3→11→9→8'), ['1', '2', '0'])
        self.assertEqual(self.choices('3→10'), ['1', '2', '3', '4', '5', '0'])
        self.assertEqual(self.choices('3→4'), ['1', '2', '3', '4'])
        self.assertEqual(self.choices('6'), ['1', '2'])

    def test_match_menu_is_under_each_actual_channel(self):
        for i in range(1, 7):
            self.assertEqual(self.choices('5→' + str(i)), ['1', '2', '3'])
        self.assertNotIn('vps:5→通道', self.nodes)

    def test_port_submenus_and_return_choices(self):
        for i in ('3', '4'):
            self.assertEqual(self.choices('4→' + i), ['1', '2', '3', '0'])
            self.assertEqual(self.choices('4→' + i + '→2'), ['1', '2', '0'])
        self.assertEqual(self.choices('3→3→1'), ['1', '2', '0'])
        self.assertEqual(self.choices('3→3→2'), ['1', '2', '0'])

    def test_numeric_nodes_connect_to_immediate_parent(self):
        for root in self.model[:2]:
            for node in walk_model(root):
                for child in node['children']:
                    if node['kind'] == child['kind'] == 'menu':
                        self.assertEqual(child['path'].rsplit('→', 1)[0], node['path'])
        self.assertFalse(any(n['kind'] == 'menu' and '::' in n['path'] for n in self.nodes.values()))

    def test_prompts_are_not_fake_numbered_submenus(self):
        flows = self.nodes['vps:1']['children']
        self.assertEqual(len(flows), 6)
        self.assertTrue(all(c['kind'] == 'flow' for c in flows))
        options = self.nodes['vps:1::防火墙']['children']
        self.assertEqual(len(options), 2)
        self.assertTrue(all(c['kind'] == 'prompt' for c in options))
        self.assertEqual(self.choices('3→11→1'), [])
        self.assertIn('vps:3→11→1::mode', self.nodes)

    def test_all_167_records_keep_exact_descriptions(self):
        expected = [(i['path'], i['title'], i['note']) for s in self.data['sections']
                    for g in s['groups'] for i in g['items']]
        covered = set()
        for node in self.nodes.values():
            for ref in node['sources']:
                covered.add(tuple(ref[k] for k in ('path', 'title', 'note')))
                self.assertIn(ref.get('rendered_note', ref['note']), node['info'])
        self.assertEqual(len(expected), 167)
        self.assertEqual(set(expected), covered)

    def test_log_and_address_scope_match_script_behavior(self):
        log = ' '.join(self.nodes['vps:10']['info'])
        self.assertIn('Alpine下本菜单暂不支持', log)
        self.assertNotIn('或OpenRC日志', log)
        address = ' '.join(self.nodes['vps:15']['warnings'])
        self.assertIn('直连XHTTP导出地址随公共地址刷新', address)
        self.assertIn('禁用该服务的开机自启', ' '.join(self.nodes['vps:6→2']['warnings']))

    def test_info_and_warnings_are_visible_not_only_notes(self):
        topics = {n['id']: n for p in self.content for n in walk_topic(p['rootTopic'])}
        for key, node in self.nodes.items():
            exported = topics[BUILDER.identifier(key)]
            descendants = exported.get('children', {}).get('attached', [])
            for field, prefix in [('info', '【作用 / 说明】\n'), ('warnings', '【注意】\n')]:
                for line in node[field]:
                    self.assertTrue(any(n['title'].startswith(prefix) and
                                        n['title'][len(prefix):].replace('\n', '') == line
                                        for n in descendants), key + ': ' + line)
            self.assertIn('notes', exported)

    def test_no_source_warning_lost(self):
        warnings = {x for n in self.nodes.values() for x in n['warnings']}
        for section in self.data['sections']:
            for note in section['notes']:
                self.assertIn(note, warnings)

    def test_serv00_and_api_are_separate(self):
        self.assertEqual([n['path'] for n in self.model[1]['children']],
                         ['S→' + str(i) for i in range(1, 10)] + ['S→0'])
        self.assertTrue(all(n['kind'] == 'api' for n in self.model[2]['children']))
        self.assertNotIn('serv00:S→1/4', self.nodes)
        self.assertNotIn('serv00:S→固定', self.nodes)

    def test_unique_ids(self):
        ids = []
        for page in self.content:
            ids.append(page['id'])
            ids.extend(n['id'] for n in walk_topic(page['rootTopic']))
        self.assertEqual(len(ids), len(set(ids)))

    def test_saved_native_archive_menu_content_matches_source(self):
        BUILDER.check_workbook(BUILDER.OUTPUT, self.data)

    def test_fresh_generator_has_no_external_assets(self):
        expected = BUILDER.archive_bytes(self.data)
        self.assertEqual(set(expected), {'content.json', 'metadata.json', 'manifest.json'})
        self.assertEqual(json.loads(expected['content.json']), BUILDER.build_content(self.data))

    def test_native_style_changes_are_accepted_but_menu_changes_are_not(self):
        pages = BUILDER.build_content(self.data)
        original = BUILDER.semantic_content(pages)
        pages[0]['theme'] = {'test': 'native style'}
        pages[0]['rootTopic'].pop('class', None)
        self.assertEqual(BUILDER.semantic_content(pages), original)
        pages[0]['rootTopic']['children']['attached'][0]['title'] = 'changed choice'
        self.assertNotEqual(BUILDER.semantic_content(pages), original)

    def test_archive_integrity(self):
        with zipfile.ZipFile(BUILDER.OUTPUT) as archive:
            self.assertIsNone(archive.testzip())

    def test_rebuild_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'rebuilt.xmind'
            second = Path(directory) / 'second.xmind'
            BUILDER.write_workbook(output, self.data)
            BUILDER.write_workbook(second, self.data)
            self.assertEqual(output.read_bytes(), second.read_bytes())
            BUILDER.check_workbook(output, self.data)

    def test_only_one_xmind_workbook_is_delivered(self):
        self.assertEqual({p.name for p in (ROOT / 'docs').glob('*.xmind')},
                         {'MENU-ACTUAL-TREE.xmind'})


if __name__ == '__main__':
    unittest.main()
