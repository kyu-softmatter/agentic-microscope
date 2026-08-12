# 08 · 광학계 렌즈 설계

두 가지를 다룬다. 섞으면 안 되는 두 가지다.

| | 무엇 | 형태 | 어디에 |
|---|---|---|---|
| **§0** | 광학계 **검토위원이 판정하는 방식** | 로직 (Python) | `optics/gate.py` |
| **§1–7** | 광학계 **하드웨어를 적어두는 방식** | 데이터 (YAML) | `kb/systems/`, `data/` |

---

## 0. 검토위원의 계산 구조 — `if` 체인이 아니라 체크 레지스트리

> **질문**: 검토가 순서대로 진행되니까 `if` 문으로 이어 쓰면 되지 않나?

`if` 자체는 맞다. 문제는 **`if`를 체크 *사이*에 쓸 것인가, 체크 *안*에 쓸 것인가**다.

### ❌ 나쁜 형태 — if 체인 / 조기 반환

```python
def evaluate(ch):
    if ch.excitation_efficiency() == 0:
        return FAIL("여기가 안 된다")
    if ch.blocking_od() < 5:
        return FAIL("차단이 부족하다")
    if ch.crosstalk() > 0.05:
        return FAIL("크로스토크가 크다")
    return PASS
```

읽기 쉽고 자연스러워 보이지만 이 프로젝트에서는 네 가지가 망가진다.

**(1) 첫 번째 문제만 보고한다.**
실험자는 고치고 → 재실행 → 또 하나 발견 → 재실행을 반복하게 된다.
필요한 건 **한 번에 전체 그림**이다. 광경로를 손보러 현미경 앞에 가는 건
한 번이어야 한다.

**(2) 난이도 등급을 만들 수 없다.**
[05 §3](05-consensus-gate.md)의 `ROUTINE`/`TIGHT`/`HARD` 등급은
**모든 게이트의 여유(margin)** 가 있어야 나온다. G1에서 반환해버리면
G2~G4의 여유를 모른다. "이 실험이 얼마나 어려운가"에 답할 수 없다.

**(3) 개선 제안을 만들 수 없다.**
민감도 분석은 "어느 게이트가 병목이고, 각 개입이 그 여유를 얼마나 올리는가"다.
전부 계산되어 있어야 한다.

**(4) 체크를 추가하려면 함수를 수정해야 한다.**
새 체크마다 `evaluate`가 길어지고, 테스트는 함수 전체를 다시 태운다.
체크 하나만 단위 테스트할 수 없다.

### ✅ 맞는 형태 — 2단계 + 평평한 체크 목록

```
Phase 0   입력 충족 검사
          ← 여기만 전제 의존. 미충족이면 BLOCKED, 나머지 계산 안 함
            (NA가 없으면 수집효율 계산 자체가 무의미하므로)

Phase 1   체크 전부 독립 실행
          ← 서로 모른다. 실패해도 멈추지 않는다. 각자 margin을 낸다.

Phase 2   집계
          ← hard 게이트 veto / 난이도 = 최악 margin / 민감도 분석
```

**`if`는 체크 *안*에서만 쓴다.**

```python
@dataclass
class Check:
    code: str
    kind: str                  # hard | bias | soft   ← [05 §2]
    requires: tuple[str, ...]  # 이 체크가 필요로 하는 입력
    run: Callable[[Channel, list[Channel]], CheckResult]

@dataclass
class CheckResult:
    margin: float        # 달성/요구. 1.0 = 딱 걸침. 등급과 민감도의 재료
    severity: str        # fail | warn | info | ok
    message: str
    action: str | None   # FAIL이면 반드시 있어야 함
    numbers: dict        # 판정 근거가 된 값 전부
```

체크 하나는 이렇게 생긴다. 안에서 `if`를 쓰는 건 자연스럽다:

