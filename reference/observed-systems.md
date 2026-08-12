# 관찰된 시스템 인벤토리 — ⚠ 구(舊) 셋업

> ## 이 문서는 현재 시스템이 아니다
>
> 여기 적힌 내용은 **과거에 촬영된 데이터에서 역추출한 옛 셋업**이다.
> 현재 운용 중인 현미경은 이것과 다르며, 이후 몇 가지 장치가 더 연결될 예정이다.
>
> **용도**: 과거 데이터를 해석하고, 어떤 정보가 메타데이터에서 유실되는지
> 파악하고, 지식베이스 스키마를 검증하기 위한 자료.
>
> **금지**: 이 문서의 어떤 값도 현재 시스템의 설정 추천 근거로 쓰지 말 것.
>
> **갱신 조건**: full capability가 연결된 MM `.cfg`가 들어오면
> 이 문서를 폐기하지 말고 `reference/legacy-systems.md`로 남긴 뒤,
> 새 `.cfg` + NIS-Elements 대조로 `reference/current-system.md`를 새로 만든다.
> 두 문서의 차이(diff)가 곧 "과거 데이터를 현재 장비로 옮길 때의 변환표"가 된다.

`D:\data`의 Micro-Manager 메타데이터 **2,343건**(30.17 GB)의 헤더를 전수 스캔해서
추출한 실측 내용. 추정이 아니라 파일에 실제로 적혀 있는 값이다.

> 스캔 방법: 각 `*_metadata.txt`의 첫 420줄(= `Summary` + 첫 `FrameKey` 전체 장치 스냅샷)만
> 읽음. 파일 하나가 최대 44 MB이므로 전체를 읽지 않는다.

---

## 1. 결론 먼저 — 한 대의 현미경, 세 개의 설정 세대

컴퓨터 이름은 3개지만 하드웨어 지문(카메라 칩·스탠드 장치 구성)은 사실상 같은 계열이다.
**PC 이름으로 시스템을 구분하면 안 된다.**

| 세대 | ComputerName | MM 버전 | 조명 장치 | 특징 | 건수 |
|---|---|---|---|---|---|
| **A** | `DESKTOP-221I6SM` | 1.4.23 (2020-09-17) | `Spectra` (Lumencor Spectra X) | Wheel-A, Triggering(NI DAQ), LightPath 있음 | 2,137 |
| **B** | `PC-7C612437CB` | 2.0.3 (2023-11-17 / 2025-07-24) | `Spectra` **+ `LightEngine`** (Spectra III 8-NII-XS) | A + ZDrive 추가 | 179 |
| **C** | `Takatori_lab` | 2.0.3 (2025-02-28) | `LightEngine`만 | **Wheel-A · LightPath · IntermediateMagnification · Triggering 없음** | 27 |

기록된 촬영 기간: 세대 B는 2024-07-02 ~ 2026-04-17, 세대 C는 2025-03-19.
세대 A는 MM 1.4가 `StartTime`을 `Summary`에 쓰지 않아 파일 시각으로 추정해야 한다.

### 여기서 바로 나오는 설계 요구사항

- 시스템 동일성 판정은 **장치 라벨 집합 + 카메라 칩/시리얼**의 지문으로 한다.
- 세대 C는 `IntermediateMagnification` 장치가 없는데 폴더명은 `..._100x1.5x_...`이다.
  → **1.5x 배율기를 손으로 넣고 메타데이터에는 남기지 않았다.** 폴더명이 유일한 기록이다.
- 세대 C는 대물렌즈 라벨이 `"6-"`(빈 문자열)이다. 터렛 위치만 있고 이름이 없다.

---

## 2. 프로젝트 분포

| 프로젝트 | 건수 | 주 사용 세대 |
|---|---|---|
| ATPS motility induced partitioning | 1,829 | A |
| Liquid crystal | 320 | A(300) / B(20) |
| Active particle control | 145 | B |
| ATPS passive particle | 27 | C |
| Actin rheology | 14 | B |
| tweezers calibration | 4 | A |
| ATPS inclusion | 4 | A |

---

## 3. 카메라

전 세대 동일. `ChipName = GS144BSI`, `X/Y-dimension = 1608`.

| 항목 | 값 | 출처 |
|---|---|---|
| 장치 라벨 | `Prime95B` (일부 세션에서 오타 `Pirme95B` 20건) | 메타데이터 |
| 센서 | GS144BSI, 1608 × 1608 | 메타데이터 |
| 모델 추정 | **Photometrics Prime 95B 25mm** | 1608² 배열은 25mm 버전. 18mm 버전은 1200² |
| 픽셀 피치 | 11 µm (추정) | ⚠ 데이터시트 확인 필요 |
| 냉각 | 설정 −15 °C, 실측 −14.9 °C | 메타데이터 |
| 트리거 | `Internal Trigger` — **2,339/2,343 전부** | 메타데이터 |

