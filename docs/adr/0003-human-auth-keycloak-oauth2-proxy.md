# 0003 사람 인증: Keycloak + oauth2-proxy

- 상태: 채택(deploy 의 U82 결정을 이 영역으로 옮김)
- 맥락: 사람 계정·가입 승인·역할이 필요하다. 계약은 로그인 세션 경로(R3.23)와 역할 판정(R3.24)을 정한다.
- 결정: Keycloak(realm `openit`, 그룹 = 역할)이 계정을, oauth2-proxy 가 OIDC 클라이언트·쿠키 세션을, 공개 입구가 `forward_auth` 로 판정한다. 둘 다 공식 이미지를 그대로 쓰고(`locks/images.lock` digest) Keycloak 만 optimized 이미지로 다시 빌드한다(읽기 전용 루트, `identity/keycloak/Dockerfile`). 서비스 TLS 는 영역 게이트웨이 이미지(ADR 0001)가 맡는다. 비밀은 파일(`--config-file`, `*_FILE`).
- 왜: OIDC·forward_auth 는 표준 조합이다. oauth2-proxy 공급자는 `oidc` — `keycloak-oidc` 는 realm 역할을 `role:` 그룹으로 섞어 역할 헤더에 잡음이 들어간다(스모크가 잡음). 쿠키 8h 절대 만료(OWASP Session Management), 5m 새로 고침(Keycloak 액세스 토큰 5분과 맞춤): 측정하지 않았다.
- 대안: 정적 계정 파일 + basic_auth — 가입 승인·역할·로그아웃이 없다(U82 에서 폐기). 
- 결과: 실제 Keycloak 으로 로그인·역할·승인 대기 403·가입 승인·로그아웃을 시험한다(`identity/tests/test-idp-smoke.sh`). 시험용 PKI·비밀은 시험이 만든다.
- 되돌리는 조건: Keycloak 대체 IdP 요구가 생길 때.
