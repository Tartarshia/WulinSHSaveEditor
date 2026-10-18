"""Reviewed explanations, guarded by exact installed configuration fingerprints.

Only handwritten explanations and hashes are shipped, never game assets. A game
update must not silently reuse a review for different predicates/effects/actions.
Success AND failure actions participate in the fingerprint. These describe an
already-held status, not a way to bypass its story or acquisition requirements.
"""
import hashlib
import json

BUFF_DEFINITIONS_HASH = 'b66f83cf466ddf9edef95cc2ad4a56bb61907dbd1c229489aa0e71a8917f3a9f'


def buff_definitions_fingerprint(env):
    """Protect descriptions of linked effects, tags and immunity as well."""
    for obj in env.objects:
        if obj.type.name == 'MonoBehaviour' and obj.peek_name() == 'BuffData':
            raw = obj.get_raw_data()
            if len(raw) > 16_000_000: return None
            return hashlib.sha256(raw).hexdigest()
    return None


FINGERPRINTS = {
    37: '378160cf417e86a016965393e2f1dc447d5696496c620ddbab185348c342b928',
    1105622: '78e3f2208fe25bbae4d65f96376704f3f498617d0c60aa3eee648ec8e7737763',
    8802: '6535d75ba9e718b516492f73f78327547a11b52ca29ebfb32da861e1e727d265',
    8806: 'bdf55483b99cbb183893be1bc0d70bd5a417bb95a2ac5e2e66f7a4da0fb44859',
    8808: '49ce813f663615c97917ecc749015e4a97bd40198e2c0b955720055dd2d55c78',
    8810: '9a6cdb0acb38b2e9a2e415917ca010bbb64c73a9b475720b9100d9a7e0e0bf67',
    1405: 'ccd0317e4369ed1c055aa9bf6aa7df9219d91e7d55e7ea2975178fffac993a72',
    23527: '062dab26675ac826238b36803161f26c2c6e12d0f7aff913459dd9f0e7d7a16e',
    33527: 'c9f5fed141d5da9c03f56344d4ad7b06983663301168d5ec9a88a6eb43598655',
    3660: 'd4c5e8fbbb56c84e8602abad411da5ef1524edb6345aac019fcd7dd8a23f7694',
    3676: 'e6102ca86797476041c2160bf5e952cce24f7d74d12db8a4ac1201d8da7885b2',
    3844: '734d8426c2e9f9f457d9627fe76dac6e30575c9191710d2ac2d66b8e15882f23',
    3956: '940be0bea218ddd0f3fdf18f921a1d9a83cee016f0dbefb7c303d52eecae47fd',
    3973: 'd52584d904d196ba789f3fa96295a17fb1d1443b105c15d39dbbd7d29968c934',
    3012: '85914003f288eddbcc9e67de2628a2837d44213a4c07c85fc4f82843e0709026',
    31025: 'be27466a019471415629c650166c3dc94efd21799a6daf72c08d58826baff0b9',
    31044: '9515cd046ad44642161c6e86b255213510c1c7f3b5223d2167f9b84e4f5c3461',
    31050: '16b4beb876c9b52b1f3726119a2af703b75b5216cf69764de09f24687918d9c7',
    31056: '09c4e7fd146c90ec0da9109fbd1b4ad1035e16e82b3cc30d0d3b8d59f9da0ea2',
    1120529: '93adbf6d83d4e0cb2b5d6b1214ab621fe1557d157a4b35f40d327de52669355c',
    6024: '127769a7c4588cd1c0f0efbbcb1285b48f3cc84a1ac327db4125e227057cd406',
    6031: '72b8bace7739fe27342c8d230d16bb747e3a028e1b9f0651a8117ac5096a2d43',
    6032: '6f9bbb3e354ae05b4361fefdddcb8b5c2f9ba74d7c81a5c326564dce667775f1',
    6033: '750affa8591665cce46fcb41b0825fd83101fc361ade40e14c83298eacdad1e9',
    6034: '59b183464ebd7d276eb47a1548666739c6e46eaccd2a02736e1623e7f5c7774c',
    6035: 'c0f7c71cf1fab5b1a25ca20569d96f89fe29b3431d4fe0e6f623da821f6acbb5',
    6036: 'af3505c0de2f0beeb620edec4f9effece9174b8522661d05084d615ae61963ec',
    6071: '1860656c85e9465f78ed342454705d40580dce5ca6b7337a2ef93eb4d20c7ceb',
    6072: 'fe73da36bc816f5aad41ca2e2cd301446de001fef22b953223a527ea4cb40413',
    6073: 'f584f34b2e4be0ca49b1009ac98d32f9c3070e3aa65bdf66be529c4958be5401',
    6088: 'de23b082488ef1cd2442b44fab623c5a24fe833eeb0c196d58e8017155de276e',
    6625: '47930362a251ad78e0e8211fe66810dc8464bc5f5bad5f089cbc6eb39b16a01a',
    6626: '4cf895db362ff5bf3fe7f2b0a2781bef97037c7ec845846d46aea5c6888dfe9c',
    6627: 'f4a00129154818bc552dd769c1d503084ed26165c9c3f81ad226cd4bbdcf7b3d',
    6628: '3664406a96b8bd7ff854dd10959ea83f1813fd1be5fc5be2ac583081df4fcda1',
    6101: 'b90bb341af4b745bab434ff9aad6bacd0f8ff133de8ca8695ec70d7a544b5e3b',
    6102: 'f34216867651c165309323d5988ffba612e47be56652bc321bf66d6e1ea536f8',
    6103: '14cdb88f75f20a83d2d267de10779121a92ae2dce29c070daea1f37e2366601a',
    6104: 'ec8f894c0d4a4cd62ca7e488d62f9aacb750784d58a18c3bdbed6b4d99473d5f',
    6105: '7bc84589da4e14ffe9bff4fc59dc5367fe18f11cd2f51e54b38603f807212b96',
    6106: '79bb1eafef6e888ad3aedf52cef1dec2f001d3aff83175ff253fbce08d5cc344',
    6107: '7392ee80d9223c5f382cc61e3688a1a4fbbd5b4b908081a051c9e2580b89b124',
    6108: '01ec528e23f8011e341a2e06dda04a93ecbbeadb3905097d0cfaa89828831389',
    6109: '5051939b04dab999a35749e8ca3b1544923ca02423f7459ff93415c34bb43b5b',
    6110: '5a967beee1a4ecb3ec7a3701dc0df7e168ded6ab8f678fceea7da734a81a1dc6',
    7121: '976f0c20322d4c1343fbc692793b69d54f2436194c66fce6a14ae16e0a2b4361',
    9269: '65fa5a4ed8e874f794c27ba0f9567fca53087ef258cc8371ee03d212ff4bff8c',
    9277: '291a784fdf7e3157f15a494f71ba05543bd7587b9aad14c94afc9f19d8191dab',
    9284: '87f3acb52cc03c5f8211ba1b9b1be5ee637997cb81fe5886abc540fd224c4973',
    9308: '02102df1de87f5fc16602253dbfa3488259a43e72881ca45d0189717577c044e',
    9804: '629f2a6487967da31345e73c5b55d14e62a69141b773b60fa663b92765972edb',
    130131: 'c701260911b969ca546b5ba74266d01eff7a7bc91487fba453dd52159c5af795',
    130392: 'd5a4ad399b48addbf48da1d8f838fde4e3420cacc769432088b074f8a9d4d498',
    130642: 'f9104f78daa9c54a6952d60203ef469c3f855b6a964a84789604d80454e94c2d',
    130762: 'a677810b0113ba62991481b723476039299bf4df659d5498bf947b454417032a',
    40251: '4972eea7702cfb524aa36afc5e9140b9d7346e65a1afd2a5739b83503639ddec',
    40252: '7fe9ac08c7840158a4bf2b693cf938f6792fbf046b0951f5e021577ba8b1984a',
    40253: '78f245bf1f101e80598f129ad0a0aec977f619d1f8de112ecc4b5a9abdd664a7',
    40254: '4cf00246714ae77180af308ce99b537ecc8f8baaaedd76697f8b85e412151668',
    40255: 'ef2c13d4cbb57ff9da36163f4ab8b051c63f74614f9550c2390389afd91f962d',
    40258: 'b059319bc6c094801149f4b522ee637bb8225432910f448126e8f1ef15723b5d',
    40259: 'da3023ba7125de81789ffae9d8ff68f76abb3ba5a88a1191da539adbdbea763d',
    40260: '6096e65a93ceeb532aa8f435eef6b61e48b440f5cdb32a9c91a1c956d11b6f1c',
    40261: 'c5fbe379e1bb01b3a23da8490d87aa1bc5a5a94e0f44e15e7c98abccc72ba254',
    40411: '1d0ae2c596ec0268259517a0650e22d97b80c0fe2fbf20fe787aae5eef1289e4',
    40412: '6fbbbbc6ef9960ae448440f684f080265858932b57061ed503f01301ba2f181e',
    40414: '159175054e569535490f034474128904013935bbfffbcf78e44f79c5637c86ed',
    40415: '66766499d906b7f7f3839176fb3935d77480561328c810d0f8b5eb5479ccd90b',
    207111: '85869203c42a10a0345cdea707f7bdfe7d16dc7d6af6adc9102d59d6c709cd1e',
    207112: 'ec2a99df578fff357531356b66c71823bb46de6f64260ca6693419936ef67ebd',
}

