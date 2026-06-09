# Lecture 2 — The Four GKE Upgrade Strategies and What Each Costs in Availability

> **Reading time:** ~75 minutes. **Hands-on time:** ~50 minutes (you configure surge settings and watch a node-pool upgrade roll, with a PDB in the way).

This is the lecture that lets you run a GKE upgrade without paging anyone. By the end you can explain the difference between a control-plane upgrade and a node upgrade, choose a release channel and defend it, configure all four node-upgrade strategies, and — the part that matters in an incident — predict the availability cost of each one *before* you press the button. The thesis is simple and you should hold onto it through the whole lecture: **an upgrade is a controlled disruption, every strategy trades the same three currencies — availability, time, and money — and the strategy that costs the least availability costs the most of the other two.** There is no upgrade that costs nothing. Your job is to know which currency you are spending and how much.

## 2.1 — Two upgrades, not one

People say "upgrade the cluster" as if it is one operation. It is two, with different owners, different blast radii, and different controls.

The **control-plane upgrade** bumps the version of the API server, scheduler, controller-manager, and `etcd`. Google does this. On a **regional** cluster the control plane is replicated across three zones and upgraded one replica at a time, so the API stays reachable throughout — your workloads keep running, your `kubectl` keeps working (maybe with a momentary blip on a single in-flight request). On a **zonal** cluster the single control-plane replica goes *down* during its upgrade: `kubectl` stops responding, the HPA stops scaling, controllers stop reconciling — but your already-running pods keep serving traffic, because the data path does not flow through the control plane. This is the single best argument for a regional control plane: **a zonal cluster has a control-plane maintenance window during which you are flying blind.** The mini-project is regional for this reason.

The **node upgrade** replaces the node VMs with ones running the new node version (the `kubelet`, the container runtime, the node OS). This is the upgrade *you* control on Standard, and the one with the real availability cost, because upgrading a node means **draining it** — evicting every pod on it so it can be deleted and replaced. Draining is where your PodDisruptionBudgets, your `terminationGracePeriodSeconds`, your readiness probes, and your replica count all come together to decide whether the upgrade is invisible or an outage. The four strategies are four ways to sequence those drains.

A rule worth tattooing: **the node version must never lead the control-plane version.** GKE enforces version skew — nodes may run up to two minor versions *behind* the control plane, never ahead. So the order is always: control plane first (Google), nodes second (you, or Google via the channel). You cannot upgrade nodes to a version the control plane has not reached.

## 2.2 — Release channels: choosing how aggressively you ride

A **release channel** is a subscription to a stream of GKE versions, with an associated risk/recency trade. You set it at cluster creation. The four channels in 2026:

- **Rapid** — newest versions first, days after upstream Kubernetes GA. You get features early; you also get the bugs early. Appropriate for a non-production cluster where you want to canary the next version. Not appropriate for anything you page on.
- **Regular** — the default and the right answer for most production clusters. Versions land here a few weeks after Rapid, once they have soaked. This is what the mini-project uses.
- **Stable** — versions land here after a longer soak in Regular. Fewer, later upgrades. Appropriate for risk-averse production where you would rather be a quarter behind and certain.
- **Extended** — the longest support window per minor version (you can pin to a version for over a year before forced upgrade). Appropriate for workloads with heavy qualification requirements (regulated, or a vendor that certifies against specific Kubernetes minors).

The channel controls **when** auto-upgrades happen, not **whether**. Every channel auto-upgrades the control plane on Google's schedule and, by default, auto-upgrades the nodes to match within a maintenance window. You can pin a node pool to a specific version and pause auto-upgrade, but you cannot pause it forever — each version has an end-of-life, after which GKE force-upgrades you. The senior move is not "disable auto-upgrade"; it is "choose Regular, define a **maintenance window** during your low-traffic hours, set a **PodDisruptionBudget** that protects availability, configure a **surge strategy** that respects the PDB, and let auto-upgrade run inside those guardrails." You do not fight the upgrade; you shape it.

Define a maintenance window so upgrades never start during your peak:

```hcl
resource "google_container_cluster" "primary" {
  # ...
  maintenance_policy {
    recurring_window {
      # 02:00–06:00 UTC daily — pick your real low-traffic window.
      start_time = "2026-01-01T02:00:00Z"
      end_time   = "2026-01-01T06:00:00Z"
      recurrence = "FREQ=DAILY"
    }
  }
}
```

## 2.3 — The node-drain mechanics every strategy shares

