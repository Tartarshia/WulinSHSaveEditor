"""Read the installed game's official item table; no table is bundled or uploaded."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import re
import struct
from decimal import Decimal, InvalidOperation
from zipfile import ZipFile

from openpyxl import load_workbook


def plain_game_text(value: str) -> str:
    """Keep game text, but remove Unity rich-text markup, never render it as HTML."""
    value = str(value or "").replace("\\n", "\n")
    return re.sub(r"</?(?:color|size|b|i|u|sprite|link|align|indent|line-height|font|voffset)\b[^>]*>|<#[0-9a-fA-F]{6,8}>", "", value).strip()


def read_localized_item_info(raw: bytes, prefix: str = "ItemInfo_") -> dict[str, str]:
    """Read only validated named Odin string fields, not the entire game graph."""
    key_marker = b"\x27\x01\x05\x00\x00\x00" + "UName".encode("utf-16-le")
    chinese_marker = b"\x27\x01\x08\x00\x00\x00" + "SChinese".encode("utf-16-le")
    def string_at(offset):
        if offset + 5 > len(raw): raise ValueError("本地化字符串不完整")
        encoding = raw[offset]
        length = struct.unpack_from("<i", raw, offset + 1)[0]
        if encoding not in (0, 1) or not 0 <= length <= 1_000_000: raise ValueError("本地化字符串格式不支持")
        end = offset + 5 + length * (2 if encoding else 1)
        if end > len(raw): raise ValueError("本地化字符串越界")
        return raw[offset + 5:end].decode("utf-16-le" if encoding else "latin1"), end
    result = {}
    for match in re.finditer(re.escape(key_marker), raw):
        try: key, offset = string_at(match.end())
        except (ValueError, UnicodeError): continue
        if not key.startswith(prefix): continue
        if raw[offset:offset + len(chinese_marker)] != chinese_marker: continue
        value, _ = string_at(offset + len(chinese_marker))
        result[key.removeprefix(prefix)] = plain_game_text(value)
    if not result: raise ValueError("未找到游戏物品中文说明")
    return result


def format_item_stat(entry: str, property_names: dict[str, str] | None = None, direct: bool = False) -> str:
    """Translate effect keys without treating state counters as healing amounts."""
    aliases = {"D_Hp": "气血", "D_Ep": "内力", "D_Mp": "内力", "D_Exp": "实战经验",
               "T_队伍体力": "队伍体力", "T_队伍心情": "队伍心情", "D_玩家关系": "玩家关系",
               "B_BattleMedicine": "吃药次数", "B_集气": "集气"}
    names = property_names or {}
    def label(key):
        if key in aliases: return aliases[key]
        if names.get(key): return names[key]
        if key.startswith("能力经验_"): return key.rsplit("_", 1)[-1] + "经验"
        if re.search(r"[A-Za-z_]", key): return f"未识别属性（{key}）"
        return key
    key, separator, value = str(entry).partition("|")
    if not separator:
        comparison = re.fullmatch(r"(.+?)(>=|<=|==|≥|≤|>|<|=)(.+)", key)
        if comparison: return label(comparison[1]) + comparison[2] + comparison[3]
        return label(key)
    percentage = key.endswith("%")
    base_key = key.removesuffix("%")
    name = label(base_key)
    try:
        amount = Decimal(value)
        if not amount.is_finite(): raise InvalidOperation
    except InvalidOperation:
        return f"{name} {value}"
    if percentage: amount *= 100
    number = format(abs(amount), "f").rstrip("0").rstrip(".") if "." in format(abs(amount), "f") else format(abs(amount), "f")
    suffix = "%" if percentage else ""
    if direct and base_key in {"D_Hp", "D_Ep", "D_Mp", "T_队伍体力", "T_队伍心情"}:
        return f"{name}{'恢复' if amount >= 0 else '减少'} {number}{suffix}"
    return f"{name} {'+' if amount >= 0 else '-'}{number}{suffix}"


def load_item_descriptions(game_root: Path, map_names: dict[int, str] | None = None) -> dict[int, str]:
    import UnityPy
    bundle = game_root / "Wulin_Data/StreamingAssets/aa/StandaloneWindows64/config_assets_all.bundle"
    env = UnityPy.load(str(bundle))
    localized = None
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour" and obj.peek_name() == "LocData":
            raw = obj.get_raw_data()
            localized = read_localized_item_info(raw)
            property_names = read_localized_item_info(raw, "CharPropName_")
            if map_names is not None:
                for key, name in read_localized_item_info(raw, "MapName_").items():
                    if key.isdigit() and name: map_names[int(key)] = name
            break
    if localized is None: raise ValueError("游戏资源包中未找到 LocData 物品说明")
    del env
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as source:
        def table(name):
            return json.loads(source.read(f"Assets/GameRes/json/1/{name}.txt").decode("utf-8-sig"))[name]
        items, buffs = table("ItemData"), {row["uName"]: row for row in table("BuffData")}
    result = {}
    def stats(values, direct=False):
        return "、".join(format_item_stat(entry, property_names, direct) for entry in values or [])
    for row in items:
        try: item_id = int(row["uid"])
        except (TypeError, ValueError): continue
        name = row["uName"]
        lines = [localized.get(name, localized.get(name.strip(), "游戏资料中暂无文字说明。"))]
        for label, field in (("装备要求", "equipRequire"), ("基础装备属性", "equipBonus"), ("使用条件", "usageRestrict")):
            if row.get(field): lines.append(label + "：" + stats(row[field]))
        effects = []
        for buff_name in str(row.get("consumeEffect") or "").split(","):
            effects.extend(buffs.get(buff_name, {}).get("instantEffect") or [])
        if effects: lines.append("使用直接效果（表中值）：" + stats(effects, direct=True))
        if row.get("kungfuLearn"): lines.append("可学习武功：" + row["kungfuLearn"])
        result[item_id] = "\n".join(lines)
    # The shipped JSON may lag the spreadsheet for DLC/newly added items.
    for item_id, (name, _) in load_item_catalog(game_root).items():
        if item_id not in result:
            result[item_id] = localized.get(name, localized.get(name.strip(), "游戏资料中暂无文字说明。"))
    return result


def item_category(item_type: str) -> str:
    """Map the game's detailed ItemType enum to the familiar inventory groups."""
    if item_type.startswith("Equip_Weapon_Pet") or item_type.startswith("Equip_Armor_Pet") or item_type.startswith("Equip_Amulet_Pet"):
        return "宠物装备"
    if item_type.startswith("Equip_Weapon"):
        return "武器"
    if item_type.startswith("Equip_Armor"):
        return "防具"
    if item_type.startswith("Equip_Amulet"):
        return "饰品"
    if item_type.startswith("KungfuBook"):
        return "武功秘籍"
    if item_type.startswith("Consumeable_Material"):
        return "材料"
    if item_type.startswith("Consumeable_Recipe"):
        return "配方"
    if item_type.startswith("Consumeable"):
        return "消耗品"
    if item_type.startswith("Misc_HidWep"):
        return "暗器"
    if item_type.startswith("Misc_Map"):
        return "地图"
    if item_type.startswith("Misc_Poison"):
        return "毒物"
    if item_type.startswith("Misc_Quest"):
        return "任务物品"
    if item_type.startswith("Misc_Treasure"):
        return "珍宝"
    return "杂项" if item_type != "None" else "未分类"


