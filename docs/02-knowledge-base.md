# 02 · 지식베이스

> **상태: 스케치.** 스키마와 구조는 확정 제안, 내용은 현재 시스템 `.cfg` 수령 후 채운다.

기존 시스템들에 대한 지식을 **영속적으로** 저장해서 이후 실험 기획·실행에 쓰기 위한
구조. 세 가지를 만족해야 한다: 사람이 열어 고칠 수 있을 것, 에이전트가 질의할 수
있을 것, "왜 이 값인가"를 추적할 수 있을 것.

---

## 1. 저장 구조

```
kb\
├── systems\                    현미경 한 대 = 파일 하나
│   ├── legacy-nikon-prime95b.md      구 셋업 (아카이브 해석용)
│   ├── current.md                    ← .cfg 수령 후 생성
│   └── _template.md
│
├── samples\                    시료계별 이미징 레시피
│   ├── atps-dextran-peg.md
│   ├── actin-network.md
│   ├── liquid-crystal-5cb.md
│   └── active-janus-colloid.md
│
├── decisions\                  추천 → 실행 → 결과 로그 (학습 루프)
│   └── 2026-08-08-atps-647-tracking.md
│
├── calibrations\               실측값. 날짜와 측정자 필수
│   ├── pixel-size.yaml
│   ├── illumination-power.yaml
│   └── disk-bandwidth.yaml
│
└── envelope.sqlite             아카이브 2,343건 정량 인덱스 (생성물)
```

**markdown + SQLite만 쓴다.** 벡터DB를 쓰지 않는 이유: 임베딩 검색은 "왜 이 선례가
선택되었나"를 설명할 수 없고, 잘못된 추천의 원인을 역추적할 수 없다. 선례 검색은
SQL의 명시적 조건(염료·대물·시간스케일·시료계)으로 한다.

---

## 2. 3-tier 정규화

[01 §3 원칙 2](01-architecture.md)의 상세.

| tier | 예시 | 이전 가능성 |
|---|---|---|
| **raw** | `"Spectra-Red_Level": "10"` | — 원본 보존용. 절대 유실 금지 |
| **device** | 광원 `Spectra`, 라인 `Red`, 레벨 10% | 같은 시스템 안에서만 |
| **physical** | 640±15 nm, **? mW/cm² @ sample** | 시스템 무관 — 유일한 이전 매개 |

tier 3 항목과 그 산출 방법:

| 물리량 | 산출식 | 필요 입력 | 현재 |
|---|---|---|---|
| 유효 픽셀 크기 | `p_sensor·B/(M_obj·M_int)` | 센서 피치, 배율 | 계산 가능 |
| 여기 대역 | 광원 라인 × 여기필터 × 다이크로익 | 스펙트럼 곡선 | 부분 |
| 방출 대역 | 다이크로익 × 방출필터 | 스펙트럼 곡선 | **없음** |
| 샘플면 조도 | `P/A` | **파워미터 실측** | **없음** |
| 총 광자 dose | `조도 × t_exp × N_frames` | 위 + 노출 | **없음** |
| 실측 프레임레이트 | `(N−1)/Δt_total` | tail 파싱 | 계산 가능 |
| 수집 입체각 | `(1−cosθ)/2` | NA | NA 미검증 |

**세 항목이 비어서 현재 시스템 간 이전이 불가능하다.** → [03](03-cross-system-transfer.md)

---

## 3. 시스템 dossier

`kb/systems/<id>.md` 한 파일이 현미경 한 대를 기술한다.
YAML front matter(기계 판독) + markdown 본문(사람 판독).

