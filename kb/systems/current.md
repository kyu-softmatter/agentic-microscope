---
id: current
status: current
fingerprint: null  # TODO: 장치 라벨 집합 + 카메라 시리얼 해시. 자동 인덱서 붙기 전까지 비움.
sources:
  - {kind: mm_config, path: "C:\\Users\\Takatori lab\\Desktop\\Maintanance\\micromanager\\DMD_dualcam.cfg", date: 2026-07-03}
  - {kind: calibration, path: "C:\\Users\\Takatori lab\\Desktop\\Confocal_microscope_conversion_factor(Apr 2025).xlsx", date: 2025-04}
  - {kind: nis_elements_device_manager, path: "live GUI — Device Manager (Nikon Ti2 hardware setup) + Filter Block Settings dialogs (Turret1/DM/Splitter/EM1)", date: 2026-08-10}
  - {kind: nikon_catalog, path: "https://www.microscope.healthcare.nikon.com/products/optics/selector/comparison/ [-179794, -179798, -179802, -1923, -179808, -179810]", date: 2026-08-10}
  - {kind: purchase_quote, path: "reference/quotes/2024-09-29_nikon-quote-REDACTED_ti2e-csuw1_takatori.md", date: 2024-09-29, note: "Nikon 견적 #REDACTED (Takatori 랩). 대물렌즈 6종·EM1 필터 4종·FilterTurret1 pos0 큐브(MXR00724)·CSU-W1 본체가 부품번호까지 일치 — 해당 필드의 구매 기록 출처로 격상 가능. 카메라 구성은 불일치(견적: Kinetix22+Prime95B, 현재: Kinetix ×2) — 최종 발주 변경 또는 이후 교체, 미확인. 상세 대조는 해당 md 파일 참고."}
  - {kind: nis_elements_device_manager, path: "live GUI — Filter Block Settings (DM) 재확인 + calibration.cli camera-probe 실측 대조", date: 2026-08-11, note: "DM=CSUW1-Dichroic 동일 소자 확인, EM1=Kinetix_red/EM2=Kinetix_blue 카메라 배정 확정, EM2 필터 구성 독립 확인."}
  - {kind: calibration, path: kb/calibrations/disk-bandwidth.yaml, date: 2026-08-12, note: "D: 드라이브 지속쓰기 대역폭 206.8 MB/s 실측 (calibration.cli disk-bandwidth, 4GB). G12 예산 = 0.7×206.8 = 144.8 MB/s. MM 실제 저장 폴더와 정확히 일치하는지는 미확인 — 다른 폴더면 재측정."}
  - {kind: calibration, path: kb/calibrations/camera-readout.yaml, date: 2026-08-12, note: "PVCAM 어댑터 실측 (calibration.cli camera-readout, dual_cam_test.cfg). Timing-ReadoutTimeNs=8,475,000 → row time ≈3531.2 ns/row (ROI 2400 rows). 단위는 property명 근거 추정, 문서 대조 아직 없음."}
  - {kind: pymmcore_plus_live, path: "DMD_dualcam.cfg 사본(MightexPolygon1000 줄만 제거) — pymmcore-plus로 실제 로드", date: 2026-08-12, note: "Ti2-E__0/CSUW1-Hub/CSUW1-Dichroic/CSUW1-Filter_Red(EM1)/CSUW1-Filter_Blue(EM2)/Kinetix_red/Kinetix_blue/LightEngine/Aura 등 DMD 제외 전 장치 로드 성공, CSUW1-Dichroic state 0(on)·EM1/EM2 state 0(multi) 실측값이 kb 기록과 일치. NikonTi2 어댑터 로드에 Ti2_Mic_Driver.dll(랩 기존 설치에서 복사) 필요했음 — 아래 devices_not_in_mm_config 노트 참고."}

stand:
  vendor: Nikon
  model: Ti2-E
  mm_device: Ti2-E__0
  tube_lens_mm: 200          # Nikon Ti2 표준값. 실측/데이터시트 대조 안 됨 — verify
  autofocus: PFS
  verified: false

cameras:
  - device: Kinetix_red
    role: Core.Camera (기본 활성 카메라)
    vendor: Photometrics
    model: Kinetix
    adapter: PVCAM
    mm_label: Camera-2
    serial: null             # .cfg에 시리얼 없음 — PVCAM 장치 속성이나 라벨에서 추가 확인 필요
  - device: Kinetix_blue
    vendor: Photometrics
    model: Kinetix
    adapter: PVCAM
    mm_label: Camera-1
    serial: null

objectives:            # Nosepiece (6-position). 2026-08-10: label 끝자리는 WD(mm)로 확정 (Nikon 카탈로그 파트넘버 대조). 2026-08-11: 물리 경통 각인 대조도 사용자가 완료·확인.
  - {turret: Nosepiece, position: 0, label: "1-Plan Apo LmbdD20 4x",         mag: 4,   product: "CFI Plan Apo Lambda D 4X",         part_number: MRD70040, na: 0.20, wd_mm: 20,        immersion: air,   cover_glass_mm: "0-0.17",  verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 1, label: "2-Plan Apo LmbdD4 10x",        mag: 10,  product: "CFI Plan Apo Lambda D 10X",        part_number: MRD70170, na: 0.45, wd_mm: 4,         immersion: air,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 2, label: "3-Plan Apo LmbdD0.8 20x",      mag: 20,  product: "CFI Plan Apo Lambda D 20X",        part_number: MRD70270, na: 0.80, wd_mm: 0.8,       immersion: air,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 3, label: "4-Apo LmbdS 40x WI",           mag: 40,  product: "CFI Apo Lambda S 40XC WI",         part_number: MRD77400, na: 1.25, wd_mm: "0.2-0.16 (correction collar dependent)", immersion: water, cover_glass_mm: "0.15-0.19", verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 4, label: "5-Plan Apo LmbdD0.15 60x Oil", mag: 60,  product: "CFI Plan Apo Lambda D 60X Oil",    part_number: MRD71670, na: 1.42, wd_mm: 0.15,      immersion: oil,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog, note: "pol: Simple POL, phase ring: EXT PH3"}
  - {turret: Nosepiece, position: 5, label: "6-Plan Apo LmbdD0.13 100x Oil",mag: 100, product: "CFI Plan Apo Lambda D 100X Oil",   part_number: MRD71970, na: 1.45, wd_mm: 0.13,      immersion: oil,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog}

