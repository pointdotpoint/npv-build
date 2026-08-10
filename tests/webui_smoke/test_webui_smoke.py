"""End-to-end flow through the static frontend with a mocked bridge.

Requires: uv run playwright install chromium
"""

import re
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
        cards = page.locator(".card.selectable.save-card")
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
        good_card = page.locator(".card.selectable.save-card").first
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
        cards = page.locator(".card.selectable.save-card")
        expect(cards).to_have_count(2)
        expect(cards.nth(0).locator(".badge")).to_have_text("2.31")
        expect(cards.nth(1).locator(".badge")).to_have_count(0)  # unknown -> no badge
        # Browse… adds the picked save as a new selected card with a preview
        page.click("text=Browse…")
        expect(page.locator(".card.selectable.save-card")).to_have_count(3)
        browsed = page.locator(".card.selectable.save-card.selected")
        expect(browsed).to_contain_text("BrowsedSave")
        expect(browsed.locator(".preview")).to_contain_text("pwa")
        browser.close()


def test_drag_drop_save_file(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        expect(page.locator(".card.selectable.save-card")).to_have_count(2)
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
        expect(page.locator(".card.selectable.save-card")).to_have_count(3)
        expect(page.locator(".card.selectable.save-card.selected")).to_contain_text("DroppedSave")
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
        page.locator(".card.selectable.save-card").first.click()
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
            " return l.scrollTop + l.clientHeight >= l.scrollHeight - 4; }"
        )
        # User scrolls up -> auto-scroll pauses
        page.evaluate(
            "() => { const l = document.querySelector('.log');"
            " l.scrollTop = 0; l.dispatchEvent(new Event('scroll')); }"
        )
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
        # Delete is two-step and removes that card (other builds stay listed)
        page.click("text=My NPVs")
        before = page.locator(".grid .card").count()
        first = page.locator(".grid .card").first
        first.locator("text=Delete").click()
        first.locator("text=Really delete?").click()
        expect(page.locator(".grid .card")).to_have_count(before - 1)
        expect(page.locator(".grid .card").first).not_to_contain_text("TestV")
        browser.close()


def test_library_render_preview_shows_images(webui_server):
    """My NPVs entry -> Render preview -> image strip appears from bridge data URLs."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=My NPVs")
        page.wait_for_selector(".btn-render-preview")
        page.click(".btn-render-preview")
        page.wait_for_selector(".preview-strip .preview-img")
        images = page.eval_on_selector_all(
            ".preview-strip .preview-img", "els => els.map(e => e.src)"
        )
        assert len(images) == 2 and all(src.startswith("data:image/png") for src in images)
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
        cache.locator("text=Really clear?").click()  # tools: step 2
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
        good_card = page.locator(".card.selectable.save-card").first
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


def test_appearance_inspector_override_flow(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        rows = page.locator(".irow")
        expect(rows).to_have_count(9)  # 4 mock + hair-mod + 4 clothing rows
        # Read-only row has no select
        morph = page.locator(".irow", has_text="Eyes (morph preset)")
        expect(morph.locator("select")).to_have_count(0)
        # Override skin tone -> row marked, revert appears, category badge counts
        skin = page.locator(".irow", has_text="Skin tone")
        skin.locator("select").select_option("03_ca_medium")
        expect(skin).to_have_class(re.compile("overridden"))
        expect(skin.locator("button.revert")).to_be_visible()
        expect(page.locator(".cat", has_text="Skin").locator(".override-count")).to_have_text("1")
        # Search filters rows (hair style + hair color + modded-hair row)
        page.fill("#inspector-search", "hair")
        expect(page.locator(".irow")).to_have_count(3)
        page.fill("#inspector-search", "")
        # Revert clears it
        skin.locator("button.revert").click()
        expect(skin).not_to_have_class(re.compile("overridden"))
        # Reset all after two overrides
        skin.locator("select").select_option("03_ca_medium")
        page.locator(".irow", has_text="Hair color").locator("select").select_option(
            "06_black_carbon"
        )
        page.click("#reset-all")
        expect(page.locator(".irow.overridden")).to_have_count(0)
        # Continue persists via set_overrides and advances
        skin.locator("select").select_option("03_ca_medium")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        assert page.evaluate("() => window.__mockApi._overrides") == {"skin_tone": "03_ca_medium"}
        browser.close()


def test_appearance_modded_hair_flow(webui_server):
    """Picking a CCXL hair mod file sets the hair_mod override, is mutually
    exclusive with the vanilla hair_style dropdown, and shows the
    stay-installed warning."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        hair_mod_row = page.locator(".irow.hair-mod-row")
        expect(hair_mod_row).to_contain_text("—")  # no mod hair yet
        # First set a vanilla style override, then pick a mod file
        style_row = page.locator(".irow", has_text="Hair style")
        style_row.locator("select").select_option("hh_041_pwa__bob")
        expect(style_row).to_have_class(re.compile("overridden"))
        hair_mod_row.locator("button.browse-hair-mod").click()
        expect(hair_mod_row).to_have_class(re.compile("overridden"))
        expect(hair_mod_row).to_contain_text("edie")
        expect(page.locator("main")).to_contain_text("needs this hair mod to stay installed")
        # Mutual exclusion: the vanilla style override was cleared
        expect(style_row).not_to_have_class(re.compile("overridden"))
        # Re-picking a vanilla style clears the mod override
        style_row.locator("select").select_option("hh_041_pwa__bob")
        expect(hair_mod_row).not_to_have_class(re.compile("overridden"))
        # Back to the mod, then Continue persists hair_mod
        hair_mod_row.locator("button.browse-hair-mod").click()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        assert page.evaluate("() => window.__mockApi._overrides") == {"hair_mod": "edie"}
        browser.close()


