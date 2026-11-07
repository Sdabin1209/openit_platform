package main

import (
	"encoding/json"
	"os"
	"strings"
)

// Keycloak's declarative profile configuration is a realm component (Keycloak
// UserProfileProvider); importing it applies one rule to every user creation UI.
func userProfileComponents() map[string]any {
	raw, err := os.ReadFile("/etc/openit/schemas/_common.schema.json")
	if err != nil {
		die(70, "HumanUserId 스키마를 읽지 못했다")
	}
	var root map[string]any
	if json.Unmarshal(raw, &root) != nil {
		die(70, "HumanUserId 스키마 형식 오류")
	}
	defs, ok := root["$defs"].(map[string]any)
	if !ok {
		die(70, "HumanUserId 정의가 없다")
	}
	node, ok := defs["HumanUserId"].(map[string]any)
	if !ok {
		die(70, "HumanUserId 정의가 없다")
	}
	seen := map[string]bool{}
	for {
		ref, exists := node["$ref"].(string)
		if !exists {
			break
		}
		if !strings.HasPrefix(ref, "#/$defs/") || seen[ref] {
			die(70, "HumanUserId 참조를 해석하지 못했다")
		}
		seen[ref] = true
		node, ok = defs[strings.TrimPrefix(ref, "#/$defs/")].(map[string]any)
		if !ok {
			die(70, "HumanUserId 참조가 없다")
		}
	}
	pattern, ok := node["pattern"].(string)
	if !ok {
		die(70, "HumanUserId 패턴이 없다")
	}
	minimum, minOK := node["minLength"].(float64)
	maximum, maxOK := node["maxLength"].(float64)
	if !minOK || !maxOK {
		die(70, "HumanUserId 길이 조건이 없다")
	}
	permissions := map[string]any{"view": []string{"admin", "user"}, "edit": []string{"admin", "user"}}
	attributes := []any{
		map[string]any{"name": "username", "displayName": "${username}", "required": map[string]any{"roles": []string{"user"}}, "permissions": permissions,
			"validations": map[string]any{"pattern": map[string]any{"pattern": pattern}, "length": map[string]any{"min": minimum, "max": maximum}}},
		map[string]any{"name": "email", "displayName": "${email}", "permissions": permissions, "validations": map[string]any{"email": map[string]any{}}},
		map[string]any{"name": "firstName", "displayName": "${firstName}", "permissions": permissions},
		map[string]any{"name": "lastName", "displayName": "${lastName}", "permissions": permissions},
	}
	profile, err := json.Marshal(map[string]any{"attributes": attributes})
	if err != nil {
		die(70, "사용자 프로필 설정을 만들지 못했다")
	}
	return map[string]any{"org.keycloak.userprofile.UserProfileProvider": []any{
		map[string]any{"name": "declarative-user-profile", "providerId": "declarative-user-profile",
			"config": map[string]any{"kc.user.profile.config": []string{string(profile)}}},
	}}
}
