package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"dian115/internal/model"
	"dian115/internal/store"
)

func main() {
	outputDir := flag.String("output-dir", "online-rules/category", "directory for generated YAML files")
	flag.Parse()

	templates, err := store.BuiltInCategoryTemplates()
	if err != nil || len(templates) == 0 {
		fatalf("load built-in category template: %v", err)
	}
	template := templates[0]
	if err := os.MkdirAll(*outputDir, 0o755); err != nil {
		fatalf("create output directory: %v", err)
	}
	write(filepath.Join(*outputDir, "standard.yaml"), renderTemplate(template.Movie, template.TV, false, false))
	write(filepath.Join(*outputDir, "collections.yaml"), renderTemplate(template.Movie, template.TV, true, false))
	write(filepath.Join(*outputDir, "decade.yaml"), renderTemplate(template.Movie, template.TV, true, true))
}

func renderTemplate(movie, tv []model.CategoryRule, collections, decade bool) string {
	var out strings.Builder
	out.WriteString("# Generated from the built-in dian115 category template.\n")
	out.WriteString("# Explicit tmdb_id rules always have the highest runtime priority.\n")
	if decade {
		out.WriteString("sub_classify:\n")
		out.WriteString("  movie:\n    enabled: true\n    levels: [year_decade]\n")
		out.WriteString("  tv:\n    enabled: true\n    levels: [year_decade]\n\n")
	}
	writeSection(&out, "movie", movie, collections)
	out.WriteByte('\n')
	writeSection(&out, "tv", tv, collections)
	return out.String()
}

func writeSection(out *strings.Builder, mediaType string, rules []model.CategoryRule, collections bool) {
	out.WriteString(mediaType)
	out.WriteString(":\n")
	if collections {
		out.WriteString("  ")
		out.WriteString(strconv.Quote("合集"))
		out.WriteString(":\n    classify_by: collection_vocabulary\n")
	}
	for _, rule := range rules {
		path := strings.TrimSpace(rule.Path)
		if path == "" {
			continue
		}
		out.WriteString("  ")
		out.WriteString(strconv.Quote(path))
		if len(rule.Conditions) == 0 {
			out.WriteString(": {}\n")
			continue
		}
		out.WriteString(":\n")
		for _, condition := range rule.Conditions {
			key := strings.TrimSpace(condition.Field)
			if strings.EqualFold(strings.TrimSpace(condition.Logic), "OR") {
				key = "?" + key
			}
			out.WriteString("    ")
			out.WriteString(key)
			out.WriteString(": ")
			out.WriteString(strconv.Quote(condition.Value))
			out.WriteByte('\n')
		}
	}
}

func write(path, content string) {
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		fatalf("write %s: %v", path, err)
	}
	fmt.Printf("wrote %s\n", path)
}

func fatalf(format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}