filter_turrets:
  - device: FilterTurret1     # NIS-Elements 표시명: "Turret1"
    positions:
      0:
        label: "MXR00724 - LED-DA/FI/TR/Cy5/Cy7-A (DAPI/FITC/TRITC/Cy5/Cy7)"
        excitation_nm: [[353,403], [462,486], [544,565], [627,643], [722,748]]
        mirror_nm:     [[414,450], [499,530], [580,611], [661,701], [768,849]]
        emission_nm:   [[420,460], [510,531], [589,623], [677,711], [768,849]]
        registry: ["MXR00724-EX", "MXR00724-DM", "MXR00724-EM"]   # data/filters.yaml
        verified: true
        verified_date: 2026-08-10
        source: nis_elements_device_manager
      1: {label: "2-Empty"}
      2: {label: "3-Empty"}
      3: {label: "4-Empty"}
      4: {label: "5-Empty"}
      5: {label: "6-Empty"}
    note: >
      2026-08-10 NIS-Elements Device Manager > Filter Block Settings - Turret1에서
      실측 확인. 과거 MM .cfg 라벨 "1-MXR00724 -Empty"는 오해의 소지가 있었다 —
      실제로는 position 0에 실물 5-band 큐브가 있고, "Empty"는 표시 형식 문제였던
      것으로 결론. data/filters.yaml의 "DA/FI/TR10Empty"(kind: unknown, 과거
      메타데이터 2,312건이 가리키던 그 큐브) 항목이 이걸로 해소됨.
  - device: FilterTurret2
    positions:
      0:
        label: "OT 다이크로익 + 750/SP 방출필터"
        mirror_nm: [[750, null]]     # 750 nm보다 긴 파장만 반사 (1064 nm 트랩광용)
        emission_nm: [[null, 750]]   # 750/SP: 750 nm 이하만 통과
        registry: ["OT-Dichroic-750LP", "OT-EM-750SP"]
        verified: true
        verified_date: 2026-08-11
        source: user_dictation
      1: Empty
      2: Empty
      3: Empty
      4: Empty
      5: Empty
    note: >
      ⚠ 2026-08-10 정정: 위 "6개 슬롯 전부 비어 있음"은 NIS-Elements Device
      Manager 미확인 상태에서 쓴 것이었다. 사용자 구술로 광집게(OT) 경로에
      Turret2가 실제로 쓰인다는 것이 확인됨.
      **2026-08-11 갱신**: "여기·방출 필터는 없다"던 이전 문장은 틀렸음 —
      실제로는 부품 두 개가 있다: 다이크로익(750 nm보다 긴 파장만 반사 —
      1064 nm 트랩광을 대물렌즈 쪽으로 보내고 그보다 짧은 가시광은 투과)과
      750/SP(shortpass) 방출 필터(750 nm 이상 차단 — 산란된 1064 nm가
      접안/카메라로 새는 것을 방지). 사용자가 "slot 1"로 지칭 — 다른 항목의
      1-indexed GUI 라벨 관례를 따라 position 0으로 기록했으나 인덱싱 자체는
      재확인 전까지 가정. 정확한 vendor/part number는 여전히 미확인 —
      data/filters.yaml에 `OT-Dichroic-750LP`/`OT-EM-750SP`로 임시 등록.
      아래 light_paths > optical-tweezers 참고.

optical_path_nis:      # 2026-08-10 NIS-Elements Device Manager로만 확인 — MM .cfg에는 없음
  # 2026-08-11 정정: 여기 있던 'DM'(다이크로익 빔스플리터, Di01-T405/488/568/647)
  # 항목은 confocal_scanner > sub_devices > CSUW1-Dichroic와 동일한 물리 소자로
  # 확인됨 — "외부 DM과는 별개의 두 번째 소자"라던 2026-08-10 구술은 오류였다.
  # 중복 기록을 없애고 CSUW1-Dichroic 쪽으로 병합. 상세·band 값은 그 항목 참고.
  - device: Splitter
    purpose: "듀얼 카메라(C3PO/R2D2) 이미지 스플리터"
    positions:
      0: {label: "100/0 mirror", note: "완전 반사 — 단일 카메라 모드"}
      1: {label: "DM A561LP", mirror_nm: [[561, null]], note: "561 nm longpass", registry: "DM A561LP"}
      2: Empty
    current_position: 1 # DM A561LP
    note: >
      2026-08-10 사용자 확인: 현재 카메라 2대(Kinetix_red/Kinetix_blue)를 동시에
      쓰는 구성이고, 이 스플리터가 561 nm 기준으로 방출을 두 카메라에 나눈다
      (position 1, DM A561LP). 단일 카메라 모드(position 0)가 아님.
      → optics.Channel은 현재 다이크로익 필드가 하나뿐이라, 메인 컨포칼
      다이크로익(Di01-T) 다음에 이 스플리터까지 2단으로 파장에 따라 갈라지는
      구조를 아직 정확히 표현하지 못한다 — 카메라별 채널을 만들려면 Channel에
      "이 소자의 투과측/반사측 중 어느 쪽으로 가는가"를 표현할 방법이 필요함.
      대화에서 architecture 확장 방식을 논의 중.
    verified: true
    verified_date: 2026-08-10
  - device: EM1
    purpose: "방출 필터휠 — Kinetix_red(적색 채널 카메라) 전담"
    positions:
      0: {label: "multi", registry: null}
      1: {label: "405", registry: null}
      2: {label: "488", registry: null}
      3: {label: "555", registry: null}
      4: {label: "647", registry: null}
      5: Blocked   # 물리적으로 금속판으로 막혀 빛이 전혀 통과 못함 — 선택 불가 (2026-08-11 확인)
      6: Blocked
      7: Blocked
      8: Blocked
      9: {label: "Open", registry: "EM-Open", note: "빈 슬롯 — 필터 없음, 모든 광원에 대해 완전 개방(전 파장 투과). 2026-08-11 확인. .cfg Label 'open'과 일치."}
    verified: true
    verified_date: 2026-08-11
    source: mm_config
    note: >
      **2026-08-11 최종 정정**: 처음에 "88000v2-Quad/455/50/525/36/605/52/
      705/72"로 기록했던 필터 세트는 EM1의 실제 필터가 아니었다(다른 소자
      데이터가 잘못 여기 붙었던 것으로 보임 — 정확히 어디서 왔는지는 불명).
      실제 위치 0-4는 DMD_dualcam.cfg의 CSUW1-Filter_Red Label 값(multi/
      405/488/555/647)과 일치 — 이게 진짜 값이라고 사용자가 확인. 다만
      이 5개는 아직 중심파장 숫자만 있고 fwhm·실제 통과대역 데이터가 없어
      registry: null로 둔다(추측 금지 — data/filters.yaml에 값 생기면 연결).
      position 5-8은 Blocked(금속판, .cfg Label엔 "b1"~"b4"로 잘못 남아
      있던 것 — 실제로는 빈 카트리지 자리가 아니라 물리적으로 막혀 있음),
      9는 Open — .cfg Label "open"과 정확히 일치. 총 10개(0-9), .cfg의
      실제 슬롯 수와 맞음(2026-08-11 최종 확인).
      Splitter와 카메라 사이, 카메라 바로 앞에 있다. EM1/EM2 각각 카메라
      한 대씩 전담.
      **카메라 배정 확정**: EM1 = Kinetix_red (카메라별 밝기 실측 대조로
      확인 — 로드맵 Phase 0의 EM1/EM2 카메라 배정 블로커 해소).
      **정정**: "CSUW1-Filter_Red/Blue와는 별개 — 그쪽은 CSU-W1
      내부 소자"라던 예전 문장은 틀렸음. 물리 필터휠은 red/blue 담당 각 1개,
      총 2개뿐이고 confocal_scanner.sub_devices에 따로 있던 CSUW1-Filter_Red
      가 바로 이 EM1이다 (병합, 아래 confocal_scanner 참고). 컨포컬/와이드필드
      모드와 무관하게 항상 이 자리에 있다(사용자 확인).
    camera: Kinetix_red
  - device: EM2
    purpose: "방출 필터휠 — EM1과 동일 구성, Kinetix_blue(청색 채널 카메라) 전담"
    positions:
      0: {label: "multi", registry: null}
      1: {label: "405", registry: null}
      2: {label: "488", registry: null}
      3: {label: "555", registry: null}
      4: {label: "647", registry: null}
      5: Blocked   # 물리적으로 금속판으로 막혀 빛이 전혀 통과 못함 — 선택 불가 (2026-08-11 확인)
      6: Blocked
      7: Blocked
      8: Blocked
      9: {label: "Open", registry: "EM-Open", note: "빈 슬롯 — 필터 없음, 모든 광원에 대해 완전 개방(전 파장 투과). 2026-08-11 확인. .cfg Label 'open'과 일치."}
    camera: Kinetix_blue
    verified: true
    verified_date: 2026-08-11
    source: mm_config
    note: >
      2026-08-10 사용자 확인: "EM2는 EM1과 동일한 구성" — 그래서 positions는
      EM1과 같은 필터(부품 스펙 기준)를 그대로 참조했다.
      **2026-08-11 최종 정정**: 위 EM1과 같은 이유로 "88000v2-Quad/455/50/
      525/36/605/52/705/72" 세트는 실제 값이 아니었음 — multi/405/488/555/
      647(position 0-4) + Blocked(5-8) + Open(9)으로 정정, 총 10개(0-9)로
      .cfg 슬롯 수와 일치. fwhm·실제 통과대역 데이터 없어 registry: null
      (추측 금지). EM1과 동일 구성임은 NIS-Elements 직접 대조로 확인됨
      (더 이상 진술 추정 아님).
      카메라 배정 확정: EM2 = Kinetix_blue (EM1 확정과 함께 실측 대조됨 —
      위 EM1 note 참고).
    verified: true
    verified_date: 2026-08-11

