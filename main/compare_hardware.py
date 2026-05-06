"""
compare_hardware.py — All paper figures for cross-platform HashMap study.

Generates exactly 4 figures, each answering one research question:

  Fig 1 — performance_overview.png
      Q: Do the same implementations win on both platforms, and does rank
         change depending on workload distribution?
      Slope (bump) chart: 3 panels (one per distribution). Each panel shows
      RPi rank on the left axis and HPC rank on the right. A crossing line
      means the implementation's rank changed across hardware tiers.

  Fig 2 — scalability.png
      Q: Do implementations scale differently across hardware tiers?
         Where does the memory bandwidth plateau appear on each platform?
      2-panel plot, both platforms overlaid per implementation.

  Fig 3 — hardware_advantage.png
      Q: How much faster is HPC than RPi, and does it depend on implementation
         or thread count?
      log2(HPC/RPi) heatmap: impl x common thread counts.

  Fig 4 — distribution_sensitivity.png
      Q: Does Zipfian skew hurt more on RPi (small 2 MB L3) than on HPC,
         as predicted by the memory bandwidth and cache capacity analysis?
      Per-platform throughput drop: uniform -> zipfian_0.99.

Usage:
    python3 compare_hardware.py results/raspberrypi-2026-03-27_18-16-22 \\
                                results/spark-c183-2026-03-27_19-10-10 --save
    (plots saved to results/cross_comparison/)
"""

import sys, os, re, argparse, glob
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

MAP_ORDER = [
    "SynchronizedMap", "StripedMap", "StripedMapPadded",
    "StripedWriteMap", "StripedWriteMapPadded",
    "StripedLevelWriteMap", "HashTrieMap", "WrapConcurrentHashMap"
]
MAP_SHORT = {
    "SynchronizedMap":       "Sync",
    "StripedMap":            "Striped",
    "StripedMapPadded":      "StripedPad",
    "StripedWriteMap":       "WriteMap",
    "StripedWriteMapPadded": "WriteMapPad",
    "StripedLevelWriteMap":  "LevelWrite",
    "HashTrieMap":           "HashTrie",
    "WrapConcurrentHashMap": "WrapCHM",
}

HPC_COLOR, RPI_COLOR = "#4C72B0", "#DD8452"

IMPL_COLORS = {
    "SynchronizedMap":       "#e41a1c",
    "StripedMap":            "#ff7f00",
    "StripedMapPadded":      "#fdbf6f",
    "StripedWriteMap":       "#33a02c",
    "StripedWriteMapPadded": "#b2df8a",
    "StripedLevelWriteMap":  "#1f78b4",
    "HashTrieMap":           "#6a3d9a",
    "WrapConcurrentHashMap": "#b15928",
}

plt.rcParams.update({
    "figure.dpi":        150,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.3,
    "font.size":         10,
})


# -- Data loading --------------------------------------------------------------

def _normalise_cols(df):
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    rename = {}
    for col in df.columns:
        if "error" in col or "99.9" in col:
            rename[col] = "ci99"
        elif col.startswith("param:_"):
            rename[col] = col[len("param:_"):]
    return df.rename(columns=rename)


def load_folder(folder):
    csvs = sorted(glob.glob(os.path.join(folder, "*.csv")))
    if not csvs:
        sys.exit(f"No CSV files found in {folder}")
    frames = []
    for path in csvs:
        df = pd.read_csv(path)
        df = _normalise_cols(df)
        if "threads" not in df.columns:
            fname = os.path.basename(path)
            m = re.search(r'-t(\d+)\.csv$', fname) or re.search(r'threads(\d+)', fname)
            df["threads"] = int(m.group(1)) if m else 1
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    if "ci99" not in df.columns:
        df["ci99"] = 0.0
    df["maptype"]   = df["maptype"].str.strip()
    df["score"]     = pd.to_numeric(df["score"],     errors="coerce")
    df["ci99"]      = pd.to_numeric(df["ci99"],      errors="coerce").fillna(0)
    df["threads"]   = pd.to_numeric(df["threads"],   errors="coerce").fillna(1).astype(int)
    df["keyrange"]  = pd.to_numeric(df["keyrange"],  errors="coerce").astype(int)
    df["readratio"] = pd.to_numeric(df["readratio"], errors="coerce")
    df = df[df["mode"] == "thrpt"].copy()
    if "unit" in df.columns:
        mask = df["unit"].str.strip() == "ops/s"
        df.loc[mask, "score"] /= 1e6
        df.loc[mask, "ci99"]  /= 1e6
    return df


