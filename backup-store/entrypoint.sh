#!/bin/sh
# 백업 저장소 시작(ADR 0011). 영역마다 자격 파일 하나(/run/secrets/areas/<영역>, 내용 한 줄 '<영역>:<암호>' = 그 영역의 OPENIT_BACKUP_CREDENTIALS_FILE 과 같은 모양, RFC 7617)를 받아
# bcrypt htpasswd 를 /tmp(읽기 전용 루트의 tmpfs)에 만들고 rest-server --private-repos 로 띄운다: 사용자 이름 = 저장소 첫 경로 조각이라 영역은 자기 경로(/<영역>/…)만 쓴다.
# 암호 값은 출력하지 않는다(htpasswd -i 는 표준 입력으로 받는다). append-only 는 켜지 않는다: 영역 백업 잡이 forget --prune 으로 보존을 지킨다(헤드 결정, ADR 0011).
set -eu
# 환경은 계약 BackupStoreEnv 로 검증하고 기본값을 채운다(위반 64)
eval "$(envcheck /etc/openit/schemas/BackupStoreEnv.schema.json)" || exit 64
DIR=$OPENIT_BACKUP_AREAS_DIR; TLS=$OPENIT_BACKUP_TLS_DIR; HT=/tmp/htpasswd
[ -r "$TLS/tls.crt" ] && [ -r "$TLS/tls.key" ] || { echo "backup-store: $TLS/tls.crt, tls.key 가 없다(https 전용)" >&2; exit 2; }
: > "$HT"; n=0
for f in "$DIR"/*; do
  [ -f "$f" ] || continue
  line=$(head -n1 "$f"); user=${line%%:*}; pw=${line#*:}
  case "$user" in ''|*[!a-z0-9-]*) echo "backup-store: 자격 파일 $(basename "$f") 의 사용자 이름은 소문자·숫자·- 만(영역 이름)" >&2; exit 2;; esac
  [ "$user" = "$(basename "$f")" ] || { echo "backup-store: 자격 파일 이름과 사용자 이름이 다르다: $(basename "$f")" >&2; exit 2; }
  [ -n "$pw" ] && [ "$pw" != "$line" ] || { echo "backup-store: 자격 파일 $(basename "$f") 에 '<사용자>:<암호>' 가 없다" >&2; exit 2; }
  printf '%s' "$pw" | htpasswd -iB "$HT" "$user" >/dev/null 2>&1 || { echo "backup-store: htpasswd 실패: $user" >&2; exit 2; }
  n=$((n+1))
done
[ "$n" -gt 0 ] || { echo "backup-store: $DIR 에 영역 자격 파일이 없다(인증 없는 시작은 하지 않는다)" >&2; exit 2; }
echo "backup-store: 영역 $n 개, private-repos, https" >&2
exec rest-server --path /data --listen ":$OPENIT_BACKUP_PORT" --private-repos --htpasswd-file "$HT" --tls --tls-cert "$TLS/tls.crt" --tls-key "$TLS/tls.key" --tls-min-ver 1.2