def test_saved_modded_hair_shows_installed_registration(webui_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.evaluate(
            """() => {
              const original = window.__mockApi.appearance_data.bind(window.__mockApi);
              window.__mockApi.appearance_data = async () => {
                const out = await original();
                out.saved_hair = {
                  state: "registered",
                  selection_label: "b1w_003_wa",
                  mesh_appearance: "teal_ombre",
                  source: "b1whair003ccxl.archive.xl",
                  depot: "b1w\\\\ccxl\\\\hair003\\\\appearances\\\\b1w_003_wa.app",
                };
                return out;
              };
            }"""
        )
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")

        hair = page.locator(".hair-mod-row")
        expect(hair).to_contain_text("b1w_003_wa")
        expect(hair).to_have_class(re.compile("saved-loaded"))
        status = page.locator(".hair-mod-status.loaded")
        expect(status).to_contain_text("Saved hair is installed and registered")
        expect(status).to_contain_text("b1whair003ccxl.archive.xl")
        expect(status).to_contain_text("teal_ombre")
        browser.close()


def test_clothing_picker_flow(webui_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")

        row = page.locator(".irow", has_text="Inner torso")
        expect(row).to_contain_text("t1_024_pwa_tshirt__sweater")
        row.locator("button.browse-garment").click()
        expect(page.locator(".picker")).to_be_visible()
        expect(page.locator(".picker-item.disabled", has_text="GHOST SWEATER")).to_be_visible()
        page.locator(".picker-item", has_text="RED SWEATER").click()

        expect(page.locator(".picker")).to_have_count(0)
        expect(row).to_have_class(re.compile("overridden"))
        expect(row).to_contain_text("RED SWEATER")
        expect(row).to_contain_text("red")
        page.click("text=Continue →")
        assert page.evaluate("() => window.__mockApi._overrides") == {
            "garment_inner_torso": {
                "item_id": "A",
                "name": "RED SWEATER",
                "slot": "inner_torso",
                "mesh": (
                    "base\\characters\\garment\\player_equipment\\torso\\"
                    "t1_024_pwa_tshirt__sweater.mesh"
                ),
                "appearance": "red",
                "occupied_slots": ["inner_torso"],
                "source_kind": "catalog",
                "components": [
                    {
                        "type": "entGarmentSkinnedMeshComponent",
                        "name": "red_sweater",
                        "mesh": (
                            "base\\characters\\garment\\player_equipment\\torso\\"
                            "t1_024_pwa_tshirt__sweater.mesh"
                        ),
                        "appearance": "red",
                        "bind_to": "root",
                        "chunk_mask": "",
                    }
                ],
            }
        }
        browser.close()


def test_exact_clothing_selection_survives_reload_and_can_be_reverted(
    webui_server,
):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")
        row = page.locator(".irow", has_text="Inner torso")
        row.locator("button.browse-garment").click()
        page.locator(".picker-item", has_text="RED SWEATER").click()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")

        page.reload()
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")
        restored = page.locator(".irow", has_text="Inner torso")
        expect(restored).to_have_class(re.compile("overridden"))
        expect(restored).to_contain_text("RED SWEATER")
        expect(restored).to_contain_text("red")

        restored.locator("button.revert").click()
        expect(restored).not_to_have_class(re.compile("overridden"))
        page.click("text=Continue →")
        assert page.evaluate("() => window.__mockApi._overrides") == {}
        browser.close()


def test_clothing_picker_builds_missing_catalog(webui_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.add_init_script(
            """(() => {
              window.__mockApi._catalogBuilt = false;
            })()"""
        )
        page.goto(webui_server)
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")
        page.locator(".irow", has_text="Inner torso").locator(".browse-garment").click()

        prompt = page.locator(".catalog-build-prompt")
        expect(prompt).to_contain_text("Build the vanilla clothing catalog")
        prompt.locator("button", has_text="Build catalog").click()
        expect(page.locator("#picker-search")).to_be_visible()
        expect(page.locator(".picker-item", has_text="RED SWEATER")).to_be_visible()
        browser.close()


def test_legacy_mesh_only_garment_requires_reselection(webui_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.evaluate(
            """() => {
              const original = window.__mockApi.appearance_data.bind(window.__mockApi);
              window.__mockApi.appearance_data = async () => {
                const out = await original();
                out.overrides = {
                  garment_inner_torso:
                    "base\\\\characters\\\\garment\\\\player_equipment\\\\torso\\\\t1_024_pwa_tshirt__sweater.mesh",
                };
                return out;
              };
            }"""
        )
        page.locator(".card.selectable.save-card").first.click()
        page.click("text=Continue →")

        row = page.locator(".irow", has_text="Inner torso")
        expect(row).to_contain_text("Variant unknown — reselect this garment")
        expect(page.get_by_role("button", name="Reselect garment to continue")).to_be_disabled()

        row.locator("button.browse-garment").click()
        page.locator(".picker-item", has_text="RED SWEATER").click()
        expect(row).to_contain_text("RED SWEATER")
        expect(page.get_by_role("button", name="Continue →")).to_be_enabled()
        browser.close()


def test_modded_hair_loading_blocks_progress_until_override_is_ready(webui_server):
    """The slow archive probe must be visible and impossible to bypass."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card", has_text="From scratch").click()
        page.click("#rig-pwa")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        page.get_by_role("button", name="Choose image…").click()

        page.evaluate(
            """() => {
                window.__mockApi.browse_for_hair_mod = () =>
                    new Promise((resolve) => {
                        window.__resolveHairMod = resolve;
                    });
            }"""
        )
        hair_mod_row = page.locator(".irow.hair-mod-row")
        hair_mod_row.locator("button.browse-hair-mod").click()

        expect(hair_mod_row).to_have_attribute("aria-busy", "true")
        expect(hair_mod_row).to_contain_text("Loading…")
        expect(page.locator(".hair-mod-status")).to_contain_text(
            "Loading and validating the hair mod"
        )
        expect(page.get_by_role("button", name="Waiting for hair to load…")).to_be_disabled()
        expect(page.locator(".rail-item", has_text="3 · Build")).to_have_class(re.compile("locked"))

        page.evaluate(
            """() => window.__resolveHairMod({
                ok: true,
                token: "axiom_hair",
                source: "axiom_hair.archive",
                warning: "The NPV needs this hair mod to stay installed.",
            })"""
        )

        expect(hair_mod_row).to_have_attribute("aria-busy", "false")
        expect(hair_mod_row).to_contain_text("axiom_hair")
        continue_button = page.get_by_role("button", name="Continue →")
        expect(continue_button).to_be_enabled()
        continue_button.click()
        page.get_by_role("button", name="Start build").click()
        page.wait_for_function("window.__mockApi._startRequests.length === 1")
        [request] = page.evaluate("window.__mockApi._startRequests")
        assert request["cc_overrides"] == {"hair_mod": "axiom_hair"}
        browser.close()


def test_from_scratch_preset_flow(webui_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)

        page.locator(".card", has_text="From scratch").click()
        page.click("#rig-pwa")
        expect(page.locator("#rig-pma")).to_be_disabled()
        page.click("text=Continue →")

        expect(page.locator("h1")).to_have_text("Appearance")
        page.get_by_role("button", name="Choose image…").click()
        expect(page.locator("main")).to_contain_text("pwa")
        expect(page.locator(".irow")).to_have_count(10)
        cyberware = page.locator(".irow", has_text="Cyberware")
        cyberware.locator("select").select_option(label="Cyberware 02 · 03 ca senna")
        expect(cyberware).to_have_class(re.compile("overridden"))
        expect(page.locator("#npv-name")).to_have_value("Default V")
        expect(page.locator("#output-dir")).to_have_value("/out/DefaultV-pwa")
        page.click("text=Continue →")

        expect(page.locator("h1")).to_have_text("Build")
        page.click("text=Start build")
        page.wait_for_function("window.__mockApi._startRequests.length === 1")
        [request] = page.evaluate("window.__mockApi._startRequests")
        assert request["resume"] is True
        assert request["preset_rig"] == "pwa"
        assert "save_path" not in request
        assert request["cc_overrides"]["cc:cyberware_01"].startswith('{"label":"cyberware_02"')
        browser.close()


def test_library_render_preview_shows_progress_counter(webui_server):
    """While the render bridge call is pending, the button polls progress and
    shows a live counter instead of a bare 'Rendering…'."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=My NPVs")
        page.wait_for_selector(".btn-render-preview")
        page.click(".btn-render-preview")
        page.wait_for_selector("text=Rendering… 12/28", timeout=5000)
        page.wait_for_selector(".preview-strip .preview-img")
        # With a preview now on the card, the button offers to re-run it.
        assert page.locator(".btn-render-preview").first.text_content() == "Re-render preview"
        browser.close()


def test_library_cards_show_build_source(webui_server):
    """Each My NPVs card states what it was built from — a save file or a
    from-scratch preset — so the user knows which NPV they are previewing."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=My NPVs")
        page.wait_for_selector(".mod-source")
        sources = page.eval_on_selector_all(".mod-source", "els => els.map(e => e.textContent)")
        assert any(s.startswith("From save:") for s in sources), sources
        assert any("preset" in s.lower() and "pwa" in s.lower() for s in sources), sources
        browser.close()


def test_preview_states_untextured_fidelity(webui_server):
    """The rendered preview is labelled as untextured so a correct build with
    invisible colour choices is not mistaken for a wrong appearance."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=My NPVs")
        page.wait_for_selector(".btn-render-preview")
        page.locator(".btn-render-preview").first.click()
        page.wait_for_selector(".preview-strip .preview-img")
        note = page.locator(".preview-fidelity").first
        assert "colour" in note.text_content().lower()
        browser.close()


def test_library_shows_previously_rendered_preview(webui_server):
    """A preview already on disk appears without re-running a 15-minute render."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=My NPVs")
        first = page.locator(".grid .card").first
        expect(first.locator(".preview-img")).to_have_count(1)
        # The build with no preview on disk shows none
        expect(page.locator(".grid .card").nth(1).locator(".preview-img")).to_have_count(0)
        browser.close()


def test_render_preview_sets_time_expectation(webui_server):
    """A render takes many minutes. Say so before the user starts one, so a
    working render is not mistaken for a hang."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.click("text=My NPVs")
        btn = page.locator(".btn-render-preview").first
        assert "minute" in (btn.get_attribute("title") or "").lower()
        browser.close()
