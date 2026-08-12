# 2026-08-12 · 디스크 대역폭 우회 — RAM 선촬영 후 flush

> `docs/02 §9`의 결정 로그 양식은 **실제로 실행한 실험 결과**를 위한 것이다.
> 이 항목은 아직 실행 전 설계 아이디어라 "실제로 쓴 설정"·"결과" 대신
> "제안한 우회법"·"계산 근거"·"남은 확인사항"을 적는다. 실제로 이 방식을
> 구현·실행하면 이 파일에 결과를 추가하거나 별도 결정 로그를 만들 것.

## 요구

Kinetix 듀얼캠(Kinetix_red/Kinetix_blue), 카메라당 2400×2400 ROI, 200 fps,
60초 촬영이 이 시스템에서 가능한지 확인.

## 게이트 출력 (`compute.cli check`, 실제 실행)

```
python -m compute.cli check --width 4800 --height 2400 --fps 200 \
    --disk-bandwidth-mb-s 206.8 --ram-budget-mb 16000 \
    --acquisition-duration-s 60 --free-disk-gb 2559
```
(가로폭 2배 트릭으로 듀얼캠 합산 바이트량을 표현 — `compute.checks`는 단일
스트림 기준이라 두 카메라 합산은 수동으로 반영해야 함.)

결과: **FAIL / INFEASIBLE**
- `data_rate.exceeds_disk`: margin 0.03 — 필요 4608 MB/s (2400×2400×2bytes×200fps×2대)
  vs 디스크 예산 145 MB/s (D: 드라이브 실측 206.8 MB/s × 0.7, [kb/calibrations/disk-bandwidth.yaml](../calibrations/disk-bandwidth.yaml))
  → **약 32배 초과**. 실시간 디스크 쓰기로는 이 조합이 안 됨 (silent frame drop).
- `buffer.too_small`: margin 0.69 — RAM 16GB 버퍼로 3.5초치만 (5초 기준 미달)

병목은 D: 드라이브 자체(SATA SSD급, ~207 MB/s)가 이 데이터율을 감당 못 하는 것.
ROI/fps로 풀려면: 200fps 유지 시 ROI ≤ 카메라당 ~425×425 px, 또는 2400×2400
유지 시 ~6 fps까지 낮춰야 함.

## 제안한 우회법: RAM 선촬영 → 촬영 후 flush

촬영 중엔 디스크에 안 쓰고 프레임을 전부 RAM(numpy 배열 등)에 쌓은 뒤,
촬영이 끝나고 나서 디스크로 flush. 이러면 실시간 디스크 대역폭 제약(G12)이
없어지고, 제약이 **"전체 촬영 데이터가 RAM에 들어가는가"**로 바뀐다
(G13b 용량 체크와 같은 형태지만 기준이 디스크가 아니라 RAM).

### 계산 근거

시스템 총 RAM: 255.65 GB (측정 시점 idle 사용량 ~29.8 GB, 여유 ~226 GB).
2400×2400 듀얼캠 데이터율 = 23.04 MB/frame-pair × fps.

| 시나리오 | 필요 RAM | 판정 |
|---|---|---|
| 200 fps × 60 s (원래 목표) | ~276 GB | ❌ 총 RAM(255.65GB)보다 큼 — 전체를 다 써도 불가 |
| 200 fps × 55 s | ~253 GB | ⚠ 거의 전량, OS/MM 여유 없음 — 위험 |
| 200 fps × **43 s** | ~200 GB | ✅ 55GB 여유 두고 안전 |
| **145 fps** × 60 s | ~200 GB | ✅ 60초 유지, fps만 낮춤 |
| 200 fps × 30 s | ~138 GB | ✅ 여유 있음 |

촬영 후 디스크 flush 시간 (D: 실측 206.8 MB/s 기준): 200 GB ≈ 16분 (비실시간,
그동안 이 드라이브로 다른 촬영 불가).

### 구현 상 걸림돌 (미확인)

Micro-Manager 기본 저장 방식(원형 버퍼 → 계속 디스크로 흘려보냄)은 이
"다 찍고 한번에 쓰기" 패턴을 기본으로 지원하지 않을 가능성이 높다.
[project_pymmcore_only_no_nis 결정](../../docs/07-roadmap.md)에 따라 이
프로젝트는 NIS-Elements 대신 pymmcore-plus로 직접 장치를 제어하기로 했으므로,
MM의 표준 스트리밍 저장 대신 **pymmcore-plus로 프레임을 직접 polling해서
preallocated numpy 배열에 채우고, 끝난 뒤 저장하는 커스텀 캡처 루프**를
짜야 할 것으로 보인다 — 아직 코드로 구현/검증 안 됨.

## 구현한 것 (2026-08-12)

| 파일 | 역할 |
|---|---|
| [`calibration/ram_capture.py`](../../calibration/ram_capture.py) | `capture_burst_to_ram()` — MMCore 시퀀스 획득으로 프레임을 preallocated numpy 배열에 채움 (디스크 미기록). `flush_to_disk()` — 캡처 끝난 뒤 `.npy`로 저장(fsync 포함), 처리량 리포트 |
| CLI `python -m calibration.cli ram-burst <cfg> --camera <label> --n-frames <N> [--out <path>]` | |
| [`tests/test_ram_capture.py`](../../tests/test_ram_capture.py) | pymmcore-plus 데모카메라로 3개 테스트 통과 (요청 프레임 수만큼 캡처, 잘못된 입력 거부, flush 후 round-trip 일치) |

**실측 확인된 것**: 데모카메라(512×512, 16bit) 기준 8프레임 91 fps 캡처, 5프레임
플러시 89 MB/s — 플러밍 자체는 동작. **아직 미확인**: 랩의 실제 PVCAM/Kinetix
어댑터 대상 실행, 그리고 **듀얼카메라 동시 캡처** (`capture_burst_to_ram()`은
카메라 1대 기준 — 두 카메라를 동시에 돌리려면 스레드 2개 또는 `CMMCorePlus`
인스턴스 2개로 호출해야 하는데, 실제 어댑터에서 정말 동시에 도는지 직렬화되는지
미확인, 추측 금지).

## 남은 확인사항

- [x] 실제 MM/pymmcore-plus로 "촬영 중 디스크 미기록, RAM만 채우기"가 되는지 확인
      → 데모카메라로 구현·검증 완료 (`calibration/ram_capture.py`)
- [ ] 실제 Kinetix/PVCAM 어댑터 대상으로 재검증 (데모카메라와 실제 어댑터의
      시퀀스 획득 동작이 같다고 가정하지 말 것)
- [ ] 듀얼카메라(Kinetix_red/Kinetix_blue) 동시 캡처가 실제로 동시에 도는지 확인
- [ ] 촬영 중 다른 프로세스(DMD·피에조·광집게 제어, OS)가 실제로 얼마나 RAM을
      쓰는지 실측 — 위 표의 "55GB 여유"는 idle 기준 추정값
- [ ] 이 방식을 `compute.checks`에 새 체크(예: G13d "RAM capacity")로 코드화할지 결정
