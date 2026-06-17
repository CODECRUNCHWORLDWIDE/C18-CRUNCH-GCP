# Week 14 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 15. Answer key at the bottom — don't peek.

---

**Q1.** Which of these is **not** one of the five GCP defaults Lecture 1 says you must change on day one of a new org?

- A) External IPs are allowed on VMs.
- B) Service-account key creation is allowed.
- C) The default VPC network exists with permissive firewall rules.
- D) BigQuery on-demand pricing is enabled instead of slot reservations.

---

**Q2.** You apply `constraints/compute.vmExternalIpAccess` with `deny_all = "TRUE"` at the project level, then run `gcloud compute instances create probe-public` (no `--no-address`). What should happen, and what does it prove?

- A) It succeeds, because project-level org policy cannot override instance creation.
- B) It fails with a constraint-violation error, proving the control is enforced — and *seeing the deny* is the point, not the apply.
- C) It succeeds but logs a warning; org policy only audits, never blocks.
- D) It fails, but only because the project has no Cloud NAT configured.

---

**Q3.** Why does Lecture 1 insist that VPC Service Controls and Binary Authorization be rolled out in **dry-run** before enforcement, but the four "deny the lazy pattern" Org Policy constraints can go straight to enforce?

- A) Dry-run is only available for VPC SC and Binary Auth; Org Policy has no dry-run.
- B) The four Org Policy constraints break only bad habits (a public IP, a public bucket); VPC SC and Binary Auth can lock out your own *deploy pipeline*, causing a self-inflicted outage.
- C) Org Policy changes are instant; VPC SC and Binary Auth take 24 hours to propagate.
- D) Dry-run is more expensive, so you only use it where the control is risky to your budget.

---

**Q4.** A teammate enables CMEK on a new BigQuery dataset by setting `default_encryption_configuration.kms_key_name`, but every table write fails. The KMS key exists and the dataset was created. What is the most likely cause?