NOTES = {
    37: '队伍休息联动：队伍至少有 1 名队友，进行带有完整休息／高级床铺标签的休息交互时，主角义气增加 2 点。这是内部休息处理，不是采集能力加成。',
    1105622: '装备触发：攻击时按该件夸父装备附加的概率判定，成功则使目标临时护甲失效；免疫卸甲的目标不受此附属效果影响。实际概率取装备数值，并非一律采用配置默认的 25%。',
    8802: '情缘联动：华青青同阵营且存活、距主角不超过 2 格时，主角受击后使攻击者增加 20 点流血。此条只说明已有情缘状态的战斗效果。',
    8806: '情缘联动：主角仅有 1 名结缘配偶，且绛紫烟同阵营存活时，主角每次受击后使绛紫烟增加 15 点战意。',
    8808: '情缘联动：哑琴同阵营且存活、距主角至少 1 格，双方乐器能力相差不超过 24 点时，主角攻击获得增伤。能力相同时增伤 25%，每相差 1 点，增伤少 1 个百分点。',
    8810: '情缘联动：曼陀罗同阵营且存活、距主角 1～2 格时，主角格挡提高 15 个百分点、闪避提高 10 个百分点、集气速度提高 5%。条件不再满足或战斗结束时，撤销这些加成。',
    1405: '受击后结算：自身战意减少 75 点，攻击者战意增加 25 点。',
    23527: '获得此光环时计算：主角每有 1 级名声，集气速度提高 1.5%。',
    33527: '获得此光环时计算：主角每有 1 级名声，集气速度降低 1.5%。',
    3660: '攻击时生效：对当前受击目标临时施加格挡降低 5 个百分点的效果；自身暴击加成为常驻效果。',
    3676: '受击时生效：本次所受伤害乘以 50%；异常状态抗性由此状态的常驻效果提供。',
    3844: '监测建立条件：战斗入场时，凌梦蝶与自己同阵营且存活。后续在她重伤退场时，触发攻击提高 50%、防御降低至零、集气速度提高 25% 的增益。',
    3956: '获得光环时按名声差计算：霍诗楼的名声每高于自身 1 级，自身集气速度降低 5%；名声差反向时，修正方向也反向。',
    3973: '每次行动结束后，下一次行动的保底集气在 80～150 区间随机取值；战斗结束时清除这项临时数值。',
    3012: '资源不完整：状态表明确记载生命恢复效果提高 20%，但关联脚本缺失，无法核实光环的施加和移除规则。保持只读。',
    31025: '攻击时生效：向当前受击目标施加护甲失效效果，从而忽略其护甲属性及效果；免疫卸甲的目标除外。',
    31044: '攻击时生效：向当前受击目标施加护甲失效效果，从而忽略其护甲属性及效果；免疫卸甲的目标除外。',
    31050: '资源不完整：这是宠物同名状态，不是武道天赋。当前表没有说明或直接效果，且引用的宠物触发脚本缺失，无法确认本版本有可触发效果。保持只读，不套用武道的效果。',
    31056: '资源不完整：当前表没有说明或直接效果，且引用的宠物触发脚本缺失，无法确认本版本有可触发效果。保持只读。',
    1120529: '按双方名声差生效：攻击名声比自己高的目标时，对方每高 1 级名声，自己的伤害减少 3%；受到名声更高者攻击时，对方每高 1 级名声，自己受到的伤害增加 3%。',
    6024: '获得状态时立即计算：按角色不受百分比加成影响的原始内力上限，施加等量的负向内力上限修正；不是单纯清空当前剩余内力。',
    6036: '持有状态时生效：攻击造成的伤害降低 50%；防御和集气速度的减益为常驻效果。',
    6071: '队伍联动：入队时向队伍提供打造武器能力提高 1 级的附属效果，离队时执行对应的退出处理。',
    6072: '队伍联动：入队时向队伍提供暗取成功率提高 25% 的附属效果，离队时执行对应的退出处理。',
    6073: '持有时无法移动；受击判定期间临时压低闪避，受击结算后撤销这项闪避修正。撤销临时修正不等于解除铁链。',
    6088: '持有状态进行攻击时生效：最终伤害只按正常值的 35% 结算。',
    7121: '开箱时结算：根据已有摸金记录分档发放铜钱，并更新记录；后续开箱的钱数递增。不是达到某项属性门槛才获得的状态。',
    9269: '受击后按双方轻功差调整移动格数：攻击者轻功每高于自身 50 点，移动减少 1 格；反向差值产生反向修正，按完整的 50 点差值取整。',
    9277: '获得状态时按当前内力差计算：攻击者内力每高于自身 100 点，集气速度降低 1%，最多降低 30%；差值反向时，修正方向反向。',
    9284: '获得状态时按队伍心情计算：以 50 为基准，每高 1 点，集气速度提高 0.2%；每低 1 点则降低 0.2%。',
    9308: '获得状态时按资质差计算：攻击者臂力每高于自身敏捷 1 点，格挡和闪避各降低 2 个百分点；差值反向时，修正方向反向。',
    9804: '获得状态时按乐器能力差计算：攻击者每高于自身 10 点，集气速度降低 1%，最多降低 15%；按完整的 10 点差值取整，反向差值产生反向修正。',
    130131: '受击后结算免伤次数：计数为 2～99 时扣除 1 次，否则施加清理效果，不额外增加免伤次数。',
    130392: '获得状态时立即结算：自身中毒、流血、内伤、致盲、封穴各减少 50%；集气速度增益由常驻效果提供。',
    130642: '本次攻击前生效：临时提高暴击和连击，游戏效果说明为本次攻击必定暴击、必定连击。',
    130762: '光环变化时重新计算：施放者每有 1 点悟性，光环提供攻击提高 1%、防御提高 1%、集气速度增加 1 点。',
    40411: '攻击期间生效：攻击前临时压低连击，攻击后撤销该项修正，从而限制本次攻击触发连击。',
    40412: '整场战斗生效：入场时压低反击，战斗结束时撤销这项修正。',
    40414: '攻击期间生效：攻击前临时压低暴击，攻击后撤销该项修正，从而限制本次攻击触发暴击。',
    40415: '受击期间生效：受击判定前临时压低闪避，受击后撤销这项修正。',
    207111: '获得状态时立即恢复 50 点内力；移动距离增加 1 格来自此状态的常驻效果。',
    207112: '持有状态攻击时生效：最终伤害提高 5%；暴击提高 5 个百分点来自常驻效果。',
}
for uid, increase in zip(range(6031, 6036), (100, 80, 60, 40, 20)):
    NOTES[uid] = f'持有状态进行攻击时生效：最终伤害提高 {increase}%；生命、防御和集气速度的加成为常驻效果，具体数值见游戏说明。'
