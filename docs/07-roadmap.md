# 07 · 로드맵

> **상태: 스케치.** 단계 순서와 선행조건은 확정 제안, 일정은 없음.

원칙 하나: **각 단계는 그 자체로 쓸모가 있어야 한다.** 전부 끝나야 쓸 수 있는
설계는 끝나지 않는다.

---

## Phase 0 · 근거 확보 — 지금 여기

지금 막혀 있는 것은 코드가 아니라 **사실**이다. 게이트는 이미 동작하고,
계산할 입력이 없어서 `BLOCKED`을 낼 뿐이다.

| 할 일 | 산출 | 비용 | 상태 |
|---|---|---|---|
| 현재 시스템 MM `.cfg` | `kb/systems/current.md` | — | ✅ 확보 (2026-07-03) |
| ↳ `Label,` 줄 확인 | 필터 휠·터렛 위치 이름 | — | ✅ 완료 |
| NIS-Elements 장치 목록 | 3자 대조표 [02 §4] | — | ✅ 완료 (2026-08-11). EM1/EM2 카메라 배정(EM1=Kinetix_red/EM2=Kinetix_blue) 확정, EM2 필터 구성 독립 확인, DM=CSUW1-Dichroic·CSUW1-Filter_Red/Blue=EM1/EM2 중복 병합, FilterTurret2·CondenserTurret·DMD 물리연결까지 전부 해소 — kb/systems/current.md 참고 |
| 필터 휠 위치별 부품 | `data/filters.yaml` | — | 확보 |
| 형광 염료 정보 | `data/fluorophores.yaml` | — | 확보 |
| 대물렌즈 실물 각인 | NA·WD·커버글라스 | 10분 | ✅ 완료 (2026-08-11) — 카탈로그 대조(2026-08-10) + 경통 실측 대조(2026-08-11) 사용자 확인 |
| **조명 광량 실측** | `power_at_sample_mw` | 30분 | **최대 효과, 남은 유일한 최우선 블로커** — 파워미터 실측, 추후 진행 예정 |
| 픽셀 크기 실측 교정 | `ConfigPixelSize` (MM2에 등록) | 30분 | ✅ 확보 (Kinetix, 2025-04) |
| 디스크 지속쓰기 대역폭 | `kb/calibrations/disk-bandwidth.yaml` | 10분 | ✅ 확보 (2026-08-12) — D: 드라이브 206.8 MB/s (4GB 실측). MM 실제 저장 폴더와 정확히 일치하는지는 미확인 — 다르면 재측정 |
| 카메라 행 시간 | `ReadoutTimeNs / ROI높이` | 5분 | ✅ 확보 (2026-08-12) — `kb/calibrations/camera-readout.yaml`. 실제 PVCAM 어댑터 property `Timing-ReadoutTimeNs` = 8,475,000 (name상 ns로 강하게 추정, 문서 대조는 아직 안 됨) → row time ≈ 3531.2 ns/row (ROI height 2400 rows 기준). `DMD_dualcam.cfg`가 아니라 `dual_cam_test.cfg`(PVCAM만, NikonTi2/Mightex 없음)로 로드 — 이유는 아래 노트 참고 |

**광량 실측이 가장 큰 잠금 해제다.** 그거 하나로 절대 광자수지가 열리고,
노출시간을 처음부터 계산해줄 수 있게 되며, 앞으로의 모든 데이터가
다른 시스템으로 이전 가능해진다. → [03 §5](03-cross-system-transfer.md)

**하드웨어 연결 시 실행할 코드는 [`calibration/`](../calibration/)에 준비됨**
(디스크 대역폭, 카메라 행 시간, EM1/EM2 카메라 판별) — 조명 광량만 코드로
대체 안 됨(파워미터 실측 필요). `calibration.disk_bandwidth`는 하드웨어
무관, 테스트 4개. `calibration.mm_live`(카메라 행 시간·EM 판별)는
pymmcore-plus 필요, 데모카메라로 테스트 4개 통과 — **2026-08-12: 실제
PVCAM 어댑터로도 확인 완료**(위 표 참고).

