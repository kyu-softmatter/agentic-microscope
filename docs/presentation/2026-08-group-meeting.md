# experimentalist — 그룹 미팅 발표 대본

> **용도**: 랩 그룹 미팅 (동료 연구자), 발표 25–30분 + 토론
> **언어 규칙**: 본문·발표 스크립트는 한국어, **도표·표·코드 블록·용어는 영어 원문**
> (추후 전체 영어 번역 예정이므로 도표는 손대지 않고 재사용 가능하게 작성)
> **근거**: 모든 숫자와 주장은 `docs/01`–`docs/09`, `README.md`, 코드에서 확인된 것만 사용.
> 슬라이드별 근거를 각 항목 끝에 `→ docs/0X §Y` 로 표기.

---

## 0. 덱 개요

| # | 슬라이드 | 파트 | 분 | 핵심 메시지 한 줄 |
|---|---|---|---|---|
| 1 | Title | — | 0.5 | — |
| 2 | 왜 만드는가 | 도입 | 2 | 설정 계산기가 아니라 **전문성 이식 장치** |
| 3 | 왜 일반 챗봇이 아닌가 | 도입 | 2 | 구조적 제약 3개가 설계를 결정했다 |
| 4 | 시스템 한 장 요약 | 요소 | 1.5 | 요소 4개: KB · 결정론 코드 · LLM · 위원회 |
| 5 | 요소 ① 결정론적 Python | 요소 | 2 | 계산되는 것은 추측하지 않는다 |
| 6 | 요소 ② LLM의 역할 | 요소 | 2 | LLM은 숫자를 만들지 않는다 |
| 7 | 요소 ③ Verdict 스키마 | 요소 | 2.5 | `advances = passed AND evidence == measured` |
| 8 | 요소 ④ BLOCKED ≠ FAIL / 난이도 등급 | 요소 | 2 | 이진 판정은 게이트를 꺼지게 만든다 |
| 9 | 요소 ⑤ 문제제기 A — 개선 제안 | 요소 | 2 | "어렵다"만 말하면 쓸모없다. 무엇을 고칠지 계산 |
| 10 | 요소 ⑥ 문제제기 B — 교착을 사람에게 | 요소 | 2 | 충돌 제시가 실패가 아니라 정상 동작 |
| 11 | KB 역할 — 3-tier normalization | KB | 2 | 물리량만 시스템을 건너간다 |
| 12 | KB 구성 | KB | 2 | markdown + SQLite. vector DB 안 씀 |
| 13 | KB — 장부 밖 설정 (off-ledger) | KB | 1.5 | 안 물어보면 영구히 소실된다 |
| 14 | KB — 전문성 엔트리 & 수집 3경로 | KB | 2.5 | `Why`와 `반증 조건`이 필수 필드 |
| 15 | KB — 학습 루프 & 충돌 기록 | KB | 1.5 | 계산이 자동으로 이기지 않는다 |
| 16 | 워크플로우 A — L0→L5 계층 | WF | 2 | 원본은 읽기 전용, KB만 영속 |
| 17 | 워크플로우 B — 결정 순서 ①–⑨ | WF | 2.5 | 순서는 물리가 정한다. 사이클 2개 |
| 18 | 워크플로우 C — 위원회 6+2 | WF | 2.5 | 학문이 아니라 **서브시스템**으로 분할 |
| 19 | 워크플로우 D — 교차 렌즈 제약 | WF | 2 | 이게 위원회의 존재 이유 |
| 20 | 워크플로우 E — 오케스트레이션 + 실행 예시 | WF | 2.5 | 계산 렌즈 먼저, 결과가 LLM의 입력 |
| 21 | 폴더 구성 | 구조 | 2 | 한 렌즈 = 한 폴더 = 한 CLI |
| 22 | 완성도 | 현황 | 2.5 | 8개 렌즈 코드 완료, 게이트 32개 |
| 23 | 막힌 것은 코드가 아니라 사실 | 현황 | 2 | `power_at_sample_mw` 하나가 최상위 블로커 |
| 24 | 로드맵 Phase 0–5 + 즉시 이득 3 | 현황 | 2 | 각 단계가 단독으로 유용해야 한다 |
| 25 | 기대효과 (1/2) | 효과 | 2 | 구축 · 수행 · 집중 |
| 26 | 기대효과 (2/2) | 효과 | 2 | 실패 데이터 · 진입장벽 · 타 랩 수용도 |
| 27 | 정리 + 요청사항 | 마무리 | 1.5 | 파워미터 30분이 최대 언락 |
|  | 부록 A–D | 백업 | — | 질문 대응용 |

**20분으로 줄여야 할 때 자를 순서**: 15 → 13 → 19 → 9
(단, 9를 자르면 "그래서 뭘 고치라는 건데"라는 질문이 반드시 나옴 → 부록으로 이동)

**한 장만 남긴다면**: Slide 7 (Verdict 스키마). 이 시스템에서 새로운 건 사실상 이거 하나.

---

## Slide 1 — Title

**슬라이드 본문**

```
experimentalist
An agent that designs experiments and proposes microscope settings

Kyu Hwan Choi · Takatori Group · 2026-08
```

**발표 스크립트**
> 현미경 실험 설정을 제안하는 에이전트를 만들고 있습니다. 오늘은 어떤 부품으로 구성돼 있고, 어떻게 동작하고, 어디까지 됐고, 뭐가 좋아지는지를 순서대로 말씀드리겠습니다.
>
> 결론을 먼저 말씀드리면 — 이건 챗봇이 아니고, "계산할 수 있는 건 코드가 계산하고, 판단이 필요한 것만 LLM이 하고, 근거가 없으면 대답을 거절하는" 시스템입니다. 그 거절이 버그가 아니라 기능입니다.

---

## Slide 2 — 왜 만드는가

**한 줄 메시지**: 설정 계산기가 아니라 **전문성 이식 장치(expertise transplant device)**다.

**슬라이드 본문**
- 출발점이 된 문제의식: 장비와 실험에 대한 노하우를 후배마다 한 명씩 붙어서 설명하는 대신, **내 수준의 지식을 갖고 있는 에이전트**를 만들어 더 쉽고 일반적으로 쓰게 하고 싶다
- 그래서 목표는 "숫자 뽑는 계산기"가 아님. 계산 게이트는 절반이고, **나머지 절반은 계산이 만들어내지 못하는 지식**
- 왼쪽은 코드로 되고, 오른쪽은 지금 사람 머릿속에만 있음 → 데이터시트에도 논문에도 없다

**도표 (English)**

```
What computation gives          What computation does NOT
──────────────────────────      ─────────────────────────────────────────────────
transmission, SNR, sampling     this sample changes composition 30 min after prep
trap stiffness, data rate       this dye adsorbs non-specifically at this interface
diffraction limit               a 647 exposure that reached 500 ms means the light
photon budget                       level was insufficient
                                this objective is unusable past 20 um unless the
                                    correction collar is set
                                sample preparation is 80% of this experiment
```

→ `docs/09 §0`

**발표 스크립트**
> 시작은 아주 실용적인 동기였습니다. 장비 노하우를 후배마다 1:1로 설명하는 게 반복되니까, 그 지식을 담은 에이전트를 만들자는 것이었습니다.
>
> 그런데 만들다 보니 이게 설정 계산기가 아니란 걸 알게 됐습니다. 계산으로 나오는 건 왼쪽입니다. 투과율, SNR, 샘플링, 트랩 강성 — 이건 닫힌 형태의 식이 있으니까 코드가 하면 됩니다.
>
> 문제는 오른쪽입니다. "이 샘플은 준비 후 30분이면 조성이 바뀐다", "이 형광색소는 이 계면에 비특이적으로 붙는다", "647 노출이 500 ms까지 올라갔다는 건 광량이 부족했다는 신호다". 이건 어떤 데이터시트에도 논문에도 없습니다. 이걸 대화에서 꺼내서 저장하는 게 이 프로젝트의 실제 목적입니다.

---

## Slide 3 — 왜 일반 챗봇이 아닌가

**한 줄 메시지**: 구조적 제약 3개가 설계 전체를 결정했다.

**슬라이드 본문**

**(1) 과거 설정은 그대로 복사되지 않는다**
- 보관된 취득 데이터 2,343건은 지금 존재하지 않는 셋업에서 나온 것 (Nikon + Photometrics 조합)
- `Exposure=500ms, Spectra-Red_Level=10` 같은 장치 값은 카메라·광원·필터가 바뀌면 무의미
- 넘어가는 건 그 설정이 만들어낸 **물리량**뿐: 시료면 광자 플럭스, 유효 픽셀 크기, 여기/방출 밴드, 총 광자 선량

**(2) 계산할 수 있는 것을 추측하면 안 된다**
- 광학 투과율, SNR, 샘플링, 트랩 강성은 모두 닫힌 형태의 식이 있음
- LLM이 "대충 이 정도면 됩니다"라고 답한 순간 이 프로젝트는 실패

**(3) 렌즈에 따라 최적이 반대 방향이다**
- 광구동 능동 입자: 광학 렌즈는 "SNR 위해 광량 올려라", 광섭동 렌즈는 "그 빛이 입자를 밀고 있다"
- 형태 관찰과 입자 추적은 **최적 픽셀 크기가 반대 방향**
- 단일 관점 최적화는 조용히 틀린 답을 낸다

→ `docs/01 §1`, `README`

**발표 스크립트**
> 왜 그냥 GPT에 물어보면 안 되냐는 질문에 대한 답이 이 세 개입니다.
>
> 첫째, 과거 설정은 복사가 안 됩니다. 저희 아카이브 2,343건은 지금 없어진 셋업에서 찍은 겁니다. 노출 500 ms, 광량 레벨 10 같은 값은 카메라랑 광원이 바뀌면 아무 의미가 없습니다. 넘어가는 건 그 설정이 만들어낸 물리량 — 시료면 광자 플럭스, 유효 픽셀 크기 — 뿐입니다. 그래서 시스템의 중심축이 "장치 값 → 물리량 → 현재 장비로 재투영"입니다.
>
> 둘째, 계산되는 걸 추측하면 안 됩니다. 투과율이든 SNR이든 식이 있습니다. LLM이 "한 80 ms 정도면 될 것 같습니다"라고 말하기 시작하면 이 프로젝트는 그 시점에 실패한 겁니다.
>
> 셋째, 이게 제일 중요한데, 관점에 따라 최적이 반대입니다. 광구동 능동 입자를 볼 때 광학 관점에서는 광량을 올리는 게 맞고, 광섭동 관점에서는 그 빛이 실험을 망치는 겁니다. 형태를 볼 때와 추적할 때 최적 픽셀 크기도 반대 방향입니다. 그래서 관점을 쪼개서 서로 충돌시키는 구조가 필요했습니다.

---

## Slide 4 — 시스템 한 장 요약

**한 줄 메시지**: 요소는 4개다 — 지식베이스, 결정론적 코드, LLM, 위원회.

**도표 (English)**

```
                        ┌──────────────────────────────┐
   past metadata  ─────▶│  KB  (markdown + SQLite)     │
   hardware specs ─────▶│  physical quantities only    │
   conversation   ─────▶│  + expertise + decision log  │
                        └───────────────┬──────────────┘
                                        │
       user request  ──────▶  ┌─────────▼──────────┐
       "track 647 in ATPS"    │  LLM               │  gathers inputs,
                              │  (reasoning layer) │  asks what is missing,
                              └─────────┬──────────┘  interprets, NEVER computes
                                        │
                              ┌─────────▼──────────┐
                              │  deterministic     │  32 hard gates
                              │  Python (8 lenses) │  closed-form only
                              └─────────┬──────────┘  refuses if input missing
                                        │
                              ┌─────────▼──────────┐
                              │  committee 6 + 2   │  unanimous ADVANCE
                              └─────────┬──────────┘  or escalate to human
                                        │
                    proposal + rationale + assumptions + difficulty grade
                              + improvement options + failure signatures
```