```yaml
---
id: current
status: current            # current | legacy | planned
fingerprint: <장치라벨집합 + 카메라칩/시리얼 해시>
sources:                   # 이 dossier가 무엇에서 파생되었는가
  - {kind: mm_config,  path: ..., date: 2026-08-XX}
  - {kind: nis_export, path: ..., date: 2026-08-XX}
  - {kind: datasheet,  part: ..., }
  - {kind: calibration, path: kb/calibrations/..., date: ...}

stand:      {vendor: Nikon, model: ?, tube_lens_mm: 200, autofocus: PFS}
camera:     {ref: data/detectors.yaml#<key>}
objectives: [{turret: 1, label: ..., mag: ..., na: ..., immersion: ..., verified: false}]
filters:    [{turret: 1, ref: data/filters.yaml#<key>}]
wheels:     [{device: Wheel-A, positions: {0: ..., 1: ...}}]
light:      [{ref: data/light_sources.yaml#<key>}]
magnifiers: [1.0, 1.5]
---
```

본문에는 계산으로 안 나오는 것만 적는다: 알려진 문제, 정렬 이력, 손대면 안 되는 것,
과거 고장, 소모품 교체 주기.

---

## 4. 장치 연결상태 — 3자 대조표

**처음 요청하신 "현미경 하드웨어와 연결상태"가 이것이다.**

같은 현미경에 두 개의 제어 스택(Micro-Manager, NIS-Elements)이 얹혀 있고,
그 어느 쪽에도 없는 장치가 존재한다. 세 가지를 따로 기록해야 한다.

| 장치 | 물리적 존재 | MM 등록 | NIS 등록 | 상태 기록됨 | 제어 주체 |
|---|---|---|---|---|---|
| 카메라 | ✅ | ✅ | ✅ | ✅ | MM |
| 대물 터렛 | ✅ | ✅ | ✅ | ✅ | MM |
| 필터 큐브 터렛 | ✅ | ✅ | ✅ | ⚠ 라벨 뭉개짐 | MM |
| 필터 휠 | ✅ | ✅ | ? | ⚠ **위치 라벨 미등록** → 위치 정보 수령 예정 | MM |
| 광원 | ✅ | ✅ | ? | ✅ | MM |
| PFS | ✅ | ✅ | ✅ | ✅ | MM |
| 중간배율기 1.5x | ✅ | ✅ | ? | ✅ | MM |
| **광집게** | ✅ | ❌ | ❌ | ❌ **폴더명에만** · 출력 실측 예정 | 별도 |
| **피에조 스테이지** | ✅ | ❌ | ❌ | ❌ | **별도 프로그램 예정** |
| DMD | ✅ 2026-08-11 확인 | ❌ | ? | ❌ | ? |

> - **중간배율기**: 현재 시스템에는 MM 장치로 등록되어 있다. 아카이브 세대 C는
>   그 장치가 없는 config로 촬영되어 1.5x가 폴더명에만 남았다 —
>   *장치 등록 여부*와 *그 config로 촬영했는지*는 별개다.
> - **DMD**: `ChNames`에 `DMD_Green` 채널이 2건 있는데 config에 장치가 없다.
>   물리적 존재는 2026-08-11 사용자 확인으로 해소 — MM/NIS 등록 여부·제어
>   주체는 아직 미확인 (kb/systems/current.md > dmd 참고).
> - **MM 버전**: 현재 시스템은 **MM2 확정**. 아카이브의 91%(2,137건)는 MM 1.4.23이므로
>   읽기 전용 레거시 파서가 계속 필요하다.

### 왜 3자 대조가 필요한가

- **MM에 있고 NIS에 없는 것**: NIS로 찍은 데이터에는 그 설정이 안 남는다
- **NIS에 있고 MM에 없는 것**: MM 자동화 대상에서 빠진다
- **둘 다 없는 것**: 어떤 소프트웨어도 기록하지 않는다 → 사람이 적어야 한다
- **둘 다 있는 것**: **동시 접속 충돌** 위험. 한쪽이 장치를 잡고 있으면 다른 쪽이
  실패하거나, 더 나쁘게는 조용히 잘못된 상태로 진행한다

### 대조 절차 (`.cfg` 수령 후)

1. MM `.cfg`에서 `Device,` 줄 전부 추출 → MM 장치 목록
2. NIS-Elements 장치 관리자에서 장치 목록 추출
3. 물리적 실사 (실제로 붙어 있는 것)
4. 세 목록을 합쳐 위 표를 생성
5. 불일치 각각에 대해 조치 결정: MM에 추가 / 사이드카로 기록 / 무시