for uid, current, next_state in ((6625, '微醺', '半酣'), (6626, '半酣', '酣畅'),
                                 (6627, '酣畅', '酩酊'), (6628, '酩酊', '醉酒')):
    NOTES[uid] = f'醉酒阶段升级：再次附加状态时，若「{current}」计数达到 2～9999，就向自身附加「{next_state}」。不是要求饮用某一种固定酒。'
for uid, reduction in zip(range(6101, 6111), (90, 80, 70, 60, 50, 40, 30, 20, 10, 50)):
    NOTES[uid] = f'战斗入场时计算：按角色不受百分比加成影响的原始攻击、防御，各施加 {reduction}% 的负向修正；集气速度减益为常驻效果。'
for uid, prop, amount in ((40251, '生命', 25), (40252, '攻击', 25), (40253, '防御', 25),
                          (40254, '轻功', 25), (40255, '集气速度', 25), (40258, '命中', 3),
                          (40259, '闪避', 3), (40260, '暴击', 3), (40261, '格挡', 3)):
    NOTES[uid] = f'通天塔附属效果：获得时读取角色的通天塔{prop}加成数值，每增加 1，提供 {amount}% 的{prop}加成。由上级通天塔状态施加，不是独立属性门槛。'

RESOURCE_GAPS = {3012, 31050, 31056}