```python
def check_blocking(ch, others):
    od = ch.excitation_blocking_od()
    required = 5.0
    margin = od / required
    if margin >= 1.0:
        return CheckResult(margin, "ok", f"차단 {od:.1f} OD", None, {"od": od})
    return CheckResult(
        margin, "fail",
        f"검출 경로가 여기광을 {od:.1f} OD만 감쇠한다. 후방산란이 신호를 덮는다.",
        action=f"{ch.source.center_nm:.0f} nm에서 충분한 차단을 갖는 방출필터 추가",
        numbers={"od": od, "required": required},
    )

CHECKS = [
    Check("excitation.coupling", "hard", ("dye.abs", "source", "ex_path"), check_excitation),
    Check("blocking",            "hard", ("source", "em_path", "qe"),      check_blocking),
    Check("collection",          "soft", ("dye.em", "em_path", "qe"),      check_collection),
    Check("crosstalk",           "bias", ("dye.em", "em_path", "others"),  check_crosstalk),
    ...
]
```

집계는 이것뿐이다:

```python
def evaluate(ch, others):
    missing = [c for c in CHECKS if not inputs_available(ch, c.requires)]
    if missing:
        return Verdict(status="BLOCKED", ...)          # Phase 0

    results = {c.code: c.run(ch, others) for c in CHECKS}   # Phase 1 — 전부 실행

    hard_veto = any(r.margin < 1 for c, r in pairs if c.kind == "hard")
    worst = min(r.margin for c, r in pairs if c.kind in ("soft", "bias"))
    return Verdict(                                     # Phase 2
        status="FAIL" if hard_veto else grade(worst),
        feasibility=grade(worst),
        margins={code: r.margin for code, r in results.items()},
        ...
    )
```

### 왜 "순서대로"라는 느낌이 드는가

빛은 순서대로 지나가지만, **판정은 순서가 없다.**

- 투과율은 곱이다: `T = Π Tᵢ` — 교환법칙 성립, 순서 무관
- 판정은 독립 조건의 AND다: `여기 ∧ 수집 ∧ 차단 ∧ 크로스토크`
- 순서처럼 보이는 건 **서술 순서**지 계산 의존성이 아니다

진짜 의존성은 딱 하나, **입력 충족(Phase 0)** 뿐이다. 그래서 2단계면 충분하다.

### 다른 렌즈에도 같은 구조를 쓴다

검출계·전산자원·광집게 렌즈 전부 같은 `Check` / `CheckResult` / `Verdict`
스키마를 쓴다. 그래야 위원회가 렌즈들을 균일하게 집계할 수 있고,
난이도 등급과 민감도 분석이 렌즈를 가리지 않는다. → [05 §5](05-consensus-gate.md)

### 현재 구현 ✅

이 구조로 구현되어 있다.

- `optics/checks.py` — `Check` / `CheckResult(margin)` / `CHECKS` 레지스트리,
  `available_facts()`(Phase 0), `grade()`(난이도 등급)
- `optics/gate.py` — Phase 0/1/2 집계만. 체크 로직 없음

출력에 margin이 그대로 나온다:

```
feasibility: COMFORTABLE  정상 범위.
bottleneck:  blocking  (margin 1.65)

  margins (achieved / required; 1.0 = exactly at the limit)
      0.98  emission.centering         #########
      1.65  blocking                   ################
      1.95  excitation.coupling        ###################
      2.20  spectral.separation        ######################
      3.04  collection                 ##############################
     10.00  crosstalk                  ##############################
```

구현하면서 걸린 두 가지:

- **margin 폭주** — 크로스토크가 사실상 0이면 `limit/actual`이 1e28이 된다.
  `MAX_MARGIN = 10.0`으로 클램프
- **같은 양을 두 번 채점** — `collection`(절대)과 `emission.centering`(필터 기여분)이
  같은 물리량을 재는데 둘 다 채점하면 하나의 약점이 두 번 깎인다.
  게다가 필터 효율 49% vs 목표 50%가 전체를 `HARD`로 끌어내렸다.
  → `centering`은 `INFO`로 강등. **`collection`이 등급을 소유하고
  `centering`은 이유를 설명한다**