def load_item_catalog(game_root: Path) -> dict[int, tuple[str, str]]:
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"未找到游戏自带物品表：{archive}")
    with ZipFile(archive) as bundle:
        candidates = [info for info in bundle.infolist() if info.filename.lower().endswith(".xlsx") and "/xls/1/" in info.filename.replace("\\", "/")]
        for info in candidates:
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "ItemData" not in workbook.sheetnames:
                workbook.close()
                continue
            sheet = workbook["ItemData"]
            # The shipped ItemData table defines uid in B and display name in C.
            result: dict[int, tuple[str, str]] = {}
            for row in sheet.iter_rows(min_row=4, min_col=2, max_col=10, values_only=True):
                item_id, name, item_type = row[0], row[1], row[8]
                try:
                    item_id = int(item_id)
                except (TypeError, ValueError):
                    continue
                if isinstance(name, str) and name:
                    result[item_id] = (name, item_category(str(item_type or "None")))
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到 ItemData 物品表")


def load_item_names(game_root: Path) -> dict[int, str]:
    """Compatibility helper for callers which only need display names."""
    return {item_id: value[0] for item_id, value in load_item_catalog(game_root).items()}


def load_book_catalog(game_root: Path) -> dict[int, dict]:
    """Read book rarity and detailed martial-art types from the same official ItemData."""
    kinds = {"Inner": "内功", "Outer_Fist": "外功 · 拳掌", "Outer_Sword": "外功 · 剑法",
             "Outer_Blade": "外功 · 刀法", "Outer_Lance": "外功 · 枪法", "Outer_Staff": "外功 · 棍法",
             "Outer_Fan": "外功 · 扇法", "Outer_Brush": "外功 · 笔法", "Outer_Dagger": "外功 · 短兵",
             "Outer_Guqin": "外功 · 琴", "Outer_Flute": "外功 · 箫", "Outer_Pipa": "外功 · 琵琶"}
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx") or "/xls/1/" not in info.filename.replace("\\", "/"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "ItemData" not in workbook.sheetnames:
                workbook.close()
                continue
            result = {}
            for row in workbook["ItemData"].iter_rows(min_row=4, min_col=2, max_col=10, values_only=True):
                item_type = str(row[8] or "")
                if not item_type.startswith("KungfuBook"):
                    continue
                try:
                    item_id, rarity = int(row[0]), int(row[3])
                except (TypeError, ValueError):
                    continue
                if not isinstance(row[1], str) or not row[1]:
                    continue
                kind = item_type.removeprefix("KungfuBook_")
                result[item_id] = {"rarity": rarity, "group": kinds.get(kind, "其他秘籍"),
                                   "group_order": list(kinds).index(kind) if kind in kinds else len(kinds)}
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到秘籍品级和种类资料")