light_sources:
  - device: LightEngine
    vendor: Lumencor
    model: SpectraIII         # 2026-08-10 NIS-Elements Device Manager로 확인 (다이어그램 라벨 "SpectraIII")
    model_field: GEN3         # MM 어댑터의 통신 프로토콜 세대 표기
    connection: COM3
    lines_nm_approx: [365, 440, 488, 514, 561, 594, 640]   # 다이어그램 아이콘 판독 — fwhm 미확인
    registry: SpectraIII      # data/light_sources.yaml
    verified_product_name: true
    verified_date: 2026-08-10
    source: nis_elements_device_manager
  - device: Aura
    vendor: Lumencor
    model: AuraIII            # 2026-08-10 NIS-Elements Device Manager로 확인 (다이어그램 라벨 "AuraIII")
    model_field: GEN3
    connection: COM7
    lines_nm_approx: [405, 440, 488, 561, 640]   # 다이어그램 아이콘 판독 — fwhm 미확인
    registry: AuraIII         # data/light_sources.yaml
    verified_product_name: true
    verified_date: 2026-08-10
    source: nis_elements_device_manager

lasers:            # 2026-08-10 NIS-Elements Device Manager로 확인 — MM .cfg에는 등록되어 있지 않음
  - device: LUN-F-XL
    vendor: Nikon
    kind: laser_combiner
    lines_nm: [405, 488, 561, 640]
    feeds: CSUW1-Hub
    registry: LUN-F-XL        # data/light_sources.yaml
    note: >
      Di01-T405/488/568/647 다이크로익(confocal_scanner > sub_devices >
      CSUW1-Dichroic)의 반사대역과 라인이 정확히 일치 — CSU-W1 컨포칼 경로의
      실제 여기 레이저원임이 강하게 뒷받침됨. SpectraIII/AuraIII는 LED
      광원이고 이것만 레이저다.
    verified: true
    verified_date: 2026-08-10
    source: nis_elements_device_manager

