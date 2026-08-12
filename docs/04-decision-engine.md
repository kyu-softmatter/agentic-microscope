# 04 · 결정 엔진

설정을 **계산으로** 정하는 부분. LLM이 판단하지 않는 영역이다.
여기 있는 식은 전부 닫힌 형태이고, 입력이 없으면 값을 만들지 않고 거절한다.

> 이 문서의 수치 예시는 아카이브(구 셋업)에서 나온 것이다.
> 현재 시스템 값으로 반드시 다시 계산할 것. → [reference/observed-systems.md](../reference/observed-systems.md)

---

## 1. 결정 순서

자유도를 아무 순서로나 정하면 안 된다. **뒤 단계가 앞 단계를 무효화하지 않는 순서**가
있고, 그 순서는 물리가 정한다.

```
 ① 측정하려는 물리량과 목표 정밀도            ← 사람이 준다
        │
 ①' 계의 특성 시간 τ_c · 특성 길이 ℓ_c        ← kb/samples/<system>.md
        │                  (측정 가능하면 측정, 아니면 이론 추정 + evidence=assumed)
        │
 ② τ_c  →  필요 프레임레이트 f
        │                  (τ_c/10, 또는 광집게면 f ≳ 10·f_c)
        │
 ③ f  →  노출시간 상한   t_exp ≤ 1/f − t_readout
        │  그리고 모션블러 상한 (§5)
        │
 ④ 목표 정밀도  →  필요 검출 광자수 N        (§4 위치추정 정밀도 역산)
        │
 ⑤ N / t_exp  →  필요 검출 전자율  →  필요 여기 irradiance   (§3 광자수지 역산)
        │
 ⑥ irradiance  →  광표백 dose · 광섭동 확인   (초과하면 ②로 돌아감)
        │
 ⑦ ℓ_c + 대물·중간배율·binning  →  표본화 확인   (§2, ℓ_c와 작업 종속 둘 다 반영)
        │
 ⑧ ROI  →  ③의 t_readout 재계산 + 통계력 확인 (§7)
        │
 ⑨ 데이터율·버퍼·저장 확인                     (§8)
```

②↔⑥과 ③↔⑧이 순환한다. 수렴하지 않으면 **양립 불가**이고, 그 사실 자체가
출력이다 ([01 §3 원칙 5](01-architecture.md)).

**①'의 근거 등급**: `evidence: assumed`(이론 추정)여도 뒤 단계 계산에는
그대로 쓴다. 다만 최종 `advances`는 `evidence: measured`가 아니면 `false`로
남는다 — §3의 `power_at_sample_mw`와 같은 규칙. → [02 §8](02-knowledge-base.md)

---

## 2. 공간 — 표본화

### 유효 픽셀 크기

$$p_{\text{sample}} = \frac{p_{\text{sensor}} \times B}{M_{\text{obj}} \times M_{\text{int}}}$$

`PixelSizeUm`이 아카이브 전 파일에서 `0.0`이므로 **반드시 계산해야 한다.**

구 셋업 (11 µm 피치, B=1) 기준:

| 대물 | 중간배율 | p_sample |
|---|---|---|
| 100x | 1.5x | 73.3 nm |
| 100x | 1.0x | 110 nm |
| 60x | 1.0x | 183 nm |
| 40x | 1.0x | 275 nm |
| 20x | 1.0x | 550 nm |
| 10x | 1.0x | 1,100 nm |

> ⚠ 계산값이지 교정값이 아니다. 스테이지 마이크로미터나 격자로 배율별 실측 교정을
> 한 번 하고, 그 값을 프로파일에 넣어야 한다. 계산과 실측이 3–5% 어긋나는 건 흔하다.

### 회절 한계

$$r_{\text{Rayleigh}} = \frac{0.61\,\lambda_{em}}{NA} \qquad
\sigma_{\text{PSF}} \approx \frac{0.21\,\lambda_{em}}{NA} \qquad
\text{DOF} \approx \frac{n\,\lambda}{NA^2}$$

### ⚠ 최적 픽셀 크기는 작업에 따라 반대로 간다

**이것이 이 엔진에서 가장 틀리기 쉬운 지점이다.**

| 작업 | 기준 | 100x/NA1.45, λ=668 nm |
|---|---|---|
| **형태·구조 관찰** | Nyquist: `p ≤ r/2` | r = 281 nm → **p ≤ 140 nm** |
| **단일입자 위치추적** | `p ≈ σ_PSF` 부근이 최적 | σ = 97 nm → **p ≈ 100 nm** |

