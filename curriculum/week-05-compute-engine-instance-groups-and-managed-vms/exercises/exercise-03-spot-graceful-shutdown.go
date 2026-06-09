// =============================================================================
// Exercise 3 — Spot VMs + graceful shutdown on preemption
// =============================================================================
//
// Goal: Turn the MIG's instances into spot VMs (60-91% cheaper) and make the
//       Go service survive preemption WITHOUT dropping in-flight requests.
//
// When Google reclaims a spot VM it sends an ACPI G2 Soft Off (which the OS
// sees as SIGTERM to PID 1 / your service) and flips the instance metadata
// key `instance/preempted` to "TRUE". You get ~30 seconds. The job in those
// 30 seconds is:
//
//   1. Immediately mark this instance UNHEALTHY so the load balancer and the
//      MIG stop sending it NEW connections.
//   2. Let in-flight requests finish (graceful HTTP shutdown with a deadline).
//   3. Flush anything that must be flushed (checkpoint, log, close DB conns).
//   4. Exit cleanly BEFORE the box is forcibly killed.
//
// Estimated time: 75 minutes.
//
// HOW TO USE THIS FILE
//
//   1. Save as main.go and run locally first to see the shutdown sequence:
//        go run main.go
//        # in another shell: curl localhost:8080/healthz   -> ok
//        # then: kill -TERM <pid>   (simulates the preemption SIGTERM)
//        # watch the log show: drain -> wait -> clean exit
//
//   2. Use this as the binary in your instance template (replace the
//      Lecture 2 main.go). Then apply the Terraform diff at the bottom of this
//      file to make the MIG's instances spot, and run the SIMULATE PREEMPTION
//      drill to prove zero dropped requests.
//
// ACCEPTANCE CRITERIA
//
//   [ ] The MIG's instances are spot (provisioning_model=SPACE confirmed via
//       gcloud), at the discounted price.
//   [ ] On SIGTERM the service flips /healthz to 503 IMMEDIATELY.
//   [ ] In-flight requests that arrived before SIGTERM still complete with 200.
//   [ ] The process exits within the drain deadline (well under 30s).
//   [ ] A `hey` load test running across a simulated preemption reports
//       Success rate: 100.00% (zero non-2xx, zero connection errors).
//   [ ] Teardown is clean.
// =============================================================================

package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"
)

// healthy is flipped to false the instant we receive the preemption signal.
// /healthz reads it; once false, the load balancer health check fails within
// a couple of poll intervals and stops sending new connections here.
var healthy atomic.Bool

// metadataPreemptedURL is the instance-metadata key that flips to "TRUE" when
// THIS spot VM is being preempted. Polling it is an alternative/confirmation
// to catching SIGTERM; we catch SIGTERM as the primary trigger because it is
// instant and works locally too.
const metadataPreemptedURL = "http://metadata.google.internal/computeMetadata/v1/instance/preempted"

// work simulates CPU-bound per-request work (same as the Lecture 2 service)
// so the load test and the autoscaling exercise drive real CPU.
func work(seed []byte, iterations int) string {
	buf := make([]byte, len(seed))
	copy(buf, seed)
	var sum [32]byte
	for i := 0; i < iterations; i++ {
		sum = sha256.Sum256(buf)
		copy(buf, sum[:])
	}
	return hex.EncodeToString(sum[:])
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	healthy.Store(true)

	mux := http.NewServeMux()

	// /healthz reflects readiness. Once we begin draining it returns 503 so
	// the LB/MIG health check marks us unhealthy and routes new traffic away.
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		if healthy.Load() {
			w.WriteHeader(http.StatusOK)
			io.WriteString(w, "ok\n")
			return
		}
		w.WriteHeader(http.StatusServiceUnavailable)
		io.WriteString(w, "draining\n")
	})

	// /work does the real (CPU-bound) work. A request already executing here
	// when SIGTERM arrives MUST be allowed to finish — that is the whole point.
	mux.HandleFunc("/work", func(w http.ResponseWriter, r *http.Request) {
		digest := work([]byte("crunch-gcp-week5"), 2000)
		fmt.Fprintf(w, "%s\n", digest)
	})

	srv := &http.Server{Addr: ":" + port, Handler: mux}

	// Run the server in the background.
	go func() {
		log.Printf("listening on :%s (healthy=%v)", port, healthy.Load())
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	// Watch for preemption from TWO sources:
	//   (a) SIGTERM  — what the ACPI G2 Soft Off looks like to the process.
	//   (b) the instance/preempted metadata key flipping to TRUE.
	// Whichever fires first triggers the drain. We treat them identically.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)

	preemptCh := make(chan struct{}, 1)
	go pollPreemptionMetadata(preemptCh)

	select {
	case s := <-sigCh:
		log.Printf("received signal %v: beginning graceful drain", s)
	case <-preemptCh:
		log.Printf("instance/preempted=TRUE: beginning graceful drain")
	}

	drain(srv)
	log.Printf("clean exit")
}