---

## 1. 하드웨어를 `if` 문으로 적으면 안 되는 이유

*(여기서부터는 하드웨어 기술 형식 이야기 — 판정 로직과 별개다)*

```python
# ❌ 이렇게 쓰면 안 된다
def throughput(wavelength, channel):
    t = 1.0
    if channel == "647":
        t *= excitation_filter_640(wavelength)
        if dichroic_installed:
            t *= dichroic_650(wavelength)
        ...
```

**(1) 하드웨어가 바뀔 때마다 코드를 고쳐야 한다.**
필터 하나 갈면 코드 수정 → 테스트 → 커밋. 실험실에서 필터는 자주 바뀐다.
YAML 한 줄 고치는 것과 비교가 안 된다.

**(2) ablation을 할 수 없다.**
이 프로젝트에서 광학계 렌즈의 핵심 기능은 **"이 요소를 빼면 어떻게 되나"** 를
추측이 아니라 실제로 계산하는 것이다. 곱셈에서 항을 하나 빼려면 항들이
**리스트의 원소**여야 한다. `if` 분기는 뺄 수가 없다.

```python
# ✅ 리스트라서 가능한 것
signal_without = channel.relative_signal(skip="FF01-692/40")
gain = signal_without / channel.relative_signal()
```

**(3) `.cfg`와 대조할 수 없다.**
Micro-Manager 설정 파일과 실제 광경로가 일치하는지 확인하려면 둘 다 같은 형태의
**목록**이어야 한다. 코드 분기와 `.cfg`를 diff할 수는 없다.

**(4) 이력이 안 남는다.**
`git diff`에서 `- FF01-692/40` / `+ FF01-685/70` 은 한눈에 읽힌다.
`if` 조건이 바뀐 diff는 무슨 하드웨어 변경인지 알 수 없다.

**(5) 곱셈은 교환법칙이 성립한다.**
투과율 계산에서 순서는 애초에 의미가 없다. `T = Π Tᵢ`.
`if` 문의 순차성은 물리를 반영한 게 아니라 착시다.

---

## 2. 순서가 실제로 중요한 경우

투과율 계산에는 순서가 무관하지만, **다음은 순서에 의존한다.** 그래서 순서를
버리지 않고 기록은 해둔다 — 계산에 안 쓸 뿐이다.

| 항목 | 왜 순서가 중요한가 |
|---|---|
| **구간(segment)** | 빔스플리터 앞/뒤가 여기경로/방출경로를 가른다. **이건 계산에 직접 영향** |
| 자가형광 | 형광을 내는 요소(플라스틱, 접착제, 일부 ND)는 방출필터 **앞**에 있어야 걸러진다 |
| 손상 임계 | 고출력 앞단에 ND를 두느냐 뒤에 두느냐가 부품 수명을 가른다 |
| 고스트·에탈론 | 인접한 두 평행 광학면 사이의 다중반사 |
| 편광 | 편광 소자끼리는 순서가 결과를 바꾼다 |
| 물리적 제약 | 어느 슬롯에 들어갈 수 있는가 |

→ 따라서 **구간별 순서 있는 리스트**로 적는다. 계산은 곱, 기록은 순서.

---

## 3. 2단계 모델 — 장비와 채널을 분리한다

이게 핵심이다. **장비는 안 바뀌고 슬롯 설정만 바뀐다.**

```
① 장비 (instrument)   무엇이 어느 슬롯에 물리적으로 설치되어 있는가
                      kb/systems/current.md
                      바뀌는 빈도: 몇 달에 한 번

② 채널 (channel)      각 설정 가능 슬롯을 어느 위치로 놓는가
                      config/channels/*.yaml
                      바뀌는 빈도: 실험마다
```

**이 구조가 Micro-Manager의 `ConfigGroup` 과 정확히 같다.**