`.cfg`에서 함께 추출할 것: `ConfigGroup,Channel,...` 프리셋 정의 (채널별로 어떤
장치 속성 조합인지), `Label,` 줄 (터렛·휠 위치 이름), `Property,` 기본값.

---

## 5. 장부 밖(off-ledger) 설정 — 사이드카

MM도 NIS도 기록하지 않는 설정은 **획득 시점에 사람이 적지 않으면 영구 유실**된다.
아카이브가 그 증거다.

획득 폴더마다 `acquisition.yaml`을 남긴다:

```yaml
# kb 스키마 v1 — 장부 밖 설정만 적는다. MM이 기록하는 건 중복 금지.
acquisition: OT0.05_Atto647_Exp80_100x_1.5x_1x1_3
date: 2026-08-08
operator: KH

# MM2가 기록하는 것은 여기 적지 않는다 (중간배율기·터렛·휠 위치·노출·광량 등).
# MM이 놓치는 것만.
off_ledger:
  optical_tweezers:
    power_setting: 0.05              # 단위·의미를 반드시 명시
    power_unit: "AOM control (0-1)"  # 실측 mW는 교정 후 채움
    power_mw_at_sample: null         # ← 측정 예정
    wavelength_nm: 1064
    n_traps: 1
  piezo:
    controller: "<별도 프로그램 이름>"
    z_range_um: null
    step_um: null
    log_file: null                   # 별도 프로그램이 로그를 남기면 경로
  emission_path_notes: "AUX 미러 제거함"

# MM은 위치 번호를 기록하지만 그게 무슨 필터인지는 .cfg의 Label에 달려 있다.
# Label이 등록되어 있으면 이 절은 불필요하다.
ledger_gaps:
  filter_wheel_position: 2           # MM은 Filter-0으로만 기록 중
  filter_wheel_part: null            # ← 위치별 부품 정보 수령 예정

sample:
  system: "ATPS PEG/dextran"
  fluorophore: "ATTO 647N"           # 결합체가 아니라 실제 형광단
  concentration: "10 nM"
  chamber: "coverslip #1.5, 100 um spacer"
  medium_ri: 1.34

intent:
  task: tracking                     # imaging | tracking | frap | photometry
  measured_quantity: "MSD -> G*(w)"
  target_precision_nm: 10
  characteristic_time_s: 0.05
```

**에이전트의 책임**: 설정을 제안할 때 이 파일의 초안을 함께 생성하고,
장부 밖 항목은 **명시적으로 물어본다.** 안 물어보면 다음 사람이 못 쓴다.

---

## 6. 정량 인덱스 (SQLite)

아카이브 2,343건 + 앞으로의 획득을 하나의 테이블로. 선례 검색용.

```sql
CREATE TABLE acquisitions (
  acq_id            TEXT PRIMARY KEY,
  path              TEXT,
  system_id         TEXT,      -- 지문으로 판정
  project           TEXT,
  session_date      TEXT,
  folder            TEXT,

  -- device tier
  camera            TEXT,  camera_chip TEXT,
  objective_label   TEXT,  intermediate_mag REAL,  binning INTEGER,
  roi_x INTEGER, roi_y INTEGER, roi_w INTEGER, roi_h INTEGER,
  bit_depth INTEGER, readout_rate TEXT, camera_gain TEXT,
  exposure_ms       REAL,
  filter_cube       TEXT,  filter_wheel TEXT,  light_path TEXT,
  shutter_device    TEXT,
  illum_device      TEXT,  illum_line TEXT,  illum_percent REAL,
  channel_name      TEXT,

  -- physical tier  (NULL이면 그 항목은 이전 불가)
  sample_pixel_um   REAL,
  excitation_nm     REAL,  excitation_fwhm REAL,
  emission_band     TEXT,
  irradiance_w_cm2  REAL,          -- 광량 실측 없으면 NULL
  total_dose_j_cm2  REAL,          -- 〃

  -- 실측 결과
  n_frames          INTEGER,
  requested_fps     REAL,
  measured_fps      REAL,          -- tail 파싱. 요청값과 다르다
  duty_cycle        REAL,
  dropped_frames    INTEGER,       -- ElapsedTime 차분 이상치

  -- 폴더명에서 파싱
  name_dye          TEXT,  name_exposure_ms REAL,  name_illum_percent REAL,
  name_trap_power   REAL,  name_tags TEXT,

  -- 사이드카
  sidecar_json      TEXT,
  raw_props_json    TEXT,          -- 전체 장치 스냅샷 보존
  parse_error       TEXT
);

CREATE TABLE device_properties (   -- 시스템 프로파일 자동 도출용
  system_id TEXT, device TEXT, property TEXT, value TEXT, n_observed INTEGER
);
```