**발표 스크립트**
> 전체를 한 장으로 보면 이렇습니다. 요소가 4개입니다.
>
> 왼쪽 위가 지식베이스입니다. 과거 메타데이터, 하드웨어 스펙, 그리고 대화에서 뽑아낸 전문성이 여기 쌓입니다.
>
> 사용자 요청이 들어오면 LLM이 받습니다. LLM이 하는 일은 뭐가 부족한지 물어보고, 입력을 모으고, 결과를 해석하는 겁니다. 계산은 안 합니다.
>
> 계산은 그 아래 결정론적 파이썬이 합니다. 게이트가 32개 있고, 전부 닫힌 형태의 식입니다. 입력이 없으면 값을 만들어내지 않고 거절합니다.
>
> 그 결과를 위원회가 심사합니다. 상임 6개, 조건부 2개. 전원 통과가 아니면 확정이 안 되고, 3라운드 안에 수렴 안 하면 충돌을 사람에게 넘깁니다.
>
> 최종 산출물은 설정 값 하나가 아니라 — 근거, 가정, 난이도, 개선 옵션, 그리고 실패 시그니처까지 붙어 나옵니다.

---

## Slide 5 — 요소 ① 결정론적 Python: 계산은 코드가

**한 줄 메시지**: 계산되는 것은 추측하지 않는다. 입력이 없으면 `None`을 반환한다.

**슬라이드 본문**
- 광자 예산 전체 체인이 닫힌 형태로 구현돼 있음 (`optics/path.py`, `detection/photometry.py`)
- 자주 빠뜨리는 최대 항목이 **기하학적 집광 효율** — 100x NA 1.45 oil이 전체 입체각의 35.2%, 10x NA 0.3 air는 2.3%
- **핵심 동작**: 시료면 광량(`power_at_sample_mw`)이 비어 있으면 `detected_e_per_s()`가 숫자를 만들지 않고 `None`을 반환

**도표 (English)**

```
source power P [W]   (measured at the sample plane)
   |  / illuminated area A
irradiance   I = P/A             [W/cm2]
   |  / photon energy hc/lambda
photon flux  phi = I*lambda/(hc) [photons cm-2 s-1]
   |  * absorption cross-section  (sigma_abs = 3.82e-21 * epsilon)
excitation rate  k_ex = sigma_abs * phi * (spectral overlap)
   |  * quantum yield
emission rate    k_em = k_ex * Phi_F
   |  * eta_geo * T_em * QE
detection rate   k_det                     [e-/s/molecule]
   |  * exposure time
signal per frame S = k_det * t_exp         [e-]

eta_geo = (1 - cos theta)/2,   sin theta = NA/n
  100x NA1.45 oil  -> 0.352   (35.2% of 4pi)
   60x NA1.20 water-> 0.282
   10x NA0.30 air  -> 0.0230  ( 2.3%)
```

```python
# archive state, as-is
ch.detected_e_per_s()                                      # -> None

# after 30 minutes with a power meter
ch.detected_e_per_s(power_mw_at_sample=1.0,
                    illuminated_area_um2=100*100)          # -> a value
```

→ `docs/04 §3`

**발표 스크립트**
> 결정론적 파이썬 쪽이 어떤 걸 하는지 대표적인 예가 광자 예산입니다. 광원 파워에서 시작해서, 조명 면적으로 나눠 조도를 구하고, 광자 에너지로 나눠 광자 플럭스, 흡수 단면적 곱해서 여기율, 양자수율 곱해서 방출률, 그리고 집광 효율과 투과율과 QE를 곱해서 검출률까지 — 전 구간이 식으로 이어집니다.
>
> 여기서 사람들이 자주 빼먹는 게 기하학적 집광 효율입니다. 100배 NA 1.45 오일이 전체 입체각의 35% 정도인데, 10배 NA 0.3 공기는 2.3%입니다. 열 배 이상 차이인데 손계산에서는 잘 빠집니다.
>
> 그리고 이 슬라이드에서 제일 봐야 할 건 아래 코드입니다. 지금 시료면 광량이 측정돼 있지 않은데, 그럴 때 이 함수는 `None`을 반환합니다. 그럴싸한 숫자를 만들지 않습니다. 파워미터로 30분 재고 나면 값이 나옵니다. 이 동작이 시스템 전체의 설계 원칙입니다.

---

## Slide 6 — 요소 ② LLM의 역할

**한 줄 메시지**: LLM은 숫자를 만들지 않는다. 입력을 모으고, 정성적 판단을 하고, 결과를 사람 언어로 옮긴다.

**슬라이드 본문**

**LLM이 하는 일**
- 자연어 요청 → 계산 가능한 입력으로 변환, **없는 입력은 물어본다** (예: task가 imaging인지 tracking인지 — 기본값을 쓰지 않고 반드시 질문)
- 정성적 판단 렌즈: 챔버 설계, 시료 농도 판단, 다중 산란, 광독성, 삼중항 블링킹, 광구동 물리 — 식이 없거나 입력이 기록되지 않는 영역
- **분석 코드를 읽는 일** — `D:\codes`의 어느 스크립트로 처리할지가 설정 요구사항을 바꿈. 렌즈 6만 이걸 함
- 대화에서 전문성을 감지해서 KB 저장을 제안 (`docs/09`)
- 청중에 따라 답을 다르게 전달 (teaching mode)

**LLM이 하지 않는 일**
- 계산 가능한 값의 추정
- 계산 렌즈의 결과를 **입력으로 받는다.** 스스로 숫자를 생성하지 않는다
- KB에 추측을 넣는 것 — 에이전트 자신의 추론은 출처가 될 수 없다

**도표 (English)**

```
.claude/agents/            (LLM subagent definitions, prompt-only)
  sample-optics.md            Lens 4  qualitative half
  photo-perturbation.md       Lens 5  qualitative half
  measurement-validity.md     Lens 6  qualitative half

Each returns the SAME schema as the code lenses:
  status | feasibility | evidence | confidence | margins
  assumed_inputs | findings[{severity, code, message, action}] | advances
```

→ `docs/01 §3 P1`, `docs/05 §5`, `docs/09 §7`

**발표 스크립트**
> 그럼 LLM은 뭘 하냐. 네 가지입니다.
>
> 첫째, 자연어 요청을 계산 입력으로 바꿉니다. 그리고 없는 입력은 물어봅니다. 예를 들어 형태 관찰인지 추적인지에 따라 최적 픽셀 크기가 반대 방향이니까, 이건 기본값을 쓰지 않고 반드시 질문하게 되어 있습니다.
>
> 둘째, 정성 판단 렌즈입니다. 챔버 설계, 다중 산란, 광독성, 삼중항 블링킹 같은 건 식이 없거나 입력이 아무데도 기록돼 있지 않습니다. 이건 LLM이 판단합니다.
>
> 셋째, 분석 코드를 읽습니다. 어떤 분석 스크립트를 돌릴 건지가 설정 요구사항을 바꿉니다. 픽셀 크기가 확산계수에는 치명적이고 화학량론에는 무관한 것처럼요. 이건 렌즈 6만 합니다.
>
> 넷째, 대화에서 전문성을 감지해서 저장을 제안합니다.
>
> 중요한 건 LLM 렌즈도 코드 렌즈와 **같은 스키마**로 답한다는 겁니다. 그래서 나중에 위원회가 8개 판정을 같은 방식으로 취합할 수 있습니다.

---

## Slide 7 — 요소 ③ Verdict 스키마 ★

**한 줄 메시지**: `advances = passed AND evidence == "measured"`. 위원회는 이것만 본다.

**슬라이드 본문**
- 판정을 **두 축으로 분리**한 것이 이 시스템에서 사실상 유일하게 새로운 부분
  - `status` — 물리적으로 타당한가 (`PASS` / `PASS_WITH_CHANGES` / `FAIL` / `BLOCKED`)
  - `evidence` — 쓴 값이 측정값인가 카탈로그 값인가 (`measured` / `assumed`)
- 카탈로그 명목값으로 계산해서 `PASS`가 나와도 `advances`는 `NO`
- 추정한 것은 전부 `assumed_inputs`에 열거됨 → 뭘 재야 하는지가 그대로 다음 할 일 목록
- **8개 렌즈 전부 이 규칙 적용** (2026-08-17 커밋에서 `feasibility >= TIGHT`까지 조건에 포함)

**도표 (English)**

```python
@dataclass
class LensVerdict:
    lens: str
    status: str               # PASS | PASS_WITH_CHANGES | FAIL | BLOCKED
    feasibility: str          # ROUTINE .. INFEASIBLE
    evidence: str             # measured | assumed
    margins: dict[str, float] # m = achieved / required, per gate
    assumed_inputs: list[str]
    findings: list[Finding]   # severity, code, message, action, numbers
    interventions: list[Intervention]
    advances: bool            # passed AND evidence == "measured"
                              #   AND feasibility >= TIGHT
                              #   AND no hard gate below m = 1.0
```

```
evidence: assumed   confidence: low   advances: NO
assumed:  ATTO647N spectra, FF01-692/40, Plan Apo 100x Oil transmission,
          Spectra.Red power at sample
```

→ `docs/01 §3 P1`, `docs/05 §5`

**발표 스크립트**
> 이 슬라이드가 오늘 발표에서 하나만 기억하시면 되는 부분입니다.
>
> 보통 게이트는 통과/실패 하나로 답합니다. 여기서는 두 축으로 쪼갰습니다. 하나는 "물리적으로 타당한가", 다른 하나는 "그 판단에 쓴 값이 실제 측정값인가 아니면 카탈로그 명목값인가"입니다.
>
> 그리고 위원회가 보는 건 `advances` 하나인데, 이게 "통과했고 **그리고** 근거가 측정값이다"입니다. 즉 카탈로그 값으로 계산해서 PASS가 나와도 통과가 안 됩니다.
>
> 이게 왜 중요하냐면 — 데이터시트 곡선으로 계산한 SNR 8.2와 실제로 측정해서 얻은 SNR 8.2는 신뢰도가 완전히 다른데, 보통은 둘 다 그냥 "8.2"로 보고됩니다. 그 구분이 코드 레벨에서 강제됩니다.
>
> 부수 효과가 하나 더 있는데, 추정한 항목이 전부 `assumed_inputs`에 열거됩니다. 그러니까 이 리스트가 그대로 "다음에 뭘 재야 하는가" 목록이 됩니다. 실험 준비 계획이 자동으로 나오는 셈입니다.

---

## Slide 8 — 요소 ④ BLOCKED ≠ FAIL, 그리고 난이도 등급

**한 줄 메시지**: 이진 판정은 사람이 게이트를 끄게 만든다. 그래서 "얼마나 어려운지"를 답한다.

**슬라이드 본문**

**BLOCKED와 FAIL은 다르다**
- `FAIL` = 이 설정은 물리적으로 나쁘다 → **설정을 바꿔라**
- `BLOCKED` = 판단할 근거가 없다 → **재러 가라, 데이터시트를 찾아라**
- 둘 다 다음 단계로 안 가지만 사람이 할 행동이 다르다

**이진 판정을 버린 이유**
- 측정 한계에서 찍어야 하는 실험은 실제로 존재함. 신호가 약한 걸 알면서도 데이터가 필요한 경우
- 이때 게이트가 `FAIL`밖에 못 내면 → 사람이 게이트를 끄거나, 무시하는 습관이 생김. 둘 다 최악

**게이트 3종 — 미달 시 결과가 다르므로 처리도 달라야 함**

**도표 (English)**

```
kind    if it falls short                             proceed?
──────  ─────────────────────────────────────────────  ──────────────────────────
soft    quality degrades only, data stays valid        yes, flag the difficulty
bias    THE RESULT IS WRONG. data looks plausible      only with a correction
hard    it simply does not work                        no, stop

margin  m = achieved / required
  m >= 3      ROUTINE      comfortable headroom
  1.5 - 3     COMFORTABLE  normal
  1.0 - 1.5   TIGHT        fails if conditions slip slightly
  0.5 - 1.0   HARD         at the limit. low yield. MAY PROCEED
  0.2 - 0.5   MARGINAL     interpret with great care
  < 0.2       INFEASIBLE   impossible without improvement

overall grade = grade of the WORST soft/bias gate
                (any hard gate m < 1 -> stop regardless of the grade)
```