Before the strategies, the shared mechanism. To upgrade a node, GKE **cordons** it (marks it unschedulable so no new pods land), then **drains** it (evicts the existing pods). Eviction is *graceful*: the API server sends each pod a `SIGTERM`, waits up to `terminationGracePeriodSeconds` (default 30s) for it to exit, then `SIGKILL`s it. The scheduler places the evicted pods on other nodes; the Deployment controller notices the replica deficit and may create replacements. If a **PodDisruptionBudget** would be violated by an eviction — i.e., evicting this pod would drop the set below `minAvailable` — the eviction API **refuses the eviction** and the drain **blocks** until enough replacement pods are Ready elsewhere to make room.

This is the crux. **A PDB does not prevent the upgrade; it paces it.** It forces GKE to wait for replacement capacity before taking down the next pod, which is exactly what keeps an upgrade from becoming an outage — and exactly what can stall an upgrade forever if you configure it impossibly (a `minAvailable` that equals your replica count means *no* pod may ever be evicted, and the drain blocks indefinitely; GKE will eventually time out and report the upgrade failed). Lecture-in-a-sentence: **set `minAvailable` strictly less than your replica count, or your PDB will deadlock your own upgrade.**

A correct PDB for a 3-replica service:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fastapi-pdb
spec:
  minAvailable: 2          # never drop below 2 of 3 during a voluntary disruption
  selector:
    matchLabels:
      app: fastapi