**2026-08-12 환경 노트**: `mmcore install`로 받은 pymmcore-plus 자체 MM
빌드(interface v75)는 `Ti2_Mic_Driver.dll`(Nikon 벤더 SDK, 배포판에 안
들어있음)이 없어 `NikonTi2` 어댑터 로드가 막혀 있었다 — 랩의 기존 설치
(`C:\Program Files\Micro-Manager-2.0`)에서 그 DLL만 복사해 해소, 이제
`DMD_dualcam.cfg`의 DMD(`MightexPolygon1000`)를 뺀 나머지 전체 장치
(스탠드·CSU-W1·EM1/EM2·카메라·광원)가 pymmcore-plus로 한 번에 로드된다.
DMD 자체는 여전히 안 됨 — 그 벤더 지원 패키지가 interface v71 고정이라
v75 코어와 안 맞음(별개 미해결 과제, 급하지 않음).

**검증**: `python -m optics.cli check <현재시스템 채널>` 이
`BLOCKED`가 아니라 `advances: YES`를 낸다.

---

## Phase 1 · 계산 렌즈 완성

전부 순수 계산이라 하드웨어 없이 개발·테스트 가능하다.
식은 [04](04-decision-engine.md)에 이미 정리되어 있다.

| 렌즈 | 게이트 | 선행 | 산출 |
|---|---|---|---|
| 1 광학계 | G1–G4 | — | ✅ **완료** (26 tests) |
| 2 검출계 | G5 G6 G7 G8 G9 | 카메라 스펙, 행 시간 | ✅ **완료**(2026-08-11, `detection/`, 33 tests) — 렌즈 1과 같은 전체 스키마(`feasibility` 포함) |
| 3 전산자원 | G12 G13 | 디스크 대역폭 실측 | ✅ **완료**(2026-08-11, `compute/`, 19 tests) |
| 7 광집게 | G14 | — | ✅ **게이트 연결 완료**(2026-08-10, `trapping/`, 42 tests) — 남은 건 실측 캘리브레이션뿐 |

렌즈 2·3·7 전부 렌즈 1과 **같은 스키마**를 쓴다: `Check` / `CheckResult(margin)` /
`Verdict(status, evidence, advances)` (각 렌즈의 `checks.py`/`gate.py`).
렌즈 2(`detection/`)·렌즈 3(`compute/`)은 `feasibility` 등급까지 포함한
렌즈 1의 전체 스키마를 그대로 쓴다(2026-08-11). 렌즈 7만 아직 `feasibility`가
없음(렌즈 1보다 체크 종류가 적어서 grade table을 쓸 근거가 부족) — 렌즈 7에
언젠가 SOFT/BIAS 성격의 체크가 추가되면 그때 같이 볼 것.
`python -m trapping.cli check --dial 100` / `python -m detection.cli check ...` /
`python -m compute.cli check ...`로 각각 확인 가능. → [08 §0](08-optical-path-spec.md)

렌즈 7의 남은 갭(2026-08-10 기준): 다이얼%→mW **실측** 캘리브레이션 포인트
없음(`LaserCalibration.points`가 비어 있어 evidence가 항상 assumed로 나옴),
매질 점성은 물 기준 온도-보간 표만 있고 ATPS 등 다른 매질은 미지원, G14의
`f_s ≥ 10·f_c` 비교는 `--detector-fps` 파라미터로만 선택적으로 검증
가능(안 주면 정보성 안내만 출력, 전체 판정을 막지 않음). 렌즈 2(`detection/`,
2026-08-11)가 이제 실현 프레임레이트(`check_frame_rate`의 `max_fps`)를
계산하지만, 아직 두 CLI가 자동으로 엮여있지는 않다 — 사람이 렌즈 2 출력을
읽어 `trapping.cli check --detector-fps`에 손으로 넣어야 한다. 자동 연결은
Phase 3(위원회 오케스트레이션) 몫.

추가로:
- **난이도 등급 + 민감도 분석** ([05 §3–4](05-consensus-gate.md))
  — 렌즈 1에 margin은 이미 들어갔고, `data/interventions.yaml`과
  개선 랭킹이 남았다
