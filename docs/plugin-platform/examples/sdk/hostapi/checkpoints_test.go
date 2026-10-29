package hostapi

import (
	"context"
	"strings"
	"testing"

	"example.com/dian115-plugin-sdk/pluginjson"
)

func TestCurrentJobAndCheckpointUseOneHostCall(t *testing.T) {
	calls := 0
	c := Client{Call: func(_ context.Context, method string, params any) (pluginjson.Raw, error) {
		calls++
		if method == "host.job.current" {
			return pluginjson.Raw(`{"job":{"job_ref":"job_123","invocation_id":"inv_business","attempt":1,"checkpoint":{"cursor":5},"verifying":true}}`), nil
		}
		if method != "host.job.checkpoint" {
			t.Fatal(method)
		}
		value := params.(map[string]any)
		if value["progress"] != 50 || string(value["checkpoint"].(pluginjson.Raw)) != `{"cursor":6}` {
			t.Fatal(value)
		}
		return pluginjson.Raw(`{"saved":true}`), nil
	}}
	current, err := c.CurrentJob(context.Background())
	if err != nil || current == nil || current.Ref != "job_123" || current.Attempt != 1 || !current.Verifying {
		t.Fatal(current, err)
	}
	if err := c.SaveCheckpoint(context.Background(), pluginjson.Raw(`{"cursor":6}`), 50); err != nil {
		t.Fatal(err)
	}
	if calls != 2 {
		t.Fatal("checkpoint helper retried or polled", calls)
	}
	if c.SaveCheckpoint(context.Background(), pluginjson.Raw(`{}`), 101) == nil || c.SaveCheckpoint(context.Background(), pluginjson.Raw(`"`+strings.Repeat("x", 64<<10)+`"`), 1) == nil {
		t.Fatal("unbounded checkpoint accepted")
	}
	if calls != 2 {
		t.Fatal("invalid checkpoint reached host")
	}
}

func TestCurrentJobRejectsMalformedAuthority(t *testing.T) {
	for _, body := range []string{`{}`, `{"job":null} trailing`, `{"job":{}}`, `{"job":{"job_ref":"job_x","invocation_id":"inv_y","attempt":4,"checkpoint":null,"verifying":false}}`} {
		c := Client{Call: func(context.Context, string, any) (pluginjson.Raw, error) { return pluginjson.Raw(body), nil }}
		if _, err := c.CurrentJob(context.Background()); err == nil {
			t.Fatal("malformed scope accepted", body)
		}
	}
	c := Client{Call: func(context.Context, string, any) (pluginjson.Raw, error) { return pluginjson.Raw(`{"job":null}`), nil }}
	if current, err := c.CurrentJob(context.Background()); err != nil || current != nil {
		t.Fatal(current, err)
	}
	c.Call = func(context.Context, string, any) (pluginjson.Raw, error) {
		return pluginjson.Raw(`{"saved":false}`), nil
	}
	if c.SaveCheckpoint(context.Background(), pluginjson.Raw(`null`), 0) == nil {
		t.Fatal("uncommitted checkpoint accepted")
	}
	c.Call = func(context.Context, string, any) (pluginjson.Raw, error) {
		return pluginjson.Raw(`{"saved":true} trailing`), nil
	}
	if c.SaveCheckpoint(context.Background(), pluginjson.Raw(`null`), 0) == nil {
		t.Fatal("malformed checkpoint acknowledgement accepted")
	}
}
