# Week 3 — Challenges

One challenge this week. It is the full version of the hands-on lab from the syllabus, and it is deliberately harder and more open-ended than the exercises: you get acceptance criteria, not a step-by-step. No solution is provided. You'll re-use the bones of what you build here in the mini-project, so do it well.

| # | File | What you build | Est. time |
|---|------|----------------|-----------|
| 1 | [challenge-01-multi-region-shared-vpc.md](./challenge-01-multi-region-shared-vpc.md) | A multi-region shared VPC with three regional subnets, Cloud NAT for egress in each region, Private Google Access for `*.googleapis.com`, and a hierarchical firewall policy. Validate it with `traceroute` and BGP route inspection on the Cloud Router. | 2.5–4 h |

## Ground rules

- **Terraform (or OpenTofu) only.** No console click-ops except to *inspect*. If you click to create, you fail the spirit of the week.
- **No instance gets an external IP.** Egress is Cloud NAT; API access is Private Google Access. If any VM has a public IP, the challenge is not done.
- **The IAP lifeline rule goes in first.** You must be able to SSH to your probe VMs through IAP at all times.
- **Validate, don't assume.** Every claim ("the subnets reach each other," "the VIP is private," "the route is advertised") must be backed by a Connectivity Test, a `traceroute`, or a `gcloud compute routers get-status` reading you can paste into your writeup.
- **Teardown is part of the grade.** `terraform destroy` clean, `gcloud compute routers list` empty.

## What "done" looks like

A short writeup (`RESULTS.md`) containing: the `terraform apply` summary, the three Connectivity Test results (intra-region, cross-region, and subnet→VIP), a `traceroute` to the private VIP showing one hop into Google's network, and a `gcloud compute routers get-status` excerpt showing the routes the Cloud Router knows. That artifact is the deliverable — the running infrastructure is torn down by the time anyone grades it.