```

`minAvailable: 2` of 3 means GKE may evict exactly one pod at a time, wait for a replacement to become Ready, then evict the next. The upgrade proceeds; availability never drops below 2/3. If you had written `minAvailable: 3`, no eviction would ever be permitted and the drain would hang. If you had written nothing (no PDB), GKE would evict pods as fast as it could drain nodes, and a fast surge could briefly take all three down at once. The PDB is the throttle.

> **`minAvailable` and `maxUnavailable` are mutually exclusive** in a PDB — set one, never both. `minAvailable: 2` and `maxUnavailable: 1` express the same thing for a 3-replica set; pick the one that reads more clearly for your replica count. For autoscaled sets where the replica count changes, `maxUnavailable` (as a percentage) is usually the better choice because it does not need updating when the count changes.

## 2.4 — Strategy 1: Surge upgrade (the default)

Surge is the default and the one you will use 95% of the time. It works on a *single node pool* and rolls nodes in place, controlled by two settings inside `upgrade_settings`:

- **`max_surge`** — how many **extra** nodes GKE may add above the pool's size during the upgrade. These surge nodes come up on the *new* version first, giving the scheduler somewhere to put drained pods *before* old nodes go down.
- **`max_unavailable`** — how many nodes may be **simultaneously unavailable** (cordoned + draining) during the upgrade.

The two together set the upgrade's pace. The arithmetic GKE follows: it can have up to `max_surge` new nodes up and up to `max_unavailable` old nodes down at once, so the number of nodes it processes per "wave" is `max_surge + max_unavailable`.

The three configurations you should recognize on sight:

**`max_surge = 1, max_unavailable = 0`** — the safe default, and the one the mini-project uses.

```hcl
upgrade_settings {
  strategy        = "SURGE"
  max_surge       = 1
  max_unavailable = 0
}
```

GKE adds one new-version node, then drains one old node onto it (and onto existing capacity, respecting your PDB), deletes the drained node, adds the next new node, and so on. **Availability cost: effectively zero** — there is always at least the original capacity available because the surge node is added *before* the old one is removed. **Time cost: high** — nodes roll one at a time, so a 10-node pool takes ~10× one node's drain+replace time. **Money cost: one extra node's worth of compute for the duration of the upgrade** (the surge node).

**`max_surge = 0, max_unavailable = 1`** — the cheap-and-risky configuration.

```hcl
upgrade_settings {
  strategy        = "SURGE"
  max_surge       = 0
  max_unavailable = 1
}
```

No surge node is added. GKE drains one existing node, replaces it, then the next. **Money cost: zero extra** (no surge node). **Time cost: same as above** (one node at a time). **Availability cost: real** — during each node's drain you are down one node's worth of pod capacity, *and* this configuration is the one most likely to fight your PDB: if `max_unavailable: 1` would evict a pod that the PDB protects, the drain blocks and the upgrade stalls. Use this only when you have spare capacity baked into the pool and a PDB that permits the eviction.

**`max_surge = 3, max_unavailable = 0`** — the fast configuration.

```hcl
upgrade_settings {
  strategy        = "SURGE"
  max_surge       = 3
  max_unavailable = 0
}
```

GKE adds three surge nodes, drains three old nodes in parallel, repeats. **Time cost: low** — three nodes per wave. **Money cost: three extra nodes for the duration.** **Availability cost: still near-zero** (surge-before-drain), but with a sharper edge: draining three nodes at once evicts more pods at once, so your PDB had better permit it, and your replacement pods had better come Ready fast, or the wave stalls waiting on Ready replicas.

The trade in one line: **`max_surge` buys speed with money; `max_unavailable` buys money with availability.** The default `surge=1, unavailable=0` spends a little money and a lot of time to spend zero availability, which is the right default for production.

## 2.5 — Strategy 2: Blue-green upgrade

Blue-green is the heavyweight. Instead of rolling nodes within the pool, GKE stands up an **entire parallel set of new-version nodes** (the "green" pool) alongside the existing ("blue") nodes, drains workloads from blue to green in a controlled batch, holds both for a **soak time** so you can validate, and only then deletes the blue nodes. If the new version misbehaves during the soak, you **roll back** by draining green back to blue and deleting green — fast, because blue is still there.

```hcl
upgrade_settings {
  strategy = "BLUE_GREEN"
  blue_green_settings {
    standard_rollout_policy {
      batch_percentage    = 0.25   # move 25% of nodes per batch
      batch_soak_duration = "60s"  # wait 60s between batches
    }
    node_pool_soak_duration = "1800s"  # hold blue for 30 min after green is full
  }
}
```

**Availability cost: lowest of all strategies** — both versions run simultaneously during the soak, so there is never a capacity dip, and rollback is near-instant because the old nodes still exist. **Time cost: highest** — you provision a whole second pool and hold both through the soak. **Money cost: highest** — you pay for double the nodes for the duration of the upgrade (blue + green both running). Use blue-green for a workload where a bad upgrade is expensive enough to justify paying for a fast, capacity-preserving rollback path: a stateful tier you cannot lose, a node-version change you do not trust, a regulated workload that requires a documented rollback procedure.

The four strategies, then, are really **two strategies and two knobs**: SURGE (with the `max_surge`/`max_unavailable` knobs giving you the safe-default, cheap-risky, and fast variants) and BLUE_GREEN. When the syllabus says "four upgrade strategies," it means the three distinct SURGE configurations you must be able to reason about plus BLUE_GREEN — four operationally distinct behaviors, two underlying mechanisms.

## 2.6 — The cost table you should be able to reproduce from memory

| Strategy | Availability cost | Time cost | Money cost | Use when |
|---|---|---|---|---|
| **Surge `surge=1, unavail=0`** | ~zero (surge before drain) | High (1 node/wave) | +1 node for duration | Default production. Almost always this. |
| **Surge `surge=0, unavail=1`** | Real (down 1 node's capacity; fights PDB) | High (1 node/wave) | Zero extra | Tight budget, ample pool headroom, permissive PDB. |
| **Surge `surge=3, unavail=0`** | ~zero, sharper edge | Low (3 nodes/wave) | +3 nodes for duration | Large pool, want speed, can pay surge, PDB permits parallel evictions. |
| **Blue-green** | Lowest (both versions run; instant rollback) | Highest (provision 2nd pool + soak) | Highest (2× nodes for duration) | Can't lose the tier; need fast, validated rollback. |

If you can fill this table in from memory and explain *why* each row trades what it trades, you have the lecture. The exam question and the interview question are both "you need to upgrade a 20-node pool serving 10k RPS at 99.9% with a tight budget — which strategy and what settings?" The answer is `SURGE, max_surge=2 (or 3), max_unavailable=0`, a `maxUnavailable: 10%` PDB, a maintenance window in your trough, and a sentence about why not blue-green (cost) and why not `unavailable=1` (availability + PDB stall risk).

## 2.7 — Watching it happen: a real surge upgrade with a PDB in the way

Exercise 3 does this end-to-end with a load generator; here is the shape so the exercise lands. Assume a 3-node pool running a 3-replica FastAPI Deployment with the `minAvailable: 2` PDB from §2.3.

First, set the node pool's upgrade strategy to the safe default and a small surge:

```bash
gcloud container node-pools update default-pool \
  --cluster=crunch-standard \
  --region=us-central1 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