**`measured_fps`와 `requested_fps`를 따로 두는 게 핵심이다.** 아카이브에서
10 ms 노출 요청에 실측 35.67 ms였다. 요청값만 기록하면 선례가 거짓말을 한다.

---

## 7. 파서가 처리해야 하는 것

| 항목 | 내용 |
|---|---|
| 파일 크기 | 최대 44 MB. **헤더만 스트리밍**으로 읽는다 (Summary + 첫 FrameKey + tail 96 kB) |
| 이중 스키마 | MM 1.4.23(2,137건, 91%)과 2.0.3이 다르다. → [reference §10](../reference/observed-systems.md) |
| 시스템 지문 | PC 이름으로 구분하면 틀린다. 장치 라벨 집합 + 카메라 칩/시리얼 해시 사용 |
| 라벨 오타 | `Prime95B` vs `Pirme95B`(20건). 별칭 테이블 필요 |
| 활성 조명 판정 | 두 광원이 동시 등록됨. `Core-Shutter`를 기준으로 판정 |
| 폴더명 파싱 | `Las10`=세기, `Las488`=파장, `Las555_5`=555 nm를 5%. 350–800 정수면 파장 |
| tail | 마지막 `ElapsedTime-ms`와 프레임 인덱스로 실측 fps·드랍 검출 |

---

## 8. 시료계 레시피 (`kb/samples/`)

시스템이 아니라 **무엇을 찍는가**에 붙는 지식. 하드웨어가 바뀌어도 남는다.

`characteristic_scales`(τ_c, ℓ_c)는 [04 §1](04-decision-engine.md) 결정
순서의 ①'·②·⑦이 소비하는 값이다. 시료계마다 물리 모델이 다르므로(확산,
능동입자 run-and-tumble, 계면 이완...) 범용 계산기를 두지 않고 시료계 파일
자체에 구조화된 필드로 적는다.

```markdown
---
system: ATPS PEG/dextran
characteristic_scales:
  time:
    value_s: null              # 없으면 자원 배분 불가 — 추정값이라도 채운다
    evidence: assumed          # measured | assumed — advances 판정은 이것만 본다
    method: calculation        # measurement | calculation | literature | expert-judgment
    model: "confinement diffusion: tau_c = ell_c^2 / (2D), D from Stokes-Einstein"
    inputs: {particle_radius_nm: 500, viscosity_pa_s: 0.001}
    measured_by: null          # evidence=measured면 kb/calibrations/... 링크
    review_after: 2027-02-12
  length:
    value_m: 1.0e-6
    evidence: assumed
    method: literature
    model: "알려진 입자 반경 (DLS 미실시)"
    review_after: 2027-02-12
---
## 광학적 성질
- 두 상의 굴절률: PEG-rich ?, dextran-rich ?     ← ⚠ 측정 필요
- 굴절률 부정합 → 계면 근처 구면수차, 초점 이동

## 형광 표지
- DEX647: 덱스트란 분자량이 상 분배와 D를 결정 ← 반드시 기록
- ATTO 647N: 소수성 → 계면 비특이 흡착 가능

## 알려진 함정
- 침투압으로 시간에 따라 상 조성이 변함 → 장시간 실험 시 기준 이동
- 액적 침강/부상

## 검증된 설정 (system_id별)
| system | 대물 | 노출 | 조도 | 실측 fps | 결과 |
|---|---|---|---|---|---|
```

