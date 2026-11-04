#!/usr/bin/env python3
"""기기 토큰 폴더(계약 PublicIngressEnv.INGRESS_DEVICE_TOKENS_DIR)에서 Caddy 조각 devices.caddy 를 만든다: 기기마다 파일 하나, 파일 이름 = device_id(PUBLIC_API F절 패턴), 내용 = 토큰 한 줄(비밀 D84).
폴더가 없거나 비어 있으면 모든 기기 토큰을 거부한다(0개도 유효). 파일을 지우고 다시 시작하면 그 기기는 폐기된다(Caddy 는 설정을 읽을 때 한 번 치환한다).
출력: Caddy 조각(표준 출력, 토큰 값이 들어 있다: 호출자가 0600 으로 쓴다). 이름·형식이 어긋나면 종료 65(값은 출력하지 않는다).
사용: gen-devices.py <폴더>"""
import pathlib, re, sys

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")   # PUBLIC_API F절 device_id
TOKEN = re.compile(r"^[A-Za-z0-9._~+/=-]{16,512}$")        # 토큰 한 줄(RFC 6750 b64token 문자). 따옴표·공백이 있으면 Caddy 식을 깰 수 있어 거부한다


def main(d):
    vals = []
    p = pathlib.Path(d)
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.name.startswith(".") or not f.is_file():   # ..data 같은 마운트 내부 항목은 기기가 아니다
                continue
            if not ID.match(f.name):
                sys.exit(f"기기 토큰 파일 이름이 device_id 형식이 아니다: {f.name}")
            tok = f.read_text(encoding="utf-8").strip()
            if not TOKEN.match(tok):
                sys.exit(f"기기 토큰 파일 {f.name} 의 내용이 토큰 한 줄 형식이 아니다(값은 출력하지 않는다)")
            vals.append('"Bearer %s"' % tok)
    out = ["# 생성됨(ingress/gen-devices.py): 기기 토큰 목록이라 비밀이다."]
    if vals:
        out += ["(kiosk_devices) {", "\t@device_ok expression {http.request.header.Authorization} in [%s]" % ", ".join(vals), "}"]
    else:
        out += ["(kiosk_devices) {", "\t@device_ok expression false", "}"]
    print("\n".join(out))
    print("기기 %d대" % len(vals), file=sys.stderr)


if len(sys.argv) != 2:
    sys.exit("사용: gen-devices.py <폴더>")
main(sys.argv[1])