Find the available node version and start the node upgrade (the control plane is already on this version — Google upgraded it first):

```bash
gcloud container node-pools update default-pool \
  --cluster=crunch-standard \
  --region=us-central1 \
  --node-version=1.31.4-gke.1183000
```

Now watch the dance in two terminals. Terminal A:

```bash
kubectl get nodes -w
# A new node appears (the surge node, NotReady → Ready on the new version).
# An old node goes SchedulingDisabled (cordoned), then disappears (drained + deleted).
# Repeat until all original nodes are replaced.
```

Terminal B watches the PDB doing its job:

```bash
kubectl get pdb fastapi-pdb -w
# NAME          MIN AVAILABLE   ALLOWED DISRUPTIONS   CURRENT   DESIRED
# fastapi-pdb   2               1                     3         3
# When a drain wants to evict a FastAPI pod, ALLOWED DISRUPTIONS must be ≥1.
# If a second eviction is attempted while one replacement is still not Ready,
# ALLOWED DISRUPTIONS shows 0 and the drain WAITS — that is the PDB pacing the upgrade.
```

And the load generator (Exercise 3 provides a `hey`-based one) confirms the availability cost is what the table predicts: with `surge=1, unavailable=0` and `minAvailable: 2`, you should see **zero failed requests** through the entire upgrade. Flip the node pool to `surge=0, unavailable=1` and re-run, and — depending on timing and your `minAvailable` — you will either see brief 5xx blips as capacity dips below what the load needs, or a stalled upgrade as the PDB refuses the eviction. Producing both outcomes on purpose is the point of the exercise; you do not understand the strategies until you have watched one of them stall.

## 2.8 — Autopilot upgrades: same mechanics, fewer knobs

On Autopilot you do not manage node pools, so you do not set `max_surge` directly per pool — Google manages node upgrades for you within the release channel and your maintenance window. But the **PDB still applies**: Autopilot honors your PodDisruptionBudgets when it drains nodes to upgrade or to bin-pack, so the `minAvailable: 2` discipline from §2.3 is exactly as important on Autopilot as on Standard. The difference is that on Autopilot the *sequencing* of the drain is Google's to optimize and yours only to *constrain* (via the PDB and `terminationGracePeriodSeconds`), whereas on Standard you own both the constraint and the sequencing. This is one more entry in the Autopilot ledger: less control over *how* the upgrade rolls, in exchange for not having to configure it. As with everything in Lecture 1, it is a trade, and for most stateless services it is a trade worth making.

## 2.9 — Maintenance windows and exclusions: shaping *when* upgrades happen

You choose the strategy for *how* an upgrade rolls; you use **maintenance windows** and **maintenance exclusions** to choose *when*. These are the two controls that keep an auto-upgrade from starting in the middle of your Black Friday peak.

A **maintenance window** is a recurring time range during which GKE is *allowed* to perform automatic maintenance (control-plane and node auto-upgrades). Outside the window, GKE defers. You set it to your traffic trough:

```hcl
maintenance_policy {
  recurring_window {
    start_time = "2026-01-01T07:00:00Z"   # 07:00 UTC = your low-traffic hour
    end_time   = "2026-01-01T11:00:00Z"   # a 4-hour window
    recurrence = "FREQ=WEEKLY;BYDAY=TU,WE,TH"  # mid-week only, never Fri–Mon
  }
}
```

A **maintenance exclusion** is a one-off blackout: a date range during which *no* automatic maintenance happens at all, regardless of the window. Three scopes exist, and the scope determines what is still allowed:

- **`NO_UPGRADES`** — no control-plane and no node upgrades during the exclusion. The strongest freeze. Use it for a code-freeze week or a major launch.
- **`NO_MINOR_UPGRADES`** — patch upgrades still happen (security fixes you want), but no minor-version bumps. A middle ground.
- **`NO_MINOR_OR_NODE_UPGRADES`** — freezes minor and node upgrades but allows control-plane patches.

```hcl
maintenance_policy {
  maintenance_exclusion {
    exclusion_name = "black-friday-freeze"
    start_time     = "2026-11-25T00:00:00Z"
    end_time       = "2026-12-02T00:00:00Z"
    exclusion_options {
      scope = "NO_UPGRADES"
    }
  }
}
```

