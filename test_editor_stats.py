import copy
import unittest

from web_app import EditorState
from game_data import consumable_group, read_localized_item_info, plain_game_text, format_item_stat, stackable_other_group


class EditorStatsTests(unittest.TestCase):
    def test_other_stackable_classification_requires_explicit_flag(self):
        for flag in (True, "TRUE", " true ", 1):
            self.assertEqual(stackable_other_group("Misc_HidWep", "飞镖", "", flag), "暗器")
        for flag in (False, "FALSE", None, "", 0):
            self.assertIsNone(stackable_other_group("Misc_Quest", "铜钥匙", "钥匙", flag))
        self.assertEqual(stackable_other_group("Misc_Poison", "毒物", "", "TRUE"), "毒物")
        self.assertEqual(stackable_other_group("Misc", "杂物", "", "TRUE"), "杂项")
        for name, tags in (("铜钥匙", ""), ("藏宝密窟钥", ""), ("任务道具", "钥匙")):
            self.assertEqual(stackable_other_group("Misc_Quest", name, tags, "TRUE"), "钥匙")
        self.assertIsNone(stackable_other_group("Misc_Quest", "信件", "任务", "TRUE"))
        self.assertIsNone(stackable_other_group("None", "停用物品", "", "TRUE"))

    def test_other_stackable_subset_filters_and_quantity(self):
        self.state.item_catalog.update({10: ("铜钥匙", "任务物品"), 11: ("信件", "任务物品"), 12: ("不可堆叠杂物", "杂项")})
        self.state.other_stackable_catalog = {10: {"rarity": 1, "group": "钥匙"}}
        self.state.inventory.extend([{"m_templeteId": i, "m_stack": 1} for i in (10, 11, 12, 10)])
        original = copy.deepcopy(self.state.inventory)
        self.assertEqual([x["id"] for x in self.state.items()["items"]], [11, 12])
        self.assertEqual([x["id"] for x in self.state.items(include_other_stackable=True)["items"]], [10, 10, 11, 12])
        self.assertEqual([x["id"] for x in self.state.catalog("")], [11, 12])
        self.assertIn(10, [x["id"] for x in self.state.catalog("", include_other_stackable=True)])
        self.assertIn("任务物品", self.state.items()["categories"])
        self.assertEqual(self.state.inventory, original)
        self.assertEqual(self.state.inventory_group("other_stackable")["rows"][0]["count"], 2)
        self.state.set_inventory_group_count("other_stackable", 10, 999)
        self.assertEqual(self.state.inventory_group("other_stackable", status="owned")["rows"][0]["count"], 999)
        for rejected in (11, 12):
            with self.assertRaises(ValueError): self.state.set_inventory_group_count("other_stackable", rejected, 999)
        self.state.set_inventory_group_count("other_stackable", 10, 0)
        self.assertEqual(self.state.inventory_group("other_stackable", status="missing")["rows"][0]["count"], 0)
        self.assertEqual([x for x in self.state.inventory if x["m_templeteId"] in (11, 12)], original[4:6])

    def test_reserve_members_show_homestead_rooms_without_guessing_all_are_home(self):
        self.state.map_names = {502: "天工坊", 1100: "无名小村"}
        self.state.team["playerTeam"] = [100401]
        char = copy.deepcopy(self.state.hero)
        char.update({"m_templeteUid": 10092, "m_TeamMemberState": {"isJoined": True}, "m_curMapId": 502, "m_curPos": {"x": -2147483648, "y": -2147483648}})
        self.state.all_characters["10092"] = char
        before = copy.deepcopy(self.state.char_data)
        row = next(x for x in self.state.characters() if x["id"] == "10092")
        self.assertEqual(row["status"], "已入队，未出战")
        self.assertEqual(row["location"]["name"], "家园 · 天工坊")
        self.assertIsNone(row["location"]["pos"])
        self.assertEqual(self.state.character_detail("10092")["location"], row["location"])
        self.assertEqual(self.state.char_data, before)
        self.assertEqual(self.state.character_location({"m_curMapId": 500})["name"], "家园")
        self.assertEqual(self.state.character_location({"m_curMapId": 1100})["name"], "无名小村")
        self.state.team["playerTeam"].append(10092)
        self.assertIsNone(next(x for x in self.state.characters() if x["id"] == "10092")["location"])

    def test_max_life_abilities_sets_each_cap_and_clears_only_its_experience(self):
        self.state.life_catalog = {"能力_采集_采矿": 5, "能力_鉴定_字画": 3}
        self.state.hero["m_additionProps"].update({"能力_采集_采矿": 1, "能力经验_采集_采矿": 123.5, "能力经验_鉴定_字画": 77, "其他经验": 88})
        self.state.all_characters["10092"] = copy.deepcopy(self.state.hero)
        companion = copy.deepcopy(self.state.all_characters["10092"])
        before = copy.deepcopy(self.state.hero)
        self.assertEqual(self.state.max_life_abilities()["count"], 2)
        expected = copy.deepcopy(before)
        for key, maximum in self.state.life_catalog.items():
            expected["m_additionProps"][key] = maximum
            expected["m_additionProps"]["能力经验_" + key[len("能力_"):]] = 0
        self.assertEqual(self.state.hero, expected)
        self.assertEqual(self.state.all_characters["10092"], companion)
        self.state.max_life_abilities()
        self.assertEqual(self.state.hero, expected)
        self.state.life_catalog = {}
        with self.assertRaises(ValueError): self.state.max_life_abilities()
        self.assertEqual(self.state.hero, expected)

    def test_life_ability_listing_and_edit_target_only_hero(self):
        self.state.life_catalog = {"能力_采集_采矿": 5, "能力_鉴定_字画": 3}
        before = copy.deepcopy(self.state.char_data)
        rows = self.state.life_abilities()["abilities"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({x["category"] for x in rows}, {"采集", "鉴定"})
        self.assertEqual(self.state.char_data, before)
        self.state.all_characters["10092"] = copy.deepcopy(self.state.hero)
        companion = copy.deepcopy(self.state.all_characters["10092"])
        self.state.set_character("100401", {"kind": "life", "key": "能力_采集_采矿", "level": 5, "exp": 123.5})
        row = next(x for x in self.state.life_abilities()["abilities"] if x["name"] == "采矿")
        self.assertEqual((row["level"], row["exp"], row["max"]), (5, 123.5, 5))
        self.assertEqual(self.state.all_characters["10092"], companion)
        before = copy.deepcopy(self.state.char_data)
        for level, exp in [(6, 0), (-1, 0), (2, -1), (2, "nan"), (2, "inf")]:
            with self.assertRaises(ValueError): self.state.set_character("100401", {"kind": "life", "key": "能力_采集_采矿", "level": level, "exp": exp})
            self.assertEqual(self.state.char_data, before)
        with self.assertRaises(ValueError): self.state.set_character("10092", {"kind": "life", "key": "能力_采集_采矿", "level": 1, "exp": 0})
        with self.assertRaises(ValueError): self.state.set_character("100401", {"kind": "life", "key": "能力_未知", "level": 1, "exp": 0})

    def test_life_save_uses_character_file_and_backup(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as folder:
            self.state.save_root = Path(folder)
            self.state.slot = "SyntheticSlot"
            with patch("web_app.shutil.copytree") as backup, patch("web_app.es3_codec.atomic_write") as write:
                self.state.save("life")
                backup.assert_called_once()
                write.assert_called_once_with(Path(folder) / "SyntheticSlot" / "SaveObjectGameCharacter.save", self.state.char_data)

    def test_experience_books_shortcut_sets_all_to_999_without_touching_other_items(self):
        self.state.item_catalog.update({4: ("测试经验书甲", "消耗品"), 5: ("测试经验书乙", "消耗品")})
        self.state.consumable_catalog.update({4: {"group": "经验书"}, 5: {"group": "经验书"}})
        self.state.inventory.extend([{"m_templeteId": 4, "m_stack": 2000, "modifyData": {"test": 1}}, {"m_templeteId": 4, "m_stack": 7}])
        unrelated = copy.deepcopy([x for x in self.state.inventory if x["m_templeteId"] != 4])
        result = self.state.set_experience_books_999()
        self.assertEqual(result["count"], 2)
        for item_id in (4, 5):
            records = [x for x in self.state.inventory if x["m_templeteId"] == item_id]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["m_stack"], 999)
        self.assertEqual(next(x for x in self.state.inventory if x["m_templeteId"] == 4)["modifyData"], {"test": 1})
        self.assertEqual([x for x in self.state.inventory if x["m_templeteId"] not in (4, 5)], unrelated)
        before = copy.deepcopy(self.state.inventory)
        self.state.set_experience_books_999()
        self.assertEqual(self.state.inventory, before)

    def test_experience_books_shortcut_validates_catalog_before_mutating(self):
        before = copy.deepcopy(self.state.inventory)
        with self.assertRaises(ValueError): self.state.set_experience_books_999()
        self.state.consumable_catalog.update({3: {"group": "经验书"}, 8: {"group": "经验书"}})
        with self.assertRaises(ValueError): self.state.set_experience_books_999()
        self.assertEqual(self.state.inventory, before)

    def test_effects_use_localized_names_and_preserve_sign_and_units(self):
        names = {"B_NegBlind": "致盲", "B_NegPoison": "中毒", "生命": "生命上限"}
        self.assertEqual(format_item_stat("D_Hp|2000", names, True), "气血恢复 2000")
        self.assertEqual(format_item_stat("B_NegBlind|-100", names, True), "致盲 -100")
        self.assertEqual(format_item_stat("B_BattleMedicine|1", names, True), "吃药次数 +1")
        self.assertEqual(format_item_stat("D_Ep%|1", names, True), "内力恢复 100%")
        self.assertEqual(format_item_stat("D_Hp%|0.15", names, True), "气血恢复 15%")
        self.assertEqual(format_item_stat("B_NegPoison|5", names, True), "中毒 +5")
        self.assertEqual(format_item_stat("生命|100", names), "生命上限 +100")
        self.assertEqual(format_item_stat("能力经验_采集_采矿|100", names, True), "采矿经验 +100")
        self.assertEqual(format_item_stat("B_NegBlind<100", names), "致盲<100")
        self.assertIn("未识别属性", format_item_stat("B_Unknown|1", names, True))

    def test_departed_location_uses_saved_current_map_not_leave_or_respawn(self):
        self.state.map_names = {1: "测试当前地图", 2: "测试离队地图"}
        char = {"m_curMapId": 1, "m_curPos": {"x": 3, "y": 4}, "m_RespawnMap": 999, "m_TeamMemberState": {"isJoined": False, "leaveTeamMap": 2}}
        original = copy.deepcopy(char)
        location = self.state.character_location(char)
        self.assertEqual(location["name"], "测试当前地图")
        self.assertEqual(location["source"], "存档所在地")
        self.assertEqual(location["pos"], {"x": 3, "y": 4})
        self.assertEqual(char, original)
        char["m_curMapId"] = 0
        self.assertEqual(self.state.character_location(char)["source"], "上次离队地点")
        self.assertEqual(self.state.character_location({"m_curMapId": 999})["name"], "未知地图 999")
        self.assertIsNone(self.state.character_location({})["map_id"])
        char["m_isAlive"] = False
        self.assertIn("已死亡", self.state.character_location(char)["source"])

    def test_description_reader_uses_validated_simplified_chinese_fields(self):
        import struct
        def string(value): return b"\x01" + struct.pack("<i", len(value)) + value.encode("utf-16-le")
        key = b"\x27" + string("UName")
        chinese = b"\x27" + string("SChinese")
        raw = key + string("ItemInfo_测试") + chinese + string("<#d09a09>用途：服用</color>\\n第二行")
        self.assertEqual(read_localized_item_info(raw), {"测试": "用途：服用\n第二行"})
        with self.assertRaises(ValueError): read_localized_item_info(b"invalid")
        self.assertEqual(plain_game_text("毒术<100"), "毒术<100")

    def test_descriptions_are_present_across_inventory_apis(self):
        self.state.item_descriptions = {1: "秘籍说明", 3: "药品说明"}
        self.assertEqual(self.state.items(include_books=True)["items"][0]["description"], "秘籍说明")
        self.assertEqual(self.state.catalog("", include_books=True)[0]["description"], "秘籍说明")
        self.assertEqual(self.state.consumables()["consumables"][0]["description"], "药品说明")
        self.assertIn("暂无", self.state.item_description(999))

    def test_experience_books_are_not_food(self):
        self.assertEqual(consumable_group("Consumeable_Edible_Meal", "典籍", "食物与酒水"), "经验书")
        self.assertEqual(consumable_group("Consumeable_Edible_Meal", "其他, 典籍", "食物与酒水"), "经验书")
        self.assertEqual(consumable_group("Consumeable_Edible_Meal", "食物,主食", "食物与酒水"), "食物与酒水")
        self.assertEqual(consumable_group("Consumeable_Special", "书籍", "特殊消耗品"), "特殊消耗品")

    def setUp(self):
        self.state = EditorState.__new__(EditorState)
        self.state.team_data = {"Data": {"value": {"playerTeamInventory": {"contents": [
            {"m_templeteId": 1, "m_stack": 1}, {"m_templeteId": 2, "m_stack": 2}, {"m_templeteId": 3, "m_stack": 5}]}}}}
        self.state.item_catalog = {1: ("测试秘籍", "武功秘籍"), 2: ("测试配方", "配方"), 3: ("测试药品", "消耗品")}
        self.state.main_prop_growth = {"max": 10, "exp_to_next": {level: level * 50 for level in range(10)}}
        self.state.character_names = {}
        self.state.book_catalog = {}
        self.state.consumable_catalog = {3: {"rarity": 1, "group": "药品"}}
        self.state.life_catalog = {}
        self.state.material_catalog = {8: {"rarity": 2, "group": "药材"}}
        self.state.other_stackable_catalog = {}
        self.state.treasure_catalog = {9: {"rarity": 3, "group": "古董"}}
        self.state.time_data = {"Data": {"value": {}}}
        self.state.char_data = {"Data": {"value": {"createdCharacter": {"100401": {
            "m_originProps": {"臂力": 5, "仁德": 10}, "m_additionProps": {"臂力": 6, "臂力经验": 42, "仁德": 20}}}}}}

    def test_innate_edits_preserve_bonus_and_unrelated_fields(self):
        self.state.set_character("100401", {"kind": "innate", "key": "臂力", "level": 10, "exp": 100.5})
        self.assertEqual(self.state.hero["m_originProps"]["臂力"], 10)
        self.assertEqual(self.state.hero["m_additionProps"]["臂力"], 6)
        self.assertEqual(self.state.hero["m_additionProps"]["臂力经验"], 100.5)
        self.assertEqual(self.state.hero["m_additionProps"]["仁德"], 20)

    def test_invalid_growth_edit_does_not_mutate(self):
        original = copy.deepcopy(self.state.char_data)
        for level, exp in ((11, 0), (0, 0), (10, -1), (10, "nan")):
            with self.assertRaises(ValueError):
                self.state.set_character("100401", {"kind": "innate", "key": "臂力", "level": level, "exp": exp})
            self.assertEqual(self.state.char_data, original)

    def test_max_innate_targets_only_selected_character(self):
        other = copy.deepcopy(self.state.hero)
        self.state.all_characters["10092"] = other
        other_before = copy.deepcopy(other)
        addition_before = copy.deepcopy(self.state.hero["m_additionProps"])
        self.state.set_character("100401", {"kind": "innate_max"})
        for key in ("体质", "臂力", "敏捷", "悟性", "福缘"):
            self.assertEqual(self.state.hero["m_originProps"][key], 10)
        self.assertEqual(self.state.hero["m_additionProps"], addition_before)
        self.assertEqual(self.state.hero["m_originProps"]["仁德"], 10)
        self.assertEqual(other, other_before)

    def test_moral_total_edit_preserves_origin(self):
        self.state.set_character("100401", {"kind": "moral", "key": "仁德", "value": 100})
        self.assertEqual(self.state.hero["m_originProps"]["仁德"], 10)
        self.assertEqual(self.state.hero["m_additionProps"]["仁德"], 90)

    def test_companion_cannot_edit_moral_stats(self):
        self.state.all_characters["10092"] = copy.deepcopy(self.state.hero)
        original = copy.deepcopy(self.state.char_data)
        with self.assertRaisesRegex(ValueError, "仅属于主角"):
            self.state.set_character("10092", {"kind": "moral", "key": "仁德", "value": 100})
        self.assertEqual(self.state.char_data, original)

    def test_inventory_toggles_filter_without_deleting(self):
        self.state.item_catalog[8] = ("测试材料", "材料")
        self.state.inventory.append({"m_templeteId": 8, "m_stack": 1})
        original = copy.deepcopy(self.state.inventory)
        self.assertEqual([row["id"] for row in self.state.items()["items"]], [])
        self.assertEqual([row["id"] for row in self.state.items(include_books=True)["items"]], [1])
        self.assertEqual([row["id"] for row in self.state.items(include_recipes=True)["items"]], [2])
        self.assertEqual([row["id"] for row in self.state.items(include_books=True, include_recipes=True)["items"]], [1, 2])
        self.assertEqual([row["id"] for row in self.state.items(include_consumables=True)["items"]], [3])
        self.assertEqual([row["id"] for row in self.state.items(include_materials=True)["items"]], [8])
        self.assertEqual([row["id"] for row in self.state.catalog("")], [])
        self.assertEqual([row["id"] for row in self.state.catalog("", include_materials=True)], [8])
        self.assertEqual(self.state.inventory, original)

    def test_materials_and_treasures_quantity_and_filters(self):
        self.state.item_catalog.update({8: ("测试药材", "材料"), 9: ("测试古董", "珍宝")})
        self.assertEqual(self.state.inventory_group("materials", status="missing")["rows"][0]["count"], 0)
        self.state.set_inventory_group_count("materials", 8, 5)
        self.assertEqual(self.state.inventory_group("materials", status="owned")["rows"][0]["count"], 5)
        self.assertEqual(self.state.inventory_group("materials", status="missing")["rows"], [])
        self.state.set_inventory_group_count("treasures", 9, 2)
        self.assertEqual([x["id"] for x in self.state.items(include_treasures=True)["items"]], [9])
        self.state.set_inventory_group_count("materials", 8, 0)
        with self.assertRaises(ValueError): self.state.set_inventory_group_count("treasures", 8, 1)
        with self.assertRaises(ValueError): self.state.set_inventory_group_count("materials", 8, -1)
        self.assertEqual(self.state.inventory_group("treasures")["rows"][0]["count"], 2)

    def test_consumable_quantity_is_total_and_zero_removes(self):
        self.state.inventory.append({"m_templeteId": 3, "m_stack": 7})
        self.assertEqual(self.state.consumables()["consumables"][0]["count"], 12)
        self.state.set_consumable_count(3, 20)
        self.assertEqual(self.state.consumables()["consumables"][0]["count"], 20)
        self.state.set_consumable_count(3, 0)
        self.assertEqual(self.state.consumables()["consumables"][0]["count"], 0)
        self.state.set_consumable_count(3, 4)
        self.assertEqual(self.state.consumables()["consumables"][0]["count"], 4)
        with self.assertRaises(ValueError): self.state.set_consumable_count(1, 4)
        with self.assertRaises(ValueError): self.state.set_consumable_count(3, -1)

    def test_books_count_current_members_equipment_and_personal_bags(self):
        self.state.item_catalog.update({4: ("装备秘籍", "武功秘籍"), 5: ("随身秘籍", "武功秘籍"), 6: ("未拥有秘籍", "武功秘籍"), 7: ("离队秘籍", "武功秘籍")})
        self.state.team["playerTeam"] = [100401, 10092]
        self.state.all_characters["10092"] = {"m_givenName": "测试队友", "equipSlot": {"book": {"m_templeteId": 4, "m_stack": 1}, "empty": None}, "backPack": {"contents": [{"m_templeteId": 5, "m_stack": 1}]}}
        self.state.all_characters["10093"] = {"equipSlot": {"book": {"m_templeteId": 7, "m_stack": 1}}}
        rows = {row["id"]: row for row in self.state.books()["books"]}
        self.assertTrue(rows[4]["owned"])
        self.assertTrue(rows[5]["owned"])
        self.assertFalse(rows[7]["owned"])
        original = copy.deepcopy(self.state.inventory)
        self.state.set_book_owned(4, True)
        self.assertEqual(self.state.inventory, original)
        with self.assertRaises(ValueError): self.state.set_book_owned(4, False)
        self.state.set_global("books")
        ids = [item["m_templeteId"] for item in self.state.inventory]
        self.assertNotIn(4, ids)
        self.assertNotIn(5, ids)
        self.assertIn(6, ids)
        again = copy.deepcopy(self.state.inventory)
        self.state.set_global("books")
        self.assertEqual(self.state.inventory, again)


if __name__ == "__main__":
    unittest.main()
