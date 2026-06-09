# Week 6 — Quiz

Thirteen questions on GKE architecture, Autopilot constraints, Workload Identity, PDB/HPA/VPA, and upgrades. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 7. Answer key at the bottom — don't peek.

---

**Q1.** On a GKE cluster, which component is **always** Google-managed regardless of Autopilot or Standard mode?

- A) The node pools.
- B) The control plane (API server, etcd, scheduler, controller-manager).
- C) The pods' resource requests.
- D) The Workload Identity bindings.

---

**Q2.** Your stateless service runs as three small pods (0.5 vCPU / 512 MiB each), 24/7. On Standard you would need a three-node regional pool for zonal spread, mostly idle. Which mode is likely cheaper for *this* workload, and why?

- A) Standard, because committed-use discounts always beat Autopilot.
- B) Autopilot, because it bills the pods' resource requests, not idle node capacity.
- C) Identical, because both charge the same per-cluster fee.
- D) Standard, because Autopilot cannot run pods smaller than 1 vCPU.

---

**Q3.** You `kubectl apply` a pod with `securityContext.privileged: true` to an Autopilot cluster. What happens?

- A) It runs; Autopilot allows privileged pods on the `performance` compute class.
- B) It is rejected at admission by GKE Warden with a constraint-violation message.
- C) It schedules but silently never starts, with no error.
- D) Autopilot converts it to a non-privileged pod automatically and runs it.

---

**Q4.** The Autopilot decision procedure has two checks. In what order do you run them?

- A) Cost first (cheaper mode wins), then feature constraints.
- B) Feature constraints first (does it need something Autopilot forbids?), then cost.
- C) Always Autopilot; there is no procedure.
- D) Always Standard for production; Autopilot is dev-only.

---

**Q5.** With Workload Identity, how does a pod authenticate to a Google API with no key file?

- A) A key file is mounted as a Kubernetes Secret at startup.
- B) The application calls the GKE metadata server via ADC, which mints a short-lived OAuth token for the bound Google service account.
- C) The pod SSHes to the node and uses the node's service account.
- D) The kubelet copies the project's default key file into every container.

---

**Q6.** A `/read` endpoint that uses Workload Identity returns HTTP **403** after you removed the GSA's `roles/storage.objectViewer` grant. What does the 403 (rather than an auth/identity error) tell you?

- A) Workload Identity failed; the pod has no identity.
- B) The identity resolved correctly (authentication succeeded) but lacks authorization for the object. Auth-n and auth-z are separate.
- C) The metadata server is down.
- D) The key file expired.

---

**Q7.** Which two PodDisruptionBudget fields are **mutually exclusive** (you set one, never both)?

- A) `minAvailable` and `selector`.
- B) `maxUnavailable` and `selector`.
- C) `minAvailable` and `maxUnavailable`.
- D) `minAvailable` and `replicas`.

---

**Q8.** You set `minAvailable: 3` on a Deployment with exactly 3 replicas, then start a node upgrade. What happens to the upgrade?

- A) It completes normally; the PDB is satisfied.
- B) It stalls — no pod may ever be evicted without breaching `minAvailable`, so every drain is refused until GKE times out and reports failure.
- C) The PDB is ignored during upgrades.
- D) GKE automatically scales the Deployment to 4 to make room.

---

**Q9.** A plain `kubectl delete pod` is **not** blocked by a PodDisruptionBudget, but a node drain during an upgrade **is** paced by it. Why?

- A) `delete` uses the eviction API; drains do not.
- B) Drains use the **eviction API**, which enforces the PDB; a plain `delete` bypasses the eviction API and the PDB.
- C) PDBs only apply to pods older than one hour.
- D) `delete` is gated by the PDB only on Autopilot.

---

**Q10.** You want to autoscale the FastAPI Deployment on **requests-per-second**, not CPU. What component lets the HPA read that metric from Cloud Monitoring?

- A) The VerticalPodAutoscaler.
- B) The Custom Metrics Stackdriver Adapter, which exposes the metric on the `custom.metrics.k8s.io` API.
- C) The cluster autoscaler.
- D) The GKE metadata server.

---

**Q11.** Why is running an HPA-on-CPU and a VPA in `Auto` mode on the **same** Deployment a known foot-gun?

- A) They are incompatible APIs and Kubernetes rejects both.
- B) Both react to CPU: the VPA changes the pod's CPU *requests* while the HPA scales replica count off CPU utilization, and they fight each other into oscillation.
- C) The VPA deletes the HPA on apply.
- D) It is fine; there is no conflict.

---

**Q12.** With a node-pool upgrade configured as `strategy=SURGE, max_surge=1, max_unavailable=0` and a `minAvailable: 2`-of-3 PDB, what is the **availability cost** during the upgrade?

