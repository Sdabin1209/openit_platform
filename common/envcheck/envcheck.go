// Package envcheck validates container environments with their complete JSON
// Schema contract. Defaults are applied before validation and exports contain
// only properties declared by the owner. Diagnostics never include values.
package envcheck

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/dlclark/regexp2"
	"github.com/santhosh-tekuri/jsonschema/v6"
	"github.com/santhosh-tekuri/jsonschema/v6/kind"
)

func asMap(v any) map[string]any { m, _ := v.(map[string]any); return m }

type ecmaRegexp regexp2.Regexp

func (r *ecmaRegexp) MatchString(s string) bool {
	ok, err := (*regexp2.Regexp)(r).MatchString(s)
	return err == nil && ok
}
func (r *ecmaRegexp) String() string { return (*regexp2.Regexp)(r).String() }
func compileRegexp(pattern string) (jsonschema.Regexp, error) {
	r, err := regexp2.Compile(pattern, regexp2.ECMAScript)
	if err != nil {
		return nil, err
	}
	return (*ecmaRegexp)(r), nil
}

type offlineLoader struct{}

func (offlineLoader) Load(string) (any, error) {
	return nil, errors.New("schema resource is not packaged locally")
}

// Default is an annotation: use the owner's property or referenced property.
// Reference lookup itself belongs to the standard schema compiler.
func propertyDefault(s *jsonschema.Schema, seen map[*jsonschema.Schema]bool) (any, bool) {
	if s == nil || seen[s] {
		return nil, false
	}
	seen[s] = true
	if s.Default != nil {
		return *s.Default, true
	}
	return propertyDefault(s.Ref, seen)
}

func problems(e *jsonschema.ValidationError, result map[string]bool) {
	if required, ok := e.ErrorKind.(*kind.Required); ok {
		for _, name := range required.Missing {
			result[name+": 필수인데 없다 (required)"] = true
		}
	} else if len(e.Causes) == 0 {
		path := strings.Join(e.InstanceLocation, "/")
		if path == "" {
			path = "(환경)"
		}
		keyword := strings.Join(e.ErrorKind.KeywordPath(), "/")
		if keyword == "" {
			keyword = "validation"
		}
		result[path+": 값이 스키마 형식("+keyword+")에 맞지 않는다"] = true
	}
	for _, child := range e.Causes {
		problems(child, result)
	}
}

// Load uses the full Draft 2020-12 validator, including compositions, formats,
// propertyNames and chained references. Unknown resources fail without network.
func Load(schemaPath string) (map[string]string, []string) {
	absolute, err := filepath.Abs(schemaPath)
	if err != nil {
		return nil, []string{"스키마 경로 오류"}
	}
	raw, err := os.ReadFile(absolute)
	if err != nil {
		return nil, []string{"스키마를 읽지 못했다"}
	}
	document, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		return nil, []string{"스키마 형식 오류"}
	}
	root := asMap(document)
	if root == nil {
		return nil, []string{"환경 스키마는 객체여야 한다"}
	}
	compiler := jsonschema.NewCompiler()
	compiler.DefaultDraft(jsonschema.Draft2020)
	compiler.AssertFormat()
	compiler.UseRegexpEngine(compileRegexp)
	compiler.UseLoader(offlineLoader{})
	// Register only packaged schema files. Never fetch URLs or adjacent repositories.
	paths, err := filepath.Glob(filepath.Join(filepath.Dir(absolute), "*.schema.json"))
	if err != nil {
		return nil, []string{"스키마 목록 오류"}
	}
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, []string{"패키지 스키마를 읽지 못했다"}
		}
		doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
		if err != nil {
			return nil, []string{"패키지 스키마 형식 오류"}
		}
		if err = compiler.AddResource(path, doc); err != nil {
			return nil, []string{"패키지 스키마 등록 오류"}
		}
	}
	// A caller may use another filename, for example a temporary contract fixture.
	found := false
	for _, path := range paths {
		if path == absolute {
			found = true
		}
	}
	if !found {
		if err = compiler.AddResource(absolute, document); err != nil {
			return nil, []string{"스키마 등록 오류"}
		}
	}
	schema, err := compiler.Compile(absolute)
	if err != nil {
		return nil, []string{"스키마를 완전히 해석하지 못했다"}
	}
	instance := map[string]any{}
	for _, item := range os.Environ() {
		key, value, _ := strings.Cut(item, "=")
		instance[key] = value
	}
	exports := map[string]string{}
	for name, definition := range schema.Properties {
		if actual, present := instance[name]; present {
			exports[name] = actual.(string)
			continue
		}
		if fallback, present := propertyDefault(definition, map[*jsonschema.Schema]bool{}); present {
			text, ok := fallback.(string)
			if !ok {
				return nil, []string{name + ": 환경 기본값은 문자열이어야 한다"}
			}
			exports[name] = text
			instance[name] = text
		}
	}
	if err = schema.Validate(instance); err != nil {
		var validation *jsonschema.ValidationError
		if !errors.As(err, &validation) {
			return nil, []string{"환경 검증 실패"}
		}
		unique := map[string]bool{}
		problems(validation, unique)
		bad := make([]string, 0, len(unique))
		for item := range unique {
			bad = append(bad, item)
		}
		sort.Strings(bad)
		return nil, bad
	}
	return exports, nil
}