# ─────────────────────────────────────────────────────────────────────────
# 광원별 광경로 — 2026-08-10 사용자 구술로 확보. 위에 이미 등록된 장치들을
# 순서대로 참조만 한다 (장치 자체의 스펙은 여기서 반복하지 않음, docs/08 §6).
# ─────────────────────────────────────────────────────────────────────────
light_paths:
  - name: confocal-laser
    source: LUN-F-XL
    order:
      - {stage: source, device: LUN-F-XL, lines_nm: [405, 488, 561, 640]}
      - {stage: dichroic, device: CSUW1-Dichroic, registry: "Di01-T405/488/568/647-13x15x0.5",
         note: "여기·방출이 같은 소자를 왕복 — 라인에서는 반사, 방출 대역에서는 투과 (사용자 확인). 2026-08-11: 과거 'DM'(외부)/'CSUW1-Dichroic'(내부)을 별개 소자 두 개로 기록했던 것은 오류 — 동일한 하나의 소자로 정정."}
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: dichroic, device: CSUW1-Dichroic, registry: "Di01-T405/488/568/647-13x15x0.5", note: "돌아오는 방출, 위와 동일 소자"}
      - {stage: splitter, device: Splitter, registry: "DM A561LP", side_by_camera: {Kinetix_red: transmit, Kinetix_blue: reflect}}
      - stage: emission_filter
        note: >
          EM1/EM2가 Splitter와 카메라 사이, 카메라 바로 앞에 하나씩(arm당
          하나) 있다. 2026-08-11 확인: EM1 = Kinetix_red 전담, EM2 =
          Kinetix_blue 전담. EM2 필터 구성도 EM1과 동일함이 독립 확인됨.
        by_camera:
          Kinetix_red: {device: EM1}
          Kinetix_blue: {device: EM2}
      - {stage: camera, device: [Kinetix_red, Kinetix_blue]}

  - name: widefield-spectra3
    source: LightEngine # registry: SpectraIII
    order:
      - {stage: source, device: LightEngine, lines_nm_approx: [365, 440, 488, 514, 561, 594, 640]}
      - stage: dmd
        device: MightexPolygon1000
        note: >
          2026-08-10 사용자 확인: 전 파장대에서 조명 강도와 패턴(형태)을
          제어하는 pattern illuminator다. 파장선택 기능은 없음 — 계산상
          스펙트럼 중립(투과율 손실만 있을 수 있음, 값 미확인)으로 취급.
          3자 대조(물리적 연결 여부)는 여전히 미완료 (위 dmd: 절).
      - stage: branch
        device: LappMainBranch1
        note: >
          2026-08-10 사용자 확인 (해소): 기하 비대칭 — SpectraIII는 주광축
          인라인, Aura는 옆에서 결합. mirror_out: SpectraIII 100% 통과,
          Aura는 결합 안 됨(0%). mirror_in: 50/50 플레이트라 양쪽 다 50%.
          자세한 설명은 위 lapp_branch: 절 참고.
      - {stage: excitation_filter, device: FilterTurret1, registry: "MXR00724-EX"}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM"}
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM", note: "돌아오는 방출, 위와 동일 소자"}
      - {stage: emission_filter, device: FilterTurret1, registry: "MXR00724-EM"}
      - stage: internal_dichroic
        device: CSUW1-Dichroic
        registry: "Di01-T405/488/568/647-13x15x0.5"
        note: >
          2026-08-10 사용자 확인 (해소): CSUW1-Bright 상태와 무관하게
          다이크로익은 항상 "on"이다 — Bright Field라고 해서 이 소자가
          빠지지 않는다. 대신 EM1/EM2를 quad-band(position 0, "multi"에
          해당) 또는 Open(position 10, "empty"에 해당)으로 놓고 쓴다
          (2026-08-11 정정: 이전에 "CSUW1-Filter_Red/Blue"라는 별개 내부
          필터휠로 기록했던 것이 실은 EM1/EM2였음— 아래 confocal_scanner
          참고). 즉 이 경로는 **진짜 백색광 촬영이 아니다** — 다이크로익
          (4색 노치)과 필터휠 상태에 따라 스펙트럼이 제한된 상태로
          촬영된다. 2026-08-11: band 값 확인됨 (위 confocal-laser 항목 참고).
      - {stage: splitter, device: Splitter, registry: "DM A561LP", side_by_camera: {Kinetix_red: transmit, Kinetix_blue: reflect}}
      - {stage: emission_filter, note: "EM1/EM2, 카메라당 하나씩 — 위 confocal-laser 항목과 동일, 상세는 그쪽 참고"}
      - {stage: camera, device: [Kinetix_red, Kinetix_blue]}
    note: "와이드필드(LED-epi) 조명도 CSU-W1 내부 광학계를 그대로 통과한다 — 다이크로익은 항상 on (2026-08-10 확인)."

  - name: widefield-aura
    source: Aura # registry: AuraIII
    order:
      - {stage: source, device: Aura, lines_nm_approx: [405, 440, 488, 561, 640]}
      - stage: branch
        device: LappMainBranch1
        note: "위 widefield-spectra3와 동일 — 자세한 설명은 lapp_branch: 절 참고. mirror_in(50/50) 상태여야 Aura가 샘플에 도달한다."
      - {stage: excitation_filter, device: FilterTurret1, registry: "MXR00724-EX"}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM"}
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM"}
      - {stage: emission_filter, device: FilterTurret1, registry: "MXR00724-EM"}
      - {stage: internal_dichroic, device: CSUW1-Dichroic, note: "위 widefield-spectra3와 동일 — 항상 on, 진짜 백색광 촬영 아님"}
      - {stage: splitter, device: Splitter, registry: "DM A561LP", side_by_camera: {Kinetix_red: transmit, Kinetix_blue: reflect}}
      - {stage: emission_filter, note: "EM1/EM2, 카메라당 하나씩 — 위 confocal-laser 항목 참고"}
      - {stage: camera, device: [Kinetix_red, Kinetix_blue]}

  - name: transmitted-light
    source: DiaLamp
    order:
      - {stage: source, device: DiaLamp, note: "백색광"}
      - {stage: polarizer, device: null, registry: "Polarizer-Linear",
         note: "각도조절 가능, 제거가능. MM/NIS 미등록 장치일 수 있음 — 각도 자체는 장부 밖 설정."}
      - stage: condenser
        device: CondenserTurret
        positions: {0: "1-ND", 1: "2-Shutter", 2: "3-", 3: "4-", 4: "5-", 5: "6-", 6: "7-"}
        verified: true
        verified_date: 2026-08-11
        source: mm_config
        note: >
          ⚠ 신규 발견 (2026-08-10) — 다크필드/브라이트필드 전환 콘덴서.
          **2026-08-11 해소**: MM .cfg(DMD_dualcam.cfg) 실측 확인 — 별도
          장치 `CondenserTurret`(어댑터 NikonTi2, Ti2-E__0 하위)로 실제
          등록되어 있다. "DiaLamp 장치 밑 속성일 것"이라던 이전 추정은
          틀렸음. Position 0/1만 라벨 있음(ND/Shutter) — 2-6번 라벨은 MM
          .cfg에 이름이 없어(순수 "3-"~"7-") 실제 정체(다크필드 링 등)는
          여전히 미확인.
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: filter_cube, device: FilterTurret1, note: "제거가능 — 형광 큐브가 투과광 경로에 그대로 남아있을 수 있음"}
      - {stage: analyzer, device: null, registry: "Analyzer-Linear",
         note: "각도조절 불가능(고정), 제거가능"}
      - {stage: internal_dichroic, device: CSUW1-Dichroic, note: "위 widefield 항목들과 동일 — 항상 on, 필터휠 empty/multi. 이 경로도 진짜 백색광 촬영이 아니다."}
      - {stage: splitter, device: Splitter, registry: "DM A561LP"}
      - {stage: emission_filter, note: "EM1/EM2, 카메라당 하나씩 — 위 confocal-laser 항목 참고"}
      - {stage: camera, device: [Kinetix_red, Kinetix_blue]}
    note: >
      편광자/검광자는 액정 편광 관찰용 (data/filters.yaml 항목 note와 일치).
      형광 실험에서는 이 경로 자체가 쓰이지 않으므로 편광자/검광자가 경로에
      남아있다면 순손실 — docs/01 §6에서 이미 지적된 ablation 후보.

  - name: optical-tweezers
    source: Trap
    order:
      - {stage: source, device: Trap, registry: "Trap#IR1064", note: "1064 nm, MM 미등록 — 장부 밖(off-ledger)"}
      - stage: dichroic
        device: FilterTurret2
        registry: "OT-Dichroic-750LP"
        note: >
          2026-08-10 사용자 확인: FilterTurret2는 이전에 "6개 슬롯 전부
          비어 있음"으로 기록했으나(위 filter_turrets 절 참고), 실제로는
          NIR(1064nm) 전용 다이크로익이 있다.
          **2026-08-11 정정**: "여기·방출 필터는 없다"는 틀렸음 — 750/SP
          방출 필터도 함께 있다(위 filter_turrets > FilterTurret2 참고).
          다이크로익은 750 nm보다 긴 파장만 반사(1064 nm을 대물렌즈로 보냄).
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: emission_filter, device: FilterTurret2, registry: "OT-EM-750SP",
         note: "750/SP — 750 nm 이상(산란된 1064 nm 트랩광) 차단. 2026-08-11 신규 확인."}
    note: >
      2026-08-10 사용자 확인: 샘플 이후 경로는 전부 차단되어(전 구간
      가시광~근적외 대역용 필터/다이크로익이 1064nm를 통과시키지 않음)
      검출 경로 쪽은 광집게 광경로 정리에서 고려할 필요가 없다고 봄 —
      다만 docs/04 §3의 "1100nm까지 격자를 잡아둔 이유"(누설 확인)는 여전히
      유효한 별개 우려사항이며, 이 결론과 모순되지 않음(그 확인 자체가
      바로 "정말 다 차단되는가"를 검증하는 것).

  - name: known_gaps
    note: >
      2026-08-11 갱신 (3차) — 해소된 것과 남은 것.

      **해소됨:**
      - CSUW1-Bright 상태와 무관하게 CSUW1-Dichroic는 항상 "on". 와이드필드/
        투과광 촬영도 이 다이크로익을 그대로 지난다 — 즉 이 랩엔 "진짜
        백색광" 촬영 경로가 없다.
      - LappMainBranch1: SpectraIII(인라인)/Aura(측면결합) 기하 비대칭 확인.
        mirror_out → SpectraIII 100%, Aura 0%. mirror_in → 둘 다 50%.
        2026-08-11: **용도**까지 확인 — DMD+와이드필드 동시 사용을 위해
        mirror_in을 쓰고, Aura 50% 손실은 와이드필드에는 강한 광량이
        필요 없어 감수할 만하다는 사용자 판단.
      - FilterTurret2에 NIR 전용 다이크로익 존재 확인 (여기·방출 필터 없음).
        2026-08-11: 슬롯·구성까지 확인(slot 1, 다이크로익[750nm 초과 반사]
        + 750/SP 방출필터 2부품). vendor/part number는 edge 값만으로 계산에
        충분하다는 사용자 판단 — 확보되면 갱신, 그전까지 재확인 요청 안 함.
      - DMD는 전 파장대 조명강도·패턴 제어용 pattern illuminator, 파장선택
        없음. 2026-08-11: 물리적 연결 여부 확인(docs/02 §4 참고). **같은 날
        MM .cfg(DMD_dualcam.cfg) 실측으로 MightexPolygon1000 장치 등록도
        확인** — pymmcore-plus로 제어 가능. 이 프로젝트는 NIS-Elements
        제어 경로를 쓰지 않기로 결정(2026-08-11, 사용자) — 아래 dmd: 절 참고.
      - 투과광 콘덴서 확인 (2026-08-11): "DiaLamp 밑 속성일 것"이라던 추정은
        틀렸음 — MM .cfg에 별도 장치 `CondenserTurret`(NikonTi2 어댑터,
        Ti2-E__0 하위)로 실제 등록되어 있다. 7-position, position 0="1-ND",
        1="2-Shutter", 2-6은 라벨 없음("3-"~"7-"). 아래 light_paths >
        transmitted-light > condenser 참고.
      - CSUW1-Dichroic의 정확한 band 값 확보 (2026-08-11, Di01-T405/488/
        568/647-13x15x0.5) — 이전에 별개 소자로 기록했던 optical_path_nis의
        'DM'과 동일한 물리 소자임도 함께 확인, 병합됨.
      - EM1/EM2 카메라 배정 확정 (2026-08-11): EM1 = Kinetix_red,
        EM2 = Kinetix_blue (카메라별 밝기 실측 대조).
      - EM2 필터 위치별 구성 독립 확인 (2026-08-11) — 더 이상 "EM1과 동일할
        것"이라는 진술 추정이 아니라 NIS-Elements 직접 대조로 확정.
      - `CSUW1-Filter_Red`/`CSUW1-Filter_Blue`(CSU-W1 내부 필터휠, EM1/EM2와
        별개로 기록했던 것)는 EM1/EM2와 동일한 물리 소자였음 확인 (2026-08-11)
        — 물리 필터휠은 red/blue 담당 각 1개, 총 2개뿐. 컨포컬/와이드필드
        모드와 무관하게 항상 그 자리에 있다(사용자 확인). confocal_scanner
        sub_devices의 중복 항목 제거, optical_path_nis > EM1/EM2로 병합.
      - EM1/EM2 필터 실제 내용 정정 (2026-08-11): 위 병합 과정에서 DMD_
        dualcam.cfg의 CSUW1-Filter_Red Label을 직접 읽어보니, 처음에 EM1/
        EM2 필터로 기록했던 "88000v2-quad/455/50/525/36/605/52/705/72"는
        실제 값이 아니었다(다른 소자 데이터의 오귀속 — data/filters.yaml
        해당 항목에 정정 주석 남김). 진짜 값은 multi/405/488/555/647
        (position 0-4) + Blocked(5-8) + Open(9). fwhm·실제 통과대역 데이터가
        없어 registry: null로 남기고, config/scopes/current-laser.yaml의
        emission_filters 후보에서도 뺐다 — 계산 후보는 지금 "EM-Open"
        하나뿐이다. 5개 필터의 실제 스펙 확보가 새로운 남은 일.

      **아직 남은 것:**
      (1) EM1/EM2 position 0-4(multi/405/488/555/647)의 실제 fwhm·통과대역
          스펙 — 확보 전까지 emission_filters 계산 후보는 "EM-Open" 하나뿐.
      이 절이 추적하던 나머지 광경로 항목은 2026-08-11 기준 해소됐다.
      (남은 실측은 이 절의 범위 밖: 조명 광량 파워미터 실측 등 로드맵
      Phase 0의 다른 항목 — [07 로드맵](../../docs/07-roadmap.md) 참고.)

