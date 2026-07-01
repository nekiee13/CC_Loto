# User Manual — DynaMix Lottery Forecasting

This guide shows you how to use the app. You do not need to be a coder.
Follow the steps in order. Copy each command and run it.

---

## 1. What this app does

The app looks at past lottery draws. It learns from them. Then it guesses the
next draw. It gives you up to 5 "tickets" to play.

It works in three parts:

1. **Read the data.** It reads your file of past draws.
2. **Train.** It studies the whole history. This is the slow part.
3. **Forecast.** It makes a guess for the next draw.

You run "train" once in a while. You run "forecast" often.

> **Note:** No tool can truly predict the lottery. This app finds patterns for
> fun and study. Play safe. Never bet money you cannot lose.

---

## 2. Words to know

Here are the words this guide uses. They are simple.

- **Draw / round** — one lottery event. One row in your data file.
- **DATA.csv** — the file with all past draws. You keep it up to date.
- **Training** — the app reads all draws and learns from them. Slow.
- **StatGrid** — the notes the app saves after training. It reuses them later.
- **Forecast / projection** — the app's guess for the next draw. Fast.
- **Ticket** — one set of numbers to play. You get up to 5.
- **Run** — one saved job with its own folder and name.
- **Flag** — an extra word you add to a command, like `--horizon 5`. It
  changes how the command works.

---

## 3. Set up (do this once)

You need Python on your computer. Then install the app one time.

Open a terminal (CMD on Windows) in the app folder. Run:

```
pip install -e .
```

That is it. You are ready.

> Tip: If `python` does not work, try `py` instead. Both are fine.

---

## 4. The big picture

Here is the loop you will follow:

```
Update DATA.csv  ->  Train (slow, rare)  ->  Forecast (fast, often)
        ^                                            |
        |                                            v
        +--------  add the new draw, forecast again  +
```

- You **train** rarely. Maybe once every six months. It is your choice.
- You **forecast** every time a new draw comes in.
- New data is added twice a week. So you forecast often.

---

## 5. Step by step

### Step 1 — Update the raw data

Your draws live in a file called `DATA.csv`. It sits in the app's main folder.

Open it with any text editor or Excel. It looks like this:

```
Date,TS_1,TS_2,TS_3,TS_4,TS_5,TS_6,TS_7
30/05/2017,3,10,25,32,43,1,3
06/06/2017,6,12,35,39,49,4,9
```

- The first line is the header. Do not change it.
- Each line after is one draw.
- The date format is day/month/year (like `30/05/2017`).
- `TS_1` to `TS_7` are the seven numbers of that draw.

To add a new draw, add one new line at the bottom. Then save the file.

> New draws come twice a week. Add each one as it happens. The order of rows
> matters. Always add new draws to the bottom.

### Step 2 — Do a full training

Do this the first time. Then do it again once in a while (say, every six
months). There is no fixed rule. You decide when.

Full training has two commands. Run them in order.

**2a. Build the notes from all your draws.** This is the slow one.

```
python stat.py --statgrid-export full
```

**2b. Train and test the ticket picker.** This checks how good it is.

```
python orchestrator.py --action optimize --run-id latest --optimizer all
```

When 2a finishes, it saves a StatGrid run. `--run-id latest` in 2b means "use
the newest one." You do not need to type the run's name.

> Step 2b is a good check, but it is optional for making tickets. Forecasting
> (Step 3) works after Step 2a alone.

### Step 3 — Make your first projection

Now ask the app for tickets for the next draw:

```
python orchestrator.py --action forecast --run-id latest
```

The app saves the answer in a file named `forecast.json`. Look in the `Output`
folder, under `Reports/Optimization/State/`. The file lists your tickets.

### Step 4 — Add the new draw

Wait for the real draw. Then open `DATA.csv`. Add the new draw as a new line at
the bottom. Save the file. (This is the same as Step 1.)

### Step 5 — Make a fresh projection

Now the app has one more draw to learn from. Fold it in, then forecast again.

**5a. Add the new draw to the notes.** This is fast. It only adds the new row.

```
python stat.py --resume latest --statgrid-export incremental
```

**5b. Forecast again.**

```
python orchestrator.py --action forecast --run-id latest
```

Your old guess used N draws. This new guess uses N+1 draws. More data usually
means a better guess.

### Step 6 — Repeat

Keep doing Step 4 and Step 5 each time a new draw comes.

Do a full training (Step 2) again only when you want a fresh start. Once every
six months is a fine habit. It is your call.

---

## 6. Command cheat sheet

Copy and paste these. They cover the whole loop.

| What you want | Command |
| --- | --- |
| Full training (slow, all draws) | `python stat.py --statgrid-export full` |
| Add a new draw to the notes | `python stat.py --resume latest --statgrid-export incremental` |
| Train and test the picker | `python orchestrator.py --action optimize --run-id latest --optimizer all` |
| Make tickets (forecast) | `python orchestrator.py --action forecast --run-id latest` |
| Read a training report | `python stat_report.py --checkpoint latest` |
| Forecast one series only | `python run_cli.py --target TS_1 --horizon 5` |

> These short names also work after install: `dynamix-stat`, `dynamix-opt`,
> `dynamix-report`, `dynamix-cli`. For example: `dynamix-opt --action forecast
> --run-id latest`.