The limits matter: exclusions have maximum durations (a `NO_UPGRADES` exclusion lasts up to a bounded number of days; the longer scopes allow longer freezes, up to ~180 days for `NO_MINOR_OR_NODE_UPGRADES` on some channels). You cannot freeze forever — every version still has an end-of-life, and GKE force-upgrades you when it arrives. The discipline is: **a maintenance window for the routine, an exclusion for the exceptional, and a calendar reminder to lift the exclusion** so you do not accidentally fall off a supported version. A cluster frozen so long it is force-upgraded across two minor versions in one jump is a worse incident than the routine upgrade you were avoiding.

## 2.10 — Rolling back an upgrade

Upgrades go wrong. A new node version ships a `containerd` change that breaks an image you depend on; a `kubelet` change tightens a default your manifest relied on. Knowing the rollback path *before* you upgrade is the difference between a five-minute fix and an outage.

**Node-pool rollback (surge).** A surge upgrade rolls forward node by node. If you catch a problem mid-roll, you set the node pool's target version back to the old version, and GKE rolls the *remaining* nodes back — but nodes already replaced are on the new version and roll back the same node-by-node way. There is no instant "undo"; it is another surge in the reverse direction, with the same availability properties.

```bash
# Roll a node pool back to the previous version (another surge, in reverse).
gcloud container clusters upgrade crunch-standard \
  --region=us-central1 --node-pool=default-pool \
  --cluster-version="1.31.3-gke.1xxxxxx" --quiet   # the OLD version
```

**Node-pool rollback (blue-green).** This is blue-green's whole reason to exist. During the soak, the blue (old) nodes still exist. If green misbehaves, you abort and GKE drains green back to blue and deletes green — **near-instant**, because blue was never torn down. This is why you pay the double-node cost for blue-green: you are buying a fast, validated rollback path.

**Control-plane rollback.** You generally *cannot* roll the control plane back to a previous minor version — Kubernetes does not support downgrading the API server across a minor, and GKE does not expose it. This is the asymmetry that makes the **control-plane-first** ordering (§2.1) consequential: once the control plane is on the new minor, you are committed to it, and your only forward path is fixing the nodes/workloads to match. The mitigation is the release channel and the maintenance window: let versions soak in the channel before they reach you, and upgrade in a window where a problem is survivable. The senior habit is to **canary the new version on a non-production cluster in the Rapid channel** before your production Regular cluster reaches it, so you have seen the version run your workloads before it is irreversible.

## 2.11 — `terminationGracePeriodSeconds` and graceful shutdown: the other half of zero-downtime

A PDB controls *how many* pods drain at once; `terminationGracePeriodSeconds` and your app's signal handling control whether *each* draining pod finishes its in-flight requests or drops them. A surge upgrade with a perfect PDB still drops requests if your pods are `SIGKILL`ed mid-request.

The sequence when a pod is evicted: the API server sets a deletion timestamp, the endpoints controller removes the pod from the Service's endpoints (so new traffic stops routing to it), and the kubelet sends `SIGTERM`. Your app has `terminationGracePeriodSeconds` (default 30s) to finish in-flight work and exit; if it does not, it gets `SIGKILL`. Two things must be true for zero-downtime:

1. **The app handles `SIGTERM` gracefully** — stops accepting new connections, finishes in-flight requests, then exits. Uvicorn/FastAPI does this out of the box (it drains on `SIGTERM`), which is one reason the FastAPI service is a good zero-downtime demonstrator. Verify your `terminationGracePeriodSeconds` exceeds your longest in-flight request.
2. **There is a small `preStop` delay or readiness flip** so the load balancer / kube-proxy stops sending new traffic *before* the app starts refusing it. The race is: endpoint removal propagates asynchronously, so for a brief moment after `SIGTERM` the pod may still receive new connections. A `preStop` hook that sleeps a couple of seconds (or a readiness probe that fails immediately on shutdown) closes that race:

```yaml
        lifecycle:
          preStop:
            exec:
              command: ["sh", "-c", "sleep 5"]   # let endpoint removal propagate
        terminationGracePeriodSeconds: 30
```

This is why Exercise 3's load generator is the real test: a PDB plus surge config *looks* zero-downtime in `kubectl get`, but only the `hey` summary showing `[200] 72000` and zero non-200s *proves* the graceful-shutdown path also works. A PDB without graceful shutdown gives you "no pod was force-killed" but not "no request was dropped." You need both.

## 2.11a — The surge arithmetic, worked on a real pool

The §2.4 descriptions are easier to trust once you have walked the arithmetic on a concrete pool. Take a **12-node** node pool running a 24-replica Deployment (2 pods/node), with a `maxUnavailable: 25%` PDB (so at most 6 of 24 pods may be voluntarily disrupted at once).