추적에서 Nyquist를 기계적으로 적용해 픽셀을 더 잘게 쪼개면 **정밀도가 나빠진다.**
Thompson–Larson–Webb / Mortensen 위치추정 분산:

$$\sigma_{\text{loc}}^2 = \frac{\sigma_a^2}{N} + \frac{8\pi\,\sigma_a^4\,b^2}{p^2 N^2},
\qquad \sigma_a^2 = \sigma_{\text{PSF}}^2 + \frac{p^2}{12}$$

- 첫째 항(광자 산탄잡음)은 `p`가 커지면 `p²/12` 때문에 나빠진다
- 둘째 항(배경잡음)은 `p`가 커지면 **좋아진다** (`1/p²`)

→ 배경이 있는 실전에서는 유한한 최적 `p`가 존재한다. 이 랩의 마이크로레올로지는
전부 여기에 해당한다.

**게이트 구현**: 작업 종류(`imaging` / `tracking`)를 입력으로 받아 기준을 바꾼다.
작업이 명시되지 않으면 **묻는다.** 기본값을 쓰지 않는다.

### ⚠ ℓ_c가 회절한계 이하면 애초에 분해 불가

`kb/samples/<system>.md`의 `characteristic_scales.length`(예: 액틴 메시
크기, ATPS 계면 두께)가 `σ_PSF`보다 작으면, 픽셀을 아무리 줄여도 그 구조를
직접 분해할 수 없다. 표본화 게이트(위 두 기준)가 통과해도 의미가 없다 —
**문제가 카메라가 아니라 광학 회절한계이기 때문이다.** 이 판정은 아직
게이트가 없다.

---

## 3. 광자수지

### 사슬 전체

```
광원 출력 P [W]  (샘플면 실측)
   ↓  조명 면적 A로 나눔
irradiance  I = P/A  [W/cm²]
   ↓  광자 에너지 hc/λ 로 나눔
광자속  φ = I λ /(hc)  [photons cm⁻² s⁻¹]
   ↓  흡수 단면적
여기율  k_ex = σ_abs · φ · (스펙트럼 겹침)  [s⁻¹]
   ↓  양자수율
방출율  k_em = k_ex · Φ_F
   ↓  대물 수집 입체각
   ↓  방출경로 투과율 × 카메라 QE
검출율  k_det = k_em · η_geo · T_em · QE   [e⁻/s/분자]
   ↓  노출시간
프레임당 신호  S = k_det · t_exp  [e⁻]
```

**흡수 단면적** (ε는 M⁻¹cm⁻¹):

$$\sigma_{\text{abs}} = 3.82\times10^{-21}\,\varepsilon \quad [\text{cm}^2]$$

**기하 수집 효율** — 광자수지에서 가장 큰 항이고 어림 계산에서 가장 자주 빠진다:

$$\eta_{\text{geo}} = \frac{1-\cos\theta}{2}, \qquad \sin\theta = \frac{NA}{n}$$

| 대물 | η_geo | 4π 중 |
|---|---|---|
| 100x NA 1.45 oil (n=1.518) | **0.352** | 35.2% |
| 60x NA 1.20 water (n=1.333) | **0.282** | 28.2% |
| 10x NA 0.30 air | **0.0230** | 2.3% |

`optics/components.py :: Objective.collection_efficiency` 로 구현되어 있고
테스트로 검증되어 있다.

### 포화

$$I_{\text{sat}} = \frac{hc}{\lambda\,\sigma_{\text{abs}}\,\tau_{\text{fl}}}$$

`k_ex → 1/τ_fl` 에 접근하면 위 선형 모델은 과대평가한다. 삼중항 shelving은
더 낮은 세기에서 먼저 온다. **현재 구현은 포화를 모델링하지 않으므로**
`I ≳ 0.1·I_sat` 이면 경고를 내야 한다.

### ⚠ 광량 실측이 없으면 이 절 전체가 무효

`power_at_sample_mw`가 비어 있으면 `detected_e_per_s()`는 **`None`을 반환한다.**
숫자를 지어내지 않는다. 그 경우 가능한 것은 같은 장비 안에서의 상대 비교뿐이다.

```python
# 아카이브 상태 그대로
ch.detected_e_per_s()  # -> None

# 파워미터로 30분 측정한 뒤
ch.detected_e_per_s(power_mw_at_sample=1.0, illuminated_area_um2=100*100)  # -> 값
```

