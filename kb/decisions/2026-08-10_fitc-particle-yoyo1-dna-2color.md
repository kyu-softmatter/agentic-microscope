# 2026-08-10 · FITC 입자 + YOYO-1 DNA 동시 2-color 설계

## 요구
FITC로 코팅된 입자와 YOYO-1로 표지한 DNA를 현재 시스템
(current-laser 스코프, CSU-W1 스피닝디스크 + LUN-F-XL 레이저)에서
동시에(한 프레임에서 구분되는 채널로) 보고 싶다.

## 제안한 설정 + 근거 (게이트 출력 요약)
- 1차 계산 `optics.cli recommend config/scopes/current-laser.yaml --dyes FITC,YOYO1`:
  두 다이 모두 최적 조합이 488nm / EM1-525/36 / Kinetix_blue로 완전히
  동일하게 나옴 → 물리적으로 같은 채널, crosstalk 사실상 100%. 이 조합
  으로는 동시 2-color 불가능 (→ [[current-laser-green-band-single-slot]]).
- `--panel --lines 488,405`으로 강제 배정해도 FITC의 405nm 후보 밝기가
  0.0000 — 여기 자체가 안 됨. 진짜 해법 아님.
- 대안 탐색: 입자 라벨을 647-class 빨강으로 교체.
  `optics.cli recommend --dyes YOYO1,ATTO647N --panel --lines 488,640`:
  YOYO1(488/EM1-525/36/Kinetix_blue) + ATTO647N류(640/EM1-705/72/Kinetix_red),
  crosstalk margin 10.0으로 계산됨 — 물리적으로 분리됨.
  (동등한 대안: FITC 유지 + DNA염색을 SYTO61(628/645nm)로 교체해도 같은
  margin이 나옴 — 어느 쪽 라벨을 바꿀지는 시약 확보 편의에 따라 선택.)
- 채널 정의 파일: config/channels/particle647-yoyo1-2color.yaml
  (dye: ATTO647N은 예시 — 실제 입자 컨쥬게이트 이름으로 교체 필요)
- 두 채널 다 grade `HARD`(margin 0.87, PASS 아님) — evidence가 assumed
  (파라메트릭 스펙트럼)라 차단요구가 7 OD로 올라가는데 실측 없이는 6.1 OD
  근사치만 나옴. 진행 가능하나 재현성 낮음.
- `optics.cli check` 최종 실행 결과는 **BLOCKED** — Kinetix는
  data/detectors.yaml에 등록은 돼 있으나 `read_noise_e`가 카메라 모드
  (Speed 2.0e-/Sensitivity 1.2e-/DynamicRange 1.6e-) 미확정이라 null,
  `full_well_e`/`dark_e_per_s`는 데이터시트 자체에 값이 없음. 어느 모드를
  쓰는지 확정 전까지 SNR·새추레이션 계산 불가.

## 실제로 쓴 설정 (다르면 왜)
TBD — 아직 실험 전. 실행하면 이 항목을 채울 것 (입자 라벨 실제 교체
여부, 어느 647-class 다이를 썼는지, Kinetix 모드 등).

## 결과
TBD.

## 배운 것 → 어느 파일을 고쳤나
- 그린밴드(495-530nm) 다이 쌍은 이 스코프에서 항상 같은 채널로 계산됨
  → 일반 규칙으로 정리해 kb/expertise/current-laser-green-band-single-slot.md 신규 작성.
- config/channels/particle647-yoyo1-2color.yaml 신규 작성 (입자=647-class, DNA=YOYO1).
- Kinetix 카메라 모드 미확정이 모든 채널의 `check`를 막는다는 사실 확인
  → docs/02-knowledge-base.md §10 열린 질문에 추가.

## 관련
[[current-laser-green-band-single-slot]] · config/scopes/current-laser.yaml ·
config/channels/particle647-yoyo1-2color.yaml
