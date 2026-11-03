공개 입구 시험용 Exposure 선언 사본(각 영역 리포의 deploy-exposure.json, 2026-11-04 시점). 제품에서는 deploy 가 각 영역 이미지의 라벨 io.openit.exposure 에서 꺼내 /etc/openit/exposures/ 에 마운트한다. 이 사본은 시험 입력이고 정본이 아니다.
synthetic-data.json 은 뺐다: 그 선언이 /readyz 를 survey-service 와 같이 열어 공개 입구가 시작을 거부한다(같은 공개 경로를 두 영역이 열 수 없다). 영역 쪽 선언 수정이 필요하다(헤드에 알림).
