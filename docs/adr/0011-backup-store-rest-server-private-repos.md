# 0011. 백업 저장소: restic rest-server, --private-repos, append-only 없음

## 상태
채택(헤드 결정 2026-11-04; 계약 RUNTIME R10.1, CommonEnv OPENIT_BACKUP_URL·CREDENTIALS_FILE·REPO_PASSWORD_FILE). 측정하지 않은 값은 "측정 안 함".

## 맥락
영역은 자기 데이터를 꺼내 자기 영역 게이트웨이 출구(`external:backup`)로 이 저장소에 restic REST 프로토콜(https)로 보낸다. 영역마다 저장 경로·자격이 다르다. 영역 백업 잡이 백업 직후 `restic forget --prune` 으로 보존 상한을 지킨다(ops-feedback ADR 0032).

## 결정
- `restic/rest-server`(digest 고정)를 `--private-repos`, HTTPS 전용, HTTP 기본 인증(RFC 7617)으로 실행한다. 사용자 이름이 저장소 첫 경로 조각이므로 영역은 `/<영역>/…` 만 쓸 수 있다.
- `--append-only` 는 켜지 않는다: 켜면 영역의 `forget --prune` 이 403 으로 실패해 보존 상한을 지킬 수 없다. 대신 영역 사이 격리는 private-repos 와 영역별 자격이 맡는다.
- 자격은 영역마다 파일 하나(`/run/secrets/areas/<영역>`, 한 줄 `<영역>:<암호>` = 그 영역의 `OPENIT_BACKUP_CREDENTIALS_FILE` 과 같은 모양). 진입점이 시작 때 bcrypt htpasswd 를 `/tmp`(tmpfs)에 만든다. 자격이 하나도 없거나 TLS 가 없으면 시작하지 않는다(종료 2). 암호는 출력하지 않는다.
- restic 저장소 암호(`OPENIT_BACKUP_REPO_PASSWORD_FILE`)는 서버가 모른다: 데이터는 클라이언트에서 암호화된다.

## 왜
rest-server 문서의 `--private-repos` 가 사용자별 저장소 격리의 표준 방식이다. 시험(`tests/test_backup_store.py`)이 실제 restic 으로 왕복·`forget --prune` 성공·남의 경로 거부(rest-server 는 401 로 답한다: 측정함)를 확인했고, `--private-repos` 를 뺀 변이에서는 남의 경로가 열린다.

## 검토한 대안과 버리는 이유
- append-only: 위 이유(영역 보존 정리가 막힌다). 대신 감수하는 것: 탈취된 영역 자격으로 그 영역 자신의 백업을 지울 수 있다(다른 영역 것은 못 지운다).
- 영역마다 rest-server 인스턴스: 격리는 강하나 포트·인증서·볼륨이 영역 수만큼 늘어난다.
- S3 호환(MinIO 등): 계약이 restic REST 로 고정되어 있다.

## 결과
얻는 것: 한 프로세스, 영역별 격리, 보존 정리 가능. 감수하는 것: 위 자격 탈취 시 자기 백업 삭제.

## 되돌리는 조건
영역이 보존 정리를 저장소 쪽 관리 작업으로 옮기면 append-only 를 켠다(새 ADR 로 대체).