dmd:
  device: MightexPolygon1000
  vendor: Mightex
  model: Polygon1000
  mm_device: MightexPolygon1000   # DMD_dualcam.cfg: "Device,MightexPolygon1000,MightexPolygon1000,MightexPolygon1000"
  control: pymmcore-plus   # 2026-08-11 프로젝트 결정: NIS-Elements 경로 안 씀, MM 등록 장치는 전부 pymmcore-plus로
  verified: true
  verified_date: 2026-08-11
  source: mm_config
  note: >
    **2026-08-11**: 물리적으로 연결되어 있음을 확인 (docs/02 §4 DMD 행,
    "물리적 존재" 해소). MM .cfg(DMD_dualcam.cfg) 실측으로 MightexPolygon1000
    장치 등록도 확인 — pymmcore-plus로 제어 가능. **프로젝트 결정
    (2026-08-11, 사용자)**: 이 프로젝트는 NIS-Elements 제어 경로를 쓰지
    않는다 — DMD를 포함해 앞으로의 자동화(로드맵 Phase 5)는 MM에 등록된
    장치라면 pymmcore-plus로만 제어한다.
    3자 대조는 아직 완전히 끝나지 않았다.
    기능은 2026-08-10 사용자 확인: 전 파장대에서 조명 강도·패턴(형태)을
    제어하는 pattern illuminator — 파장선택 기능 없음. light_paths >
    widefield-spectra3 참고.

