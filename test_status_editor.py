import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import threading
import re

from status_editor import list_statuses, numeric_effects, readonly_reason, set_status, load_status_catalog, status_conditions


class StatusEditorTests(unittest.TestCase):
    def test_script_conditions_are_separate_from_editing_restriction(self):
        row = dict(dynamicModifier=['Traits/SiLiTaoSheng'])
        self.assertIn('首次遭遇致命伤害', status_conditions(row)[0])
        self.assertIn('每场战斗', status_conditions(row)[0])
        self.assertIn('只读', readonly_reason(row))
        self.assertIn('未提供', status_conditions(dict(dynamicModifier=['Unknown/Script']))[0])
        self.assertEqual(status_conditions({}), [])
        self.assertIn('免疫', status_conditions(dict(tagsNotActive=['免疫']))[0])

    def test_catalog_merges_multiple_official_workbooks_and_creation_links(self):
        class Sheet:
            def __init__(self, header, rows): self.header, self.rows = header, rows
            def iter_rows(self, **kwargs): return iter([self.header] if kwargs['min_row'] == 3 else self.rows)
        class Book(dict):
            @property
            def sheetnames(self): return list(self)
            def close(self): pass
        header = (None, 'uid', 'uName', 'isVisible', 'rarity', 'tickType', 'lifeTime', 'continousEffect')
        books = [Book(BuffData=Sheet(header, [(None, 1, '第一状态', True, 1, 'Infinite', 1, '攻击|2')])),
                 Book(BuffData=Sheet(header, [(None, 2, '第二状态', True, 2, 'Time', 48, '防御|3')])),
                 Book(TraitData=Sheet((None, 'uid', 'uName', 'isUseByPlayer', 'bonusBuff'), [(None, 3, '创建天赋', 'True', '第一状态')]))]
        with patch('status_editor.ZipFile') as archive, patch('status_editor.load_workbook', side_effect=books), patch('UnityPy.load', return_value=SimpleNamespace(objects=[])):
            archive.return_value.__enter__.return_value.infolist.return_value = [SimpleNamespace(filename=f'Game/xls/1/{i}.xlsx') for i in range(3)]
            archive.return_value.__enter__.return_value.read.return_value = b'workbook'
            catalog = load_status_catalog(Path('synthetic-game'))
        self.assertEqual(set(catalog), {'第一状态', '第二状态'})
        self.assertEqual(catalog['第一状态']['source'], '创建角色可选')
        self.assertEqual(catalog['第一状态']['creation'], ['创建天赋'])
        self.assertEqual(catalog['第二状态']['order'], 1)

    def setUp(self):
        self.catalog = {}
        for key, uid, rarity, order in (("普通", 20, 1, 0), ("临时", 10, 3, 1), ("特殊", 30, 2, 2)):
            self.catalog[key] = dict(key=key, uName=key, id=uid, rarity=rarity, order=order, name=key,
                                     description="游戏说明", source="创建角色可选" if key == "普通" else "其他状态",
                                     creation=["创建天赋"] if key == "普通" else [], isVisible=True,
                                     permanent=key != "临时", tickType="Time" if key == "临时" else "Infinite",
                                     lifeTime=48 if key == "临时" else 1, continousEffect=["攻击|2", "命中|0.1"], readonly="")
        self.catalog["特殊"].update(dynamicModifier=["script"])
        self.catalog["特殊"]["readonly"] = readonly_reason(self.catalog["特殊"])
        self.hero = dict(buffLib=dict(buffInstances=[], buffStats={"攻击": 10, "其他": 42}, buffsFromTemplete=[]), Traits=[123])

    def test_add_remove_roundtrip_cache_and_unrelated_data(self):
        original = copy.deepcopy(self.hero)
        set_status(self.hero, self.catalog, "普通", True, 100)
        row = list_statuses(self.hero, self.catalog)["rows"][0]
        self.assertTrue(row["owned"] and row["active"])
        self.assertEqual(self.hero["buffLib"]["buffStats"]["攻击"], 12)
        self.assertEqual(self.hero["buffLib"]["buffStats"]["命中"], .1)
        after = copy.deepcopy(self.hero)
        set_status(self.hero, self.catalog, "普通", True, 100)
        self.assertEqual(self.hero, after)
        set_status(self.hero, self.catalog, "普通", False, 100)
        self.assertEqual(self.hero["buffLib"]["buffStats"]["攻击"], 10)
        self.assertEqual(self.hero["buffLib"]["buffStats"]["命中"], 0)
        self.assertEqual(self.hero["Traits"], original["Traits"])
        self.assertEqual(self.hero["buffLib"]["buffStats"]["其他"], 42)
        self.assertEqual(self.hero["buffLib"]["buffInstances"], [])

    def test_http_status_writes_require_token_and_reject_readonly(self):
        from web_app import EditorState, make_app
        state = EditorState.__new__(EditorState)
        state.team_data = {}
        state.char_data = {'Data': {'value': {'createdCharacter': {'100401': self.hero}}}}
        state.time_data = {'Data': {'value': {'TotalQuaterPassed': 10}}}
        state.status_catalog = self.catalog
        state._status_lock = threading.RLock()
        with patch('web_app.EditorState', return_value=state): app = make_app(8765)
        client = app.test_client()
        token = re.search(r'name="wulin-token" content="([^"]+)"', client.get('/').text)[1]
        before = copy.deepcopy(self.hero)
        self.assertEqual(client.post('/api/statuses', json={'key': '普通', 'owned': True}).status_code, 403)
        self.assertEqual(self.hero, before)
        headers = {'X-Wulin-Token': token}
        self.assertEqual(client.post('/api/statuses', json={'key': '特殊', 'owned': True}, headers=headers).status_code, 400)
        self.assertEqual(self.hero, before)
        self.assertEqual(client.post('/api/statuses', json={'key': '普通', 'owned': True}, headers=headers).status_code, 200)
        self.assertTrue(client.get('/api/statuses').json['rows'][0]['owned'])

    def test_temporary_status_uses_game_time_and_official_lifetime(self):
        set_status(self.hero, self.catalog, "临时", True, 123.5)
        instance = self.hero["buffLib"]["buffInstances"][0]
        self.assertEqual((instance["initTime"], instance["lifeTime"], instance["stack"]), (123.5, 48, 1))

    def test_special_unknown_conditions_and_invalid_numbers_are_atomic(self):
        before = copy.deepcopy(self.hero)
        for key, owned, now in (("特殊", True, 1), ("未知", True, 1), ("普通", "true", 1), ("普通", True, float('nan'))):
            with self.assertRaises(ValueError): set_status(self.hero, self.catalog, key, owned, now)
            self.assertEqual(self.hero, before)
        for field, value in (("instantEffect", ["体质|2"]), ("endRemoveEffect", ["体质|-2"]),
                             ("tagsNotActive", ["免疫"]), ("teammateBuff", ["队友"]),
                             ("displayType", "经脉"), ("displayType", "家园"), ("continousEffect", ["攻击|nan"]),
                             ("continousEffect", ["攻击|1|2"]), ("lifeTime", 0)):
            row = dict(self.catalog["普通"], **{field: value})
            self.assertTrue(readonly_reason(row), (field, value))
        self.assertTrue(readonly_reason(dict(self.catalog["普通"], continousEffect=["队伍体力Max@团队|10"])))
        for key in ("团队体力效果_0", "团队心情效果_0", "主角与测试角色情缘buff"):
            self.assertTrue(readonly_reason(dict(self.catalog["普通"], uName=key)))

    def test_template_and_overrides_are_readonly(self):
        self.hero["buffLib"]["buffsFromTemplete"] = ["普通"]
        with self.assertRaises(ValueError): set_status(self.hero, self.catalog, "普通", True, 0)
        self.hero["buffLib"]["buffsFromTemplete"] = []
        self.hero["buffLib"]["buffInstances"] = [dict(dataId="普通", isValid=True, overrideValues=[2], stack=1)]
        with self.assertRaises(ValueError): set_status(self.hero, self.catalog, "普通", False, 0)

    def test_unknown_owned_is_shown_readonly_and_inactive_is_still_owned(self):
        self.hero["buffLib"]["buffInstances"] = [dict(dataId="缺表", isValid=False, lifeTime=2)]
        row = list_statuses(self.hero, self.catalog)["rows"][0]
        self.assertEqual(row["key"], "缺表")
        self.assertTrue(row["owned"] and row["readonly"])
        self.assertFalse(row["active"])

    def test_sorting_filters_and_creation_source(self):
        self.assertEqual([x["key"] for x in list_statuses(self.hero, self.catalog)["rows"]], ["普通", "临时", "特殊"])
        self.assertEqual([x["key"] for x in list_statuses(self.hero, self.catalog, sort="id")["rows"]], ["临时", "普通", "特殊"])
        self.assertEqual([x["key"] for x in list_statuses(self.hero, self.catalog, sort="rarity")["rows"]], ["临时", "特殊", "普通"])
        self.assertEqual([x["key"] for x in list_statuses(self.hero, self.catalog, kind="temporary")["rows"]], ["临时"])
        self.assertEqual([x["key"] for x in list_statuses(self.hero, self.catalog, source="创建角色可选")["rows"]], ["普通"])
        set_status(self.hero, self.catalog, "普通", True, 0)
        self.assertEqual(list_statuses(self.hero, self.catalog, sort="rarity")["rows"][0]["key"], "普通")

    def test_missing_cache_prevents_removal_and_duplicate_instances_are_removed_together(self):
        instance = dict(dataId="普通", isValid=True, overrideValues=None, stack=2, lifeTime=1)
        self.hero["buffLib"]["buffInstances"] = [instance, dict(instance, stack=1, isValid=False)]
        before = copy.deepcopy(self.hero)
        with self.assertRaises(ValueError): set_status(self.hero, self.catalog, "普通", False, 0)
        self.assertEqual(self.hero, before)
        self.hero["buffLib"]["buffStats"]["命中"] = .2
        set_status(self.hero, self.catalog, "普通", False, 0)
        self.assertEqual(self.hero["buffLib"]["buffStats"]["攻击"], 6)
        self.assertEqual(self.hero["buffLib"]["buffStats"]["命中"], 0)
        self.assertEqual(self.hero["buffLib"]["buffInstances"], [])


if __name__ == "__main__":
    unittest.main()