### 두 가지 readout 모드만 사용됨

`ReadoutRate`와 `Gain`이 완전히 상관되어 있다.

| ReadoutRate | Gain | BitDepth | 건수 | 성격 |
|---|---|---|---|---|
| `100MHz 16bit` | `1-HDR` | 16 | 1,270 | 고 다이내믹레인지, 저속 |
| `200MHz 12bit` | `1-Full well` | 12 | 1,069 | 고속, DR 희생 |

`FullWellCapacity = 62000 e⁻`, `Offset = 100 ADU` (12bit 모드 실측값).

### ⚠ 후처리 필터가 켜져 있다

```
"Prime95B-PP  1   ENABLED": "Yes"   PP 1 DESPECKLE BRIGHT LOW/HIGH,  THRESHOLD 125
"Prime95B-PP  2   ENABLED": "Yes"   PP 2 DESPECKLE DARK LOW,         THRESHOLD 125
"Prime95B-PP  3   ENABLED": "Yes"   PP 3 DESPECKLE DARK HIGH,        THRESHOLD  80
"Prime95B-PP  4   ENABLED": "Yes"   PP 4 (MIN ADU AFFECTED 200),     THRESHOLD  75
```

PVCAM 온카메라 despeckle이 활성 상태다. 정량 광도측정과 서브픽셀 위치추정의
전제(픽셀값 선형성, 독립 잡음)를 깨뜨린다. → [주의할 점 §4](../docs/06-pitfalls.md)

---

## 4. 대물렌즈 — 터렛 위치는 고정 식별자가 아니다

| 터렛 | 세대 A 라벨 | 세대 B 라벨 | 건수(A/B) |
|---|---|---|---|
| 1 | Plan Fluor 10x | Plan Fluor 10x | 2 / 141 |
| 2 | Plan Fluor 20x | — | 7 / 0 |
| 3 | Plan Apo Lmbd 40x | — | 21 / 0 |
| 4 | Plan Apo Lmbd 60x **Oil** | Plan Apo VC 60x **WI** | 80 / 20 |
| 5 | Plan Apo Lmbd 100x Oil | Plan Apo Lmbd 100x Oil | 1,852 / 14 |
| 6 | Plan Apo Lmbd 60x Water | *(라벨 없음, 세대 C)* | 175 / 27 |

**터렛 4번이 세대 사이에 물리적으로 교체되었다.** 위치 번호로 렌즈를 식별하면 틀린다.

### NA 값은 메타데이터에 없다 — 반드시 채워야 함

Micro-Manager는 NA를 기록하지 않는다. 아래는 Nikon 제품명 기준 **추정치이며 검증 전에는
계산에 쓰면 안 된다.**

| 라벨 | 추정 NA | 침지 | 검증 상태 |
|---|---|---|---|
| Plan Apo Lmbd 100x Oil | 1.45 | oil | ⚠ 미검증 |
| Plan Apo Lmbd 60x Oil | 1.40 | oil | ⚠ 미검증 |
| Plan Apo VC 60x WI | 1.20 | water | ⚠ 미검증 |
| Plan Apo Lmbd 60x Water | ? | water | ⚠ **제품명 불일치** — Plan Apo λ 계열에 water 사양이 없음. 실물 각인 확인 필요 |
| Plan Apo Lmbd 40x | 0.95 | air | ⚠ 미검증 |
| Plan Fluor 20x | 0.50 | air | ⚠ 미검증 |
| Plan Fluor 10x | 0.30 | air | ⚠ 미검증 |

### 중간 배율

`IntermediateMagnification-Magnification`: `1.0x` 2,298건, `1.5x` 14건, 없음 31건.

### 유효 픽셀 크기 (11 µm 피치 가정, binning 1×1)

| 대물 | 중간배율 | 총배율 | 샘플면 픽셀 |
|---|---|---|---|
| 100x | 1.5x | 150x | **73.3 nm** |
| 100x | 1.0x | 100x | **110 nm** |
| 60x | 1.0x | 60x | **183 nm** |
| 40x | 1.0x | 40x | **275 nm** |
| 20x | 1.0x | 20x | **550 nm** |
| 10x | 1.0x | 10x | **1,100 nm** |

