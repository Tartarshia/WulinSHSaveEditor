import copy
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import threading
import re
import struct
from decimal import Decimal

from status_editor import list_statuses, numeric_effects, readonly_reason, set_status, load_status_catalog, status_conditions
from status_reference import acquisition_reference, local_trigger_reference, readable_runtime_summary, description_trigger_reference
from modifier_conditions import OdinReader, explain_modifiers, explain_condition, compact_condition, read_runtime_tables, read_runtime_modifiers
from status_sources import source_notes, modifier_source_notes
from status_reviews import FINGERPRINTS, NOTES, RESOURCE_GAPS, BUFF_DEFINITIONS_HASH, review_fingerprint, reviewed_resolution


class StatusEditorTests(unittest.TestCase):
    def test_present_but_unreadable_modifier_is_not_reported_as_missing(self):
        path='Assets/__WuLin/Scripts/ModShare/Runtime/GDData/DynamicModifier/PetTraits/SiJiErDong1.asset'
        unreadable=SimpleNamespace(read_typetree=lambda:dict(serializationData=dict(SerializedFormat=1)))
        bundle=SimpleNamespace(type=SimpleNamespace(name='AssetBundle'),
                               read_typetree=lambda:dict(m_Container=[(path,dict(asset=dict(m_FileID=0,m_PathID=1)))]),
                               assets_file=SimpleNamespace(objects={1:unreadable}))
        result=read_runtime_modifiers(SimpleNamespace(objects=[bundle]),{'PetTraits/SiJiErDong1'})
        self.assertIn('read_error',result['PetTraits/SiJiErDong1'])
        branch=explain_modifiers(['PetTraits/SiJiErDong1'],result)[0]
        self.assertFalse(branch['complete'])
        self.assertIn('存在',branch['conditions'][0])
        self.assertEqual(branch['path'],path)

    def test_review_inventory_and_configuration_drift_guards(self):
        self.assertEqual(set(FINGERPRINTS),set(NOTES))
        self.assertEqual(len(NOTES),70)
        self.assertEqual(RESOURCE_GAPS,{3012,31050,31056})
        self.assertTrue(all(re.fullmatch('[a-f0-9]{64}',value) for value in FINGERPRINTS.values()))
        self.assertTrue(all('暂未解析' not in text and '分支' not in text for text in NOTES.values()))
        self.assertIn('轻功',NOTES[40254])
        row=dict(id=1405,key='test',continousEffect=[],dynamicModifier=['x'])
        runtime=dict(x=dict(path='x',conditions=[],stages=[206],actions=[dict(value=1)],failed_actions=[]))
        digest=review_fingerprint(row,runtime)
        with patch.dict(FINGERPRINTS,{1405:digest}):
            self.assertEqual(reviewed_resolution(row,runtime,BUFF_DEFINITIONS_HASH)['state'],'reviewed')
            self.assertIsNone(reviewed_resolution(row,runtime,'changed-definition'))
            self.assertIsNone(reviewed_resolution(row,runtime))
            for changed in (dict(row,id=33527),dict(row,key='other'),dict(row,continousEffect=['攻击|1']),
                            dict(row,instantEffect=['体质|1']),dict(row,endRemoveEffect=['体质|-1'])):
                self.assertIsNone(reviewed_resolution(changed,runtime,BUFF_DEFINITIONS_HASH))
            for field,value in (('conditions',[dict(x=1)]),('actions',[]),('failed_actions',[dict(x=1)]),('stages',[4])):
                changed=copy.deepcopy(runtime);changed['x'][field]=value
                self.assertIsNone(reviewed_resolution(row,changed,BUFF_DEFINITIONS_HASH))

    def test_missing_pet_resource_is_explicit_not_a_guessed_wudao_effect(self):
        row=dict(id=31050,key='宠物特征伺机而动',description='',continousEffect=[],dynamicModifier=['PetTraits/SiJiErDong1'])
        with patch.dict(FINGERPRINTS,{31050:review_fingerprint(row,{})}):
            review=reviewed_resolution(row,{},BUFF_DEFINITIONS_HASH)
            self.assertEqual(review['state'],'resource_missing')
            self.assertIn('不是武道天赋',review['notes'][0])
            self.assertNotIn('增加100',review['notes'][0])
            self.assertIsNone(reviewed_resolution(dict(row,description='新版已有说明'),{},BUFF_DEFINITIONS_HASH))
            # Present-but-unreadable is not the same as missing from the index.
            self.assertIsNone(reviewed_resolution(row,{'PetTraits/SiJiErDong1':dict(read_error='resource_unreadable')},BUFF_DEFINITIONS_HASH))
        display=dict(self.catalog['特殊'],condition_review=review)
        data=list_statuses(self.hero,{'特殊':display})['rows'][0]
        self.assertEqual(data['condition_review_state'],'resource_missing')
        self.assertIn('资源不完整',' '.join(data['conditions']))
        self.assertTrue(data['readonly'])
        with self.assertRaises(ValueError):set_status(self.hero,{'特殊':display},'特殊',True,0)

    def test_modifier_sources_reject_random_and_unknown_targets(self):
        action=dict(type='WuLin.ApplyBuffToCharacterAction, ModShare.Runtime',fields=dict(
            useRandomBuff=False,buffName='child',buffTarget=dict(fields=dict(target=2))))
        catalog=dict(parent=dict(key='parent',name='原状态',dynamicModifier=['x']),child=dict(key='child',name='附属'))
        runtime=dict(x=dict(actions=[action]))
        self.assertIn('受击者',modifier_source_notes(catalog,runtime)['child'][0])
        action['fields']['useRandomBuff']=True
        self.assertEqual(modifier_source_notes(catalog,runtime),{})
        action['fields']['useRandomBuff']=False
        action['fields']['buffTarget']['fields']['target']=99
        self.assertEqual(modifier_source_notes(catalog,runtime),{})

    def test_readable_scripts_preserve_attack_defence_and_separate_effects(self):
        def branch(timing,conditions): return dict(path='x',complete=True,timing=[timing],conditions=conditions)
        attack=branch('攻击方伤害计算前',['随机触发概率 15%','15 ≤ 战斗攻击者·等级-战斗受击者·等级 ≤ 99999','战斗受击者·Boss角色 = 0'])
        text=readable_runtime_summary([attack])[0]
        for word in ('15%','15 级','不是首领'): self.assertIn(word,text)
        defence=branch('受击方伤害计算后',['本次伤害判定：发生格挡'])
        text=readable_runtime_summary([attack,defence])[0]
        self.assertIn('受到攻击并触发格挡',text)
        self.assertIn('结算对应效果',text)
        self.assertNotIn('或者',text)
        self.assertEqual(readable_runtime_summary([defence,branch('未知',['未识别'])]),[])

    def test_explicit_description_conditions_preserve_probability_and_limits(self):
        text='处于“酩酊”状态时，触发暴击时有25%概率造成10点内伤，每场战斗仅1次。'
        self.assertIn(text, description_trigger_reference(dict(description=text))[0])
        self.assertEqual(description_trigger_reference(dict(description='格挡与闪避降低。')), [])
        self.assertEqual(description_trigger_reference(dict(description='攻击时增加{value}点伤害')), [])
        notes=status_conditions(dict(dynamicModifier=['x'],description='每天自动获得1贯钱。'))
        self.assertIn('游戏说明', notes[0])
        self.assertNotIn('未解析', notes[0])

    def test_runtime_sources_do_not_invent_recipient_or_unlock_level(self):
        def array(items): return dict(fields={},items=[items])
        tables=dict(ItemData=[dict(UName='药',EquipBuff=['装备状态'],ConsumeEffect=dict(fields=dict(refNames=array(['中毒']))))],
                    KungfuData=[dict(UName='内功',ActiveInternalBuffs=['内功状态'],CastBuffs=['招式状态'])],
                    CharacterPetExtendData=[dict(UName='宠物',AbilityBuffs=array([dict(fields=dict(key='宠物状态',isValid=True,values=[5]))]))])
        notes=source_notes(tables)
        self.assertIn('对象以物品用法为准',notes['中毒'][0])
        self.assertIn('设为主内功',notes['内功状态'][0])
        self.assertNotIn('5级',notes['宠物状态'][0])
        # Source discovery must not hide a genuinely unknown activation trigger.
        result=status_conditions(dict(dynamicModifier=['x'],source_notes=notes['装备状态']))
        self.assertIn('激活条件：暂未解析。',result)

    def test_runtime_table_primary_root_and_strict_default_bounds(self):
        def string(value): return b'\x00'+struct.pack('<i',len(value))+value.encode('ascii')
        data=b'\x01'+string('Test')+b'\x2f'+struct.pack('<i',0)+string('Rows')+struct.pack('<i',0)
        data+=b'\x06'+struct.pack('<q',0)+b'\x07\x05'
        obj=SimpleNamespace(type=SimpleNamespace(name='MonoBehaviour'),peek_name=lambda:'Test',
                            read_typetree=lambda:dict(serializationData=dict(SerializedFormat=0,SerializedBytes=data)))
        self.assertEqual(read_runtime_tables(SimpleNamespace(objects=[obj]),{'Test'}),{'Test':[]})
        self.assertEqual(read_runtime_tables(SimpleNamespace(objects=[obj]),{'Other'}),{})
        obj.read_typetree=lambda:dict(serializationData=dict(SerializedFormat=0,SerializedBytes=data[:-1]))
        self.assertEqual(read_runtime_tables(SimpleNamespace(objects=[obj]),{'Test'}),{})
        with self.assertRaises(ValueError): OdinReader(bytes(2_000_001))
        with self.assertRaises(ValueError): OdinReader(bytes(16_000_001),table=True)

    def test_human_conditions_story_variants_and_no_diagnostic_filler(self):
        row=dict(key='剧情博采众长', uName='剧情博采众长', id=13529, description='外功到第十重，内功到第十重。', dynamicModifier=['script'])
        notes=status_conditions(row)
        self.assertIn('基础攻击', notes[0])
        self.assertIn('基础防御', notes[0])
        self.assertNotIn('分支', ' '.join(notes))
        self.assertEqual(acquisition_reference(row), ([], []))
        self.assertIn('只读', readonly_reason(row))
        self.assertEqual(local_trigger_reference(dict(row,id=13530)), [])
        self.assertEqual(local_trigger_reference(dict(row,description='新版未知效果')), [])
        branch=dict(path='Assets/x', timing=['武功变化时'], conditions=['此脚本分支没有额外条件项（不代表状态可自动获得）'],complete=True)
        self.assertEqual(status_conditions(dict(dynamicModifier=['script'],runtime_conditions=[branch])), ['激活条件：暂未解析。'])
        valid=dict(branch, conditions=['-99900% ≤ 持有者生命比例 ≤ 30.0%','1 ≤ 队伍·持有者是队友*战场·敌人数量 ≤ 9999'])
        self.assertIn('自身气血不高于 30%', readable_runtime_summary([valid])[0])
        self.assertIn('队伍伙伴', readable_runtime_summary([valid])[0])
        self.assertEqual(readable_runtime_summary([dict(valid,conditions=['任意复杂公式'])]), [])

    def test_bounded_odin_reader_decimals_strings_and_fail_closed(self):
        def string(value, wide=True):
            return bytes([int(wide)]) + struct.pack('<i', len(value)) + value.encode('utf-16-le' if wide else 'latin-1')
        # Named string followed by a named decimal in CLR memory layout.
        data = b'\x27' + string('label', False) + string('测试范围')
        data += b'\x23' + string('min') + struct.pack('<IIII', 0x80010000, 0, 125, 0)
        self.assertEqual(OdinReader(data).read(), dict(label='测试范围', min=Decimal('-12.5')))
        maximal = b'\x23' + string('x') + struct.pack('<IIII', 0, 0xffffffff, 0xffffffff, 0xffffffff)
        self.assertEqual(OdinReader(maximal).read()['x'], Decimal('79228162514264337593543950335'))
        for bad in (data[:-1], b'\xff', b'\x27\x01\xff\xff\xff\x7f', b'\x31trailing'):
            with self.assertRaises(ValueError): OdinReader(bad).read()
        with self.assertRaises(ValueError): OdinReader(bytes(2_000_001))
        self.assertEqual(OdinReader(b'\x09'+string('ref')+struct.pack('<i', 3)).read()['ref'], {'reference':3})
        nested = b'\x01' + string('conditions') + b'\x2f' + struct.pack('<i',0) + string('List') + struct.pack('<i',0)
        nested += b'\x06' + struct.pack('<q',1) + b'\x28' + string('条件') + b'\x07\x05'
        self.assertEqual(OdinReader(nested).read()['conditions']['items'], [['条件']])
        for bad in (nested[:-1], nested.replace(b'\x07\x05', b'\x05\x05')):
            with self.assertRaises(ValueError): OdinReader(bad).read()

    def test_runtime_modifier_conditions_keep_branch_logic_and_full_bounds(self):
        def node(kind, **values): return dict(type='WuLin.'+kind+', ModShare.Runtime', fields=values, items=[])
        expression = node('SimpleEvalValueMatchedCondition', eval=node('Eval', evalStr='【持有者_Hp】/【持有者_生命】'), minValue=Decimal('-999'), maxValue=Decimal('.3'))
        self.assertIn('30.0%', explain_condition(expression, {}))
        self.assertIn('-99900%', explain_condition(expression, {}))
        self.assertNotIn('-99900%', compact_condition(explain_condition(expression, {})))
        runtime = {'a':dict(path='Assets/a.asset', stages=[200], conditions=[expression]),
                   'b':dict(path='Assets/b.asset', stages=[208], conditions=[node('UnknownCondition')]),
                   'c':dict(path='Assets/c.asset', stages=[205], conditions=[])}
        result = explain_modifiers(['a','b','c','missing'], runtime)
        self.assertTrue(result[0]['complete'])
        self.assertFalse(result[1]['complete'])
        self.assertFalse(result[3]['complete'])
        self.assertEqual(result[0]['timing'], ['进入战斗时'])
        self.assertIn('不代表状态可自动获得', result[2]['conditions'][0])
        invalid_group=node('BattleActorCheckLabelCondition', checkGroups=[['a'],['b']])
        with self.assertRaises(ValueError): explain_condition(invalid_group,{})
        check = node('CheckDamageCondition', checkDict=[node('', **{'$k':5,'$v':0})])
        self.assertIn('未发生暴击', explain_condition(check,{}))
        probability=node('RandomActiveModifier', rate=25, useCharacterPropAsRate=False)
        self.assertIn('25%', explain_condition(probability,{}))
        actor=node('CurrentActionUsingSpecifiedKungfu', kungfuType=1, idOrName=[], excludeIdOrName=None)
        self.assertIn('外功', explain_condition(actor,{}))
        self.assertIn('尚未翻译', result[1]['conditions'][0])

    def test_community_routes_do_not_match_npc_or_other_id_variants(self):
        row = dict(key='千王之王', id=3523)
        notes, refs = acquisition_reference(row)
        self.assertIn('20', notes[0])
        self.assertTrue(refs[0]['url'].startswith('https://heros-adventure.wikidot.com/'))
        self.assertEqual(acquisition_reference(dict(row, id=9999)), ([], []))
        self.assertEqual(acquisition_reference(dict(row, key='伙伴特征千王之王')), ([], []))
        self.assertEqual(acquisition_reference(dict(row, id='bad')), ([], []))
        trigger = dict(key='影子护卫', id=3506, description='生命值低于25%')
        self.assertIn('25%', local_trigger_reference(trigger)[0])
        self.assertEqual(local_trigger_reference(dict(trigger, description='新版不同条件')), [])

    def test_script_conditions_are_separate_from_editing_restriction(self):
        row = dict(dynamicModifier=['Traits/SiLiTaoSheng'])
        self.assertIn('首次遭遇致命伤害', status_conditions(row)[0])
        self.assertIn('每场战斗', status_conditions(row)[0])
        self.assertIn('只读', readonly_reason(row))
        self.assertEqual(status_conditions(dict(dynamicModifier=['Unknown/Script'])), ['激活条件：暂未解析。'])
        self.assertEqual(status_conditions({}), [])
        self.assertEqual(status_conditions(dict(tagsNotActive=['免疫'])), [])

    def test_property_thresholds_and_readonly_guard(self):
        for raw, expected in [('福缘|10|9999', '福缘 ≥ 10'), ('仁德|-9999|-100', '仁德 ≤ -100'),
                              ('体质|25|9999', '体质 ≥ 25'), ('口才|1|999', '1 ≤ 口才 ≤ 999'),
                              ('悟性|10|10', '悟性 = 10')]:
            self.assertIn(expected, status_conditions(dict(property_requirements=[[raw]]))[0])
        self.assertIn('未解析', status_conditions(dict(property_requirements=[['福缘|NaN|9999']]))[0])
        row = self.catalog['普通']
        row['property_requirements'] = [['福缘|10|9999']]
        row['readonly'] = readonly_reason(row)
        self.assertIn('属性达标', row['readonly'])
        before = copy.deepcopy(self.hero)
        with self.assertRaises(ValueError): set_status(self.hero, self.catalog, '普通', True, 100)
        self.assertEqual(before, self.hero)
        result = next(x for x in list_statuses(self.hero, self.catalog)['rows'] if x['key']=='普通')
        self.assertIn('福缘 ≥ 10', result['conditions'][0])
        self.assertIn('SelfPropBufflData', result['condition_source'])

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
            archive.return_value.__enter__.return_value.infolist.return_value = [SimpleNamespace(filename=f'Game/xls/1/{i}.xlsx') for i in range(3)] + [SimpleNamespace(filename='Game/json/1/SelfPropBufflData.txt'), SimpleNamespace(filename='Game/json/1/AchievementData.txt')]
            def read(info):
                if 'SelfPropBufflData' in info.filename: return json.dumps({'SelfPropBufflData':[dict(getBuff='第二状态', propRequire=['福缘|10|9999'])]}).encode()
                if 'AchievementData' in info.filename: return json.dumps({'AchievementData':[dict(uid=5, traitID=3, emType='PropertyValue', TargetParams=['0','福缘','15'])]}).encode()
                return b'workbook'
            archive.return_value.__enter__.return_value.read.side_effect = read
            catalog = load_status_catalog(Path('synthetic-game'))
        self.assertEqual(set(catalog), {'第一状态', '第二状态'})
        self.assertEqual(catalog['第一状态']['source'], '创建角色可选')
        self.assertEqual(catalog['第一状态']['creation'], ['创建天赋'])
        self.assertEqual(catalog['第二状态']['order'], 1)
        self.assertEqual(catalog['第二状态']['property_requirements'], [['福缘|10|9999']])
        self.assertIn('属性达标', catalog['第二状态']['readonly'])
        self.assertIn('福缘 ≥ 15', catalog['第一状态']['unlock_conditions'][0])
        self.assertIn('开局天赋解锁', catalog['第一状态']['unlock_conditions'][0])
        self.assertFalse(catalog['第一状态']['readonly'])

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
