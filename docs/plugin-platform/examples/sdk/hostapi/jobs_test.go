package hostapi

import (
	"context"
	"encoding/base64"
	"errors"
	"strings"
	"testing"

	"example.com/dian115-plugin-sdk/pluginjson"
)

func jobHostResponse(status int, body string) pluginjson.Raw {
	raw, _ := pluginjson.Encode(map[string]any{"status": status, "body_base64": base64.RawStdEncoding.EncodeToString([]byte(body))})
	return raw
}

func TestJobQueryKeepsUncertainFailureAndDiagnostic(t *testing.T) {
	calls := 0
	client := Client{Call: func(_ context.Context, method string, params any) (pluginjson.Raw, error) {
		calls++
		req := params.(map[string]any)
		if method != "host.call" || req["method"] != "GET" || req["path"] != "/api/plugin-host/jobs/job_abc123" {
			t.Fatal(req)
		}
		return jobHostResponse(200, `{"data":{"job_ref":"job_abc123","kind":"transfer.115.offline_download","status":"attention_required","progress":50,"cancellable":true,"retryable":false,"error":{"code":"submission_uncertain","detail":"verify upstream","diagnostic_id":"diag_example"}}}`), nil
	}}
	job, err := client.JobGet(context.Background(), "job_abc123")
	if err != nil || !job.Terminal() || job.Status != JobAttentionRequired || job.Retryable || job.Failure.Code != "submission_uncertain" || job.Failure.DiagnosticID != "diag_example" {
		t.Fatal(job, err)
	}
	if calls != 1 {
		t.Fatal("query started hidden polling", calls)
	}
	if (Job{Status: JobRunning}).Terminal() {
		t.Fatal("running job considered complete")
	}
}

func TestJobCancellationIncludesRecoveryIntent(t *testing.T) {
	for _, status := range []JobStatus{JobQueued, JobRunning, JobFailed, JobAttentionRequired, JobSucceeded, JobCancelled} {
		for _, recovery := range []bool{false, true} {
			job := Job{Status: status, Cancellable: true, RecoverySupported: recovery}
			want := status == JobQueued || status == JobRunning || (recovery && (status == JobFailed || status == JobAttentionRequired))
			if job.CanCancel() != want {
				t.Fatal(status, recovery)
			}
			job.CancelRequested = true
			if job.CanCancel() {
				t.Fatal("duplicate cancellation offered")
			}
			job.CancelRequested, job.Cancellable = false, false
			if job.CanCancel() {
				t.Fatal("uncancellable job offered")
			}
		}
	}
}

func TestJobQueryRejectsMalformedAndCrossReferenceResults(t *testing.T) {
	valid := `{"data":{"job_ref":"job_abc123","kind":"test","status":"running","progress":1,"cancellable":true}}`
	for _, body := range []string{`{}`, strings.Replace(valid, "job_abc123", "job_other", 1), strings.Replace(valid, "running", "unknown", 1), strings.Replace(valid, `"progress":1`, `"progress":101`, 1), strings.Replace(valid, `"cancellable":true`, `"cancellable":null`, 1), strings.Replace(valid, "running", "failed", 1)} {
		client := Client{Call: func(context.Context, string, any) (pluginjson.Raw, error) { return jobHostResponse(200, body), nil }}
		if _, err := client.JobGet(context.Background(), "job_abc123"); err == nil {
			t.Fatal("malformed job accepted", body)
		}
	}
}

func TestJobCancellationChecksAcknowledgementAndNeverRetries(t *testing.T) {
	calls := 0
	status, body := 202, `{"data":{"job_ref":"job_abc123","status":"cancellation_requested"}}`
	client := Client{Call: func(_ context.Context, _ string, params any) (pluginjson.Raw, error) {
		calls++
		req := params.(map[string]any)
		if req["method"] != "POST" || req["path"] != "/api/plugin-host/jobs/job_abc123/cancel" || req["headers"].(map[string]string)["idempotency-key"] != "cancel-job-abc12345" {
			t.Fatal(req)
		}
		return jobHostResponse(status, body), nil
	}}
	if err := client.JobCancel(context.Background(), "job_abc123", "cancel-job-abc12345"); err != nil {
		t.Fatal(err)
	}
	status, body = 503, `{"code":"temporarily_unavailable","detail":"try later","retryable":true,"diagnostic_id":"diag_problem"}`
	var problem *Problem
	if err := client.JobCancel(context.Background(), "job_abc123", "cancel-job-abc12345"); !errors.As(err, &problem) || !problem.Retryable || problem.DiagnosticID != "diag_problem" || calls != 2 {
		t.Fatal("HTTP failure lost or retried", err, calls)
	}
	status, body = 202, `{"data":{"job_ref":"job_other","status":"cancellation_requested"}}`
	if err := client.JobCancel(context.Background(), "job_abc123", "cancel-job-abc12345"); err == nil {
		t.Fatal("wrong-reference acknowledgement accepted")
	}
	for _, ref := range []string{"job_abc123/cancel", "job_x?override=1", "", "../../jobs/other"} {
		if err := client.JobCancel(context.Background(), ref, "cancel-job-abc12345"); err == nil {
			t.Fatal("unsafe reference accepted", ref)
		}
	}
	if calls != 3 {
		t.Fatal("invalid arguments reached host", calls)
	}
}
