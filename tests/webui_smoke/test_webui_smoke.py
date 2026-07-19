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


def test_error_path_recovery(webui_server):
    """Click bad save → expect error card; click good save → expect preview and Continue works."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        expect(page.locator(".rail-title")).to_have_text("NPV BUILD")
        # Click bad save card
        cards = page.locator(".card.selectable")
        expect(cards).to_have_count(2)
        cards.nth(1).click()  # BadSave-1
        bad_card = cards.nth(1)
        expect(bad_card.locator(".preview")).to_contain_text("Unsupported patch")
        # Click good save card
        cards.nth(0).click()  # ManualSave-3
        good_card = cards.nth(0)
        expect(good_card.locator(".preview")).to_contain_text("pwa · skin 03 · bob")
        # Name/output-dir fields live on the Appearance step now, not Source
        expect(page.locator("#npv-name")).to_have_count(0)
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        # Auto-filled from the save name and default_output_root
        expect(page.locator("#npv-name")).to_have_value("ManualSave-3")
        expect(page.locator("#output-dir")).to_have_value("/out/ManualSave-3")
        page.fill("#npv-name", "TestV")
        page.fill("#output-dir", "/out/v")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        browser.close()


def test_continue_with_empty_fields_shows_error(webui_server):
    """Empty output dir on Appearance must produce visible feedback, not a silent no-op."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        good_card = page.locator(".card.selectable").first
        good_card.click()
        expect(good_card.locator(".preview")).to_contain_text("pwa")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        page.fill("#output-dir", "")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")  # did not advance
        expect(page.locator(".form-error")).to_contain_text("Output directory")
        # Filling the field and retrying clears the error and advances
        page.fill("#output-dir", "/out/v")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        browser.close()