`PixelSizeUm`은 전 파일에서 **0.0** — 픽셀 크기 교정이 MM에 설정된 적이 없다.
위 값들은 전부 계산으로 얻은 것이고, 실측 교정(스테이지 마이크로미터/격자)과
대조된 적이 없다. → [주의할 점 §2](../docs/06-pitfalls.md)

---

## 5. 광경로 · 필터 — 가장 큰 공백

| 항목 | 관찰값 | 문제 |
|---|---|---|
| `FilterTurret1-Label` | `1-DA/FI/TR10Empty` 2,312건 / `1-Empty` 27건 | **큐브가 사실상 1개.** 라벨 문자열이 뭉개져 있어 정확한 부품 특정 불가 |
| `Wheel-A-Label` | `Filter-0` 2,292건 | Sutter Lambda 휠 위치에 **이름이 안 붙어 있음.** 어떤 방출필터였는지 메타데이터로 복원 불가 |
| `LightPath-Label` | `4-L100` 1,728건 / `3-AUX` 564건 | L100 = 카메라 포트 100%. AUX = 광집게/DMD 경로로 추정 |
| `Turret1Shutter-State` | 대부분 `1` | |

### ⚠ 해소되지 않는 모순

`DA/FI/TR`는 DAPI/FITC/TRITC 3-band 세트인데, 실제로는 **647-Cy5 채널을 764건 촬영**했다.
가능한 설명:

1. 실제 큐브가 4-band(DA/FI/TR/Cy5)이고 라벨이 잘렸다
2. 방출 선택을 Wheel-A가 하는데 위치 라벨이 없어 안 보인다
3. 라벨이 실물과 다르다

셋 중 무엇인지 메타데이터만으로는 알 수 없다. **현재 시스템 `.cfg` + 실물 확인이 필요하다.**
이것이 지금 지식베이스의 최대 공백이다.

---

## 6. 조명

### 사용된 라인 (Lumencor Spectra X, `Spectra` 장치)

| 라인 | 중심파장(공칭) | 관찰된 레벨 | 주 용도 |
|---|---|---|---|
| Red | 640 nm | 5, 7, 8, 10, 13, 100 | 647-Cy5 |
| Cyan | 470 nm | 2, 5, 10, 50, 100 | 488-GFP |
| Green | 555 nm | 5, 10 | 555-TRITC |

`LightEngine`(Spectra III)은 세대 B/C에 존재하지만 스캔 창 안에서 **비영(非零) 세기가
한 건도 관찰되지 않았다.** 42건이 `Core-Shutter = LightEngine`인데도 그렇다.
→ 속성 이름이 다르거나, 실제 조명은 다른 경로였다는 뜻. 미해결.

### 투과광

`DiaLamp-State = 1` 130건, `Intensity` 예: 1901 (단위 불명, 아마 DAC counts).
`Core-Shutter = DiaLamp`가 1,186건 — 명시야 촬영이 전체의 절반.

### ⚠ 두 개의 조명 장치가 동시에 설정되어 있다

세대 B는 `Spectra`와 `LightEngine`이 둘 다 config에 있다. `Core-Shutter`가 어느 쪽인지로
판단해야 하지만, 남은 다른 장치의 레벨값도 메타데이터에 그대로 남아 헷갈린다.
파서는 **`Core-Shutter`를 기준으로 활성 조명을 판정**해야 한다.

---

## 7. 채널과 노출 — 실측 운용 범위

`ChNames`는 MM Channel 그룹의 프리셋 이름이다.

| 채널 | 건수 | 노출 min | 중앙값 | P90 | max |
|---|---|---|---|---|---|
| `OFF` (명시야) | 1,230 | 5 ms | **7 ms** | 30 ms | 50 ms |
| `647-Cy5` | 764 | 10 ms | **500 ms** | 500 ms | 500 ms |
| `488-GFP` | 302 | 5 ms | **50 ms** | 2,000 ms | 2,000 ms |
| `555-TRITC` | 23 | 5 ms | 10 ms | 20 ms | 20 ms |
| `488nm_Blue` | 20 | 20 ms | 30 ms | 30 ms | 30 ms |
| `DMD_Green` | 2 | 30 ms | 30 ms | — | 30 ms |

`DMD_Green` 채널의 존재 = **DMD(패턴 조명)가 시스템에 있(었)다.** 광구동 능동물질
실험에 직결되는데 config에는 DMD 장치가 안 보인다. 확인 필요.

647-Cy5의 노출이 500 ms에 몰려 있는 것은 실질적으로 **상한에 붙어 있다**는 뜻이고,
그 조건에서는 2 Hz 이상 촬영이 불가능하다.

---

