// Package envcheck: 컨테이너가 받은 환경 변수를 계약 Env 스키마(JSON Schema 2020-12 의 이 영역이 쓰는 부분집합)로 검증하고 기본값을 채운다.
// 왜 스키마 파일을 읽나: 이름·패턴·기본값의 정본은 계약(구조 규칙 6)이다. 이미지는 계약 스키마를 빌드 때 받아 넣고 여기서는 해석만 한다(복사본을 손으로 쓰지 않는다).
// 왜 Go 인가: Keycloak(ubi-micro)·oauth2-proxy(distroless) 이미지에는 파이썬도 셸도 없을 수 있다. 같은 코드를 모든 platform 이미지가 쓴다.
package envcheck

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"sort"
	"strings"
)

func asMap(v any) map[string]any { m, _ := v.(map[string]any); return m }

// resolve: $ref(#/$defs/X)를 따라가 속성 정의를 합친다.
func resolve(root map[string]any, prop map[string]any) map[string]any {
	out := map[string]any{}
	if ref, ok := prop["$ref"].(string); ok {
		name := strings.TrimPrefix(ref, "#/$defs/")
		for k, v := range asMap(asMap(root["$defs"])[name]) {
			out[k] = v
		}
	}
	for k, v := range prop {
		if k != "$ref" {
			out[k] = v
		}
	}
	return out
}

// Load: 스키마 파일로 현재 환경을 검증한다. 반환: 기본값이 채워진 값들(스키마 속성 이름만), 위반 목록(값은 담지 않는다).
func Load(schemaPath string) (map[string]string, []string) {
	raw, err := os.ReadFile(schemaPath)
	if err != nil {
		return nil, []string{"스키마를 읽지 못했다: " + err.Error()}
	}
	var root map[string]any
	if err := json.Unmarshal(raw, &root); err != nil {
		return nil, []string{"스키마 형식 오류: " + err.Error()}
	}
	props := asMap(root["properties"])
	var bad []string
	vals := map[string]string{}
	// 1) 이름 규칙(propertyNames): 이 영역 접두어를 쓰는데 스키마에 없는 이름은 위반
	if pn := asMap(root["propertyNames"]); pn != nil {
		if any_, ok := pn["anyOf"].([]any); ok {
			for _, kv := range os.Environ() {
				name := strings.SplitN(kv, "=", 2)[0]
				okName := false
				for _, alt := range any_ {
					a := asMap(alt)
					if n := asMap(a["not"]); n != nil {
						if re, e := regexp.Compile(fmt.Sprint(n["pattern"])); e == nil && !re.MatchString(name) {
							okName = true
						}
					}
					if en, ok := a["enum"].([]any); ok {
						for _, x := range en {
							if x == name {
								okName = true
							}
						}
					}
				}
				if !okName {
					bad = append(bad, name+": 이 영역 접두어를 쓰지만 스키마에 없는 이름")
				}
			}
		}
	}
	// 2) 속성: 값 검증, 기본값 채우기
	names := make([]string, 0, len(props))
	for n := range props {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, n := range names {
		p := resolve(root, asMap(props[n]))
		v, set := os.LookupEnv(n)
		if !set {
			if d, ok := p["default"]; ok {
				vals[n] = fmt.Sprint(d)
			}
			continue
		}
		if pat, ok := p["pattern"].(string); ok {
			if re, e := regexp.Compile(pat); e != nil || !re.MatchString(v) {
				bad = append(bad, n+": 값이 형식(pattern)에 맞지 않는다")
			}
		}
		if en, ok := p["enum"].([]any); ok {
			found := false
			for _, x := range en {
				if x == v {
					found = true
				}
			}
			if !found {
				bad = append(bad, n+": 허용된 값이 아니다(enum)")
			}
		}
		vals[n] = v
	}
	// 3) 필수와 조건부 필수
	if req, ok := root["required"].([]any); ok {
		for _, r := range req {
			if _, ok := vals[fmt.Sprint(r)]; !ok {
				bad = append(bad, fmt.Sprint(r)+": 필수인데 없다")
			}
		}
	}
	if all, ok := root["allOf"].([]any); ok {
		for _, c := range all {
			cm := asMap(c)
			ifc, thn := asMap(cm["if"]), asMap(cm["then"])
			if ifc == nil || thn == nil {
				continue
			}
			match := true
			for pn, pv := range asMap(ifc["properties"]) {
				if cst, ok := asMap(pv)["const"]; ok && vals[pn] != fmt.Sprint(cst) {
					match = false
				}
			}
			if match {
				if req, ok := thn["required"].([]any); ok {
					for _, r := range req {
						if _, ok := vals[fmt.Sprint(r)]; !ok {
							bad = append(bad, fmt.Sprint(r)+": 이 조건에서 필수인데 없다")
						}
					}
				}
			}
		}
	}
	sort.Strings(bad)
	return vals, bad
}