// drain is the 30-second-budget shutdown sequence.
func drain(srv *http.Server) {
	// Step 1: stop advertising readiness IMMEDIATELY. New traffic stops
	// arriving once the health check notices (a couple of poll intervals).
	healthy.Store(false)
	log.Printf("step 1: marked unhealthy; /healthz now returns 503")

	// Step 2: brief grace so the LB/MIG health check actually observes the
	// 503 and stops routing new connections to us before we close the
	// listener. Without this pause you can close mid-flight on connections
	// the LB was still sending. Keep it short — it eats into the 30s budget.
	const healthCheckGrace = 3 * time.Second
	log.Printf("step 2: waiting %s for health check to deregister us", healthCheckGrace)
	time.Sleep(healthCheckGrace)

	// Step 3: graceful HTTP shutdown. srv.Shutdown stops accepting new
	// connections and BLOCKS until in-flight requests finish or the deadline
	// hits. Budget well under the ~30s preemption window.
	const drainDeadline = 20 * time.Second
	ctx, cancel := context.WithTimeout(context.Background(), drainDeadline)
	defer cancel()

	log.Printf("step 3: draining in-flight requests (deadline %s)", drainDeadline)
	if err := srv.Shutdown(ctx); err != nil {
		// Deadline exceeded: some request took too long. In production you'd
		// emit a metric here so you can tune drainDeadline or your handlers.
		log.Printf("drain exceeded deadline: %v (forcing close)", err)
		_ = srv.Close()
		return
	}
	log.Printf("step 3: all in-flight requests completed cleanly")

	// Step 4: flush whatever must be flushed before the box dies. For a
	// stateless service this is logs/metrics; for a batch worker this is the
	// final checkpoint to GCS. (Nothing to flush here; the hook is the point.)
	log.Printf("step 4: final flush complete")
}

// pollPreemptionMetadata polls the instance metadata server for the preemption
// flag. On a real spot VM this flips to "TRUE" at preemption time. Off-GCP
// (local dev) the metadata server is unreachable and this simply never fires,
// which is fine — SIGTERM is the primary trigger.
func pollPreemptionMetadata(out chan<- struct{}) {
	client := &http.Client{Timeout: 2 * time.Second}
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		req, err := http.NewRequest(http.MethodGet, metadataPreemptedURL, nil)
		if err != nil {
			return
		}
		req.Header.Set("Metadata-Flavor", "Google")
		resp, err := client.Do(req)
		if err != nil {
			// Not on GCP, or metadata server unreachable: stop polling quietly.
			return
		}
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		if string(body) == "TRUE" {
			select {
			case out <- struct{}{}:
			default:
			}
			return
		}
	}
}

