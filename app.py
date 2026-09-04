from __future__ import annotations

import shutil
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import es3_codec
from game_data import load_character_names, load_faction_names, load_item_catalog, load_job_factions, load_kungfu_catalog
from paths import discover_game_roots, discover_save_roots, is_game_root, is_save_root, load_preferences, save_preferences

TEAM_FILE = "SaveObjectPlayerTeam.save"
CHAR_FILE = "SaveObjectGameCharacter.save"
FACTION_FILE = "SaveObjectFaction.save"
class Editor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("大侠立志传：本地存档修改器")
        self.geometry("1050x680")
        preferences = load_preferences()
        configured_game = Path(preferences["game_root"]) if preferences.get("game_root") else None
        configured_save = Path(preferences["save_root"]) if preferences.get("save_root") else None
        self.game_root = configured_game if configured_game and is_game_root(configured_game) else next(iter(discover_game_roots()), None)
        self.root_path = configured_save if configured_save and is_save_root(configured_save) else next(iter(discover_save_roots()), None)
        self.slot = tk.StringVar()
        self.item_id = tk.StringVar()
        self.item_qty = tk.StringVar(value="1")
        self.item_filter = tk.StringVar()
        self.catalog_filter = tk.StringVar()
        self.item_category_filter = tk.StringVar(value="全部")
        self.item_sort = tk.StringVar(value="道具 ID 升序")
        self.item_names: dict[int, str] = {}
        self.item_categories: dict[int, str] = {}
        self.character_names: dict[int, str] = {}
        self.faction_names: dict[int, str] = {}
        self.job_factions: dict[int, str] = {}
        self.kungfu_catalog: dict[int, tuple[str, int]] = {}
        self.hero_current_name = ""
        self.team_data = None
        self.char_data = None
        self.faction_data = None
        self.inventory = None
        self.all_characters: dict[str, dict] = {}
        self.characters: dict[str, dict] = {}
        self.character_status: dict[str, str] = {}
        self.character_level = tk.StringVar(); self.character_exp = tk.StringVar()
        self.ability_level = tk.StringVar(); self.ability_exp = tk.StringVar()
        self._build()
        self.reload_slots()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=10); top.pack(fill="x")
        game_row = ttk.Frame(top); game_row.pack(fill="x", pady=(0, 4))
        save_row = ttk.Frame(top); save_row.pack(fill="x")
        self.game_path_label = tk.StringVar(); self.save_path_label = tk.StringVar()
        ttk.Label(game_row, text="游戏目录：").pack(side="left")
        ttk.Label(game_row, textvariable=self.game_path_label, width=78, anchor="w").pack(side="left", padx=(0, 8))
        ttk.Button(game_row, text="选择游戏目录", command=self.choose_game_root).pack(side="left")
        ttk.Label(save_row, text="存档目录：").pack(side="left")
        ttk.Label(save_row, textvariable=self.save_path_label, width=52, anchor="w").pack(side="left", padx=(0, 8))
        ttk.Button(save_row, text="选择存档目录", command=self.choose_save_root).pack(side="left")
        ttk.Label(save_row, text="存档槽").pack(side="left", padx=(12, 2))
        self.slots = ttk.Combobox(save_row, textvariable=self.slot, width=14, state="readonly")
        self.slots.pack(side="left")
        ttk.Button(save_row, text="读取存档", command=self.load_slot).pack(side="left", padx=6)

        notebook = ttk.Notebook(self); notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        item_tab = ttk.Frame(notebook, padding=10); char_tab = ttk.Frame(notebook, padding=10)
        relation_tab = ttk.Frame(notebook, padding=10)
        notebook.add(item_tab, text="物品栏：数量 / 添加")
        notebook.add(char_tab, text="队友：属性")
        notebook.add(relation_tab, text="关系：NPC / 势力")
        self._items(item_tab); self._characters(char_tab); self._relations(relation_tab)
        self.status = tk.StringVar(value="请选择一个手动存档或快速存档，再读取。")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(10, 0, 10, 10)).pack(fill="x")
        self.update_path_label()

    def _items(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent); controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="道具 ID").pack(side="left")
        ttk.Entry(controls, textvariable=self.item_id, width=12).pack(side="left", padx=(4, 12))
        ttk.Label(controls, text="数量").pack(side="left")
        ttk.Entry(controls, textvariable=self.item_qty, width=10).pack(side="left", padx=4)
        ttk.Button(controls, text="添加 / 改为此数量", command=self.set_item).pack(side="left", padx=8)
        ttk.Button(controls, text="删除选中道具", command=self.remove_item).pack(side="left")
        ttk.Button(controls, text="保存物品栏", command=lambda: self.save("items")).pack(side="right")
        search = ttk.Frame(parent); search.pack(fill="x", pady=(0, 6))
        ttk.Label(search, text="背包筛选").pack(side="left")
        filter_box = ttk.Entry(search, textvariable=self.item_filter, width=35); filter_box.pack(side="left", padx=4)
        filter_box.bind("<KeyRelease>", lambda _event: self.refresh_items())
        ttk.Button(search, text="清除", command=lambda: (self.item_filter.set(""), self.refresh_items())).pack(side="left")
        ttk.Label(search, text="分类").pack(side="left", padx=(14, 0))
        self.category_box = ttk.Combobox(search, textvariable=self.item_category_filter, width=11, state="readonly")
        self.category_box.pack(side="left", padx=4); self.category_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_items())
        ttk.Label(search, text="排序").pack(side="left", padx=(8, 0))
        sort_box = ttk.Combobox(search, textvariable=self.item_sort, values=("道具 ID 升序", "道具 ID 降序", "名称排序"), width=13, state="readonly")
        sort_box.pack(side="left", padx=4); sort_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_items())

        item_box = ttk.Frame(parent); item_box.pack(fill="both", expand=True)
        self.item_tree = ttk.Treeview(item_box, columns=("id", "name", "category", "count", "modified"), show="headings", selectmode="browse")
        for col, label, width in (("id", "道具 ID", 100), ("name", "名称", 200), ("category", "分类", 90), ("count", "数量", 80), ("modified", "随机属性", 180)):
            self.item_tree.heading(col, text=label); self.item_tree.column(col, width=width, anchor="w")
        item_scroll = ttk.Scrollbar(item_box, orient="vertical", command=self.item_tree.yview)
        self.item_tree.configure(yscrollcommand=item_scroll.set)
        self.item_tree.pack(side="left", fill="both", expand=True); item_scroll.pack(side="right", fill="y")
        self.item_tree.bind("<<TreeviewSelect>>", self.pick_item)
        self.item_tree.bind("<Double-1>", self.pick_item)

        catalog_label = ttk.Frame(parent); catalog_label.pack(fill="x", pady=(8, 2))
        ttk.Label(catalog_label, text="游戏物品目录（选中后会带入上方道具 ID）").pack(side="left")
        catalog_box = ttk.Entry(catalog_label, textvariable=self.catalog_filter, width=35); catalog_box.pack(side="left", padx=6)
        catalog_box.bind("<KeyRelease>", lambda _event: self.refresh_catalog())
        self.catalog_tree = ttk.Treeview(parent, columns=("id", "name"), show="headings", height=7, selectmode="browse")
        self.catalog_tree.heading("id", text="道具 ID"); self.catalog_tree.heading("name", text="名称")
        self.catalog_tree.column("id", width=100); self.catalog_tree.column("name", width=300)
        catalog_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.catalog_tree.yview)
        self.catalog_tree.configure(yscrollcommand=catalog_scroll.set)
        self.catalog_tree.pack(side="left", fill="x", expand=True); catalog_scroll.pack(side="right", fill="y")
        self.catalog_tree.bind("<<TreeviewSelect>>", self.pick_catalog)

    def _characters(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent); left.pack(side="left", fill="y")
        self.char_tree = ttk.Treeview(left, columns=("name", "status", "id", "level"), show="headings", height=24)
        self.char_tree.heading("name", text="角色"); self.char_tree.heading("status", text="队伍状态"); self.char_tree.heading("id", text="角色 ID"); self.char_tree.heading("level", text="等级")
        self.char_tree.column("name", width=140); self.char_tree.column("status", width=115); self.char_tree.column("id", width=90); self.char_tree.column("level", width=55)
        self.char_tree.pack(fill="y")
        self.char_tree.bind("<<TreeviewSelect>>", self.show_props)
        right = ttk.Frame(parent); right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        ttk.Label(right, text="包含出战、已入队未出战和曾入队已离队角色；仅修改基础属性，不碰剧情状态、好感、任务或成就。").pack(anchor="w")
        self.prop_tree = ttk.Treeview(right, columns=("name", "value"), show="headings")
        self.prop_tree.heading("name", text="属性"); self.prop_tree.heading("value", text="数值")
        self.prop_tree.column("name", width=350); self.prop_tree.column("value", width=120)
        self.prop_tree.pack(fill="both", expand=True, pady=8)
        bar = ttk.Frame(right); bar.pack(fill="x")
        ttk.Label(bar, text="新数值").pack(side="left")
        self.prop_value = tk.StringVar(); ttk.Entry(bar, textvariable=self.prop_value, width=12).pack(side="left", padx=4)
        ttk.Button(bar, text="修改选中属性", command=self.set_prop).pack(side="left", padx=4)
        ttk.Button(bar, text="保存角色属性", command=lambda: self.save("characters")).pack(side="right")
        ttk.Separator(right).pack(fill="x", pady=8)
        level_bar = ttk.Frame(right); level_bar.pack(fill="x")
        ttk.Label(level_bar, text="角色等级").pack(side="left")
        ttk.Entry(level_bar, textvariable=self.character_level, width=7).pack(side="left", padx=4)
        ttk.Label(level_bar, text="经验").pack(side="left", padx=(8, 0))
        ttk.Entry(level_bar, textvariable=self.character_exp, width=12).pack(side="left", padx=4)
        ttk.Button(level_bar, text="修改角色等级/经验", command=self.set_character_level).pack(side="left", padx=4)
        ttk.Label(right, text="已学能力 / 武功（等级受游戏数据表中的最大等级限制）").pack(anchor="w", pady=(6, 0))
        ability_box = ttk.Frame(right); ability_box.pack(fill="both", expand=True)
        self.ability_tree = ttk.Treeview(ability_box, columns=("name", "id", "level", "max", "exp"), show="headings", height=7, selectmode="browse")
        for column, label, width in (("name", "能力 / 武功", 200), ("id", "ID", 80), ("level", "等级", 55), ("max", "上限", 55), ("exp", "经验", 90)):
            self.ability_tree.heading(column, text=label); self.ability_tree.column(column, width=width)
        ability_scroll = ttk.Scrollbar(ability_box, orient="vertical", command=self.ability_tree.yview)
        self.ability_tree.configure(yscrollcommand=ability_scroll.set)
        self.ability_tree.pack(side="left", fill="both", expand=True); ability_scroll.pack(side="right", fill="y")
        self.ability_tree.bind("<<TreeviewSelect>>", self.pick_ability)
        ability_bar = ttk.Frame(right); ability_bar.pack(fill="x", pady=(4, 0))
        ttk.Label(ability_bar, text="等级").pack(side="left")
        ttk.Entry(ability_bar, textvariable=self.ability_level, width=7).pack(side="left", padx=4)
        ttk.Label(ability_bar, text="经验").pack(side="left", padx=(8, 0))
        ttk.Entry(ability_bar, textvariable=self.ability_exp, width=12).pack(side="left", padx=4)
        ttk.Button(ability_bar, text="修改选中能力", command=self.set_ability).pack(side="left", padx=4)

    def _relations(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent); notebook.pack(fill="both", expand=True)
        npc_tab = ttk.Frame(notebook, padding=10); faction_tab = ttk.Frame(notebook, padding=10)
        notebook.add(npc_tab, text="NPC 关系")
        notebook.add(faction_tab, text="势力关系")

        self.npc_filter = tk.StringVar(); self.npc_value = tk.StringVar()
        npc_bar = ttk.Frame(npc_tab); npc_bar.pack(fill="x", pady=(0, 8))
        self.npc_group = tk.StringVar(value="请选择势力")
        ttk.Label(npc_bar, text="势力 / 城镇").pack(side="left")
        self.npc_group_box = ttk.Combobox(npc_bar, textvariable=self.npc_group, width=23, state="readonly")
        self.npc_group_box.pack(side="left", padx=4)
        self.npc_group_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_npc_relations())
        ttk.Label(npc_bar, text="搜索 NPC").pack(side="left")
        npc_search = ttk.Entry(npc_bar, textvariable=self.npc_filter, width=35); npc_search.pack(side="left", padx=4)
        npc_search.bind("<KeyRelease>", lambda _event: self.refresh_npc_relations())
        ttk.Label(npc_bar, text="关系值（-100 至 100）").pack(side="left", padx=(14, 0))
        ttk.Entry(npc_bar, textvariable=self.npc_value, width=10).pack(side="left", padx=4)
        ttk.Button(npc_bar, text="修改选中 NPC", command=self.set_npc_relation).pack(side="left", padx=4)
        ttk.Button(npc_bar, text="保存 NPC 关系", command=lambda: self.save("relations")).pack(side="right")
        npc_box = ttk.Frame(npc_tab); npc_box.pack(fill="both", expand=True)
        self.npc_tree = ttk.Treeview(npc_box, columns=("name", "id", "value"), show="headings", selectmode="browse")
        for column, label, width in (("name", "NPC", 330), ("id", "角色 ID", 130), ("value", "关系", 100)):
            self.npc_tree.heading(column, text=label); self.npc_tree.column(column, width=width)
        npc_scroll = ttk.Scrollbar(npc_box, orient="vertical", command=self.npc_tree.yview)
        self.npc_tree.configure(yscrollcommand=npc_scroll.set)
        self.npc_tree.pack(side="left", fill="both", expand=True); npc_scroll.pack(side="right", fill="y")
        self.npc_tree.bind("<<TreeviewSelect>>", self.pick_npc_relation)

        self.faction_filter = tk.StringVar(); self.faction_value = tk.StringVar()
        faction_bar = ttk.Frame(faction_tab); faction_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(faction_bar, text="搜索势力").pack(side="left")
        faction_search = ttk.Entry(faction_bar, textvariable=self.faction_filter, width=35); faction_search.pack(side="left", padx=4)
        faction_search.bind("<KeyRelease>", lambda _event: self.refresh_factions())
        ttk.Label(faction_bar, text="关系值（-100 至 100）").pack(side="left", padx=(14, 0))
        ttk.Entry(faction_bar, textvariable=self.faction_value, width=10).pack(side="left", padx=4)
        ttk.Button(faction_bar, text="修改选中势力", command=self.set_faction_relation).pack(side="left", padx=4)
        ttk.Button(faction_bar, text="保存势力关系", command=lambda: self.save("faction")).pack(side="right")
        faction_box = ttk.Frame(faction_tab); faction_box.pack(fill="both", expand=True)
        self.faction_tree = ttk.Treeview(faction_box, columns=("name", "id", "value"), show="headings", selectmode="browse")
        for column, label, width in (("name", "势力", 330), ("id", "势力 ID", 130), ("value", "关系", 100)):
            self.faction_tree.heading(column, text=label); self.faction_tree.column(column, width=width)
        faction_scroll = ttk.Scrollbar(faction_box, orient="vertical", command=self.faction_tree.yview)
        self.faction_tree.configure(yscrollcommand=faction_scroll.set)
        self.faction_tree.pack(side="left", fill="both", expand=True); faction_scroll.pack(side="right", fill="y")
        self.faction_tree.bind("<<TreeviewSelect>>", self.pick_faction_relation)

    def reload_slots(self) -> None:
        if self.root_path is None:
            self.slots["values"] = []
            self.slot.set("")
            return
        allowed = [p.name for p in self.root_path.iterdir() if p.is_dir() and (p.name.startswith("Save") or p.name.startswith("QuickSave")) and (p / TEAM_FILE).exists()]
        self.slots["values"] = sorted(allowed)
        if allowed: self.slot.set("Save0" if "Save0" in allowed else allowed[0])

    def update_path_label(self) -> None:
        game = str(self.game_root) if self.game_root else "未找到"
        save = str(self.root_path) if self.root_path else "未找到"
        self.game_path_label.set(game)
        self.save_path_label.set(save)

    def choose_save_root(self) -> None:
        chosen = filedialog.askdirectory(title="选择存档根目录（包含 Save0、QuickSave0 等文件夹）", initialdir=str(self.root_path or Path.home()))
        if not chosen:
            return
        path = Path(chosen)
        if not is_save_root(path):
            return messagebox.showerror("目录不正确", "请选择直接包含 Save0 / QuickSave0 文件夹的存档根目录。")
        self.root_path = path
        save_preferences(self.game_root, self.root_path)
        self.update_path_label(); self.reload_slots()

    def choose_game_root(self) -> None:
        chosen = filedialog.askdirectory(title="选择游戏安装目录（包含 Wulin.exe）", initialdir=str(self.game_root or Path.home()))
        if not chosen:
            return
        path = Path(chosen)
        if not is_game_root(path):
            return messagebox.showerror("目录不正确", "请选择包含 Wulin.exe 和 Wulin_Data 的游戏安装目录。")
        self.game_root = path
        self.item_names = {}; self.item_categories = {}; self.character_names = {}
        save_preferences(self.game_root, self.root_path)
        self.update_path_label()

    def load_slot(self) -> None:
        try:
            if self.root_path is None:
                raise FileNotFoundError("未找到存档目录；请点击“选择存档目录”。")
            if self.game_root is None:
                raise FileNotFoundError("未找到游戏目录；请点击“选择游戏目录”。")
            folder = self.root_path / self.slot.get()
            self.team_data = es3_codec.load(folder / TEAM_FILE)
            self.char_data = es3_codec.load(folder / CHAR_FILE)
            self.faction_data = es3_codec.load(folder / FACTION_FILE)
            team = self.team_data["Data"]["value"]
            self.inventory = team["playerTeamInventory"]["contents"]
            if not self.item_names:
                catalog = load_item_catalog(self.game_root)
                self.item_names = {item_id: value[0] for item_id, value in catalog.items()}
                self.item_categories = {item_id: value[1] for item_id, value in catalog.items()}
                self.category_box["values"] = ["全部", *sorted(set(self.item_categories.values()))]
            if not self.character_names:
                self.character_names = load_character_names(self.game_root)
            if not self.faction_names:
                self.faction_names = load_faction_names(self.game_root)
            if not self.job_factions:
                self.job_factions = load_job_factions(self.game_root)
            if not self.kungfu_catalog:
                self.kungfu_catalog = load_kungfu_catalog(self.game_root)
            all_characters = self.char_data["Data"]["value"]["createdCharacter"]
            self.all_characters = all_characters
            hero = all_characters.get("100401", {})
            self.hero_current_name = (hero.get("m_surName") or "") + (hero.get("m_givenName") or "")
            active_ids = {str(i) for i in team["playerTeam"]}
            self.characters = {}
            self.character_status = {}
            for character_id, character in all_characters.items():
                member_state = character.get("m_TeamMemberState")
                if character_id in active_ids or isinstance(member_state, dict):
                    self.characters[character_id] = character
                    self.character_status[character_id] = ("出战中" if character_id in active_ids else ("已入队，未出战" if member_state.get("isJoined") else "曾入队，现已离队"))
            self.refresh_items(); self.refresh_characters(); self.refresh_npc_relations(); self.refresh_factions()
            self.status.set(f"已读取 {self.slot.get()}：{len(self.inventory)} 个物品，{len(self.characters)} 名当前或曾经入队角色；已载入官方物品和角色名称。")
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))

    def refresh_items(self) -> None:
        self.item_tree.delete(*self.item_tree.get_children())
        needle = self.item_filter.get().strip().casefold()
        rows = []
        for i, item in enumerate(self.inventory or []):
            item_id = item.get("m_templeteId")
            name = self.item_names.get(item_id, "（未在官方物品表找到）")
            category = self.item_categories.get(item_id, "未分类")
            if needle and needle not in str(item_id) and needle not in name.casefold():
                continue
            if self.item_category_filter.get() != "全部" and category != self.item_category_filter.get():
                continue
            rows.append((i, item_id, name, category, item))
        if self.item_sort.get() == "道具 ID 升序":
            rows.sort(key=lambda row: row[1])
        elif self.item_sort.get() == "道具 ID 降序":
            rows.sort(key=lambda row: row[1], reverse=True)
        else:
            rows.sort(key=lambda row: row[2])
        for i, item_id, name, category, item in rows:
            self.item_tree.insert("", "end", iid=str(i), values=(item_id, name, category, item.get("m_stack"), "有" if item.get("modifyData") else "无"))
        self.refresh_catalog()

    def refresh_catalog(self) -> None:
        if not hasattr(self, "catalog_tree"):
            return
        self.catalog_tree.delete(*self.catalog_tree.get_children())
        needle = self.catalog_filter.get().strip().casefold()
        matches = ((item_id, name) for item_id, name in self.item_names.items() if not needle or needle in str(item_id) or needle in name.casefold())
        for item_id, name in list(matches)[:300]:
            self.catalog_tree.insert("", "end", iid=f"catalog-{item_id}", values=(item_id, name))

    def pick_catalog(self, _=None) -> None:
        selection = self.catalog_tree.selection()
        if selection:
            self.item_id.set(str(self.catalog_tree.item(selection[0], "values")[0]))

    def pick_item(self, _=None) -> None:
        selection = self.item_tree.selection()
        if selection:
            item = self.inventory[int(selection[0])]
            self.item_id.set(str(item["m_templeteId"])); self.item_qty.set(str(item["m_stack"]))

    def set_item(self) -> None:
        if self.inventory is None: return messagebox.showwarning("尚未读取", "请先读取存档。")
        try: item_id, qty = int(self.item_id.get()), int(self.item_qty.get())
        except ValueError: return messagebox.showwarning("输入错误", "道具 ID 和数量必须是整数。")
        if item_id <= 0 or not 0 < qty <= 999999: return messagebox.showwarning("输入错误", "ID 必须大于 0，数量范围为 1–999999。")
        for item in self.inventory:
            if item.get("m_templeteId") == item_id:
                item["m_stack"] = qty; break
        else:
            self.inventory.append({"m_templeteId": item_id, "m_stack": qty, "modifyData": None, "IsNew": False, "IsForbidden": False})
        self.refresh_items(); self.status.set("物品栏已在内存中修改；点击“保存物品栏”才会写入磁盘。")

    def remove_item(self) -> None:
        sel = self.item_tree.selection()
        if not sel: return
        del self.inventory[int(sel[0])]; self.refresh_items()

    def refresh_characters(self) -> None:
        self.char_tree.delete(*self.char_tree.get_children())
        for cid, character in self.characters.items():
            name = self.display_name(character)
            self.char_tree.insert("", "end", iid=cid, values=(name, self.character_status.get(cid, "未知"), cid, character.get("m_level", 0)))

    def display_name(self, character: dict) -> str:
        """Use save names, while retaining a template suffix such as '心魔'."""
        template_id = character.get("m_templeteUid")
        saved_name = (character.get("m_surName") or "") + (character.get("m_givenName") or "")
        template_name = self.character_names.get(template_id, "")
        hero_template_name = self.character_names.get(100401, "")
        if saved_name and self.hero_current_name and template_name.startswith(hero_template_name) and saved_name == self.hero_current_name:
            return saved_name + template_name[len(hero_template_name):]
        return saved_name or template_name or f"未知角色 {template_id}"

    def show_props(self, _=None) -> None:
        self.prop_tree.delete(*self.prop_tree.get_children()); sel = self.char_tree.selection()
        if not sel: return
        character = self.characters[sel[0]]
        for key, value in character.get("m_originProps", {}).items():
            self.prop_tree.insert("", "end", iid=key, values=(key, value))
        self.character_level.set(str(character.get("m_level", 1)))
        self.character_exp.set(str(character.get("m_exp", 0)))
        self.refresh_abilities(character)

    def set_prop(self) -> None:
        char, prop = self.char_tree.selection(), self.prop_tree.selection()
        if not char or not prop: return messagebox.showwarning("尚未选择", "请选择角色和属性。")
        try: value = float(self.prop_value.get())
        except ValueError: return messagebox.showwarning("输入错误", "属性值必须是数字。")
        self.characters[char[0]]["m_originProps"][prop[0]] = int(value) if value.is_integer() else value
        self.show_props(); self.status.set("角色属性已在内存中修改；点击“保存角色属性”才会写入磁盘。")

    def set_character_level(self) -> None:
        selected = self.char_tree.selection()
        if not selected:
            return messagebox.showwarning("尚未选择", "请选择角色。")
        try:
            level, exp = int(self.character_level.get()), int(self.character_exp.get())
        except ValueError:
            return messagebox.showwarning("输入错误", "等级和经验必须是整数。")
        if not 1 <= level <= 100 or not 0 <= exp <= 9_999_999:
            return messagebox.showwarning("输入错误", "角色等级范围为 1–100，经验范围为 0–9999999。")
        character = self.characters[selected[0]]
        character["m_level"], character["m_exp"] = level, exp
        self.show_props(); self.status.set("角色等级和经验已在内存中修改；点击“保存角色属性”才会写入磁盘。")

    def refresh_abilities(self, character: dict) -> None:
        self.ability_tree.delete(*self.ability_tree.get_children())
        for index, ability in enumerate(character.get("kungfuInstances", [])):
            ability_id = ability.get("m_templeteUid")
            name, maximum = self.kungfu_catalog.get(ability_id, (f"未知能力 {ability_id}", 10))
            self.ability_tree.insert("", "end", iid=f"ability-{index}", values=(name, ability_id, ability.get("m_level", 1), maximum, ability.get("m_exp", 0)))

    def pick_ability(self, _=None) -> None:
        selected = self.ability_tree.selection()
        if selected:
            values = self.ability_tree.item(selected[0], "values")
            self.ability_level.set(str(values[2])); self.ability_exp.set(str(values[4]))

    def set_ability(self) -> None:
        character_selected, ability_selected = self.char_tree.selection(), self.ability_tree.selection()
        if not character_selected or not ability_selected:
            return messagebox.showwarning("尚未选择", "请选择角色和能力。")
        try:
            level, exp = int(self.ability_level.get()), int(self.ability_exp.get())
        except ValueError:
            return messagebox.showwarning("输入错误", "等级和经验必须是整数。")
        index = int(ability_selected[0].rsplit("-", 1)[1])
        ability = self.characters[character_selected[0]]["kungfuInstances"][index]
        maximum = self.kungfu_catalog.get(ability.get("m_templeteUid"), ("", 10))[1]
        if not 1 <= level <= maximum or not 0 <= exp <= 9_999_999:
            return messagebox.showwarning("输入错误", f"该能力等级范围为 1–{maximum}，经验范围为 0–9999999。")
        ability["m_level"], ability["m_exp"] = level, exp
        self.refresh_abilities(self.characters[character_selected[0]])
        self.status.set("能力等级和经验已在内存中修改；点击“保存角色属性”才会写入磁盘。")

    def refresh_npc_relations(self) -> None:
        if self.char_data is None:
            return
        self.npc_tree.delete(*self.npc_tree.get_children())
        needle = self.npc_filter.get().strip().casefold()
        hero_relations = self.all_characters.get("100401", {}).get("relationShip", {})
        rows = []
        for character_id, value in hero_relations.items():
            character = self.all_characters.get(str(character_id))
            if character is None:
                continue
            name = self.display_name(character)
            if needle and needle not in name.casefold() and needle not in str(character_id):
                continue
            group = self.job_factions.get(character.get("m_factionJob"), "其他 / 无势力")
            rows.append((name, str(character_id), value, group))
        groups: dict[str, int] = {}
        for _name, _character_id, _value, group in rows:
            groups[group] = groups.get(group, 0) + 1
        group_values = ["请选择势力", f"全部 NPC（{len(rows)}）", *[f"{group}（{count}）" for group, count in sorted(groups.items())]]
        if tuple(self.npc_group_box["values"]) != tuple(group_values):
            self.npc_group_box["values"] = group_values
        selected_group = self.npc_group.get()
        if selected_group == "请选择势力":
            return
        if selected_group != group_values[1]:
            selected_group = selected_group.rsplit("（", 1)[0]
            rows = [row for row in rows if row[3] == selected_group]
        for name, character_id, value, _group in sorted(rows, key=lambda row: (row[0], int(row[1]))):
            self.npc_tree.insert("", "end", iid=character_id, values=(name, character_id, value))

    def pick_npc_relation(self, _=None) -> None:
        selected = self.npc_tree.selection()
        if selected:
            self.npc_value.set(str(self.npc_tree.item(selected[0], "values")[2]))

    def set_npc_relation(self) -> None:
        selected = self.npc_tree.selection()
        if not selected:
            return messagebox.showwarning("尚未选择", "请选择一个 NPC。")
        try:
            value = int(self.npc_value.get())
        except ValueError:
            return messagebox.showwarning("输入错误", "关系值必须是 -100 到 100 的整数。")
        if not -100 <= value <= 100:
            return messagebox.showwarning("输入错误", "关系值范围为 -100 到 100。")
        character_id = selected[0]
        hero = self.all_characters["100401"]
        hero.setdefault("relationShip", {})[character_id] = value
        target = self.all_characters.get(character_id)
        if target is not None:
            target.setdefault("relationShip", {})["100401"] = value
        self.refresh_npc_relations()
        self.status.set("NPC 关系已在内存中修改；点击“保存 NPC 关系”才会写入磁盘。")

    def refresh_factions(self) -> None:
        if self.faction_data is None:
            return
        self.faction_tree.delete(*self.faction_tree.get_children())
        needle = self.faction_filter.get().strip().casefold()
        factions = self.faction_data["Data"]["value"].get("factions", {})
        rows = []
        for faction_id, faction in factions.items():
            numeric_id = faction.get("templeteId", faction_id)
            name = self.faction_names.get(int(numeric_id), f"未知势力 {numeric_id}")
            if needle and needle not in name.casefold() and needle not in str(numeric_id):
                continue
            rows.append((name, str(numeric_id), faction.get("playerFame", 0)))
        for name, faction_id, value in sorted(rows, key=lambda row: (row[0], int(row[1]))):
            self.faction_tree.insert("", "end", iid=faction_id, values=(name, faction_id, value))

    def pick_faction_relation(self, _=None) -> None:
        selected = self.faction_tree.selection()
        if selected:
            self.faction_value.set(str(self.faction_tree.item(selected[0], "values")[2]))

    def set_faction_relation(self) -> None:
        selected = self.faction_tree.selection()
        if not selected:
            return messagebox.showwarning("尚未选择", "请选择一个势力。")
        try:
            value = int(self.faction_value.get())
        except ValueError:
            return messagebox.showwarning("输入错误", "关系值必须是 -100 到 100 的整数。")
        if not -100 <= value <= 100:
            return messagebox.showwarning("输入错误", "关系值范围为 -100 到 100。")
        faction_id = selected[0]
        faction_state = self.faction_data["Data"]["value"]
        faction_state["factions"][faction_id]["playerFame"] = value
        # ES3 persists both ID- and name-keyed dictionaries; keep them consistent.
        for faction in faction_state.get("factionDict", {}).values():
            if str(faction.get("templeteId")) == faction_id:
                faction["playerFame"] = value
        self.refresh_factions()
        self.status.set("势力关系已在内存中修改；点击“保存势力关系”才会写入磁盘。")

    def save(self, target: str) -> None:
        if self.team_data is None: return messagebox.showwarning("尚未读取", "请先读取存档。")
        if not messagebox.askyesno("确认写入", "游戏必须已经完全退出。将先完整备份这个存档槽，然后原子写入并回读校验。继续？"): return
        try:
            folder = self.root_path / self.slot.get(); backup = self.root_path / "_EditorBackups" / f"{self.slot.get()}_{datetime.now():%Y%m%d_%H%M%S}"
            backup.parent.mkdir(exist_ok=True); shutil.copytree(folder, backup)
            if target == "items": es3_codec.atomic_write(folder / TEAM_FILE, self.team_data)
            elif target in {"characters", "relations"}: es3_codec.atomic_write(folder / CHAR_FILE, self.char_data)
            else: es3_codec.atomic_write(folder / FACTION_FILE, self.faction_data)
            self.status.set(f"已保存并回读校验。完整备份：{backup}")
            messagebox.showinfo("完成", "写入成功。请启动游戏读取该存档验证效果。")
        except Exception as exc:
            messagebox.showerror("保存失败", f"原档未被替换或可从备份恢复。\n\n{exc}")


if __name__ == "__main__":
    Editor().mainloop()
