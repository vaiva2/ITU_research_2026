# Presentation Outline: Concurrent Hash Table Performance Across ARM Hardware Tiers

**Authors:** Vaiva Staugaityte & Elias Illeris Poggi  
**Supervisor:** Peter Sestoft  
**Venue:** IT-Universitetet i København, May 26, 2026

---

## SECTION 1 — Introduction

### Slide 1: Title
**Concurrent Hash Table Performance Across ARM Hardware Tiers**

- Authors, supervisor, institution, date
- One-sentence framing: _We benchmarked 8 concurrent hash map implementations across two ARM machines separated by a large hardware gap, and asked whether the performance rankings known from x86/Apple Silicon research survive the transition._

---

## SECTION 2 — Motivation and Background

### Slide 1: The Research Gap

**Why this matters:**
- Concurrent data structure research has historically targeted high-end hardware: multi-socket x86 servers, Apple Silicon M-series chips.
  - Key prior work: Chen et al. (lock-free map studies), Sestoft's own hash map benchmarks.
- A growing class of real-world deployments runs on hardware with far fewer resources: IoT sensors, wearable health monitors, bedside medical diagnostics, edge inference nodes.
  - These are ARM-based, often quad-core or fewer, with small last-level caches and modest memory bandwidth.
- **The gap**: few, if any, have systematically tested whether the performance ordering established on high-end hardware still holds when the hardware budget drops dramatically, or when the ISA shifts from x86 to ARM.
NOTE: discuss peter sestoft's work, as well as chen et al as needed.

**Our research question in one sentence:**
> Does the performance hierarchy of concurrent hash map implementations transfer from high-end to resource-constrained ARM hardware?

**Why this is non-trivial:**
- Algorithmic differences (lock granularity, CAS-based vs lock-based, pointer-chasing vs flat arrays) interact with hardware characteristics (core count, cache size, memory bandwidth) in ways that can change relative rankings.
- What looks like a "better algorithm" on a 64-core server may perform worse than a simple alternative on a 4-core embedded board.

---

## SECTION 3 — Hardware Platforms

### Slide 1: The Two Machines

**Design choice:** both machines are ARM (aarch64), which lets us isolate hardware tier effects from ISA effects. We ran an identical Nix flake on both, pinning JDK 21 and Gradle to bit-for-bit identical versions.

| Property | Raspberry Pi 5 | NVIDIA DGX Spark (HPC node) |
|---|---|---|
| Architecture | ARMv8.2-A (aarch64) | ARMv9.2-A (aarch64) |
| SoC | Broadcom BCM2712 | NVIDIA GB10 |
| Physical cores | 4× Cortex-A76 @ 2.4 GHz | 10× Cortex-X925 @ 4.0 GHz + 10× Cortex-A725 @ 2.86 GHz |
| L3 cache | 2 MiB shared | 24 MiB aggregate (16 MiB X925 + 8 MiB A725) |
| DRAM | 8 GB LPDDR4X | 128 GB LPDDR5X |
| Memory bandwidth | ~17 GB/s | ~273 GB/s |
| Benchmark thread counts | 1, 2, 4, 8 | 1, 2, 4, 8, 16, 32, 64 |

**On the RPi being "resource-constrained":**
- The RPi 5 is actually quite capable by embedded standards — it runs a full Linux stack, has hardware-accelerated video, etc.
- We use it as a proxy for the lower end of the ARM hardware spectrum: the quad-core limit and 2 MB L3 cache are structurally similar to what you find in wearable SoCs and edge compute modules.
- The claim is moreso that its hardware profile (few cores, small cache) is representative of the constraints found in industries that use _relatively_ resource-constrained hardware.

---

## SECTION 4 — The Implementations

### Slide 1: Three Families, Eight Implementations

All implementations share the `OurMap<K,V>` interface (`get`, `put`, `remove`), which lets the benchmark harness swap them in and out via a single `@Param`.

