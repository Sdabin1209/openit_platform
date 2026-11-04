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

## 공개 입구의 사설 CA 를 믿는 길 (루트 내보내기, 계약 3.4.16)
internal 모드의 공개 입구는 자기 사설 CA 의 루트 인증서(공개)를 `INGRESS_ROOT_EXPORT_DIR`(기본 `/etc/openit/root-out`, deploy 가 연결하는 쓰기 가능한 출력 마운트)에 `root_ca.crt` 로 쓴다 — 루트가 생기거나 바뀔 때마다 같은 폴더에 쓰고 `rename` 으로 바꿔 넣는다(5초 주기로 확인, 측정하지 않은 값). 폴더에 쓸 수 없으면 시작하지 않는다(종료 64). 부명령이나 이미지 안 경로에 기대지 않는다. 감시는 이 파일을 step-ca 루트와 이어 붙인 한 파일(여러 PEM 허용)을 `MONITORING_ROOT_CA` 로 받는다. 시험: `ingress/tests/test-gateway-auth.sh`(내보낸 루트로 인증서 검증, 쓸 수 없는 폴더는 종료 64), `tests/test_env_contract.py`.

## monitoring node 역할의 입력 (스키마 밖의 마운트)
`node`: `/host`(호스트 `/` 읽기 전용: 파일시스템·시계 수집), `/textfile`(읽기 전용: 주기 잡이 쓴 지표 파일). 환경 변수는 없다.

## export-root 의 출력 폴더
`export-root <폴더>` 는 쓸 수 있는 아무 폴더나 받는다(예: 이미지 VOLUME 인 `/config`). 별도 입력 변수나 VOLUME 은 만들지 않았다(폴더는 부명령의 인자라 환경 스키마에 없다).


## 이미지가 내는 잡 (라벨 io.openit.jobs, JobsDeclaration, 계약 3.4.16)
정본은 `<서비스 폴더>/jobs-<서비스>.json` 이고 `scripts/build-image.sh` 가 계약 validator 로 검증해 라벨에 넣는다.
| 이미지 | 잡 | 하는 일 | 설정 파일 | needs |
|---|---|---|---|---|
| identity | `register-users` | realm openit 에 사용자와 역할 그룹을 만들고 이미 있으면 같은 상태로 맞춘다(멱등). `enabled:false` 는 그룹 없는 승인 대기 | `/etc/openit/identity-users.json` (IdentityUsersConfig) | - |
| public-ingress | `gateway-backup` / `gateway-restore` | `/data`(gateway-data) 를 백업 저장소로 백업 / 되돌림 | - | gateway-data |
| step-ca | `pki-backup` / `pki-restore` | `$STEP_CA_HOME`(pki-ca) 를 백업 / 되돌림. 저장소 인증서는 밖에서 준 `/etc/openit/pki/root_ca.crt` 로 검증 | - | pki-ca |
백업·복구 잡: 입력은 CommonEnv(`OPENIT_BACKUP_URL`, `OPENIT_BACKUP_CREDENTIALS_FILE`, `OPENIT_BACKUP_REPO_PASSWORD_FILE`)와 잡의 `env` 목록. 결과는 표준 출력 마지막 줄 BackupJobResult, 종료 코드 0 ok / 75 재시도 가능 / 1 실패. 스냅숏에 태그(`gateway-data`, `pki-ca`)를 붙여 같은 저장소를 나눠 쓴다. 백업 저장소가 platform 안이라 영역 안 통신이다(영역 게이트웨이 출구를 거치지 않는다). 한계: 실행 중인 서비스의 폴더를 파일 단위로 복사한다(스냅숏 도중 쓰기는 다음 스냅숏에 들어간다).


## 역할은 Env 로, 상태 확인은 이미지가 (계약 3.4.17, CONVENTIONS 13절)
deploy 는 이미지 부명령·`command`·`entrypoint`·`healthcheck`·`user` 를 쓰지 않는다. 이미지가 자기 실행 명령, `HEALTHCHECK`, `USER` 를 갖는다.
- monitoring: 역할은 `MONITORING_ROLE`(prometheus|alertmanager|blackbox|json|node), 없거나 모르는 값이면 종료 64. HEALTHCHECK = 역할의 HTTP 상태 경로(prometheus·alertmanager·blackbox `/-/healthy`, json·node `/`).
- step-ca: 역할은 `STEP_ROLE`(serve|root|token|cert, 기본 serve). cert 는 `STEP_CERT_NAME`, token 은 `STEP_TOKEN_NAMES`(공백 구분)를 읽고 없으면 종료 64. cert 의 키 파일은 0640, 그룹 `STEP_CERT_GID`(기본 10100: 이미지의 step 사용자가 이 그룹 구성원), 인증서는 0644 — 갱신 데몬이 파일을 바꾼 뒤 `--exec` 로 다시 맞춘다(바꾼 직후 잠깐은 키가 0600 일 수 있다). 다른 gid 는 deploy 의 `group_add` 로 보조 그룹을 받는다. HEALTHCHECK = serve: CA 응답(`step ca health`), cert: 만료를 포함한 검증, root: 루트 파일이 있음, token: 이름마다 토큰 파일이 있음.
- area-gateway: 출구(loopback)·들어오는 포트가 TCP 를 받는지. backup-store: 저장소 포트가 TCP 를 받는지. public-ingress: 평문 루프백 `/healthz` 200 + `{"status":"ok"}`. identity: 관리 포트의 `/auth/health/ready` UP. identity-proxy: `/ping`. identity-db: 선언 계정으로 TLS 접속(앞 절).
- 간격·재시도·시작 유예 값은 측정하지 않은 값이다(Dockerfile 주석).