- **광집게 중간영역 처리** — `a/λ ~ 1`이면 Rayleigh도 광선광학도 무효.
  근사식으로 답하지 않고 `BLOCKED`
- **ℓ_c 회절한계 게이트** (신규, 2026-08-12) — `kb/samples/<system>.md`의
  `characteristic_scales.length`가 `σ_PSF`보다 작으면 표본화가 통과해도
  구조를 직접 분해할 수 없다는 뜻. 지금 렌즈 2(G5)에 없는 체크.
  → [04 §2](04-decision-engine.md)

**검증**: 실제로 찍었던 조건을 입력하면 게이트가 그때의 문제
(647 노출 500 ms, duty 88%, despeckle)를 스스로 지적한다.

---

## Phase 2 · 지식베이스 구축

| 할 일 | 산출 |
|---|---|
| MM 메타데이터 인덱서 (1.4 + 2.0) | `kb/envelope.sqlite`, 2,343건 |
| 시스템 지문 → 세대 자동 분류 | `system_id` |
| 폴더명 파서 | `name_*` 컬럼 |
| tail 파싱 → `measured_fps`, 드랍 검출 | **요청값이 아닌 실측값** |
| 사이드카 스키마 + 생성기 | `acquisition.yaml` |
| 시료계 레시피 초안 | `kb/samples/*.md` (이제 `characteristic_scales`(τ_c, ℓ_c) 필드 필수 → [02 §8](02-knowledge-base.md)) |

**첫 부산물**: 아카이브 전체에 드랍 검출을 돌려서 어떤 세션이 오염되었는지
목록화한다. 이건 새 실험 없이 지금 당장 가치가 나온다.

**검증**: "ATPS에서 647로 추적한 선례 보여줘" → SQL로 나오고,
각 선례의 물리량과 알려진 결함이 함께 나온다.

---

## Phase 3 · 에이전트 층

여기서 비로소 "챗봇"이 된다.

```
D:\experimentalist\
├── CLAUDE.md                      항상 로드되는 운영 지침
└── .claude\
    ├── skills\
    │   ├── scope-setup\           설정 추천 (주 워크플로)
    │   ├── knowledge-capture\     전문성 포착 [09]
    │   └── system-onboard\        새 .cfg 수령 시 KB 구축
    └── agents\
        ├── sample-optics.md       렌즈 4
        ├── photo-perturbation.md  렌즈 5
        ├── measurement-validity.md 렌즈 6
        └── mechanical-env.md      렌즈 8
```

- 계산 렌즈(1·2·3·7)는 코드로 먼저 돌리고, **그 결과를 판단 렌즈의 입력으로 준다.**
  LLM이 숫자를 스스로 만들지 않는다
- 위원회 오케스트레이션 + 교착 처리 ([05 §6](05-consensus-gate.md))
- 전문성 포착 루프 ([09 §3](09-knowledge-capture.md))
- 교육 모드 ([09 §5](09-knowledge-capture.md))

**검증**: 후배가 "ATPS 647 추적하고 싶어요"라고 말하면 —
질문 → 계산 → 위원회 → 난이도 등급 → 설정안 + 근거 + 실패 신호가 나온다.

---

## Phase 4 · 실험 기획

설정에서 실험 설계로 올라간다. 위원회가 하나 더 붙는다:
**실험 기획 관점** (가설 → 측정량 → 필요 정밀도 → 통계 설계).

계통별 위원회는 "이 설정이 되는가"를 묻고, 기획 위원회는
"이 실험이 질문에 답하는가"를 묻는다. 단계가 다르므로 게이트도 따로 둔다.

- **τ_c·ℓ_c 확보** (측정 우선, 없으면 이론 추정 + `evidence: assumed`) —
  이 위원회의 첫 동작이자 계통별 위원회의 입력. `kb/samples/*.md`의
  `characteristic_scales`에 기록 → [04 §1](04-decision-engine.md) ①'
