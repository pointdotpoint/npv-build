import argparse
import sys
from pathlib import Path
from .config import load_config, save_config, get_cache_dir
from .orchestrator import run_orchestrator

def main():
    parser = argparse.ArgumentParser(description="NPV Automation - Build a mod package from a Cyberpunk 2077 save.")
    parser.add_argument("save_dat", metavar="<sav.dat>", nargs="?", default=None, help="Path to the source save file (or omit if using --cc-json).")
    parser.add_argument("npv_name", metavar="<NPV name>", help="User-facing label for the NPC.")
    parser.add_argument("--output", required=True, metavar="<dir>", help="Root of the produced Mod package install tree.")
    parser.add_argument("--cc-json", metavar="<path>", help="Use a CC dump produced by the npv_dumper CET script instead of parsing a sav.dat.")
    parser.add_argument("--game-dir", metavar="<path>", help="Path to the Cyberpunk 2077 installation.")
    parser.add_argument("--template-cache", metavar="<dir>", help="Override the template cache location.")
    parser.add_argument("--clear-cache", action="store_true", help="Wipe the Template cache before running.")
    parser.add_argument("--hair", metavar="<id|none>", help="Override hair: a vanilla hair number (e.g. 1 -> hh_001), a modded hair name (e.g. 'zara'), or 'none'.")
    parser.add_argument("--skin", metavar="<tone>", default="01_ca_pale", help="Skin tone meshAppearance for head and body (default: 01_ca_pale for Ava Skin pale). Examples: 01_ca_pale, 02_ca_limestone, 03_ca_senna, 04_ca_almond, 05_ca_coffee.")
    parser.add_argument("--garment", metavar="<depot_path>", action="append", default=[], help="Add a garment part .ent depot path to the NPV (repeatable). E.g. base\\\\characters\\\\garment\\\\...\\\\t1_097_pwa_tank__corset_doll_prostitute.ent")

    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument("-v", action="count", default=0, help="Verbosity level 1.")
    verbosity_group.add_argument("-vv", action="store_const", dest="v", const=2, help="Verbosity level 2.")

    args = parser.parse_args()

    # Load and update config
    config = load_config()
    if args.game_dir:
        config["game_dir"] = str(Path(args.game_dir).resolve())
        save_config(config)
    
    game_dir = config.get("game_dir")
    
    if args.template_cache:
        template_cache = Path(args.template_cache).resolve()
    else:
        template_cache = get_cache_dir() / "templates"

    if not args.save_dat and not args.cc_json:
        parser.error("Either <sav.dat> or --cc-json must be provided.")

    try:
        out_dir = run_orchestrator(
            save_path=Path(args.save_dat).resolve() if args.save_dat else None,
            cc_json_path=Path(args.cc_json).resolve() if args.cc_json else None,
            npv_name=args.npv_name,
            output_dir=Path(args.output).resolve(),
            game_dir=Path(game_dir) if game_dir else None,
            template_cache=template_cache,
            clear_cache=args.clear_cache,
            verbosity=args.v,
            hair_override=args.hair,
            skin_override=args.skin,
            garments=args.garment,
        )
        readme_path = Path(args.output).resolve() / "README_GUI_STEPS.md"
        if readme_path.exists():
            print("\n" + "=" * 60)
            print("PROJECT READY — Open in WolvenKit GUI")
            print("=" * 60)
            print(f"\nProject dir: {Path(args.output).resolve()}")
            print(f"Instructions: {readme_path}")
            print(f"\nQuick summary:")
            print(f"  1. Open project in WolvenKit GUI")
            print(f"  2. Add components from npv_components.json to the .app")
            print(f"  3. Set parentTransform.bindName = root on each")
            print(f"  4. Set skinning.bindName = root on each")
            print(f"  5. Pack mod in WolvenKit GUI")
            print(f"  6. Copy archive/ + bin/ to game dir")
        elif args.v == 0:
            print(out_dir)
    except Exception as e:
        # Assuming run_orchestrator raises a structured error with a tag
        if hasattr(e, "module_name"):
            print(f"Error in {e.module_name}: {e}", file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