```
feasibility:  HARD  (m = 0.64, deciding gate: G7 SNR)
  hard gates   all pass
  bias gates   G8 motion blur m=0.9 -> correction mandatory (Savin-Doyle)
  soft gates   G7 SNR m=0.64  <- bottleneck
               G11 statistical power m=1.8
```

→ `docs/05 §1–3`, `docs/06 E2·E4`

**발표 스크립트**
> 판정 종류에 대한 얘기입니다. 두 가지 구분이 있습니다.
>
> 먼저 BLOCKED와 FAIL이 다릅니다. FAIL은 "이 설정이 물리적으로 나쁘다"니까 설정을 바꾸면 됩니다. BLOCKED는 "판단할 근거가 없다"니까 재러 가야 합니다. 둘 다 통과는 아닌데 사람이 할 행동이 완전히 다릅니다. 지금 이 시스템이 내는 판정 대부분이 BLOCKED인데, 그게 정상입니다.
>
> 두 번째로, 처음엔 PASS/FAIL 이진으로 설계했다가 버렸습니다. 이유가 실용적입니다. 측정 한계에서 찍어야 하는 실험이 실제로 있잖아요. 신호 약한 거 알지만 그래도 데이터가 필요한 경우. 그때 게이트가 FAIL만 낼 수 있으면 사람이 게이트를 꺼버립니다. 아니면 무시하는 습관이 생깁니다. 둘 다 최악이라서, "얼마나 어려운지"를 등급으로 답하게 바꿨습니다.
>
> 그리고 게이트를 세 종류로 나눴습니다. soft는 화질만 나빠지는 것, hard는 아예 안 되는 것, 그리고 **bias가 제일 위험합니다.** 데이터가 그럴싸하게 나오는데 해석이 틀립니다. 나중에 알아채기가 제일 어렵습니다. 뒤에서 실제 예를 보여드리겠습니다.

---

## Slide 9 — 요소 ⑤ 문제제기 A: 개선 제안 = 감도 분석

**한 줄 메시지**: "어렵다"만 말하면 쓸모없다. 병목 게이트의 마진을 파라미터로 편미분해서 개선 배율을 계산한다.

**슬라이드 본문**
- 각 게이트에 `sensitivity()`를 붙여 파라미터별 마진 변화(편미분/유한차분)를 계산
- 개입안을 **비용 계층**으로 묶어 제시: tier 0 설정(무료) → 1 광로 → 2 시약 → 3 부품 → 4 장비 → 5 설계
- 이 표에서 바로 보이는 3가지: ① **가장 큰 이득이 가장 싸다** ② 밝아 보이는 색소가 실제로 더 어두울 수 있다 ③ **모든 개선안은 게이트를 다시 통과해야 한다**

**도표 (English) — SNR short by 1.6x**

```
improvement candidates - computed gains

tier 0 (free)
  200MHz 12bit -> 100MHz 16bit       x3.4   effective noise 4.65 -> 1.35 e-
                                            but check max fps (revisit G9)
  2x light level                     x1.4   sqrt(2), shot-noise limited
                                            2x bleaching dose -> recheck G10
  2x2 binning                        x2.0   effective pixel 110 -> 220 nm
                                            G5 bias if tracking -> NOT advised
tier 1 (light path)
  emission filter 692/40 -> 685/70   x1.4   collection 21% -> 30%
tier 2 (reagents)
  ATTO647N -> Alexa Fluor 647        x1.8   epsilon 150k -> 270k
                                            BUT Phi 0.65 -> 0.33  => net x0.9
                                            -> a net LOSS in brightness eps*Phi
tier 3 (parts)
  objective NA 1.45 -> 1.49          x1.15  eta_geo 0.352 -> 0.404
                                            poor cost-effectiveness
tier 5 (design)
  frame rate 20 -> 10 Hz             x1.4   2x exposure -> sqrt(2)
                                            risks missing the 50 ms tau_c
```

→ `docs/05 §4`, `docs/06 E5`

**발표 스크립트**
> "이 실험 어렵습니다"까지만 말하면 아무 쓸모가 없습니다. 그래서 병목 게이트의 마진을 파라미터마다 편미분해서, 뭘 바꾸면 몇 배 좋아지는지를 계산해서 같이 냅니다.
>
> 이 표를 보시면 재밌는 게 세 개 나옵니다.
>
> 첫째, **가장 큰 이득이 가장 쌉니다.** 12비트를 16비트로 바꾸는 게 3.4배인데 공짜입니다. 대물렌즈를 NA 1.45에서 1.49로 바꾸는 게 1.15배인데 수백만원입니다. 직관은 반대로 갑니다.
>
> 둘째, 밝아 보이는 색소가 실제로 더 어두울 수 있습니다. ATTO647N을 Alexa 647로 바꾸면 흡광계수가 1.8배인데 양자수율이 절반으로 떨어져서, ε·Φ로 보면 오히려 손해입니다. ε만 보고 판단하면 틀립니다.
>
> 셋째, **모든 개선안이 다른 게이트를 건드립니다.** 광량 2배는 표백 선량 2배고, 비닝은 샘플링을 망칩니다. 그래서 개선 제안도 게이트를 다시 통과해야 합니다.

---

## Slide 10 — 요소 ⑥ 문제제기 B: 교착 상태를 사람에게

**한 줄 메시지**: 요구사항이 물리적으로 양립 불가능하면, **그 충돌 자체가 산출물**이다.

**슬라이드 본문**
- 전원 합의만 통과. 하지만 렌즈 6개 만장일치는 쉽게 교착됨 → 규칙을 명시
- 모든 FAIL은 **구체적 수정 지시**를 동반해야 함 (불평 금지)
- 수정 → 재심사 루프는 **최대 3회**
- 3라운드에 수렴 안 하면 **충돌을 사람에게 제시**하고, 선택지마다 무엇을 양보하는지 계산해서 붙임
- **이게 실패가 아니라 정상 동작.** 실패는 양립 불가능한 요구를 억지로 봉합하는 것

**도표 (English)**

```
There are incompatible requirements.

  Lens 5 (photo-perturbation): light level <= 5%. Above that the Janus
                               particles are light-driven.
                               Basis: [kb/samples/active-janus-colloid.md]
  Lens 2 (detection):          reaching SNR 5 at 20 Hz needs at least 30%.
                               Basis: photon budget calculation [details]

Options:
  (a) lower frame rate to 10 Hz -> light level drops to 15%. STILL above 5%
  (b) brighter label            -> required light drops proportionally.
                                   reagent change needed
  (c) accept the light-driven perturbation
                                -> the measured quantity CHANGES from
                                   "passive diffusion" to "light-driven motion"
  (d) excite at a different wavelength
                                -> best if it avoids the Janus absorption band.
                                   needs the absorption spectrum

What would you like to concede?
```

→ `docs/01 §3 P5`, `docs/05 §6`

**발표 스크립트**
> 위원회가 만장일치제인데, 렌즈가 6개면 당연히 교착됩니다. 그래서 규칙을 세 개 박아놨습니다. 모든 FAIL은 구체적 수정 지시를 달아야 합니다. 불평만 하면 안 됩니다. 수정하고 다시 심사하는 루프는 최대 3번입니다. 그리고 3번 안에 수렴 안 하면 충돌 자체를 사람에게 넘깁니다.
>
> 이 예시가 실제로 나올 수 있는 상황입니다. 광섭동 렌즈는 야누스 입자가 광구동되니까 광량 5% 이하를 요구하고, 검출 렌즈는 20 Hz에서 SNR 5를 맞추려면 최소 30%가 필요하다고 합니다. 이건 봉합이 안 됩니다.
>
> 그러면 선택지를 계산해서 냅니다. 프레임률 낮추면 15%까지 내려가는데 여전히 5% 초과라서 안 됩니다. 표지를 밝은 걸로 바꾸는 건 됩니다. 아니면 광구동을 받아들이는데, 그러면 **측정하는 물리량 자체가 "수동 확산"에서 "광구동 운동"으로 바뀝니다.** 이건 실험의 의미가 바뀌는 거니까 사람이 결정해야 합니다.
>
> 그래서 저는 이 출력을 실패로 안 봅니다. 이게 정상 동작입니다. 실패는 양립 불가능한 요구를 억지로 하나의 숫자로 봉합해서 내놓는 겁니다.

---

## Slide 11 — 지식베이스의 역할: 3-tier normalization

**한 줄 메시지**: 물리량(tier 3)만 시스템을 건너간다. 지금 tier 3가 세 칸 비어 있어서 이전이 불가능하다.

**슬라이드 본문**
- 원본은 절대 지우지 않음(tier 1) → 장치 값(tier 2) → 물리량(tier 3)으로 3단 정규화
- tier 2는 **같은 시스템 안에서만** 유효. tier 3만 시스템 독립
- tier 3가 비면 시스템 간 이전이 **원리적으로 불가능** — 그리고 그게 지금 아카이브의 상태

**도표 (English)**

```
tier 1  raw       "Spectra-Red_Level": "10"        verbatim. never lost.
tier 2  device    source=Spectra, line=Red, 10%    instrument-bound. valid only
                                                   within the same system.
tier 3  physical  640 +/- 15 nm, ? mW/cm2 @sample  instrument-independent.
                                                   ONLY this transfers.

physical quantity        formula                      status today
──────────────────────── ──────────────────────────── ────────────────
effective pixel size     p_sensor*B/(M_obj*M_int)     computable
excitation band          source x ex-filter x dichroic  partial
emission band            dichroic x em-filter         MISSING
irradiance at sample     P/A   <- power meter         MISSING
total photon dose        irradiance * t_exp * N       MISSING
measured frame rate      (N-1)/dt_total (tail parse)  computable
collection solid angle   (1-cos theta)/2              NA unverified
```

→ `docs/01 §3 P2`, `docs/02 §2`, `docs/03`

**발표 스크립트**
> 지식베이스가 하는 첫 번째 일이 정규화입니다. 3단으로 나눕니다.
>
> 1단은 원본입니다. `Spectra-Red_Level: 10` 이런 문자열 그대로. 절대 안 지웁니다. 나중에 해석이 틀렸다는 걸 알게 됐을 때 되돌릴 수 있어야 하니까요.
>
> 2단은 장치 값입니다. "Spectra 광원의 Red 라인, 10%". 이건 같은 시스템 안에서만 의미가 있습니다.
>
> 3단이 물리량입니다. "640±15 nm, 시료면에서 몇 mW/cm²". 이것만 장비를 건너갑니다.
>
> 아래 표에서 보시면, 지금 3단에 세 칸이 비어 있습니다. 방출 밴드, 시료면 조도, 총 광자 선량. 그래서 지금은 시스템 간 이전이 원리적으로 불가능합니다. 코드가 없어서가 아니고 **값이 없어서** 안 되는 겁니다.

---

## Slide 12 — 지식베이스의 구성

**한 줄 메시지**: markdown + SQLite만. vector DB를 쓰지 않는 건 의도적이다.

**슬라이드 본문**
- 요구 조건 3개: 사람이 열어서 고칠 수 있고, 에이전트가 질의할 수 있고, "왜 이 값인지"가 역추적 가능해야 함
- **vector DB를 안 쓰는 이유**: 임베딩 검색은 "왜 이 선례를 골랐는지" 설명이 안 되고, 잘못된 추천의 원인을 역추적할 수 없다. 선례 검색은 명시적 SQL 조건으로 (색소·대물렌즈·시간 스케일·샘플계)
- 정량 인덱스는 SQLite 한 테이블. **`measured_fps`와 `requested_fps`를 분리 저장하는 것이 핵심** — 아카이브에서 요청 10 ms가 실측 35.67 ms였음. 요청만 기록하면 선례가 거짓말을 한다

**도표 (English)**

```
kb\
├── systems\        one microscope = one file. YAML front matter + markdown body
│                     current.md (748 lines), legacy dossiers, _template.md
├── samples\        imaging recipes per sample system. survives hardware change
│                     characteristic_scales (tau_c, ell_c) is a MANDATORY field
├── calibrations\   measured values. date and measurer mandatory
│                     camera-readout.yaml, disk-bandwidth.yaml (both 2026-08-12)
├── decisions\      recommendation -> execution -> outcome  = the learning loop
├── expertise\      expertise captured from conversation (docs/09)
└── envelope.sqlite quantitative index of 2,343 acquisitions (generated)

data\               registries, filled in by hand
  fluorophores.yaml  filters.yaml  light_sources.yaml  detectors.yaml
  objectives.yaml    spectra\ (measured vendor curves)
```