#### Family 1: Coarse-Grained Lock

**SynchronizedMap** — single `synchronized` block on every method using the object's intrinsic lock. One global lock serializes all threads.
- Throughput _decreases_ as thread count grows: more threads = more contention, with no parallelism to compensate.
- Serves as the correctness baseline. Any implementation slower than this has something seriously wrong.

#### Family 2: Fine-Grained (Striped) Locking

All striped variants partition the key space across **32 independent lock stripes** (`lockCount = 32`). Threads operating on different stripes can run in parallel; only threads landing on the same stripe block each other.

**StripedMap** — both reads and writes acquire the stripe lock. Linked-list `ItemNode<K,V>` nodes are mutable (`V v` is non-final).

**StripedMapPadded** — identical to `StripedMap`, but the `locks` and `sizes` arrays are allocated with a padding factor of 16 between entries (`locks = new Object[lockCount * 16]`, accessed as `locks[s * 16]`).
- _Why padding?_ Without it, two adjacent lock objects may share a cache line (64 bytes). When one thread writes to one lock, the cache coherence protocol invalidates the entire line on every other core — including cores working on adjacent, _unrelated_ stripes. This is **false sharing**. The padding ensures no two stripes share a cache line, so a lock acquisition on stripe `s` does not evict lock data for stripe `s+1` from another core's L1 cache.
- The effect is most visible at high thread counts on many-core hardware. Here's why: at low thread counts (e.g., 2 threads on the RPi), the chance that two threads are simultaneously writing to locks that happen to share a cache line is small — there simply aren't enough concurrent writers to trigger the invalidation cascade frequently. As thread count grows, more cores are actively acquiring and releasing locks at the same time. On a 64-core machine, dozens of threads may be hammering neighboring stripes simultaneously, and if those lock objects are packed tightly in memory, each write ripples through the cache coherence bus as an invalidation broadcast to all other cores. Padding eliminates this by ensuring adjacent stripes land in different cache lines, so a write to stripe 0's lock never touches stripe 1's cache line at all.

**StripedWriteMap** — immutable `ItemNode<K,V>` nodes (all fields `final`). Writes lock the stripe and build a new node list; reads do _not_ lock. Visibility of writes to readers is ensured through `AtomicIntegerArray sizes`: writes update the count even when size doesn't change, and reads load it before traversing the bucket chain. Because traversing an immutable linked list is safe without a lock (no half-completed nodes), read throughput is no longer gated by the write lock.

**StripedWriteMapPadded** — `StripedWriteMap` with the same cache-line padding strategy as `StripedMapPadded`.

**StripedLevelWriteMap** — a two-level (2D) variant. Instead of one flat bucket array shared across all stripes, each stripe owns its _own_ bucket array inside a `Stripe<K,V>` object. This lets stripes resize independently (only the stripe's own lock is needed for reallocation, not all 32 locks). Reads are lock-free like in `StripedWriteMap`; visibility is via an `AtomicInteger size` per stripe.

#### Family 3: Lock-Free

**HashTrieMap** — a concurrent hash trie (Ctrie) based on Prokopec et al. (2011–2017). Uses `AtomicReferenceFieldUpdater` on `INode.main` for compare-and-swap (CAS) without `synchronized`. The trie has a configurable fan-out width (default 6 bits per level, giving 64 children per `CNode`). On a failed CAS, the operation restarts from scratch (the `RESTART` result type). Deletion uses tombstoning (`TNode`) to allow safe compaction. No locks anywhere; all mutations go through CAS loops.

**WrapConcurrentHashMap** (WrapCHM) — a thin wrapper around Java's `java.util.concurrent.ConcurrentHashMap`. This is the JDK's battle-hardened, segment-based implementation with dynamic concurrency level, tree-ification of long buckets, and extensive JIT optimization. It serves as the production baseline.

---

## SECTION 5 — Benchmark Design

### Slide 1: Workload Space — 18 Configurations per Implementation

```
8 implementations
  × 3 read ratios    (0.8 / 0.5 / 0.2)
  × 2 key ranges     (1,000 / 1,000,000)
  × 3 distributions  (uniform / zipfian-0.5 / zipfian-0.99)
= 144 total benchmark configurations
```

**Read ratios (0.8 / 0.5 / 0.2):**
- Each iteration, a thread picks a key, then with probability `readRatio` calls `get`; otherwise with 50/50 probability calls `put` or `remove`.
- 0.8: read-heavy (realistic for caches, lookup tables)
- 0.5: balanced
- 0.2: write-heavy (stress-tests lock contention and GC pressure)

**Key ranges — the cache boundary:**
- **1,000 keys** — the working set fits inside the RPi's 2 MB L3 cache. Cache misses are rare; the bottleneck is lock contention or CAS retries. Both platforms keep the hot data warm.
- **1,000,000 keys** — the working set exceeds the RPi's L3 cache (and stresses even the HPC's large cache under uniform access). Memory latency and cache miss rates become the dominant cost, and implementations that require following many pointers to complete a single operation — like HashTrieMap's INode → CNode → SNode traversal — pay a higher penalty per operation than flat-array structures that resolve a lookup in one or two memory accesses.