---

## 7. All the options, explained

Flags are extra words you add to a command. Each one changes the result. You
can skip them all — the app has good defaults. Add them only if you want.

### Training tool — `stat.py`

| Flag | What it does | Default |
| --- | --- | --- |
| `--statgrid-export full` | Build the notes from every draw. Slow. | — |
| `--statgrid-export incremental` | Add only new draws. Fast. | incremental |
| `--statgrid-export none` | Train but save no grid. | — |
| `--resume latest` | Pick up the newest run and continue. | off |
| `--statgrid-dedupe` | Save the notes in a smaller way. Same result. | off |

Example — train from scratch and save a smaller grid:

```
python stat.py --statgrid-export full --statgrid-dedupe
```

### Ticket tool — `orchestrator.py`

This tool has two modes. Pick one with `--action`.

- `--action optimize` — train and test the picker on past draws.
- `--action forecast` — make tickets for the next draw.

Main flags:

| Flag | What it does | Default |
| --- | --- | --- |
| `--action optimize` / `--action forecast` | Choose the mode. | optimize |
| `--run-id latest` | Which training run to use. `latest` is newest. | latest |
| `--optimizer all` | Which pickers to run (see below). | all |
| `--max-tickets 5` | How many tickets to make. | 5 |
| `--seed 123` | Fix the "luck." Same seed gives the same result. | 123 |
| `--quiet` | Show less text on screen. | off |

The `--optimizer` choices:

- `all` — runs the three fast pickers: `greedy`, `milp`, `bandit`.
- `greedy` — a simple, fast picker.
- `milp` — a math-based picker (needs the extra `milp` install).
- `bandit` — a picker that learns which settings win.
- `evo` — a smart search that tries many settings. It is strong but **slow**.
  It is not in `all`. You must ask for it by name.

Example — run the slow, smart picker with more search power:

```
python orchestrator.py --action optimize --run-id latest --optimizer evo --evo-generations 25 --evo-pop-size 22
```

Fine-tuning flags (for advanced users):

| Flag | What it does | Default |
| --- | --- | --- |
| `--max-overlap-k 3` | How much tickets may share numbers. | 3 |
| `--shortlist-m 10` | How many top numbers to keep per position. | 10 |
| `--beam 200` | How wide the search looks. | 200 |
| `--hit-threshold 3` | How many correct numbers counts as a "win." | 3 |
| `--evo-generations 25` | How many rounds the `evo` search runs. | 25 |
| `--evo-pop-size 22` | How many settings `evo` tries each round. | 22 |
| `--cooc on` / `off` | Use number-pair patterns. | on |
| `--train-frac 0.8` | Share of draws used for learning. | 0.8 |

Example — make more tickets and stay quiet:

```
python orchestrator.py --action forecast --run-id latest --max-tickets 5 --quiet
```

### Report tool — `stat_report.py`

This tool prints a report from a saved training run.

| Flag | What it does | Default |
| --- | --- | --- |
| `--checkpoint latest` | Which run to read. Needed. | — |
| `--show-multihit` | Show every near-miss in detail. | off |
| `--max-per-hit 50` | Limit how many rows print per win level. | all |

Example:

```
python stat_report.py --checkpoint latest --show-multihit
```

### Single-series tool — `run_cli.py`

This tool forecasts just one number series. It is a quick peek.

| Flag | What it does | Default |
| --- | --- | --- |
| `--target TS_1` | Which series to forecast. Leave out for all. | all |
| `--horizon 5` | How many steps ahead to guess. | 1 |
| `--window 200` | How many past draws to learn from. | full |
| `--no-window` | Use the full history. | off |

Example:

```
python run_cli.py --target TS_3 --horizon 5
```

---

## 8. Where the app saves things

Everything lands in the `Output` folder. You do not need to open these files.
But here is where they are:

- **Training notes (StatGrid):** `Output/Reports/Exports/StatGrid/<run>/`
- **Your tickets (forecast.json):** `Output/Reports/Optimization/State/<run>/`
- **Reports and scores:** `Output/Reports/Optimization/`
- **Logs:** `Output/Logs/`

`<run>` is the name of a run, like a date-stamped folder.

---

## 9. Common questions

**Which command makes my tickets?**
This one: `python orchestrator.py --action forecast --run-id latest`.

**How often do I train?**
Rarely. Maybe every six months. It is your choice.

**How often do I forecast?**
Often. Every time a new draw is added (twice a week).

**Do I need to type the run name?**
No. Use `--run-id latest`. It means "the newest run."

**My command is slow. Is that normal?**
Full training (`--statgrid-export full`) is slow. So is `--optimizer evo`.
This is normal.

**The `milp` picker fails. Why?**
It needs an extra part. Install it once with `pip install -e .[milp]`.

**Can I change where DATA.csv lives?**
Yes. Set `DYNAMIX_DATA_FILE` to the file path before you run a command.

---

## 10. Quick daily routine

Once you have trained, your normal day looks like this:

1. A new draw happens.
2. Add it to `DATA.csv` (one new line, save).
3. Run: `python stat.py --resume latest --statgrid-export incremental`
4. Run: `python orchestrator.py --action forecast --run-id latest`
5. Open `forecast.json` in the `Output` folder to see your tickets.

That is the whole loop. Train again only when you choose to.