confocal_scanner:
  device: CSUW1-Hub
  vendor: Yokogawa
  model: CSU-W1
  connection: COM10
  sub_devices:
    # 2026-08-11 정정: 여기 있던 CSUW1-Filter_Red(wheel 1)/CSUW1-Filter_Blue
    # (wheel 2)는 실제로는 optical_path_nis의 EM1/EM2와 동일한 물리 필터휠
    # 이었다 (사용자 확인: "I have two physical filter wheels. one is only
    # for the camera-red, the other(EM2) is only for the camera-blue" — CSU-W1
    # 내부의 별개 소자가 아니었음). 여기 있던 위치값(multi/405/488/555/647/
    # b1-b4/open)은 실측 검증 없이 기록된 것이었고, EM1/EM2 쪽 값(실측·
    # verified: true)이 맞다. 중복 제거, optical_path_nis > EM1/EM2 참고.
    - device: CSUW1-Dichroic
      positions:
        0: {label: "Di01-T405/488/568/647-13x15x0.5", mirror_nm: [[404,406],[487,489],[561,568],[633,647]], registry: "Di01-T405/488/568/647-13x15x0.5"}
        1: b1
        2: b2
      current_position: 0 # on
      verified: true
      verified_date: 2026-08-11
      source: nis_elements_device_manager
      note: >
        2026-08-10 사용자 확인: 현재 "on". 컨포컬 레이저 4색(405/488/561/640)
        분리용 multiband. b1/b2는 빈 카트리지 자리.
        **2026-08-11**: band 값 확보 (Di01-T405/488/568/647-13x15x0.5,
        NIS-Elements Mirror 표시값 404-406/487-489/561-568/633-647 nm).
        이전에 별개 소자로 기록했던 optical_path_nis의 'DM'과 동일한 물리
        소자임도 함께 확인됨 (2026-08-10 구술 오류 정정) — 그 항목은 여기로
        병합. light_paths > confocal-laser 참고.
    - {device: CSUW1-Bright, positions: {0: Confocal, 1: "Bright Field"}}
    - {device: CSUW1-Port, positions: {0: blue_only, 1: blue_red, 2: red_only}}
    - {device: CSUW1-Shutter}

light_path:               # LightPath device — 접안/좌우 포트 선택
  device: LightPath
  positions: {0: EYE, 1: R100, 2: AUX, 3: L100}

intermediate_magnification:
  device: IntermediateMagnification
  values: [1.0, 1.5]        # 배율 보정계수 표(Sheet1)의 열 헤더와 일치

lapp_branch:
  device: LappMainBranch1
  positions: {0: mirror_in, 1: mirror_out}
  current_position: 0 # mirror_in — 사용자 확인 시점 상태로 추정, 상시 고정인지는 미확인
  note: >
    2026-08-10 사용자 확인 (완전히 해소됨). 두 광원이 기하적으로 비대칭이다:
    SpectraIII는 주 광축에 인라인으로 들어오고, Aura는 옆에서 들어와 이
    미러로 주 광축에 결합된다.
      - mirror_out (미러 없음, 빈 자리와 동일): SpectraIII 인라인 빔은
        방해물이 없어 100% 그대로 샘플로 간다. Aura는 결합해줄 것이 없어
        샘플에 전혀 도달하지 못한다.
      - mirror_in (50/50 플레이트 삽입): 어느 쪽에서 들어오든 50%는
        투과, 50%는 반사 — 그 결과 SpectraIII 인라인 빔의 50%가 계속
        진행하고, 동시에 Aura 빔의 50%가 반사되어 같은 주 광축에 합류한다.
    출처: 사용자 구술 (kb/systems/current.md 편집 시점 대화).

    **2026-08-11 용도 확인**: mirror_in을 쓰는 이유는 DMD 패턴 조명과
    와이드필드(Aura)를 동시에 쓰고 싶을 때다 — Aura 광량이 50% 손실되지만,
    와이드필드 이미징은 보통 강한 광량이 필요 없어서 그 손실을 감수할 만
    하다는 사용자 판단. mirror_out은 그 조합이 필요 없을 때(Aura 안 씀,
    SpectraIII 인라인 100% 유지).
  verified: true
  verified_date: 2026-08-10
  source: user_dictation

