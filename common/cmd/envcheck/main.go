// envcheck: 계약 Env 스키마로 환경을 검증하고 기본값을 채워 `export NAME='값'` 줄로 낸다. 사용: envcheck <스키마 파일> [--no-export]   종료 코드 0 통과, 64 위반(이름·사유만 출력, 값은 출력하지 않는다).
package main

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"openit/platform/common/envcheck"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "사용: envcheck <스키마 파일> [--no-export]")
		os.Exit(64)
	}
	vals, bad := envcheck.Load(os.Args[1])
	if len(bad) > 0 {
		name := os.Args[1][strings.LastIndex(os.Args[1], "/")+1:]
		fmt.Fprintf(os.Stderr, "envcheck: %s 위반 %d건\n", strings.TrimSuffix(name, ".schema.json"), len(bad))
		for _, b := range bad {
			fmt.Fprintln(os.Stderr, "  "+b)
		}
		os.Exit(64)
	}
	if len(os.Args) > 2 && os.Args[2] == "--no-export" {
		return
	}
	keys := make([]string, 0, len(vals))
	for k := range vals {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		fmt.Printf("export %s='%s'\n", k, strings.ReplaceAll(vals[k], "'", `'\''`))
	}
}