**Distributions:**
- **Uniform** — every key equally likely. Maximally spreads load across stripes.
- **Zipfian-0.5** (moderate skew) — mild hot-key concentration. Models typical in-memory caches.
- **Zipfian-0.99** (heavy skew) — a small fraction of keys receives almost all traffic. Concentrates contention on a few stripes/buckets.

**Pre-sampled key array:**
- Before the benchmark starts, we draw 1 million keys from the chosen distribution and store them in an array. During the run, each thread steps through this array in order — no random number generation happening mid-measurement, just an array lookup. We also pre-fill the map with about half the key range before timing begins, so reads find real entries from the very first operation instead of hitting an empty map.

**Why these specific choices?**

_Why Zipfian distributions?_ Real workloads are rarely uniform. In web caches, databases, and key-value stores, a small fraction of keys absorbs a disproportionate share of traffic — the same pattern described by Zipf's law in word frequencies and Pareto's 80/20 rule in economics. We wanted to test whether our findings from uniform access hold when the workload is skewed, as it typically is in production. The two exponents cover a mild skew (0.5, like a reasonably popular cache entry) and a heavy one (0.99, like a viral item or a configuration value read millions of times per second).

_Why these read ratios?_ Different applications sit at different points on the read/write spectrum. A lookup table or in-memory cache is mostly reads (0.8). A key-value store doing both reads and updates is roughly balanced (0.5). An ingestion pipeline writing new sensor readings is write-heavy (0.2). We include all three to see whether optimizations like lock-free reads in `StripedWriteMap` actually help where reads dominate, or whether they disappear under heavy write pressure.

### Slide 2: JMH — Why We Used It and How We Configured It

**Why not a DIY timer?**
- The JVM's JIT compiler observes what code runs and optimizes it aggressively. A naive `System.nanoTime()` loop will measure a different compiled artifact than the code you think you're measuring — branches get folded, computations get hoisted, and the JIT may eliminate the map operations entirely if it proves the results are unused.
- JMH is designed specifically to defeat these artifacts.

**Key JMH mechanisms we relied on:**

