// Package pluginjson provides bounded JSON field access and deterministic
// encoding for small WASM plugins. Raw values borrow the input: copy them if
// they must survive reuse of that input buffer. It does not use encoding/json.
package pluginjson

import (
	"errors"
	"math"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
)

type Raw []byte

const MaxBytes = 16 << 20
const maxDepth = 64

var errJSON = errors.New("invalid, unsupported or excessive JSON value")

type parser struct {
	raw Raw
	pos int
}

func (p *parser) space() {
	for p.pos < len(p.raw) && strings.ContainsRune(" \t\r\n", rune(p.raw[p.pos])) {
		p.pos++
	}
}
func (p *parser) stringValue() (string, bool) {
	if p.pos >= len(p.raw) || p.raw[p.pos] != '"' {
		return "", false
	}
	p.pos++
	var out []byte
	for p.pos < len(p.raw) {
		c := p.raw[p.pos]
		p.pos++
		if c == '"' {
			return string(out), utf8.Valid(out)
		}
		if c < 0x20 {
			return "", false
		}
		if c != '\\' {
			out = append(out, c)
			continue
		}
		if p.pos >= len(p.raw) {
			return "", false
		}
		c = p.raw[p.pos]
		p.pos++
		switch c {
		case '"', '\\', '/':
			out = append(out, c)
		case 'b':
			out = append(out, '\b')
		case 'f':
			out = append(out, '\f')
		case 'n':
			out = append(out, '\n')
		case 'r':
			out = append(out, '\r')
		case 't':
			out = append(out, '\t')
		case 'u':
			r, ok := p.hexRune()
			if !ok {
				return "", false
			}
			if r >= 0xd800 && r <= 0xdbff {
				if p.pos+2 > len(p.raw) || string(p.raw[p.pos:p.pos+2]) != `\u` {
					return "", false
				}
				p.pos += 2
				low, ok := p.hexRune()
				if !ok || low < 0xdc00 || low > 0xdfff {
					return "", false
				}
				r = utf16.DecodeRune(r, low)
			} else if r >= 0xdc00 && r <= 0xdfff {
				return "", false
			}
			out = utf8.AppendRune(out, r)
		default:
			return "", false
		}
	}
	return "", false
}
func (p *parser) hexRune() (rune, bool) {
	if p.pos+4 > len(p.raw) {
		return 0, false
	}
	value, err := strconv.ParseUint(string(p.raw[p.pos:p.pos+4]), 16, 16)
	p.pos += 4
	return rune(value), err == nil
}
func (p *parser) value(depth int) bool {
	if depth > maxDepth {
		return false
	}
	p.space()
	if p.pos >= len(p.raw) {
		return false
	}
	switch p.raw[p.pos] {
	case '"':
		_, ok := p.stringValue()
		return ok
	case '{', '[':
		object := p.raw[p.pos] == '{'
		end := byte(']')
		if object {
			end = '}'
		}
		p.pos++
		p.space()
		if p.pos < len(p.raw) && p.raw[p.pos] == end {
			p.pos++
			return true
		}
		for {
			if object {
				p.space()
				if _, ok := p.stringValue(); !ok {
					return false
				}
				p.space()
				if p.pos >= len(p.raw) || p.raw[p.pos] != ':' {
					return false
				}
				p.pos++
			}
			if !p.value(depth + 1) {
				return false
			}
			p.space()
			if p.pos >= len(p.raw) {
				return false
			}
			c := p.raw[p.pos]
			p.pos++
			if c == end {
				return true
			}
			if c != ',' {
				return false
			}
		}
	case 't', 'f', 'n':
		for _, word := range []string{"true", "false", "null"} {
			if strings.HasPrefix(string(p.raw[p.pos:]), word) {
				p.pos += len(word)
				return true
			}
		}
		return false
	default:
		start := p.pos
		if p.raw[p.pos] == '-' {
			p.pos++
		}
		if p.pos >= len(p.raw) {
			return false
		}
		if p.raw[p.pos] == '0' {
			p.pos++
		} else {
			if p.raw[p.pos] < '1' || p.raw[p.pos] > '9' {
				return false
			}
			for p.pos < len(p.raw) && p.raw[p.pos] >= '0' && p.raw[p.pos] <= '9' {
				p.pos++
			}
		}
		if p.pos < len(p.raw) && p.raw[p.pos] == '.' {
			p.pos++
			begin := p.pos
			for p.pos < len(p.raw) && p.raw[p.pos] >= '0' && p.raw[p.pos] <= '9' {
				p.pos++
			}
			if begin == p.pos {
				return false
			}
		}
		if p.pos < len(p.raw) && (p.raw[p.pos] == 'e' || p.raw[p.pos] == 'E') {
			p.pos++
			if p.pos < len(p.raw) && (p.raw[p.pos] == '+' || p.raw[p.pos] == '-') {
				p.pos++
			}
			begin := p.pos
			for p.pos < len(p.raw) && p.raw[p.pos] >= '0' && p.raw[p.pos] <= '9' {
				p.pos++
			}
			if begin == p.pos {
				return false
			}
		}
		return p.pos > start
	}
}

func Valid(raw Raw) bool {
	if len(raw) == 0 || len(raw) > MaxBytes {
		return false
	}
	p := parser{raw: raw}
	if !p.value(0) {
		return false
	}
	p.space()
	return p.pos == len(raw)
}