// =============================================================================
// TERRAFORM DIFF — make the MIG's instances SPOT
// =============================================================================
//
// In the instance template from Exercise 1, ADD a scheduling block. Because
// the template is immutable (name_prefix + create_before_destroy), applying
// this creates a NEW template and the MIG's update_policy rolls onto it.
//
//   resource "google_compute_instance_template" "workserver" {
//     # ... everything from Exercise 1 ...
//
//     scheduling {
//       provisioning_model          = "SPOT"   # the spot pricing model
//       preemptible                 = true      # legacy flag; set with SPOT
//       automatic_restart           = false     # spot VMs can't auto-restart
//       on_host_maintenance         = "TERMINATE"
//       instance_termination_action = "STOP"    # STOP (reclaimable) vs DELETE
//     }
//   }
//
// Notes:
//   - provisioning_model = "SPOT" is the modern spot model (no fixed max
//     runtime, deeper discount than the legacy preemptible 24h-cap model).
//   - automatic_restart MUST be false and on_host_maintenance MUST be
//     "TERMINATE" for spot — the provider will reject other combinations.
//   - instance_termination_action: "STOP" stops the VM (the MIG recreates it);
//     "DELETE" deletes it. For a MIG, "STOP" is fine — the MIG replaces it
//     either way to maintain target size.
//   - The MIG's update_policy (max_surge=3, max_unavailable=0 from Exercise 2)
//     makes the roll onto the spot template zero-drop, exactly like any other
//     template change.
//
// =============================================================================
// SIMULATE PREEMPTION — prove zero dropped requests
// =============================================================================
//
// You cannot reliably force Google to preempt your VM on demand, but you CAN
// simulate the exact signal it sends and verify your handler:
//
//   1. Start a steady load against the MIG (via the LB VIP in the mini-project,
//      or one instance here) from the in-VPC load generator:
//
//        ~/go/bin/hey -z 90s -c 50 http://<TARGET>:8080/work
//
//   2. ~30s in, SSH to one MIG instance and simulate preemption by sending the
//      same signal Google sends (SIGTERM to the service):
//
//        gcloud compute ssh <instance> --zone=<zone> --tunnel-through-iap \
//          --command="sudo systemctl kill -s SIGTERM workserver.service"
//
//      (Or, to test the real reclaim path end to end, use:
//        gcloud compute instances simulate-maintenance-event <instance> --zone=<zone>
//       for the maintenance signal; the spot preemption signal is delivered the
//       same way to your process.)
//
//   3. Watch the service log on that instance:
//        gcloud compute ssh <instance> --zone=<zone> --tunnel-through-iap \
//          --command="sudo journalctl -u workserver.service -f"
//
//      You should see the four-step drain sequence, then "clean exit".
//      The MIG then recreates the instance (autohealing/target-size).
//
//   4. When `hey` finishes, confirm:
//
//        Summary:
//          Total:        90.0012 secs
//          Requests:     224,931
//          Success rate: 100.00%
//        Status code distribution:
//          [200] 224931 responses
//
//      ZERO non-2xx and ZERO connection errors across the preemption. That is
//      the "zero dropped requests" promise for this week. If you see even one
//      non-2xx, your healthCheckGrace was too short (you closed the listener
//      before the LB stopped routing to you) or your drainDeadline was too
//      short (a request was cut off). Tune and re-run.
//
// =============================================================================
// TEARDOWN
// =============================================================================
//
//   gcloud compute instances delete week5-loadgen --zone=<zone> --quiet
//   terraform destroy -var="project_id=$(gcloud config get-value project)" -auto-approve
//   gcloud compute instances list   # expect: Listed 0 items.
//
// =============================================================================
// WHY THE ORDER MATTERS (the subtle part)
// =============================================================================
//
//   The single most common mistake is closing the HTTP listener BEFORE the
//   load balancer has stopped routing to the instance. If you call
//   srv.Shutdown() the instant SIGTERM arrives, the LB is still sending new
//   connections (it hasn't run a health check yet) and those connections hit a
//   closed listener -> connection refused -> a non-2xx in someone's browser.
//
//   The correct order is ALWAYS:
//     (1) fail the health check,
//     (2) wait for the LB to observe it and deregister you,
//     (3) THEN drain in-flight and close.
//
//   This is "fail readiness, then drain" and it is identical to the Kubernetes
//   preStop-sleep-then-SIGTERM pattern. The 30-second spot budget is generous
//   for it; a 3s grace + 20s drain leaves margin. Internalize this order — it
//   is the difference between "spot saved us 70%" and "spot dropped a
//   customer's checkout."