| Mechanism | Our setting | Purpose |
|---|---|---|
| `@Warmup(iterations=5, time=2s)` | 5 × 2s | Let the JIT compile and stabilize the hot path before recording. By iteration 5, the bytecode interpreter has been replaced by optimized machine code. |
| `@Measurement(iterations=10, time=1s)` | 10 × 1s | 10 independent measurements give us a distribution, not a single sample. JMH reports mean ± 99.9% CI. |
| `@Fork(2)` | 2 forks | Each fork launches a fresh JVM process. JIT profiles do not carry over between forks, so we get two fully independent optimization histories. This prevents a lucky (or unlucky) JIT compilation from dominating the result. |
| `Blackhole.consume()` | on every `get` return | Forces the JIT to treat the return value as observable. Without this, the compiler can prove the result is unused and eliminate the `get` call entirely. |
| `@State(Scope.Benchmark)` | for map + keys | One shared map instance per benchmark configuration — all threads operate on the same map, which is the correct model for concurrent data structure testing. |
| `@State(Scope.Thread)` | for `ThreadState` | Each thread gets its own `Random` instance and array index, seeded from `Thread.currentThread().getId()`. Threads do not share random state, so their key sequences are independent. |

**Fork isolation is especially important here:** without forking, the JIT's adaptive compilation for `SynchronizedMap` could influence how `HashTrieMap` is compiled in the same run. With 2 forks, each configuration gets a clean JVM with no optimization history.

### Slide 3: Aggregation — Why Geometric Mean

**The problem with arithmetic mean:**
- Our throughput values span roughly two orders of magnitude: `SynchronizedMap` at high contention produces ~4 Mops/s; `WrapConcurrentHashMap` at 64 threads produces ~211 Mops/s.
- Arithmetic mean gives the same absolute weight to each data point. A 50 Mops/s improvement on WrapCHM and a 50 Mops/s improvement on SynchronizedMap look identical, but the latter is a 10× improvement while the former is barely a 30% change.
- When summarizing across configurations that differ by two orders of magnitude, arithmetic mean is dominated by the high-throughput cases and masks what happens at the low end.

**Why geometric mean:**
- The geometric mean gives equal weight to equal _relative_ changes. A doubling is a doubling, regardless of the baseline.
- It is the natural aggregate for ratios and throughput comparisons across heterogeneous workloads.
- Concretely: `geomean([4, 200]) ≈ 28.3`, not `102`. This keeps SynchronizedMap's behavior visible in the aggregate.
- Formally: `geomean(x₁, …, xₙ) = exp(mean(log(x₁), …, log(xₙ)))`.

**In the figures:** every "summary" bar or point in our cross-platform figures is a geometric mean across the 18 workload configurations (3 read ratios × 2 key ranges × 3 distributions) for a given implementation and thread count.

---

## SECTION 6 — Findings

### Slide 1: The Overall Ranking Transfers (Fig. 1 — Slope Chart)

**What the figure shows:** a bump (slope) chart. Left axis: implementation rank on RPi5 at peak thread count (4), under Zipfian-0.99. Right axis: rank on HPC at peak thread count (64). A line that crosses others means the implementation's rank changed across hardware.

**Main result:** the broad ranking is stable.
- `WrapConcurrentHashMap` is first on both platforms. This is expected: the JDK's implementation has been tuned by expert engineers for decades, benefits from JIT-specific intrinsics, and adapts its concurrency level dynamically.
- `SynchronizedMap` is last on both platforms. With a single global lock, adding threads strictly increases contention with no parallelism; throughput _falls_ as thread count rises. This is the expected sanity-check result.
- The striped variants cluster in the middle and maintain their relative order across platforms.

**Interpretation:** the algorithmic properties that make an implementation good (fine-grained locking, lock-free reads, adaptive sizing) are relevant regardless of hardware tier. The research question's first sub-answer is: yes, the hierarchy transfers.

### Slide 2: The Central Outlier — HashTrieMap (Fig. 1)

**The notable exception:** `HashTrieMap` ranks **7th out of 8 on RPi5**, but **2nd out of 8 on HPC**. This is the most striking finding of the paper.

**Why does it fall on RPi?**

Two reinforcing mechanisms:

1. **Pointer-chasing and cache misses.** The Ctrie is a tree-structured data structure. Every `get` or `put` traverses a sequence of `INode → CNode → INode → SNode` hops, each of which is a pointer dereference to a different memory location. On the RPi's 2 MB L3 cache, with 4 threads all touching a large key range (1M keys), these indirections frequently miss L3 and go to main memory. Each miss costs ~100+ ns on LPDDR4X. Flat-array structures like `StripedMap` have far fewer indirections per operation.

