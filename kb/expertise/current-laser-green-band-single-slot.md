---
id: current-laser-green-band-single-slot
question: "current-laser 스코프(LUN-F-XL + CSU-W1)에서 여기 488nm·방출
  500-530nm대인 다이 두 개를 동시에 구분되는 채널로 볼 수 있는가"
source: calculation
expert: KH
date: 2026-08-10
confidence: high
scope: "config/scopes/current-laser.yaml — LUN-F-XL 4라인(405/488/561/640) +
  EM1 필터휠 + 561nm 기준 듀얼카메라 스플리터(DM A561LP)"
applies_to_systems: [current-laser]
review_after: 2027-08-10
supersedes: null
---

## 판단
불가능하다. `optics.cli recommend`로 계산하면 FITC와 YOYO-1(dsDNA 결합형,
둘 다 em_peak 500-530nm대)은 최적 (라인, 필터, 카메라) 조합이
488nm / EM1-525/36 / Kinetix_blue로 완전히 동일하게 나온다 — 물리적으로
같은 채널이라 crosstalk가 사실상 100%다. em_peak nm만 눈으로 비교해서
"10nm 차이니 괜찮겠지"라고 판단하면 안 되고, 반드시 recommend로 재계산해야
한다.

## 왜
- 여기 라인이 405/488/561/640 네 개뿐이라, 이 대역 다이는 488 라인만
  실질적으로 쓴다 (405/561/640에서는 여기효율이 0에 가까움 — 실제로
  FITC의 405nm 후보 brightness는 0.0000으로 계산됨)
- EM1 필터휠에 500-530nm대를 담당하는 대역이 EM1-525/36 하나뿐이다
  (88000v2-EM 4-band는 차단 OD가 더 나빠서 순위가 낮음 — 대안이 아님)
- 듀얼카메라 스플리터(DM A561LP)가 561nm 기준이라, 500-530nm 방출은 항상
  반사측(Kinetix_blue) 한 곳에만 간다 — 스플리터로도 못 가른다

## 적용 범위
- config/scopes/current-laser.yaml 스코프에 한정 (다른 스코프/광원 조합은
  재계산 필요)
- em_peak가 대략 495-530nm에 들어오는 다이 쌍 전체에 적용될 것으로 예상됨
  (FITC/YOYO-1로 확인, 예: AlexaFluor488 + EGFP 조합도 같은 이유로 충돌할
  가능성이 높음 — 개별 재계산 권장, 이 엔트리가 자동으로 보증하지 않음)
- 라인 자체가 다른 다이(예: 405 전용 다이)나 순차(시간분할) 촬영에는
  적용되지 않음 — 이 판단은 "동시" 관찰에만 해당

## 반증 조건
이 판단은 파라메트릭(peak_nm + FWHM) 근사 스펙트럼 기반이다
(evidence: assumed — data/fluorophores.yaml에 FITC/YOYO-1 실측 curves가
연결돼 있지 않음, data/spectra/README.md 참고). 다음 중 하나라도 관찰되면
재검토 대상이다:

1. FITC와 YOYO-1(dsDNA 결합형)의 실측 흡수/방출 곡선을 data/spectra/에
   추가하고 fluorophores.yaml의 `curves:`로 연결해 재계산했는데, 최적
   (라인, 필터, 카메라) 조합이 지금과 달라진다
2. EM1(또는 EM2) 필터휠에 500-530nm대를 나누는 필터가 새로 추가된다
   (예: 510/20 같은 좁은 대역)
3. 듀얼카메라 스플리터가 561nm이 아니라 이 대역(495-530nm) 안에서 나누는
   파장(예: 510nm)으로 교체된다

## 관련
[[fitc-yoyo1-channel-conflict]] (에이전트 메모리) ·
kb/decisions/2026-08-10_fitc-particle-yoyo1-dna-2color.md ·
config/channels/particle647-yoyo1-2color.yaml