**Config A — `max_surge=1, max_unavailable=0` (safe default).** GKE adds 1 surge node (13 nodes briefly), drains 1 old node's 2 pods onto the surge node and existing headroom, deletes the drained node (back to 12), repeats. Per wave: 1 node, ~2 pods evicted. The PDB permits up to 6 evictions at once, so the PDB never blocks — the *surge config* is the throttle here, not the PDB. Time: 12 waves × (provision + drain + delete) ≈ 12 × ~3–5 min ≈ **36–60 minutes**. Money: 1 extra node for the whole window. Availability: zero dip (surge-before-drain).

**Config B — `max_surge=3, max_unavailable=0` (fast).** GKE adds 3 surge nodes (15 briefly), drains 3 old nodes (~6 pods) in parallel, repeats. Now the PDB *does* engage: 6 pods evicted at once is exactly the PDB's `maxUnavailable: 25%` ceiling, so GKE evicts up to 6, waits for replacements to become Ready, then proceeds. Per wave: 3 nodes. Time: 4 waves ≈ **12–20 minutes** — roughly 3× faster than Config A. Money: 3 extra nodes for the window. Availability: zero dip, but the system runs at the PDB's edge, so a slow-to-Ready replacement stalls the wave until it recovers.

**Config C — `max_surge=0, max_unavailable=2` (cheap).** No surge nodes. GKE cordons and drains 2 nodes (~4 pods) at once, replaces them in place, repeats. The PDB permits 6, so 4 is fine — *but* during each wave the pool is down 2 nodes' worth of *scheduling capacity*, so the evicted pods must fit on the remaining 10 nodes. If the pool was packed tight, there is nowhere to put them and the drain stalls. Money: zero extra. Availability: real — you run with reduced capacity each wave, and if load is near the pool's ceiling, you drop requests.

The takeaway you should be able to reconstruct: **the surge knobs and the PDB are two throttles in series, and the tighter one wins.** With generous surge and a tight PDB, the PDB paces you. With no surge and a generous PDB, capacity-availability paces you. The safe production default — Config A with a sensible PDB — keeps both throttles slack so neither stalls, at the cost of being the slowest.

## 2.11b — HPA, the cluster autoscaler, and an upgrade all happening at once

In production an upgrade rarely happens in isolation. The HPA may be scaling the Deployment, the cluster autoscaler may be adding nodes, and the upgrade is draining nodes — simultaneously. The interactions you must anticipate:

- **HPA + drain.** When a node drains, its evicted pods are rescheduled and the Deployment's replica count is unchanged — the HPA does not see a reason to scale. But if the eviction briefly raises per-pod load on the remaining replicas (fewer pods absorbing the same traffic), the HPA may scale *up* mid-upgrade, which is fine: more replicas means the PDB has more headroom and the drain proceeds faster. An upgrade and an HPA scale-up are cooperative, not adversarial.
- **Cluster autoscaler + surge.** The surge nodes are added by the upgrade machinery, not the autoscaler, and are removed when the wave completes. The autoscaler does not fight this. But if the upgrade's drains push pods that do not fit on remaining nodes, the autoscaler may add *additional* nodes to place them — which is the autoscaler doing its job, at extra cost for the upgrade window. Budget for it.
- **Spot reclamation + upgrade.** On a spot pool (which the mini-project uses), Google may reclaim a spot node *during* the upgrade. This is an **involuntary** disruption — the PDB does **not** protect against it (the PDB only gates voluntary, eviction-API disruptions). The protection against spot reclamation is the same as always: enough replicas spread across enough nodes that losing one is absorbed, plus the HPA replacing capacity. An upgrade running concurrently with a spot reclaim is the realistic worst case, and the answer is the same answer as everywhere this week: multiple replicas, a sane PDB, honest readiness probes, and graceful shutdown.

The senior mental model: an upgrade is one more source of pod churn in a system that already churns (HPA, autoscaler, spot reclaims, rollouts). The same resilience primitives — replicas, PDB, readiness, graceful shutdown — protect against all of them. You do not need a special "upgrade safety" mechanism; you need the resilience you should already have, and the upgrade is just a test of it.

## 2.11c — A pre-upgrade checklist

Before you trigger any production node-pool upgrade, run this list. It is the difference between a non-event and a page.

