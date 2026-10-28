package hostapi

import (
	"context"
	"errors"
	"strconv"
	"strings"

	"example.com/dian115-plugin-sdk/pluginjson"
)

type JobStatus string

const (
	JobQueued            JobStatus = "queued"
	JobRunning           JobStatus = "running"
	JobSucceeded         JobStatus = "succeeded"
	JobFailed            JobStatus = "failed"
	JobCancelled         JobStatus = "cancelled"
	JobAttentionRequired JobStatus = "attention_required"
)

type JobFailure struct{ Code, Detail, DiagnosticID string }
type Job struct {
	Ref, Kind                               string
	Status                                  JobStatus
	Progress                                int
	Cancellable, CancelRequested, Retryable bool
	RecoverySupported, RecoveryPending      bool
	RecoveryAttempt                         int
	Result                                  pluginjson.Raw
	Failure                                 JobFailure
}

// Terminal describes the current run, including uncertain results. A recovery
// record can still own future work; use CanCancel when offering cancellation.
// An accepted child job still requires querying its separate reference.
func (j Job) Terminal() bool {
	switch j.Status {
	case JobSucceeded, JobFailed, JobCancelled, JobAttentionRequired:
		return true
	}
	return false
}

func (j Job) CanCancel() bool {
	if !j.Cancellable || j.CancelRequested {
		return false
	}
	return j.Status == JobQueued || j.Status == JobRunning || (j.RecoverySupported && (j.Status == JobFailed || j.Status == JobAttentionRequired))
}

func validJobRef(ref string) bool {
	if !strings.HasPrefix(ref, "job_") || len(ref) <= 4 || len(ref) > 80 {
		return false
	}
	for _, c := range ref[4:] {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9') {
			return false
		}
	}
	return true
}

// JobGet performs exactly one query. Callers choose a bounded refresh cadence;
// the SDK starts no goroutine, timer, retry loop or blocking wait.
func (c Client) JobGet(ctx context.Context, ref string) (Job, error) {
	if !validJobRef(ref) {
		return Job{}, errors.New("invalid job reference")
	}
	data, err := c.readData(ctx, "/api/plugin-host/jobs/"+ref)
	if err != nil {
		return Job{}, err
	}
	job := Job{Ref: pluginjson.Text(pluginjson.Field(data, "job_ref")), Kind: pluginjson.Text(pluginjson.Field(data, "kind")), Status: JobStatus(pluginjson.Text(pluginjson.Field(data, "status"))), Result: pluginjson.Field(data, "result")}
	n, err := strconv.ParseInt(strings.TrimSpace(string(pluginjson.Field(data, "progress"))), 10, 32)
	if err != nil || n < 0 || n > 100 || job.Ref != ref || job.Kind == "" {
		return Job{}, errors.New("invalid job response")
	}
	job.Progress = int(n)
	switch job.Status {
	case JobQueued, JobRunning, JobSucceeded, JobFailed, JobCancelled, JobAttentionRequired:
	default:
		return Job{}, errors.New("unknown job status")
	}
	for key, target := range map[string]*bool{"cancellable": &job.Cancellable, "cancel_requested": &job.CancelRequested, "retryable": &job.Retryable, "recovery_supported": &job.RecoverySupported, "recovery_pending": &job.RecoveryPending} {
		raw := pluginjson.Field(data, key)
		if len(raw) == 0 && key != "cancellable" {
			continue
		}
		switch string(raw) {
		case "true":
			*target = true
		case "false":
		default:
			return Job{}, errors.New("invalid job flags")
		}
	}
	if field := pluginjson.Field(data, "recovery_attempt"); len(field) > 0 {
		n, err := strconv.ParseInt(string(field), 10, 32)
		if err != nil || n < 0 || n > 3 {
			return Job{}, errors.New("invalid recovery attempt")
		}
		job.RecoveryAttempt = int(n)
	}
	failure := pluginjson.Field(data, "error")
	if len(failure) > 0 && string(failure) != "null" {
		if failure[0] != '{' {
			return Job{}, errors.New("invalid job failure")
		}
		job.Failure = JobFailure{Code: pluginjson.Text(pluginjson.Field(failure, "code")), Detail: pluginjson.Text(pluginjson.Field(failure, "detail")), DiagnosticID: pluginjson.Text(pluginjson.Field(failure, "diagnostic_id"))}
	}
	if (job.Status == JobFailed || job.Status == JobAttentionRequired) && job.Failure.Code == "" {
		return Job{}, errors.New("job failure code is missing")
	}
	return job, nil
}

// JobCancel acknowledges only the cancellation request, not rollback or a
// terminal result. Reuse the idempotency key for the same cancellation attempt.
func (c Client) JobCancel(ctx context.Context, ref, idempotencyKey string) error {
	if c.Call == nil || !validJobRef(ref) || !validIdempotencyKey(idempotencyKey) {
		return errors.New("invalid job cancellation request")
	}
	raw, err := c.Call(ctx, "host.call", map[string]any{"method": "POST", "path": "/api/plugin-host/jobs/" + ref + "/cancel", "headers": map[string]string{"accept": "application/json", "idempotency-key": idempotencyKey}})
	if err != nil {
		return err
	}
	data, err := responseData(raw)
	if err != nil {
		return err
	}
	if pluginjson.Int(pluginjson.Field(raw, "status")) != 202 || pluginjson.Text(pluginjson.Field(data, "job_ref")) != ref || pluginjson.Text(pluginjson.Field(data, "status")) != "cancellation_requested" {
		return errors.New("invalid job cancellation acknowledgement")
	}
	return nil
}
