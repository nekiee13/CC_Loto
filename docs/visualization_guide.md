# Visualization Guide

**Status:** living document · **Companion to:** Epic U19 in
[CC_Loto_ENHANCED_UPGRADE_PLAN.md](CC_Loto_ENHANCED_UPGRADE_PLAN.md)

This guide explains the five charts this project uses for oversight. It explains
what each chart shows, why a logged number cannot show the same thing, and how to
read each one. It is written in plain language on purpose.

---

## 1. The big idea: averages hide things

Almost every metric we log is a single number. Total profit. Hit rate. A test
score. Each of these numbers is a sum or an average over many draws.

Sums and averages crush information. They crush it in four ways:

1. **Path.** The total tells you where you ended. It does not tell you *how* you
   got there. A steady climb and one lucky jump can end at the same total.
2. **Place.** A test score can say "something is off". It cannot say *where*.
   Which ball? Which position? Which direction?
3. **Shape.** An average tells you the middle of a pile of outcomes. It hides
   what the whole pile looks like. Two piles can share a middle and look nothing
   alike.
4. **Time.** A whole-run number assumes nothing changed along the way. It hides
   the moment when something broke or shifted.

Each chart in this guide rescues exactly one of these four things (plus one chart
for pipeline health). That is the test every chart had to pass to be included:
**it must show something that no logged number can show.** Charts that failed
that test were cut.

---

## 2. Why this project needs pictures more than most

Lottery payouts are extremely lopsided. On most draws, a ticket wins nothing or
almost nothing. Very rarely, a ticket hits many numbers and wins a lot at once.

That means our money totals are dominated by one or two rare events. Think of it
like this: the average wealth of people in a room changes completely the moment
one billionaire walks in. Our "net EUR" numbers work the same way. One lucky
draw can carry the whole total.

So in this project, **averages and totals are the least trustworthy numbers we
have.** The charts below are not decoration. They are the correction for that
problem.

---

## 3. Chart 1 — The money curve and the luck cloud

*(Rescues: path. Data source: optimizer diagnostics + the random baselines from
Epic U1.)*

### What it is

- The x-axis is the draws of the evaluation period, in order.
- The y-axis is the running money total: winnings minus ticket costs so far.
- Each strategy gets one line.
- Behind the lines sits a gray band: the **luck cloud**.

### What the luck cloud is

We simulate many random players. Each one buys the same number of tickets, under
the same rules, but picks numbers at random. At every draw we mark the range
that holds most of these random players (for example, the middle 90%). That
range, drawn over time, is the gray band.

The band answers one question: **what does pure luck look like here?**

### Why a logged number cannot do this job

Our summary logs a final edge, say `+40 EUR`. That number is equally consistent
with two opposite stories:

- **Story A:** small steady gains, draw after draw. The line climbs gently.
- **Story B:** losses everywhere, plus one lucky multi-hit spike on draw 37.

Story A would be interesting. Story B is guaranteed to be noise. The final
number is *identical* in both. Only the path can tell them apart.

### How to read it

- **Line wiggles inside the cloud:** nothing is happening. This is the expected
  picture, and seeing it clearly is the point.
- **Line jumps once, then goes flat or falls:** that was luck. Ignore the total.
- **Line drifts upward steadily, exits the cloud, and stays out:** now it is
  interesting. Not proof — but worth the deeper tests.
- **Caution:** about 1 random player in 20 pokes outside a 90% band just by
  chance. Leaving the cloud briefly means little. *Staying* out is what counts.

---

## 4. Chart 2 — Real numbers vs. expected numbers

*(Rescues: place. Data source: DATA.csv + the exact math from Epic U15.)*

### The key fact behind this chart

Our columns store the drawn balls **in sorted order**. TS_1 is always the
smallest of the five main balls, TS_5 the biggest. This was checked: it holds in
every one of the 613 rows.

Sorting creates strong patterns that have nothing to do with prediction. The
smallest of five balls is usually a small number. The biggest is usually large.
And here is the useful part: for a fair lottery, math gives us the **exact**
expected pattern for each position. No model, no training. Just a formula.

### What it is

Seven small panels, one per position (TS_1 … TS_7). In each panel:

- **Bars:** how often each value actually appeared in our data.
- **Line:** how often a perfectly fair lottery would produce each value.

### Why a logged number cannot do this job

The fairness test (Epic U15) gives a single score, a p-value. That score can say
"the data does not match a fair lottery". It cannot say **where** the mismatch
is or what shape it has. But "where" is the whole decision:

- A bump concentrated on one or two specific balls → possibly a real mechanical
  bias. That would be worth acting on.
- The same test score smeared thinly across all values → almost certainly random
  noise plus the fact that we ran many comparisons.
- Extra weight exactly at the edge of the allowed range → smells like a data
  entry mistake, not physics.

Three different actions. One identical score. Only the picture separates them.

### How to read it

- **Bars hug the line:** consistent with a fair draw. That is the honest,
  expected outcome.
- **One bar clearly above the line, in several positions, at the same ball:**
  flag it. Check when it started (Chart 4 helps).
- **Warning:** with 50 + 12 possible balls, a few bars will always stick out a
  little just by chance. One mildly tall bar is not a discovery.

This chart has a second job. When we test the pipeline with a *planted* bias
(fake data where ball 7 is deliberately favored — Epic U14), the bump must
appear in this chart at ball 7. If it does not, our instruments are broken.

---

## 5. Chart 3 — The shuffle test

*(Rescues: shape. Data source: permutation runs from Epic U16.)*

### The question it answers