- A) High — up to all three pods can be down at once.
- B) Effectively zero — the surge node is added on the new version *before* an old node is drained, so capacity never dips, and the PDB ensures at least 2 pods stay Ready.
- C) Total outage — surge upgrades take the whole pool down.
- D) Unknowable without blue-green.

---

**Q13.** A blue-green node-pool upgrade costs the **least availability** but the **most** of what?

- A) Security.
- B) Time and money (you provision an entire parallel node pool and hold both through the soak).
- C) Control-plane stability.
- D) Nothing; blue-green is strictly better than surge on every axis.

---

## Answer key

> No peeking until you've answered all thirteen.

**A1 — B.** The control plane (API server, etcd, scheduler, controller-manager) is always Google-managed on GKE. What differs between modes is the node plane: you own node pools on Standard; Google owns the nodes on Autopilot. (Lecture 1, §1.1.)

**A2 — B.** Autopilot bills the sum of pod resource requests, not node capacity. Three small pods that would leave a three-node Standard pool mostly idle are cheaper billed per-request on Autopilot. (Lecture 1, §1.2 — the small/spiky/low-density case where Autopilot's constraints save money.) Committed-use discounts (A) help Standard but only matter at dense, steady scale; Autopilot floors are 0.25 vCPU, not 1 (D).

**A3 — B.** GKE Warden, Autopilot's admission webhook, rejects the privileged pod synchronously at `kubectl apply` with a constraint-violation message naming `autogke-disallow-privilege`. It does not silently fail (C) or auto-fix (D). (Lecture 1, §1.5.)

**A4 — B.** Feature constraints first: if the workload needs something Autopilot forbids (privileged, host network, custom CNI/node image/kubelet flag), you are on Standard and the cost question is moot. Cost second. A cheaper option you cannot use is not an option. (Lecture 1, §1.4.)

**A5 — B.** The application uses Application Default Credentials, which on GKE resolve to the metadata server; the metadata server checks the KSA→GSA binding and mints a short-lived OAuth token for the bound GSA. No key file is created at any point. (Lecture 1, §1.6; Exercise 2.)

**A6 — B.** A 403 means the request was *authenticated* (the identity resolved) but *not authorized* (the identity lacks the IAM grant). Authentication and authorization are separate concerns; Workload Identity handled the first, IAM the second. An identity failure would not produce a clean 403 on the GCS read. (Exercise 2, negative test.)

**A7 — C.** `minAvailable` and `maxUnavailable` are mutually exclusive in a PDB — set exactly one. For autoscaled sets, `maxUnavailable` as a percentage is usually better because it tracks the changing replica count. (Lecture 2, §2.3.)

**A8 — B.** `minAvailable: 3` of 3 means no pod may ever be evicted without breaching the budget, so every drain is refused and the upgrade stalls until GKE times out and reports failure. Set `minAvailable` strictly below the replica count. (Lecture 2, §2.3.)

**A9 — B.** The eviction API enforces the PDB; a plain `delete` bypasses it. Node drains (during upgrades, autoscaler scale-down, etc.) go through the eviction API, which is *why* the PDB paces an upgrade. (Exercise 1, Step 7; Lecture 2, §2.3.)

**A10 — B.** The Custom Metrics Stackdriver Adapter reads the metric from Cloud Monitoring and exposes it on the `custom.metrics.k8s.io` API, which the HPA v2 consumes. The adapter itself authenticates via Workload Identity. (Challenge 1, Part 2.)

**A11 — B.** Both react to CPU. The VPA in `Auto` mode rewrites the pod's CPU *requests*, while the HPA scales *replicas* off CPU utilization; changing requests moves the utilization target the HPA is chasing, and the two oscillate. Run VPA in `Off` (recommendation) mode alongside an HPA, or scale the HPA on a non-CPU metric (like RPS). (Mini-project; Lecture references to VPA modes.)

**A12 — B.** With `max_surge=1, max_unavailable=0` the surge node comes up on the new version before an old node is drained, so capacity never dips; the `minAvailable: 2` PDB keeps at least two pods Ready throughout. Availability cost is effectively zero — the trade is money (one surge node) and time (one node per wave). (Lecture 2, §2.4 and §2.6.)

**A13 — B.** Blue-green has the lowest availability cost (both versions run during the soak; rollback is near-instant) but the highest time and money cost (you provision and pay for an entire parallel pool and hold both through the soak). (Lecture 2, §2.5 and §2.6.)

---

*Score 11+/13 and you're ready for Week 7. Below that, re-read the lecture the questions you missed point to before moving on.*
