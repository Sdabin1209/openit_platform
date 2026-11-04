#!/bin/sh
# 감시 이미지 진입점(ADR 0010): 역할 하나를 골라 그 프로세스를 실행한다. 설정은 이미지 안(/etc/openit/monitoring), 대상 파일(targets/)과 루트 인증서(/etc/openit/pki)는 배치가 마운트한다.
# 역할: prometheus(:9090, 데이터 /prometheus) alertmanager(:9093, 데이터 /alertmanager) blackbox(:9115) json(:7979) node(:9100, 호스트 루트 /host 읽기 전용, textfile /textfile)
#      check: 이미지 안 설정 점검(promtool check config/rules, amtool check-config, blackbox --config.check). 추가 인자는 그대로 넘긴다.
set -eu
# 환경은 계약 MonitoringEnv 로 검증하고 기본값을 채운다(위반 64)
eval "$(envcheck /etc/openit/schemas/MonitoringEnv.schema.json)" || exit 64
# 설정 틀(이미지 안 /etc/openit/monitoring)의 두 자리(@TARGETS_DIR@, @ROOT_CA@)를 입력(MONITORING_TARGETS_DIR, MONITORING_ROOT_CA)으로 채워 /tmp 에 둔다: 배치는 이미지 안 설정 경로를 알 필요가 없다
I=/etc/openit/monitoring; C=/tmp/openit-monitoring; role=${1:-prometheus}; [ $# -eq 0 ] || shift
mkdir -p "$C"
for f in prometheus.yml alertmanager.yml blackbox.yml json-exporter.yml; do sed -e "s|@TARGETS_DIR@|$MONITORING_TARGETS_DIR|g" -e "s|@ROOT_CA@|$MONITORING_ROOT_CA|g" "$I/$f" > "$C/$f"; done
ln -sfn "$I/rules" "$C/rules"
case "$role" in
  prometheus)   exec prometheus --config.file="$C/prometheus.yml" --storage.tsdb.path=/prometheus --storage.tsdb.retention.time="$PROMETHEUS_RETENTION" --web.listen-address=:9090 "$@" ;;   # 15d: Prometheus 기본값(측정 안 함)
  alertmanager) exec alertmanager --config.file="$C/alertmanager.yml" --storage.path=/alertmanager --web.listen-address=:9093 "$@" ;;
  blackbox)     exec blackbox_exporter --config.file="$C/blackbox.yml" "$@" ;;
  json)         exec json_exporter --config.file="$C/json-exporter.yml" "$@" ;;
  node)         exec node_exporter --path.rootfs=/host --collector.disable-defaults --collector.filesystem --collector.timex --collector.textfile --collector.textfile.directory=/textfile --web.listen-address=:9100 "$@" ;;   # 필요한 수집기만(최소 권한)
  check)
    promtool check config "$C/prometheus.yml" && promtool check rules "$C/rules/openit.yml" && amtool check-config "$C/alertmanager.yml" && blackbox_exporter --config.check --config.file="$C/blackbox.yml" ;;
  *) echo "알 수 없는 역할: $role (prometheus|alertmanager|blackbox|json|node|check)" >&2; exit 2 ;;
esac
