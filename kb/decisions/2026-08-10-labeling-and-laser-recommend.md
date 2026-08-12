# 2026-08-10 · 필터·레이저 기반 표지/레이저 추천 루프

> `docs/02 §9`의 결정 로그 양식(요구/제안/실제결과)은 **실험 실행 결과**를 위한
> 것이다. 이 항목은 실험이 아니라 **도구를 설계·구현한 세션**의 기록이라 양식을
> 그만큼 바꿨다 — "실제로 쓴 설정"·"결과" 대신 "구현한 것"·"발견한 버그"를 적는다.
> 배운 것을 다음 사람(에이전트 포함)이 반복하지 않게 하려는 목적은 같다.

## 요구

"필터, 레이저 정보를 바탕으로 시스템의 적절한 labeling, 레이저에 대한 추천
루프를 만들고 싶다." 이후 대화에서 범위가 구체화됨:
1. 큐브 필터의 여기·방출은 다이크로익과 달리 개별 교체 가능한 유닛
2. 광원별 실제 광경로 확보 (레이저/SpectraIII/Aura/DiaLamp/광집게)
3. 듀얼카메라(Kinetix_red/blue) 분리를 인식할 것
4. **단일 광원 선호** — 광원별로 후보를 보여주고 사람이 고르는 워크플로우

## 구현한 것

| 파일 | 역할 |
|---|---|
| `optics/recommend.py` | `screen()` 단일 후보 채점 · `recommend_labels()` 라인별 랭킹 · `recommend_panel()` 동시다색 패널 · `compare_sources()` 광원 간 비교 |
| `config/scopes/current-laser.yaml` | CSU-W1 + LUN-F-XL 레이저 경로 프로파일 |
| `config/scopes/current-spectra.yaml` | SpectraIII(LightEngine) 와이드필드 경로 |
| `config/scopes/current-aura.yaml` | Aura 와이드필드 경로 |
| `optics/components.py :: Element.as_reflected()` | 빔스플리터의 반사측을 투과측처럼 다루는 뷰 (듀얼카메라용) |
| `optics/build.py` | 필터 지정에 `{"ref": name, "side": "reflect"}` 지원 |
| CLI `python -m optics.cli recommend <scope> [--panel] [--dyes] [--lines]` | |
| CLI `python -m optics.cli sources <scope>... [--dyes] [--lines]` | 광원별 최선 패널을 나란히 보여줌, **자동으로 고르지 않음** |
| `kb/systems/current.md > light_paths` | 4개 광원 + 광집게 경로, `known_gaps`에 미확인 사항 정리 |

## 핵심 설계 결정과 근거

**`gate.evaluate()`를 그대로 안 쓰고 체크(`check_excitation` 등 4개)를 직접
호출한다.** Phase 0가 대물 NA·카메라 스펙 완비 여부로 즉시 BLOCKED를 내는데,
이 랩은 NA도 카메라도 아직 미확정이다(`kb/systems/current.md`). 하지만 저 4개
체크 자체는 NA도 read noise/full well도 안 읽으므로, "이 채널을 오늘 찍어도
되는가"(gate의 역할)와 "이 염료가 이 라인에 맞는가"(recommend의 역할)를
분리하면 지금 계산 가능한 걸 계산 못 할 이유가 없었다.