**규칙**: `evidence: assumed`인 값도 프레임레이트·픽셀 크기 계산에는 그대로
쓴다 — 추정 없이는 애초에 노출·프레임레이트를 정할 수 없다. 하지만 `evidence
== measured`가 아니면 [05 §5](05-consensus-gate.md)의 `Verdict.advances`는
`false`로 남는다 — `power_at_sample_mw` 미실측 시 [04 §3](04-decision-engine.md)이
계산을 거절하는 것과 같은 규칙이다. **숫자는 지어내어 쓰되, 확정은 안 한다.**

`length.value_m`이 회절한계(`σ_PSF`)나 목표 픽셀 크기보다 작으면 — 예: 액틴
메시 크기가 회절한계 이하 — 직접 분해 자체가 불가능하다는 신호다. 지금 이걸
잡는 게이트가 없다 → [04 §2](04-decision-engine.md).

---

## 9. 결정 로그 (`kb/decisions/`) — 학습 루프

추천이 실제로 맞았는지 기록하지 않으면 시스템이 개선되지 않는다.

```markdown
# 2026-08-08 · ATPS 647 추적
## 요구
## 제안한 설정 + 근거 (게이트 출력 전문)
## 실제로 쓴 설정 (다르면 왜)
## 결과
- 달성 SNR / 위치추정 정밀도 / 실측 fps / 드랍
- 예측 대비 오차
## 배운 것 → 어느 파일을 고쳤나
```

이게 쌓이면 게이트 임계값을 경험적으로 조정할 수 있다.

---

## 10. 열린 질문

**수령 예정 (사용자 확인됨)**
- [ ] 현재 시스템 `.cfg` — full capability 연결 상태. 장치·프리셋·`Label,` 전부
- [ ] 필터 휠 위치별 부품
- [ ] 광집게 출력 실측 (`OT` 설정값 → mW @ sample)
- [ ] 자주 쓰는 형광 염료 정보 → `data/fluorophores.yaml`
- [ ] 광집게 MATLAB 코드 + 논문 → 렌즈 7

**아직 미확보**
- [ ] NIS-Elements 장치 목록 (3자 대조용)
- [ ] 필터 큐브 실체 (아카이브의 `DA/FI/TR10Empty`가 현재도 같은지)
- [ ] 대물렌즈 실물 각인 (NA·WD·커버글라스 두께)
- [ ] 조명 광량 실측 (라인 × 대물 × 레벨)
- [ ] 픽셀 크기 실측 교정 (배율별)
- [ ] 디스크 지속쓰기 대역폭 실측
- [ ] `SA647`/`DEX647`/`Phal647`의 실제 형광단과 DOL
- [ ] Kinetix 실제 사용 카메라 모드(Speed/Sensitivity/DynamicRange) — 이게
      없으면 `read_noise_e`가 null로 남아 `optics.cli check`가 이 카메라를
      쓰는 모든 채널에서 BLOCKED로 나온다 (full_well_e/dark_e_per_s는
      데이터시트 자체에 없어 모드 확정과 무관하게 별도 실측 필요,
      2026-08-10 config/channels/particle647-yoyo1-2color.yaml 설계 중 확인)
- [ ] 피에조 제어 프로그램 이름과 로그 형식
- [x] DMD 존재 여부 — 2026-08-11 물리적으로 연결됨을 확인 (MM/NIS 등록 여부는 별개, 미확인)
- [ ] ND2/LIF(다른 시스템) 인덱싱 여부

**확정된 것**
- ✅ 제어 소프트웨어: **Micro-Manager 2.x**
- ✅ 현재 시스템 ≠ 아카이브 셋업
- ✅ 중간배율기는 MM 장치로 등록됨
- ✅ 피에조는 MM·NIS 밖. 별도 프로그램 가능
