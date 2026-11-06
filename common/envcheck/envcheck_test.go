package envcheck

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func fixture(t *testing.T, schema string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "Env.schema.json")
	if err := os.WriteFile(path, []byte(schema), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestSchemaConditionsAreNotSilentlyIgnored(t *testing.T) {
	tests := []struct {
		name, schema, value string
		valid               bool
	}{
		{"minLength", `{"properties":{"ENV_TEST_VALUE":{"type":"string","minLength":2}}}`, "a", false},
		{"unicodeLength", `{"properties":{"ENV_TEST_VALUE":{"type":"string","maxLength":2}}}`, "가😀", true},
		{"maxLength", `{"properties":{"ENV_TEST_VALUE":{"type":"string","maxLength":2}}}`, "가😀a", false},
		{"const", `{"properties":{"ENV_TEST_VALUE":{"const":"accepted"}}}`, "rejected", false},
		{"anyOf", `{"properties":{"ENV_TEST_VALUE":{"anyOf":[{"const":"a"},{"const":"b"}]}}}`, "CONFIDENTIAL_SENTINEL", false},
		{"not", `{"properties":{"ENV_TEST_VALUE":{"not":{"const":"forbidden"}}}}`, "forbidden", false},
		{"referenceChain", `{"properties":{"ENV_TEST_VALUE":{"$ref":"#/$defs/A"}},"$defs":{"A":{"$ref":"#/$defs/B"},"B":{"type":"string","minLength":2}}}`, "a", false},
		{"format", `{"properties":{"ENV_TEST_VALUE":{"type":"string","format":"date-time"}}}`, "2026-02-30T00:00:00Z", false},
		{"validFormat", `{"properties":{"ENV_TEST_VALUE":{"type":"string","format":"date-time"}}}`, "2026-11-06T00:00:00Z", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Setenv("ENV_TEST_VALUE", tt.value)
			_, bad := Load(fixture(t, tt.schema))
			if (len(bad) == 0) != tt.valid {
				t.Fatalf("valid=%v want=%v; rules=%v", len(bad) == 0, tt.valid, bad)
			}
			if strings.Contains(strings.Join(bad, " "), tt.value) {
				t.Fatal("validation exposed an input value")
			}
		})
	}
}

func TestDefaultsAreValidated(t *testing.T) {
	t.Setenv("ENV_TEST_OTHER", "present")
	os.Unsetenv("ENV_TEST_DEFAULT")
	_, bad := Load(fixture(t, `{"properties":{"ENV_TEST_DEFAULT":{"type":"string","minLength":1,"default":""}}}`))
	if len(bad) == 0 {
		t.Fatal("invalid default accepted")
	}
	values, bad := Load(fixture(t, `{"properties":{"ENV_TEST_DEFAULT":{"type":"string","default":"ok"}}}`))
	if len(bad) != 0 || values["ENV_TEST_DEFAULT"] != "ok" {
		t.Fatal("valid default not applied")
	}
}

func TestNestedConditionRequiredAndElse(t *testing.T) {
	path := fixture(t, `{"properties":{"ENV_TEST_MODE":{"type":"string"},"ENV_TEST_REQUIRED":{"type":"string"}},"allOf":[{"if":{"properties":{"ENV_TEST_MODE":{"enum":["a","b"]}},"required":["ENV_TEST_MODE"]},"then":{"required":["ENV_TEST_REQUIRED"]},"else":{"not":{"required":["ENV_TEST_REQUIRED"]}}}]}`)
	t.Setenv("ENV_TEST_MODE", "a")
	os.Unsetenv("ENV_TEST_REQUIRED")
	_, bad := Load(path)
	if len(bad) == 0 {
		t.Fatal("conditional required ignored")
	}
	t.Setenv("ENV_TEST_REQUIRED", "nonsecret")
	_, bad = Load(path)
	if len(bad) != 0 {
		t.Fatal("valid conditional input rejected")
	}
	t.Setenv("ENV_TEST_MODE", "c")
	_, bad = Load(path)
	if len(bad) == 0 {
		t.Fatal("else ignored")
	}
}

func TestUnpackagedReferenceFailsWithoutNetwork(t *testing.T) {
	t.Setenv("ENV_TEST_VALUE", "private-sentinel")
	_, bad := Load(fixture(t, `{"properties":{"ENV_TEST_VALUE":{"$ref":"https://unpackaged.invalid/Secret.schema.json"}}}`))
	if len(bad) == 0 {
		t.Fatal("unpackaged reference accepted")
	}
	if strings.Contains(strings.Join(bad, " "), "private-sentinel") {
		t.Fatal("value exposed")
	}
}

func TestConditionalPresenceDoesNotInventAnAbsentProperty(t *testing.T) {
	path := fixture(t, `{"properties":{"ENV_TEST_MODE":{"type":"string"},"ENV_TEST_OTHER":{"type":"string"}},"allOf":[{"if":{"properties":{"ENV_TEST_MODE":{"const":"yes"}},"required":["ENV_TEST_MODE"]},"then":{"required":["ENV_TEST_OTHER"]}}]}`)
	t.Setenv("ENV_TEST_MODE", "temporary")
	os.Unsetenv("ENV_TEST_MODE")
	t.Setenv("ENV_TEST_OTHER", "temporary")
	os.Unsetenv("ENV_TEST_OTHER")
	_, bad := Load(path)
	if len(bad) != 0 {
		t.Fatalf("absent condition incorrectly matched: %v", bad)
	}
}

func TestPackagedRelativeReference(t *testing.T) {
	directory := t.TempDir()
	target := filepath.Join(directory, "Target.schema.json")
	if err := os.WriteFile(target, []byte(`{"$id":"Target.schema.json","type":"string","minLength":2}`), 0600); err != nil {
		t.Fatal(err)
	}
	source := filepath.Join(directory, "Env.schema.json")
	if err := os.WriteFile(source, []byte(`{"properties":{"ENV_TEST_VALUE":{"$ref":"Target.schema.json"}}}`), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("ENV_TEST_VALUE", "x")
	_, bad := Load(source)
	if len(bad) == 0 {
		t.Fatal("packaged assertion ignored")
	}
	t.Setenv("ENV_TEST_VALUE", "valid")
	_, bad = Load(source)
	if len(bad) != 0 {
		t.Fatalf("packaged reference rejected: %v", bad)
	}
}