- A) The key is in a different project from the dataset.
- B) The BigQuery service agent (`bq-<projectnumber>@bigquery-encryption.iam.gserviceaccount.com`) was not granted `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the key.
- C) CMEK requires a 3-year key rotation period, not 90 days.
- D) BigQuery does not support CMEK; only Spanner does.

---

**Q5.** What threat does a VPC Service Controls perimeter primarily defend against?

- A) A DDoS attack against your public load balancer.
- B) A SQL-injection attempt in an HTTP request body.
- C) Data exfiltration from a protected service (e.g. BigQuery) using a *stolen but otherwise valid* credential, from outside the perimeter.
- D) A misconfigured firewall rule allowing SSH from 0.0.0.0/0.

---

**Q6.** In Binary Authorization, what exactly is an *attestation*, and who creates it in the Lecture 1 / Exercise 2 design?

- A) A scan report from Container Analysis; created automatically on push.
- B) A cryptographically signed statement that a specific image digest passed your pipeline, signed by an attestor's KMS key — created by the Cloud Build step after a successful build.
- C) An IAM binding that allows a pod to pull an image.
- D) A network policy that restricts which registries the cluster can pull from.

---

**Q7.** You flip a fresh Binary Authorization policy straight to `ENFORCED_BLOCK_AND_AUDIT_LOG` (skipping dry-run) on a running GKE cluster whose existing workloads were deployed before any attestor existed. What happens at the next rollout, including a legitimate one?

- A) Nothing — existing pods are grandfathered in forever.
- B) New pods whose images carry no attestation are denied at admission, so any rollout (legitimate or not) of an un-attested image fails — a self-inflicted outage. This is exactly why you dry-run first.
- C) The cluster control plane crashes.
- D) Only `nginx`-style public images are blocked; your own registry images are always allowed.

---

**Q8.** In a Cloud Billing export, you sum the `cost` column and report it as the bill. A colleague says you have overstated it. Why?

- A) `cost` is in micro-dollars and must be divided by 1,000,000.
- B) The real (effective) cost is `cost` plus the (negative) `credits`; reporting `cost` alone ignores discounts already earned (sustained-use, existing CUDs).
- C) `cost` includes tax, which you should exclude.
- D) `cost` double-counts each line item because the export streams duplicates.

---

**Q9.** A 1-year committed-use discount is 37% off the on-demand rate. At what utilization of the committed capacity does the commitment break even versus on-demand, and what is the rule?

- A) 37% — commit if you use it more than 37% of the time.
- B) 50% — commitments always break even at half utilization.
- C) 63% — you pay 63% of the on-demand rate up front regardless of use, so you must use the capacity at least 63% of the term; commit only above your demonstrated floor.
- D) 100% — commitments only pay off at full utilization.

---

**Q10.** Which workload is the **right** fit for spot/preemptible capacity?

- A) The single-replica Spanner primary holding your transactional state.
- B) A Dataflow batch pipeline whose bundles can be retried after a worker is preempted.
- C) The `min-instances=1` Cloud Run ingest service that must always answer.
- D) The GKE control plane.

---

**Q11.** A postmortem is described as "blameless." What is the primary *engineering* reason for this, not the social one?

- A) It is kinder to the engineer who made the mistake.
- B) If you blame people, they stop reporting near-misses and incidents, so you lose your best reliability data — and you fix processes, not people, because the next tired human will face the same process.
- C) Legal requires it.
- D) It makes the postmortem shorter.

---

**Q12.** In the no-blame postmortem template, why does the course prefer "contributing factors (plural)" over "root cause (singular)"?

- A) "Root cause" is a trademarked term.
- B) Complex-system failures rarely have a single cause; several factors line up, and each is a separate place to intervene — listing only one hides the others.
- C) There is no difference; they are synonyms.
- D) Regulators require at least three causes per incident.

---

**Q13.** Which section of the drill postmortem does the grading rubric weight most heavily, alongside the timeline and contributing factors?

- A) The summary, because it must be exactly two sentences.
- B) The "what went well" section.
- C) The action items — each must have an **owner and a due date**; an un-owned, undated action item is a wish, not a fix.
- D) The lessons-learned paragraph's word count.

---

## Answer key

**Q1 — D.** The five security defaults are external IP, SA key creation, public storage, the default network, and Data Access audit logs off. BigQuery pricing is a FinOps topic (Lecture 2), not one of the five security defaults.

**Q2 — B.** Project-level org policy *does* govern instance creation; the create fails with a `compute.vmExternalIpAccess` violation. The lecture's whole point is "verify the deny" — applying the policy is not enough; you must see it reject the forbidden action.

**Q3 — B.** The four lazy-pattern constraints only break bad habits and are independently safe to enforce. VPC SC and Binary Auth can lock out your own CI/CD identity, so you dry-run, read the would-deny log, fix your deploy path, and only then enforce. (Org Policy *also* supports dry-run; the point is which controls *require* it for safety.)

**Q4 — B.** Every CMEK-using Google service uses a per-service service agent that needs `cryptoKeyEncrypterDecrypter` on the key. Forgetting that grant is the #1 CMEK mistake; writes fail silently until it is fixed.

**Q5 — C.** VPC SC defends against data exfiltration with a stolen-but-valid credential from outside the perimeter. It is not a WAF (that is Cloud Armor) and not a firewall rule.

**Q6 — B.** An attestation is a KMS-signed statement that a specific image digest passed the pipeline, created by the Cloud Build signing step. Binary Authorization's admission controller verifies it with the attestor's public key before admitting a pod.

**Q7 — B.** Un-attested images are denied at admission, so the next rollout of any un-attested image — including a legitimate one — fails. This self-inflicted outage is exactly why you roll out in dry-run, confirm existing workloads are attested, and only then enforce.

**Q8 — B.** Effective cost = `cost` + `credits` (credits are negative). Reporting `cost` alone overstates the bill by the discounts you already earn. You must `UNNEST` the repeated `credits` field to compute it.

**Q9 — C.** A 37%-off CUD means you pay 63% of the on-demand rate up front for the whole term regardless of use, so breakeven is 63% utilization. Commit only above your demonstrated floor; below breakeven the "discount" costs more than on-demand.

**Q10 — B.** Spot fits fault-tolerant, retryable work — a Dataflow batch pipeline. It is wrong for stateful primaries, must-always-answer services, and control planes, which cannot survive a 30-second preemption.

**Q11 — B.** Blameless is an engineering choice: blame stops the flow of near-miss and incident reports (your best reliability data), and you fix processes rather than people because the process is what the next tired human will face.

**Q12 — B.** Complex-system failures have multiple contributing factors that line up; each is a distinct intervention point. Forcing a single "root cause" hides the other factors you also need to fix.

**Q13 — C.** The rubric weights the timeline, the contributing factors, and the action items. Each action item must have an owner and a due date; an un-owned, undated item is a wish, not a fix.