def load_character_names(game_root: Path) -> dict[int, str]:
    """Return template ID -> display name from the installed CharacterPoolData."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"未找到游戏自带角色表：{archive}")
    with ZipFile(archive) as bundle:
        candidates = [info for info in bundle.infolist() if info.filename.lower().endswith(".xlsx") and "/xls/1/" in info.filename.replace("\\", "/")]
        for info in candidates:
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "CharacterPoolData" not in workbook.sheetnames:
                workbook.close()
                continue
            sheet = workbook["CharacterPoolData"]
            result: dict[int, str] = {}
            for template_id, name in sheet.iter_rows(min_row=4, min_col=2, max_col=3, values_only=True):
                try:
                    template_id = int(template_id)
                except (TypeError, ValueError):
                    continue
                if isinstance(name, str) and name:
                    result[template_id] = name
            # Verified DLC2 identity: the legacy table labels this reserved slot "已占用".
            if result.get(10136) == "已占用": result[10136] = "纪茯苓"
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到 CharacterPoolData 角色表")


def load_character_profiles(game_root: Path) -> dict[int, tuple[str, str]]:
    """Return unique character template ID -> (display name, official sex)."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "CharacterPoolData" not in workbook.sheetnames:
                workbook.close()
                continue
            result: dict[int, tuple[str, str]] = {}
            for row in workbook["CharacterPoolData"].iter_rows(min_row=4, min_col=2, max_col=9, values_only=True):
                try:
                    template_id = int(row[0])
                except (TypeError, ValueError):
                    continue
                name, sex, unique = row[1], row[6], row[7]
                if template_id == 10136 and name == "已占用":
                    result[template_id] = ("纪茯苓", "Female")
                    continue
                if isinstance(name, str) and name and str(unique).upper() == "TRUE" and sex in {"Female", "Male"}:
                    result[template_id] = (name, sex)
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到可用的角色性别资料")