→ `docs/01 §3 P4`, `docs/02 §1·§6`

**발표 스크립트**
> 지식베이스 구성입니다. 디렉터리가 다섯 개입니다. 시스템 명세서, 샘플계별 레시피, 측정 캘리브레이션, 결정 로그, 그리고 전문성.
>
> 형식은 markdown하고 SQLite뿐입니다. vector DB를 안 쓰는 게 의도적인 선택인데, 이유는 설명 가능성입니다. 임베딩 검색은 "왜 이 선례를 골랐는지"를 설명을 못 합니다. 그리고 추천이 틀렸을 때 원인을 역추적할 수가 없습니다. 그래서 선례 검색은 명시적 SQL 조건으로 합니다. 색소, 대물렌즈, 시간 스케일, 샘플계로 걸러서요.
>
> 그리고 사람이 열어서 고칠 수 있어야 하고, git이 이력을 남겨야 합니다. 지식이 왜 바뀌었는지가 그 자체로 지식이니까요.
>
> SQLite 스키마에서 하나만 강조하면, **요청 프레임률과 실측 프레임률을 따로 저장합니다.** 아카이브에 요청 10 ms인데 실측 35.67 ms인 게 있습니다. 3배 차이입니다. 요청값만 기록하면 선례가 거짓말을 합니다.

---

## Slide 13 — 지식베이스: 장부 밖 설정 (off-ledger)

**한 줄 메시지**: 소프트웨어가 기록하지 않는 설정은, 사람이 그 자리에서 안 적으면 영구히 소실된다.

**슬라이드 본문**
- Micro-Manager도 NIS도 기록하지 않는 설정이 실재함 → **1급 시민으로 취급**
- 광 트위저 파워는 폴더명 `OT0.005`에만 남아 있고, 피에조 스테이지는 **아무 데도 없음**
- 대책: 모든 취득에 `acquisition.yaml` 사이드카를 남기고, **에이전트가 장부 밖 항목을 명시적으로 물어본다.** 안 물어보면 정보는 영구 소실
- 하드웨어·MM·NIS **3중 교차 점검 표**로 어느 장치가 어디에 등록됐는지 관리 (양쪽 등록 시 동시 접근 충돌 위험까지)

**도표 (English)**

```
device                  physical  in MM  in NIS  state recorded     controlled by
─────────────────────── ───────── ────── ─────── ────────────────── ────────────
camera / objective      yes       yes    yes     yes                MM
filter cube turret      yes       yes    yes     label mangled      MM
filter wheel            yes       yes    ?       passbands MISSING  MM
1.5x intermediate mag   yes       yes    ?       yes                MM
optical tweezers        yes       NO     NO      FOLDER NAME ONLY   separate
piezo stage             yes       NO     NO      NOWHERE            separate Python
DMD                     yes       yes    ?       no                 MM (pymmcore)

why a three-way check is needed:
  in MM not NIS  -> data shot with NIS does not retain that setting
  in NIS not MM  -> it drops out of MM automation
  in neither     -> no software records it. a human must write it down
  in both        -> SIMULTANEOUS-ACCESS CONFLICT risk. if one side holds the
                    device the other fails - or worse, quietly proceeds in the
                    wrong state
```

→ `docs/01 §3 P3`, `docs/02 §4–5`

**발표 스크립트**
> 이건 실무적으로 제일 아픈 부분입니다. 소프트웨어가 기록을 안 하는 설정이 실제로 있습니다.
>
> 광 트위저 파워는 MM에도 NIS에도 안 들어갑니다. 폴더 이름에 `OT0.005`로 적어놓은 게 유일한 기록입니다. 피에조 스테이지는 아예 아무 데도 없습니다. 별도 프로그램으로 돌리니까요.
>
> 그래서 이런 항목을 1급 시민으로 취급합니다. 모든 취득에 `acquisition.yaml` 사이드카를 남기고, **에이전트가 이걸 명시적으로 물어봅니다.** 안 물어보면 그 정보는 그날로 영구 소실입니다. 지금 아카이브가 그 증거고요.
>
> 그리고 아래 표가 하드웨어, MM, NIS 3중 교차 점검입니다. 이게 왜 필요하냐면 — 한쪽에만 등록된 장치는 다른 쪽으로 찍으면 설정이 안 남고, 양쪽에 등록되면 동시 접근 충돌이 납니다. 한쪽이 장치를 잡고 있으면 다른 쪽이 실패하는데, 더 나쁜 경우는 조용히 틀린 상태로 진행하는 겁니다.

---

## Slide 14 — 지식베이스: 전문성 엔트리와 수집 3경로 ★

**한 줄 메시지**: `Why`와 `반증 조건(falsifying condition)`이 **필수 필드**다. 없으면 저장하지 않는다.

**슬라이드 본문**

**왜 필수인가**
- `Why` 없으면 후배가 일반화를 못 함
  - "노출 80 ms 쓰세요" → 다른 샘플에 그대로 적용 → 실패
  - "이 샘플은 표백이 빠르니 duty 30% 이하여야 하고, 12 Hz에서 그게 80 ms다" → 일반화됨
- `반증 조건` 없으면 지식이 **늙지 않음.** 장비가 바뀌어도 살아남아서 계속 틀린 조언을 함
- 출처별로 신뢰도와 반박 방법이 다름. **`precedent`(선례)가 가장 약한 출처** — 과거에 그렇게 했다는 게 그게 옳았다는 뜻이 아님

**수집 3경로**
1. **기회적 포착** — 대화 중 비자명한 판단이 나오면 감지해서 저장 제안. 신호: 인과 주장 / 조건부 규칙 / 금지 / 예외 / **사용자의 정정(가장 가치 높음)**
2. **간극 주도 (가장 효율적)** — 게이트가 `BLOCKED`를 낼 때마다 그게 KB 간극. 답을 받으면 판단 근거까지 함께 저장
3. **계획된 인터뷰** — KB의 빈 영역을 에이전트가 찾아서 물어봄. 최우선 질문: **"뭘 보면 실패했다고 판단하십니까"**

**도표 (English)**

```
source           trust            how to refute            example
──────────────── ──────────────── ──────────────────────── ────────────────────────
measurement      highest          re-measure               mW from a power meter
datasheet        high             check the part number    filter transmission curve
calculation      = its inputs     validate the inputs      collection eff. 0.352
expert-judgment  until falsified  observe the condition    "changes in 30 min"
literature       citation needed  check the original       Savin-Doyle correction
precedent        WEAKEST          the physics gates        "we used 80 ms last time"
```

```
Gate:   BLOCKED - passband of 'DA/FI/TR10Empty' unknown
Agent:  Do you know what this cube actually is?
User:   Oh, that one is really a quad-band. The label is just old and
        never got updated.
Agent:  -> (1) update data/filters.yaml
        -> (2) create a kb/expertise entry:
               "MM labels are sometimes not updated after a part is swapped.
                Never take a label as evidence for a part."
                        ^^^ the second store is the real gain
```

→ `docs/09 §1–3`

**발표 스크립트**
> 여기가 이 프로젝트의 진짜 핵심입니다. 전문성을 어떻게 저장하느냐.
>
> 엔트리에 필수 필드가 두 개 있습니다. `Why`하고 `반증 조건`입니다. 이게 없으면 저장을 안 합니다.
>
> `Why`가 왜 필수냐면, "노출 80 ms 쓰세요"만 저장하면 후배가 다른 샘플에 그대로 적용해서 실패합니다. "이 샘플은 표백이 빨라서 duty 30% 이하로 가야 하고, 12 Hz에서 그게 80 ms다"라고 저장하면 일반화가 됩니다.
>
> `반증 조건`이 왜 필수냐면 — 이게 없으면 지식이 늙지 않습니다. 장비를 바꿨는데도 그 지식이 살아남아서 계속 틀린 조언을 합니다. 그래서 "어떤 관찰이 이 판단을 틀리게 만드는가"를 항상 물어봅니다. 이건 사람만 답할 수 있습니다.
>
> 출처 표에서 하나 보시면, **선례가 가장 약한 출처입니다.** 과거에 그렇게 했다는 게 옳았다는 뜻이 아니니까요. 물리 게이트가 선례를 반박하면 선례 출처 항목은 자동으로 강등됩니다.
>
> 수집 경로가 세 개인데, **간극 주도가 제일 효율적입니다.** 게이트가 BLOCKED를 낼 때마다 그게 정확히 KB의 빈칸이니까요. 아래 예시가 그건데, 여기서 진짜 이득은 두 번째 저장입니다. 필터 정보는 한 번 쓰고 끝인데, "라벨을 부품의 증거로 삼지 말라"는 일반 규칙은 계속 쓰입니다.
>
> 그리고 계획된 인터뷰에서 최우선 질문이 **"뭘 보면 실패했다고 판단하십니까"** 입니다. 이건 전문가만 갖고 있고 후배가 가장 늦게 배우는 지식입니다.

---

## Slide 15 — 지식베이스: 학습 루프와 충돌 기록

**한 줄 메시지**: 계산이 전문가 판단을 자동으로 이기지 않는다. 충돌 지점에서 최고의 지식이 나온다.

**슬라이드 본문**
- 추천이 실제로 맞았는지 기록이 없으면 시스템은 개선되지 않음 → `kb/decisions/`에 추천 → 실행 → 결과 → 예측 대비 오차를 기록
- 이게 쌓이면 게이트 임계값을 **경험적으로** 조정할 수 있음
- 계산과 전문가 판단이 충돌할 때 처리 순서: ① 계산의 **입력**을 먼저 의심 (보통 항이 빠져 있음) ② 입력이 맞는데도 안 맞으면 **모델이 부족한 것** ③ 어느 쪽이든 **충돌 자체를 KB에 기록**
- 사용자가 게이트를 강제로 무시하는 것도 허용해야 하지만, **무시했다는 사실이 반드시 기록되어야 함**

**도표 (English)**

```
Computation:  SNR 8.2 - sufficient
User:         No, you can't see anything at that setting.

id: atps-background-fluorescence-dominates
source: expert-judgment + calculation-mismatch
## Observed mismatch
  predicted SNR 8.2, but in practice the particles were invisible
## Cause (hypothesis)
  autofluorescence of the dextran phase itself enters the background -
  a term absent from the current model
## Action
  - add a measured background frame to the acquisition protocol
  - record the background level in kb/samples/atps-dextran-peg.md
  - Lens 6: with no measured background, report SNR as an UPPER BOUND only
```

→ `docs/02 §9`, `docs/09 §4`, `docs/05 §7`

**발표 스크립트**
> 추천이 실제로 맞았는지를 기록하지 않으면 시스템이 안 좋아집니다. 그래서 결정 로그를 남깁니다. 추천한 설정, 실제로 쓴 설정, 결과, 그리고 예측 대비 오차. 이게 쌓이면 게이트 임계값을 경험적으로 조정할 수 있습니다.
>
> 그리고 여기서 중요한 원칙이 하나 있습니다. **계산이 자동으로 이기지 않습니다.** 계산은 SNR 8.2로 충분하다고 하는데 사람이 "그 설정으로는 아무것도 안 보인다"고 하는 상황이요.
>
> 이럴 때 순서가 있습니다. 먼저 계산의 입력을 의심합니다. 보통 항이 빠져 있습니다. 이 경우에는 배경 형광이 모델에 없었던 겁니다 — 실제로 저희 SNR 식에서 배경항은 사용자 입력이고 기본값이 없습니다. 입력이 맞는데도 안 맞으면 모델이 부족한 겁니다.
>
> 어느 쪽이든 **충돌 자체를 KB에 기록합니다.** 왜냐면 가장 좋은 지식이 충돌 지점에서 나오기 때문입니다. 그래서 충돌을 숨기지 않습니다.

---

## Slide 16 — 워크플로우 A: L0 → L5 계층

**한 줄 메시지**: 원본은 읽기 전용, KB만 영속. 그 위에 추론 → 위원회 → 출력.

**도표 (English)**

