"""Browser regressions use synthetic API responses and never open or save game slots."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import unittest
from urllib.parse import urlsplit, parse_qs
from urllib.request import urlopen


class BrowserUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("Install requirements-test.txt for browser tests")
        cls.driver = sync_playwright().start()
        try:
            cls.browser = cls.driver.chromium.launch(channel="msedge", headless=True)
        except Exception as error:
            cls.driver.stop()
            raise unittest.SkipTest(f"Microsoft Edge unavailable: {error}")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen([sys.executable, "web_app.py", "--no-browser", "--port", str(port)],
                                      cwd=Path(__file__).parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urlopen(cls.base, timeout=1):
                    return
            except OSError:
                time.sleep(.1)
        cls.tearDownClass()
        raise RuntimeError("Test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()
        if cls.server.poll() is None:
            cls.server.terminate()
            cls.server.wait(timeout=10)

    def test_group_folding_status_bar_and_narrow_layout(self):
        page = self.browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        loaded = False
        long_path = "C:\\" + "SyntheticBackupFolder\\" * 24
        consumables = [dict(id=1, name="测试丹药", group="丹药", rarity=3, count=2, description="直接显示的说明"),
                       dict(id=2, name="测试水果", group="水果", rarity=1, count=0, description="测试说明")]
        statuses = []
        for key, uid, rarity, owned, source, permanent in (("active", 2, 1, True, "特征", True), ("normal", 9, 3, False, "创建角色可选", True), ("readonly", 1, 2, False, "经脉", True), ("temporary", 3, 0, False, "其他状态", False)):
            statuses.append(dict(key=key, id=uid, name="测试状态" + key, description="悬停状态说明 <script>" + key,
                                 rarity=rarity, order=len(statuses), owned=owned, active=owned, source=source,
                                 permanent=permanent, creation=["创建天赋"] if key == "normal" else [],
                                 readonly="特殊状态只读" if key == "readonly" else "", remaining=[1] if owned else [],
                                 conditions=['属性激活条件：福缘 ≥ 10。'] if key == 'readonly' else [],
                                 condition_source='官方属性条件表 SelfPropBufflData' if key == 'readonly' else '',
                                 tag_conditions=['额外限制：存在以下标签时不生效：测试标签'] if key == 'readonly' else [],
                                 condition_references=[dict(title='Wiki 参考', url='https://heros-adventure.wikidot.com/traits', checked='2026-10-17')],
                                 runtime_conditions=[dict(script='测试/<script>', timing=['行动结束时'], conditions=['0% ≤ 生命比例 ≤ 30%'], complete=False, path='Assets/test.asset')] if key=='readonly' else [],
                                 readonly_detail='仅增删记录不能保证脚本正确初始化' if key == 'readonly' else '',
                                 lifetime=1 if permanent else 48, tick="Infinite" if permanent else "Time"))

        for key, owned in [('internal-owned', True), ('internal-missing', False)]:
            statuses.append(dict(statuses[0], key=key, id=99, name='内部状态'+key, owned=owned,
                                 readonly='游戏内部隐藏状态，只读', source='其他状态'))

        def respond(route):
            nonlocal loaded
            path = urlsplit(route.request.url).path
            if path.startswith("/api/session/"):
                route.continue_()
                return
            if path == "/api/state":
                data = dict(game_root="", save_root="", loaded=loaded, slot="Save0", slots=[dict(name="Save0", saved_at="2026-10-14 22:49")])
            elif path == "/api/load":
                loaded = True
                data = {}
            elif path == "/api/save":
                data = dict(message="已保存并回读校验。完整备份：" + long_path)
            elif path == "/api/consumables":
                data = dict(consumables=consumables, total=2)
            elif path == "/api/books":
                data = dict(books=[dict(id=3, name="测试秘籍", group="内功", rarity=2, owned=False, description="测试说明")], total=1)
            elif path == "/api/statuses":
                if route.request.method == 'POST':
                    payload = json.loads(route.request.post_data)
                    row = next(x for x in statuses if x['key'] == payload['key'])
                    assert not row['readonly']
                    row['owned'] = row['active'] = payload['owned']
                    row['remaining'] = [1] if row['owned'] else []
                    data = dict(message="状态已在内存中修改")
                else:
                    query = parse_qs(urlsplit(route.request.url).query)
                    rows = [x for x in statuses if (query.get('source', ['all'])[0] in ('all', x['source'])) and (query.get('kind', ['all'])[0] == 'all' or (query['kind'][0] == 'permanent') == x['permanent'])]
                    sorting = query.get('sort', ['default'])[0]
                    rows.sort(key=lambda x: (not x['owned'], x['id'] if sorting == 'id' else -x['rarity'] if sorting == 'rarity' else x['order'], x['order']))
                    data = dict(rows=rows, total=len(statuses), owned=sum(x['owned'] for x in statuses), sources=list(dict.fromkeys(x['source'] for x in statuses)))
            elif path == "/api/equipment":
                data = dict(rows=[dict(id=6, name="测试武器", group="武器 · 剑", rarity=3, copies=[], description="装备说明"), dict(id=7, name="测试防具", group="防具", rarity=2, copies=[dict(index=0, fingerprint="test", modified=True, extra_data=[dict(label="锻造等级（原值）", value="2"), dict(label="测试字段", value="<script>")]), dict(index=1, fingerprint="second", modified=False, extra_data=[])], description="防具说明"), dict(id=8, name="测试宠物装备", group="宠物武器", rarity=1, copies=[], description="宠物武器说明")], total=3)
            elif path == "/api/recipes":
                data = dict(recipes=[dict(id=4, name="测试配方", group="食物", rarity=1, owned=False, description="测试说明")], total=1)
            elif path.startswith("/api/inventory-groups/"):
                data = dict(rows=[dict(id=5, name="测试材料", group="药材", rarity=1, count=0, description="测试说明")], total=1)
            elif path == "/api/items":
                data = dict(items=[], categories=["全部"])
            elif path == "/api/catalog":
                data = []
            elif path == "/api/characters":
                data = dict(characters=[dict(id=str(1000 + i), name=f"测试角色{i}", status="已入队，未出战", level=1) for i in range(40)])
            elif path.startswith("/api/characters/"):
                cid = path.rsplit("/", 1)[-1]
                data = dict(id=cid, name=f"测试角色{int(cid) - 1000}", level=1, exp=0, props=[], innate=[], morals=[], kungfu=[], life=[], location=None)
            elif path == "/api/life-abilities":
                data = dict(abilities=[dict(key="能力_采集_采矿", category="采集", name="采矿", level=1, max=5, exp=0)], total=1)
            elif path == "/api/global":
                data = dict(money=0, stamina=100, mood=100, stamina_max=100, jianghu=0, jianghu_max=9999, day=1)
            else:
                data = dict(rows=[], groups=[])
            route.fulfill(content_type="application/json", body=json.dumps(data, ensure_ascii=False))

        page.route("**/api/**", respond)
        try:
            page.goto(self.base)
            page.locator("#load").click()
            page.wait_for_function("() => document.querySelector('#status').textContent.includes('加载完成')")
            self.assertEqual(page.locator("#loadingStatus").count(), 0)
            self.assertTrue(page.locator("#loadingProgress").is_hidden())
            page.locator('[data-tab="consumables"]').click()
            toggle = page.locator("#consumableGroups .group-toggle").filter(has_text="丹药")
            toggle.wait_for()
            panel = page.locator("#" + toggle.get_attribute("aria-controls"))
            self.assertTrue(panel.is_visible())
            toggle.click()
            self.assertTrue(panel.is_hidden())
            self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
            page.locator("#refreshConsumables").click()
            panel.wait_for(state="detached")
            toggle = page.locator("#consumableGroups .group-toggle").filter(has_text="丹药")
            self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
            toggle.focus()
            page.keyboard.press("Enter")
            self.assertTrue(page.locator("#" + toggle.get_attribute("aria-controls")).is_visible())
            page.keyboard.press("Space")
            self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
            toggle.click()
            self.assertTrue(page.locator("#consumableGroups .item-description").first.is_visible())
            for tab in ["books", "recipes", "materials", "treasures", "other_stackable", "equipment", "life"]:
                page.locator(f'[data-tab="{tab}"]').click()
                button = page.locator(f"#{tab} .group-toggle").first
                button.wait_for()
                self.assertEqual(button.get_attribute("aria-expanded"), "true")
            old_form = page.locator('#other_stackable .consumable-form').first.element_handle()
            page.locator('[data-tab="other_stackable"]').click()
            page.wait_for_function('(el) => !el.isConnected', arg=old_form)
            form = page.locator('#other_stackable .consumable-form').first
            form.locator('input').fill('999')
            with page.expect_request(lambda r: '/api/inventory-groups/other_stackable' in r.url and r.method == 'POST') as changed:
                form.locator('button').click()
            self.assertEqual(json.loads(changed.value.post_data), dict(id="5", count="999"))
            page.locator('[data-tab="items"]').click()
            self.assertFalse(page.locator('#showItemOtherStackable').is_checked())
            with page.expect_request(lambda r: '/api/items?' in r.url and 'include_other_stackable=1' in r.url):
                page.locator('#showItemOtherStackable').check()
            self.assertFalse(page.locator('#showItemEquipment').is_checked())
            with page.expect_request(lambda r: '/api/items?' in r.url and 'include_equipment=1' in r.url):
                page.locator('#showItemEquipment').check()
            page.locator('[data-tab="equipment"]').click()
            page.locator('#equipmentGroups .book-card').first.wait_for()
            self.assertEqual(page.locator('#equipmentGroups .book-card').count(), 5)
            self.assertIn('武器 · 剑', page.locator('#equipmentGroups .group-toggle').first.inner_text())
            self.assertEqual(page.locator('[data-equipment="add"]').count(), 3)
            self.assertEqual(page.locator('[data-equipment="add"]').first.inner_text(), '添加1件')
            self.assertEqual(page.locator('[data-equipment="delete"]').first.inner_text(), '删除1件')
            self.assertNotIn('锻造等级（原值）', page.locator('#equipmentGroups').inner_text())
            self.assertEqual(page.locator('[data-equipment-extra]').count(), 1)
            extra_button = page.locator('[data-equipment-extra]')
            self.assertEqual(extra_button.inner_text(), '显示附加数据')
            self.assertFalse(page.locator('#equipmentExtraDialog').is_visible())
            extra_button.click()
            self.assertTrue(page.locator('#equipmentExtraDialog').is_visible())
            self.assertIn('测试防具 · 第 1 件', page.locator('#equipmentExtraTitle').inner_text())
            self.assertIn('锻造等级（原值）', page.locator('#equipmentExtraContent').inner_text())
            self.assertIn('<script>', page.locator('#equipmentExtraContent').inner_text())
            self.assertEqual(page.locator('#equipmentExtraContent script').count(), 0)
            page.keyboard.press('Escape')
            self.assertFalse(page.locator('#equipmentExtraDialog').is_visible())
            self.assertTrue(extra_button.evaluate('el => document.activeElement === el'))
            page.set_viewport_size(dict(width=320, height=900))
            extra_button.click()
            modal = page.locator('#equipmentExtraDialog')
            rect = modal.bounding_box()
            self.assertGreaterEqual(rect['x'], 0)
            self.assertLessEqual(rect['x'] + rect['width'], 320)
            self.assertTrue(modal.evaluate('el => el.scrollWidth <= el.clientWidth'))
            page.locator('#equipmentExtraDialog button').click()
            self.assertFalse(modal.is_visible())
            page.set_viewport_size(dict(width=1400, height=900))
            # Resizing back from mobile can still reflow/scroll-anchor between
            # two protocol calls. Measure both cards in the same browser frame.
            page.wait_for_function("""() => {
                const cards = document.querySelectorAll('#equipmentGroups .book-card');
                if (cards.length < 3) return false;
                const a = cards[1].getBoundingClientRect(), b = cards[2].getBoundingClientRect();
                return Math.abs(a.top - b.top) <= 1 && a.left < b.left;
            }""")
            self.assertEqual(page.locator('#equipmentGroups input').count(), 0)
            self.assertEqual(page.locator('#equipmentGroups button').filter(has_text="编辑").count(), 0)
            with page.expect_request(lambda r: '/api/equipment' in r.url and r.method == 'POST') as added:
                page.locator('[data-equipment="add"]').first.click()
            self.assertEqual(json.loads(added.value.post_data), dict(action="add", id="6"))
            with page.expect_request(lambda r: '/api/equipment' in r.url and r.method == 'POST') as duplicate:
                page.locator('[data-equipment="add"][data-id="7"]').click()
            self.assertEqual(json.loads(duplicate.value.post_data), dict(action="add", id="7"))
            self.assertIn('宠物武器', page.locator('#equipmentGroups').inner_text())
            with page.expect_request(lambda r: '/api/equipment' in r.url and r.method == 'POST') as pet:
                page.locator('[data-equipment="add"][data-id="8"]').click()
            self.assertEqual(json.loads(pet.value.post_data), dict(action="add", id="8"))
            page.locator('[data-equipment="delete"]').first.click()
            with page.expect_request(lambda r: '/api/equipment' in r.url and r.method == 'POST') as removed:
                page.locator('#confirm button[value="ok"]').click()
            self.assertEqual(json.loads(removed.value.post_data), dict(action="delete", id="7", index="0", fingerprint="test"))
            page.locator('[data-tab="life"]').click()
            page.locator('#life [data-save="life"]').click()
            page.locator('#confirm button[value="ok"]').click()
            page.wait_for_function("() => document.querySelector('#status').textContent.includes('已保存')")
            self.assertIn(long_path, page.locator("#status").inner_text())
            self.assertEqual(page.locator("#statusBar #status").count(), 1)
            page.locator('[data-tab="characters"]').click()
            characters = page.locator("#characterList")
            self.assertTrue(characters.evaluate("el => el.scrollHeight > el.clientHeight"))
            self.assertLess(characters.bounding_box()["height"], 900)
            self.assertEqual(characters.evaluate("el => getComputedStyle(el).overflowY"), "auto")
            characters.locator("button").last.click()
            page.locator("#characterDetail h2").first.wait_for()
            self.assertEqual(page.locator("#characterDetail h2").first.inner_text(), "测试角色39")
            page.locator('[data-tab="statuses"]').click()
            page.locator('#missingStatusGroups [data-status-toggle="normal"]').wait_for()
            self.assertTrue(page.locator('[data-status-toggle="readonly"]').is_disabled())
            self.assertFalse(page.locator('#statusShowInternal').is_checked())
            self.assertFalse(page.locator('#statusShowTemporary').is_checked())
            self.assertEqual(page.locator('[data-status-toggle="temporary"]').count(), 0)
            page.locator('#statusShowTemporary').check()
            page.locator('[data-status-toggle="temporary"]').wait_for()
            page.locator('#statusShowTemporary').uncheck()
            page.locator('[data-status-toggle="temporary"]').wait_for(state='detached')
            page.locator('#statusShowTemporary').check()
            page.locator('[data-status-toggle="temporary"]').wait_for()
            self.assertEqual(page.locator('[data-status-toggle^="internal-"]').count(), 0)
            self.assertIn('已隐藏 2 个内部状态', page.locator('#statusSummary').inner_text())
            page.locator('#statusShowInternal').check()
            page.locator('[data-status-toggle="internal-owned"]').wait_for()
            self.assertTrue(page.locator('#ownedStatusGroups [data-status-toggle="internal-owned"]').is_checked())
            self.assertTrue(page.locator('#missingStatusGroups [data-status-toggle="internal-missing"]').is_disabled())
            page.locator('#statusShowInternal').uncheck()
            page.locator('[data-status-toggle="internal-owned"]').wait_for(state='detached')
            self.assertTrue(page.locator('[data-status-toggle="readonly"]').is_disabled())
            special = page.locator('.status-card[data-status-key="readonly"]')
            self.assertIn('属性激活条件：福缘 ≥ 10。', special.inner_text())
            self.assertNotIn('测试标签', special.inner_text())
            special.hover()
            page.locator('#statusTooltip').wait_for(state='visible')
            self.assertIn('不能保证脚本正确初始化', page.locator('#statusTooltip').inner_text())
            self.assertIn('SelfPropBufflData', page.locator('#statusTooltip').inner_text())
            self.assertIn('测试标签', page.locator('#statusTooltip').inner_text())
            self.assertIn('脚本配置推导', page.locator('#statusTooltip').inner_text())
            self.assertIn('仍含未翻译项', page.locator('#statusTooltip').inner_text())
            self.assertIn('0% ≤ 生命比例 ≤ 30%', page.locator('#statusTooltip').inner_text())
            self.assertEqual(page.locator('#statusTooltip script').count(), 0)
            self.assertEqual(page.locator('#statusTooltip a').get_attribute('href'), 'https://heros-adventure.wikidot.com/traits')
            self.assertTrue(page.locator('#ownedStatusGroups [data-status-toggle="active"]').is_checked())
            card = page.locator('.status-card[data-status-key="normal"]')
            self.assertNotIn('悬停状态说明', card.inner_text())
            self.assertNotIn('悬停或聚焦查看说明', card.inner_text())
            self.assertEqual(page.locator('.status-hover-hint').count(), 0)
            card.hover()
            page.locator('#statusTooltip').wait_for(state='visible')
            self.assertIn('悬停状态说明 <script>normal', page.locator('#statusTooltip').inner_text())
            self.assertEqual(page.locator('#statusTooltip script').count(), 0)
            page.keyboard.press('Escape')
            self.assertTrue(page.locator('#statusTooltip').is_hidden())
            page.locator('[data-status-toggle="normal"]').check()
            page.locator('#ownedStatusGroups [data-status-toggle="normal"]').wait_for()
            page.locator('[data-status-toggle="normal"]').uncheck()
            page.locator('#missingStatusGroups [data-status-toggle="normal"]').wait_for()
            page.locator('#statusGrouping').uncheck()
            page.locator('#statusSort').select_option('id')
            page.wait_for_function("() => [...document.querySelectorAll('#missingStatusGroups .status-card')].map(x=>x.dataset.statusKey).join(',') === 'readonly,temporary,normal'")
            page.locator('#statusSort').select_option('rarity')
            page.wait_for_function("() => [...document.querySelectorAll('#missingStatusGroups .status-card')].map(x=>x.dataset.statusKey).join(',') === 'normal,readonly,temporary'")
            page.locator('#statusSource').select_option('创建角色可选')
            page.wait_for_function("() => document.querySelectorAll('#statuses .status-card').length === 1")
            page.locator('#statusSource').select_option('all')
            page.locator('#statusShowTemporary').uncheck()
            page.locator('#statusKind').select_option('temporary')
            page.wait_for_function("() => document.querySelectorAll('#statuses .status-card').length === 1 && document.querySelector('#statuses .status-card').dataset.statusKey === 'temporary'")
            self.assertTrue(page.locator('#statusShowTemporary').is_checked())
            page.locator('#statusShowTemporary').uncheck()
            self.assertEqual(page.locator('#statusKind').input_value(), 'all')
            page.locator('#statusKind').select_option('all')
            page.locator('#statusGrouping').check()
            for width in [1400, 900, 540, 375, 320]:
                page.set_viewport_size({"width": width, "height": 900})
                for tab in ["life", "global", "items", "characters", "statuses", "consumables", "books", "recipes", "materials", "treasures", "other_stackable", "equipment", "relations", "factions"]:
                    page.locator(f'[data-tab="{tab}"]').click()
                    page.wait_for_timeout(40)
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), (width, tab))
                    rect = page.locator("#statusBar").bounding_box()
                    self.assertAlmostEqual(rect["y"] + rect["height"], 900, delta=1)
                    self.assertGreaterEqual(page.evaluate("parseFloat(getComputedStyle(document.body).paddingBottom)"), rect["height"])
            self.assertEqual(errors, [])
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