2. **GC pressure from immutable node allocation.** Every insert or update in HashTrieMap allocates new `CNode` arrays, new `SNode` wrappers, and sometimes new `INode` containers. Even for a key whose value has not changed, the path from root to that key is rewritten with new objects. On the RPi, with limited heap and a JVM GC that competes with benchmark threads for CPU cycles (only 4 cores total), GC pauses and GC overhead reduce net throughput significantly.

**Why does it excel on HPC?**

1. **Larger cache and far higher memory bandwidth.** The DGX Spark has 24 MiB L3 (vs 2 MiB on RPi) and ~273 GB/s memory bandwidth (vs ~17 GB/s on RPi — a 16× difference). Hot trie nodes are more likely to stay in the larger L2/L3, and even on a cache miss the data arrives far faster. The pointer-chasing penalty per miss is much lower.

2. **More cores absorb GC cost.** With 20 cores, GC threads can run on otherwise-idle cores and compete less with benchmark threads than they do on the RPi's 4-core setup. The JVM can collect more aggressively in the background.

3. **Lock-free scalability.** At higher thread counts, lock-based implementations face growing contention (threads queue for stripe locks). HashTrieMap's CAS loop means threads never block; they retry on conflict instead of queuing. This matters most when many threads are active simultaneously.

**Practical implication:** choosing HashTrieMap for a 4-core embedded device would give you near-worst performance. The same choice on a 20-core server gives you near-best. The algorithm is not universally good or bad — its goodness is hardware-dependent.

### Slide 3: The Hardware Ceiling (Fig. 2 — Scalability)

**What the figure shows:** a 2×2 grid — RPi and HPC columns, 1K-key and 1M-key rows. Each panel shows geometric mean throughput vs. thread count for all 8 implementations.

**RPi — saturation at 4 threads:**
- Every single implementation, regardless of design, levels off completely at 4 threads and does not improve from 4 → 8 threads.
- The reason is physical: the RPi has 4 CPU cores. At 4 threads, all cores are busy. Adding a 5th–8th thread means time-slicing — threads take turns on the same cores, adding context-switch overhead with no additional parallelism.
- The hardware ceiling is hit before any algorithmic differences between implementations become meaningful at higher thread counts.

**Practical consequence for the RPi:**
- If your device has 4 physical cores and you're considering concurrent hash maps, the choice of implementation barely matters. Any correctly thread-safe implementation will perform similarly at 4 threads.
- Under these conditions, you should prefer the **simplest, lowest-overhead implementation** — likely `StripedWriteMap` (correct, fast, low GC pressure, easy to audit) — rather than the theoretically sophisticated but practically disadvantaged HashTrieMap.

**HPC — continued scaling:**
- The striped variants, WrapCHM, and especially HashTrieMap continue to benefit from additional threads up to 32–64.
- SynchronizedMap actually loses throughput as threads increase beyond 1, confirming the single-lock contention model.
- The 1M-key vs 1K-key split is visible: under 1M keys, even the HPC sees performance degradation on implementations with poor locality (long pointer chains), though less severe than on the RPi because of the larger cache.

### Slide 4: Zipfian Skew Is Platform-Dependent (Fig. 4 — Distribution Sensitivity)

**What the figure shows:** for each implementation and each key range, the percentage throughput change when moving from uniform access to Zipfian-0.99 (heavy skew), at peak thread count. Positive = skew hurt, negative = skew helped.

**1K key range (fits in RPi L3):**
- Both platforms see a throughput _decrease_ under high skew.
- Mechanism: with only 1,000 keys and heavy skew, nearly all traffic concentrates on a handful of keys, which map to the same stripe. Multiple threads compete for the same stripe lock repeatedly, creating a hot-stripe bottleneck. The parallelism that striping was supposed to provide largely disappears.
- The HPC sees this more severely than the RPi, because the HPC has more threads simultaneously competing for the same hot stripe.