```
L0  Sources (READ-ONLY)
    MM metadata *_metadata.txt | MM .cfg | NIS-Elements settings
    hardware datasheets | filter/dye spectral curves | protocol documents
    analysis code (D:\codes)  <- which analysis you run SETS the requirements
                    |
L1  Ingest & normalize
    streaming parser (headers only: Summary + first FrameKey + 96 kB tail)
    handles the MM 1.4 / 2.0 dual schema
    3-tier normalization: raw -> device -> physical
    system fingerprint decides "which microscope is this" automatically
                    |
L2  Knowledge base (PERSISTENT)
    kb/systems   kb/calibrations   kb/decisions   kb/expertise   data/
                    |
L3  Inference
    find precedent -> convert to physical -> reproject onto current instrument
    -> solve the constraints (exposure, light level, binning, ROI
       under required SNR / time resolution / photon budget)
                    |
L4  Committee
    hard gates (code) + per-subsystem lenses 6+2
    nothing passes unless every lens ADVANCEs
    every FAIL must carry a concrete fix instruction
                    |
L5  Output
    setting proposal (rationale, assumptions, uncertainty, alternatives)
    MM Channel preset | off-ledger checklist | experiment plan
```

→ `docs/01 §2`

**발표 스크립트**
> 워크플로우를 계층으로 보면 여섯 단입니다.
>
> L0가 원본인데, 읽기 전용입니다. 메타데이터, 설정 파일, 데이터시트, 스펙트럼 곡선, 그리고 **분석 코드**. 분석 코드가 여기 들어가는 게 중요한데, 어떤 분석을 돌릴지가 설정 요구사항을 결정하기 때문입니다.
>
> L1이 파싱과 정규화입니다. 메타데이터 파일이 최대 44 MB까지 있어서 전체를 읽지 않고 헤더만 스트리밍합니다. Summary하고 첫 FrameKey하고 꼬리 96 kB만요. 꼬리를 읽는 건 실측 프레임률과 드롭을 알아내기 위해서입니다. 그리고 MM 1.4랑 2.0이 스키마가 달라서 둘 다 처리해야 합니다. 아카이브의 91%가 1.4입니다.
>
> L2가 지식베이스, L3이 추론, L4가 위원회, L5가 출력입니다. 여기서 영속적인 건 L2 하나뿐입니다.

---

## Slide 17 — 워크플로우 B: 결정 순서 ①–⑨

**한 줄 메시지**: 자유도를 고정하는 순서는 물리가 정한다. 사이클 두 개가 수렴하지 않으면 요구사항이 양립 불가능하다는 뜻.

**슬라이드 본문**
- 나중 단계가 앞 단계를 무효화하지 않는 순서가 존재하고, 그 순서는 물리가 정함
- ②↔⑥, ③↔⑧이 **사이클.** 수렴 안 하면 그 사실 자체가 출력
- ①(측정할 물리량과 목표 정밀도)은 **사람이 준다.** 여기서 시작 안 하면 나머지가 정의되지 않음
- ①'의 특성 시간·길이(τ_c, ℓ_c)는 `kb/samples/`에서. 측정 못 하면 이론 추정 + `evidence: assumed` — **값은 쓰되 확정은 안 함**

**도표 (English)**

```
(1)  physical quantity to measure + target precision   <- THE HUMAN GIVES THIS
      |
(1') system's characteristic time tau_c, length ell_c  <- kb/samples/<sys>.md
      |    (measure if possible, else theoretical estimate + evidence=assumed)
(2)  tau_c  ->  required frame rate f    (tau_c/10, or f >= 10*f_c w/ tweezers)
      |
(3)  f  ->  exposure ceiling  t_exp <= 1/f - t_readout  + motion-blur ceiling
      |
(4)  target precision  ->  required detected photons N
      |
(5)  N / t_exp  ->  required electron rate  ->  required irradiance
      |
(6)  irradiance  ->  photobleaching dose + photo-perturbation check
      |                                          if exceeded, BACK TO (2)
(7)  ell_c + objective x int.mag x binning  ->  sampling check (task-dependent)
      |
(8)  ROI  ->  recompute t_readout + statistical power check   BACK TO (3)
      |
(9)  data rate / buffer / storage check

cycles: (2)<->(6) and (3)<->(8).  If they do not converge, the requirements are
INCOMPATIBLE - and that fact is itself the output.
```

→ `docs/04 §1`

**발표 스크립트**
> 설정 자유도를 아무 순서로나 고정할 수 없습니다. 나중 단계가 앞 단계를 무효화하지 않는 순서가 있고, 그건 물리가 정합니다.
>
> 시작은 ①번, "무슨 물리량을 얼마나 정확하게 재고 싶은가"입니다. 이건 사람이 줘야 합니다. 이게 없으면 나머지가 정의가 안 됩니다.
>
> 그 다음 ①'번이 샘플계의 특성 시간과 길이입니다. 이게 프레임률을 결정합니다. 특성 시간의 10분의 1로 잡으니까요. 트위저를 쓰면 코너 주파수의 10배 이상이어야 합니다.
>
> 프레임률이 정해지면 노출 상한이 나오고, 목표 정밀도에서 필요한 광자 수가 나오고, 그걸 노출 시간으로 나누면 필요한 조도가 나옵니다. 그 조도로 표백 선량을 계산해서 초과하면 ②번으로 돌아갑니다.
>
> 여기서 **사이클이 두 개** 있습니다. 프레임률과 광 선량, 그리고 노출과 ROI. 이게 수렴하지 않으면 요구사항이 양립 불가능하다는 뜻이고, 그 사실 자체가 출력입니다. 아까 보여드린 교착 출력이 여기서 나옵니다.

---

## Slide 18 — 워크플로우 C: 위원회 6 + 2

**한 줄 메시지**: 학문 분야가 아니라 **서브시스템**으로 쪼갰다. 그래서 FAIL이 곧 수정 지시가 된다.

**슬라이드 본문**
- 학문(광학/콜로이드/이론)으로 쪼개면 관할이 겹쳐서 "다들 대충 괜찮다고 본다"는 판정이 나옴
- 서브시스템으로 쪼개면 **각 렌즈가 소유한 설정**이 명확 → FAIL이 이미 수정 지시
- 렌즈 4와 5를 분리한 이유: 샘플의 **기하/광학 성질**과 **광반응성**은 다른 전문성이고 결론이 반대로 나온다. 하나로 묶으면 그 충돌이 숨는다

**도표 (English)**

```
STANDING (6)
#  lens                    owns                              basis         code
── ─────────────────────── ───────────────────────────────── ───────────── ──────────
1  Optics                  filters, dichroics, ND, objective spectral      optics/
                           light path                        integration
2  Detection               exposure, binning, ROI, readout,  photon        detection/
                           gain, frame interval              budget / SNR
3  Compute resources       frame rate, buffer, storage       bandwidth     compute/
4  Sample geometry&optics  objective, immersion, coverslip,  RI, WD,       sample/
                           imaging depth                     aberration
5  Photo-perturbation      light level, duty, total dose,    bleaching,    photo/
                           wavelength                        light-driving
6  Measurement validity    whether all of the above yields   bias +        validity/
                           the intended quantity, unbiased   qualitative

CONDITIONAL (2)
7  Optical tweezers        trap stiffness k, U/kT, f_c       computed      trapping/
                           (convened when tweezers in use)
8  Mechanical & environ.   drift, vibration, evaporation,    measured      stability/
                           PFS lock (convened when > 30 min) rates
```

→ `docs/01 §4`, `docs/05 §5`

**발표 스크립트**
> 위원회 구성입니다. 상임 6개, 조건부 2개.
>
> 여기서 설계 결정 하나를 짚고 싶은데, **학문 분야가 아니라 서브시스템으로 쪼갰습니다.** 광학 전문가, 콜로이드 전문가, 이론 전문가로 나누면 관할이 겹칩니다. 그러면 "다들 대충 괜찮다고 본다"는 판정이 나옵니다. 서브시스템으로 나누면 각 렌즈가 어떤 설정을 소유하는지가 명확해집니다. 그래서 FAIL이 나오면 그게 이미 수정 지시입니다. "노출을 바꿔라"가 검출 렌즈의 FAIL이니까요.
>
> 렌즈 4와 5를 왜 나눴냐는 질문이 나올 수 있는데 — 샘플의 기하·광학 성질하고 광반응성은 다른 전문성이고, 결론이 반대로 나옵니다. 하나로 묶으면 그 충돌이 숨습니다.
>
> 조건부 2개는 트위저 쓸 때, 그리고 30분 넘는 실험일 때 소집됩니다.

---

## Slide 19 — 워크플로우 D: 교차 렌즈 제약 ★

**한 줄 메시지**: 단일 렌즈가 못 잡는 것들 — 이게 위원회를 만든 실제 이유다.

**슬라이드 본문**
- 각 제약이 두 렌즈 사이에서만 보임. 한 관점 안에서는 문제가 없어 보임
- 특히 **모션 블러(2↔6)** 가 대표적인 bias 사례. MSD가 예쁜 직선으로 나오면서 기울기가 틀림

**도표 (English)**

```
constraint                 lenses  content
────────────────────────── ─────── ────────────────────────────────────────────
motion blur                2 <-> 6 travel during exposure > PSF -> MSD is
                                   UNDERESTIMATED
trap stiffness vs sampling 7 <-> 2 PSD calibration needs f_s >= 10 f_c. raising
                                   laser power raises f_c -> raises fps demand
light level vs driving     1 <-> 5 the extra light needed for SNR drives active
                                   particles
ROI vs statistics          3 <-> 6 shrinking ROI for speed cuts particle count
                                   -> weakens statistical power
pixel size                 2 <-> 6 morphology wants Nyquist; tracking optimal at
                                   sigma_PSF ~ pixel. OPPOSITE DIRECTIONS
immersion vs depth         4 <-> 1 RI mismatch grows spherical aberration with
                                   depth. ATPS: two phases, different RI
```

```
Savin-Doyle (1D, uniform exposure):
   <dx^2>_meas(tau) = 2D (tau - t_exp/3) + 2 eps^2
      -2D t_exp/3 : dynamic error (blur)      -> UNDERestimates MSD
      +2 eps^2    : static localization error -> OVERestimates MSD
   at short lags the two CANCEL -> a plausible but WRONG straight line
   gate G8:  |t_exp/3 / tau_min| < 0.1  <=>  t_exp < 0.3 tau_min  (duty <= 30%)
             archive duty 28% happens to pass. duty 100% -> 33% bias

pixel size, 100x NA1.45, lambda_em 668 nm:
   morphology (Nyquist p <= r/2):  r = 281 nm    ->  p <= 140 nm
   tracking   (p ~ sigma_PSF):     sigma = 97 nm ->  p ~  100 nm
   applying Nyquist to tracking and slicing finer MAKES PRECISION WORSE
```

→ `docs/01 §4`, `docs/04 §2·§5`, `docs/06 C6·D1`

**발표 스크립트**
> 이 슬라이드가 위원회를 만든 실제 이유입니다. 두 렌즈 사이에서만 보이는 제약들입니다.
>
> 대표적인 게 모션 블러입니다. 노출 시간 동안 입자가 PSF보다 많이 움직이면 신호가 번지는데, 더 나쁜 건 MSD에 계통 오차가 들어간다는 겁니다. Savin-Doyle 식을 보시면 항이 두 개인데, 블러 항은 MSD를 과소평가하고 정지 국소화 오차는 과대평가합니다. 짧은 lag에서 이 둘이 서로 상쇄되면서 **그럴싸한데 틀린 직선**이 나옵니다. 이걸 그대로 GSER에 넣으면 모듈러스가 틀립니다.
>
> 그래서 게이트가 duty를 30% 이하로 제한합니다. 저희 아카이브가 28%인데 우연히 통과합니다. duty를 100%로 밀면 가장 짧은 lag에서 33% 편향이 생깁니다.
>
> 두 번째 예가 픽셀 크기입니다. 형태를 볼 때는 Nyquist로 281 나노 해상도의 절반, 140 나노 이하로 가야 합니다. 추적할 때는 σ_PSF 근처인 100 나노가 최적입니다. **추적하면서 Nyquist를 기계적으로 적용해서 픽셀을 더 잘게 쪼개면 정밀도가 나빠집니다.** 배경이 있는 실제 조건에서는 유한한 최적 픽셀 크기가 존재하는데, 저희 랩 마이크로레올로지가 전부 그 영역입니다.