**랭킹은 margin이 아니라 "밝기"(여기효율×방출수집) 우선, margin은 하드
게이트로만.** 처음엔 margin(체크 중 최솟값)으로 정렬했는데, 필터 레지스트리
전체가 같은 `blocking_od: 6` 기본값을 쓰다 보니 "약하게 여기되지만 우연히
필터가 멀리 떨어져 있어 차단 마진만 높은" 조합이 "잘 여기되지만 필터가
가까워 마진이 살짝 낮은" 조합을 이기는 일이 실제로 발생했다(EGFP가 488nm
1순위에서 밀려남). margin은 grade가 INFEASIBLE(<0.2, `checks.GRADES`)이
아닌 한 통과시키고, 그 안에서는 밝기로 정렬하도록 바꿨다 — 이 프로젝트의
등급 철학("HARD는 진행 가능, `docs/05` §3)과도 맞다.

**스코프 파일 = 광원 하나.** "단일 광원 선호"가 코드 변경 없이 이미 성립한다
— `recommend_panel`은 한 스코프 안의 라인만 쓰므로, 스코프를 광원별로
나눠두면 패널이 광원을 섞을 수가 없다. `compare_sources()`는 스코프별로
따로 계산해서 나열만 하고 **선택은 하지 않는다** — 어느 광원이 시료에
맞는지(절편 필요성·광표백·다른 예약 등)는 이 도구가 판단할 근거가 없는
영역이라(`docs/01` 원칙 5), 사람에게 넘긴다.

**빔스플리터 반사측 = `Element.as_reflected()`.** `Channel.emission`은
항상 `.transmission`만 읽는데, 듀얼카메라 스플리터는 한쪽 카메라에
반사측을 보낸다. 새 필드나 `Channel` 구조 변경 대신, "반사율을 투과율
자리에 넣은 새 `Element`"를 만들어 끼워 넣는 방식을 택했다 — 기존 코드
경로를 하나도 안 건드리고 데이터(YAML)만으로 표현 가능해서(`docs/08` §6
철학과 일치).

## 발견하고 고친 버그 4개

**전부 "확신을 갖고 계산했는데 사실은 정반대"인 유형** — `compute-never-infer`
원칙이 지키려는 바로 그 실패 양상이다.

1. **`Di01-T405/488/568/647` 반사/투과 반전** (`data/filters.yaml`). `kind:
   multiband`로 노치 반사대역을 최상위 `bands:`에 넣어, 코드가 "레이저 4
   라인에서만 통과, 나머지 전부 6 OD 차단"으로 계산 — 실제로는 정반대
   (4 라인만 반사, 나머지 광대역 투과). 레이저 경로의 모든 채널이 허구로
   collection≈0이 나왔다. `reflection:` 서브키로 분리해 수정.
2. **`Channel.stokes_headroom_nm()`가 광원 스펙트럼을 안 봄** (`optics/path.py`).
   다이크로익 하나가 레이저 4개 라인을 동시에 반사하다 보니, 소자의
   "통과 가능 영역"을 그대로 여기대역으로 오인 — 어떤 라인을 쓰든
   "여기대역 240nm 폭"으로 보여 모든 염료가 허구로 스펙트럼 겹침 판정을
   받았다. `excitation_blocking_od`와 같은 방식으로 광원 스펙트럼을
   곱하도록 수정.
3. **밝기 무시 랭킹** (`optics/recommend.py`, 위 "핵심 설계 결정" 참고).
4. **`FilterTurret2` "6슬롯 전부 비어있음"이 틀림** (`kb/systems/current.md`).
   실제로는 광집게(OT) 결합용 NIR 다이크로익이 있음. 사용자 구술로 정정.

공통점: 셋 다 **"이 정도면 맞겠지"로 채워 넣은 가정이 정확히 반대 방향으로
틀렸다.** 벤치에서 확인 안 하면 안 걸리는 종류라 테스트로 회귀 고정해뒀다
(`tests/test_optics.py`, `tests/test_recommend.py`).

## 남은 것 (`kb/systems/current.md > light_paths > known_gaps` 참고)

- `CSUW1-Dichroic` 정확한 band 값
- `EM1`/`EM2` 중 어느 쪽이 `Kinetix_red` 앞인지 (구성은 동일해서 계산엔
  영향 없음 — 벤치 배선 확인용)
- `FilterTurret2` NIR 다이크로익 슬롯 번호·부품명
- 투과광 콘덴서 MM/NIS 등록 여부
- **`SpectraIII`/`Aura` 스코프에 아직 안 넣은 것**: `LappMainBranch1`(광량
  배분만 바꿈, 스펙트럼 무관이라 이 스크리닝엔 원래 불필요),
  `CSUW1-Dichroic`(band 미확인이라 아직 중립으로 가정)
- **아직 안 만든 것**: 광집게(Trap) 스코프 — 샘플까지만 정리됨, 검출계와는
  무관하다고 결론났으므로 이 recommend 루프의 대상이 아닐 가능성 높음

## 다음 단계 후보

- `data/spectra/`에 EM1-525/36·EM1-705/72 벤더 곡선을 넣으면 두 채널 다
  HARD→COMFORTABLE로 오를 것으로 예상 (blocking 요구치 7→5 OD)
- `data/detectors.yaml`에 Kinetix 데이터시트 QE 곡선 추가
- 대물 NA 확정 후 `optics.cli check`로 최종 확인 (이 recommend 루프는
  스크리닝이지 최종 판정이 아님)