def review_fingerprint(row, runtime):
    config = dict(key=row['key'], effects=row.get('continousEffect', []),
                  scripts={key: runtime.get(key) for key in row.get('dynamicModifier', [])})
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False,
                                     default=str, separators=(',', ':')).encode('utf-8')).hexdigest()


def reviewed_resolution(row, runtime, definitions_hash=None, catalog=None):
    """A different ID, effect, predicate, action or failure action invalidates it."""
    uid = row.get('id')
    if definitions_hash != BUFF_DEFINITIONS_HASH: return None
    if uid not in FINGERPRINTS or review_fingerprint(row, runtime) != FINGERPRINTS[uid]: return None
    if uid == 3844:
        child = (catalog or {}).get('伙伴特征生无可恋_附属1')
        if not child or review_fingerprint(child, runtime) != '1c77fce401828c9916242dde7f0ac27e17c99205bc4c49104df49d27315ab6ad':
            return None
    # These reviewed rows have no on-add/on-remove direct effects. Do not reuse
    # the prose if a later export introduces such side effects.
    if row.get('instantEffect') or row.get('endRemoveEffect'): return None
    if uid in {31050, 31056} and row.get('description', '').strip() not in {'', '游戏资源中暂无文字说明。'}:
        return None
    return dict(state='resource_missing' if uid in RESOURCE_GAPS else 'reviewed', notes=[NOTES[uid]])