def detect_label(folder):
    name = os.path.basename(folder).lower()
    if "raspberry" in name or "rpi" in name:
        return "RPi 5"
    if "spark" in name:
        return "HPC"
    return os.path.basename(folder)


def save_fig(fig, save_dir, name, tight=True):
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, name)
        fig.savefig(path, bbox_inches="tight")
        print(f"  Saved {path}")
    else:
        if tight:
            plt.tight_layout()
        plt.show()
    plt.close(fig)


def filt(df, threads=None, dist=None, kr=None, ratio=None):
    d = df
    if threads is not None: d = d[d["threads"]      == threads]
    if dist    is not None: d = d[d["distribution"] == dist]
    if kr      is not None: d = d[d["keyrange"]     == kr]
    if ratio   is not None: d = d[d["readratio"]    == ratio]
    return d


def short(m): return MAP_SHORT.get(m, m)


# -- Figure 1: Slope chart (rank stability) ------------------------------------
#
# Three panels side by side, one per distribution.
# Within each panel: left axis = RPi rank, right axis = HPC rank.
# Each implementation is a labelled line connecting its rank on both sides.
# A line that crosses others means that implementation's rank changed.
# Rank 1 = highest throughput, plotted at the top.
#
# This directly answers: do rankings hold across hardware, and does the
# answer depend on workload distribution? HashTrie's rank shift under
# high Zipfian skew is immediately visible as an intersecting line.