```
# MM .cfg의 구조
ConfigGroup,Channel,647-Cy5,FilterTurret1,Label,1-Quad
ConfigGroup,Channel,647-Cy5,Wheel-A,Label,2-FF01-692/40
ConfigGroup,Channel,647-Cy5,Spectra,Red_Enable,1
```

즉 **`.cfg`에서 채널 정의를 자동 생성할 수 있고, 거꾸로 추천 결과를 `.cfg`
프리셋으로 내보낼 수도 있다.** MM2 확정이므로 이 왕복이 계획대로 가능하다.

---

## 4. 장비 기술 형식

`kb/systems/current.md` 의 front matter. **슬롯 중심**으로 적는다.

```yaml
optical_slots:

  # ── 여기 경로 (광원 → 시료) ────────────────────────────────
  - slot: light_engine
    segment: excitation
    order: 10
    device: Spectra            # MM 장치 라벨
    kind: light_source
    fixed: true                # 위치가 바뀌지 않음
    ref: data/light_sources.yaml#Spectra

  - slot: cube.excitation
    segment: excitation
    order: 20
    device: FilterTurret1      # 큐브 안에 들어있음
    kind: bandpass
    selectable: true           # 터렛 회전으로 바뀜
    positions:
      1: {ref: "data/filters.yaml#<큐브1 여기필터>"}
      2: null                  # 비어 있음
    note: "큐브 내장. 개별 교체 불가"

  - slot: cube.dichroic
    segment: shared            # 여기는 반사, 방출은 투과
    order: 30
    device: FilterTurret1
    kind: dichroic
    selectable: true
    removable: false           # 구조 요소
    positions:
      1: {ref: "data/filters.yaml#<큐브1 다이크로익>"}

  - slot: nosepiece
    segment: shared
    order: 40
    device: Nosepiece
    kind: objective
    selectable: true
    positions:
      1: {ref: "objectives#10x"}
      5: {ref: "objectives#100x-oil"}

  # ── 방출 경로 (시료 → 카메라) ──────────────────────────────
  - slot: cube.emission
    segment: emission
    order: 50
    device: FilterTurret1
    kind: bandpass
    selectable: true

  - slot: wheel_A
    segment: emission
    order: 60
    device: Wheel-A
    kind: bandpass
    selectable: true
    positions:                 # ⚠ 구 셋업에서는 전부 비어 있었다
      0: null
      1: {ref: "data/filters.yaml#..."}
      2: {ref: "data/filters.yaml#..."}
    note: "MM .cfg에 Label을 등록해야 메타데이터에 남는다"

  - slot: magnifier
    segment: emission
    order: 70
    device: IntermediateMagnification
    kind: magnifier
    selectable: true
    positions: {1: 1.0, 2: 1.5}
    off_ledger: false          # MM에 등록되어 있으면 false

  - slot: sideport
    segment: emission
    order: 80
    device: LightPath
    kind: beam_split
    selectable: true
    positions:
      "4-L100": {fraction: 1.00, destination: camera}
      "3-AUX":  {fraction: 0.00, destination: aux, note: "광집게/DMD"}

  - slot: camera
    segment: emission
    order: 99
    device: Prime95B
    kind: detector
    fixed: true
    ref: data/detectors.yaml#Prime95B
```

**핵심 필드**

| 필드 | 역할 |
|---|---|
| `segment` | `excitation` / `emission` / `shared` — **계산에 직접 쓰임** |
| `order` | 물리적 순서. §2의 순서 의존 항목 판정용 |
| `selectable` | 자동으로 바꿀 수 있는가 (터렛·휠) vs 손으로 갈아야 하는가 |
| `removable` | ablation 대상인가. 구조 요소는 `false` |
| `positions` | 선택 가능한 위치 → 각각 무엇인지 |
| `off_ledger` | MM이 상태를 기록하지 않는가 → 사이드카 필수 |
| `ref` | 실제 스펙은 `data/` 레지스트리에 있고 여기선 참조만 |

