# IMC Prosperity 4 Backtester — with Batch Wrapper (`btw`)

This is a fork of [kevin-fu1/imc-prosperity-4-backtester](https://github.com/kevin-fu1/imc-prosperity-4-backtester) with one addition: **`btw.py`**, a batch backtesting wrapper that lets you test multiple algorithms across multiple datasets in a single command.

Everything in the original backtester works exactly as before. `btw.py` is purely additive — drop it into any clone of the original repo and it just works.

---

## `btw.py` — Batch Backtesting Wrapper

Instead of running one algorithm against one dataset at a time, define a JSON config and run an entire test suite at once. You get a live console summary and an auto-generated Markdown report.

> Requires Python 3.10+

---

### Step 1 — Add your data

The backtester loads price and trade CSVs from numbered folders inside `prosperity4bt/resources/`. Each dataset gets its own folder:

```
prosperity4bt/resources/
  round6/
    prices_round_6_day_-2.csv
    prices_round_6_day_-1.csv
    prices_round_6_day_0.csv
    trades_round_6_day_-2.csv
    trades_round_6_day_-1.csv
    trades_round_6_day_0.csv
```

Files must follow the naming convention `prices_round_<N>_day_<D>.csv` / `trades_round_<N>_day_<D>.csv`, where `<N>` matches the folder number and `<D>` is the day (`-2`, `-1`, `0`, etc.).

> **Important:** IMC Prosperity 4 has 5 official rounds (rounds 0–5). **Always use round numbers 6 and above for custom or synthetic datasets** to avoid collisions with official data.

You also need to tell the backtester which days exist for your round. Add a branch to the `get_days` method in `prosperity4bt/tools/data_reader.py`:

```python
if round == 6:
    return [-2, -1, 0]
```

---

### Step 2 — Register your datasets

`btw` maps friendly alias names to round numbers so your configs stay readable. The registry is stored locally in `btw_registry.json` (gitignored — each user maintains their own).

```bash
python btw.py register round1        1 --desc "Round 1 official data"
python btw.py register gradual_shock 6 --desc "Gradual -700 shock scenario"
```

Check what's registered:
```bash
python btw.py list
```

See `btw_registry.example.json` for the registry file format.

---

### Step 3 — Create a config file

Define which algorithms to test and which datasets to run them against. See `btw_config.example.json` for a ready-to-copy template.

```json
{
  "name": "My Algorithm Comparison",
  "algorithms": [
    {"path": "../algos/MyTrader.py",  "alias": "MyTrader"},
    {"path": "../algos/Baseline.py",  "alias": "Baseline"}
  ],
  "datasets": ["round1", "gradual_shock"],
  "day": null,
  "output": "../results/my_comparison.md"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Suite name — used in report headers and output folder names |
| `algorithms` | list | yes | Each entry: `{"path": "...", "alias": "..."}` |
| `datasets` | list | yes | Registered alias names — first entry is the baseline for delta comparisons |
| `day` | string \| null | no | `null` runs all days; `"0"` or `"-2"` filters to one day |
| `output` | string | no | Extra path to copy the Markdown report to |

---

### Step 4 — Run

```bash
python btw.py run my_config.json
```

### What you get

- Live per-run output in the console as each backtest completes
- A **summary table** showing total profit for every algorithm × dataset combination, with deltas vs the baseline
- A **`results.md` Markdown report** saved automatically into a timestamped folder under `backtests/`

---

### Full CLI reference

```
python btw.py register <alias> <round> [--desc "..."]   Register a dataset alias
python btw.py unregister <alias>                         Remove an alias
python btw.py list                                       Show all registered aliases
python btw.py run <config.json> [--save <file>]          Run a batch test suite
```

---
---

## Original Backtester — Documentation

> The following is the original documentation from [kevin-fu1/imc-prosperity-4-backtester](https://github.com/kevin-fu1/imc-prosperity-4-backtester), preserved here for reference.

This repository contains a Python-based backtester designed in preparation for the [IMC Prosperity 4 challenge](https://prosperity.imc.com/).

**Key Notes:**
* **Origin:** This project is heavily based on [jmerle/imc-prosperity-3-backtester](https://github.com/jmerle/imc-prosperity-3-backtester), but it has been rewritten to utilize a more Object-Oriented Programming (OOP) style.
* **Current Status:** The codebase is up to date with the Prosperity 4 tutorial round.
* **License:** MIT License.

---

### Basic usage

Run the backtester on an algorithm using all data from round 0:
```bash
python -m prosperity4bt <path to algorithm file> 0
```

Run the backtester on an algorithm using all data from round 0, day `-2`:
```bash
python -m prosperity4bt <path to algorithm file> 0--2
```

If you see `No module named 'datamodel'`, set PYTHONPATH to the folder containing `datamodel.py`:
```bash
$env:PYTHONPATH="<path to>\imc-prosperity-4-backtester\prosperity4bt"
```

**Run/Debug from PyCharm** — Add Run/Debug Configuration:

![PyCharm Config](images/pycharm.png)

---

### Overall Structure & How It Works

The architecture is modularized to cleanly separate data loading, simulation execution, and order matching:

![Backtester Architecture](images/backtester.png)

#### 1. The `BackTester` (Main Controller)
* Loads the algorithm module, iterates through rounds and days, calls `TestRunner` for each day, merges results, and writes the output log.

#### 2. The `TestRunner` (Daily Simulator)
For each timestamp in the day:
1. Initializes `TradingState` and passes it to the algorithm
2. Captures orders and `TraderData` returned by the algorithm
3. Logs activity via `ActivityLogCreator`
4. Matches orders against the historical order book via `OrderMatchMaker`

#### 3. Core Helper Modules
* **`BackDataReader`** — Ingests price and trade CSVs into `BacktestData` objects
* **`ActivityLogCreator`** — Formats activity logs for analysis and debugging
* **`OrderMatchMaker`** — Simulates exchange order matching and position updates

---

### Data Models

* **`datamodel.py`** — Shared between the backtester and your algorithm. **Do not modify** — changes may break compatibility with the official Prosperity environment.
* **`models/input.py`** — Defines how raw CSV data is parsed into `BacktestData`
* **`models/output.py`** — Defines `BacktestResult` and the output log format

**Price Data:**

![Price Data](images/price_data.png)

**Trade Data:**

![Trade Data](images/trade_data.png)

**Backtest Data:**

![Backtest Data](images/back_test_data.png)

**Backtest Result:**

![Backtest Result](images/result_final_stage.png)

**Output Log File:**

![Output Log File](images/out_put_log_file.png)

If you use the Logger class from the [Visualizer](https://github.com/kevin-fu1/imc-prosperity-4-visualizer), the `lambda_log` will look like this:

![Lambda Log](images/lambda_log_data.png)
