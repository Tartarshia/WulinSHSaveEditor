import copy
import unittest

from web_app import EditorState
from game_data import consumable_group, read_localized_item_info, plain_game_text


class EditorStatsTests(unittest.TestCase):
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
        self.state.material_catalog = {8: {"rarity": 2, "group": "药材"}}
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