1. **Confirm the control plane is already on the target version.** Nodes cannot lead it. `gcloud container clusters describe ... --format='value(currentMasterVersion)'`.
2. **Confirm every workload has a PDB with `minAvailable` strictly below its replica count** (or `maxUnavailable` as a non-100% percentage). A missing or impossible PDB is the most common cause of a stalled or destructive upgrade.
3. **Confirm readiness probes are honest** — a pod that reports Ready before it can actually serve will let the drain proceed into a capacity hole. Test the probe.
4. **Confirm graceful shutdown** — `terminationGracePeriodSeconds` exceeds your longest request, and the app drains on `SIGTERM` (§2.11).
5. **Confirm you are inside the maintenance window** (for auto-upgrades) or that you are running a manual upgrade in your trough.
6. **Confirm the surge config** — `max_surge >= 1, max_unavailable = 0` for zero-downtime, or blue-green for fast rollback, never `max_surge=0` on a tightly-packed pool.
7. **Have the rollback command ready** (§2.10) and know that the control plane cannot roll back across a minor.
8. **Have a load generator or real-traffic dashboard watching** so "zero traffic loss" is a measured claim, not a hope.

Eight checks, two minutes. The upgrade that pages someone is almost always one where two or more of these were skipped — a missing PDB *and* a dishonest readiness probe, or `max_surge=0` *and* a packed pool. Each check is cheap; skipping them is how a routine Tuesday upgrade becomes a Tuesday incident.

## 2.11d — Zonal vs. regional control-plane upgrades, in detail

Section 2.1 said a regional control plane upgrades non-disruptively and a zonal one has a window where you fly blind. The detail is worth pinning down because it is the single best argument for paying for a regional cluster, and it is a favorite interview question.

A **regional** control plane runs **three replicas** of the API server and `etcd`, one in each of three zones, behind a single endpoint. When GKE upgrades it, it takes **one replica at a time**: replica A is drained of leadership, upgraded, rejoined; then B; then C. Throughout, at least two replicas are serving, so the endpoint stays up. Your `kubectl` keeps working, the HPA keeps scaling, the controllers keep reconciling. A single in-flight API request *might* see a momentary connection reset as a replica cycles, and well-behaved clients (including `kubectl` and the controllers) retry transparently. The 99.95% SLA reflects this: the control plane is essentially always available across an upgrade.

A **zonal** control plane runs **one replica** in one zone. When GKE upgrades it, that single replica goes down for the duration of its upgrade — typically a few minutes. During that window: `kubectl` returns connection errors, the HPA cannot scale (it cannot read metrics or write replica counts), the Deployment controller cannot reconcile (a pod that crashes is not replaced until the control plane returns), and you cannot deploy. **Your already-running pods keep serving traffic** — the data path does not flow through the control plane — so a purely steady-state workload survives. But you are operating without a control plane for those minutes, and if *anything* needs the control plane during the window (a crash that needs rescheduling, a scale event, a deploy), it waits. The 99.5% SLA reflects this: the control plane has real, scheduled downtime.

The cost difference is the management fee structure, not a per-node cost — a regional and a zonal cluster of the same node shape cost nearly the same, and the regional control plane is worth the negligible difference for anything you page on. The mini-project is regional for exactly this reason. The only time zonal is defensible is a genuinely disposable dev cluster where a few minutes of control-plane downtime during an upgrade is a non-event. **For production, regional is the default, and "why is the control plane regional?" has a one-sentence answer: so an upgrade is invisible instead of a multi-minute window where I cannot react to anything.**

## 2.11e — Node-pool recreate: the blunt fourth option

The three surge configs and blue-green are the supported, graceful node-upgrade strategies. There is a blunter fourth approach you will see in Terraform-driven shops and should understand even though it is not a `upgrade_settings` strategy: **recreate the node pool.** You add a *new* node pool on the new version, migrate workloads to it (cordon and drain the old pool, or let the scheduler rebalance), then delete the old pool. In Terraform this often happens implicitly — a change to a node pool's immutable field (machine type, disk type, certain `node_config` attributes) forces Terraform to *replace* the pool, which is a recreate.