pixel_size_calibration:
  source_file: "Confocal_microscope_conversion_factor(Apr 2025).xlsx"
  sheet: Sheet1
  date: 2025-04
  camera: Kinetix
  unit: um/px
  table:
    "4x":   {"1x": 1.625,   "1.5x": 1.0833}
    "10x":  {"1x": 0.65,    "1.5x": 0.43333}
    "20x":  {"1x": 0.32373, "1.5x": 0.21582}
    "40x":  {"1x": 0.1625,  "1.5x": 0.10833}
    "60x":  {"1x": 0.10833, "1.5x": 0.07222}
    "100x": {"1x": 0.065,   "1.5x": 0.04333}

devices_not_in_mm_config:   # docs/02 §4 "3자 대조표" — MM .cfg에 없는 별도 제어 장치
  - {name: "피에조 스테이지 (Prior/Queensgate NPC-D, Nanobench 6000)", control: "별도 Python (hardware/piezo_stage.py)", mm_registered: false, python_control: confirmed, confirmed_date: 2026-08-10}
  - {name: "광집게 (Aresis Tweez 305/310, Tweez 300)", control: "별도 Python (hardware/optical_tweezers.py, TCP 2070)", mm_registered: false, python_control: confirmed, confirmed_date: 2026-08-10}
  - name: "LUN-F-XL 레이저 콤바이너 (405/488/561/640)"
    control: "없음 — 아직 어떤 프로그래밍 인터페이스에도 연결 안 됨"
    mm_registered: false
    python_control: not_connected
    confirmed_date: 2026-08-12
    note: >
      2026-08-10 사용자 구술로는 "Python 제어 가능 확인"이었으나 어떤
      인터페이스였는지 기록이 없었음. 2026-08-12 grep/pymmcore-plus 실제
      로드로 MM 미등록은 확정했으나, 그때는 "숨은 경로가 어딘가 있을
      것"이라고 잘못 가정했음. **2026-08-12 사용자 정정**: 아직 연결
      자체를 안 했다 — 즉 찾아야 할 기존 경로가 있는 게 아니라, 앞으로
      연결 작업(Nikon SDK 설치, 시리얼/USB 결선 등) 자체를 새로 해야
      하는 상태다. 이 프로젝트는 NIS-Elements 경로를 안 쓰기로 했으므로
      ([[project-pymmcore-only-no-nis]]) 그 연결이 이뤄지면 pymmcore-plus로
      닿을 수 있는지부터 다시 확인 필요 — 착수 전.
  - name: "CSUW1-Dichroic / EM1(CSUW1-Filter_Red) / EM2(CSUW1-Filter_Blue) 필터 요소 (컨포칼 경로)"
    control: pymmcore-plus
    mm_registered: true
    python_control: confirmed
    confirmed_date: 2026-08-12
    note: >
      **2026-08-12 해소**: DMD_dualcam.cfg(사본, MightexPolygon1000만 제거)를
      pymmcore-plus로 실제 로드해 세 장치 모두 라이브로 값 읽음 —
      CSUW1-Dichroic state 0/"on", CSUW1-Filter_Red(EM1) state 0/"multi",
      CSUW1-Filter_Blue(EM2) state 0/"multi" — 전부 이 문서의 기존 기록과
      일치. "NIS-Elements 전용"이라던 이전 가정은 틀렸음 — 애초에 MM
      `.cfg`의 `Device,CSUW1-Dichroic,...`/`Device,CSUW1-Filter_Red,...`/
      `Device,CSUW1-Filter_Blue,...` 줄로 정식 등록되어 있었다(위
      confocal_scanner, optical_path_nis > EM1/EM2 참고) — NIS-Elements는
      그저 이 장치들을 *관찰*하는 데 쓴 도구였을 뿐, 유일한 제어 경로는
      아니었다.
  - name: "Splitter (듀얼 카메라 이미지 스플리터, DM A561LP)"
    control: "없음 — 아직 어떤 프로그래밍 인터페이스에도 연결 안 됨"
    mm_registered: false
    python_control: not_connected
    confirmed_date: 2026-08-12
    note: >
      위 CSUW1 그룹과 같이 재확인하다가 갈라짐: **Splitter는 이 폴더의
      .cfg 9개 어디에도 `Device,` 줄이 없고, pymmcore-plus 실제 로드
      결과(getLoadedDevices())에도 없다** — CSUW1-Dichroic/EM1/EM2와
      달리 MM 미등록이 확정. **2026-08-12 사용자 정정**: LUN-F-XL과
      마찬가지로 "찾아야 할 숨은 경로"가 아니라 **아직 연결을 안 한
      상태** — optical_path_nis > Splitter 항목은 NIS-Elements Device
      Manager로 관찰만 한 것이고, 프로그래밍 제어는 아예 시도된 적이
      없다. 현재는 수동 조작만 가능한 상태로 보고, 연결 작업이 이뤄지면
      pymmcore-plus 경로 여부를 다시 확인.

# 2026-08-10 사용자 구술: 위 두 항목뿐 아니라 현미경 스탠드(Ti2-E)·컨포칼
# (CSU-W1)·DMD(Polygon1000)까지 포함해 이 dossier에 등장하는 모든 장비를
# Python으로 제어할 수 있음을 확인했다고 함. 스탠드/컨포칼/DMD는 이미 MM
# .cfg 등록 장치라 pymmcore-plus 경로로 통할 가능성이 높다고 봤음.
#
# 2026-08-11 확정 (마이크로스코프 PC 실제 접속): DMD는 MM .cfg에 실제
# 등록되어 있음을 grep으로 직접 확인(위 dmd: 절 참고). 그리고 **프로젝트
# 결정**: 이 프로젝트는 NIS-Elements 제어 경로를 쓰지 않는다 — 위
# LUN-F-XL/CSUW1-Dichroic 등 NIS-Elements 전용으로 남아있던 항목들도
# "재확인 예정"이 아니라 이제 이 결정에 따라 판단할 것. MM 미등록 장치
# (레이저 콤바이너, 컨포칼 내부 필터 요소 등)는 여전히 pymmcore-plus로
# 닿지 않으므로 그 경로를 어떻게 확보할지는 별개 문제로 남는다.
#
# 2026-08-12 재확인 (마이크로스코프 PC, pymmcore-plus 실제 로드로 검증):
# 위 devices_not_in_mm_config 세 항목이 CSUW1-Dichroic/EM1/EM2(해소,
# pymmcore-plus 확인) vs LUN-F-XL/Splitter(미해결, MM 미등록 확정)로
# 갈렸다 — 각 항목 note 참고. 부수적으로 환경 이슈 하나 발견·해소:
# `mmcore install`로 받은 pymmcore-plus 자체 MM 빌드(interface v75)는
# `Ti2_Mic_Driver.dll`(Nikon 벤더 SDK)이 빠져 있어 NikonTi2 어댑터가
# 아예 로드되지 않았음 — 랩 기존 설치(`C:\Program Files\Micro-Manager-2.0`)
# 에서 그 DLL만 복사해 해소(재현 가능, 어댑터 DLL 자체는 안 건드림).
# 이 복사가 없으면 스탠드·CSU-W1을 포함한 모든 NikonTi2 하위 장치가
# pymmcore-plus에서 로드 실패한다 — Phase 5a(상태 읽기) 착수 전 다시
# 필요할 수 있는 조치.
---