def load_affinity_candidates(game_root: Path, profiles: dict[int, tuple[str, str]]) -> dict[str, set[int]]:
    """Use the game's romance pool, teammate table, and explicit sworn exclusions."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        constants = json.loads(bundle.read("Assets/GameRes/json/1/GameEnvConstStrData.txt").decode("utf-8-sig"))["GameEnvConstStrData"]
        constants = {row["uName"]: row["value"] for row in constants}
        romance = {int(value) for value in constants["UIBondsPot"].split(",")}
        buffs = json.loads(bundle.read("Assets/GameRes/json/1/BuffData.txt").decode("utf-8-sig"))["BuffData"]
        romance_names = {match.group(1) for row in buffs for match in [re.fullmatch(r"主角与(.+)情缘buff", str(row.get("uName", "")))] if match}
        # Special-story/DLC bonds need not appear in the old romance UI pool.
        romance_names.update({"凤璇玑", "海棠秋", "纪茯苓", "完颜昭宁"})
        romance_names.update({"鱼薇儿"} if "鱼玄儿" in romance_names else set())
        romance.update(uid for uid, (name, sex) in profiles.items() if sex == "Female" and name in romance_names)
        teammates = json.loads(bundle.read("Assets/GameRes/json/1/CharacterTeamMemberExtendData.txt").decode("utf-8-sig"))["CharacterTeamMemberExtendData"]
        forbidden = set(constants["SwornForbiddenList"].split(","))
        sworn = {int(row["uid"]) for row in teammates if row.get("uName") not in forbidden}
    return {"Female": {uid for uid in romance if profiles.get(uid, ("", ""))[1] == "Female"},
            "Male": {uid for uid in sworn if profiles.get(uid, ("", ""))[1] == "Male"}}


def load_faction_names(game_root: Path) -> dict[int, str]:
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"未找到游戏自带势力表：{archive}")
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "FactionData" not in workbook.sheetnames:
                workbook.close()
                continue
            result: dict[int, str] = {}
            for faction_id, name in workbook["FactionData"].iter_rows(min_row=4, min_col=2, max_col=3, values_only=True):
                try:
                    faction_id = int(faction_id)
                except (TypeError, ValueError):
                    continue
                if isinstance(name, str) and name:
                    result[faction_id] = name
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到 FactionData 势力表")


def load_job_factions(game_root: Path) -> dict[int, str]:
    """Return faction job ID -> parent faction display name."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "FactionJobData" not in workbook.sheetnames:
                workbook.close()
                continue
            result: dict[int, str] = {}
            for job_id, _name, faction_name in workbook["FactionJobData"].iter_rows(min_row=4, min_col=2, max_col=4, values_only=True):
                try:
                    job_id = int(job_id)
                except (TypeError, ValueError):
                    continue
                if isinstance(faction_name, str) and faction_name:
                    result[job_id] = faction_name
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到 FactionJobData 势力职位表")


def load_kungfu_catalog(game_root: Path) -> dict[int, tuple[str, int]]:
    """Return kungfu ID -> (display name, maximum level)."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "KungfuData" not in workbook.sheetnames:
                workbook.close()
                continue
            result: dict[int, tuple[str, int]] = {}
            for row in workbook["KungfuData"].iter_rows(min_row=4, min_col=2, max_col=9, values_only=True):
                try:
                    kungfu_id, max_level = int(row[0]), int(row[7])
                except (TypeError, ValueError):
                    continue
                if isinstance(row[1], str) and row[1]:
                    result[kungfu_id] = (row[1], max_level)
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到 KungfuData 武功表")


def load_life_ability_catalog(game_root: Path) -> dict[str, int]:
    """Return player life-ability property key -> official maximum level."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "GameEnvConstData" not in workbook.sheetnames:
                workbook.close()
                continue
            result: dict[str, int] = {}
            for row in workbook["GameEnvConstData"].iter_rows(values_only=True):
                if len(row) < 4 or not isinstance(row[2], str) or not row[2].startswith("能力_") or not row[2].endswith("Max"):
                    continue
                ability_key = row[2][:-3]
                if ability_key.count("_") != 2:
                    continue
                try:
                    result[ability_key] = int(row[3])
                except (TypeError, ValueError):
                    continue
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到主角生活能力上限表")