Every forecasting model in this project makes one claim: **the order of past
draws contains information.** The shuffle test attacks exactly that claim.

We take the same history and shuffle the order of the draws. Everything else
stays identical — same numbers, same frequencies, same tickets rules. Only time
order is destroyed. Then we run the optimizer on the shuffled history and record
the "edge" it finds. We repeat this many times with different shuffles.

### What it is

- A histogram (a pile) of the edges found on shuffled, meaningless histories.
- A vertical line marking the edge found on the *real* history.

### Why a logged number cannot do this job

We could log just the rank: "the real edge beats 95% of shuffles." But the
meaning of that rank depends on the **shape** of the pile — and the shape here
is ugly on purpose. Shuffled histories also hit occasional jackpots, so the pile
has a long tail stretching to the right. In a long-tailed pile, sitting just
past the 95% mark is weak evidence. Big fake edges are simply common there. You
must see the pile to know how much the rank is worth.

### How to read it

- **Real-edge line lands in the middle of the pile:** the "edge" on real data is
  the same thing shuffled nonsense produces. Story over.
- **Line lands just past the bulk, inside the long tail:** weak. Treat as noise
  unless other charts agree.
- **Line lands far beyond nearly everything, and Chart 1 shows steady drift:**
  the time order genuinely mattered. This is the strongest signal this project
  can produce.

---

## 6. Chart 4 — Hit rate over time

*(Rescues: time. Data source: backtest rows that already exist today.)*

### What it is

For each model: a line showing its hit rate over a sliding window — for example,
"hit rate across the last 50 backtest steps" — recomputed at every step.

### Why a logged number cannot do this job

A whole-run hit rate silently assumes the world never changed. Two realistic
events break that assumption:

1. **The lottery changes.** Real lotteries replace machines and ball sets. If
   any physical bias ever existed, it appears and *disappears* with equipment.
   A whole-run average smears the interesting period into the boring one.
2. **Our own pipeline changes.** This system is deliberately built to keep
   running when a model breaks ("fail-soft"). That is a good design — with a
   side effect: a model can quietly stop working mid-run, and the totals only
   dip a little.

Both events look like a **step change** in this chart. Both are invisible in the
aggregate.

### How to read it

- **Flat, wiggly line:** stable. Normal.
- **Sudden drop or jump at a specific step:** something changed right there.
  First suspect: our pipeline (check Chart 5). Second suspect: the lottery
  itself (check the draw dates around that step).
- The line separates two stories a scalar cannot: "this model was never good"
  versus "this model was fine until step 214, then died."

---

## 7. Chart 5 — The coverage map

*(Rescues: nothing scientific — it protects your time. Data source: StatGrid
rows that already exist today.)*

### What it is

A grid. Rows are backtest steps. Columns are each model-and-series pair. Every
cell gets a color:

- produced a prediction and **hit**
- produced a prediction and **missed**
- **failed** (the model errored on that step)
- **skipped** (the model was not available)

### Why a logged number cannot do this job

Because of the fail-soft design, a model family can die silently in the middle
of a long run. The run still "succeeds". The row counts shrink a bit, and
nothing shouts. A count tells you rows are missing. The map tells you **which
model, which series, and starting at exactly which step** — an empty stripe with
a visible starting point. That is the difference between a five-minute diagnosis
and a lost evening. It also stops you from optimizing on top of a grid with a
hole in it, which wastes compute and produces misleading scores.

### How to read it

- **Solid columns, mixed hit/miss colors:** healthy. (Mostly "miss" is normal —
  this is a lottery.)
- **A stripe that goes empty and stays empty:** that family died at that step.
  Find the first empty cell; read the log around it.
- **A column that never filled at all:** the dependency was missing from the
  start. Run `dynamix-health` (Epic U3) to see why.

---

## 8. Reading the charts together

The charts form a short pipeline of questions. Use them in this order:

1. **Chart 5:** was the run itself healthy? If not, stop — fix the run first.
2. **Chart 1:** does any strategy leave the luck cloud and stay out?
   If no — done. Honest answer: nothing here. This is the expected result.
3. **Chart 3:** if yes — does the real edge also beat the shuffled histories by
   a clear margin, not just the tail?
4. **Chart 2:** if yes — is there a *located* reason? A specific ball or
   position that deviates from the exact fair-lottery curve?
5. **Chart 4:** is that deviation stable in time, or tied to one period
   (one machine, one ball set)?

An "edge" only deserves attention if it survives **all five** questions. Every
earlier exit is the system working correctly, not failing.

---

## 9. Glossary

- **Edge:** how much better (in EUR) a strategy did than random ticket picking
  under the same rules. Positive edge = better than luck *in that sample*.
- **Baseline / random player:** a simulated player who follows the same rules
  but picks numbers at random. Our fairest comparison.
- **Luck cloud (null envelope):** the band of outcomes that many random players
  produce. If your line lives inside it, your result is indistinguishable from
  luck.
- **Permutation / shuffle test:** rerunning the analysis on time-shuffled
  history. Any "edge" that survives shuffling was never about time — it is an
  artifact.
- **Rolling window:** a moving slice of recent steps (say, the last 50), used to
  see change over time instead of one all-time average.
- **Order statistics:** the values you get after sorting a random draw. The
  smallest of five balls behaves in a precisely known way — that is why we can
  draw the exact "expected" curve with no model at all.
- **p-value:** a score for "how surprising is this data if the lottery is
  fair?" Small = surprising. It says *that* something is off, never *what*.
- **Fail-soft:** the design rule that a missing or broken model disables only
  itself instead of crashing the run. Good for robustness; it is the reason
  Chart 5 must exist.