**1M key range (exceeds RPi L3 cache):**
- **RPi:** skew _helps_. With 1M keys and only 4 threads, uniform access scatters reads across the full key space, generating frequent L3 cache misses. High Zipfian skew means most accesses go to a small set of hot keys that remain in L1/L2. Even with some lock contention, fewer cache misses outweighs the lock overhead at just 4 threads.
- **HPC:** skew _hurts_. With 24 MiB L3 and 273 GB/s memory bandwidth, the HPC resolves cache misses cheaply enough that uniform access across 1M keys is tolerable. High skew then adds thread contention on hot stripes without offering a meaningful cache benefit. At peak thread counts, the contention cost dominates.

**Key insight:** the same workload characteristic (high key skew) has opposite effects on the two platforms. An optimization that targets high-skew workloads on one tier could actively harm performance on the other.

### Slide 5: How Much Faster Is HPC? (Fig. 3 — Hardware Advantage Heatmap)

**What the figure shows:** a heatmap where each cell is `log₂(HPC_throughput / RPi_throughput)`, geometric mean across all 18 workload configurations, at matched thread counts (1, 2, 4, 8 — the common range).

**Below 8 threads:** HPC is consistently about **2× faster** across all implementations. At equal thread counts (e.g., both running 4 threads), the dominant factor is raw per-core performance: the DGX Spark's ~4 GHz vs RPi's ~2.4 GHz, plus the HPC's superior memory bandwidth and larger L2 cache.

**Implication:** the ~2× advantage at low thread counts is plausibly explained by the clock-speed ratio alone (~4/2.4 ≈ 1.67×), with memory bandwidth and L2 making up the rest. At this range, algorithmic differences matter less than raw clock and memory speed.

**Beyond 8 threads:** the HPC's advantage grows substantially, but only the HPC _has_ threads beyond 4 (the RPi saturates). The heatmap captures this as the HPC-only columns extending rightward.

---

## SECTION 7 — Discussion and Implications

### Slide 1: Practical Guidelines

From our data, two concrete guidelines emerge:

**For devices with few cores and small last-level cache (RPi profile):**
- Use the simplest implementation with the lowest overhead. `StripedWriteMap` is the best choice: lock-free reads eliminate read contention, immutable nodes are GC-friendly (they reuse unchanged path segments when possible), and there are no pointer-chasing trie traversals.
- Avoid `HashTrieMap`: the pointer-chasing traversal and allocation pressure outweigh the CAS-based scalability benefit when you only have 4 cores.
- Do not overengineer: you will saturate at the physical core count before algorithmic differences have room to matter.

**For many-core servers with large caches (HPC/server profile):**
- Use `WrapConcurrentHashMap` (industry-hardened) or `HashTrieMap` (best scaling at high thread counts). Both benefit from the larger cache and higher memory bandwidth reducing pointer-chasing costs, and from GC threads competing less for CPU time on a 20-core machine.
- The padded variants (`StripedMapPadded`, `StripedWriteMapPadded`) provide measurable benefit over their unpadded counterparts at high thread counts due to false-sharing reduction.

---

## SECTION 8 — Future Work

### Slide 1: Hardware-Level Profiling

Our current findings rest on inference: we observe throughput and explain the pattern using cache sizes and core counts, but we did not directly measure cache miss rates, CAS retry frequencies, or memory bandwidth utilization.

Running the same benchmark suite under Linux `perf stat` (already included in our Nix flake as `linuxPackages.perf`) would yield hardware performance counters: L1/L2/L3 miss rates per benchmark configuration, CPU cycle counts, instruction-per-cycle ratios. This would convert our inferences about HashTrieMap's cache-miss overhead into direct evidence — or reveal that another mechanism (GC pauses, branch misprediction) is the dominant factor.