---

## Slide 20 — 워크플로우 E: 오케스트레이션 + 실행 예시

**한 줄 메시지**: 계산 렌즈가 먼저 돌고, **그 결과가 LLM 렌즈의 입력**이 된다.

**슬라이드 본문**
- 계산 렌즈(1·2·3·7) 병렬 → hard 게이트 m<1이면 즉시 중단하고 수정안 반환
- 판단 렌즈(4·5·6·8) 병렬, **계산 결과를 입력으로 받음**
- 합성: 난이도 = 최악의 soft/bias 게이트, 개선안 = 병목 게이트 감도 분석
- 렌즈 6은 **반드시 마지막.** 다른 렌즈의 판정이 주 입력이라서 먼저 돌리면 심사할 게 없음
- 계산 렌즈를 먼저 돌리는 이유: ① 물리적으로 불가능한 안을 LLM이 숙고하는 낭비 방지 ② LLM이 숫자를 스스로 만들지 못하게 강제

**도표 (English)**

```
generate proposal
   |
   +- computational lenses (1,2,3,7) in parallel   <- code. deterministic. fast
   |     any hard gate m<1 -> stop immediately, return a revision
   |
   +- judgment lenses (4,5,6,8) in parallel        <- LLM subagents
   |     receive the computational lens results AS INPUT
   |
   +- synthesis
   |     difficulty grade = worst soft/bias gate
   |     improvement proposals = sensitivity analysis of the bottleneck gate
   |
   +- verdict
        all advance  ->  confirmed
        otherwise    ->  re-propose with fix instructions (at most 3 rounds)
```

```
$ python -m optics.cli check config/channels/legacy-observed.yaml

channel: 647-Cy5 (as observed)  dye: SA647  ->  BLOCKED - insufficient information
  [FAIL] missing.filter_spec
         Element 'DA/FI/TR10Empty' has no passband on record
      -> Add it to data/filters.yaml with its part number and passband

--- with the specs filled in -------------------------------------------------
excitation efficiency  36.8%     spectral collection   21.1%
geometric collection   35.2%     total collection       7.4%
excitation blocking    11.5 OD   Stokes headroom       25 nm
Rayleigh resolution     281 nm   depth of field       483 nm

[WARN] emission.peak_clipped
       Detection band starts at 672 nm - past the ATTO647N emission peak
       (669 nm). You are discarding the brightest part.

element ablation
  candidate  FF01-640/14   signal +104%  based on approximate spectra, so not an
                                         instruction until confirmed on the bench
  required   FF01-692/40   signal  +43%  removing it drops blocking to 5.6 OD
  required   Di03-R405/... signal   +0%  structural element
```

→ `docs/05 §6`, `docs/01 §6`

**발표 스크립트**
> 오케스트레이션 순서입니다. 계산 렌즈 네 개가 병렬로 먼저 돕니다. hard 게이트가 하나라도 깨지면 거기서 멈추고 수정안을 반환합니다. LLM한테 안 넘깁니다.
>
> 통과하면 판단 렌즈들이 병렬로 도는데, **계산 결과를 입력으로 받습니다.** 이게 중요합니다. LLM이 숫자를 스스로 만들지 못하게 구조적으로 막는 겁니다.
>
> 렌즈 6은 반드시 마지막입니다. 다른 렌즈의 판정을 심사하는 게 주 업무라서, 먼저 돌리면 심사할 게 없습니다.
>
> 아래가 실제 출력입니다. 위쪽은 과거 셋업을 그대로 넣은 건데, 필터 통과대역이 기록에 없어서 BLOCKED입니다. 그리고 "필터 파일에 부품번호랑 통과대역을 추가하라"는 행동 지시가 붙습니다.
>
> 스펙을 채워 넣으면 실제 숫자가 나옵니다. 여기서 WARN 하나 보시면 — 검출 밴드가 672 나노부터 시작하는데 ATTO647N 방출 피크가 669 나노입니다. 즉 **가장 밝은 부분을 버리고 있습니다.** 이건 사람이 곡선 겹쳐봐야 알아채는 건데 게이트가 잡습니다.
>
> 맨 아래가 이 렌즈의 특기인 ablation 분석입니다. "이 필터를 빼면 어떻게 되나"를 추측이 아니라 **곱셈에서 그 항을 실제로 빼고 다시 계산해서** 답합니다. 신호가 오르면서 차단과 누화가 유지되면 제거를 제안하고, 아니면 왜 필요한지를 숫자로 설명합니다.

---

## Slide 21 — 폴더 구성

**한 줄 메시지**: 한 렌즈 = 한 폴더 = 한 CLI. 전부 같은 스키마.

**도표 (English)**

```
experimentalist/
├── docs/            design documents 01-09 (~3,400 lines)
│                      01 architecture      02 knowledge-base
│                      03 cross-system      04 decision-engine (all formulas)
│                      05 committee         06 pitfalls (evidence-grounded)
│                      07 roadmap           08 optics-lens spec
│                      09 knowledge-capture  <- the real purpose
│
├── optics/     lens 1  spectra, components, path, ablation          3,265 L
├── detection/  lens 2  photometry (photon budget, SNR), timing      1,118 L
├── compute/    lens 3  resources: data rate, buffer, capacity         686 L
├── sample/     lens 4  aberration: RI mismatch, WD, overlap         1,214 L
├── photo/      lens 5  dose: irradiance, bleaching, saturation      1,160 L
├── validity/   lens 6  power: statistical power, ROI tradeoff       1,307 L
├── stability/  lens 8  drift: thermal drift, Stokes settling, evap. 1,250 L
├── trapping/   lens 7  laser, dynamics (kappa, f_c), GOA            1,258 L
│      every lens has the SAME four files:
│        checks.py  check registry, margin, difficulty grade
│        gate.py    aggregation + evidence separation -> Verdict
│        setup.py   input assembly
│        cli.py     python -m <lens>.cli check <config>
│
├── .claude/agents/  LLM judgment halves of lenses 4, 5, 6 (prompt only)
├── calibration/     Phase 0 measurement scripts: disk bw, row time,
│                      EM1/EM2 discrimination, RAM burst capture        491 L
├── hardware/        off-ledger device control: tweezers, piezo (+DLL)  392 L
├── data/            registries: fluorophores, filters, light_sources,
│                      detectors, objectives, spectra/ (measured curves)
├── config/          channels/ (channel proposals), scopes/ (system profiles)
├── kb/              systems, calibrations, decisions, expertise
├── reference/       observed-systems.md (full 2,343-record scan), quotes/
├── manual/          vendor manuals: DMD, optical tweezers, piezo stage
└── tests/           22 files, 366 test functions                    3,719 L
```

→ `docs/01 §5`

**발표 스크립트**
> 폴더 구조입니다. 규칙이 단순합니다. **한 렌즈가 한 폴더고, 한 CLI입니다.**
>
> 렌즈 폴더 여덟 개가 전부 같은 파일 네 개를 갖습니다. `checks.py`가 검사 레지스트리하고 마진 계산, `gate.py`가 취합해서 Verdict 만들기, `setup.py`가 입력 조립, `cli.py`가 명령줄입니다. 그 위에 렌즈 고유의 물리 모듈이 하나씩 붙습니다. 광학은 스펙트럼, 검출은 광도측정, 샘플은 수차, 안정성은 드리프트 이런 식으로요.
>
> `docs/`가 설계 문서 아홉 개, 3,400줄 정도입니다. 코드보다 문서를 먼저 썼는데, 그게 이 프로젝트에서 잘한 결정이었다고 생각합니다. 특히 `06-pitfalls`는 "실제로 뭐가 잘못되는가"를 아카이브에서 확인된 것만 모아놓은 문서인데, 게이트를 만들 때 그대로 명세서가 됐습니다.
>
> `.claude/agents/`가 LLM 렌즈 정의고, `calibration/`이 하드웨어 붙었을 때 돌릴 측정 스크립트고, `kb/`가 지식베이스입니다.

---

## Slide 22 — 완성도

**한 줄 메시지**: 8개 렌즈 코드 전부 구현. 게이트 32개. 남은 건 값과 오케스트레이션.

**도표 (English)**

```
lens                        gates        status
─────────────────────────── ──────────── ────────────────────────────────────────
1 optics                    G1-G4        DONE
2 detection                 G5-G9        DONE
3 compute resources         G12, G13     DONE
4 sample geometry & optics  G15-G19      DONE. needs measured medium RI
                                         (default 1.333 assumed -> no advance)
5 photo-perturbation        G10, G20-G22 DONE. BLOCKED on the real instrument
                                         until power_at_sample_mw +
                                         bleach_photons exist
6 measurement validity      G11, G23-G27 DONE. reviews other lenses -> call LAST
7 optical tweezers          G14          DONE except LOCAL HEATING at 1064 nm.
                                         needs measured dial-% -> mW
8 mechanical & environment  G28-G32      DONE. G28/G31 work today.
                                         G29 BLOCKED until a drift rate is
                                         measured. vibration and stage
                                         repeatability remain UNGATED

code       ~12,100 lines (8 lenses + calibration + hardware)
tests      22 files, 366 test functions
docs       9 design documents, ~3,400 lines
gates      32 designed, 32 implemented in code
LLM lenses 3 subagent definitions drafted (4, 5, 6). lens 8 not drafted
```

**아직 남은 것**
- **오케스트레이터가 없음** — 각 렌즈를 개별 CLI로 호출. 위원회가 실제로 모인 적이 없고, G27(위원회 커버리지)만이 그 사실을 알아챈다
- 렌즈 간 자동 배선 없음 — 렌즈 2의 `max_fps`를 사람이 읽어서 `trapping.cli --detector-fps`로 넘겨야 함
- L1 인덱서 미구현 — 아카이브 2,343건 → SQLite
- `data/interventions.yaml` 개입 카탈로그 비어 있음 (감도 분석의 절반)
- Verdict/Finding 정의가 렌즈마다 복사됨 (8부) — 알려진 부채
- 미구현 물리: 트위저 1064 nm 국소 가열, 광독성, 조명 국소 가열, 중간 영역(a/λ~1) GLMT

→ `README`, `docs/04 §10`, `docs/05 §5`

**발표 스크립트**
> 완성도입니다. 렌즈 여덟 개가 코드로 전부 구현됐습니다. 게이트가 설계상 32개고, 32개 다 코드에 들어가 있습니다. 코드 1만 2천 줄, 테스트 함수 366개, 설계 문서 3,400줄입니다.
>
> 렌즈별로 남은 걸 보시면 대부분 **값이 없어서** 못 도는 겁니다. 렌즈 4는 매질 굴절률을 안 재서 1.333을 가정하고 있어서 판정이 확정으로 안 올라갑니다. 렌즈 5는 시료면 광량하고 표백 광자수가 없어서 실기에서는 BLOCKED입니다. 렌즈 8은 드리프트율을 안 재서 G29가 막혀 있습니다.
>
> 코드로 남은 것 중에 제일 큰 건 **오케스트레이터가 없다는 겁니다.** 지금은 렌즈마다 CLI를 따로 호출합니다. 그러니까 위원회가 실제로 모인 적이 한 번도 없습니다. 재밌는 게, 그 사실을 알아채는 게 G27 하나뿐입니다. 위원회 커버리지 게이트요. 상임 렌즈가 안 돌았거나 BLOCKED면 렌즈 6이 자기 위에 아무것도 못 얹는다고 거부합니다.
>
> 그 외에 아카이브 인덱서, 개입 카탈로그, 그리고 미구현 물리가 몇 개 있습니다. 1064 나노 국소 가열은 명시적으로 "아무도 안 잡고 있다"고 문서에 적어놨습니다. 조용히 통과시키는 것보다 낫다고 봤습니다.

---

## Slide 23 — 막힌 것은 코드가 아니라 사실

**한 줄 메시지**: 게이트는 돈다. 계산할 입력이 없어서 `BLOCKED`이 나온다. 파워미터 30분이 최대 언락.