- 대조군·반복수 설계
- 측정량 → 필요 정밀도 역산
- `D:\codes`의 분석 파이프라인과 연결 (렌즈 6이 이미 참조)
- 프로토콜 문서 생성

---

## Phase 5 · 현미경 조작 자동화

**Phase 0–3이 끝나기 전에는 시작하지 않는다.** 검증되지 않은 설정을
자동으로 밀어넣는 것은 위험하다.

**사실 확인(2026-08-10)**: 이 dossier에 등장하는 장비(현미경 스탠드·컨포칼·
광원/레이저·DMD·광집게·피에조 스테이지) 전부 Python 제어가 가능함이
사용자 구술로 확인됨 — 이 Phase를 시작해도 될지에 대한 전제 하나는 풀렸다.

**제어 인터페이스 결정 (2026-08-11)**: 이 프로젝트는 **NIS-Elements 제어
경로를 쓰지 않는다** — MM에 등록된 장치는 전부 pymmcore-plus로만 제어.
DMD(MightexPolygon1000)는 마이크로스코프 PC에서 MM `.cfg` 실측으로
등록을 직접 확인했다(`kb/systems/current.md > dmd`). LUN-F-XL 레이저
콤바이너·CSUW1-Dichroic/Splitter/EM1처럼 MM에 등록되지 않고 이전에
"NIS-Elements 전용"으로 기록됐던 장치들은, 이 결정에 따라 NIS 경로로
갈 수 없으므로 **pymmcore-plus로 어떻게 닿을지(직접 SDK/시리얼 등 별도
경로 필요)가 새로운 과제**로 남는다 — 착수 시점은 여전히 Phase 0–3
완료 이후다.

단계적으로:

| 단계 | 범위 | 안전장치 |
|---|---|---|
| 5a | 상태 **읽기** (pymmcore-plus) | 하드웨어 불변 |
| 5b | 추천 vs 현재 상태 **비교** 표시 | 〃 |
| 5c | MM ConfigGroup 프리셋 **생성** (적용 안 함) | 사람이 적용 |
| 5d | 사람 확인 후 **적용** | 확인 필수 · 되돌리기 |
| 5e | 획득 실행 + 실시간 게이트 감시 | 이상 시 중단 |

MM2 확정이므로 `.cfg` ↔ 프리셋 왕복이 계획대로 가능하다.
→ [08 §7](08-optical-path-spec.md)

**피에조**는 MM 밖이므로 별도 경로가 필요하다. 자동화에 포함하려면
(a) MM 장치로 등록하거나 (b) 별도 프로그램과 연동하거나
(c) 수동 단계로 남기고 사이드카에 기록한다. (c)가 기본값이다.

---

## 의존 관계

```
Phase 0 (사실)  ─────┬─────────────────────────▶ 모든 것의 전제
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
Phase 1 (계산 렌즈)        Phase 2 (지식베이스)
   └─ 하드웨어 없이            └─ 아카이브만으로 가능,
      개발 가능                   지금 시작해도 됨
        │                         │
        └────────────┬────────────┘
                     ▼
              Phase 3 (에이전트)
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
  Phase 4 (기획)          Phase 5 (조작 자동화)
```

**Phase 1과 2는 병렬 가능하고, 둘 다 Phase 0 없이도 상당 부분 진행된다.**
지금 당장 할 수 있는 것: 렌즈 2·3 구현, 아카이브 인덱서, 드랍 검출.

---

## 지금 당장 가치가 나오는 것 셋

Phase 0가 끝나기 전에도 할 수 있고, 각각 독립적으로 쓸모가 있다.

1. **아카이브 드랍 검출** — `ElapsedTime` 차분으로 오염된 세션 목록화.
   기존 분석 결과의 신뢰도를 바로 재평가할 수 있다
2. **despeckle 영향 평가** — 후처리가 켜진 데이터가 정량 분석에
   실제로 얼마나 영향을 줬는지 확인
3. **duty cycle 감사** — 마이크로레올로지 세션의 모션블러 편향을
   Savin-Doyle로 소급 보정 가능한지 판정
