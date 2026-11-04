#!/bin/sh
# platform 데이터 주인 백업·복구 잡(RUNTIME R10.1, DATA_OWNERSHIP 백업 행): 폴더 하나를 platform 백업 저장소(restic REST, https)로 백업하거나 거기서 되돌린다. 백업 저장소가 platform 안이라 영역 안 통신이다(영역 게이트웨이 출구를 거치지 않는다).
# 사용: platform-backup-job <backup|restore> <태그> <폴더|@환경변수[/뒤붙임]> <저장소 인증서를 검증할 루트 PEM|@환경변수[/뒤붙임]> [postgres @DB접속URI파일변수]   (@NAME 은 deploy 가 준 환경 변수 NAME 의 값)
# 저장소 인증서를 검증할 루트는 잡이 복구하려는 데이터 안에 두지 않는다(step-ca 는 그 CA 가 발급한 인증서를 백업 저장소가 쓰므로, 전부 잃은 뒤 복구에는 밖에서 준 루트(/etc/openit/pki/root_ca.crt)가 있어야 한다).
# 입력은 계약 CommonEnv: OPENIT_BACKUP_URL(저장 위치), OPENIT_BACKUP_CREDENTIALS_FILE('<사용자>:<암호>' 한 줄), OPENIT_BACKUP_REPO_PASSWORD_FILE(restic 암호). 비밀은 파일로 받고 어떤 출력에도 쓰지 않는다(D84).
# 출력: 표준 출력 마지막 줄 BackupJobResult JSON 한 줄. 종료 코드 0 ok, 75 재시도 가능(저장소에 닿지 못함, EX_TEMPFAIL), 1 그 밖의 실패. 같은 저장소를 여러 데이터가 쓰므로 스냅숏에 태그를 붙이고 복구는 그 태그의 최신을 쓴다.
# 멱등: 저장소가 없으면 만들고(restic init), 백업은 새 스냅숏을 더할 뿐이며 복구는 같은 스냅숏을 같은 폴더에 다시 쓴다. 일관성: 실행 중인 서비스의 폴더를 파일 단위로 복사한다(스냅숏 도중 쓰기는 다음 스냅숏에 들어간다).
set -u
mode=${1:-}; tag=${2:-}; dirarg=${3:-}; caarg=${4:-}; engine=${5:-}; urlarg=${6:-}   # engine=postgres: 백업 전에 pg_dump 로 폴더에 덤프하고 복구 뒤에 pg_restore 로 되돌린다(urlarg = DB 접속 URI 파일 경로를 담은 @환경변수)
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
started=$(now); ERR=/tmp/.platform-backup.err
json_str() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
finish() { # finish <ok|failed> <snapshot|""> <bytes> <종료코드> <오류코드> <메시지> <retryable>
  if [ "$1" = ok ]; then printf '{"status":"ok","snapshot_id":"%s","bytes":%s,"started_at":"%s","finished_at":"%s","error":null}\n' "$2" "$3" "$started" "$(now)"
  else [ -s "$ERR" ] && sed 's#rest:[^[:space:]]*#<저장소>#g' "$ERR" | tail -n 3 >&2   # 작업 로그용 진단(저장소 주소는 가린다, 자격은 환경에만 있어 나오지 않는다)
    printf '{"status":"failed","snapshot_id":null,"bytes":0,"started_at":"%s","finished_at":"%s","error":{"code":"%s","message":"%s","retryable":%s}}\n' "$started" "$(now)" "$5" "$(json_str "$6")" "$7"; fi
  exit "$4"
}
resolve() { # @NAME[/뒤붙임] -> 값
  case "$1" in @*) n=${1#@}; v=${n%%/*}; rest=${n#"$v"}; eval "val=\${$v:-}"; [ -n "$val" ] || return 1; printf '%s%s' "$val" "$rest";; *) printf '%s' "$1";; esac
}
case "$mode" in backup|restore) ;; *) finish failed "" 0 1 INVALID_RECORD "사용: backup|restore <태그> <폴더> <루트 PEM>" false;; esac
ENVOUT=$(envcheck /etc/openit/schemas/CommonEnv.schema.json 2>"$ERR") || finish failed "" 0 1 INVALID_RECORD "환경이 CommonEnv 를 어겼다" false
eval "$ENVOUT"
dir=$(resolve "$dirarg") || finish failed "" 0 1 INVALID_RECORD "폴더 환경 변수가 없다" false
ca=$(resolve "$caarg") || finish failed "" 0 1 INVALID_RECORD "루트 인증서 환경 변수가 없다" false
[ -n "${OPENIT_BACKUP_URL:-}" ] && [ -r "${OPENIT_BACKUP_CREDENTIALS_FILE:-/nonexistent}" ] && [ -r "${OPENIT_BACKUP_REPO_PASSWORD_FILE:-/nonexistent}" ] && [ -r "$ca" ] || finish failed "" 0 1 INVALID_RECORD "OPENIT_BACKUP_URL·자격 파일·저장소 암호 파일·루트 인증서가 필요하다" false
case "$OPENIT_BACKUP_URL" in https://*) ;; *) finish failed "" 0 1 INVALID_RECORD "OPENIT_BACKUP_URL 은 https 주소여야 한다(R1.1)" false;; esac
creds=$(head -n1 "$OPENIT_BACKUP_CREDENTIALS_FILE")
export RESTIC_REPOSITORY="rest:$OPENIT_BACKUP_URL" RESTIC_PASSWORD_FILE="$OPENIT_BACKUP_REPO_PASSWORD_FILE" RESTIC_CACERT="$ca" RESTIC_CACHE_DIR=/tmp/.restic-cache RESTIC_REST_USERNAME="${creds%%:*}" RESTIC_REST_PASSWORD="${creds#*:}"   # restic REST 백엔드의 표준 자격 변수: 이 프로세스의 자식에게만 간다
unset creds
net_err() { grep -qiE 'dial|connect|timeout|no such host|refused|unreachable|EOF|tls' "$ERR"; }
# 연결 확인: restic REST 백엔드는 닿지 않으면 오래 재시도하므로(수 분) 첫 접속은 30초로 끝낸다. 시간 초과는 닿지 못한 것(75, 재시도 가능)이다. 30초는 측정하지 않은 값이다
timeout 30 restic cat config >/dev/null 2>"$ERR"; rc=$?
if [ $rc -eq 124 ] || [ $rc -eq 143 ]; then echo "백업 저장소 연결 시간 초과" > "$ERR"; finish failed "" 0 75 UNAVAILABLE "백업 저장소에 닿지 못했다" true; fi
if [ $rc -eq 10 ]; then
  [ "$mode" = backup ] || finish failed "" 0 1 NOT_FOUND "백업 저장소에 이 저장소가 없다" false
  restic init >/dev/null 2>"$ERR" || { net_err && finish failed "" 0 75 UNAVAILABLE "백업 저장소에 닿지 못했다" true; finish failed "" 0 1 INTERNAL "저장소를 만들지 못했다" false; }
