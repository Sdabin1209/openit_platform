# 컴포넌트 배포 입력 (monitoring, backup-store, step-ca 등)

환경 변수의 이름·기본값은 계약 Env 스키마가 정본이다(`docs/boundary.md` 의 "이미지 입력" 절). 이 문서는 마운트·역할 같은 스키마 밖의 운영 사실만 적는다. 아래 환경 변수 표기는 설명용이다.

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

## public-ingress 자체 점검 명령
`selfcheck-unauth <https://주소:포트> --cacert 파일`: 인자·종료 코드·기대 행은 `docs/boundary.md` 의 "공개 입구 자체 점검 명령" 절. 선언 폴더(`/etc/openit/exposures`)는 공개 입구를 띄울 때와 같은 것을 마운트한다.

## 상태 폴더는 이미지가 VOLUME 으로 선언한다
배치는 `docker image inspect` 의 `Config.Volumes` 를 읽어 마운트하고 경로를 따로 알지 않는다: step-ca `/home/step`·`/tokens`·`/certs`, monitoring `/prometheus`·`/alertmanager`, backup-store `/data`, public-ingress `/data`(internal 모드의 사설 CA)·`/config`, identity-db `/var/lib/postgresql/data`(공식 postgres 선언 그대로). 시험: `tests/test_env_contract.py::test_state_folders_are_declared_as_docker_volumes`.

## 공개 입구의 사설 CA 를 믿는 길 (`export-root`)
`docker run --rm --volumes-from <공개 입구 컨테이너> -v <출력 폴더>:/out --user 10001:10001 <public-ingress 이미지> export-root /out` → `/out/root_ca.crt`(공개 인증서). 루트는 internal 모드 첫 기동 때 `/data` 에 생기므로 같은 `/data` 볼륨을 써야 한다(없으면 종료 1). 감시는 이 파일을 step-ca 루트와 이어 붙인 한 파일(여러 PEM 허용)을 `MONITORING_ROOT_CA` 로 받는다. 시험: `ingress/tests/test-gateway-auth.sh`(내보낸 루트로 인증서 검증), `tests/test_env_contract.py`(이어 붙인 묶음 수용·쓰레기 거부).

## monitoring node 역할의 입력 (스키마 밖의 마운트)
`node`: `/host`(호스트 `/` 읽기 전용: 파일시스템·시계 수집), `/textfile`(읽기 전용: 주기 잡이 쓴 지표 파일). 환경 변수는 없다.

## export-root 의 출력 폴더
`export-root <폴더>` 는 쓸 수 있는 아무 폴더나 받는다(예: 이미지 VOLUME 인 `/config`). 별도 입력 변수나 VOLUME 은 만들지 않았다(폴더는 부명령의 인자라 환경 스키마에 없다).