## 확보 경위

이 dossier는 사용자가 제공한 두 파일에서 그대로 추출한 것이다:

1. `DMD_dualcam.cfg` — Micro-Manager 설정 파일 (Configurator가 2026-07-03 15:32 PDT 생성).
   README에서 "최우선 · 미확보"로 표시했던 **현재 시스템 MM `.cfg`**가 이것이다.
2. `Confocal_microscope_conversion_factor(Apr 2025).xlsx` — Kinetix 카메라 기준
   배율별(4x~100x) × 중간배율(1x/1.5x) 유효 픽셀 크기 실측표. 로드맵 Phase 0의
   "픽셀 크기 실측 교정" 항목이 이걸로 채워진다.
3. **NIS-Elements Device Manager 실측 (2026-08-10)** — 사용자가 NIS-Elements를 켜고
   Device Manager > Hardware Configurations 및 각 필터 요소의 Filter Block
   Settings 대화상자를 직접 캡처해 전달. MM .cfg에서 라벨만 있고 내용을 몰랐던
   `FilterTurret1` 위치 0(MXR00724)의 실제 통과대역을 확인했고, MM .cfg에
   아예 등록되지 않은 컨포칼 경로 필터 요소(DM/Splitter/EM1)와 레이저
   콤바이너(LUN-F-XL)를 새로 발견했다. `optical_path_nis`, `lasers`,
   `light_sources`(LightEngine/Aura 제품명) 항목이 이 소스에서 나왔다.
4. **Nikon Objective Selector 카탈로그 대조 (2026-08-10)** — `.cfg`의 6개 대물렌즈
   라벨 문자열을 니콘 공식 제품 비교 페이지(파트넘버 기준)와 대조해 NA·WD·커버글라스·
   침액·파트넘버를 확정했다. `objectives` 항목 전체가 이 소스에서 나왔다.

## 시리얼/모델 번호 — 확보된 것과 안 된 것

`.cfg` 파일 자체는 대부분 장치 이름과 어댑터만 기록하고 시리얼은 남기지 않는다.
이번 추출에서 실제로 찾은 코드성 문자열은 **`MXR00724`** 하나뿐이다
(`FilterTurret1` 0번 슬롯 라벨 `"1-MXR00724 -Empty"`). Nikon 필터 큐브 카탈로그
번호로 보이지만 그 슬롯 자체는 `Empty`로 기록되어 있어 실물이 있는지도 불확실하다.

카메라(Kinetix ×2), DMD(Polygon1000), 컨포칼(CSU-W1), 광원(Lumencor ×2)은 전부
**모델명만 확인되고 시리얼은 `.cfg`에 없다** — 실제 장비 라벨을 보거나 해당 소프트웨어의
"장치 정보/About" 화면에서 읽어야 한다. 이전 세션에서 피에조 스테이지는 이미 라이브
쿼리로 시리얼을 확보할 수 있는 명령(`identity.hardware.serial.get` 등)을 확인해뒀다
([hardware/piezo_stage.py](../../hardware/piezo_stage.py)) — 필요하면 실행해서 채울 수 있다.

## 확인이 필요한 항목 (verified: false로 표시된 것들)

- ~~대물렌즈 라벨의 마지막 숫자가 NA인지 WD(mm)인지~~ → **2026-08-10 해소.**
  니콘 공식 카탈로그(Objective Selector, 파트넘버 대조)로 6개 전부 확인 — 끝자리는
  전부 **WD(mm)**다. 20x(`LmbdD0.8`)만 NA(0.80)와 WD(0.8mm)가 우연히 같은 값이라
  혼란의 원인이었다. **2026-08-11 완전 해소**: 물리 경통 각인 대조(렌즈가
  실제로 그 라벨과 같은 물건인지, 교체·오표기 여부)도 사용자가 직접 확인
  완료 — 로드맵 Phase 0의 이 항목은 끝.
- ~~`LightEngine`/`Aura` 두 Lumencor 장치의 정확한 제품명~~ → **2026-08-10 해소.**
  NIS-Elements Device Manager에서 `LightEngine`=SpectraIII, `Aura`=AuraIII로 확인.
  단, 두 장치의 라인별 중심파장은 다이어그램 아이콘 판독값(근사)이라 fwhm과
  실제 카탈로그 스펙 대조는 아직 안 됨.
- ~~`MightexPolygon1000`(DMD)의 실제 물리적 연결 여부~~ → **2026-08-11 해소.**
  물리적으로 연결되어 있음을 사용자가 확인 — [02 §4](../../docs/02-knowledge-base.md)
  3자 대조표의 "DMD: 물리적 존재" 칸도 함께 갱신. MM/NIS 등록 여부·제어
  주체는 여전히 미확인 (위 `dmd:` 절 참고).
- ~~`LappMainBranch1`의 용도~~ → **2026-08-10 동작 해소, 2026-08-11 용도 추가.**
  mirror_in/out의 물리적 동작은 2026-08-10에 확인됐고, 2026-08-11에 **왜**
  mirror_in을 쓰는지(DMD+와이드필드 동시 사용, Aura 50% 손실을 감수할 만한
  이유)까지 확인됨 — 위 `lapp_branch` 절 참고.
- ~~두 카메라(Kinetix_blue/red)와 CSU-W1, DMD, 두 광원 전부 시리얼 번호 미확보~~
  → **2026-08-11: 사용자 판단으로 불필요 — 더 이상 확인 대상 아님.**

## 관련 문서

- [02 지식베이스 §3 시스템 dossier](../../docs/02-knowledge-base.md) — 이 파일이 따르는 스키마
- [02 §4 3자 대조표](../../docs/02-knowledge-base.md) — MM/NIS/실물 대조가 왜 필요한지
- [07 로드맵 Phase 0](../../docs/07-roadmap.md) — 이 dossier가 채우는 항목들