func Field(raw Raw, name string) Raw {
	// Scan without decoding complete documents or allocating a field map.
	if len(raw) == 0 || len(raw) > MaxBytes {
		return nil
	}
	p := parser{raw: raw}
	p.space()
	if p.pos >= len(raw) || raw[p.pos] != '{' {
		return nil
	}
	p.pos++
	var result Raw
	for {
		p.space()
		if p.pos >= len(raw) {
			return nil
		}
		if raw[p.pos] == '}' {
			p.pos++
			p.space()
			if p.pos != len(raw) {
				return nil
			}
			return result
		}
		key, ok := p.stringValue()
		if !ok {
			return nil
		}
		p.space()
		if p.pos >= len(raw) || raw[p.pos] != ':' {
			return nil
		}
		p.pos++
		p.space()
		start := p.pos
		if !p.value(1) {
			return nil
		}
		if key == name {
			result = raw[start:p.pos]
		}
		p.space()
		if p.pos >= len(raw) {
			return nil
		}
		if raw[p.pos] == '}' {
			continue
		}
		if raw[p.pos] != ',' {
			return nil
		}
		p.pos++
		p.space()
		if p.pos >= len(raw) || raw[p.pos] == '}' {
			return nil
		}
	}
}

func Fields(raw Raw) map[string]Raw {
	if !Valid(raw) {
		return nil
	}
	p := parser{raw: raw}
	p.space()
	if raw[p.pos] != '{' {
		return nil
	}
	p.pos++
	fields := make(map[string]Raw)
	for {
		p.space()
		if raw[p.pos] == '}' {
			return fields
		}
		key, _ := p.stringValue()
		p.space()
		p.pos++
		p.space()
		start := p.pos
		p.value(1)
		fields[key] = raw[start:p.pos]
		p.space()
		if raw[p.pos] == ',' {
			p.pos++
		}
	}
}

func Index(raw Raw, index int) Raw {
	if index < 0 || !Valid(raw) {
		return nil
	}
	p := parser{raw: raw}
	p.space()
	if raw[p.pos] != '[' {
		return nil
	}
	p.pos++
	for n := 0; ; n++ {
		p.space()
		if raw[p.pos] == ']' {
			return nil
		}
		start := p.pos
		p.value(1)
		if n == index {
			return raw[start:p.pos]
		}
		p.space()
		if raw[p.pos] == ',' {
			p.pos++
		}
	}
}
func Text(raw Raw) string {
	if len(raw) > MaxBytes {
		return ""
	}
	p := parser{raw: raw}
	p.space()
	text, ok := p.stringValue()
	p.space()
	if !ok || p.pos != len(raw) {
		return ""
	}
	return text
}
func Int(raw Raw) int     { n, _ := strconv.Atoi(strings.TrimSpace(string(raw))); return n }
func Number(n int) string { return strconv.Itoa(n) }

// Encode supports explicit JSON values, never reflection or arbitrary structs.
// Raw is embedded after validation; []byte is deliberately not a JSON string.
func Encode(value any) (Raw, error) {
	raw, err := appendValue(nil, value, 0)
	if len(raw) > MaxBytes {
		return nil, errJSON
	}
	return raw, err
}
func appendString(out []byte, value string) []byte {
	out = append(out, '"')
	for _, r := range value {
		if len(out) > MaxBytes {
			return out
		}
		switch r {
		case '"', '\\':
			out = append(out, '\\', byte(r))
		case '\n':
			out = append(out, '\\', 'n')
		case '\r':
			out = append(out, '\\', 'r')
		case '\t':
			out = append(out, '\\', 't')
		default:
			if r < 0x20 {
				out = append(out, '\\', 'u', '0', '0', "0123456789abcdef"[r>>4], "0123456789abcdef"[r&15])
			} else {
				out = utf8.AppendRune(out, r)
			}
		}
	}
	return append(out, '"')
}
func appendValue(out []byte, value any, depth int) ([]byte, error) {
	if depth > maxDepth || len(out) > MaxBytes {
		return nil, errJSON
	}
	switch v := value.(type) {
	case nil:
		return append(out, "null"...), nil
	case Raw:
		if !Valid(v) {
			return nil, errJSON
		}
		return append(out, v...), nil
	case string:
		if len(v) > MaxBytes {
			return nil, errJSON
		}
		return appendString(out, v), nil
	case bool:
		return strconv.AppendBool(out, v), nil
	case int:
		return strconv.AppendInt(out, int64(v), 10), nil
	case int32:
		return strconv.AppendInt(out, int64(v), 10), nil
	case int64:
		return strconv.AppendInt(out, v, 10), nil
	case uint32:
		return strconv.AppendUint(out, uint64(v), 10), nil
	case uint64:
		return strconv.AppendUint(out, v, 10), nil
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return nil, errJSON
		}
		return strconv.AppendFloat(out, v, 'g', -1, 64), nil
	case map[string]any:
		keys := make([]string, 0, len(v))
		for key := range v {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		out = append(out, '{')
		for i, key := range keys {
			if i > 0 {
				out = append(out, ',')
			}
			out = appendString(out, key)
			out = append(out, ':')
			var err error
			out, err = appendValue(out, v[key], depth+1)
			if err != nil {
				return nil, err
			}
		}
		return append(out, '}'), nil
	case map[string]string:
		values := make(map[string]any, len(v))
		for key, item := range v {
			values[key] = item
		}
		return appendValue(out, values, depth)
	case []any:
		out = append(out, '[')
		for i, item := range v {
			if i > 0 {
				out = append(out, ',')
			}
			var err error
			out, err = appendValue(out, item, depth+1)
			if err != nil {
				return nil, err
			}
		}
		return append(out, ']'), nil
	case []string:
		out = append(out, '[')
		for i, item := range v {
			if i > 0 {
				out = append(out, ',')
			}
			out = appendString(out, item)
			if len(out) > MaxBytes {
				return nil, errJSON
			}
		}
		return append(out, ']'), nil
	default:
		return nil, errJSON
	}
}