## 8. ROI 사용 패턴

| ROI | 건수 | 해석 |
|---|---|---|
| `0-0-1608-1608` | 1,218 | 전체 프레임 |
| `~90–200 px` 정사각 (센서 중앙 부근) | 다수 | **고속 추적용 크롭.** 예: `726-762-120-108`, `717-750-138-135` |
| `603-603-402-402` | 27 | 중간 크기 |

크롭 중심이 대략 (780, 810)으로 센서 중심(804, 804) 근처다.
sCMOS는 행 단위 readout이므로 세로 크기를 줄여야 속도가 오른다 —
가로만 줄이면 효과가 없다. → [결정 엔진 §4](../docs/04-decision-engine.md)

---

## 9. 초점 유지

`PFS-FocusMaintenance`: `On` 1,033 / `Off` 1,306.
`PFS-PFS in Range`는 예시 파일에서 `Out of Range`였다 —
PFS가 켜져 있어도 잠기지 않은 세션이 섞여 있을 수 있다. 인덱싱 시 함께 기록할 것.

---

## 10. Micro-Manager 1.4 vs 2.0 — 스키마가 다르다

세대 A(2,137건, 전체의 91%)는 MM 1.4.23이고 `Summary` 구조가 2.0과 다르다.
**하나의 파서로 처리하면 대부분의 데이터를 놓친다.**

| 필드 | MM 1.4.23 | MM 2.0.3 |
|---|---|---|
| 픽셀 크기 | `PixelSize_um` | `PixelSizeUm` |
| ROI | `Summary.ROI` = 배열 `[606,690,357,186]` | FrameKey 문자열 `"742-898-160-176"` |
| 시작 시각 | **없음** (`UUID`만) | `StartTime` |
| 프레임의 카메라 | **없음** | `Camera` |
| 프레임의 binning | **없음** | `Binning` |
| 비트깊이 | `Summary.BitDepth` | FrameKey `BitDepth` |
| 장치 키 목록 | 없음 | `ScopeDataKeys` |
| 기타 | `PVCAM-TimeStamp`, `ChColors`, `IJType` | `AxisOrder`, `IntendedDimensions`, `UserData` |

세대 A에서 `Camera` 필드가 없어 스캔 결과 1,118건이 카메라 미상으로 나왔다.
`Prime95B-*` 접두 속성이나 `Core-Camera`로 역추적해야 한다.

---

## 11. 폴더명 규약 — 사실상 가장 정직한 기록

메타데이터에 안 남은 정보가 폴더명에는 남아 있다(예: 세대 C의 1.5x).
547개의 고유 폴더명이 있다.

```
{시료/염료}_{Las<세기 또는 파장>}_{Exp<노출ms>}_{배율}_{binning}_{반복번호}
```

실례:
```
SA647_Las10_Exp500_100x_1x1_20
OT0.005_Las555_5_exp10_100x_1.5x_1x1_1
dtz1um_g-actin_488_Las5_Exp50_100x_1x1_2
Polar_0deg_Exp30_60x_1x1_1
va5_vr5_BF_Exp10_100x_1x1_1
Focus0.4_OT0.05_str0.1_exp10_100x1.5x_1x1_1
```

관찰된 라벨 토큰: `SA647`(243), `DEX647`(134), `Atto647`(111), `AO488`(103),
`std488`(76), `Las488`(61), `BF`(31), `AF647`(19), `FITC`(15), `Phal647`(10),
`MQFITC`(10), `TRITC555`(9), `Polar/Pol0/Pol90`(11), `Cy5`(2).

기타 토큰: `OT<값>`(광집게 출력), `str<값>`, `Focus<값>`, `va5_vr5`, `<n>mM`, `dtz1um`.

**주의**: `Las10`은 세기 10%, `Las488`은 파장 488 nm, `Las555_5`는 555 nm 라인을 5%.
같은 접두어가 두 가지 뜻이다. 숫자가 350–800 정수면 파장으로 해석해야 한다.

---

## 12. 이 인벤토리에서 도출되는 최우선 확보 대상

1. **현재 시스템의 MM `.cfg`** — 필터 휠/큐브 라벨, Channel 프리셋 정의
2. **필터 세트 부품번호** — `DA/FI/TR10Empty`의 실체
3. **대물렌즈 실물 각인** — NA, 침지, WD
4. **픽셀 크기 실측 교정** — 배율별
5. **조명 출력 실측** — 파워미터로 `%` → mW@sample, 대물렌즈별
6. **현재 시스템이 위 세 세대 중 무엇의 후속인지, 아니면 완전히 별개인지**
