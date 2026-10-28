package main

import (
	"context"
	"errors"
	"time"

	"example.com/dian115-plugin-sdk/hostapi"
	"example.com/dian115-plugin-sdk/pluginjson"
)

// These actions run only after an explicit user request. Neither initialize,
// state nor wake-up imports credentials or writes the shared CookieCloud.
func (r *runtime) httpSessionAction(action, invocationID string, input pluginjson.Raw) (any, error) {
	client := hostapi.Client{Call: r.peer.call}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	session := pluginjson.Text(pluginjson.Field(input, "session"))
	if session == "" {
		session = "account-a"
	}
	key, e := hostapi.Key("http-session", invocationID)
	if e != nil {
		return nil, e
	}
	var data pluginjson.Raw
	switch action {
	case "cookiecloud-info":
		data, e = client.CookieCloud(ctx)
	case "cookiecloud-import", "cookiecloud-export":
		domain := pluginjson.Text(pluginjson.Field(input, "domain"))
		if domain == "" {
			return nil, errors.New("select a CookieCloud domain")
		}
		if action == "cookiecloud-import" {
			data, e = client.ImportCookieCloud(ctx, session, []string{domain}, key)
		} else {
			// The UI must read and persist the revision BEFORE the explicit export
			// attempt. A conflict is surfaced, never overwritten automatically.
			revision := pluginjson.Text(pluginjson.Field(input, "revision"))
			data, e = client.ExportCookieCloud(ctx, session, []string{domain}, revision, key)
		}
	case "cookies-clear":
		data, e = client.ClearCookies(ctx, session, key)
	case "http-render":
		target := pluginjson.Text(pluginjson.Field(input, "url"))
		data, e = client.RenderPage(ctx, target, session, 3, key)
		if e == nil {
			return map[string]any{"status": "succeeded", "message": "按需渲染完成，请继续核实站点业务结果", "htmlBytes": len(pluginjson.Text(pluginjson.Field(data, "html"))), "httpStatusVerified": false}, nil
		}
	default:
		return nil, errors.New("unknown HTTP session example")
	}
	if e != nil {
		return map[string]any{"status": "failed", "message": e.Error()}, nil
	}
	// Metadata/counters only: never copy raw cookies into page state or logs.
	return map[string]any{"status": "succeeded", "message": "会话操作完成", "data": data}, nil
}