측정 절차는 [data/light_sources.yaml](../data/light_sources.yaml) 머리말에 있다.

---

## 4. SNR과 정밀도

### SNR

스팟이 `n_pix` 픽셀에 퍼져 있을 때:

$$\text{SNR} = \frac{N_{\text{sig}}}
{\sqrt{N_{\text{sig}} + N_{\text{bg}} + N_{\text{dark}} + n_{\text{pix}}\,\sigma_{\text{read}}^2}}$$

- `N_sig` : 신호 전자수 = `k_det · t_exp`
- `N_bg` : 배경 (자가형광, 산란, 초점 밖 형광) — **실측해야 한다.** 계산 불가
- `N_dark` : 암전류 × t_exp
- `σ_read` : sCMOS는 픽셀마다 다르다 (고정패턴). 평균값만 쓰면 낙관적

### ⚠ 12-bit 모드의 양자화 잡음이 read noise를 압도한다

아카이브에서 실제로 쓰인 두 모드를 계산하면:

| 모드 | full well | bits | e⁻/ADU | 양자화잡음 `q/√12` | read noise | **실효 잡음** |
|---|---|---|---|---|---|---|
| `100MHz 16bit` / HDR | 80,000 | 16 | 1.22 | 0.35 e⁻ | ~1.3 e⁻ | **1.35 e⁻** |
| `200MHz 12bit` / Full well | 62,000 | 12 | 15.14 | **4.37 e⁻** | ~1.6 e⁻ | **4.65 e⁻** |

속도를 위해 12-bit를 고르면 **실효 잡음이 3.4배** 커진다. 약신호에서는 SNR이
그대로 3.4배 나빠진다. `full_well`과 `bit_depth`는 메타데이터에 있으므로
이 계산은 항상 가능하다 — 추론이 아니다.

> read noise 자체는 데이터시트 확인 필요. 양자화 항은 확정값이다.

### 포화 여유

$$N_{\text{peak}} < 0.7 \times \text{full well}, \qquad
\text{ADU}_{\text{peak}} < 0.9 \times 2^{\text{bits}}$$

`Offset = 100 ADU`(관찰값)를 빼고 계산해야 한다.

### 목표 정밀도 → 필요 광자수

§2의 위치추정 식을 `N`에 대해 역산한다. 배경이 없을 때의 하한:

$$N \gtrsim \frac{\sigma_a^2}{\sigma_{\text{loc,target}}^2}$$

예: `σ_PSF = 97 nm`, `p = 110 nm`, 목표 `σ_loc = 10 nm`
→ `σ_a² = 97² + 110²/12 = 9409 + 1008 = 10417 nm²`
→ `N ≳ 104` 검출 광자. 배경이 있으면 훨씬 커진다.

---

## 5. 시간 — 노출·프레임레이트·모션블러

### 프레임 주기

$$t_{\text{frame}} = \max\!\left(t_{\text{exp}} + t_{\text{overhead}},\; t_{\text{readout}}\right)$$

**롤링셔터 sCMOS의 readout은 행 수에만 비례한다.**

아카이브 메타데이터에서 행 시간을 역산할 수 있다 (독립된 두 파일에서 일치):

| ROI 높이 | `Timing-ReadoutTimeNs` | 행당 |
|---|---|---|
| 176 행 | 1,809,000 ns | 10.28 µs |
| 186 행 | 1,912,000 ns | 10.28 µs |

→ **10.28 µs/행**. 이로부터:

| ROI 높이 | readout | 이론 최대 fps |
|---|---|---|
| 1608 (전체) | 16.53 ms | 60.5 |
| 402 | 4.13 ms | 242 |
| 176 | 1.81 ms | 553 |
| 108 | 1.11 ms | 901 |

**폭을 줄여도 빨라지지 않는다.** 높이를 줄여야 한다.
아카이브의 크롭들이 대체로 정사각형인데, 속도가 목적이었다면 **가로로 긴 ROI가
같은 화소수에서 더 빠르다.**

### ⚠ 실제로는 이론값의 1/3밖에 못 냈다

관찰: 노출 10 ms, ROI 176행 → 카메라 한계 ~85 Hz.
그런데 `ActualInterval-ms = 35.67` → **실측 28 Hz, duty cycle 28%.**