**도표 (English)**

```
Phase 0 - securing the evidence
task                           output                       cost    status
────────────────────────────── ──────────────────────────── ─────── ───────────
current system MM .cfg         kb/systems/current.md        -       DONE 07-03
NIS device list, 3-way check   docs/02 §4 table             -       DONE 08-11
objective barrel engravings    NA, WD, coverslip            10 min  DONE 08-11
measured pixel size            MM2 ConfigPixelSize          30 min  DONE 2025-04
disk sustained write bandwidth kb/calibrations/             10 min  DONE 08-12
                                 D: = 206.8 MB/s (4 GB test)
camera row time                ReadoutTimeNs / ROI height   5 min   DONE 08-12
                                 3531.2 ns/row @ 2400 rows
>> ILLUMINATION POWER          power_at_sample_mw           30 min  *** TO DO ***
   at the sample plane         <- cannot be replaced by code.
                                  a power meter is required

why this one matters most:
  it opens the ABSOLUTE photon budget
  -> exposure time computable from scratch (not copied from precedent)
  -> all future data becomes TRANSFERABLE to another system
  verification: optics.cli check returns  advances: YES  instead of BLOCKED
```

→ `docs/07 Phase 0`, `README`

**발표 스크립트**
> 지금 진행을 막고 있는 게 뭔지가 이 슬라이드입니다. 코드가 아닙니다. **사실이 없습니다.** 게이트는 이미 돕니다. 계산할 입력이 없어서 BLOCKED이 나오는 겁니다.
>
> Phase 0 항목이 대부분 끝났습니다. 현재 시스템 설정 파일 확보, NIS 장치 목록 3중 교차 점검, 대물렌즈 배럴 각인 확인, 픽셀 크기 캘리브레이션, 디스크 대역폭 — D 드라이브가 206.8 MB/s 나왔습니다 — 그리고 카메라 행 시간.
>
> 딱 하나 남았습니다. **시료면 조명 파워입니다.** 30분이면 됩니다. 파워미터로 재면 되는데, 이건 코드로 대체가 불가능한 유일한 항목입니다.
>
> 이게 왜 제일 중요하냐면, 이 하나가 절대 광자 예산을 엽니다. 그러면 노출 시간을 선례가 아니라 처음부터 계산할 수 있게 되고, **앞으로 찍는 모든 데이터가 다른 장비로 이전 가능해집니다.** 검증 기준도 명확합니다. `optics.cli check`가 BLOCKED 대신 `advances: YES`를 내면 된 겁니다.

---

## Slide 24 — 로드맵 + 지금 당장 되는 것 3개

**한 줄 메시지**: 각 단계가 단독으로 유용해야 한다. 전부 끝나야 쓸 수 있는 설계는 안 끝난다.

**도표 (English)**

```
Phase 0  secure the evidence        <- WE ARE HERE (1 item left)
Phase 1  complete computational lenses   done for 1,2,3,4,5,6,7,8
           remaining: interventions.yaml, GLMT intermediate regime,
                      ell_c diffraction-limit gate
Phase 2  build the knowledge base   MM metadata indexer -> envelope.sqlite
                                    fingerprint, folder-name parser,
                                    tail parse -> measured_fps + drop detection
Phase 3  the agent layer            CLAUDE.md + skills + COMMITTEE ORCHESTRATION
                                    <- this is where it becomes a "chatbot"
Phase 4  experiment planning        hypothesis -> quantity -> precision ->
                                    statistical design. one more committee joins
Phase 5  automate operation         5a read -> 5b compare -> 5c generate preset
                                    -> 5d apply w/ confirmation -> 5e run+monitor
                                    DO NOT START before 0-3 are finished

  Phase 0 ──┬───────────────────────────▶ prerequisite for everything
            ├── Phase 1 (no hardware needed) ──┐
            └── Phase 2 (archive only)  ───────┴──▶ Phase 3 ──┬── Phase 4
                                                              └── Phase 5
```

**지금 당장 이득이 나오는 3가지 (Phase 0 완료 전에도 가능)**
1. **아카이브 드롭 검출** — `ElapsedTime` 차분으로 오염된 세션을 열거. 기존 분석 결과를 얼마나 믿을지 즉시 재평가
2. **Despeckle 영향 평가** — 카메라 후처리가 켜진 상태로 찍은 데이터의 정량 분석에 실제로 얼마나 영향을 줬는지 판정
3. **Duty cycle 감사** — 마이크로레올로지 세션의 모션 블러 편향을 Savin-Doyle로 사후 보정할 수 있는지 결정

→ `docs/07`

**발표 스크립트**
> 로드맵입니다. 원칙이 하나 있는데, **각 단계가 단독으로 유용해야 합니다.** 전부 끝나야 쓸 수 있는 설계는 안 끝나니까요.
>
> Phase 0이 사실 확보고 지금 여기입니다. Phase 1이 계산 렌즈인데 여덟 개 다 됐습니다. Phase 2가 지식베이스 구축, Phase 3이 에이전트 계층 — 여기서 챗봇이 됩니다. 위원회 오케스트레이션이 여기 들어갑니다. Phase 4가 실험 설계로 올라가는 거고, Phase 5가 장비 자동 조작인데 0에서 3이 끝나기 전에는 시작하지 않습니다. 검증 안 된 설정을 장비에 자동으로 밀어넣는 건 위험합니다.
>
> 의존성을 보시면 Phase 1과 2가 병렬로 갈 수 있고, 둘 다 Phase 0 없이도 상당 부분 진행됩니다.
>
> 그래서 아래 세 개가 **지금 당장 되는 것**입니다. 새 실험 안 하고 아카이브만으로요.
>
> 첫째, 드롭 검출. 프레임이 조용히 빠진 세션을 열거할 수 있습니다. 이러면 기존 분석 결과를 얼마나 믿을지 즉시 재평가됩니다.
>
> 둘째, despeckle 후처리 영향 평가. 카메라 후처리가 켜진 채로 찍은 데이터가 있는데, 정량 분석에 얼마나 영향을 줬는지 판정할 수 있습니다.
>
> 셋째, duty cycle 감사. 마이크로레올로지 세션들 모션 블러 편향을 사후 보정할 수 있는지 결정하는 겁니다. 이건 이미 찍은 데이터를 되살리는 작업입니다.

---

## Slide 25 — 기대효과 (1/2)

**한 줄 메시지**: 실험 구축 → 실험 수행 → 사람이 쓸 시간의 재배치.

**슬라이드 본문**

**① 실험 구축에 도움**
- 설정 하나가 아니라 **근거 · 가정 · 난이도 · 개선 옵션 · 실패 시그니처**가 함께 나옴
- `assumed_inputs` 목록이 그대로 "무엇을 먼저 재야 하는가"가 됨 → 준비 순서가 자동으로 정해짐
- 개선 제안이 **비용 계층**으로 정렬되므로 "돈 안 드는 것부터" 시도 가능 (readout mode 3.4배 vs 대물렌즈 1.15배)
- 부품 구매 판단 근거가 숫자로 나옴 — ablation 분석이 "이 필터가 정말 필요한가"에 답함

**② 실험 자체를 수행 (Phase 5)**
- 5a 읽기 → 5b 비교 → 5c 프리셋 생성 → 5d 사람 확인 후 적용 → 5e 취득 + 라이브 게이트 감시
- 사람이 장비에 붙어 있어야 하는 구간이 줄면 → **다른 실험 준비를 병행**, **샘플당 측정량 증가**
- 라이브 게이트 감시의 실질적 가치: **드롭이 조용히 일어나는 걸 실시간으로 잡음** (지금은 사후에 `ElapsedTime`을 봐야 알 수 있음)
- 단, 0–3 완료 전에는 시작하지 않음 — 검증 안 된 설정을 장비에 자동 적용하는 건 위험

**③ 분석과 아이디어 개진에 더 집중**
- 지금 사람 시간이 어디로 가는가: 설정 재발명, 과거 폴더 뒤지기, 스펙트럼 겹쳐보기, 데이터시트 찾기
- 이건 전부 결정론적 작업 → 코드로 이전 가능
- 남는 시간이 가는 곳: 왜 이런 결과인가, 다음에 뭘 물어볼까 — **위임 불가능한 부분**

**발표 스크립트**
> 기대효과입니다. 여섯 개인데 세 개씩 나눠서 말씀드리겠습니다.
>
> 첫째, 실험 구축입니다. 지금은 설정 값 하나를 받는데, 이 시스템은 근거하고 가정하고 난이도하고 개선 옵션하고 실패 시그니처까지 같이 냅니다. 특히 `assumed_inputs` 목록이 유용한데, 이게 그대로 "무엇을 먼저 재야 하는가"가 됩니다. 준비 순서가 자동으로 정해지는 셈입니다. 그리고 부품 구매 판단이 숫자로 나옵니다. ablation 분석이 "이 필터가 정말 필요한가"에 답하니까요.
>
> 둘째, 실험 수행 자체입니다. Phase 5인데 다섯 단계로 나눠서 갑니다. 읽기부터 시작해서 마지막에 취득하고 라이브로 게이트를 감시하는 것까지요. 사람이 장비에 붙어 있어야 하는 구간이 줄면 그 시간에 다른 실험을 준비할 수 있고, 샘플당 측정량이 늘어납니다. 그리고 라이브 게이트 감시의 실질적 가치가 하나 있는데, **프레임 드롭이 조용히 일어나는 걸 실시간으로 잡는 겁니다.** 지금은 찍고 나서 `ElapsedTime` 봐야 압니다.
>
> 셋째, 분석과 아이디어에 집중하는 겁니다. 지금 사람 시간이 어디로 가는지 보면 — 설정을 다시 만들고, 과거 폴더를 뒤지고, 스펙트럼을 겹쳐보고, 데이터시트를 찾습니다. 이거 전부 결정론적 작업입니다. 코드로 넘길 수 있습니다. 그리고 남는 시간이 "왜 이런 결과가 나왔나", "다음에 뭘 물어볼까"로 가는데, 이게 위임이 안 되는 부분입니다.

---

## Slide 26 — 기대효과 (2/2)

**한 줄 메시지**: 실패 데이터의 자산화, 진입장벽 완화, 그리고 타 랩 실험에 대한 수용도.

**슬라이드 본문**

**④ 실패 데이터의 활용**
- 지금 실패 데이터의 문제는 **왜 실패했는지가 기록에 없다**는 것 → 재사용 불가
- 이 시스템에서 실패는 구조화됨: 어느 게이트가 어떤 마진으로 깨졌는지 + 실행 시 실제 결과 (`kb/decisions/`)
- 그러면 실패가 **게이트 임계값을 경험적으로 교정하는 데이터**가 됨. 실패할수록 시스템이 정확해짐
- 계산과 전문가 판단이 어긋난 지점을 별도로 기록 → 모델에서 빠진 항을 찾아내는 경로 (ATPS 배경 형광 사례)
- **이미 찍은 데이터도 되살아남**: 드롭 검출 · despeckle 영향 평가 · duty cycle 감사 3종이 오염된 세션을 열거하고 보정 가능성을 판정
- 계획된 인터뷰의 최우선 질문이 "뭘 보면 실패했다고 판단하십니까"인 이유 — **성공만 기록되면 KB가 편향됨** (`docs/09 §8` 미해결 항목)

**⑤ 실험장비 진입장벽 완화**
- teaching mode: 같은 질문에 **청중에 따라 다르게** 답함

```
audience                   output
────────────────────────── ──────────────────────────────────────────────
expert (the user)          conclusion + numbers. basis folded away
junior                     conclusion + WHY + source + what to verify
junior, first experiment    the above + FAILURE SIGNATURES + what to ask
```

- 답만 주면 후배가 성장하지 않음 → **충돌과 선택을 보여주는 것**이 핵심
- 실패 시그니처를 미리 알려줌: "궤적이 자주 끊기면 SNR 문제, MSD 기울기가 lag에 따라 휘면 블러/드롭"

