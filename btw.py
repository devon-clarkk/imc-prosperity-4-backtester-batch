"""
btw.py — Batch Backtesting Wrapper
====================================
Commands:
  python btw.py register <alias> <round> [--desc "..."]   Register a dataset alias
  python btw.py unregister <alias>                         Remove a registered alias
  python btw.py list                                       Show all registered aliases
  python btw.py run <config.json>                          Run a batch backtest config

Config JSON format:
  {
    "name": "Shock Test Suite",
    "algorithms": [
      {"path": "..\\algo\\Control.py",   "alias": "Control"},
      {"path": "..\\algo\\FailSafe.py",  "alias": "FailSafe"}
    ],
    "datasets": ["normal", "gradual_shock", "permanent_crash"],
    "day": null
  }

  "day" is optional — null runs all days, or specify e.g. "0" or "-2" for one day only.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REGISTRY_FILE = Path(__file__).parent / "btw_registry.json"
BACKTESTER_DIR = Path(__file__).parent


# ─── Registry helpers ────────────────────────────────────────────

def load_registry() -> dict:
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    return {}


def save_registry(registry: dict):
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


# ─── Commands ────────────────────────────────────────────────────

def cmd_register(args):
    registry = load_registry()
    alias = args.alias
    round_num = int(args.round_number)
    desc = args.desc or ""

    if alias in registry:
        old = registry[alias]
        print(f"Overwriting existing alias '{alias}' (was Round {old['round']})")

    registry[alias] = {
        "round": round_num,
        "description": desc,
        "registered": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_registry(registry)
    print(f"[OK] Registered '{alias}' -> Round {round_num}" + (f"  ({desc})" if desc else ""))


def cmd_unregister(args):
    registry = load_registry()
    alias = args.alias
    if alias not in registry:
        print(f"Alias '{alias}' not found.")
        sys.exit(1)
    del registry[alias]
    save_registry(registry)
    print(f"[OK] Removed alias '{alias}'")


def cmd_list(args):
    registry = load_registry()
    if not registry:
        print("No aliases registered.")
        print("  Use: python btw.py register <alias> <round> [--desc \"...\"]")
        return

    print(f"\n{'Alias':<22} {'Round':<8} {'Description':<30} {'Registered'}")
    print("-" * 75)
    for alias, info in sorted(registry.items(), key=lambda x: x[1]["round"]):
        print(f"{alias:<22} {info['round']:<8} {info.get('description',''):<30} {info.get('registered','')}")
    print()


def cmd_run(args):
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    registry = load_registry()
    algorithms = config.get("algorithms", [])
    datasets   = config.get("datasets", [])
    day_filter = config.get("day", None)

    if not algorithms:
        print("Config has no algorithms defined.")
        sys.exit(1)
    if not datasets:
        print("Config has no datasets defined.")
        sys.exit(1)

    # Resolve aliases → round numbers
    resolved_datasets = []
    for ds in datasets:
        if ds not in registry:
            print(f"ERROR: alias '{ds}' not registered.")
            print(f"  Register it with: python btw.py register {ds} <round_number>")
            sys.exit(1)
        resolved_datasets.append((ds, registry[ds]["round"], registry[ds].get("description", "")))

    suite_name = config.get("name", config_path.stem)
    print(f"\n{'='*65}")
    print(f"  {suite_name}")
    print("=" * 65)
    print(f"  Algorithms : {', '.join(a.get('alias', Path(a['path']).stem) for a in algorithms)}")
    print(f"  Datasets   : {', '.join(d[0] for d in resolved_datasets)}")
    print(f"  Day filter : {day_filter if day_filter is not None else 'all'}")
    print(f"{'='*65}\n")

    # Build PYTHONPATH so algorithms can import datamodel
    env = os.environ.copy()
    pythonpath_extra = str(BACKTESTER_DIR / "prosperity4bt")
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{pythonpath_extra}{os.pathsep}{existing_pp}" if existing_pp else pythonpath_extra

    # Create a timestamped run folder for logs
    run_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_suite = "".join(c if c.isascii() and (c.isalnum() or c in "-_ ") else "_" for c in suite_name).strip()
    run_folder = BACKTESTER_DIR / "backtests" / f"{run_ts}_{safe_suite}"
    run_folder.mkdir(parents=True, exist_ok=True)
    print(f"Run folder: {run_folder}\n")

    # results[algo_alias][ds_alias] = {"total": float, "days": {label: float}, "log": Path}
    results = {}

    for algo in algorithms:
        algo_path = algo["path"]
        algo_alias = algo.get("alias", Path(algo_path).stem)
        results[algo_alias] = {}

        for ds_alias, round_num, ds_desc in resolved_datasets:
            round_day_arg = (
                f"{round_num}-{day_filter}" if day_filter is not None else str(round_num)
            )
            suffix = f"(round {round_num}" + (f", day {day_filter}" if day_filter is not None else "") + ")"
            print(f">> {algo_alias} x {ds_alias}  {suffix}")

            # Name the log file after the algo and dataset
            log_name = f"{algo_alias}__{ds_alias}.log"
            log_path = run_folder / log_name

            cmd = [
                sys.executable, "-m", "prosperity4bt",
                algo_path,
                round_day_arg,
                "--out", str(log_path),
                "--no-progress",
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(BACKTESTER_DIR),
            )

            output = proc.stdout + proc.stderr
            total  = _parse_total(output)
            days   = _parse_days(output)

            results[algo_alias][ds_alias] = {"total": total, "days": days, "log": log_path}

            if total is not None:
                for day_label, day_profit in days.items():
                    print(f"     {day_label}: {day_profit:>12,.0f}")
                print(f"   {'Total':.<30} {total:>12,.0f}")
                print(f"   Log: {log_name}\n")
            else:
                print(f"   [FAIL] Run failed - output below:")
                print("   " + "\n   ".join(output.strip().splitlines()[-15:]))
                print()

    _print_summary(results, algorithms, datasets)

    # Save markdown report — always into the run folder, plus any custom path
    md = _build_markdown(suite_name, results, algorithms, datasets, day_filter, registry, run_folder)
    md_path = run_folder / "results.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[OK] Report saved to: {md_path.resolve()}")

    # Also save to the custom output path from config or --save flag if specified
    save_path = getattr(args, "save", None) or config.get("output")
    if save_path:
        custom_path = Path(save_path)
        custom_path.parent.mkdir(parents=True, exist_ok=True)
        with open(custom_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[OK] Report also saved to: {custom_path.resolve()}")


# ─── Output parsers ──────────────────────────────────────────────

def _parse_total(output: str) -> float | None:
    # There are multiple "Total profit:" lines (one per day + one grand total at end).
    # We want the last one, which is the grand total.
    result = None
    for line in output.splitlines():
        if "Total profit:" in line:
            try:
                result = float(line.split("Total profit:")[-1].strip().replace(",", ""))
            except ValueError:
                pass
    return result


def _parse_days(output: str) -> dict:
    days = {}
    for line in output.splitlines():
        line = line.strip()
        if (
            ":" in line
            and "Total" not in line
            and "Backtesting" not in line
            and "running" not in line.lower()
            and "round" in line.lower()
            and "day" in line.lower()
        ):
            try:
                key, val = line.rsplit(":", 1)
                days[key.strip()] = float(val.strip().replace(",", ""))
            except ValueError:
                pass
    return days


# ─── Markdown report ─────────────────────────────────────────────

def _build_markdown(suite_name: str, results: dict, algorithms: list, datasets: list,
                    day_filter, registry: dict, run_folder: Path = None) -> str:
    algo_aliases = [a.get("alias", Path(a["path"]).stem) for a in algorithms]
    lines = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append(f"# {suite_name}")
    lines.append(f"")
    lines.append(f"**Generated:** {ts}  ")
    lines.append(f"**Day filter:** {day_filter if day_filter is not None else 'all'}  ")
    if run_folder:
        lines.append(f"**Run folder:** `{run_folder}`  ")
    lines.append(f"")

    # Algorithm paths
    lines.append("## Algorithms")
    lines.append("")
    for a in algorithms:
        alias = a.get("alias", Path(a["path"]).stem)
        lines.append(f"- **{alias}**: `{a['path']}`")
    lines.append("")

    # Dataset registry info
    lines.append("## Datasets")
    lines.append("")
    lines.append("| Alias | Round | Description |")
    lines.append("|-------|-------|-------------|")
    for ds in datasets:
        info = registry.get(ds, {})
        lines.append(f"| {ds} | {info.get('round','?')} | {info.get('description','')} |")
    lines.append("")

    # Per-run breakdown
    lines.append("## Per-Run Breakdown")
    lines.append("")
    for algo in algorithms:
        alias = algo.get("alias", Path(algo["path"]).stem)
        lines.append(f"### {alias}")
        lines.append("")
        # Collect all day labels across datasets
        all_day_labels = []
        for ds in datasets:
            for lbl in results.get(alias, {}).get(ds, {}).get("days", {}).keys():
                if lbl not in all_day_labels:
                    all_day_labels.append(lbl)

        if all_day_labels:
            header = "| Dataset | " + " | ".join(all_day_labels) + " | **Total** |"
            sep    = "|---------|" + "|".join(["------"] * len(all_day_labels)) + "|-----------|"
            lines.append(header)
            lines.append(sep)
            for ds in datasets:
                r = results.get(alias, {}).get(ds, {})
                day_vals = " | ".join(
                    f"{r.get('days', {}).get(lbl, 0):>10,.0f}" for lbl in all_day_labels
                )
                total = r.get("total")
                total_str = f"**{total:,.0f}**" if total is not None else "ERROR"
                lines.append(f"| {ds} | {day_vals} | {total_str} |")
        else:
            lines.append("_No data_")
        lines.append("")

    # Summary comparison table
    lines.append("## Summary — Total Profit Comparison")
    lines.append("")
    header = "| Dataset | " + " | ".join(f"**{a}**" for a in algo_aliases) + " |"
    sep    = "|---------|" + "|".join(["------:"] * len(algo_aliases)) + "|"
    lines.append(header)
    lines.append(sep)
    for ds in datasets:
        row = f"| {ds} |"
        for alias in algo_aliases:
            val = results.get(alias, {}).get(ds, {}).get("total")
            row += f" {val:,.0f} |" if val is not None else " ERROR |"
        lines.append(row)
    lines.append("")

    # Log files
    if run_folder:
        lines.append("## Output Logs")
        lines.append("")
        lines.append("| Trader | Dataset | Log File |")
        lines.append("|--------|---------|----------|")
        for algo in algorithms:
            alias = algo.get("alias", Path(algo["path"]).stem)
            for ds in datasets:
                log = results.get(alias, {}).get(ds, {}).get("log")
                log_name = log.name if log else "N/A"
                lines.append(f"| {alias} | {ds} | `{log_name}` |")
        lines.append("")

    # Delta table vs baseline
    if len(datasets) > 1:
        baseline = datasets[0]
        lines.append(f"## Delta vs Baseline (`{baseline}`)")
        lines.append("")
        lines.append(f"Positive = better than baseline, Negative = worse.")
        lines.append("")
        header = "| Dataset | " + " | ".join(f"**{a}**" for a in algo_aliases) + " |"
        lines.append(header)
        lines.append(sep)
        for ds in datasets[1:]:
            row = f"| {ds} |"
            for alias in algo_aliases:
                base = results.get(alias, {}).get(baseline, {}).get("total")
                curr = results.get(alias, {}).get(ds, {}).get("total")
                if base is not None and curr is not None:
                    delta = curr - base
                    sign = "+" if delta >= 0 else ""
                    row += f" {sign}{delta:,.0f} |"
                else:
                    row += " N/A |"
            lines.append(row)
        lines.append("")

    return "\n".join(lines)


# ─── Summary table ───────────────────────────────────────────────

def _print_summary(results: dict, algorithms: list, datasets: list):
    algo_aliases = [a.get("alias", Path(a["path"]).stem) for a in algorithms]
    col_w = 16
    width = 22 + col_w * len(algo_aliases)

    print("=" * width)
    print("  SUMMARY — Total Profit")
    print("=" * width)
    header = f"  {'Dataset':<20}" + "".join(f"{a:>{col_w}}" for a in algo_aliases)
    print(header)
    print("-" * width)

    for ds in datasets:
        row = f"  {ds:<20}"
        for algo in algo_aliases:
            val = results.get(algo, {}).get(ds, {}).get("total")
            row += f"{val:>{col_w},.0f}" if val is not None else f"{'ERROR':>{col_w}}"
        print(row)

    print("-" * width)
    # Delta row vs first dataset (baseline)
    if len(datasets) > 1:
        baseline = datasets[0]
        for ds in datasets[1:]:
            label = f"{ds} vs {baseline}"
            row = f"  {label:<20}"
            for algo in algo_aliases:
                base = results.get(algo, {}).get(baseline, {}).get("total")
                curr = results.get(algo, {}).get(ds, {}).get("total")
                if base is not None and curr is not None:
                    delta = curr - base
                    sign = "+" if delta >= 0 else ""
                    row += f"{sign}{delta:>{col_w-1},.0f}"
                else:
                    row += f"{'N/A':>{col_w}}"
            print(row)
        print("-" * width)
    print()


# ─── CLI entry point ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="btw",
        description="Batch Backtesting Wrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # register
    p_reg = sub.add_parser("register", help="Register a dataset alias → round number")
    p_reg.add_argument("alias", help="Alias name, e.g. 'normal' or 'permanent_crash'")
    p_reg.add_argument("round_number", help="Round number in the backtester")
    p_reg.add_argument("--desc", default="", help="Optional description")
    p_reg.set_defaults(func=cmd_register)

    # unregister
    p_unreg = sub.add_parser("unregister", help="Remove a registered alias")
    p_unreg.add_argument("alias", help="Alias to remove")
    p_unreg.set_defaults(func=cmd_unregister)

    # list
    p_list = sub.add_parser("list", help="Show all registered aliases")
    p_list.set_defaults(func=cmd_list)

    # run
    p_run = sub.add_parser("run", help="Run a batch backtest from a JSON config file")
    p_run.add_argument("config", help="Path to JSON config file")
    p_run.add_argument("--save", default=None, metavar="FILE",
                       help="Save results as a markdown report (overrides config 'output' field)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