카메라가 병목이 아니다. MM 오버헤드 / 디스크 / 순환버퍼 중 하나다.
→ 전산자원 렌즈(§8)의 소관이고, **"요청 프레임레이트"가 아니라 "실측 프레임레이트"를
KB에 기록해야 하는 이유**다.

### 모션블러 — 마이크로레올로지에서 결정적

노출 `t_exp` 동안 입자가 움직인 거리가 PSF를 넘으면 신호가 뭉개진다.
그것보다 나쁜 건 **MSD에 계통 편향이 생기는 것**이다.

Savin–Doyle 보정 (1차원, 균일 노출):

$$\langle \Delta x^2 \rangle_{\text{meas}}(\tau)
= 2D\left(\tau - \frac{t_{\text{exp}}}{3}\right) + 2\varepsilon^2$$

- `−2D·t_exp/3` : 동적 오차(블러). MSD를 **과소평가**
- `+2ε²` : 정적 위치추정 오차. MSD를 **과대평가**

두 항이 짧은 lag에서 서로 상쇄되어 **그럴듯하지만 틀린 직선**을 만들 수 있다.
그대로 GSER로 넘기면 모듈러스가 틀린다.

**게이트**: 가장 짧은 lag `τ_min = 1/f` 에서의 상대 편향

$$\left|\frac{t_{\text{exp}}/3}{\tau_{\min}}\right| < 0.1
\quad\Longleftrightarrow\quad t_{\exp} < 0.3\,\tau_{\min}$$

즉 **duty cycle 30% 이하**. 아카이브의 28%는 우연히 이 조건을 만족한다.
`t_exp = 1/f` (duty 100%)로 밀어붙이면 최단 lag에서 33% 편향이 생긴다.

---

## 6. 광표백 예산

분자당 총 방출 광자수:

$$N_{\text{emitted}} = k_{em} \times t_{\exp} \times N_{\text{frames}}$$

염료의 `bleach_photons`(표백 전 평균 방출 광자수)를 알면:

$$f_{\text{bleached}} = 1 - \exp\!\left(-\frac{N_{\text{emitted}}}{N_{\text{bleach}}}\right)$$

**게이트**: 영상 전체에서 `f_bleached < 0.2`, 아니면 강도 감쇠 보정이 가능해야 한다.

`bleach_photons`는 [data/fluorophores.yaml](../data/fluorophores.yaml)에 아직
비어 있다. 없으면 이 게이트는 `BLOCKED`이고, 정성적 `photostability` 등급으로는
대체하지 않는다.

> 광표백은 조명 세기에 **초선형**인 경우가 많다(삼중항 경로). 위 식은 하한이다.

---

## 7. ROI — 속도와 통계력의 교환

ROI를 줄이면 빨라지지만 시야 안 입자 수가 줄어든다.

$$N_{\text{particles}} = c \times \text{FOV}_x \times \text{FOV}_y \times h$$

마이크로레올로지 앙상블 평균의 통계 오차는 대략 `1/√(N_particles × N_frames)`.
프레임레이트를 4배 얻으려고 면적을 1/4로 줄이면 입자 수가 1/4이 되어
**순이득이 사라질 수 있다.**

**게이트**: 목표 lag 범위와 목표 오차를 받아 필요한 `N_particles × N_frames`를
역산하고, 제안된 ROI가 그것을 만족하는지 확인한다.

---

## 8. 전산자원

### 데이터율

$$R = W \times H \times \frac{\text{bits}}{8} \times f \quad [\text{B/s}]$$

| 구성 | 데이터율 | 판정 |
|---|---|---|
| 1608² · 16bit · 60 fps | **310 MB/s** | NVMe 필수. SATA SSD(~500 MB/s)도 지속쓰기에서 위험 |
| 1608² · 12bit(16bit 저장) · 30 fps | 155 MB/s | SATA SSD 가능 |
| 176² · 16bit · 550 fps | 34 MB/s | 여유 |

> MM은 12bit도 16bit 컨테이너로 저장한다. 디스크 계산은 16bit로 해야 한다.

### 순환버퍼 (RAM)

$$\text{buffer} = N_{\text{frames}} \times W \times H \times 2 \text{ bytes}$$

관찰값: `CircularBufferFrameCount = 552`, `CircularBufferAutoSize = ON`

| 프레임 크기 | 552 프레임 버퍼 |
|---|---|
| 176 × 160 | 31 MB |
| 1608 × 1608 | **2.85 GB** |

