"""Human-readable provenance from installed game tables, never inferred names."""
from modifier_conditions import fields, list_values, read_runtime_tables


def references(value):
    if value is None: return []
    if isinstance(value, str): return [x.strip() for x in value.split(',') if x.strip()]
    if isinstance(value, dict) and 'refNames' in value.get('fields', {}):
        return references(value['fields']['refNames'])
    return list_values(value)


def source_notes(tables):
    result = {}
    def add(value, text):
        for key in references(value):
            if not isinstance(key, str): continue
            if text not in result.setdefault(key, []): result[key].append(text)
    for row in tables.get('ItemData', []):
        name = row['UName']
        add(row.get('EquipBuff'), f'装备来源：装备「{name}」时附带此状态。')
        add(row.get('EquipBuffToLeader'), f'装备联动：装备「{name}」时向队伍领队提供此状态。')
        # ConsumeEffect does not specify the recipient. Never assume self-use:
        # poisons and thrown items can apply these effects to another character.
        add(row.get('ConsumeEffect'), f'物品来源：使用「{name}」会施加此状态，作用对象以物品用法为准。')
    for row in tables.get('KungfuData', []):
        name = row['UName']
        add(row.get('ActiveInternalBuffs'), f'内功来源：将「{name}」设为主内功时附带此状态。')
        add(row.get('LearntBuff'), f'武功来源：学习「{name}」时附带此状态。')
        add(row.get('CastBuffs'), f'招式来源：施展「{name}」会施加此状态，作用对象以招式效果为准。')
    for row in tables.get('CharacterPetExtendData', []):
        for item in references(row.get('AbilityBuffs')):
            item = fields(item)
            if item.get('isValid'):
                # The integer is not assumed to mean pet level or ability level.
                add(item.get('key'), f'宠物来源：「{row["UName"]}」的专属能力；具体解锁要求以游戏为准。')
    for row in tables.get('CustomDiffData', []):
        deprecated = '（该选项在当前表中标记为已停用）' if row.get('IsDeprecated') else ''
        add(row.get('NpcBuffs'), '难度来源：自定义难度向 NPC 附加的效果' + deprecated + '。')
    return result


def read_source_notes(env):
    tables = read_runtime_tables(env, {'ItemData', 'KungfuData', 'CharacterPetExtendData', 'CustomDiffData'})
    return source_notes(tables)


def modifier_source_notes(catalog, runtime):
    """Reverse only explicit, non-random success-branch buff assignments.

    Do not infer that this is the only source, or that its conditions are met.
    Failure branches and random/indirect buff names are intentionally excluded.
    """
    result = {}
    targets = {0:'原状态持有者', 1:'该次攻击的攻击者', 2:'该次攻击的受击者'}
    for parent in catalog.values():
        for script in parent.get('dynamicModifier', []):
            config = runtime.get(script, {})
            for action in config.get('actions', []):
                if not isinstance(action, dict): continue
                if action.get('type', '').split(',')[0] != 'WuLin.ApplyBuffToCharacterAction': continue
                try:
                    args = fields(action)
                    if args.get('useRandomBuff') is not False: continue
                    key = args.get('buffName')
                    target = fields(args['buffTarget'])
                    if not isinstance(key, str) or key not in catalog or key == parent['key']: continue
                    if target.get('target') not in targets: continue
                    text = f'联动来源：「{parent["name"]}」满足自身触发条件时，向{targets[target["target"]]}施加此状态。'
                    if text not in result.setdefault(key, []): result[key].append(text)
                except (ValueError, KeyError, TypeError):
                    continue
    return result