### Slide 2: Latency Distribution Instead of Mean Throughput

We measured throughput (operations per second). Tail latency (the 99th or 99.9th percentile operation time) is the metric that matters for real-time applications like bedside diagnostics, where a 10ms spike is unacceptable even if the average is 0.1ms.

CAS retry loops (in HashTrieMap) and lock contention spikes (in StripedMap under Zipfian workloads) would produce very different latency histograms than their throughput numbers suggest. A future study should record latency histograms using JMH's `@BenchmarkMode(Mode.SampleTime)` or external percentile tracking.

### Slide 3: Broader Coverage of the Low End

Our "resource-constrained" tier is the RPi 5, which is actually quite capable within the embedded world — it has an L3 cache, hardware-accelerated I/O, and runs a full Linux kernel.

Devices at the true low end (e.g., BeagleBone Black: no L3 cache at all, single-core Cortex-A8) would expose hardware–algorithm interaction that the RPi partially masks. Whether any fine-grained or lock-free implementation can outperform `SynchronizedMap` on a single-core device is an open question.

### Slide 4: Hardware-Adaptive Implementation

Our findings point toward a clear design direction: the optimal implementation is hardware-dependent, and the decision criteria are knowable at runtime (number of logical processors, size of last-level cache).

A hash map that queries `Runtime.getRuntime().availableProcessors()` and `java.lang.management.OperatingSystemMXBean` at startup, then selects the underlying implementation based on these values, would give application developers a single API that performs near-optimally on both a quad-core embedded board and a 20-core server — without requiring them to know the hardware in advance.

This is a natural thesis project extension of the current work.

### Slide 5: Additional Lock-Free Designs and Data Structures

We included one lock-free structure (HashTrieMap) alongside one JDK-provided concurrent map (WrapCHM). A more complete picture would include:
- A CAS-based flat-array implementation (e.g., open-addressing with linear probing and CAS on slots) to separate the "lock-free" property from the "pointer-chasing trie traversal" property.
- Other concurrent data structures (concurrent skip lists, concurrent B-trees) measured on the same hardware pair.
- A systematic literature review to position our findings relative to the broader concurrent data structures literature.

---

## APPENDIX — Figures Reference

| Figure | File | What it answers |
|---|---|---|
| Fig 1 | `fig1_performance_overview.png` | Do rankings hold across hardware? (slope/bump chart) |
| Fig 2 | `fig2_scalability.png` | Where does the hardware ceiling appear? (thread scaling, 2×2 grid) |
| Fig 3 | `fig3_hardware_advantage.png` | How much faster is HPC? (log₂ speedup heatmap) |
| Fig 4 | `fig4_distribution_sensitivity.png` | Does Zipfian skew help or hurt, per platform? (bar chart, % change) |
| Fig 5 | `fig5_read_ratio.png` | Do read-optimized designs benefit under read-heavy loads? |

---

## APPENDIX — Implementation Summary Table

| Implementation | Family | Reads lock? | Writes lock? | GC pressure | Key property |
|---|---|---|---|---|---|
| SynchronizedMap | Coarse | Yes | Yes | Low | Single global lock |
| StripedMap | Fine-grained | Yes | Yes | Low | 32 stripes, mutable nodes |
| StripedMapPadded | Fine-grained | Yes | Yes | Low | As above + cache-line padding |
| StripedWriteMap | Fine-grained | **No** | Yes | Medium | 32 stripes, immutable nodes |
| StripedWriteMapPadded | Fine-grained | **No** | Yes | Medium | As above + cache-line padding |
| StripedLevelWriteMap | Fine-grained | **No** | Yes | Medium | Per-stripe bucket arrays, independent resize |
| HashTrieMap | Lock-free | **No** | **No** (CAS) | **High** | Ctrie, pointer-chasing, restart on conflict |
| WrapConcurrentHashMap | JDK | **No** | Yes (internal) | Low | JDK ConcurrentHashMap wrapper |
