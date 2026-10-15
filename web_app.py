"""Local-only browser UI for the WulinSH save editor.

This server intentionally binds to loopback only.  It never accepts uploads and
only reads paths chosen on the local machine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import secrets
import shutil
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from werkzeug.serving import make_server

from browser_lifecycle import BrowserSessions

import es3_codec
from game_data import (
    load_character_names, load_character_profiles, load_affinity_candidates, load_faction_names, load_item_catalog, load_book_catalog, load_consumable_catalog, load_item_descriptions,
    load_jianghu_experience_max, load_job_factions, load_kungfu_catalog,
    load_life_ability_catalog, load_recipe_catalog, load_recipe_details, load_team_stamina_modifiers, load_main_prop_growth,
)
from paths import discover_game_roots, discover_save_roots, is_game_root, is_save_root, load_preferences, save_preferences

TEAM_FILE = "SaveObjectPlayerTeam.save"
CHAR_FILE = "SaveObjectGameCharacter.save"
FACTION_FILE = "SaveObjectFaction.save"
TIME_FILE = "SaveObjectGameTime.save"
MAX_VALUE = 9_999_999
INNATE_PROPS = ("体质", "臂力", "敏捷", "悟性", "福缘")
MORAL_PROPS = ("仁德", "义气", "礼节", "智慧", "信用", "勇气")
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


class EditorState:
    def __init__(self) -> None:
        pref = load_preferences()
        configured_game = Path(pref["game_root"]) if pref.get("game_root") else None
        configured_save = Path(pref["save_root"]) if pref.get("save_root") else None
        self.game_root = configured_game if configured_game and is_game_root(configured_game) else next(iter(discover_game_roots()), None)
        self.save_root = configured_save if configured_save and is_save_root(configured_save) else next(iter(discover_save_roots()), None)
        self.slot = ""
        self.team_data: dict | None = None
        self.char_data: dict | None = None
        self.faction_data: dict | None = None
        self.time_data: dict | None = None
        self.item_catalog: dict[int, tuple[str, str]] = {}
        self.item_descriptions: dict[int, str] = {}
        self.map_names: dict[int, str] = {}
        self.book_catalog: dict[int, dict] = {}
        self.consumable_catalog: dict[int, dict] = {}
        self.material_catalog: dict[int, dict] = {}
        self.treasure_catalog: dict[int, dict] = {}
        self.other_stackable_catalog: dict[int, dict] = {}
        self.equipment_catalog: dict[int, dict] = {}
        self.character_names: dict[int, str] = {}
        self.character_profiles: dict[int, tuple[str, str]] = {}
        self.affinity_candidates: dict[str, set[int]] = {}
        self.faction_names: dict[int, str] = {}
        self.job_factions: dict[int, str] = {}
        self.kungfu_catalog: dict[int, tuple[str, int]] = {}
        self.life_catalog: dict[str, int] = {}
        self.recipe_catalog: dict[int, str] = {}
        self.recipe_details: dict[int, dict] = {}
        self.main_prop_growth: dict = {}
        self.stamina_bonuses: dict[str, tuple[float, float]] = {}
        self.jianghu_max = 1_000_000

    @property
    def loaded(self) -> bool:
        return self.team_data is not None

    @property
    def team(self) -> dict:
        self.require_loaded()
        return self.team_data["Data"]["value"]

    @property
    def all_characters(self) -> dict[str, dict]:
        self.require_loaded()
        return self.char_data["Data"]["value"]["createdCharacter"]

    @property
    def hero(self) -> dict:
        return self.all_characters["100401"]

    @property
    def inventory(self) -> list[dict]:
        return self.team["playerTeamInventory"]["contents"]

    def require_loaded(self) -> None:
        if not self.loaded:
            raise ValueError("请先读取一个存档槽。")

    def slots(self) -> list[str]:
        return [record["name"] for record in self.slot_records()]

    def slot_records(self) -> list[dict[str, str | float]]:
        if not self.save_root or not self.save_root.is_dir():
            return []
        records = []
        for folder in self.save_root.iterdir():
            if not folder.is_dir() or not folder.name.startswith(("Save", "QuickSave", "AutoSave")) or not (folder / TEAM_FILE).is_file():
                continue
            latest = max((save.stat().st_mtime for save in folder.glob("*.save")), default=folder.stat().st_mtime)
            records.append({"name": folder.name, "saved_at": datetime.fromtimestamp(latest).astimezone().strftime("%Y-%m-%d %H:%M"), "saved_timestamp": latest})
        return sorted(records, key=lambda record: (-float(record["saved_timestamp"]), str(record["name"])))

    def configure(self, game_root: str, save_root: str) -> None:
        game = Path(game_root) if game_root else self.game_root
        save = Path(save_root) if save_root else self.save_root
        if not game or not is_game_root(game):
            raise ValueError("游戏目录必须直接包含 Wulin.exe 和 Wulin_Data。")
        if not save or not is_save_root(save):
            raise ValueError("存档目录必须直接包含 Save0、QuickSave0 等文件夹。")
        changed_game = game != self.game_root
        changed_save = save != self.save_root
        self.game_root, self.save_root = game, save
        if changed_game or changed_save:
            self.slot = ""
            self.team_data = self.char_data = self.faction_data = self.time_data = None
        if changed_game:
            self.item_descriptions = {}
            self.map_names = {}
            self.consumable_catalog = {}
            self.material_catalog = {}
            self.treasure_catalog = {}
            self.other_stackable_catalog = {}
            self.equipment_catalog = {}
            self.main_prop_growth = {}
            self.recipe_details = {}
            self.book_catalog = {}
            self.affinity_candidates = {}
            self.item_catalog = {}; self.character_names = {}; self.character_profiles = {}; self.faction_names = {}; self.job_factions = {}
            self.kungfu_catalog = {}; self.life_catalog = {}; self.recipe_catalog = {}; self.stamina_bonuses = {}
        save_preferences(game, save)

    def _load_catalogs(self) -> None:
        if not self.item_catalog:
            self.item_catalog = load_item_catalog(self.game_root)
        if not self.item_descriptions:
            self.item_descriptions = load_item_descriptions(self.game_root, self.map_names)
        if not self.book_catalog:
            self.book_catalog = load_book_catalog(self.game_root)
        if not self.consumable_catalog:
            self.consumable_catalog = load_consumable_catalog(self.game_root)
        if not self.material_catalog:
            self.material_catalog = load_consumable_catalog(self.game_root, "材料")
        if not self.treasure_catalog:
            self.treasure_catalog = load_consumable_catalog(self.game_root, "珍宝")
        if not self.other_stackable_catalog:
            self.other_stackable_catalog = load_consumable_catalog(self.game_root, "其他（可堆叠）")
        if not self.equipment_catalog:
            self.equipment_catalog = load_consumable_catalog(self.game_root, "装备")
        if not self.character_names:
            self.character_names = load_character_names(self.game_root)
        if not self.character_profiles:
            self.character_profiles = load_character_profiles(self.game_root)
        # Some DLC slots are still labelled "已占用" in the shipped ModEditor table.
        # Resolve them only when the actual saved character has its identifying DLC buff.
        for char in self.all_characters.values():
            if not isinstance(char, dict): continue
            template_id = char.get("m_templeteUid")
            if self.character_names.get(template_id) != "已占用": continue
            if any(buff.get("dataId") == "DLC2纪茯苓专属buff" for buff in char.get("buffLib", {}).get("buffInstances", [])):
                self.character_names[template_id] = "纪茯苓"
                self.character_profiles[template_id] = ("纪茯苓", "Female")
                self.affinity_candidates = {}
        if not self.affinity_candidates:
            self.affinity_candidates = load_affinity_candidates(self.game_root, self.character_profiles)
        # A saved spouse must never disappear from the page even if editor resources are incomplete.
        for cid, bond in self.hero.get("bonds", {}).items():
            char = self.all_characters.get(str(cid))
            if not isinstance(char, dict): continue
            template_id = char.get("m_templeteUid")
            if int(bond or 0) & 2:
                if template_id not in self.character_profiles:
                    self.character_profiles[template_id] = (self.name(char), "Female")
                self.affinity_candidates["Female"].add(template_id)
        if not self.faction_names:
            self.faction_names = load_faction_names(self.game_root)
        if not self.job_factions:
            self.job_factions = load_job_factions(self.game_root)
        if not self.kungfu_catalog:
            self.kungfu_catalog = load_kungfu_catalog(self.game_root)
        if not self.life_catalog:
            self.life_catalog = load_life_ability_catalog(self.game_root)
        if not self.recipe_catalog:
            self.recipe_catalog = load_recipe_catalog(self.game_root)
        if not self.recipe_details:
            self.recipe_details = load_recipe_details(self.game_root)
        if not self.main_prop_growth:
            self.main_prop_growth = load_main_prop_growth(self.game_root)
        if not self.stamina_bonuses:
            self.stamina_bonuses = load_team_stamina_modifiers(self.game_root)
        self.jianghu_max = load_jianghu_experience_max(self.game_root)

    def load(self, slot: str) -> None:
        self.require_paths()
        if slot not in self.slots():
            raise ValueError("请选择有效的存档槽。")
        folder = self.save_root / slot
        self.team_data = es3_codec.load(folder / TEAM_FILE)
        self.char_data = es3_codec.load(folder / CHAR_FILE)
        self.faction_data = es3_codec.load(folder / FACTION_FILE)
        self.time_data = es3_codec.load(folder / TIME_FILE)
        self.slot = slot
        self._load_catalogs()

    def require_paths(self) -> None:
        if not self.game_root or not is_game_root(self.game_root):
            raise ValueError("未找到游戏目录。")
        if not self.save_root or not is_save_root(self.save_root):
            raise ValueError("未找到存档目录。")

    def name(self, character: dict) -> str:
        template = character.get("m_templeteUid")
        saved = (character.get("m_surName") or "") + (character.get("m_givenName") or "")
        template_name = self.character_names.get(template, "")
        hero_saved = (self.hero.get("m_surName") or "") + (self.hero.get("m_givenName") or "")
        hero_template = self.character_names.get(100401, "")
        if saved and saved == hero_saved and template_name.startswith(hero_template):
            return saved + template_name[len(hero_template):]
        return saved or template_name or f"未知角色 {template}"

    def team_stamina_max(self) -> float:
        libraries = [self.team.get("teamBuffLib", {})]
        for cid in self.team.get("playerTeam", []):
            char = self.all_characters.get(str(cid))
            if isinstance(char, dict):
                libraries.append(char.get("buffLib", {}))
        additive = percentage = 0.0
        for lib in libraries:
            stats = lib.get("buffStats", {})
            fallback_additive = fallback_percentage = 0.0
            for buff in lib.get("buffInstances", []):
                if not buff.get("isValid"): continue
                flat, percent = self.stamina_bonuses.get(buff.get("dataId"), (0, 0))
                stack = max(0, float(buff.get("stack", 1)))
                fallback_additive += flat * stack
                fallback_percentage += percent * stack
            # Saved totals include the actual effective buff values; fall back to official data if absent.
            additive += float(stats.get("队伍体力Max@团队", fallback_additive))
            percentage += float(stats.get("队伍体力Max%@团队", fallback_percentage))
        return max(0, round((100 + additive) * (1 + percentage), 6))

    def overview(self) -> dict:
        slots = self.slot_records()
        result = {"game_root": str(self.game_root or ""), "save_root": str(self.save_root or ""), "slots": slots, "slot": self.slot if self.loaded else (slots[0]["name"] if slots else ""), "loaded": self.loaded}
        if self.loaded:
            result["summary"] = {"items": len(self.inventory), "characters": len(self.characters()), "message": f"已读取 {self.slot}。修改仍只在内存中，保存前不会写入磁盘。"}
        return result

    def items(self, needle: str = "", category: str = "全部", sort: str = "id", include_books: bool = False, include_recipes: bool = False, include_consumables: bool = False, include_materials: bool = False, include_treasures: bool = False, include_other_stackable: bool = False, include_equipment: bool = False) -> dict:
        self.require_loaded(); needle = needle.casefold().strip()
        rows = []
        for index, item in enumerate(self.inventory):
            item_id = item.get("m_templeteId")
            name, item_category = self.item_catalog.get(item_id, ("（未在官方物品表找到）", "未分类"))
            if item_category == "武功秘籍" and not include_books or item_category == "配方" and not include_recipes: continue
            if item_category == "消耗品" and not include_consumables: continue
            if item_category == "材料" and not include_materials or item_category == "珍宝" and not include_treasures: continue
            if item_id in self.other_stackable_catalog and not include_other_stackable: continue
            if item_category in {"武器", "防具", "饰品"} and not include_equipment: continue
            if needle and needle not in str(item_id) and needle not in name.casefold(): continue
            if category != "全部" and item_category != category: continue
            rows.append({"index": index, "id": item_id, "name": name, "description": self.item_description(item_id), "category": item_category, "count": item.get("m_stack", 0), "modified": bool(item.get("modifyData"))})
        rows.sort(key=(lambda x: x["name"]) if sort == "name" else (lambda x: x["id"]), reverse=sort == "id_desc")
        categories = {v[1] for k, v in self.item_catalog.items() if include_other_stackable or k not in self.other_stackable_catalog}
        if not include_books: categories.discard("武功秘籍")
        if not include_recipes: categories.discard("配方")
        if not include_consumables: categories.discard("消耗品")
        if not include_materials: categories.discard("材料")
        if not include_treasures: categories.discard("珍宝")
        if not include_equipment: categories.difference_update({"武器", "防具", "饰品"})
        return {"items": rows, "categories": ["全部", *sorted(categories)]}

    def catalog(self, needle: str, include_books: bool = False, include_recipes: bool = False, include_consumables: bool = False, include_materials: bool = False, include_treasures: bool = False, include_other_stackable: bool = False, include_equipment: bool = False) -> list[dict]:
        needle = needle.casefold().strip()
        return [{"id": item_id, "name": name, "description": self.item_description(item_id), "category": category} for item_id, (name, category) in sorted(self.item_catalog.items()) if (category != "武功秘籍" or include_books) and (category != "配方" or include_recipes) and (category != "消耗品" or include_consumables) and (category != "材料" or include_materials) and (category != "珍宝" or include_treasures) and (include_equipment or category not in {"武器", "防具", "饰品"}) and (include_other_stackable or item_id not in self.other_stackable_catalog) and (not needle or needle in str(item_id) or needle in name.casefold())][:300]

    def item_description(self, item_id: int) -> str:
        return getattr(self, "item_descriptions", {}).get(item_id, "游戏资料中暂无文字说明。")

    def consumables(self, needle: str = "", status: str = "all") -> dict:
        result = self.inventory_group("consumables", needle, status)
        return {"consumables": result["rows"], "total": result["total"]}

    def inventory_group(self, kind: str, needle: str = "", status: str = "all") -> dict:
        self.require_loaded(); needle = needle.casefold().strip()
        catalog = self.quantity_catalog(kind)
        counts = {}
        for item in self.inventory:
            item_id = item.get("m_templeteId")
            counts[item_id] = counts.get(item_id, 0) + max(0, int(item.get("m_stack", 0)))
        rows = []
        for item_id, detail in catalog.items():
            name = self.item_catalog[item_id][0]; count = counts.get(item_id, 0)
            if status == "owned" and not count or status == "missing" and count: continue
            if needle and needle not in str(item_id) and needle not in name.casefold(): continue
            rows.append({"id": item_id, "name": name, "description": self.item_description(item_id), "count": count, **detail})
        rows.sort(key=lambda row: (row["group"], -row["rarity"], row["id"]))
        return {"rows": rows, "total": len(catalog)}

    def quantity_catalog(self, kind: str) -> dict:
        attributes = {"consumables": "consumable_catalog", "materials": "material_catalog", "treasures": "treasure_catalog", "other_stackable": "other_stackable_catalog"}
        if kind not in attributes: raise ValueError("不支持的物品分类。")
        return getattr(self, attributes[kind])

    def set_consumable_count(self, item_id: int, count: int) -> None:
        self.set_inventory_group_count("consumables", item_id, count)

    def set_experience_books_999(self) -> dict:
        self.require_loaded()
        ids = [item_id for item_id, detail in self.consumable_catalog.items() if detail.get("group") == "经验书"]
        if not ids: raise ValueError("当前游戏资料中没有找到经验书。")
        if any(self.item_catalog.get(item_id, ("", ""))[1] != "消耗品" for item_id in ids):
            raise ValueError("经验书目录与物品分类不一致，请重新读取游戏资料。")
        for item_id in ids:
            self.set_consumable_count(item_id, 999)
        return {"count": len(ids), "message": f"已将全部 {len(ids)} 种经验书各设为 999 本（仅内存）；点击保存消耗品后才写入存档。"}

    def set_inventory_group_count(self, kind: str, item_id: int, count: int) -> None:
        self.require_loaded()
        if item_id not in self.quantity_catalog(kind): raise ValueError("该 ID 不属于所选官方物品分类。")
        if not 0 <= count <= 999_999: raise ValueError("物品数量范围为 0–999999。")
        matching = [index for index, item in enumerate(self.inventory) if item.get("m_templeteId") == item_id]
        if count and matching:
            self.inventory[matching[0]]["m_stack"] = count
            for index in reversed(matching[1:]): del self.inventory[index]
        elif count:
            self.set_item(item_id, count)
        else:
            for index in reversed(matching): del self.inventory[index]

    def book_possessions(self) -> dict[int, list[dict]]:
        self.require_loaded()
        possessions: dict[int, list[dict]] = {}
        def collect(item, location, personal):
            if not isinstance(item, dict): return
            try: item_id = int(item.get("m_templeteId", 0)); count = int(item.get("m_stack", 1))
            except (TypeError, ValueError): return
            if count <= 0 or self.item_catalog.get(item_id, ("", ""))[1] != "武功秘籍": return
            possessions.setdefault(item_id, []).append({"location": location, "personal": personal, "count": count})
        for item in self.inventory:
            collect(item, "队伍背包", False)
        for cid in dict.fromkeys(str(value) for value in self.team.get("playerTeam", [])):
            char = self.all_characters.get(cid)
            if not isinstance(char, dict): continue
            holder = self.name(char)
            if holder.startswith("@"):
                holder = self.character_names.get(char.get("m_templeteUid"), holder)
            for item in (char.get("equipSlot") or {}).values():
                collect(item, holder + " · 装备", True)
            for item in (char.get("backPack") or {}).get("contents", []):
                collect(item, holder + " · 个人背包", True)
        return possessions

    def books(self, needle: str = "", status: str = "all") -> dict:
        self.require_loaded(); needle = needle.casefold().strip()
        possessions = self.book_possessions()
        rows = []
        for item_id, (name, category) in sorted(self.item_catalog.items()):
            if category != "武功秘籍": continue
            owned = item_id in possessions
            if status == "owned" and not owned or status == "missing" and owned: continue
            if needle and needle not in str(item_id) and needle not in name.casefold(): continue
            detail = self.book_catalog.get(item_id, {"rarity": -1, "group": "其他秘籍", "group_order": 99})
            sources = possessions.get(item_id, [])
            rows.append({"id": item_id, "name": name, "description": self.item_description(item_id), "owned": owned, "records": len(sources), "holders": list(dict.fromkeys(source["location"] for source in sources)), "backpack_records": sum(not source["personal"] for source in sources), "personal_owned": any(source["personal"] for source in sources), **detail})
        rows.sort(key=lambda row: (row["group_order"], -row["rarity"], row["id"]))
        return {"books": rows, "total": len([1 for _, (_, category) in self.item_catalog.items() if category == "武功秘籍"]), "owned": sum(row["owned"] for row in rows)}

    def set_book_owned(self, item_id: int, owned: bool) -> str:
        self.require_loaded()
        if self.item_catalog.get(item_id, ("", ""))[1] != "武功秘籍": raise ValueError("该 ID 不是官方武功秘籍。")
        matching = [index for index, item in enumerate(self.inventory) if item.get("m_templeteId") == item_id]
        if owned and item_id in self.book_possessions():
            return "队伍背包或当前队员已持有该秘籍，不再重复添加。"
        if owned:
            self.inventory.append({"m_templeteId": item_id, "m_stack": 1, "modifyData": None, "IsNew": False, "IsForbidden": False})
            return "已在内存中添加该武功秘籍。"
        if not owned and matching:
            for index in reversed(matching): del self.inventory[index]
            return "已从内存背包移除该武功秘籍。"
        if not owned and item_id in self.book_possessions():
            raise ValueError("该秘籍由当前队员持有，请在游戏中卸下后再操作。")
        return "武功秘籍状态未改变。"

    def recipes(self, needle: str = "", status: str = "all") -> dict:
        self.require_loaded(); needle = needle.casefold().strip()
        learned = set(self.team.get("learntRecipes", []))
        rows = []
        for recipe_id, name in self.recipe_catalog.items():
            owned = recipe_id in learned
            if status == "owned" and not owned or status == "missing" and owned: continue
            if needle and needle not in str(recipe_id) and needle not in name.casefold(): continue
            detail = self.recipe_details.get(recipe_id, {"group": "其他配方", "rarity": -1})
            rows.append({"id": recipe_id, "name": name, "owned": owned, "description": "制作产物说明：\n" + self.item_description(detail.get("product_id")), **detail})
        rows.sort(key=lambda row: (row["group"], -row["rarity"], row["id"]))
        return {"recipes": rows, "total": len(self.recipe_catalog)}

    def set_recipe_learned(self, recipe_id: int, learned: bool) -> str:
        self.require_loaded()
        if recipe_id not in self.recipe_catalog: raise ValueError("该 ID 不是官方有效配方。")
        recipes = self.team.setdefault("learntRecipes", [])
        if learned and recipe_id not in recipes: recipes.append(recipe_id)
        if not learned: recipes[:] = [value for value in recipes if value != recipe_id]
        return "配方学习状态已在内存中修改。"

    @staticmethod
    def equipment_fingerprint(item: dict) -> str:
        return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def equipment_extra_data(data) -> list[dict]:
        """Show stored values without claiming that stored effects are active."""
        labels = {"templeteUid": "装备模板 ID", "forgeLevel": "锻造等级（原值）", "rawRnd": "随机记录（原值）",
                  "overrideBonus": "属性覆盖", "overrideBonusExt": "额外效果覆盖", "overrideEquipReq": "装备要求覆盖",
                  "forgeEffect": "锻造效果", "key": "属性或效果标识", "values": "数值（values）",
                  "dValues": "数值（dValues）", "isValid": "有效标记（原值）"}
        rows = []
        def visit(value, path):
            if isinstance(value, dict) and value:
                for key, child in value.items(): visit(child, [*path, labels.get(key, str(key))])
            else:
                text = "未设置" if value is None else "是" if value is True else "否" if value is False else json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                rows.append({"label": " / ".join(path) or "附加数据", "value": text})
        if data: visit(data, [])
        return rows

    def equipment(self, needle: str = "", status: str = "all") -> dict:
        self.require_loaded(); needle = needle.casefold().strip()
        records = {}
        for index, item in enumerate(self.inventory):
            item_id = item.get("m_templeteId")
            if item_id in self.equipment_catalog:
                records.setdefault(item_id, []).append({"index": index, "fingerprint": self.equipment_fingerprint(item), "modified": bool(item.get("modifyData")), "extra_data": self.equipment_extra_data(item.get("modifyData"))})
        rows = []
        for item_id, detail in self.equipment_catalog.items():
            name = self.item_catalog.get(item_id, (str(item_id), ""))[0]
            copies = records.get(item_id, [])
            if status == "owned" and not copies or status == "missing" and copies: continue
            if needle and needle not in str(item_id) and needle not in name.casefold(): continue
            rows.append({"id": item_id, "name": name, "description": self.item_description(item_id), "copies": copies, **detail})
        order = {"武器": 0, "防具": 1, "饰品": 2}
        rows.sort(key=lambda x: (x.get("group_order", order.get(x["group"], 99)), -x["rarity"], x["id"]))
        return {"rows": rows, "total": len(self.equipment_catalog)}

    def change_equipment(self, data: dict) -> None:
        self.require_loaded(); item_id = int(data["id"])
        if item_id not in self.equipment_catalog: raise ValueError("该 ID 不属于官方武器、防具或饰品。")
        if data.get("action") == "add":
            self.inventory.append({"m_templeteId": item_id, "m_stack": 1, "modifyData": None, "IsNew": False, "IsForbidden": False})
        elif data.get("action") == "delete":
            index = int(data["index"])
            if not 0 <= index < len(self.inventory): raise ValueError("背包已变化，请刷新页面后再删除。")
            item = self.inventory[index]
            if item.get("m_templeteId") != item_id or self.equipment_fingerprint(item) != data.get("fingerprint"):
                raise ValueError("背包已变化，请刷新页面后再删除。")
            self.delete_item(index)
        else: raise ValueError("装备只支持添加或删除。")

    def set_item(self, item_id: int, count: int) -> None:
        self.require_loaded()
        if item_id <= 0 or not 0 < count <= 999_999: raise ValueError("ID 必须大于 0，数量范围为 1–999999。")
        for item in self.inventory:
            if item.get("m_templeteId") == item_id:
                item["m_stack"] = count; return
        self.inventory.append({"m_templeteId": item_id, "m_stack": count, "modifyData": None, "IsNew": False, "IsForbidden": False})

    def delete_item(self, index: int) -> None:
        self.require_loaded(); del self.inventory[index]

    def characters(self) -> list[dict]:
        self.require_loaded(); active = {str(x) for x in self.team.get("playerTeam", [])}; rows = []
        for cid, char in self.all_characters.items():
            state = char.get("m_TeamMemberState")
            if cid in active or isinstance(state, dict):
                status = "出战中" if cid in active else ("已入队，未出战" if state.get("isJoined") else "曾入队，现已离队")
                rows.append({"id": cid, "name": self.name(char), "status": status, "level": char.get("m_level", 0), "location": self.character_location(char) if cid not in active else None})
        return sorted(rows, key=lambda x: (x["status"] != "出战中", x["name"], int(x["id"])))

    def character_location(self, char: dict) -> dict:
        """Read saved position, never confuse respawn/leave points with current map."""
        team_state = char.get("m_TeamMemberState") or {}
        def valid_map(value):
            try: value = int(value)
            except (TypeError, ValueError): return None
            return value if value > 0 else None
        map_id = valid_map(char.get("m_curMapId"))
        source, pos = "存档所在地", char.get("m_curPos")
        if map_id is None:
            map_id = valid_map(team_state.get("leaveTeamMap"))
            source, pos = "上次离队地点", team_state.get("leaveTeamPos")
        if map_id is None: return {"name": "存档未记录位置", "map_id": None, "source": "位置", "pos": None}
        if char.get("m_isAlive") is False: source = "已死亡 · 最后记录位置"
        name = getattr(self, "map_names", {}).get(map_id, f"未知地图 {map_id}")
        # Homestead main map and rooms in the installed game; room names remain local-data driven.
        if map_id in range(500, 508):
            name = "家园" if map_id == 500 else f"家园 · {name}"
        coordinates = {key: pos[key] for key in ("x", "y") if key in pos} if isinstance(pos, dict) else None
        if coordinates and any(value == -2147483648 for value in coordinates.values()): coordinates = None
        return {"name": name, "map_id": map_id, "source": source, "pos": coordinates}

    def affinities(self, sex: str) -> dict:
        self.require_loaded()
        if sex not in {"Female", "Male"}: raise ValueError("仅支持女性或男性角色列表。")
        labels = {"Female": ("未入队", "已入队", "已结缘"), "Male": ("未入队", "已入队", "已结义")}[sex]
        bonds = {str(key): value for key, value in self.hero.get("bonds", {}).items()}
        rows: list[dict] = []
        instances: dict[int, tuple[str, dict]] = {}
        for cid, char in self.all_characters.items():
            if not isinstance(char, dict) or cid == "100401": continue
            template_id = char.get("m_templeteUid")
            try: template_id = int(template_id)
            except (TypeError, ValueError): continue
            if template_id not in instances or str(cid) == str(template_id):
                instances[template_id] = (str(cid), char)
        for template_id in sorted(self.affinity_candidates.get(sex, set())):
            profile = self.character_profiles[template_id]
            cid, char = instances.get(template_id, (str(template_id), {}))
            team_state = char.get("m_TeamMemberState")
            joined = isinstance(team_state, dict) and bool(team_state.get("isJoined"))
            bond = bonds.get(str(cid), bonds.get(str(template_id)))
            # Verified against the installed game's BondType enum: Wife=2, SwornBrotherAndSister=512.
            completed = bool(int(bond or 0) & (2 if sex == "Female" else 512))
            status = labels[2] if completed else labels[1] if joined else labels[0]
            display_name = {20001: "刘十八", 20004: "包打听", 20006: "王大锤", 20022: "白头翁", 20025: "花四娘", 20063: "严如蕊", 20127: "丁小姐", 40685: "邪郎中"}.get(template_id, profile[0])
            rows.append({"id": cid, "name": display_name, "status": status, "relation": self.hero.get("relationShip", {}).get(str(cid), 0), "bond": bond})
        order = {labels[2]: 0, labels[1]: 1, labels[0]: 2}
        return {"sex": sex, "bond_label": labels[2], "rows": sorted(rows, key=lambda row: (order[row["status"]], row["name"], int(row["id"])))}

    def character_detail(self, cid: str) -> dict:
        self.require_loaded(); char = self.all_characters.get(cid)
        if not char: raise ValueError("未找到角色。")
        origin = char.get("m_originProps", {})
        addition = char.get("m_additionProps", {})
        props = [{"key": key, "value": value} for key, value in origin.items() if key not in INNATE_PROPS + MORAL_PROPS]
        innate = [{"key": key, "level": origin.get(key, 1), "bonus": addition.get(key, 0), "max": self.main_prop_growth["max"], "exp": addition.get(key + "经验", 0), "exp_to_next": self.main_prop_growth["exp_to_next"].get(int(origin.get(key, 1)))} for key in INNATE_PROPS]
        morals = [{"key": key, "value": origin.get(key, 0) + addition.get(key, 0)} for key in MORAL_PROPS] if cid == "100401" else []
        kungfu = []
        for index, ability in enumerate(char.get("kungfuInstances", [])):
            ability_id = ability.get("m_templeteUid"); name, maximum = self.kungfu_catalog.get(ability_id, (f"未知武功 {ability_id}", 10))
            kungfu.append({"index": index, "id": ability_id, "name": name, "level": ability.get("m_level", 1), "max": maximum, "exp": ability.get("m_exp", 0)})
        life = self.life_abilities()["abilities"] if cid == "100401" else []
        team_state = char.get("m_TeamMemberState")
        off_field = isinstance(team_state, dict) and cid not in {str(x) for x in self.team.get("playerTeam", [])}
        return {"id": cid, "name": self.name(char), "location": self.character_location(char) if off_field else None, "level": char.get("m_level", 1), "exp": char.get("m_exp", 0), "props": props, "innate": innate, "morals": morals, "kungfu": kungfu, "life": life}

    def life_abilities(self) -> dict:
        self.require_loaded()
        addition = self.hero.get("m_additionProps", {})
        rows = []
        for key, maximum in sorted(self.life_catalog.items()):
            _, category, name = key.split("_", 2)
            exp_key = "能力经验_" + key[len("能力_"):]
            rows.append({"key": key, "category": category, "name": name, "level": addition.get(key, 0), "max": maximum, "exp": addition.get(exp_key, 0)})
        return {"abilities": rows, "total": len(rows)}

    def max_life_abilities(self) -> dict:
        self.require_loaded()
        if not self.life_catalog: raise ValueError("当前游戏资料中没有找到生活技能。")
        props = self.hero.setdefault("m_additionProps", {})
        for key, maximum in self.life_catalog.items():
            props[key] = maximum
            props["能力经验_" + key[len("能力_"):]] = 0
        return {"count": len(self.life_catalog), "message": f"已将全部 {len(self.life_catalog)} 项生活技能设为满级，经验清零（仅内存）；点击保存生活技能后才写入存档。"}

    def set_character(self, cid: str, payload: dict) -> None:
        self.require_loaded()
        char = self.all_characters.get(cid)
        if not char: raise ValueError("未找到角色。")
        kind = payload.get("kind")
        if kind == "innate_max":
            maximum = self.main_prop_growth["max"]
            origin = char.setdefault("m_originProps", {})
            for key in INNATE_PROPS:
                origin[key] = maximum
        elif kind == "innate":
            key = payload["key"]
            if key not in INNATE_PROPS: raise ValueError("未知的先天属性。")
            level, exp = int(payload["level"]), float(payload["exp"])
            maximum = self.main_prop_growth["max"]
            if not 1 <= level <= maximum or not math.isfinite(exp) or not 0 <= exp <= MAX_VALUE:
                raise ValueError(f"先天等级范围为 1–{maximum}，经验范围为 0–{MAX_VALUE}。")
            char.setdefault("m_originProps", {})[key] = level
            char.setdefault("m_additionProps", {})[key + "经验"] = int(exp) if exp.is_integer() else exp
        elif kind == "moral":
            if cid != "100401": raise ValueError("道德六维仅属于主角。")
            key, value = payload["key"], float(payload["value"])
            if key not in MORAL_PROPS or not math.isfinite(value) or not -MAX_VALUE <= value <= MAX_VALUE:
                raise ValueError("无效的六维属性或数值。")
            change = value - char.get("m_originProps", {}).get(key, 0)
            char.setdefault("m_additionProps", {})[key] = int(change) if change.is_integer() else change
        elif kind == "prop":
            value = float(payload["value"]); char.setdefault("m_originProps", {})[payload["key"]] = int(value) if value.is_integer() else value
        elif kind == "level":
            level, exp = int(payload["level"]), int(payload["exp"])
            if not 1 <= level <= 100 or not 0 <= exp <= MAX_VALUE: raise ValueError("角色等级范围为 1–100，经验范围为 0–9999999。")
            char["m_level"], char["m_exp"] = level, exp
        elif kind == "kungfu":
            ability = char.get("kungfuInstances", [])[int(payload["index"])]; maximum = self.kungfu_catalog.get(ability.get("m_templeteUid"), ("", 10))[1]
            level, exp = int(payload["level"]), int(payload["exp"])
            if not 1 <= level <= maximum or not 0 <= exp <= MAX_VALUE: raise ValueError(f"武功等级范围为 1–{maximum}。")
            ability["m_level"], ability["m_exp"] = level, exp
        elif kind == "life":
            if cid != "100401": raise ValueError("生活技能仅属于主角。")
            if payload.get("key") not in self.life_catalog: raise ValueError("未知的生活技能。")
            key = payload["key"]; maximum = self.life_catalog[key]; level, exp = int(payload["level"]), float(payload["exp"])
            if not 0 <= level <= maximum or not 0 <= exp <= MAX_VALUE: raise ValueError(f"生活技能等级范围为 0–{maximum}。")
            props = char.setdefault("m_additionProps", {}); props[key] = level; props["能力经验_" + key[len("能力_") :]] = int(exp) if exp.is_integer() else exp
        else: raise ValueError("未知的角色修改类型。")

    def global_data(self) -> dict:
        self.require_loaded(); book_ids = {k for k, (_, cat) in self.item_catalog.items() if cat == "武功秘籍"}; owned = set(self.book_possessions())
        learned = set(self.team.get("learntRecipes", [])); time = self.time_data["Data"]["value"]
        return {"money": self.team["playerTeamInventory"].get("currencies", {}).get("0", 0), "stamina": self.team.get("teamProps", {}).get("队伍体力", 0), "stamina_max": self.team_stamina_max(), "mood": self.team.get("teamProps", {}).get("队伍心情", 0), "jianghu": self.hero.get("m_additionProps", {}).get("江湖历练", 0), "jianghu_max": self.jianghu_max, "day": int(float(time.get("TotalQuaterPassed", 0)) // 96) + 1, "books": {"all": len(book_ids), "owned": len(book_ids & owned), "missing": len(book_ids - owned)}, "recipes": {"all": len(self.recipe_catalog), "learned": len(set(self.recipe_catalog) & learned), "missing": len(set(self.recipe_catalog) - learned)}}

    def set_global(self, kind: str, value: int | None = None) -> str:
        self.require_loaded(); time = self.time_data["Data"]["value"]
        if kind == "books":
            owned = set(self.book_possessions()); ids = {k for k, (_, cat) in self.item_catalog.items() if cat == "武功秘籍"}; missing = sorted(ids - owned)
            self.inventory.extend({"m_templeteId": item_id, "m_stack": 1, "modifyData": None, "IsNew": False, "IsForbidden": False} for item_id in missing); return f"已补齐 {len(missing)} 本未拥有的武功秘籍。"
        if kind == "recipes":
            learned = self.team.setdefault("learntRecipes", []); missing = sorted(set(self.recipe_catalog) - set(learned)); learned.extend(missing); return f"已解锁 {len(missing)} 个未学配方。"
        if kind == "fill":
            self.set_global("stamina", int(self.team_stamina_max())); self.set_global("mood", 100); return "已补满体力与心情。"
        if value is None: raise ValueError("缺少数值。")
        if kind == "money":
            if not 0 <= value <= MAX_VALUE: raise ValueError("铜钱范围为 0–9999999。")
            self.team["playerTeamInventory"].setdefault("currencies", {})["0"] = value
        elif kind == "stamina":
            if not 0 <= value <= self.team_stamina_max(): raise ValueError(f"体力范围为 0–{self.team_stamina_max():g}。")
            self.team.setdefault("teamProps", {})["队伍体力"] = value; self.team["storedStaminaOdd"] = 0; self.team["lastStaminaTickByQuarter"] = float(time.get("TotalQuaterPassed", 0))
        elif kind == "mood":
            if not 0 <= value <= 100: raise ValueError("心情范围为 0–100。")
            self.team.setdefault("teamProps", {})["队伍心情"] = value; self.team["lastMoodCheckedTime"] = float(time.get("TotalQuaterPassed", 0)); self.team["nextMoodStaminaDec"] = 0
        elif kind == "jianghu":
            if not 0 <= value <= self.jianghu_max: raise ValueError(f"江湖历练范围为 0–{self.jianghu_max:,}。")
            self.hero.setdefault("m_additionProps", {})["江湖历练"] = value
        elif kind == "day":
            old_total = float(time.get("TotalQuaterPassed", 0)); current = int(old_total // 96) + 1
            if value < current: raise ValueError(f"当前已是第 {current} 日；仅支持向前推进。")
            tod = old_total % 96; total = (value - 1) * 96 + tod; year, day_of_year = divmod(value - 1, 360); month, day_in_month = divmod(day_of_year, 30)
            time.update({"TotalQuaterPassed": total, "Year": year, "Month": month + 1, "Day": day_in_month + 1, "totalYearChanged": year, "totalSecsTimeYear": day_of_year * 86400 + tod * 900, "QuaterOfDay": tod, "Dhour": int(tod) // 8, "Quarter": int(tod) % 8, "IsDaylight": 32 <= tod < 80})
            start = time.get("simulationStartTime", {}).get("ticks")
            if isinstance(start, int): time.setdefault("simulatedTime", {})["ticks"] = start + int(total * 900 * 10_000_000)
            self.team["lastStaminaTickByQuarter"] = total; self.team["lastMoodCheckedTime"] = total
        else: raise ValueError("未知的全局修改类型。")
        return "已在内存中修改；保存前不会写入磁盘。"

    def relations(self, kind: str, group: str = "", needle: str = "") -> dict:
        self.require_loaded(); needle = needle.casefold().strip()
        if kind == "npc":
            rows = []
            groups = set()
            for cid, value in self.hero.get("relationShip", {}).items():
                char = self.all_characters.get(str(cid))
                if not char: continue
                name = self.name(char); current_group = self.job_factions.get(char.get("m_factionJob"), "其他 / 无势力")
                groups.add(current_group)
                if (group and group != "全部" and current_group != group) or (needle and needle not in name.casefold() and needle not in str(cid)): continue
                rows.append({"id": str(cid), "name": name, "value": value, "group": current_group})
            return {"rows": sorted(rows, key=lambda x: (x["name"], int(x["id"]))), "groups": sorted(groups)}
        factions = self.faction_data["Data"]["value"].get("factions", {}); rows = []
        for fid, faction in factions.items():
            numeric = str(faction.get("templeteId", fid)); name = self.faction_names.get(int(numeric), f"未知势力 {numeric}")
            if not needle or needle in name.casefold() or needle in numeric: rows.append({"id": numeric, "name": name, "value": faction.get("playerFame", 0)})
        return {"rows": sorted(rows, key=lambda x: (x["name"], int(x["id"])))}

    def set_relation(self, kind: str, entity_id: str, value: int) -> None:
        self.require_loaded()
        if not -100 <= value <= 100: raise ValueError("关系值范围为 -100 至 100。")
        if kind == "npc":
            self.hero.setdefault("relationShip", {})[entity_id] = value
            if entity_id in self.all_characters: self.all_characters[entity_id].setdefault("relationShip", {})["100401"] = value
        else:
            state = self.faction_data["Data"]["value"]; state["factions"][entity_id]["playerFame"] = value
            for faction in state.get("factionDict", {}).values():
                if str(faction.get("templeteId")) == entity_id: faction["playerFame"] = value

    def save(self, target: str) -> str:
        self.require_loaded(); folder = self.save_root / self.slot; backup = self.save_root / "_EditorBackups" / f"{self.slot}_{datetime.now():%Y%m%d_%H%M%S}"
        backup.parent.mkdir(exist_ok=True); shutil.copytree(folder, backup)
        if target == "items": es3_codec.atomic_write(folder / TEAM_FILE, self.team_data)
        elif target in {"characters", "relations", "life"}: es3_codec.atomic_write(folder / CHAR_FILE, self.char_data)
        elif target in {"books", "recipes", "consumables", "materials", "treasures", "other_stackable", "equipment"}: es3_codec.atomic_write(folder / TEAM_FILE, self.team_data)
        elif target == "factions": es3_codec.atomic_write(folder / FACTION_FILE, self.faction_data)
        elif target == "global":
            es3_codec.atomic_write(folder / TEAM_FILE, self.team_data); es3_codec.atomic_write(folder / CHAR_FILE, self.char_data); es3_codec.atomic_write(folder / TIME_FILE, self.time_data)
        else: raise ValueError("未知保存范围。")
        return f"已保存并回读校验。完整备份：{backup}"


def make_app(port: int, sessions: BrowserSessions | None = None) -> Flask:
    app = Flask(__name__, template_folder=str(RESOURCE_ROOT / "templates"), static_folder=str(RESOURCE_ROOT / "static"))
    state = EditorState(); token = secrets.token_urlsafe(32); origin = f"http://127.0.0.1:{port}"
    sessions = sessions or BrowserSessions()
    app.extensions["browser_sessions"] = sessions

    @app.before_request
    def track_request():
        if not sessions.begin_request():
            return jsonify(error="修改器正在关闭，请重新启动。"), 503
        g.session_request = True

    @app.teardown_request
    def finish_request(_error):
        if getattr(g, "session_request", False):
            sessions.end_request()
            g.session_request = False

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"; response.headers["X-Content-Type-Options"] = "nosniff"; response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'"
        return response

    @app.before_request
    def protect():
        if request.method != "POST": return
        supplied_token = request.headers.get("X-Wulin-Token")
        if request.path == "/api/session/close":
            supplied_token = supplied_token or (request.get_json(silent=True) or {}).get("token")
        if request.headers.get("Origin") not in (None, origin) or supplied_token != token:
            return jsonify(error="本地服务拒绝了非本页发起的写入请求。"), 403

    def body() -> dict: return request.get_json(silent=True) or {}
    def respond(call):
        try: return jsonify(call())
        except (ValueError, KeyError, IndexError, TypeError) as exc: return jsonify(error=str(exc)), 400
        except Exception as exc: return jsonify(error=f"操作失败：{exc}"), 500

    @app.get("/")
    def index(): return render_template("index.html", token=token)
    @app.get("/api/session/info")
    def session_info(): return jsonify(application="WulinSHSaveEditor", lifecycle=1)
    @app.post("/api/session/heartbeat")
    def session_heartbeat(): return respond(lambda: {"alive": sessions.heartbeat(body().get("page"))})
    @app.post("/api/session/close")
    def session_close(): return respond(lambda: (sessions.close(body().get("page")), {"ok": True})[1])
    @app.get("/api/state")
    def api_state(): return respond(state.overview)
    @app.post("/api/config")
    def api_config(): return respond(lambda: (state.configure(body().get("game_root", ""), body().get("save_root", "")), state.overview())[1])
    @app.post("/api/load")
    def api_load(): return respond(lambda: (state.load(body()["slot"]), state.overview())[1])
    @app.get("/api/items")
    def api_items(): return respond(lambda: state.items(request.args.get("q", ""), request.args.get("category", "全部"), request.args.get("sort", "id"), request.args.get("include_books") == "1", request.args.get("include_recipes") == "1", request.args.get("include_consumables") == "1", request.args.get("include_materials") == "1", request.args.get("include_treasures") == "1", request.args.get("include_other_stackable") == "1", request.args.get("include_equipment") == "1"))
    @app.get("/api/catalog")
    def api_catalog(): return respond(lambda: state.catalog(request.args.get("q", ""), request.args.get("include_books") == "1", request.args.get("include_recipes") == "1", request.args.get("include_consumables") == "1", request.args.get("include_materials") == "1", request.args.get("include_treasures") == "1", request.args.get("include_other_stackable") == "1", request.args.get("include_equipment") == "1"))
    @app.get("/api/consumables")
    def api_consumables(): return respond(lambda: state.consumables(request.args.get("q", ""), request.args.get("status", "all")))
    @app.get("/api/equipment")
    def api_equipment(): return respond(lambda: state.equipment(request.args.get("q", ""), request.args.get("status", "all")))
    @app.post("/api/equipment")
    def api_change_equipment(): return respond(lambda: (state.change_equipment(body()), {"message": "装备已在内存中修改，点击保存装备后才写入存档。"})[1])
    @app.post("/api/consumables")
    def api_set_consumable(): return respond(lambda: (state.set_consumable_count(int(body()["id"]), int(body()["count"])), {"message": "消耗品数量已在内存中修改。"})[1])
    @app.post("/api/consumables/experience-books-999")
    def api_experience_books_999(): return respond(state.set_experience_books_999)
    @app.get("/api/inventory-groups/<kind>")
    def api_inventory_group(kind): return respond(lambda: state.inventory_group(kind, request.args.get("q", ""), request.args.get("status", "all")))
    @app.post("/api/inventory-groups/<kind>")
    def api_set_inventory_group(kind): return respond(lambda: (state.set_inventory_group_count(kind, int(body()["id"]), int(body()["count"])), {"message": "物品数量已在内存中修改。"})[1])
    @app.post("/api/items")
    def api_set_item(): return respond(lambda: (state.set_item(int(body()["id"]), int(body()["count"])), {"message": "物品已在内存中修改。"})[1])
    @app.post("/api/items/delete")
    def api_delete_item(): return respond(lambda: (state.delete_item(int(body()["index"])), {"message": "物品已在内存中删除。"})[1])
    @app.get("/api/books")
    def api_books(): return respond(lambda: state.books(request.args.get("q", ""), request.args.get("status", "all")))
    @app.post("/api/books")
    def api_set_book(): return respond(lambda: {"message": state.set_book_owned(int(body()["id"]), bool(body()["owned"]))})
    @app.get("/api/characters")
    def api_characters(): return respond(lambda: {"characters": state.characters()})
    @app.get("/api/life-abilities")
    def api_life_abilities(): return respond(state.life_abilities)
    @app.post("/api/life-abilities")
    def api_set_life_ability(): return respond(lambda: (state.set_character("100401", {**body(), "kind": "life"}), {"message": "主角生活技能已在内存中修改，点击保存生活技能后才写入存档。"})[1])
    @app.post("/api/life-abilities/max")
    def api_max_life_abilities(): return respond(state.max_life_abilities)
    @app.get("/api/recipes")
    def api_recipes(): return respond(lambda: state.recipes(request.args.get("q", ""), request.args.get("status", "all")))
    @app.post("/api/recipes")
    def api_set_recipe(): return respond(lambda: {"message": state.set_recipe_learned(int(body()["id"]), bool(body()["owned"]))})
    @app.get("/api/affinities/<sex>")
    def api_affinities(sex): return respond(lambda: state.affinities(sex))
    @app.get("/api/characters/<cid>")
    def api_character(cid): return respond(lambda: state.character_detail(cid))
    @app.post("/api/characters/<cid>")
    def api_set_character(cid): return respond(lambda: (state.set_character(cid, body()), state.character_detail(cid))[1])
    @app.get("/api/global")
    def api_global(): return respond(state.global_data)
    @app.post("/api/global")
    def api_set_global(): return respond(lambda: {"message": state.set_global(body()["kind"], body().get("value")), "data": state.global_data()})
    @app.get("/api/relations/<kind>")
    def api_relations(kind): return respond(lambda: state.relations(kind, request.args.get("group", ""), request.args.get("q", "")))
    @app.post("/api/relations/<kind>")
    def api_set_relation(kind): return respond(lambda: (state.set_relation(kind, body()["id"], int(body()["value"])), {"message": "关系已在内存中修改。"})[1])
    @app.post("/api/save")
    def api_save(): return respond(lambda: {"message": state.save(body()["target"])})
    return app


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=8765); parser.add_argument("--no-browser", action="store_true"); args = parser.parse_args()
    if not 1024 <= args.port <= 65535: raise SystemExit("端口必须在 1024–65535 之间。")
    url = f"http://127.0.0.1:{args.port}"
    # Repeated launches reuse this application's server instead of leaving another process behind.
    from urllib.request import urlopen
    import json
    try:
        with urlopen(url + "/api/session/info", timeout=1) as response:
            existing = json.load(response)
        if existing.get("application") == "WulinSHSaveEditor" and existing.get("lifecycle") == 1:
            if not args.no_browser: webbrowser.open_new_tab(url)
            return
    except (OSError, ValueError):
        pass
    sessions = BrowserSessions()
    app = make_app(args.port, sessions)
    server = make_server("127.0.0.1", args.port, app, threaded=True)
    finished = threading.Event()
    def watch_pages():
        while not finished.wait(0.5):
            if sessions.should_stop():
                server.shutdown()
                return
    threading.Thread(target=watch_pages, daemon=True).start()
    if not args.no_browser: webbrowser.open_new_tab(url)
    try:
        server.serve_forever()
    finally:
        finished.set()
        server.server_close()


if __name__ == "__main__": main()
