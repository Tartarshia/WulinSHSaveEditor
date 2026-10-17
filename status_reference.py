"""Short, independently paraphrased community acquisition hints, not script rules.

Checked 2026-10-17. Match BOTH internal key and ID: NPC traits and sect variants
with the same localized name must not inherit the player's acquisition route.
No wiki text is downloaded by the application at runtime.
"""
import re

WIKI_TRAITS = "https://heros-adventure.wikidot.com/traits"
WIKI_ACHIEVEMENTS = "https://heros-adventure.wikidot.com/chengjiu"

# Only acquisition facts are summarized. These do not establish all runtime
# activation requirements, grant achievements, or make scripted states editable.
ACQUISITION_HINTS = {
    ("千王之王", 3523): ("赌场封盘累计 20 次。", WIKI_TRAITS),
    ("雨露均沾", 3534): ("与 15 位女性结缘。", WIKI_TRAITS),
    ("财运亨通", 3533): ("持有铜钱达到 1000 贯。", WIKI_ACHIEVEMENTS),
    ("知行合一", 3526): ("入儒圣馆，读完全部馆藏书。", WIKI_TRAITS),
    ("道法自然", 3531): ("入道玄宗，完成观星悟道事件。", WIKI_TRAITS),
    ("追命阎罗", 3530): ("老头门路线，接掌新九流门。", WIKI_TRAITS),
    ("替天行道", 3527): ("小村拜师时选择统一天下志向。", WIKI_TRAITS),
    ("博采众长", 3529): ("小村拜师时选择天下第一志向。", WIKI_TRAITS),
    ("儒者之风", 3451): ("通过儒圣馆的门派考验。", WIKI_TRAITS),
    ("菩提禅心", 3452): ("释法寺出家弟子通过门派考验。", WIKI_TRAITS),
    ("妙手空空", 3442): ("通过燕子窝的门派考验。", WIKI_TRAITS),
    ("贪生怕死", 3513): ("勇气降至 -100。", WIKI_TRAITS),
}

# Independently summarized from the local BuffInfo text. The fragment guard
# prevents applying numeric thresholds when a newer game's wording differs.
LOCAL_TRIGGER_HINTS = {
    ("山林猎手", 3316): ("动物类敌人", "作用对象：动物类敌人。"),
    ("雪上加霜", 3413): ("对目标下毒后", "战斗触发：对目标用毒后，每回合最多触发一次。"),
    ("妙手仁心", 3414): ("进行治疗后", "战斗触发：治疗后，每回合最多触发一次。"),
    ("大器晚成", 3424): ("50级", "效果分界：50 级前后经验收益不同；不是达到等级才获得。"),
    ("庄周梦蝶", 3425): ("4时辰", "触发条件：一次入睡满 4 时辰。"),
    ("妙手空空", 3442): ("攻击命中", "战斗触发：攻击命中目标。"),
    ("众志成城", 3445): ("关系达到100", "加成依据：与角色的关系达到 100，按符合人数累计。"),
    ("飞星连珠", 3446): ("使用暗器后", "战斗触发：使用暗器后，每回合最多触发一次。"),
    ("逆流而上", 3448): ("15点及以上", "战斗结算：敏捷不足 15 和至少 15 分别对应两档效果。"),
    ("儒者之风", 3451): ("每项品格", "加成依据：仁、义、礼、智、信各自的正负值。"),
    ("菩提禅心", 3452): ("女性队友", "加成依据：队内女性人数，以及仁德的正负值。"),
    ("摸金校尉", 3453): ("加锁的箱子", "触发条件：搜刮加锁的箱子。"),
    ("日进斗金", 3454): ("每一天", "触发时机：每日结算，金额随江湖天数变化。"),
    ("毒蛊寄生", 3455): ("攻击及受伤", "战斗触发：自身攻击或受到攻击。"),
    ("皮糙肉厚", 3456): ("每1点体质", "加成依据：体质；在受到攻击时结算。"),
    ("所向披靡", 3501): ("暴击后再次触发连击", "战斗触发：暴击提高连击，暴击后的连击必定暴击。"),
    ("天煞孤星", 3502): ("独自一人", "生效条件：独自行动、没有队友。"),
    ("财大气粗", 3503): ("每拥有1000文", "加成依据：持有铜钱，每 1000 文一档；额外伤害上限 250。"),
    ("影子护卫", 3506): ("生命值低于25%", "战斗触发：生命低于 25%，每场战斗限一次。"),
    ("万里独行", 3511): ("没有队友", "加成依据：队友人数；没有队友时最高。"),
    ("贪生怕死", 3513): ("生命低于20%", "战斗触发：野外战斗中生命低于 20% 时可直接逃离。"),
    ("劫后余生", 3514): ("战斗胜利后", "触发时机：战斗胜利后结算。"),
    ("天命弱鸡", 3518): ("每场战斗生效一次", "保命触发：受到致命一击，每场战斗限一次；其他常驻效果见说明。"),
    ("扮猪吃虎", 3519): ("初始等级50级", "作用时机：创建角色时设置初始等级，不是战斗触发。"),
    ("武林霸主", 3521): ("初始等级100级", "作用时机：创建角色时设置初始属性，不是战斗触发。"),
    ("千王之王", 3523): ("不可连续触发", "战斗触发：施展暗器后，不可连续触发再行动。"),
    ("转世佛子", 3524): ("仁德低于0", "加成依据：仁德的正负值；初始仁德只在创建时设置。"),
    ("知行合一", 3526): ("品格全部满足100", "生效分支：仁、义、礼、智、信全部达到 100 为正面效果，否则为负面效果。"),
    ("替天行道", 3527): ("首领角色", "战斗触发：入场结算群体效果，攻击首领时结算额外伤害。"),
    ("博采众长", 3529): ("第十重", "生效条件：内功或外功练到第十重后，按武功品质累计加成；外功增加基础攻击，内功增加基础防御。"),
    ("追命阎罗", 3530): ("连击触发暴击", "战斗触发：攻击暴击，以及连击中的暴击。"),
    ("道法自然", 3531): ("使用外功攻击", "战斗触发：使用外功攻击；集气增益常驻。"),
    ("气血充盈", 3532): ("体质影响", "加成依据：体质带来的生命值效果，没有额外事件触发。"),
    ("财运亨通", 3533): ("参与骰子除外", "结算时机：获得钱财（骰子除外）、攻击命中及战斗入场。"),
    ("雨露均沾", 3534): ("队内每名结缘女性", "生效条件：女性伙伴在队；资质共享对象须已结缘且在队。"),
    ("有仇必报", 3581): ("触发反击后", "战斗触发：受攻击时叠加反击，反击触发后清除临时加成。"),
}