`AutoSize ON`이면 MM이 가용 RAM에 맞춰 잡는다. 버퍼가 데이터율을 흡수하지
못하면 **프레임 드랍**이 나고, 이건 조용히 일어난다 —
`ElapsedTime-ms` 간격이 불규칙해지는 것으로만 드러난다.

**게이트**:
- `R < 0.7 × 디스크 지속쓰기 대역폭`
- `버퍼 ≥ 5초분 데이터` (일시적 디스크 지연 흡수)
- `총 용량 = R × 촬영시간 < 여유 공간`
- 실시간 처리를 붙일 경우 프레임당 CPU 시간 `< 1/f`

**사후 검증**: 획득 후 `ElapsedTime-ms` 차분의 분산을 보고 드랍을 검출한다.
이건 지금 아카이브에서도 바로 할 수 있고, 해야 한다.

---

## 9. 하드 게이트 요약

전부 코드로 판정. 하나라도 실패하면 제안이 무효다.

| # | 게이트 | 기준 | 필요 입력 | 없으면 |
|---|---|---|---|---|
| G1 | 여기 결합 | `ex_eff > 0`, 이상 대비 ≥ 20% | 염료 흡수, 광원, 여기경로 | BLOCKED |
| G2 | 방출 수집 | `spectral_collection ≥ 15%` | 염료 방출, 방출경로, QE | BLOCKED |
| G3 | 여기광 차단 | `≥ 5 OD` (근사 스펙트럼이면 7 OD) | 방출경로 곡선 | BLOCKED |
| G4 | 크로스토크 | `< 5%` | 모든 채널 스펙트럼 | BLOCKED |
| G5 | 표본화 | 작업별 (§2) | NA, 픽셀피치, 배율, **작업 종류** | 질문 |
| G6 | 포화 여유 | `peak < 0.7 × full well` | full well, 광자수지 | BLOCKED |
| G7 | SNR | 목표치 이상 | 광량 실측, 배경 실측 | BLOCKED |
| G8 | 모션블러 | `t_exp < 0.3 τ_min` | D 또는 τ_c | 질문 |
| G9 | 프레임레이트 실현성 | `f ≤ 1/max(t_exp, t_readout)` | 행 시간, ROI | 계산 가능 |
| G10 | 광표백 | 영상 전체 `< 20%` | `bleach_photons`, 광자수지 | BLOCKED |
| G11 | 통계력 | 목표 오차 달성 | 입자농도, 목표 정밀도 | 질문 |
| G12 | 데이터율 | `< 0.7 ×` 디스크 대역폭 | 디스크 실측 대역폭 | 측정 요구 |
| G13 | 버퍼 | `≥ 5초분` | RAM, 프레임 크기 | 계산 가능 |
| G14 | 광집게 샘플링 | `f_s ≥ 10 f_c` | κ, 점성, 입자 반경 | BLOCKED |

**`BLOCKED`는 `FAIL`이 아니다.** FAIL은 "이 설정은 물리적으로 나쁘다",
BLOCKED는 "판정할 근거가 없다"이다. 둘 다 다음 단계로 못 가지만 조치가 다르다:
FAIL은 설정을 바꾸고, BLOCKED는 **측정하거나 데이터시트를 찾아야** 한다.

---

## 10. 구현 현황

| 절 | 내용 | 상태 |
|---|---|---|
| §2 회절·수집 | `Objective.resolution_nm`, `collection_efficiency`, `depth_of_field_nm` | ✅ 테스트됨 |
| §3 광자수지 | `Channel.detected_e_per_s` (광량 없으면 `None`) | ✅ 테스트됨 |
| §3 스펙트럼 | 여기효율·수집·차단·크로스토크 | ✅ 테스트됨 |
| G1–G4 | `optics.gate.evaluate` | ✅ 테스트됨 |
| §2 표본화 게이트 (G5) | 작업 종속 분기, `detection.gate.evaluate` | ✅ 테스트됨 (2026-08-11) |
| §4 SNR·포화 (G6, G7) | `detection.gate.evaluate` | ✅ 테스트됨 (2026-08-11) |
| §5 타이밍·블러 (G8, G9) | `detection.gate.evaluate` | ✅ 테스트됨 (2026-08-11) |
| §6 표백 (G10) | | ❌ |
| §7 통계력 (G11) | | ❌ |
| §8 전산자원 (G12, G13) | `compute.gate.evaluate` | ✅ 테스트됨 (2026-08-11) |
| §9 광집게 (G14) | MATLAB·논문 수령 후 | ❌ |
