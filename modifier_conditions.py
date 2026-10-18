"""Read-only, bounded inspection of Odin binary modifier condition graphs.

Independent format reader; no game code, Lua or expressions are executed.
Format reference (not vendored code): TeamSirenix/odin-serializer,
OdinSerializer/Core/DataReaderWriters/Binary/{BinaryEntryType,BinaryDataReader}.cs.
Unknown entries/conditions fail closed and retain an explicit unresolved marker.
"""
from decimal import Decimal
import math
import re
import struct


class OdinReader:
    def __init__(self, data, *, table=False):
        if len(data) > (16_000_000 if table else 2_000_000): raise ValueError("modifier too large")
        self.entry_limit = 1_000_000 if table else 20000
        self.array_limit = 50000 if table else 10000
        self.data, self.pos, self.types, self.count = bytes(data), 0, {}, 0

    def take(self, count):
        if count < 0 or self.pos + count > len(self.data): raise ValueError("truncated modifier")
        value = self.data[self.pos:self.pos + count]
        self.pos += count
        return value

    def number(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def string(self):
        width, length = self.number('B'), self.number('i')
        if width not in (0, 1) or not 0 <= length <= 32768: raise ValueError("invalid string")
        return self.take(length * (width + 1)).decode('latin-1' if width == 0 else 'utf-16-le')

    def type_name(self):
        code = self.number('B')
        if code == 0x2e: return ''
        if code == 0x2f:
            identity = self.number('i')
            if identity in self.types: raise ValueError('duplicate type')
            self.types[identity] = self.string()
            return self.types[identity]
        if code == 0x30:
            identity = self.number('i')
            if identity not in self.types: raise ValueError('unknown type')
            return self.types[identity]
        raise ValueError('unsupported type tag')

    def entry(self, depth=0):
        self.count += 1
        if depth > 64 or self.count > self.entry_limit: raise ValueError('modifier nesting limit')
        code = self.number('B')
        if code in (5, 7, 0x31): return code, None, None
        named = code in (1, 3) or 9 <= code <= 0x2d and code % 2 == 1 or code == 0x32
        name = self.string() if named else None
        if code in (1, 2, 3, 4):
            typename = self.type_name()
            identity = self.number('i') if code in (1, 2) else None
            value = dict(type=typename, fields={}, items=[], identity=identity)
            while True:
                child_code, child_name, child = self.entry(depth + 1)
                if child_code == 5: break
                if child_code in (7, 0x31): raise ValueError('wrong node end')
                if child_name is None: value['items'].append(child)
                else:
                    if child_name in value['fields']: raise ValueError('duplicate field')
                    value['fields'][child_name] = child
            return code, name, value
        if code == 6:
            length = self.number('q')
            if not 0 <= length <= self.array_limit: raise ValueError('array limit')
            values = []
            for _ in range(length):
                child_code, child_name, child = self.entry(depth + 1)
                if child_code in (5, 7, 0x31) or child_name is not None: raise ValueError('invalid array')
                values.append(child)
            if self.entry(depth + 1)[0] != 7: raise ValueError('array end missing')
            return code, None, values
        formats = {0x0f:'b',0x11:'B',0x13:'h',0x15:'H',0x17:'i',0x19:'I',
                   0x1b:'q',0x1d:'Q',0x1f:'f',0x21:'d',0x25:'H',0x2b:'B'}
        primitive = code if named else code - 1
        if primitive in formats:
            value = self.number(formats[primitive])
            if isinstance(value, float) and not math.isfinite(value): raise ValueError('nonfinite number')
            if primitive == 0x2b:
                if value not in (0, 1): raise ValueError('invalid boolean')
                value = bool(value)
            return code, name, value
        if code in (0x23, 0x24):
            flags, high, low, mid = struct.unpack('<IIII', self.take(16))
            scale = (flags >> 16) & 255
            if flags & 0x7f00ffff or scale > 28: raise ValueError('invalid decimal')
            integer = low + (mid << 32) + (high << 64)
            value = Decimal((flags >> 31, tuple(int(digit) for digit in str(integer)), -scale))
            return code, name, value
        if code in (0x27, 0x28): return code, name, self.string()
        if code in (0x2d, 0x2e): return code, name, None
        # References remain explicit; never instantiate or follow external objects.
        if code in (9, 10, 11, 12): return code, name, {'reference':self.number('i')}
        raise ValueError(f'unsupported entry {code}')

    def read(self):
        result = {}
        while self.pos < len(self.data):
            code, name, value = self.entry()
            if code == 0x31:
                if self.pos != len(self.data): raise ValueError('trailing data')
                break
            if name is None or name in result: raise ValueError('invalid root entry')
            result[name] = value
        return result


def list_values(node):
    if isinstance(node, list): return node
    if isinstance(node, dict) and 'items' in node:
        arrays = [x for x in node['items'] if isinstance(x, list)]
        if len(arrays) == 1: return arrays[0]
    raise ValueError('unsupported list structure')


def read_runtime_tables(env, wanted):
    """Read primary rows of installed tables; ignore redundant lookup indexes.

    This deliberately returns typed fields, not executable game objects. Failures
    are isolated per table and never replaced with guessed data.
    """
    result = {}
    for obj in env.objects:
        if obj.type.name != 'MonoBehaviour': continue
        name = obj.peek_name()
        if name not in wanted: continue
        try:
            tree = obj.read_typetree()
            serial = tree.get('serializationData', {})
            if serial.get('SerializedFormat') != 0: continue
            reader = OdinReader(serial.get('SerializedBytes', []), table=True)
            _, root_name, root = reader.entry()
            if root_name != name: continue
            rows = [fields(row) for row in list_values(root)]
            if not all(isinstance(row.get('UName'), str) for row in rows): continue
            result[name] = rows
        except (ValueError, KeyError, TypeError, UnicodeError, struct.error, OverflowError):
            continue
    return result


def read_runtime_modifiers(env, wanted):
    """Resolve full asset paths, not ambiguous names or stale ModEditor examples."""
    result = {}
    prefix = 'Assets/__WuLin/Scripts/ModShare/Runtime/GDData/DynamicModifier/'
    for obj in env.objects:
        if obj.type.name != 'AssetBundle': continue
        for path, info in obj.read_typetree().get('m_Container', []):
            if not path.startswith(prefix) or not path.endswith('.asset'): continue
            key = path[len(prefix):-6]
            if key not in wanted: continue
            unavailable = dict(path=path, conditions=[], stages=[], actions=[], failed_actions=[],
                               read_error='resource_unreadable')
            pointer = info.get('asset', {})
            if pointer.get('m_FileID') != 0:
                result[key] = unavailable
                continue
            reader = obj.assets_file.objects.get(pointer.get('m_PathID'))
            if reader is None:
                result[key] = unavailable
                continue
            try:
                tree = reader.read_typetree()
                serial = tree.get('serializationData', {})
                if serial.get('SerializedFormat') != 0:
                    result[key] = unavailable
                    continue
                decoded = OdinReader(serial.get('SerializedBytes', [])).read()
                result[key] = dict(path=path, conditions=list_values(decoded['conditions']),
                                   stages=tree.get('activeStages', []),
                                   actions=list_values(decoded['actions']) if 'actions' in decoded else [],
                                   failed_actions=list_values(decoded['failedActions']) if 'failedActions' in decoded else [])
            except (ValueError, KeyError, TypeError, UnicodeError, struct.error, OverflowError):
                result[key] = unavailable
    return result


# Enum values checked against the bundled ModShare.Runtime metadata; formula
# terms checked against the game's 动态修改器公式说明.txt. No expression evaluation.
STAGES = {1:'状态检查',2:'升级时',3:'名声升级时',4:'状态附加时',5:'主角品格变化时',
          6:'入队时',7:'离队时',8:'队伍成员变化时',10:'能力变化时',11:'状态移除时',
          20:'武功变化时',21:'主角属性变化时',22:'属性变化时',101:'开箱时',102:'采集时',
          103:'每日结算时',105:'每刻结算时',110:'与角色交互前',112:'与物件交互前',113:'与物件交互后',
          200:'进入战斗时',201:'攻击前',202:'攻击方伤害计算前',203:'受击方伤害计算前',
          205:'攻击方伤害计算后',206:'受击方伤害计算后',207:'攻击后',208:'行动结束时',
          209:'战斗结束时',210:'释放敌意时',211:'伤害检查时',212:'行动开始时',213:'光环改变时',
          230:'内功入场时',231:'内功攻击前',232:'内功攻击后',233:'内功受击前',
          234:'内功受击后',235:'内功行动后',236:'切换内功时',300:'掉落结算时'}
DAMAGE_CHECKS = {0:'招式',1:'加力',2:'护体',3:'命中',4:'秒杀',5:'暴击',6:'格挡',7:'闪避',
                 8:'免伤',9:'击杀',10:'侧击',11:'侧击位',12:'背击',13:'背击位',14:'连击',15:'反击'}
TARGETS = {0:'持有者',1:'攻击者',2:'受击者',4:'队友',5:'召唤主人',6:'支援者'}


def fields(node):
    if not isinstance(node, dict) or 'fields' not in node: raise ValueError('unresolved object reference')
    return node['fields']


def range_text(label, low, high, percent=False):
    if not isinstance(low, (int, float, Decimal)) or not isinstance(high, (int, float, Decimal)):
        raise ValueError('invalid condition range')
    if not math.isfinite(low) or not math.isfinite(high) or low > high: raise ValueError('invalid condition range')
    if percent:
        low, high = low * 100, high * 100
    unit = '%' if percent else ''
    # Keep real bounds, including sentinel-like values, rather than guessing
    # that a very large bound means infinity.
    if low == high: return f'{label} = {low:g}{unit}'
    return f'{low:g}{unit} ≤ {label} ≤ {high:g}{unit}'


def expression_label(expression, names):
    """Translate identifiers only; never eval or simplify unknown arithmetic."""
    if not isinstance(expression, str) or len(expression) > 2048: raise ValueError('invalid expression')
    def token(match):
        name = match[1]
        if name.startswith('战场_和持有者同队_'):
            identity = name.rsplit('_', 1)[-1]
            return names.get(identity, '角色 ' + identity) + '与持有者同场存活'
        if name.startswith('战场_角色距持有者距离_'):
            identity = name.rsplit('_', 1)[-1]
            return '与' + names.get(identity, '角色 ' + identity) + '的战场距离'
        if name.startswith('队伍_有队友_'):
            identity = name.rsplit('_', 1)[-1]
            return names.get(identity, '角色 ' + identity) + '在队'
        replacements = {'Hp':'当前生命','Ep':'当前内力','NegInjure':'内伤','NegBleed':'流血',
                        'NegPoison':'中毒','NegBlind':'致盲','NegSeal':'封穴','AccuAtk':'战意','AccuDef':'怒气'}
        return '·'.join(replacements.get(part, part) for part in name.split('_'))
    return re.sub(r'【([^】]+)】', token, expression.removesuffix('*1'))


def explain_condition(node, names):
    values = fields(node)
    kind = node.get('type', '').split(',')[0].split('.')[-1]
    if kind == 'SimpleEvalValueMatchedCondition':
        expression = fields(values['eval'])['evalStr']
        label = expression_label(expression, names)
        percent = expression in {f'【{actor}_Hp】/【{actor}_生命】' for actor in ('持有者','主角','战斗攻击者','战斗受击者')}
        if percent: label = expression.split('_')[0].lstrip('【') + '生命比例'
        low, high = values['minValue'], values['maxValue']
        if low == high:
            match = re.fullmatch(r'【([^】]+)_(性别|内力类型|武器类型)】(?:\*1)?', expression)
            if match:
                mapping = {'性别':{0:'女性',1:'男性',2:'不明/自宫',3:'动物'},
                           '内力类型':{0:'阴性',1:'阳性',2:'调和',3:'先天/无主内功'},
                           '武器类型':{0:'空手',1:'拳套',2:'剑',3:'刀',4:'杖',5:'琵琶',6:'箫',7:'琴',8:'笔',9:'匕首',10:'扇',11:'枪'}}[match[2]]
                if low in mapping: return label + ' = ' + mapping[low]
        return range_text(label, low, high, percent)
    if kind == 'CheckDamageCondition':
        notes = []
        for item in list_values(values['checkDict']):
            pair = fields(item)
            key, happened = pair['$k'], pair['$v']
            if key not in DAMAGE_CHECKS or happened not in (0, 1): raise ValueError('unknown damage check')
            notes.append(('发生' if happened else '未发生') + DAMAGE_CHECKS[key])
        if not notes: return '此分支未限制伤害判定项'
        return '本次伤害判定：' + '，且'.join(notes)
    if kind == 'RandomActiveModifier':
        if values.get('useCharacterPropAsRate'):
            return '触发概率取持有者属性：' + str(values.get('keyAsRate') or '未注明属性')
        value = values['rate']
        if not isinstance(value, (int, float, Decimal)) or not 0 <= value <= 100: raise ValueError('invalid probability')
        return f'随机触发概率 {value:g}%'
    if kind == 'CurrentCharaterIsBattleActorInAction': return '当前行动者为状态持有者'
    if kind == 'CurrentActionUsingSpecifiedKungfu':
        kinds = {0:'任意',1:'外功',2:'绝招',4:'基础'}
        if values.get('kungfuType') not in kinds: raise ValueError('unknown kungfu kind')
        result = '当前动作类别：' + kinds[values['kungfuType']]
        included = list_values(values['idOrName'])
        excluded = list_values(values['excludeIdOrName']) if values.get('excludeIdOrName') else []
        if included: result += '；限 ' + '、'.join(str(x) for x in included)
        if excluded: result += '；排除 ' + '、'.join(str(x) for x in excluded)
        return result
    if kind == 'BattleActorCheckTempPropCondition':
        target = fields(values['target'])
        code = target['target']
        if code == 3: who = names.get(str(target['characterId']), '角色 ' + str(target['characterId']))
        elif code in TARGETS: who = TARGETS[code]
        else: raise ValueError('unknown target')
        return range_text(who + '·战斗临时记录·' + values['tempPropName'], values['minValue'], values['maxValue'])
    if kind == 'BattleActorCheckLabelCondition':
        groups = list_values(values['checkGroups'])
        # Multiple label groups have unverified AND/OR semantics: don't flatten.
        if len(groups) != 1: raise ValueError('unverified label group logic')
        labels = list_values(groups[0])
        if len(labels) != 1 or not isinstance(labels[0], str): raise ValueError('unverified label combination')
        return '事件标签：' + labels[0]
    raise ValueError('unsupported condition ' + kind)


def explain_modifiers(keys, runtime, names=None):
    names = names or {}
    branches = []
    for key in keys:
        config = runtime.get(key)
        if config is None:
            branches.append(dict(script=key, timing=[], conditions=['当前资源中未能解析此分支'], complete=False, path=''))
            continue
        if config.get('read_error'):
            branches.append(dict(script=key, timing=[], conditions=['脚本资源存在，但当前格式未能安全读取'], complete=False, path=config['path']))
            continue
        notes, complete = [], True
        for condition in config['conditions']:
            try: notes.append(explain_condition(condition, names))
            except (ValueError, KeyError, TypeError):
                kind = condition.get('type', '未知对象') if isinstance(condition, dict) else '未知对象'
                notes.append('尚未翻译的条件：' + kind.split(',')[0])
                complete = False
        timing = [STAGES.get(stage, f'未映射回调 {stage}') for stage in config['stages']]
        if not timing or any(stage not in STAGES for stage in config['stages']): complete = False
        if not notes: notes = ['此脚本分支没有额外条件项（不代表状态可自动获得）']
        branches.append(dict(script=key, timing=timing, conditions=notes, complete=complete, path=config['path']))
    return branches


def compact_condition(text):
    """Card projection only. Complete finite bounds remain in hover details."""
    match = re.fullmatch(r'(-?\d+(?:\.\d+)?)(%)? ≤ (.+) ≤ (-?\d+(?:\.\d+)?)(%)?', text)
    if not match: return text
    low, low_unit, label, high, high_unit = match.groups()
    # These cutoffs are a readability heuristic, NOT an assertion that the
    # omitted finite bound is infinite. Cards explicitly label this a summary.
    if float(low) <= -999: return f'{label} ≤ {high}{high_unit or ""}'
    if float(high) >= 9999: return f'{label} ≥ {low}{low_unit or ""}'
    return text