def load_jianghu_experience_max(game_root: Path) -> int:
    """Read the Jianghu Knowledge pool cap from the installed game table."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "GameEnvConstData" not in workbook.sheetnames:
                workbook.close()
                continue
            for row in workbook["GameEnvConstData"].iter_rows(values_only=True):
                if len(row) >= 4 and row[2] == "江湖历练AddMax":
                    try:
                        maximum = int(row[3])
                    except (TypeError, ValueError):
                        break
                    workbook.close()
                    return maximum
            workbook.close()
    raise RuntimeError("游戏 ModEditor 中没有找到江湖历练上限")


def load_recipe_catalog(game_root: Path) -> dict[int, str]:
    """Return active recipe ID -> name, excluding rows marked skip by the game data."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "NewRecipeData" not in workbook.sheetnames:
                workbook.close()
                continue
            result: dict[int, str] = {}
            for remark, recipe_id, name in workbook["NewRecipeData"].iter_rows(min_row=4, min_col=1, max_col=3, values_only=True):
                if remark == "skip":
                    continue
                try:
                    recipe_id = int(recipe_id)
                except (TypeError, ValueError):
                    continue
                if isinstance(name, str) and name:
                    result[recipe_id] = name
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到有效配方表")


def load_team_stamina_bonuses(game_root: Path) -> dict[str, float]:
    """Return Buff data ID -> additive team-stamina-cap bonus from game data."""
    return {key: value[0] for key, value in load_team_stamina_modifiers(game_root).items() if value[0]}


def load_recipe_details(game_root: Path) -> dict[int, dict]:
    """Classify active recipes by crafting ability and their produced item's rarity."""
    products: dict[str, int] = {}
    product_ids: dict[str, int] = {}
    recipes = []
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx") or "/xls/1/" not in info.filename.replace("\\", "/"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "ItemData" in workbook.sheetnames:
                for row in workbook["ItemData"].iter_rows(min_row=4, min_col=2, max_col=5, values_only=True):
                    try: rarity = int(row[3]); item_id = int(row[0])
                    except (TypeError, ValueError): continue
                    products[str(item_id)] = rarity
                    product_ids[str(item_id)] = item_id
                    if isinstance(row[1], str):
                        products[row[1]] = rarity
                        product_ids[row[1]] = item_id
            if "NewRecipeData" in workbook.sheetnames:
                recipes.extend(workbook["NewRecipeData"].iter_rows(min_row=4, max_col=6, values_only=True))
            workbook.close()
    result = {}
    for remark, recipe_id, name, ability, level, product in recipes:
        if remark == "skip" or not isinstance(name, str) or not name: continue
        try: recipe_id = int(recipe_id)
        except (TypeError, ValueError): continue
        product = str(product or "").split("|", 1)[0]
        group = str(ability or "").removeprefix("能力_").replace("_", " · ") or "其他配方"
        result[recipe_id] = {"group": group, "rarity": products.get(product, -1), "product_id": product_ids.get(product)}
    if not result: raise RuntimeError("游戏 ModEditor 中没有找到配方分类和品质资料")
    return result


def load_main_prop_growth(game_root: Path) -> dict:
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        rows = json.loads(bundle.read("Assets/GameRes/json/1/GameEnvConstData.txt").decode("utf-8-sig"))["GameEnvConstData"]
    constants = {row["uName"]: row["value"] for row in rows}
    maximum = int(constants["CharacterMainPropMaxLevel"])
    return {"max": maximum, "exp_to_next": {level: int(constants[f"CharacterMainProp{level}"]) for level in range(maximum)}}


def consumable_group(item_type: str, fav_tags: str, default: str) -> str:
    """The game also uses Meal for training books; its tags distinguish them."""
    tags = {tag.strip() for tag in str(fav_tags or "").split(",")}
    if item_type == "Consumeable_Edible_Meal" and "典籍" in tags:
        return "经验书"
    return default


