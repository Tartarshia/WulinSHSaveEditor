"""Browser regressions use synthetic API responses and never open or save game slots."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import unittest
from urllib.parse import urlsplit
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

        def respond(route):
            nonlocal loaded
            path = urlsplit(route.request.url).path
            if path.startswith("/api/session/"):
                route.continue_()
                return
            if path == "/api/state":
                data = dict(game_root="", save_root="", loaded=loaded, slot="Save0", slots=[dict(name="Save0", saved_at="测试时间")])
            elif path == "/api/load":
                loaded = True
                data = {}
            elif path == "/api/save":
                data = dict(message="已保存并回读校验。完整备份：" + long_path)
            elif path == "/api/consumables":
                data = dict(consumables=consumables, total=2)
            elif path == "/api/books":
                data = dict(books=[dict(id=3, name="测试秘籍", group="内功", rarity=2, owned=False, description="测试说明")], total=1)
            elif path == "/api/recipes":
                data = dict(recipes=[dict(id=4, name="测试配方", group="食物", rarity=1, owned=False, description="测试说明")], total=1)
            elif path.startswith("/api/inventory-groups/"):
                data = dict(rows=[dict(id=5, name="测试材料", group="药材", rarity=1, count=0, description="测试说明")], total=1)
            elif path == "/api/items":
                data = dict(items=[], categories=["全部"])
            elif path == "/api/characters":
                data = dict(characters=[])
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
            for tab in ["books", "recipes", "materials", "treasures", "life"]:
                page.locator(f'[data-tab="{tab}"]').click()
                button = page.locator(f"#{tab} .group-toggle").first
                button.wait_for()
                self.assertEqual(button.get_attribute("aria-expanded"), "true")
            page.locator('#life [data-save="life"]').click()
            page.locator('#confirm button[value="ok"]').click()
            page.wait_for_function("() => document.querySelector('#status').textContent.includes('已保存')")
            self.assertIn(long_path, page.locator("#status").inner_text())
            self.assertEqual(page.locator("#statusBar #status").count(), 1)
            for width in [1400, 900, 540, 375, 320]:
                page.set_viewport_size({"width": width, "height": 900})
                for tab in ["life", "global", "items", "characters", "consumables", "books", "recipes", "materials", "treasures", "relations", "factions"]:
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