This is, in effect, a manual blue-green that *you* sequence rather than GKE. Done carefully (new pool up, PDB-respecting drain of the old, then delete) it gives you the same capacity-preserving, fast-rollback properties as blue-green. Done carelessly (`terraform apply` that deletes the old pool before the new one is Ready, or a drain without a PDB) it is an outage. The lesson for your Terraform: **know which node-pool fields are immutable and force replacement**, set `create_before_destroy` on the pool so the new one comes up before the old one goes down, and never let a `terraform apply` drain a pool without a PDB protecting the workloads on it. The mini-project's `ignore_changes = [version]` on the node pool exists precisely so that a manual `gcloud` upgrade does not trigger a Terraform-driven recreate you did not intend — a subtle but real foot-gun where your IaC and your upgrade tooling fight over the same field.

This is also why the four "strategies" framing is the right mental model rather than a rigid taxonomy: surge (three configs) and blue-green are the *managed* strategies, and node-pool recreate is the *you-sequence-it* version of blue-green that shows up whenever an immutable field changes. They all trade the same three currencies — availability, time, money — and the recreate is just the one where you, not GKE, hold the throttle.

## 2.12 — Summary and what to carry forward

- An "upgrade" is **two** upgrades: the **control plane** (Google's; non-disruptive on regional, a maintenance window on zonal) and the **nodes** (yours on Standard; the one with the real availability cost). Nodes never lead the control-plane version.
- Choose a **release channel** (Regular for most production), a **maintenance window** in your trough, and a **PDB** that protects availability. You shape auto-upgrade; you do not disable it.
- A **PDB paces** the upgrade by blocking evictions that would breach `minAvailable`. Set `minAvailable` **strictly below** your replica count or you deadlock your own upgrade. `minAvailable` and `maxUnavailable` are mutually exclusive.
- The four strategies are **SURGE** (three operationally distinct configs: safe-default `surge=1/unavail=0`, cheap-risky `surge=0/unavail=1`, fast `surge=N/unavail=0`) and **BLUE_GREEN**.
- **`max_surge` buys speed with money; `max_unavailable` buys money with availability; blue-green buys the lowest availability cost and fastest rollback with the highest money and time cost.** Reproduce the §2.6 table from memory.
- On **Autopilot** the mechanics are the same and the **PDB still applies**, but Google owns the sequencing and you only get to constrain it. One more entry in the convenience-vs-control ledger.
- Choose **regional** control planes for anything you page on: a regional upgrade is invisible (three replicas, one at a time), a zonal upgrade is a multi-minute window where you cannot react (§2.11d).
- Run the **eight-item pre-upgrade checklist** (§2.11c) before every production upgrade. The upgrade that pages someone almost always skipped two of the eight — usually a missing PDB and a dishonest readiness probe.
- An upgrade is just one more source of pod churn alongside the HPA, the autoscaler, and spot reclaims. The same resilience primitives — replicas, PDB, honest readiness, graceful shutdown — protect against all of them (§2.11b). There is no special "upgrade safety"; there is only the resilience you should already have, under test.

A closing word on judgment, the same one Lecture 1 ended on: there is no upgrade that costs nothing, and the strategy that costs the least availability costs the most time and money. The senior move is to know which currency you are spending, spend the cheap one for your situation, and *measure* the result rather than assume it. "We upgraded with surge `max_surge=2/unavailable=0` behind a `maxUnavailable: 25%` PDB during the 03:00 maintenance window, and `hey` showed zero non-200s across the roll" is a sentence you can say in a review. "The upgrade should be fine" is not. Exercise 3 makes you produce the first sentence with your own numbers; the capstone (Week 15) makes you defend an upgrade-and-rollback procedure for the whole system.

Next: the exercises. You will deploy the FastAPI service to Autopilot with a PDB (Exercise 1), wire Workload Identity so it reads GCS with no key file (Exercise 2), and run the real surge upgrade with a load generator proving zero traffic loss (Exercise 3).

---

**References**

- About cluster upgrades: <https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades>
- Node-pool upgrade strategies (surge, blue-green): <https://cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies>
- Configure maintenance windows and exclusions: <https://cloud.google.com/kubernetes-engine/docs/how-to/maintenance-windows-and-exclusions>
- Release channels: <https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels>
- Configure a PodDisruptionBudget: <https://kubernetes.io/docs/tasks/run-application/configure-pdb/>
- Pod termination and graceful shutdown: <https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination>
- `google_container_node_pool` (`upgrade_settings`): <https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/container_node_pool>

*Version strings (`1.31.4-gke.1183000`) are illustrative; check `gcloud container get-server-config --region=us-central1` for the versions actually available in your channel before you upgrade. The arithmetic and the strategy trade-offs in this lecture are stable; the version numbers are not.*
