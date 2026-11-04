#!/bin/sh
# 감시 이미지 진입점(ADR 0010): 역할 하나를 골라 그 프로세스를 실행한다. 설정은 이미지 안(/etc/openit/monitoring), 대상 파일(targets/)과 루트 인증서(/etc/openit/pki)는 배치가 마운트한다.
# 역할: prometheus(:9090, 데이터 /prometheus) alertmanager(:9093, 데이터 /alertmanager) blackbox(:9115) json(:7979) node(:9100, 호스트 루트 /host 읽기 전용, textfile /textfile)
#      check: 이미지 안 설정 점검(promtool check config/rules, amtool check-config, blackbox --config.check). 추가 인자는 그대로 넘긴다.
set -eu
C=/etc/openit/monitoring; role=${1:-prometheus}; [ $# -eq 0 ] || shift
case "$role" in
  prometheus)   exec prometheus --config.file="$C/prometheus.yml" --storage.tsdb.path=/prometheus --storage.tsdb.retention.time="${PROMETHEUS_RETENTION:-15d}" --web.listen-address=:9090 "$@" ;;   # 15d: Prometheus 기본값(측정 안 함)
  alertmanager) exec alertmanager --config.file="$C/alertmanager.yml" --storage.path=/alertmanager --web.listen-address=:9093 "$@" ;;
  blackbox)     exec blackbox_exporter --config.file="$C/blackbox.yml" "$@" ;;
  json)         exec json_exporter --config.file="$C/json-exporter.yml" "$@" ;;
  node)         exec node_exporter --path.rootfs=/host --collector.disable-defaults --collector.filesystem --collector.timex --collector.textfile --collector.textfile.directory=/textfile --web.listen-address=:9100 "$@" ;;   # 필요한 수집기만(최소 권한)
  check)
    promtool check config "$C/prometheus.yml" && promtool check rules "$C/rules/openit.yml" && amtool check-config "$C/alertmanager.yml" && blackbox_exporter --config.check --config.file="$C/blackbox.yml" ;;
  *) echo "알 수 없는 역할: $role (prometheus|alertmanager|blackbox|json|node|check)" >&2; exit 2 ;;
esac
