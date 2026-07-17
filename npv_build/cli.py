import argparse
import sys
from datetime import datetime
from pathlib import Path

from .config import get_cache_dir, load_config, save_config
from .core.errors import NpvError
from .core.logging_setup import configure_logging
from .core.pipeline import BuildRequest, PipelineService
from .gen_mapping import format_report, mapping_report
from .orchestrator import run_orchestrator
from .save_probe import format_probe, probe_save


def _default_log_file(output_dir: Path) -> Path:
    return output_dir / "logs" / f"build-{datetime.now():%Y%m%d-%H%M%S}.log"


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="NPV Automation - Build a mod package from a Cyberpunk 2077 save."
    )
    parser.add_argument(
        "save_dat",
        metavar="<sav.dat>",
        nargs="?",
        default=None,
        help="Path to the source save file (or omit if using --cc-json).",
    )
    parser.add_argument(
        "npv_name",
        metavar="<NPV name>",
        nargs="?",
        default=None,
        help="User-facing label for the NPC.",
    )
    parser.add_argument(
        "--output", metavar="<dir>", help="Root of the produced Mod package install tree."
    )
    parser.add_argument(
        "--probe-save",
        metavar="<sav.dat>",
        help="Print header version, patch mapping, and CC node facts for a save file, then exit.",
    )
    parser.add_argument(
        "--mapping-report",
        action="store_true",
        help="Diff the vendored CC mapping against the game's live asset index "
        "(missing/unmapped head parts), then exit. Unmapped candidates are "
        "scoped to head-preset basehead stems only (h0_/he_/ht_/heb_); hair, "
        "tattoo, facial-hair, and item .ent files are resolved separately "
        "and are not candidates here.",
    )
    parser.add_argument(
        "--mapping-patch",
        metavar="<patch>",
        default="2.13",
        help="Mapping patch version to check with --mapping-report (default: 2.13).",
    )
    parser.add_argument(
        "--cc-json",
        metavar="<path>",
        help="Use a CC dump produced by the npv_dumper CET script instead of parsing a sav.dat.",
    )
    parser.add_argument(
        "--game-dir", metavar="<path>", help="Path to the Cyberpunk 2077 installation."
    )
    parser.add_argument(
        "--template-cache", metavar="<dir>", help="Override the template cache location."
    )
    parser.add_argument(
        "--clear-cache", action="store_true", help="Wipe the Template cache before running."
    )
    parser.add_argument(
        "--hair",
        metavar="<id|none>",
        help="Override hair: a vanilla hair number (e.g. 1 -> hh_001), a modded hair name (e.g. 'zara'), or 'none'.",
    )
    parser.add_argument(
        "--skin",
        metavar="<tone>",
        default=None,
        help="Skin tone meshAppearance override for head and body (e.g. 01_ca_pale, 02_ca_limestone). If not specified, falls back to the character's skin tone in the save file.",
    )
    parser.add_argument(
        "--garment",
        metavar="<depot_path>",
        action="append",
        default=[],
        help="Add a garment part .ent depot path to the NPV (repeatable). E.g. base\\\\characters\\\\garment\\\\...\\\\t1_097_pwa_tank__corset_doll_prostitute.ent",
    )

    head_group = parser.add_mutually_exclusive_group()
    head_group.add_argument(
        "--head-glb",
        metavar="<path>",
        help="Use your own Blender-edited head GLB instead of baking face morphs. "
        "We import it to .mesh and restore materials/skinning.",
    )
    head_group.add_argument(
        "--head-mesh",
        metavar="<path>",
        help="Use your own finished cooked .mesh as V's head. Skips Blender AND "
        "WolvenKit import — the mesh must already have intact skinning/rig.",
    )
    parser.add_argument(
        "--heb-mesh",
        metavar="<path>",
        help="Optional skin-detail (heb_) layer to accompany --head-glb/--head-mesh. "
        "If omitted, the heb_ component is dropped.",
    )
    parser.add_argument(
        "--no-restore-head-materials",
        action="store_true",
        help="With --head-mesh: keep the materials baked into your .mesh instead of "
        "restoring stock head materials.",
    )
    parser.add_argument(
        "--dump-head-glb",
        metavar="<path>",
        help="Export the stock head GLB for editing (then feed back via --head-glb) "
        "and exit. Requires --game-dir; needs a body rig.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previous build, skipping stages whose inputs are unchanged.",
    )
    parser.add_argument(
        "--log-file",
        metavar="<path>",
        help="Write logs to this file instead of the default output_dir/logs/build-<timestamp>.log.",
    )

    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument("-v", action="count", default=0, help="Verbosity level 1.")
    verbosity_group.add_argument(
        "-vv", action="store_const", dest="v", const=2, help="Verbosity level 2."
    )

    args = parser.parse_args(argv)

    if args.probe_save:
        try:
            info = probe_save(Path(args.probe_save))
            print(format_probe(info))
            return
        except NpvError as e:
            print(e.user_message, file=sys.stderr)
            if e.remediation:
                print(e.remediation, file=sys.stderr)
            sys.exit(1)

    # Shift single positional arg to npv_name if cc_json or dump_head_glb is present
    if args.save_dat and not args.npv_name:
        if args.cc_json or args.dump_head_glb:
            args.npv_name = args.save_dat
            args.save_dat = None

    # Load and update config
    config = load_config()
    if args.game_dir:
        config["game_dir"] = str(Path(args.game_dir).resolve())
        save_config(config)

    game_dir = config.get("game_dir")

    if args.mapping_report:
        if not game_dir:
            parser.error("--mapping-report requires --game-dir (or a configured game_dir).")
        try:
            report = mapping_report(Path(game_dir), mapping_patch=args.mapping_patch)
            print(format_report(report))
            return
        except NpvError as e:
            print(e.user_message, file=sys.stderr)
            if e.remediation:
                print(e.remediation, file=sys.stderr)
            sys.exit(1)

    # Validate BYO head flags combinations
    if args.no_restore_head_materials and not args.head_mesh:
        parser.error("--no-restore-head-materials is only valid with --head-mesh")
    if args.heb_mesh and not (args.head_glb or args.head_mesh):
        parser.error("--heb-mesh requires --head-glb or --head-mesh")

    if args.head_glb:
        path = Path(args.head_glb)
        if not path.exists() or not path.is_file():
            parser.error(f"user head not found: {args.head_glb}")
        if path.suffix.lower() != ".glb":
            parser.error(f"Expected a .glb file for --head-glb, got {path.suffix}")

    if args.head_mesh:
        path = Path(args.head_mesh)
        if not path.exists() or not path.is_file():
            parser.error(f"user head not found: {args.head_mesh}")
        if path.suffix.lower() != ".mesh":
            parser.error(f"Expected a .mesh file for --head-mesh, got {path.suffix}")

    if args.heb_mesh:
        path = Path(args.heb_mesh)
        if not path.exists() or not path.is_file():
            parser.error(f"user heb mesh not found: {args.heb_mesh}")
        if path.suffix.lower() != ".mesh":
            parser.error(f"Expected a .mesh file for --heb-mesh, got {path.suffix}")

    if args.dump_head_glb and not game_dir:
        parser.error("--dump-head-glb requires --game-dir")

    if not args.dump_head_glb:
        if not args.npv_name:
            parser.error("the following arguments are required: <NPV name>")
        if not args.output:
            parser.error("the following arguments are required: --output")
        if not args.save_dat and not args.cc_json:
            parser.error("Either <sav.dat> or --cc-json must be provided.")

    if args.template_cache:
        template_cache = Path(args.template_cache).resolve()
    else:
        template_cache = get_cache_dir() / "templates"

    output_dir = Path(args.output).resolve() if args.output else None
    log_file = (
        Path(args.log_file).resolve()
        if args.log_file
        else (_default_log_file(output_dir) if output_dir else None)
    )
    configure_logging(verbosity=args.v, log_file=log_file)

    try:
        if args.dump_head_glb:
            out_dir = run_orchestrator(
                save_path=Path(args.save_dat).resolve() if args.save_dat else None,
                cc_json_path=Path(args.cc_json).resolve() if args.cc_json else None,
                npv_name=args.npv_name,
                output_dir=output_dir,
                game_dir=Path(game_dir) if game_dir else None,
                template_cache=template_cache,
                clear_cache=args.clear_cache,
                verbosity=args.v,
                hair_override=args.hair,
                skin_override=args.skin,
                garments=args.garment,
                user_head_glb=Path(args.head_glb).resolve() if args.head_glb else None,
                user_head_mesh=Path(args.head_mesh).resolve() if args.head_mesh else None,
                user_heb_mesh=Path(args.heb_mesh).resolve() if args.heb_mesh else None,
                restore_head_materials=not args.no_restore_head_materials,
                dump_head_glb=Path(args.dump_head_glb).resolve(),
            )
        else:
            req = BuildRequest(
                save_path=Path(args.save_dat).resolve() if args.save_dat else None,
                npv_name=args.npv_name,
                output_dir=output_dir,
                game_dir=Path(game_dir) if game_dir else None,
                template_cache=template_cache,
                clear_cache=args.clear_cache,
                cc_json_path=Path(args.cc_json).resolve() if args.cc_json else None,
                hair_override=args.hair,
                skin_override=args.skin,
                garments=args.garment,
                user_head_glb=Path(args.head_glb).resolve() if args.head_glb else None,
                user_head_mesh=Path(args.head_mesh).resolve() if args.head_mesh else None,
                user_heb_mesh=Path(args.heb_mesh).resolve() if args.heb_mesh else None,
                restore_head_materials=not args.no_restore_head_materials,
                resume=args.resume,
            )
            result = PipelineService().build(req)
            out_dir = result.output_dir
        readme_path = Path(args.output).resolve() / "README_GUI_STEPS.md"
        if readme_path.exists():
            print("\n" + "=" * 60)
            print("PROJECT READY — Open in WolvenKit GUI")
            print("=" * 60)
            print(f"\nProject dir: {Path(args.output).resolve()}")
            print(f"Instructions: {readme_path}")
            print("\nQuick summary:")
            print("  1. Open project in WolvenKit GUI")
            print("  2. Add components from npv_components.json to the .app")
            print("  3. Set parentTransform.bindName = root on each")
            print("  4. Set skinning.bindName = root on each")
            print("  5. Pack mod in WolvenKit GUI")
            print("  6. Copy archive/ + bin/ to game dir")
        elif args.v == 0:
            print(out_dir)
    except NpvError as e:
        print(e.user_message, file=sys.stderr)
        if e.remediation:
            print(e.remediation, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
