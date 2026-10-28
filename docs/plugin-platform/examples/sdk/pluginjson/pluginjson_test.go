package pluginjson

import (
	"encoding/json"
	"math"
	"strings"
	"testing"
)

func TestJSONFieldsEscapesAndArrays(t *testing.T) {
	raw := Raw(` {"text":"a\/b\n\uD83D\uDE00","nested":{"values":[null,42,true]},"empty":{}} `)
	if !Valid(raw) || Text(Field(raw, "text")) != "a/b\n😀" || Int(Index(Field(Field(raw, "nested"), "values"), 1)) != 42 {
		t.Fatal("field access")
	}
	if len(Fields(raw)) != 3 || Field(raw, "missing") != nil || Index(Raw(`[]`), 0) != nil {
		t.Fatal("missing values")
	}
	for _, input := range []string{`{"a":1,}`, `{"a":1} trailing`, `[1,]`, `01`, `1.`, `"\uD800"`, `"\x00"`, `truefalse`, strings.Repeat("[", 66) + strings.Repeat("]", 66)} {
		if Valid(Raw(input)) {
			t.Fatalf("accepted %q", input)
		}
	}
}

func TestEncodeDeterministicAndBounded(t *testing.T) {
	value := map[string]any{"z": true, "a": []any{"hello\x00\n😀", Raw(`{"n":42}`), nil, int64(-2), 1.25}, "headers": map[string]string{"accept": "application/json"}}
	raw, err := Encode(value)
	if err != nil || !json.Valid(raw) || !strings.HasPrefix(string(raw), `{"a":`) {
		t.Fatal(string(raw), err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	for _, v := range []any{math.NaN(), Raw(`{"x":}`), make(chan int), strings.Repeat("x", MaxBytes+1)} {
		if _, err := Encode(v); err == nil {
			t.Fatal("unsupported value accepted")
		}
	}
}

func FuzzAccessNeverPanics(f *testing.F) {
	for _, seed := range []string{`{}`, `{"x":[1,{"a":"😀"}]}`, `[true,null]`, `"\/"`, `{"x":1,}`} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, s string) {
		if len(s) > 65536 {
			t.Skip()
		}
		raw := Raw(s)
		Field(raw, "x")
		Fields(raw)
		Index(raw, 2)
		Text(raw)
		Int(raw)
	})
}