**슬롯이 비어 있으면 `null`을 명시한다.** 항목 자체를 빼면 "확인 안 함"과
"비어 있음"을 구별할 수 없다.

---

## 5. 채널 기술 형식

장비를 참조해서 **슬롯 위치만** 적는다.

```yaml
# config/channels/647-tracking.yaml
system: current                # kb/systems/current.md 참조

channels:
  - name: "647-Cy5"
    dye: ATTO647N
    slots:
      cube.dichroic: 1
      cube.emission: 1
      wheel_A: 2
      nosepiece: 5
      magnifier: 1
      sideport: "4-L100"
    illumination:
      device: Spectra
      line: Red
      level_percent: 10
    camera:
      exposure_ms: 80
      binning: 1
      roi: [742, 898, 160, 176]
      readout_mode: HDR-16bit
```

이걸 광학계 렌즈가 장비 기술과 합쳐서 `Channel` 객체로 펼친다.
사람이 필터 이름을 반복해서 적을 필요가 없고, 장비가 바뀌면 **한 곳만** 고치면 된다.

> **현재 구현**은 아직 짧은 형식(필터 이름을 채널에 직접 나열)만 지원한다.
> → [config/channels/proposed-2color.yaml](../config/channels/proposed-2color.yaml)
> 슬롯 참조 방식은 `.cfg` 수령 후 추가한다.

---

## 6. 그러면 `if` 문은 어디에 쓰나

**판정 로직에 쓴다.** 하드웨어 기술이 아니라.

```python
# ✅ 이건 로직이다 — if가 맞다
if blocking_od < floor:
    verdict = "required"
elif crosstalk > limit:
    verdict = "required"
elif gain >= threshold and not spectra_measured:
    verdict = "candidate"
```

경계선은 이렇다:

| | 형태 | 어디에 |
|---|---|---|
| **무엇이 설치되어 있는가** | 데이터 (YAML) | `kb/systems/`, `data/` |
| **무엇으로 설정하는가** | 데이터 (YAML) | `config/channels/` |
| **그게 괜찮은가** | 로직 (Python) | `optics/gate.py` |
| **물리 계산** | 수식 (Python) | `optics/spectra.py`, `path.py` |

하드웨어를 코드에 쓰기 시작하면 **판정 기준과 하드웨어 사실이 뒤섞여서**,
"이 필터를 왜 쓰지?"에 답할 수 없게 된다.

---

## 7. `.cfg` 왕복 (MM2 확정으로 가능)

```
MM .cfg  ──파싱──▶  kb/systems/current.md  (슬롯·위치·라벨)
                          │
                          ├─ NIS-Elements 장치목록과 대조 → 3자 대조표
                          │                                  [02 §4]
                          ├─ 물리 실사와 대조 → 누락 장치 발견
                          │
                          ▼
                    광학계 렌즈 계산
                          │
                          ▼
              config/channels/*.yaml  (추천된 슬롯 설정)
                          │
                     ──생성──▶  MM ConfigGroup 프리셋
                                (Phase 2: 자동 적용)
```

`.cfg`에서 추출할 것:

| `.cfg` 줄 | 쓰임 |
|---|---|
| `Device,<label>,<lib>,<name>` | 장치 목록 → 3자 대조표 |
| `Label,<device>,<state>,<name>` | **터렛·휠 위치 이름** ← 구 셋업의 최대 공백 |
| `ConfigGroup,Channel,<preset>,...` | 기존 채널 정의 → 초기 KB |
| `ConfigGroup,System,Startup,...` | 시작 상태 |
| `Property,<device>,<prop>,<val>` | 기본값 |
| `PixelSize_um`, `ConfigPixelSize` | 픽셀 교정 (구 셋업엔 없었음) |

**`Label,` 줄이 없으면 필터 휠은 영원히 `Filter-0`으로 기록된다.**
`.cfg`를 받으면 제일 먼저 확인할 것.