def stackable_other_group(item_type: str, name: str, fav_tags: str, stackable) -> str | None:
    """Only explicitly stackable items; do not treat every quest item as a key."""
    if str(stackable).strip().casefold() not in {"true", "1"}:
        return None
    category = item_category(item_type)
    if category in {"暗器", "毒物", "杂项"}:
        return category
    if category == "任务物品" and name in {"三生石", "三义香"}:
        return "杂项"
    tags = {tag.strip() for tag in str(fav_tags or "").split(",")}
    if category == "任务物品" and ("钥匙" in tags or "钥匙" in name or name.endswith("钥")):
        return "钥匙"
    return None


def load_consumable_catalog(game_root: Path, category: str = "消耗品") -> dict[int, dict]:
    groups = {"Consumeable_Edible_Meal": "食物与酒水", "Consumeable_Edible_Medicine": "药品",
              "Consumeable_Edible_Fruit": "水果", "Consumeable_Edible_Elixir": "丹药",
              "Consumeable_Special": "特殊消耗品", "Consumeable_ChestItem": "宝箱与礼包"}
    groups.update({"Consumeable_Material_" + key: name for key, name in {
        "Herb": "药材", "Ore": "矿石", "Vege": "蔬菜", "Hide": "皮革",
        "Meat": "肉类", "Misc": "其他材料", "Wood": "木材", "Seafood": "水产", "Water": "水与酿造材料"}.items()})
    groups.update({"Misc_Treasure": "其他珍宝", "Misc_Treasure_Painting": "字画",
                   "Misc_Treasure_Antique": "古董", "Misc_Treasure_Valuable": "贵重珍宝", "Misc_Treasure_Copybook": "字帖"})
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx") or "/xls/1/" not in info.filename.replace("\\", "/"): continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "ItemData" not in workbook.sheetnames:
                workbook.close(); continue
            result = {}
            for row in workbook["ItemData"].iter_rows(min_row=4, min_col=2, max_col=25, values_only=True):
                item_type = str(row[8] or "")
                other_group = stackable_other_group(item_type, str(row[1] or ""), row[23], row[5]) if category == "其他（可堆叠）" else None
                if category == "其他（可堆叠）":
                    if not other_group: continue
                elif category == "装备":
                    if item_category(item_type) not in {"武器", "防具", "饰品"}: continue
                elif item_category(item_type) != category: continue
                try: item_id, rarity = int(row[0]), int(row[3])
                except (TypeError, ValueError): continue
                group = item_category(item_type) if category == "装备" else other_group or consumable_group(item_type, row[23], groups.get(item_type, "其他" + category))
                result[item_id] = {"rarity": rarity, "group": group}
            workbook.close()
            if result: return result
    raise RuntimeError(f"游戏 ModEditor 中没有找到{category}分类与品质资料")


def load_team_stamina_modifiers(game_root: Path) -> dict[str, tuple[float, float]]:
    """Return additive and percentage modifiers, including homestead upgrades."""
    archive = game_root / "Wulin_Data/StreamingAssets/ModEditor/ModEditor.zip"
    pattern = re.compile(r"队伍体力Max(%)?@团队\|(-?\d+(?:\.\d+)?)")
    with ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.lower().endswith(".xlsx"):
                continue
            workbook = load_workbook(BytesIO(bundle.read(info)), read_only=True, data_only=True)
            if "BuffData" not in workbook.sheetnames:
                workbook.close()
                continue
            result: dict[str, tuple[float, float]] = {}
            for row in workbook["BuffData"].iter_rows(min_row=4, values_only=True):
                if len(row) < 3 or not isinstance(row[2], str):
                    continue
                matches = [match for value in row if isinstance(value, str) for match in pattern.finditer(value)]
                additive = sum(float(match.group(2)) for match in matches if not match.group(1))
                percentage = sum(float(match.group(2)) for match in matches if match.group(1))
                if additive or percentage:
                    result[row[2]] = (additive, percentage)
            workbook.close()
            if result:
                return result
    raise RuntimeError("游戏 ModEditor 中没有找到队伍体力上限 Buff 数据")