def test_patch_badge_and_browse(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        cards = page.locator(".card.selectable")
        expect(cards).to_have_count(2)
        expect(cards.nth(0).locator(".badge")).to_have_text("2.31")
        expect(cards.nth(1).locator(".badge")).to_have_count(0)  # unknown -> no badge
        # Browse… adds the picked save as a new selected card with a preview
        page.click("text=Browse…")
        expect(page.locator(".card.selectable")).to_have_count(3)
        browsed = page.locator(".card.selectable.selected")
        expect(browsed).to_contain_text("BrowsedSave")
        expect(browsed.locator(".preview")).to_contain_text("pwa")
        browser.close()


def test_drag_drop_save_file(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        expect(page.locator(".card.selectable")).to_have_count(2)
        # Simulate a pywebview-style drop (File with pywebviewFullPath)
        page.evaluate(
            """() => {
              const dt = new DataTransfer();
              const f = new File(["x"], "sav.dat");
              Object.defineProperty(f, "pywebviewFullPath",
                                    { value: "/dropped/DroppedSave/sav.dat" });
              dt.items.add(f);
              const target = document.querySelector("main");
              target.dispatchEvent(new DragEvent("drop",
                { bubbles: true, cancelable: true, dataTransfer: dt }));
            }"""
        )
        expect(page.locator(".card.selectable")).to_have_count(3)
        expect(page.locator(".card.selectable.selected")).to_contain_text("DroppedSave")
        browser.close()


def test_build_log_copy_and_scroll_pause(webui_server):
    """The build log auto-scrolls, pauses when the user scrolls up, and has a
    working Copy button."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable").first.click()
        page.click("text=Continue →")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        # Never-ending build: emit a log line on every poll so the screen stays live
        page.evaluate(
            """() => {
              window.__mockApi.poll_events = async () =>
                [{ kind: "log", text: ("line " + (window.__n = (window.__n || 0) + 1)).padEnd(80, "x") + "\\n" }];
            }"""
        )
        page.click("text=Start build")
        expect(page.locator(".log")).to_contain_text("line 5", timeout=5000)
        # Auto-scroll: pinned to bottom
        assert page.evaluate(
            "() => { const l = document.querySelector('.log');"
            " return l.scrollTop + l.clientHeight >= l.scrollHeight - 4; }")
        # User scrolls up -> auto-scroll pauses
        page.evaluate(
            "() => { const l = document.querySelector('.log');"
            " l.scrollTop = 0; l.dispatchEvent(new Event('scroll')); }")
        page.wait_for_timeout(1000)  # several polls/renders later...
        assert page.evaluate("() => document.querySelector('.log').scrollTop < 40")
        # Copy button copies the log text
        page.click("text=Copy log")
        expect(page.locator("text=Copied ✓")).to_be_visible()
        clip = page.evaluate("() => navigator.clipboard.readText()")
        assert "line 1" in clip
        browser.close()


def test_library_built_date_rebuild_delete(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=My NPVs")
        card = page.locator(".grid .card").first
        expect(card).to_contain_text("TestV")
        expect(card).to_contain_text("built")  # state badge + date row
        expect(card.locator("text=/built .*20\\d\\d/")).to_be_visible()
        # Rebuild jumps to the Build step with the mod's context loaded
        card.locator("text=Rebuild").click()
        expect(page.locator("h1")).to_have_text("Build")
        expect(page.locator("main")).to_contain_text('Building "TestV"')
        # Delete is two-step and removes the card
        page.click("text=My NPVs")
        del_btn = page.locator("text=Delete")
        del_btn.click()
        page.locator("text=Really delete?").click()
        expect(page.locator(".grid .card")).to_have_count(0)
        expect(page.locator("text=Nothing built yet.")).to_be_visible()
        browser.close()


def test_settings_tools_cache_and_clothing_dir(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=Settings")
        # Resolved tool path shown under the dependency lamp
        expect(page.locator("main")).to_contain_text("/cache/tools/wolvenkit/cp77tools")
        # blender missing -> install button; runs to completion via polled events
        expect(page.locator("#install-tools")).to_be_visible()
        page.click("#install-tools")
        expect(page.locator(".tool-progress")).to_contain_text("Downloading Blender (50%)")
        # Clothing images dir field present and editable
        expect(page.locator("#cfg-clothing-images-dir")).to_be_visible()
        # Cache rows with sizes; clearing removes the row (tools needs confirm)
        cache = page.locator(".cache-card")
        expect(cache).to_contain_text("index")
        expect(cache).to_contain_text("2.0 MB")
        expect(cache).to_contain_text("1.0 GB")
        cache.locator("button", has_text="Clear").first.click()  # index: one click
        expect(cache).not_to_contain_text("index")
        cache.locator("button", has_text="Clear").first.click()  # tools: step 1
        cache.locator("text=Really clear?").click()              # tools: step 2
        assert page.evaluate("() => window.__mockApi._cleared") == ["index", "tools"]
        browser.close()


def test_first_run_onboarding_flow(webui_server):
    """needs_onboarding lands on a guided game-dir setup screen; picking a
    detected install and continuing saves config and lands on Source."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.add_init_script(
            """
            (() => {
              const base = window.__mockApi;
              let onboarded = false;
              const origState = base.get_state.bind(base);
              base.get_state = async () => {
                const s = await origState();
                return { ...s, needs_onboarding: !onboarded };
              };
              base.detect_game_dirs = async () =>
                ({ ok: true, dirs: ["/games/Cyberpunk 2077"] });
              base._savedConfigs = [];
              base.save_config = async (cfg) => {
                base._savedConfigs.push(cfg);
                onboarded = true;
                return { ok: true, errors: [] };
              };
            })();
            """
        )
        page.goto(webui_server)
        expect(page.locator("h1")).to_have_text("Welcome")
        # Detected install rendered as a selectable card; picking it fills the field
        page.locator(".card.selectable", has_text="Cyberpunk 2077").click()
        expect(page.locator("#onboard-game-dir")).to_have_value("/games/Cyberpunk 2077")
        page.click("text=Save & continue")
        expect(page.locator("h1")).to_have_text("Source")
        saved = page.evaluate("() => window.__mockApi._savedConfigs")
        assert saved == [{"game_dir": "/games/Cyberpunk 2077"}]
        browser.close()


def test_full_flow_source_to_install(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        expect(page.locator(".rail-title")).to_have_text("NPV BUILD")
        good_card = page.locator(".card.selectable").first
        good_card.click()
        expect(good_card.locator(".preview")).to_contain_text("pwa")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        page.fill("#npv-name", "TestV")
        page.fill("#output-dir", "/out/v")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        page.click("text=Start build")
        expect(page.locator("h1")).to_have_text("Done", timeout=5000)
        # Zip summary loads (path, size, contents)
        expect(page.locator(".zip-summary")).to_contain_text("v_abc.zip")
        expect(page.locator(".zip-summary")).to_contain_text("6.3 MB")
        expect(page.locator(".zip-summary")).to_contain_text("archive/pc/mod/v_abc.archive")
        # Open folder action calls the bridge
        page.click("text=Open folder")
        assert page.evaluate("() => window.__mockApi._opened.length") == 1
        page.click("text=Install to game")
        expect(page.locator("text=Installed ✓")).to_be_visible()
        browser.close()
