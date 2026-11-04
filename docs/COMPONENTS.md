# 컴포넌트 배포 입력 (monitoring, backup-store, step-ca)

모두 비루트, 읽기 전용 루트(`--read-only`), `--cap-drop ALL`, `no-new-privileges`. 빌드: `bash scripts/build-image.sh <요청>`(variant `monitoring|backup-store|step-ca`). 라벨 `io.openit.*` 는 BuildImageResult 로 검증된다. 비밀 값은 파일로만 받는다.

## monitoring (uid 65534, ADR 0010)
한 이미지, 컨테이너마다 역할 인자 하나. 이미지 안 설정 점검: `docker run <이미지> check`.
| 역할 | 포트 | 마운트 | 비고 |
|---|---|---|---|
| prometheus | 9090 | `/prometheus`(rw 볼륨 또는 tmpfs uid 65534), `/etc/openit/pki/root_ca.crt`(ro), `/etc/openit/monitoring/targets/`(ro: `metrics.yml` `readyz.yml` `public.yml` `gate.yml`, file_sd, 비면 `[]`) | 환경 `PROMETHEUS_RETENTION`(15d). 네트워크 별칭 `alertmanager`·`blackbox-exporter`·`json-exporter`·`node-exporter` 를 이름으로 찾는다 |
| alertmanager | 9093 | `/alertmanager`(rw) | 수신자 미정(설정에 receiver 없음) |
| blackbox | 9115 | `/etc/openit/pki/root_ca.crt`(ro) | 공개 입구가 사설 인증서면 추가 루트를 `SSL_CERT_FILE` 로 |
| json | 7979 | `/etc/openit/pki/root_ca.crt`(ro) | release-gate `/readyz` 의 judging_loop |
| node | 9100 | `/host`(호스트 `/` ro), `/textfile`(ro, 주기 잡 지표) | 필요한 수집기만 |
targets 파일 형식: `metrics.yml` 은 `- targets: ['<서비스>:443']`, `readyz.yml`/`public.yml`/`gate.yml` 은 `- targets: ['https://<서비스>/readyz']`.

## backup-store (uid 65534, ADR 0011)
- 마운트: `/run/tls/tls.crt`·`tls.key`(ro), `/run/secrets/areas/<영역>`(ro, 영역마다 한 파일, 내용 한 줄 `<영역>:<암호>`, 파일 이름 = 사용자 이름), `/data`(rw 볼륨, 소유자 65534), `/tmp`(tmpfs).
- 환경(선택): `OPENIT_BACKUP_PORT`(기본 8000). 영역 게이트웨이 출구가 `backup-store:443` 만 허용하므로 배치는 포트 443(또는 443 으로 매핑)과 서비스 이름 `backup-store` 인증서를 준다. 영역의 `OPENIT_BACKUP_URL` 은 `https://backup-store/<영역>`.
- 자격·TLS 가 없으면 종료 코드 2 로 시작하지 않는다.

## step-ca (uid 1000 `step`, ADR 0012)
| 부명령 | 마운트 | 환경 |
|---|---|---|
| `serve`(기본) | `/home/step`(rw 볼륨, 키 있음, 소유자 1000), `/run/secrets/step-ca-password`(ro), `/tmp` tmpfs **exec 허용** | `STEP_CA_PORT`(9000) `STEP_CA_DNS_NAMES`(공백 구분) |
| `root` | `/home/step`(ro, CA 볼륨), `/out`(rw) | `PKI_OUT` |
| `token <이름>...` | `/tokens`(rw), `/etc/openit/pki/root_ca.crt`(ro), `/run/secrets/step-ca-password`(ro), `/tmp` | `STEP_CA_URL`(기본 `https://step-ca:$PORT`) |
| `cert <이름>` | `/certs`(rw, 소유자 1000), `/tokens`(ro), `/etc/openit/pki`(ro), `/tmp` | `STEP_CERT_NOT_AFTER` `STEP_RENEW_EXPIRES_IN`(기본 12h) |
HEALTHCHECK 는 이미지에 있다(CA 는 `step ca health`, 인증서 컨테이너는 만료 포함 검증).
