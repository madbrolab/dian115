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
	case "site-list":
		data, e = client.Sites(ctx)
	case "site-save":
		data, e = client.SaveSite(ctx, hostapi.HTTPSite{ID: pluginjson.Text(pluginjson.Field(input, "site_id")), URL: pluginjson.Text(pluginjson.Field(input, "url")), Label: pluginjson.Text(pluginjson.Field(input, "label"))}, key)
	case "site-delete":
		data, e = client.DeleteSite(ctx, pluginjson.Text(pluginjson.Field(input, "site_id")), key)
	case "cookie-save":
		data, e = client.SetCookieHeader(ctx, pluginjson.Text(pluginjson.Field(input, "url")), session, pluginjson.Text(pluginjson.Field(input, "cookie")), key)
	case "site-login":
		// The site adapter owns its login URL, field names and verification.
		// A challenge/CSRF value can be collected in an earlier GET action.
		fields := map[string]string{}
		for name, value := range pluginjson.Fields(pluginjson.Field(input, "fields")) {
			if len(value) == 0 || value[0] != '"' {
				return nil, errors.New("form fields must be strings")
			}
			fields[name] = pluginjson.Text(value)
		}
		for _, name := range []string{"username", "password"} {
			if value := pluginjson.Text(pluginjson.Field(input, name)); value != "" {
				fields[name] = value
			}
		}
		if len(fields) == 0 {
			return nil, errors.New("provide the site's form fields")
		}
		response, err := client.PostForm(ctx, hostapi.HTTPRequest{URL: pluginjson.Text(pluginjson.Field(input, "url")), Session: session, TimeoutMS: 30000}, fields)
		if err != nil {
			return nil, err
		}
		if response.Status >= 400 {
			return map[string]any{"status": "failed", "message": "登录接口返回 HTTP " + pluginjson.Number(response.Status) + "，请检查表单、验证码和站点业务结果", "httpStatus": response.Status, "verified": false}, nil
		}
		// Do not echo a login response or claim that 200 means authenticated.
		return map[string]any{"status": "succeeded", "message": "已提交登录表单；请按站点业务码核实登录状态", "httpStatus": response.Status, "verified": false}, nil
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
