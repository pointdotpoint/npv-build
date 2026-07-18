"""End-to-end flow through the static frontend with a mocked bridge.

Requires: uv run playwright install chromium
"""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

WEBUI = Path(__file__).parents[2] / "npv_build" / "webui"
MOCK = Path(__file__).parent / "mock_api.js"


@pytest.fixture
def webui_server():
    handler = partial(SimpleHTTPRequestHandler, directory=str(WEBUI))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_full_flow_source_to_install(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        expect(page.locator(".rail-title")).to_have_text("NPV BUILD")
        page.locator(".card.selectable").click()
        expect(page.locator(".preview")).to_contain_text("pwa")
        page.fill("#npv-name", "TestV")
        page.fill("#output-dir", "/out/v")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        page.click("text=Start build")
        expect(page.locator("h1")).to_have_text("Done", timeout=5000)
        page.click("text=Install to game")
        expect(page.locator("text=Installed ✓")).to_be_visible()
        browser.close()