**⑥ 타 연구실 실험에 대한 수용도 상승**
- 지식이 **시스템 종속 / 시스템 독립**으로 명시적으로 분리돼 있음 (tier 2 vs tier 3, `applies_to_systems` 필드)
- 다른 장비로 옮길 때 무엇이 넘어가고 무엇이 안 넘어가는지가 자동으로 판정됨 (`docs/03`)
- 샘플계 지식(`kb/samples/`)은 하드웨어 교체를 견딤 — 장비가 바뀌어도 남는 자산
- 시스템 교체 시 `kb/systems/_transitions/<old>-to-<new>.md`를 쓰면서 해당 시스템에 묶인 전문성 엔트리를 전부 열거해 재심사

**발표 스크립트**
> 넷째가 실패 데이터 활용인데, 개인적으로 이게 제일 크다고 봅니다.
>
> 지금 실패 데이터의 문제는 왜 실패했는지가 기록에 없다는 겁니다. 그래서 재사용이 안 됩니다. 이 시스템에서는 실패가 구조화됩니다. 어느 게이트가 어떤 마진으로 깨졌는지, 그리고 실제로 돌려봤을 때 결과가 어땠는지가 결정 로그에 남습니다.
>
> 그러면 실패가 게이트 임계값을 교정하는 데이터가 됩니다. 지금 난이도 등급 경계가 3, 1.5, 1.0, 0.5, 0.2인데 이거 사실 제가 정한 값입니다. 실사용 데이터로 조정해야 하는데, 그 조정을 실패 기록이 해줍니다.
>
> 그리고 계산과 전문가 판단이 어긋난 지점을 따로 기록합니다. 이게 모델에서 빠진 항을 찾는 경로입니다. 아까 ATPS 배경 형광 예시가 그건데, SNR 예측 8.2인데 안 보인다는 게 배경항이 모델에 없다는 신호였습니다.
>
> 그리고 **이미 찍은 데이터도 되살아납니다.** 아까 말씀드린 세 가지 — 드롭 검출, despeckle 영향, duty 감사 — 가 오염된 세션을 열거하고 보정 가능성을 판정합니다.
>
> 다섯째, 진입장벽입니다. teaching mode라는 게 있는데, 같은 질문에 청중에 따라 다르게 답합니다. 전문가한테는 결론하고 숫자만, 후배한테는 왜 그런지와 출처와 확인할 것까지, 첫 실험이면 거기에 실패 시그니처까지 붙입니다. 답만 주면 후배가 성장하지 않으니까 **충돌과 선택을 보여주는 게** 핵심입니다.
>
> 여섯째, 타 랩 실험 수용도입니다. 이건 3단 정규화의 부수 효과인데, 지식이 시스템 종속인지 독립인지가 명시적으로 분리돼 있습니다. 그러니까 다른 장비로 옮길 때 무엇이 넘어가고 무엇이 안 넘어가는지가 자동으로 판정됩니다. 샘플계 지식은 하드웨어 교체를 견디니까 장비가 바뀌어도 남는 자산이고요. 시스템을 교체할 때는 전이 문서를 쓰면서 그 시스템에 묶인 전문성 엔트리를 전부 다시 심사하게 되어 있습니다.

---

## Slide 27 — 정리 + 요청사항

**슬라이드 본문**

**정리**
1. 계산은 코드, 판단은 LLM. **계산되는 것은 추측하지 않는다**
2. `advances = passed AND evidence == "measured"` — 카탈로그 값으로 나온 PASS는 PASS가 아니다
3. `BLOCKED ≠ FAIL`. **거절은 기능이다**
4. 서브시스템 위원회 6+2. 단일 렌즈가 못 잡는 **교차 제약**이 존재 이유
5. 양립 불가능한 요구는 봉합하지 않고 **충돌 자체를 사람에게** 제시
6. 지식베이스는 텍스트. `Why`와 `반증 조건`이 없으면 저장하지 않는다

**요청사항**
- **파워미터로 시료면 조명 파워 측정 — 30분.** 이 하나가 절대 광자 예산을 열고, 앞으로의 데이터를 이전 가능하게 만듦
- 축 방향 드리프트율 — PFS 끄고 고정 지점에서 1시간, 몇 분마다 포커스 기록 (G29 언락)
- 트위저 dial-% → mW 캘리브레이션 (렌즈 7 확정 조건)
- 샘플계별 특성 시간·길이 (τ_c, ℓ_c) — 측정 불가하면 이론 추정이라도. 없으면 프레임률·노출을 정할 근거가 아예 없음
- **"뭘 보면 이 데이터를 버려야 한다고 판단하십니까"** — KB에 실패 판정 기준이 단 하나도 없음

**발표 스크립트**
> 정리하겠습니다. 여섯 개입니다.
>
> 계산은 코드가 하고 판단은 LLM이 합니다. 계산되는 걸 추측하지 않습니다. 통과 조건이 "통과했고 그리고 근거가 측정값이다"입니다. BLOCKED와 FAIL은 다르고, 거절이 기능입니다. 위원회는 학문이 아니라 서브시스템으로 쪼갰고, 단일 관점이 못 잡는 교차 제약이 존재 이유입니다. 양립 불가능한 요구는 봉합하지 않고 충돌 자체를 사람에게 넘깁니다. 지식베이스는 텍스트고, 왜인지와 반증 조건이 없으면 저장하지 않습니다.
>
> 그리고 부탁드릴 게 몇 개 있습니다.
>
> 제일 큰 건 **파워미터로 시료면 조명 파워 재는 겁니다. 30분입니다.** 이 하나가 막고 있는 게 많습니다.
>
> 그 다음이 축 방향 드리프트율인데, PFS 끄고 고정 지점에서 한 시간 동안 몇 분마다 포커스만 기록하면 됩니다.
>
> 트위저 다이얼 값을 mW로 환산하는 캘리브레이션도 필요합니다.
>
> 그리고 샘플계마다 특성 시간과 길이 — 측정이 안 되면 이론 추정이라도 주셔야 합니다. 이게 없으면 프레임률과 노출을 정할 근거가 아예 없습니다.
>
> 마지막이 제일 중요한데, **"뭘 보면 이 데이터를 버려야 한다고 판단하십니까"** 입니다. 지금 지식베이스에 실패 판정 기준이 단 하나도 없습니다. 이건 계산으로 절대 안 나오고, 경험 있는 분들 머릿속에만 있습니다.

---

# 부록 (질문 대응용 백업 슬라이드)

## 부록 A — 아카이브에서 실제로 확인된 문제들

```
A1  PixelSizeUm = 0.0 in ALL 2,343 acquisitions
      every spatial measurement rests on an external calibration whose origin
      the metadata does not record. D scales as pixel size SQUARED:
      3% pixel error -> 6% error in D
A2  MM 1.4.23 (2,137 = 91%) vs MM 2.0.3 - different schema.
      a single parser loses 91% of the data
B1  filter information effectively absent ('DA/FI/TR10Empty', 'Wheel-A:Filter-0')
C1  on-camera despeckle post-processing was ENABLED -> breaks linearity
C2  12-bit mode: quantization noise 4.37 e- vs 16-bit 0.35 e-
      effective noise 4.65 vs 1.35 e-  ->  3.4x worse SNR on a weak signal
C4  requested 10 ms exposure -> ActualInterval-ms = 35.67  (3x discrepancy)
      28 Hz measured against a camera limit of ~85 Hz. duty cycle 28%
C5  frame drops happen SILENTLY. only sign: irregular ElapsedTime-ms
D7  PFS can be ON without being LOCKED ('Out of Range' sessions exist)
E1  do not take a precedent as the target
      764 acquisitions pile up at 500 ms on 647 with no distribution above it
      = a ceiling, not a human choice -> the light level was insufficient
```
→ `docs/06`

## 부록 B — 계산 자원과 안정성 게이트가 잡는 것

```
data rate  R = W * H * (bits/8) * f
  1608^2 x 16bit x 60 fps   = 310 MB/s   NVMe required
                                         (measured D: = 206.8 MB/s -> FAILS)
  1608^2 x 12bit(->16) x 30 = 155 MB/s   SATA SSD fine
  176^2  x 16bit x 550 fps  =  34 MB/s   comfortable
gate: R < 0.7 * sustained disk write bandwidth
      buffer >= 5 seconds' worth  (552 frames x 1608^2 = 2.85 GB)

rolling shutter readout scales with ROW COUNT ONLY
  narrowing the WIDTH buys nothing. a wide short ROI is faster at equal pixels
  archive: 10.28 us/row | current Kinetix: 3531.2 ns/row @ 2400 rows

sedimentation (G31, works TODAY - sample properties only, no instrument
  measurement needed)
  a 1 um polystyrene sphere in water settles ~98 um in an hour
  against a 0.375 um depth of field on the 100x oil
  -> the population in the focal plane at the end is NOT the one that started
  density-matching removes the term entirely
```
→ `docs/04 §5·§8`, `docs/05 Lens 8`

## 부록 C — 렌즈 5·6이 다른 렌즈를 무효화하는 경로

```
G20 (saturation / triplet shelving) INVALIDATES other lenses' numbers
  past saturation, emission stops rising with power, but lens 1 and lens 2
  photon budgets ASSUME LINEARITY (optics.path.detected_e_per_s)
  -> they overestimate signal while the dose keeps climbing
  -> nothing else catches this
  scale: FITC saturates near 3.5e5 W/cm2. a widefield FOV never reaches it,
         but a focused confocal or spinning-disk spot does

G23 (bias ledger) is HARD, not BIAS
  the upstream gates are the bias gates; G23 is the meta-check that they were
  all dealt with. its margin = the worst UNCORRECTED upstream bias margin,
  so the committee's worst unhandled problem stays visible rather than being
  averaged away

G27 (committee coverage) is currently the ONLY thing that notices the committee
  never convened. there is no orchestrator - each lens is invoked by its own
  CLI. a BLOCKED upstream lens fails G27: validity cannot sit on top of a lens
  that had no basis to decide

which calibrations matter depends on the QUANTITY
  a wrong pixel size ruins a diffusion coefficient, irrelevant to stoichiometry
  flat-field is the reverse
  validity.setup.QUANTITY_REQUIREMENTS encodes that; an unlisted quantity
  BLOCKs rather than being checked against guessed criteria
```
→ `docs/05 Lens 5·6`

## 부록 D — 아무도 안 잡고 있는 것 (의도적으로 명시)

```
- local heating from the 1064 nm trap. water absorption changes viscosity ->
  changes D -> contaminates microrheology. lens 7 does not compute it and
  lens 5 deliberately does not cover it (visible excitation light only)
- phototoxicity (needs a dose limit per sample)
- illumination-driven local heating (needs the medium absorption coefficient)
- vibration and stage repeatability - no measurement channel exists.
  lens 8 SAYS SO rather than passing quietly: a quiet pass there is an absence
  of evidence, not evidence of stability
- ell_c below the diffraction limit: if the characteristic length (actin mesh
  size, ATPS interface thickness) < sigma_PSF, no pixel size resolves it.
  passing the sampling gate then means NOTHING. no gate for this yet
- tweezers intermediate regime a/lambda ~ 1: neither Rayleigh nor ray optics is
  valid. GLMT needed. current rule: return BLOCKED, do not approximate
- eight copies of Verdict/Finding, one per lens - known debt
```
→ `docs/06 "Nothing catches these yet"`, `docs/05`

---

## 발표 준비 체크리스트

- [ ] Slide 20의 CLI 출력을 **현재 시스템 설정으로 실제 재실행**해서 캡처 교체 (지금 실린 출력은 `docs/01 §6`의 예시)
- [ ] Slide 22의 "테스트 366개"는 소스에서 집계한 수치 — 발표 전 실기에서 `pytest`를 한 번 돌려 통과 확인
      (작업 PC에 Python이 없고 `.venv`는 다른 머신에서 생성돼 실행 불가)
- [ ] Slide 4·16·17의 ASCII 다이어그램을 도형으로 다시 그릴지 결정 (ASCII 유지 시 등폭 글꼴 필수)
- [ ] Slide 25–26 기대효과 순서를 청중에 맞춰 조정 — PI 대상이면 ④(실패 데이터)와 ⑥(수용도)을 앞으로
- [ ] 영어 번역 시: 도표·코드 블록은 그대로 재사용하고 본문만 번역. 용어가 이미 영어라 일관성 유지됨