elif [ $rc -ne 0 ]; then
  net_err && finish failed "" 0 75 UNAVAILABLE "백업 저장소에 닿지 못했다" true
  finish failed "" 0 1 PERMISSION_DENIED "백업 저장소가 거절했다(자격·암호)" false
fi
pg_fail() { net_err && finish failed "" 0 75 UNAVAILABLE "데이터베이스에 닿지 못했다" true; finish failed "" 0 1 INTERNAL "$1" false; }
if [ "$engine" = postgres ]; then   # 데이터베이스를 가진 영역의 백업(R10.1): 실행 중인 DB 를 일관된 한 시점의 덤프 파일로 꺼내 폴더에 두고 그 폴더를 백업한다. 덤프 파일은 비밀 URI 를 담지 않는다
  urlfile=$(resolve "$urlarg") || finish failed "" 0 1 INVALID_RECORD "DB 접속 URI 파일 환경 변수가 없다" false
  [ -r "$urlfile" ] || finish failed "" 0 1 INVALID_RECORD "DB 접속 URI 파일을 읽을 수 없다" false
  export PGSSLROOTCERT="$ca"; mkdir -p "$dir"
fi
if [ "$mode" = backup ]; then
  if [ "$engine" = postgres ]; then rm -f "$dir/dump.pgdump"; pg_dump --format=custom --no-owner --file "$dir/dump.pgdump" "$(cat "$urlfile")" 2>"$ERR" || pg_fail "덤프에 실패했다"; fi
  out=$(restic backup --json --tag "$tag" "$dir" 2>"$ERR") || { net_err && finish failed "" 0 75 UNAVAILABLE "백업 저장소에 닿지 못했다" true; finish failed "" 0 1 INTERNAL "백업에 실패했다" false; }
  sum=$(printf '%s\n' "$out" | grep '"message_type":"summary"' | tail -n1)
  snap=$(printf '%s' "$sum" | sed -n 's/.*"snapshot_id":"\([0-9a-f]*\)".*/\1/p'); bytes=$(printf '%s' "$sum" | sed -n 's/.*"total_bytes_processed":\([0-9]*\).*/\1/p')
  [ -n "$snap" ] || finish failed "" 0 1 INTERNAL "스냅숏 ID 를 읽지 못했다" false
  finish ok "$snap" "${bytes:-0}" 0
else
  snaps=$(restic snapshots --json --latest 1 --tag "$tag" 2>"$ERR") || { net_err && finish failed "" 0 75 UNAVAILABLE "백업 저장소에 닿지 못했다" true; finish failed "" 0 1 INTERNAL "스냅숏 목록을 읽지 못했다" false; }
  snap=$(printf '%s' "$snaps" | sed -n 's/.*"id":"\([0-9a-f]*\)".*/\1/p' | tail -n1)
  [ -n "$snap" ] || finish failed "" 0 1 NOT_FOUND "복구할 스냅숏이 없다(태그 $tag)" false
  # 스냅숏의 하위 폴더(snap:경로)를 그 폴더에 바로 푼다: 읽기 전용 루트 파일시스템에서 상위 경로(/home 등)를 건드리지 않는다
  out=$(restic restore "$snap:$dir" --json --target "$dir" 2>"$ERR") || { net_err && finish failed "" 0 75 UNAVAILABLE "백업 저장소에 닿지 못했다" true; finish failed "" 0 1 INTERNAL "복구에 실패했다" false; }
  bytes=$(printf '%s\n' "$out" | grep '"message_type":"summary"' | tail -n1 | sed -n 's/.*"total_bytes":\([0-9]*\).*/\1/p')
  if [ "$engine" = postgres ]; then pg_restore --clean --if-exists --no-owner --dbname "$(cat "$urlfile")" "$dir/dump.pgdump" 2>"$ERR" || pg_fail "되돌리기에 실패했다"; fi
  finish ok "$snap" "${bytes:-0}" 0
fi
