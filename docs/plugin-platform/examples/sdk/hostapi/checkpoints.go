package hostapi

import (
	"context"
	"errors"
	"strconv"
	"strings"

	"example.com/dian115-plugin-sdk/pluginjson"
)

type JobContext struct {
	Ref, InvocationID string
	Attempt           int
	Verifying         bool
	Checkpoint        pluginjson.Raw
}

// CurrentJob is null for short actions, cron delivery and ordinary events.
// Only a host-owned recoverable background run receives checkpoint authority.
func (c Client) CurrentJob(ctx context.Context) (*JobContext, error) {
	if c.Call == nil {
		return nil, errors.New("invalid job client")
	}
	raw, err := c.Call(ctx, "host.job.current", map[string]any{})
	if err != nil {
		return nil, err
	}
	if !pluginjson.Valid(raw) {
		return nil, errors.New("invalid current job response")
	}
	job := pluginjson.Field(raw, "job")
	if string(job) == "null" {
		return nil, nil
	}
	if !pluginjson.Valid(job) || len(job) == 0 || job[0] != '{' {
		return nil, errors.New("invalid current job response")
	}
	value := &JobContext{Ref: pluginjson.Text(pluginjson.Field(job, "job_ref")), InvocationID: pluginjson.Text(pluginjson.Field(job, "invocation_id")), Checkpoint: pluginjson.Field(job, "checkpoint")}
	attempt, err := strconv.ParseInt(string(pluginjson.Field(job, "attempt")), 10, 32)
	if err != nil || attempt < 0 || attempt > 3 || !validJobRef(value.Ref) || !strings.HasPrefix(value.InvocationID, "inv_") || len(value.InvocationID) > 80 || !ValidStorageKey(value.InvocationID) || !pluginjson.Valid(value.Checkpoint) || len(value.Checkpoint) > 64<<10 {
		return nil, errors.New("invalid current job fields")
	}
	flag := string(pluginjson.Field(job, "verifying"))
	if flag != "true" && flag != "false" {
		return nil, errors.New("invalid job verification flag")
	}
	value.Attempt = int(attempt)
	value.Verifying = flag == "true"
	return value, nil
}

// SaveCheckpoint commits one <=64 KiB JSON checkpoint and progress together.
// Stable business idempotency keys remain necessary for external effects.
func (c Client) SaveCheckpoint(ctx context.Context, checkpoint pluginjson.Raw, progress int) error {
	if c.Call == nil || progress < 0 || progress > 100 || !pluginjson.Valid(checkpoint) || len(checkpoint) > 64<<10 {
		return errors.New("invalid checkpoint")
	}
	raw, err := c.Call(ctx, "host.job.checkpoint", map[string]any{"checkpoint": checkpoint, "progress": progress})
	if err != nil {
		return err
	}
	if !pluginjson.Valid(raw) || string(pluginjson.Field(raw, "saved")) != "true" {
		return errors.New("checkpoint was not committed")
	}
	return nil
}