def plot_performance_overview(hpc, rpi, lbl_hpc, lbl_rpi, save_dir):
    dist  = "zipfian_0.99"
    t_hpc = hpc["threads"].max()
    t_rpi = rpi["threads"].max()

    if dist not in hpc["distribution"].values or dist not in rpi["distribution"].values:
        print("  Skipping performance overview: zipfian_0.99 not found in data.")
        return

    maps = [m for m in MAP_ORDER
            if m in hpc["maptype"].values and m in rpi["maptype"].values]
    n = len(maps)

    def get_ranks(df, t_snap):
        scores = {}
        for m in maps:
            vals = df[(df["threads"] == t_snap) &
                      (df["distribution"] == dist) &
                      (df["maptype"] == m)]["score"]
            scores[m] = vals.median() if not vals.empty else 0
        sorted_maps = sorted(scores, key=scores.get, reverse=True)
        return {m: sorted_maps.index(m) + 1 for m in maps}

    rpi_ranks = get_ranks(rpi, t_rpi)
    hpc_ranks = get_ranks(hpc, t_hpc)

    fig, ax = plt.subplots(figsize=(6, 6))

    for m in maps:
        r_rpi = rpi_ranks[m]
        r_hpc = hpc_ranks[m]
        color = IMPL_COLORS.get(m, "gray")
        lw    = 2.5 if m == "HashTrieMap" else 1.5
        ax.plot([0, 1], [r_rpi, r_hpc], color=color,
                linewidth=lw, solid_capstyle="round")
        ax.scatter([0, 1], [r_rpi, r_hpc], color=color, s=50, zorder=5)
        ax.text(-0.06, r_rpi, short(m), ha="right", va="center",
                fontsize=9, color=color)
        ax.text(1.06, r_hpc, short(m), ha="left", va="center",
                fontsize=9, color=color)

    ax.set_xlim(-0.5, 1.5)
    ax.set_ylim(n + 0.5, 0.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(
        [f"{lbl_rpi}\n(t={t_rpi})", f"{lbl_hpc}\n(t={t_hpc})"],
        fontsize=11, fontweight="bold"
    )
    ax.yaxis.set_visible(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(False)
    for rank in range(1, n + 1):
        ax.axhline(rank, color="gray", linewidth=0.4, linestyle="--", alpha=0.4)

    fig.suptitle(
        "Implementation rank by platform — Zipfian-0.99, peak thread count\n"
        "Rank 1 = highest throughput. A crossing line indicates rank changed across hardware.",
        fontsize=11, fontweight="bold"
    )
    plt.tight_layout(rect=[0, 0, 1, 0.91])
    save_fig(fig, save_dir, "fig1_performance_overview.png", tight=False)


# ── Figure 2: Scalability ──────────────────────────────────────────────────────

def plot_scalability(hpc, rpi, lbl_hpc, lbl_rpi, save_dir):
    maps = [m for m in MAP_ORDER
            if m in hpc["maptype"].values or m in rpi["maptype"].values]

    def median_by_thread(df, m):
        ts, scores = [], []
        for t in sorted(df["threads"].unique()):
            vals = df[(df["maptype"] == m) & (df["threads"] == t)]["score"]
            if not vals.empty:
                ts.append(t)
                scores.append(vals.median())
        return ts, scores

    colors  = plt.cm.tab10(np.linspace(0, 0.9, len(maps)))
    markers = ["o", "s", "^", "D", "v", "P", "X", "*"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    for ax, (df, platform_label) in zip(axes, [(rpi, lbl_rpi), (hpc, lbl_hpc)]):
        plat_t = sorted(df["threads"].unique())
        log_x  = len(plat_t) > 2 and max(plat_t) / min(plat_t) >= 8

        for idx, m in enumerate(maps):
            ts, scores = median_by_thread(df, m)
            if not scores:
                continue
            ax.plot(ts, scores, label=short(m),
                    color=colors[idx], marker=markers[idx % len(markers)],
                    linewidth=1.8, markersize=5)

        ax.set_title(platform_label, fontsize=12, fontweight="bold", pad=8)
        ax.set_xlabel("Thread count", fontsize=9)
        if ax == axes[0]:
            ax.set_ylabel("Throughput (ops/μs)", fontsize=9)

        if log_x:
            ax.set_xscale("log", base=2)
            ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
            ax.set_xticks(plat_t)
            ax.tick_params(axis="x", labelsize=9)

    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center right", bbox_to_anchor=(1.01, 0.5),
               fontsize=9, frameon=True, title="Implementation", title_fontsize=9)

    fig.suptitle(
        "Thread-count scaling — median throughput (ops/μs) across all 18 workload configurations\n"
        "Shared y-axis: vertical distance between panels = absolute hardware gap. "
        "A flattening curve = bandwidth or contention saturation.",
        fontsize=11, fontweight="bold"
    )
    plt.tight_layout(rect=[0, 0, 0.86, 0.90])
    save_fig(fig, save_dir, "fig2_scalability.png")


# -- Figure 5: Read ratio sensitivity ------------------------------------------
#
# Tests whether write-optimized variants (StripedWriteMap, StripedWriteMapPadded,
# StripedLevelWriteMap) show a distinctive advantage under read-heavy workloads
# relative to other implementations.
#
# For each implementation: throughput at read ratios 0.2, 0.5, 0.8 at peak
# thread count, median across key ranges and distributions.
# Two panels: RPi 5 and HPC.
#
# If WriteMap variants show a steeper positive slope from 0.2 to 0.8 than
# StripedMap, the unsynchronized read path is providing a measurable benefit.
# If the slope is similar, the write lock dominates even at 80% reads.

def plot_read_ratio_sensitivity(hpc, rpi, lbl_hpc, lbl_rpi, save_dir):
    maps = [m for m in MAP_ORDER
            if m in hpc["maptype"].values or m in rpi["maptype"].values]

    ratios = sorted(set(hpc["readratio"].unique()) & set(rpi["readratio"].unique()))
    if not ratios:
        print("  Skipping read ratio sensitivity: no common read ratios.")
        return

    colors  = plt.cm.tab10(np.linspace(0, 0.9, len(maps)))
    markers = ["o", "s", "^", "D", "v", "P", "X", "*"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)

    for ax, (df, platform_label) in zip(axes, [(rpi, lbl_rpi), (hpc, lbl_hpc)]):
        t_peak = df["threads"].max()
        dists  = df["distribution"].unique()
        krs    = df["keyrange"].unique()

        for idx, m in enumerate(maps):
            y = []
            for r in ratios:
                vals = []
                for dist in dists:
                    for kr in krs:
                        row = filt(df, t_peak, dist, kr, r)
                        row = row[row["maptype"] == m]
                        if not row.empty and row["score"].values[0] > 0:
                            vals.append(row["score"].values[0])
                y.append(np.median(vals) if vals else np.nan)

            ax.plot(ratios, y, label=short(m),
                    color=colors[idx], marker=markers[idx % len(markers)],
                    linewidth=1.8, markersize=6)

        ax.set_title(platform_label, fontsize=12, fontweight="bold", pad=8)
        ax.set_xlabel("Read ratio", fontsize=9)
        ax.set_xticks(ratios)
        ax.set_xticklabels([str(r) for r in ratios], fontsize=9)
        if ax == axes[0]:
            ax.set_ylabel("Throughput (ops/μs)", fontsize=9)

    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center right", bbox_to_anchor=(1.01, 0.5),
               fontsize=9, frameon=True, title="Implementation", title_fontsize=9)

    fig.suptitle(
        "Throughput by read ratio — median across distributions and key ranges, peak thread count\n"
        "A steeper slope for WriteMap variants indicates the unsynchronized read path provides benefit.",
        fontsize=11, fontweight="bold"
    )
    plt.tight_layout(rect=[0, 0, 0.86, 0.90])
    save_fig(fig, save_dir, "fig5_read_ratio.png")


# -- Figure 3: Hardware advantage heatmap -------------------------------------

def plot_hardware_advantage(hpc, rpi, lbl_hpc, lbl_rpi, save_dir):
    common_t = sorted(
        set(hpc["threads"].unique()) & set(rpi["threads"].unique())
    )
    if not common_t:
        print("  Skipping hardware advantage: no common thread counts.")
        return

    maps = [m for m in MAP_ORDER
            if m in hpc["maptype"].values and m in rpi["maptype"].values]
    common_dists  = set(hpc["distribution"].unique()) & set(rpi["distribution"].unique())
    common_krs    = set(hpc["keyrange"].unique())     & set(rpi["keyrange"].unique())
    common_ratios = set(hpc["readratio"].unique())    & set(rpi["readratio"].unique())

    matrix = np.full((len(maps), len(common_t)), np.nan)
    for j, t in enumerate(common_t):
        for i, m in enumerate(maps):
            log_ratios = []
            for dist in common_dists:
                for kr in common_krs:
                    for ratio in common_ratios:
                        a = filt(hpc, t, dist, kr, ratio)
                        a = a[a["maptype"] == m]
                        b = filt(rpi, t, dist, kr, ratio)
                        b = b[b["maptype"] == m]
                        if (not a.empty and not b.empty
                                and b["score"].values[0] > 0
                                and a["score"].values[0] > 0):
                            log_ratios.append(
                                np.log2(a["score"].values[0] /
                                        b["score"].values[0])
                            )
            if log_ratios:
                matrix[i, j] = np.median(log_ratios)

    vmax = np.nanmax(np.abs(matrix)) if not np.all(np.isnan(matrix)) else 1

    fig, ax = plt.subplots(figsize=(max(7, len(common_t) * 1.8 + 3), 6))
    im = ax.imshow(matrix, cmap="RdBu", aspect="auto", vmin=-vmax, vmax=vmax)

    ax.set_xticks(range(len(common_t)))
    ax.set_xticklabels([str(t) for t in common_t], fontsize=10)
    ax.set_yticks(range(len(maps)))
    ax.set_yticklabels([short(m) for m in maps], fontsize=10)
    ax.set_xlabel("Thread count  (shared between both platforms)", fontsize=10)

    for i in range(len(maps)):
        for j in range(len(common_t)):
            v = matrix[i, j]
            if np.isnan(v):
                continue
            mult    = 2 ** abs(v)
            txt     = f"{mult:.1f}×" if abs(v) > 0.15 else "≈1×"
            is_dark = abs(v) > vmax * 0.55
            ax.text(j, i, txt, ha="center", va="center", fontsize=9,
                    color="white" if is_dark else "black")

    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
    cbar.set_label(f"log₂({lbl_hpc} / {lbl_rpi})\nblue = HPC faster · red = RPi faster",
                   fontsize=9)

    fig.suptitle(
        f"Hardware advantage: {lbl_hpc} vs {lbl_rpi}  —  median across all 18 workload configurations\n"
        f"Each cell shows the speedup multiplier (e.g. 4× = HPC is 4× faster). "
        f"Colour encodes log₂ ratio, so equal gaps represent equal relative differences.",
        fontsize=11, fontweight="bold"
    )
    plt.tight_layout(rect=[0, 0, 1, 0.88])
    save_fig(fig, save_dir, "fig3_hardware_advantage.png")


# -- Figure 4: Distribution sensitivity ---------------------------------------

def plot_distribution_sensitivity(hpc, rpi, lbl_hpc, lbl_rpi, save_dir):
    for df in [hpc, rpi]:
        if ("uniform" not in df["distribution"].values or
                "zipfian_0.99" not in df["distribution"].values):
            print("  Skipping distribution sensitivity: missing required distributions.")
            return

    maps = [m for m in MAP_ORDER
            if m in hpc["maptype"].values or m in rpi["maptype"].values]

    common_krs    = sorted(set(hpc["keyrange"].unique()) & set(rpi["keyrange"].unique()))
    common_ratios = sorted(set(hpc["readratio"].unique()) & set(rpi["readratio"].unique()))

    fig, axes = plt.subplots(1, len(common_krs), figsize=(8.5 * len(common_krs), 6.5),
                             sharey=True)
    if len(common_krs) == 1:
        axes = [axes]

    x = np.arange(len(maps))
    w = 0.35

    for ax, kr in zip(axes, common_krs):
        for k, (df, color, label) in enumerate([
            (hpc, HPC_COLOR, lbl_hpc),
            (rpi, RPI_COLOR, lbl_rpi),
        ]):
            t_peak = df["threads"].max()
            deltas = []
            for m in maps:
                vals = []
                for ratio in common_ratios:
                    uni = filt(df, t_peak, "uniform",      kr, ratio)
                    uni = uni[uni["maptype"] == m]
                    skw = filt(df, t_peak, "zipfian_0.99", kr, ratio)
                    skw = skw[skw["maptype"] == m]
                    if (not uni.empty and not skw.empty
                            and uni["score"].values[0] > 0):
                        pct = ((uni["score"].values[0] - skw["score"].values[0])
                               / uni["score"].values[0]) * 100
                        vals.append(pct)
                deltas.append(np.median(vals) if vals else 0)

            bars = ax.bar(x + k * w, deltas, w,
                          label=f"{label}  (t={t_peak})", color=color, alpha=0.85)
            for bar, v in zip(bars, deltas):
                if abs(v) > 1:
                    ypos = bar.get_height() + (1.0 if v >= 0 else -2.5)
                    ax.text(bar.get_x() + bar.get_width() / 2, ypos,
                            f"{v:+.1f}%", ha="center", va="bottom", fontsize=7.5)

        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x + w / 2)
        ax.set_xticklabels([short(m) for m in maps], fontsize=9,
                           rotation=20, ha="right")
        kr_cache = "fits in RPi L3 (2 MB)" if kr == 1000 else "exceeds RPi L3 (2 MB)"
        ax.set_title(f"{kr:,} keys  —  {kr_cache}", fontsize=11,
                     fontweight="bold", pad=8)
        ax.legend(fontsize=9, loc="upper left")
        if ax == axes[0]:
            ax.set_ylabel(
                "Throughput change: uniform → Zipfian-0.99 (%)\n"
                "positive = skew degrades throughput  ·  negative = hot-key locality helps",
                fontsize=9
            )

    fig.suptitle(
        "Impact of Zipfian-0.99 key skew relative to uniform access — peak thread count",
        fontsize=11, fontweight="bold"
    )
    plt.tight_layout(rect=[0, 0, 1, 0.88])
    save_fig(fig, save_dir, "fig4_distribution_sensitivity.png")


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder_a", help="First results folder")
    parser.add_argument("folder_b", help="Second results folder")
    parser.add_argument("--save", action="store_true",
                        help="Save to results/cross_comparison/")
    args = parser.parse_args()

    label_a = detect_label(args.folder_a)
    label_b = detect_label(args.folder_b)

    print(f"Loading {label_a}  <- {args.folder_a}")
    df_a = load_folder(args.folder_a)
    print(f"Loading {label_b}  <- {args.folder_b}\n")
    df_b = load_folder(args.folder_b)

    if df_a["threads"].max() < df_b["threads"].max():
        df_a, df_b       = df_b, df_a
        label_a, label_b = label_b, label_a
    lbl_hpc, lbl_rpi = label_a, label_b

    parent   = os.path.commonpath([os.path.abspath(args.folder_a),
                                   os.path.abspath(args.folder_b)])
    save_dir = os.path.join(parent, "cross_comparison") if args.save else None

    print(f"HPC threads : {sorted(df_a['threads'].unique())}")
    print(f"RPi threads : {sorted(df_b['threads'].unique())}")
    print(f"Common t    : {sorted(set(df_a['threads'].unique()) & set(df_b['threads'].unique()))}\n")

    print("Figure 1: Performance overview (slope chart) ...")
    plot_performance_overview(df_a, df_b, lbl_hpc, lbl_rpi, save_dir)

    print("Figure 2: Scalability ...")
    plot_scalability(df_a, df_b, lbl_hpc, lbl_rpi, save_dir)

    print("Figure 3: Hardware advantage heatmap ...")
    plot_hardware_advantage(df_a, df_b, lbl_hpc, lbl_rpi, save_dir)

    print("Figure 4: Distribution sensitivity ...")
    plot_distribution_sensitivity(df_a, df_b, lbl_hpc, lbl_rpi, save_dir)

    print("Figure 5: Read ratio sensitivity ...")
    plot_read_ratio_sensitivity(df_a, df_b, lbl_hpc, lbl_rpi, save_dir)

    print("\nDone! 5 figures generated.")

if __name__ == "__main__":
    main()