def local_trigger_reference(row):
    try:
        key = row.get("uName", row.get("key"))
        uid = int(row.get("id", row.get("uid", 0)))
        hint = LOCAL_TRIGGER_HINTS.get((key, uid))
        # Only the known +10000 story variant can reuse a condition summary,
        # and its own game description must still pass the text guard below.
        # Never inherit creation rewards, wiki acquisition routes or editability.
        if not hint and isinstance(key, str) and key.startswith('剧情'):
            hint = LOCAL_TRIGGER_HINTS.get((key[2:], uid - 10000))
    except (ValueError, TypeError):
        return []
    if not hint or hint[0] not in row.get("description", ""): return []
    return [hint[1]]


def readable_runtime_summary(branches):
    """Small, strict human-language whitelist. Never expose raw graphs as prose."""
    if any(not branch.get('complete') for branch in branches): return []
    useful = [branch for branch in branches if branch.get('path') and
              branch.get('conditions') != ['此脚本分支没有额外条件项（不代表状态可自动获得）']]
    if len(useful) != 1 or not useful[0].get('complete'): return []
    branch = useful[0]
    notes = []
    for text in branch['conditions']:
        ratio = re.fullmatch(r'(-?[\d.]+)% ≤ 持有者生命比例 ≤ ([\d.]+)%', text)
        if ratio:
            low, high = map(float, ratio.groups())
            if low > 0: return []
            notes.append('自身气血耗尽时' if high == 0 else f'自身气血不高于 {high:g}%')
        elif text == '1 ≤ 队伍·持有者是队友*战场·敌人数量 ≤ 9999':
            notes.append('自身为队伍伙伴，且场上仍有敌人')
        elif text == '队伍·持有者是队友 = 1': notes.append('自身为队伍伙伴')
        elif text == '当前动作类别：外功': notes.append('使用外功时')
        elif text == '当前动作类别：任意；限 暗器': notes.append('使用暗器时')
        elif text == '当前动作类别：任意；限 治疗': notes.append('施展治疗时')
        elif text == '当前行动者为状态持有者': notes.append('轮到自身行动时')
        elif text == '持有者·战斗临时记录·外功出手次数 = 1': notes.append('本场战斗第一次使用外功')
        elif text == '持有者·战斗临时记录·出手次数 = 1': notes.append('本场战斗首次出手')
        elif text == '持有者·战斗临时记录·出手前移动距离 = 0': notes.append('本次行动尚未移动')
        elif re.fullmatch(r'随机触发概率 [\d.]+%', text):
            notes.append('有 ' + text.removeprefix('随机触发概率 ') + ' 的概率触发')
        elif text.startswith('本次伤害判定：'):
            event = text.removeprefix('本次伤害判定：')
            mapping = {'发生暴击':'攻击触发暴击','未发生暴击':'攻击未触发暴击',
                       '发生格挡':'攻击被格挡','发生闪避':'攻击被闪避',
                       '发生击杀':'击败敌人','发生连击':'攻击触发连击','发生反击':'触发反击'}
            if event not in mapping or any('受击方' in stage for stage in branch['timing']): return []
            notes.append(mapping[event])
        else: return []
    if not notes: return []
    return ['触发参考：' + '，并且'.join(dict.fromkeys(notes)) + '。']


def acquisition_reference(row):
    try:
        hint = ACQUISITION_HINTS.get((row.get("uName", row.get("key")), int(row.get("id", row.get("uid", 0)))))
    except (ValueError, TypeError):
        return [], []
    if not hint: return [], []
    text, url = hint
    return ["局内获得（Wiki 参考）：" + text], [dict(title="大侠立志传 Wiki · 社区攻略", url=url, checked="2026-10-17")]
