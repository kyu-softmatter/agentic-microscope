---
id: current
status: current
fingerprint: null  # TODO: hash of device label set + camera serials. Left empty until the automatic indexer is wired up.
sources:
  - {kind: mm_config, path: "C:\\Users\\Takatori lab\\Desktop\\Maintanance\\micromanager\\DMD_dualcam.cfg", date: 2026-07-03}
  - {kind: calibration, path: "C:\\Users\\Takatori lab\\Desktop\\Confocal_microscope_conversion_factor(Apr 2025).xlsx", date: 2025-04}
  - {kind: nis_elements_device_manager, path: "live GUI — Device Manager (Nikon Ti2 hardware setup) + Filter Block Settings dialogs (Turret1/DM/Splitter/EM1)", date: 2026-08-10}
  - {kind: nikon_catalog, path: "https://www.microscope.healthcare.nikon.com/products/optics/selector/comparison/ [-179794, -179798, -179802, -1923, -179808, -179810]", date: 2026-08-10}
  - {kind: purchase_quote, path: "reference/quotes/2024-09-29_nikon-quote-REDACTED_ti2e-csuw1_takatori.md", date: 2024-09-29, note: "Nikon quote #REDACTED (Takatori lab). The 6 objectives, 4 EM1 filters, FilterTurret1 pos0 cube (MXR00724), and the CSU-W1 body all match down to the part number — this can be promoted to the purchase-record source for those fields. Camera configuration does not match (quote: Kinetix22+Prime95B, current: Kinetix ×2) — either changed at final order or swapped later, unconfirmed. See that md file for the detailed cross-check."}
  - {kind: nis_elements_device_manager, path: "live GUI — Filter Block Settings (DM) re-check + calibration.cli camera-probe measured cross-check", date: 2026-08-11, note: "DM=CSUW1-Dichroic confirmed as the same physical element, EM1=Kinetix_red/EM2=Kinetix_blue camera assignment settled, EM2 filter configuration independently confirmed."}
  - {kind: calibration, path: kb/calibrations/disk-bandwidth.yaml, date: 2026-08-12, note: "D: drive sustained-write bandwidth measured at 206.8 MB/s (calibration.cli disk-bandwidth, 4GB). G12 budget = 0.7×206.8 = 144.8 MB/s. Whether this is exactly the folder MM actually saves to is unconfirmed — if it is a different folder, re-measure."}
  - {kind: calibration, path: kb/calibrations/camera-readout.yaml, date: 2026-08-12, note: "PVCAM adapter, measured (calibration.cli camera-readout, dual_cam_test.cfg). Timing-ReadoutTimeNs=8,475,000 → row time ≈3531.2 ns/row (ROI 2400 rows). Units assumed from the property name; no document cross-check yet."}
  - {kind: pymmcore_plus_live, path: "copy of DMD_dualcam.cfg (only the MightexPolygon1000 line removed) — actually loaded via pymmcore-plus", date: 2026-08-12, note: "Ti2-E__0/CSUW1-Hub/CSUW1-Dichroic/CSUW1-Filter_Red(EM1)/CSUW1-Filter_Blue(EM2)/Kinetix_red/Kinetix_blue/LightEngine/Aura — every device except the DMD loaded successfully, and the measured values CSUW1-Dichroic state 0 (on) / EM1,EM2 state 0 (multi) match the kb record. Loading the NikonTi2 adapter required Ti2_Mic_Driver.dll (copied from the lab's existing installation) — see the devices_not_in_mm_config note below."}

stand:
  vendor: Nikon
  model: Ti2-E
  mm_device: Ti2-E__0
  tube_lens_mm: 200          # Nikon Ti2 standard value. Not cross-checked against measurement/datasheet — verify
  autofocus: PFS
  verified: false

cameras:
  # 2026-08-19 user confirmation: both bodies are **Kinetix22** (2400x2400, 6.5 µm,
  # 15.6x15.6 mm, 22 mm diagonal), connected over **PCI-Express**. The MM device
  # labels read "Kinetix", which is what previously left the model unresolved; the
  # Nikon quote (2024-09-29 #REDACTED, part 77018310 "Kinetix 22") was right all
  # along, so the camera discrepancy flagged in reference/quotes/ is closed —
  # only the Prime95B→second-Kinetix22 substitution remains as a change from quote.
  # Independent corroboration: kb/calibrations/camera-readout.yaml's 8.475 ms over
  # 2400 rows is the Kinetix22 full-frame Sensitivity readout exactly (118 fps);
  # a 3200-row Kinetix would have read out in 11.30 ms.
  # Full specs (4 modes, full well 200/1000/1000/15000 e-, per-mode line times,
  # ROI×interface speed table, trigger modes): data/detectors.yaml > Kinetix22.
  - device: Kinetix_red
    role: Core.Camera (default active camera)
    vendor: Photometrics
    model: Kinetix22
    registry: Kinetix22      # data/detectors.yaml key
    interface: PCIe          # PCI-Express Gen 3. 2026-08-19 user confirmation
    adapter: PVCAM
    mm_label: Camera-2
    serial: null             # no serial in the .cfg — needs further confirmation from PVCAM device properties or the physical label
    verified: true
    verified_date: 2026-08-19
  - device: Kinetix_blue
    vendor: Photometrics
    model: Kinetix22
    registry: Kinetix22
    interface: PCIe
    adapter: PVCAM
    mm_label: Camera-1
    serial: null
    verified: true
    verified_date: 2026-08-19

objectives:            # Nosepiece (6-position). 2026-08-10: the trailing number in the label is confirmed to be WD(mm) (cross-checked against Nikon catalog part numbers). 2026-08-11: physical barrel engraving cross-check also completed and confirmed by the user.
  - {turret: Nosepiece, position: 0, label: "1-Plan Apo LmbdD20 4x",         mag: 4,   product: "CFI Plan Apo Lambda D 4X",         part_number: MRD70040, na: 0.20, wd_mm: 20,        immersion: air,   cover_glass_mm: "0-0.17",  verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 1, label: "2-Plan Apo LmbdD4 10x",        mag: 10,  product: "CFI Plan Apo Lambda D 10X",        part_number: MRD70170, na: 0.45, wd_mm: 4,         immersion: air,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 2, label: "3-Plan Apo LmbdD0.8 20x",      mag: 20,  product: "CFI Plan Apo Lambda D 20X",        part_number: MRD70270, na: 0.80, wd_mm: 0.8,       immersion: air,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 3, label: "4-Apo LmbdS 40x WI",           mag: 40,  product: "CFI Apo Lambda S 40XC WI",         part_number: MRD77400, na: 1.25, wd_mm: "0.2-0.16 (correction collar dependent)", immersion: water, cover_glass_mm: "0.15-0.19", verified: true, verified_date: 2026-08-10, source: nikon_catalog}
  - {turret: Nosepiece, position: 4, label: "5-Plan Apo LmbdD0.15 60x Oil", mag: 60,  product: "CFI Plan Apo Lambda D 60X Oil",    part_number: MRD71670, na: 1.42, wd_mm: 0.15,      immersion: oil,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog, note: "pol: Simple POL, phase ring: EXT PH3"}
  - {turret: Nosepiece, position: 5, label: "6-Plan Apo LmbdD0.13 100x Oil",mag: 100, product: "CFI Plan Apo Lambda D 100X Oil",   part_number: MRD71970, na: 1.45, wd_mm: 0.13,      immersion: oil,   cover_glass_mm: 0.17,      verified: true, verified_date: 2026-08-10, source: nikon_catalog}

filter_turrets:
  - device: FilterTurret1     # NIS-Elements display name: "Turret1"
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
      Measured and confirmed 2026-08-10 in NIS-Elements Device Manager >
      Filter Block Settings - Turret1. The old MM .cfg label
      "1-MXR00724 -Empty" was misleading — position 0 actually holds a
      physical 5-band cube, and "Empty" was a display-format artifact.
      This resolves the "DA/FI/TR10Empty" entry in data/filters.yaml
      (kind: unknown, the cube that 2,312 records of old metadata pointed at).
  - device: FilterTurret2
    positions:
      0:
        label: "OT dichroic + 750/SP emission filter"
        mirror_nm: [[750, null]]     # reflects only wavelengths longer than 750 nm (for the 1064 nm trap beam)
        emission_nm: [[null, 750]]   # 750/SP: passes only below 750 nm
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
      ⚠ 2026-08-10 correction: the "all six slots empty" above was written
      before NIS-Elements Device Manager had been checked. User dictation
      confirms Turret2 is in fact used in the optical tweezers (OT) path.
      **2026-08-11 update**: the earlier sentence "there are no excitation
      or emission filters" was wrong — there are actually two parts: a
      dichroic (reflects only wavelengths longer than 750 nm — sends the
      1064 nm trap beam toward the objective and transmits shorter visible
      light) and a 750/SP (shortpass) emission filter (blocks above 750 nm —
      prevents scattered 1064 nm from leaking into the eyepiece/camera).
      The user called it "slot 1" — recorded as position 0 following the
      1-indexed GUI label convention used elsewhere, but the indexing itself
      is assumed until re-checked. Exact vendor/part number is still
      unconfirmed — provisionally registered in data/filters.yaml as
      `OT-Dichroic-750LP`/`OT-EM-750SP`.
      See light_paths > optical-tweezers below.

optical_path_nis:      # confirmed 2026-08-10 via NIS-Elements Device Manager only — not present in the MM .cfg
  # 2026-08-11 correction: the 'DM' entry that used to be here (dichroic
  # beamsplitter, Di01-T405/488/568/647) is confirmed to be the same physical
  # element as confocal_scanner > sub_devices > CSUW1-Dichroic — the 2026-08-10
  # dictation claiming "a second element separate from the external DM" was wrong.
  # Duplicate record removed and merged into CSUW1-Dichroic. See that entry for
  # details and band values.
  - device: Splitter
    purpose: "dual-camera (C3PO/R2D2) image splitter"
    positions:
      0: {label: "100/0 mirror", note: "full reflection — single-camera mode"}
      1: {label: "DM A561LP", mirror_nm: [[561, null]], note: "561 nm longpass", registry: "DM A561LP"}
      2: Empty
    current_position: 1 # DM A561LP
    note: >
      Confirmed by user 2026-08-10: the current configuration uses both
      cameras (Kinetix_red/Kinetix_blue) simultaneously, and this splitter
      divides the emission between them at 561 nm (position 1, DM A561LP).
      Not single-camera mode (position 0).
      → optics.Channel currently has only one dichroic field, so it cannot
      yet express the two-stage wavelength split — main confocal dichroic
      (Di01-T) followed by this splitter. Building per-camera channels
      requires a way for Channel to express "which side of this element does
      the light go to, transmit or reflect". Architecture extension is being
      discussed in conversation.
    verified: true
    verified_date: 2026-08-10
  - device: EM1
    purpose: "emission filter wheel — dedicated to Kinetix_red (red-channel camera)"
    positions:
      0: {label: "multi", registry: null}
      1: {label: "405", registry: null}
      2: {label: "488", registry: null}
      3: {label: "555", registry: null}
      4: {label: "647", registry: null}
      5: Blocked   # physically blocked by a metal plate, no light passes at all — not selectable (confirmed 2026-08-11)
      6: Blocked
      7: Blocked
      8: Blocked
      9: {label: "Open", registry: "EM-Open", note: "empty slot — no filter, fully open for every light source (all wavelengths pass). Confirmed 2026-08-11. Matches .cfg Label 'open'."}
    verified: true
    verified_date: 2026-08-11
    source: mm_config
    note: >
      **2026-08-11 final correction**: the filter set originally recorded as
      "88000v2-Quad/455/50/525/36/605/52/705/72" was not EM1's actual filters
      (another element's data appears to have been attached here by mistake —
      exactly where it came from is unknown). Real positions 0-4 match the
      CSUW1-Filter_Red Label values in DMD_dualcam.cfg (multi/405/488/555/647)
      — the user confirms these are the true values. These 5 have only center
      wavelength numbers so far, with no fwhm or actual passband data, so they
      are left as registry: null (no guessing — link them once values exist in
      data/filters.yaml).
      Positions 5-8 are Blocked (metal plate; the .cfg Label wrongly carried
      "b1"~"b4" — these are not empty cartridge slots, they are physically
      blocked), and 9 is Open — an exact match to .cfg Label "open". Ten total
      (0-9), matching the actual slot count in the .cfg (final confirmation
      2026-08-11).
      Sits between the Splitter and the camera, immediately in front of the
      camera. EM1/EM2 each serve one camera.
      **Camera assignment settled**: EM1 = Kinetix_red (confirmed by measured
      per-camera brightness cross-check — clears the EM1/EM2 camera assignment
      blocker in roadmap Phase 0).
      **Correction**: the old sentence "separate from CSUW1-Filter_Red/Blue —
      those are internal CSU-W1 elements" was wrong. There are only two
      physical filter wheels, one for red and one for blue, and the
      CSUW1-Filter_Red that sat separately under confocal_scanner.sub_devices
      is this very EM1 (merged; see confocal_scanner below). It is always in
      this position regardless of confocal/widefield mode (user confirmed).
    camera: Kinetix_red
  - device: EM2
    purpose: "emission filter wheel — identical configuration to EM1, dedicated to Kinetix_blue (blue-channel camera)"
    positions:
      0: {label: "multi", registry: null}
      1: {label: "405", registry: null}
      2: {label: "488", registry: null}
      3: {label: "555", registry: null}
      4: {label: "647", registry: null}
      5: Blocked   # physically blocked by a metal plate, no light passes at all — not selectable (confirmed 2026-08-11)
      6: Blocked
      7: Blocked
      8: Blocked
      9: {label: "Open", registry: "EM-Open", note: "empty slot — no filter, fully open for every light source (all wavelengths pass). Confirmed 2026-08-11. Matches .cfg Label 'open'."}
    camera: Kinetix_blue
    verified: true
    verified_date: 2026-08-11
    source: mm_config
    note: >
      Confirmed by user 2026-08-10: "EM2 is configured identically to EM1" —
      so positions simply referenced the same filters as EM1 (by part spec).
      **2026-08-11 final correction**: for the same reason as EM1 above, the
      "88000v2-Quad/455/50/525/36/605/52/705/72" set was not the real value —
      corrected to multi/405/488/555/647 (position 0-4) + Blocked (5-8) +
      Open (9), ten total (0-9), matching the .cfg slot count. No fwhm or
      actual passband data, so registry: null (no guessing). That EM2 is
      identical to EM1 is confirmed by direct NIS-Elements cross-check
      (no longer an assumption from a statement).
      Camera assignment settled: EM2 = Kinetix_blue (cross-checked by
      measurement together with the EM1 determination — see the EM1 note
      above).
    verified: true
    verified_date: 2026-08-11

light_sources:
  - device: LightEngine
    vendor: Lumencor
    model: SpectraIII         # confirmed 2026-08-10 via NIS-Elements Device Manager (diagram label "SpectraIII")
    model_field: GEN3         # the MM adapter's communication-protocol generation designation
    connection: COM3
    lines_nm_approx: [365, 440, 488, 514, 561, 594, 640]   # read off the diagram icons — fwhm unconfirmed
    registry: SpectraIII      # data/light_sources.yaml
    verified_product_name: true
    verified_date: 2026-08-10
    source: nis_elements_device_manager
  - device: Aura
    vendor: Lumencor
    model: AuraIII            # confirmed 2026-08-10 via NIS-Elements Device Manager (diagram label "AuraIII")
    model_field: GEN3
    connection: COM7
    lines_nm_approx: [405, 440, 488, 561, 640]   # read off the diagram icons — fwhm unconfirmed
    registry: AuraIII         # data/light_sources.yaml
    verified_product_name: true
    verified_date: 2026-08-10
    source: nis_elements_device_manager

lasers:            # confirmed 2026-08-10 via NIS-Elements Device Manager — not registered in the MM .cfg
  - device: LUN-F-XL
    vendor: Nikon
    kind: laser_combiner
    lines_nm: [405, 488, 561, 640]
    feeds: CSUW1-Hub
    registry: LUN-F-XL        # data/light_sources.yaml
    note: >
      The lines match the reflection bands of the Di01-T405/488/568/647
      dichroic (confocal_scanner > sub_devices > CSUW1-Dichroic) exactly —
      strong support that this is the actual excitation laser source of the
      CSU-W1 confocal path. SpectraIII/AuraIII are LED light sources; this is
      the only laser.
    verified: true
    verified_date: 2026-08-10
    source: nis_elements_device_manager

# ─────────────────────────────────────────────────────────────────────────
# Light path per light source — obtained 2026-08-10 by user dictation. This
# only references, in order, devices already registered above (device specs
# themselves are not repeated here, docs/08 §6).
# ─────────────────────────────────────────────────────────────────────────
light_paths:
  - name: confocal-laser
    source: LUN-F-XL
    order:
      - {stage: source, device: LUN-F-XL, lines_nm: [405, 488, 561, 640]}
      - {stage: dichroic, device: CSUW1-Dichroic, registry: "Di01-T405/488/568/647-13x15x0.5",
         note: "excitation and emission make a round trip through the same element — reflected at the lines, transmitted in the emission bands (user confirmed). 2026-08-11: recording the old 'DM' (external) and 'CSUW1-Dichroic' (internal) as two separate elements was an error — corrected to one and the same element."}
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: dichroic, device: CSUW1-Dichroic, registry: "Di01-T405/488/568/647-13x15x0.5", note: "returning emission, same element as above"}
      - {stage: splitter, device: Splitter, registry: "DM A561LP", side_by_camera: {Kinetix_red: transmit, Kinetix_blue: reflect}}
      - stage: emission_filter
        note: >
          EM1/EM2 sit between the Splitter and the cameras, one immediately in
          front of each camera (one per arm). Confirmed 2026-08-11: EM1 is
          dedicated to Kinetix_red, EM2 to Kinetix_blue. EM2's filter
          configuration was also independently confirmed identical to EM1.
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
          Confirmed by user 2026-08-10: a pattern illuminator that controls
          illumination intensity and pattern (shape) across all wavelengths.
          No wavelength-selection function — treated as spectrally neutral for
          calculation (there may be transmission loss; value unconfirmed).
          The three-way cross-check (whether it is physically connected) is
          still incomplete (see the dmd: section above).
      - stage: branch
        device: LappMainBranch1
        note: >
          Confirmed by user 2026-08-10 (resolved): the geometry is asymmetric —
          SpectraIII is inline on the main optical axis, Aura is coupled in
          from the side. mirror_out: SpectraIII passes 100%, Aura is not
          coupled (0%). mirror_in: a 50/50 plate, so both sides get 50%.
          See the lapp_branch: section above for the full explanation.
      - {stage: excitation_filter, device: FilterTurret1, registry: "MXR00724-EX"}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM"}
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM", note: "returning emission, same element as above"}
      - {stage: emission_filter, device: FilterTurret1, registry: "MXR00724-EM"}
      - stage: internal_dichroic
        device: CSUW1-Dichroic
        registry: "Di01-T405/488/568/647-13x15x0.5"
        note: >
          Confirmed by user 2026-08-10 (resolved): the dichroic is always "on"
          regardless of CSUW1-Bright state — this element is not removed just
          because you are in Bright Field. Instead EM1/EM2 are set to
          quad-band (position 0, i.e. "multi") or Open (position 9, i.e.
          "empty") (2026-08-11 correction: what was previously recorded as a
          separate internal filter wheel "CSUW1-Filter_Red/Blue" was in fact
          EM1/EM2 — see confocal_scanner below). In other words this path is
          **not true white-light imaging** — imaging happens with the spectrum
          restricted by the dichroic (4-color notch) and the filter wheel
          state. 2026-08-11: band values confirmed (see the confocal-laser
          entry above).
      - {stage: splitter, device: Splitter, registry: "DM A561LP", side_by_camera: {Kinetix_red: transmit, Kinetix_blue: reflect}}
      - {stage: emission_filter, note: "EM1/EM2, one per camera — identical to the confocal-laser entry above, see there for details"}
      - {stage: camera, device: [Kinetix_red, Kinetix_blue]}
    note: "Widefield (LED-epi) illumination also passes straight through the CSU-W1 internal optics — the dichroic is always on (confirmed 2026-08-10)."

  - name: widefield-aura
    source: Aura # registry: AuraIII
    order:
      - {stage: source, device: Aura, lines_nm_approx: [405, 440, 488, 561, 640]}
      - stage: branch
        device: LappMainBranch1
        note: "Same as widefield-spectra3 above — see the lapp_branch: section for the full explanation. Aura only reaches the sample in the mirror_in (50/50) state."
      - {stage: excitation_filter, device: FilterTurret1, registry: "MXR00724-EX"}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM"}
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: dichroic, device: FilterTurret1, registry: "MXR00724-DM"}
      - {stage: emission_filter, device: FilterTurret1, registry: "MXR00724-EM"}
      - {stage: internal_dichroic, device: CSUW1-Dichroic, note: "same as widefield-spectra3 above — always on, not true white-light imaging"}
      - {stage: splitter, device: Splitter, registry: "DM A561LP", side_by_camera: {Kinetix_red: transmit, Kinetix_blue: reflect}}
      - {stage: emission_filter, note: "EM1/EM2, one per camera — see the confocal-laser entry above"}
      - {stage: camera, device: [Kinetix_red, Kinetix_blue]}

  - name: transmitted-light
    source: DiaLamp
    order:
      - {stage: source, device: DiaLamp, note: "white light"}
      - stage: color_filter
        device: null
        registry: "ColorFilter-DiaLamp"
        note: >
          User dictation 2026-08-19: a color filter can be inserted into the
          transmitted-light path (source unspecified so far — placement
          relative to the polarizer/condenser not yet confirmed). Off-ledger,
          not registered in MM/NIS.
      - {stage: polarizer, device: null, registry: "Polarizer-Linear",
         note: "angle adjustable, removable. May be a device not registered in MM/NIS — the angle itself is an off-ledger setting."}
      - stage: condenser
        device: CondenserTurret
        positions: {0: "1-ND", 1: "2-Shutter", 2: "3-", 3: "4-", 4: "5-", 5: "6-", 6: "7-"}
        verified: true
        verified_date: 2026-08-11
        source: mm_config
        note: >
          ⚠ New discovery (2026-08-10) — the darkfield/brightfield switching
          condenser.
          **Resolved 2026-08-11**: measured confirmation from the MM .cfg
          (DMD_dualcam.cfg) — it is actually registered as its own device
          `CondenserTurret` (adapter NikonTi2, child of Ti2-E__0). The earlier
          assumption that it "must be a property under the DiaLamp device" was
          wrong. Only positions 0/1 have labels (ND/Shutter) — labels 2-6 have
          no name in the MM .cfg (bare "3-"~"7-"), so what they actually are
          (darkfield ring, etc.) is still unconfirmed.
          **2026-08-19 user dictation**: confirmed there are exactly two
          condenser lens types available for this turret — bright-field and
          dark-field — consistent with the "darkfield/brightfield switching
          condenser" discovery above. Which of positions 2-6 correspond to
          each type is still unconfirmed (only that both types physically
          exist and are swappable on this turret).
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: filter_cube, device: FilterTurret1, note: "removable — a fluorescence cube may be left sitting in the transmitted-light path"}
      - {stage: analyzer, device: null, registry: "Analyzer-Linear",
         note: "angle not adjustable (fixed), removable"}
      - {stage: internal_dichroic, device: CSUW1-Dichroic, note: "same as the widefield entries above — always on, filter wheel empty/multi. This path is not true white-light imaging either."}
      - {stage: splitter, device: Splitter, registry: "DM A561LP"}
      - {stage: emission_filter, note: "EM1/EM2, one per camera — see the confocal-laser entry above"}
      - {stage: camera, device: [Kinetix_red, Kinetix_blue]}
    note: >
      The polarizer/analyzer are for liquid-crystal polarization observation
      (consistent with the note on the data/filters.yaml entry). Fluorescence
      experiments do not use this path at all, so a polarizer/analyzer left in
      the path is pure loss — already flagged as an ablation candidate in
      docs/01 §6.

  - name: mutual_exclusions
    note: >
      **2026-08-19 user dictation**: the confocal laser (LUN-F-XL, feeds
      CSUW1-Hub, see confocal-laser above) and the widefield epi-fluorescence
      lamps (LightEngine/SpectraIII, Aura/AuraIII, see widefield-spectra3 /
      widefield-aura above) cannot be used simultaneously.
      **Reason (confirmed by user)**: FilterTurret1's dichroic and emission
      filter (MXR00724-DM/MXR00724-EM) are in the way. The widefield paths
      route excitation/emission through FilterTurret1 (MXR00724 cube), while
      the confocal path is filtered instead by CSUW1-Dichroic + EM1/EM2
      downstream of the CSU-W1 — the two filtering schemes are built for
      different excitation bands (LED lines vs the 405/488/561/640 laser
      lines) and cannot both correctly pass/block light for the same
      exposure. So it is FilterTurret1's cube (dichroic + emission filter),
      not a shutter/hardware interlock, that forces the exclusivity. Any
      channel plan that assumes concurrent confocal-laser + epi-lamp
      illumination is invalid and must be flagged by Lens 1.

  - name: optical-tweezers
    source: Trap
    order:
      - {stage: source, device: Trap, registry: "Trap#IR1064", note: "1064 nm, not registered in MM — off-ledger"}
      - stage: dichroic
        device: FilterTurret2
        registry: "OT-Dichroic-750LP"
        note: >
          Confirmed by user 2026-08-10: FilterTurret2 had been recorded as
          "all six slots empty" (see the filter_turrets section above), but
          there is in fact a NIR-only (1064 nm) dichroic.
          **2026-08-11 correction**: "there are no excitation or emission
          filters" was wrong — there is also a 750/SP emission filter (see
          filter_turrets > FilterTurret2 above). The dichroic reflects only
          wavelengths longer than 750 nm (sending 1064 nm to the objective).
      - {stage: sample, device: [Nosepiece, objective, sample]}
      - {stage: emission_filter, device: FilterTurret2, registry: "OT-EM-750SP",
         note: "750/SP — blocks above 750 nm (scattered 1064 nm trap light). Newly confirmed 2026-08-11."}
    note: >
      Confirmed by user 2026-08-10: everything downstream of the sample is
      blocked (across the whole path, the visible-to-NIR filters/dichroics do
      not pass 1064 nm), so the detection path is judged not to need
      consideration when working out the optical tweezers light path — though
      docs/04 §3's "reason the grid was extended out to 1100 nm" (leak
      checking) remains a separate, still-valid concern, and does not
      contradict this conclusion (that check is precisely what verifies
      whether everything really is blocked).

  - name: known_gaps
    note: >
      Updated 2026-08-11 (3rd pass) — what is resolved and what remains.

      **Resolved:**
      - CSUW1-Dichroic is always "on" regardless of CSUW1-Bright state.
        Widefield and transmitted-light imaging pass through this dichroic
        too — i.e. this lab has no "true white light" imaging path.
      - LappMainBranch1: geometric asymmetry confirmed, SpectraIII (inline) /
        Aura (side-coupled). mirror_out → SpectraIII 100%, Aura 0%.
        mirror_in → both 50%.
        2026-08-11: **purpose** confirmed as well — mirror_in is used to run
        DMD and widefield at the same time, and the user judges the 50% Aura
        loss acceptable because widefield does not need a high light level.
      - Existence of a NIR-only dichroic in FilterTurret2 confirmed (no
        excitation or emission filter).
        2026-08-11: slot and configuration confirmed as well (slot 1, two
        parts: dichroic [reflects above 750 nm] + 750/SP emission filter).
        The user judges the edge values alone sufficient for calculation, so
        vendor/part number will be updated if obtained but will not be
        re-requested before then.
      - The DMD is a pattern illuminator for controlling illumination
        intensity and pattern across all wavelengths, with no wavelength
        selection. 2026-08-11: physical connection confirmed (see docs/02 §4).
        **The same day, measured confirmation from the MM .cfg
        (DMD_dualcam.cfg) that the MightexPolygon1000 device is registered
        too** — controllable via pymmcore-plus. This project decided not to
        use the NIS-Elements control path (2026-08-11, user) — see the dmd:
        section below.
      - Transmitted-light condenser confirmed (2026-08-11): the assumption
        that it "must be a property under DiaLamp" was wrong — it is actually
        registered in the MM .cfg as its own device `CondenserTurret`
        (NikonTi2 adapter, child of Ti2-E__0). 7-position, position 0="1-ND",
        1="2-Shutter", 2-6 unlabeled ("3-"~"7-"). See light_paths >
        transmitted-light > condenser below.
      - Exact band values for CSUW1-Dichroic obtained (2026-08-11,
        Di01-T405/488/568/647-13x15x0.5) — together with confirmation that it
        is the same physical element as the 'DM' in optical_path_nis that had
        been recorded separately; merged.
      - EM1/EM2 camera assignment settled (2026-08-11): EM1 = Kinetix_red,
        EM2 = Kinetix_blue (measured per-camera brightness cross-check).
      - EM2's per-position filter configuration independently confirmed
        (2026-08-11) — no longer an assumption from the statement "it should
        be the same as EM1", but settled by direct NIS-Elements cross-check.
      - `CSUW1-Filter_Red`/`CSUW1-Filter_Blue` (the CSU-W1 internal filter
        wheels, recorded separately from EM1/EM2) are confirmed to be the same
        physical elements as EM1/EM2 (2026-08-11) — there are only two
        physical filter wheels, one for red and one for blue. They are always
        in place regardless of confocal/widefield mode (user confirmed).
        Duplicate entries under confocal_scanner sub_devices removed, merged
        into optical_path_nis > EM1/EM2.
      - EM1/EM2 actual filter contents corrected (2026-08-11): while merging
        the above, reading the CSUW1-Filter_Red Label in DMD_dualcam.cfg
        directly showed that the "88000v2-quad/455/50/525/36/605/52/705/72"
        originally recorded as the EM1/EM2 filters was not the real value
        (misattributed data from another element — a correction note was left
        on the corresponding data/filters.yaml entry). The true values are
        multi/405/488/555/647 (position 0-4) + Blocked (5-8) + Open (9).
        With no fwhm or actual passband data they are left as registry: null,
        and they were also dropped from the emission_filters candidates in
        config/scopes/current-laser.yaml — the only calculation candidate now
        is "EM-Open". Obtaining the real specs of the 5 filters is a new open
        item.

      **Still open:**
      (1) The actual fwhm/passband specs of EM1/EM2 positions 0-4
          (multi/405/488/555/647) — until obtained, the only
          emission_filters calculation candidate is "EM-Open".
      The remaining light-path items this section was tracking are resolved as
      of 2026-08-11. (Remaining measurements are outside this section's scope:
      power-meter measurement of illumination light level and other roadmap
      Phase 0 items — see [07 roadmap](../../docs/07-roadmap.md).)

dmd:
  device: MightexPolygon1000
  vendor: Mightex
  model: Polygon1000
  mm_device: MightexPolygon1000   # DMD_dualcam.cfg: "Device,MightexPolygon1000,MightexPolygon1000,MightexPolygon1000"
  control: pymmcore-plus   # 2026-08-11 project decision: the NIS-Elements path is not used; every MM-registered device goes through pymmcore-plus
  verified: true
  verified_date: 2026-08-11
  source: mm_config
  note: >
    **2026-08-11**: confirmed physically connected (docs/02 §4 DMD row,
    "physical existence" resolved). Measured confirmation from the MM .cfg
    (DMD_dualcam.cfg) that the MightexPolygon1000 device is registered too —
    controllable via pymmcore-plus. **Project decision (2026-08-11, user)**:
    this project does not use the NIS-Elements control path — all future
    automation (roadmap Phase 5), DMD included, controls MM-registered
    devices via pymmcore-plus only.
    The three-way cross-check is not yet fully complete.
    Function confirmed by user 2026-08-10: a pattern illuminator controlling
    illumination intensity and pattern (shape) across all wavelengths — no
    wavelength-selection function. See light_paths > widefield-spectra3.

confocal_scanner:
  device: CSUW1-Hub
  vendor: Yokogawa
  model: CSU-W1
  connection: COM10
  sub_devices:
    # 2026-08-11 correction: the CSUW1-Filter_Red (wheel 1) / CSUW1-Filter_Blue
    # (wheel 2) that used to be here were in fact the same physical filter
    # wheels as EM1/EM2 in optical_path_nis (user confirmed: "I have two
    # physical filter wheels. one is only for the camera-red, the other(EM2) is
    # only for the camera-blue" — they were not separate elements inside the
    # CSU-W1). The position values that were here (multi/405/488/555/647/
    # b1-b4/open) had been recorded without measured verification; the EM1/EM2
    # values (measured, verified: true) are the correct ones. Duplicates
    # removed, see optical_path_nis > EM1/EM2.
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
        Confirmed by user 2026-08-10: currently "on". A multiband for
        separating the 4 confocal laser colors (405/488/561/640). b1/b2 are
        empty cartridge slots.
        **2026-08-11**: band values obtained
        (Di01-T405/488/568/647-13x15x0.5, NIS-Elements Mirror display values
        404-406/487-489/561-568/633-647 nm). Confirmed at the same time to be
        the same physical element as the 'DM' in optical_path_nis that had
        been recorded separately (correcting the 2026-08-10 dictation error) —
        that entry is merged here. See light_paths > confocal-laser.
    - {device: CSUW1-Bright, positions: {0: Confocal, 1: "Bright Field"}}
    - {device: CSUW1-Port, positions: {0: blue_only, 1: blue_red, 2: red_only}}
    - {device: CSUW1-Shutter}

light_path:               # LightPath device — eyepiece / left-right port selection
  device: LightPath
  positions: {0: EYE, 1: R100, 2: AUX, 3: L100}

intermediate_magnification:
  device: IntermediateMagnification
  values: [1.0, 1.5]        # matches the column headers of the magnification conversion-factor table (Sheet1)

lapp_branch:
  device: LappMainBranch1
  positions: {0: mirror_in, 1: mirror_out}
  current_position: 0 # mirror_in — assumed to be the state at the time of user confirmation; whether it is permanently fixed is unconfirmed
  note: >
    Confirmed by user 2026-08-10 (fully resolved). The two light sources are
    geometrically asymmetric: SpectraIII enters inline on the main optical
    axis, and Aura enters from the side and is coupled onto the main axis by
    this mirror.
      - mirror_out (no mirror, equivalent to an empty slot): the SpectraIII
        inline beam has nothing in its way and goes 100% to the sample. Aura
        has nothing to couple it in, so it does not reach the sample at all.
      - mirror_in (50/50 plate inserted): whichever side light comes from,
        50% transmits and 50% reflects — so 50% of the SpectraIII inline beam
        continues on, and at the same time 50% of the Aura beam is reflected
        and joins the same main optical axis.
    Source: user dictation (conversation at the time kb/systems/current.md was
    edited).

    **2026-08-11 purpose confirmed**: mirror_in is used when you want DMD
    pattern illumination and widefield (Aura) at the same time — Aura loses
    50% of its light level, but the user judges that loss acceptable since
    widefield imaging usually does not need a high light level. mirror_out is
    for when that combination is not needed (Aura unused, SpectraIII inline
    kept at 100%).
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

devices_not_in_mm_config:   # docs/02 §4 "three-way cross-check table" — separately controlled devices absent from the MM .cfg
  - name: "piezo stage (Prior/Queensgate NPC-D, Nanobench 6000)"
    control: "separate Python (hardware/piezo_stage.py), COM4 + vendor DLL — driven, with readback"
    mm_registered: false
    python_control: confirmed   # 2026-08-27: driven end to end, x axis, with readback
    confirmed_date: 2026-08-27
    driven: >
      **2026-08-27 — first light, and the stage moved under Python.** Link is the
      bare string "COM4" (no scheme; `sim:/NPC6330` is the DLL simulator), and
      `list_devices()` does not enumerate it, so the port has to be named. The
      port is **exclusive**: the vendor NanoBench 6000 GUI holds it while it has a
      session open and `connect()` then fails with "could not open comms link".

      Identity: DLL 2.7.9, firmware 6.7.8, 3 channels = x, y, z on 1, 2, 3, stage
      `SP-XYZ-600` serial 107866, calibration preset 6 "Customer 1".
      Travel **0..600 um on every axis** (`stage.position.calibrated-range.*`),
      which also settles the units question no units query could — 6.0e8 for a
      600 um stage is picometres and nothing else (the DLL's own unit getters
      answer empty, when they do not access-violate).
      Command quantisation **32 pm**, measured by stepping 2 pm at a time and
      watching `stage.position.command.get`.
      Servo/generator clock 20 us (`controller.sampling-time.get`).

      Host-timed drive, channel 1 (x), 1 Hz sine of 10 um peak-to-peak about
      300 um, 100 samples/cycle: achieved 1.0000 Hz, schedule slip median
      0.002 ms and max 0.091 ms, 0/300 overruns, measured span 9.9835 um of the
      10.0000 um commanded, |measured-commanded| median 329 nm (an upper bound —
      the readback follows the command, so it carries settling and a round trip).
      Round trips: set 0.68 ms median, get 0.42 ms median, so the link sustains
      ~890 samples/s. Static readback at 400 um: 2000 reads spanning 74 nm,
      stdev 12.6 nm, no outlier beyond 1 um.

      Security gates the command set, and this is the single most misleading
      thing about this controller. Locked (`security = None`) it reports 188
      commands of which exactly **one** is a `.set`
      (`controller.security.user.set`); `stage.position.command.set` is not
      unavailable but *invisible*, and asking about it answers "Invalid command
      name" — which reads like "this controller cannot do it". Unlocked to User:
      **414** commands. Codes are fixed vendor per-level constants in the GUI's
      own `C:/Program Files (x86)/NanoBench 6000/data/config.ini`
      `[SecurityLevels]`, and the **`0x` prefix is required** (`DEC0DED` answers
      "Not enough parameters", `0xDEC0DED` returns `User`). The level is
      controller-side state that outlives the session — the vendor GUI leaves it
      raised.
    note: >
      **ONE physical stage, TWO control interfaces** (resolved 2026-08-19).
      A discrepancy surfaced while tracing the LUN-F DAQ wiring: the NIS
      device DB (`C:\ProgramData\Laboratory Imaging\Platform\
      DeviceDatabase_6_00.dat` > dev_PhysicalDevice[NIDAQ].sConfiguration)
      carries a `PZ_Piezo Z` abstraction bound to `resource_AOPort = Dev1/ao2`
      (0-400 um <-> 0-10 V, resolution 0.0122 um, home 200 um, observed
      2026-08-19 at 197.6 um / 4.94 V), which looked like a second piezo.
      **User correction 2026-08-19: there is only one stage.** NIS drives it
      through the controller's *analog input* on `Dev1/ao2`; this repo drives
      the same controller through its *USB/COM + vendor DLL* interface. The
      USB route is the one to use, and the NIS/analog route is deliberately
      ignored -- per the user, the analog path does not expose the stage's
      full capability (the DLL command set in hardware/piezo_stage.py does).
      Consistent with [[project-pymmcore-only-no-nis]].
    hazard: >
      "Not used by us" is NOT the same as "safe to write". The analog cable
      from `Dev1/ao2` to the controller is still physically connected, so
      **never add `NIDAQAO-Dev1/ao2` to a Micro-Manager configuration** --
      MM initializes an AO device by writing 0 V, which would command the
      stage to 0 um. config/micromanager/DMD_dualcam_LUNF.cfg contains no AO
      device for exactly this reason.

      **2026-08-27 — the input-mode question, open since 2026-08-19, is
      answered.** On all three channels `stage.mode.digital-command.get` = 1 and
      `stage.mode.analogue-command.get` = 0, with `closed-loop` = 1,
      `is-sensor-only` = 0, `freeze-servo-output` = 0
      (`piezo_stage.mode_flags()`). The controller acts on the USB/DLL path and
      **ignores** the analogue input from `Dev1/ao2`. That is the reassuring
      answer, and the hazard survives it: the mode has no per-bit setter, but
      `stage.mode-mask.set` / `stage.mode-only.set` do exist at User level and
      write the raw mode word, so the mode is not immutable — it is merely not
      something this repo changes. Keep `NIDAQAO-Dev1/ao2` out of every MM
      configuration.

      **2026-08-26/27 — the command set, and what the offline extraction got
      wrong.** The 178 names in reference/npcd-command-set.md were recovered by
      pulling dotted ASCII literals out of the vendor DLL, and that file said
      plainly that they were a family-wide superset and a hypothesis. Confirmed
      against the controller on 2026-08-27 it moved both ways, so the extraction
      was not merely incomplete, and the file has been regenerated from the live
      controller (414 names at User level):

      - **Hyphens.** Real names carry them — `stage.mode.digital-command.get`,
        `function.waveform-generator.sample-period.get` — and the extraction's
        regexp could not match a hyphen, so whole families were invisible to it:
        `function.waveform-generator.*`, `function.waveform-builder.*`,
        `resonance-detect.*`, `diagnostics-logging.*`.
      - **Names that do not exist here.** `stage.command.digital.scaling.*` and
        `stage.command.analogue.scaling.gain/offset` answer "Invalid command
        name", as do the whole `fpga.*`, `peek.*` and `system.*` families. So the
        2026-08-26 claim of *independent scaling per command path* does not hold
        for this controller: there is one `stage.command.analogue.scaling.get`,
        reading 60, consistent with 600 um over a 10 V input — and consistent
        with NIS's own 0-400 um abstraction being **mis-scaled by 1.5x**, which
        would matter if anyone ever enabled the analogue path.

      **The hardware waveform generator exists but is NOT usable yet, and this
      is the hazard to carry forward.** `function.*` is 131 commands with two
      interfaces: `function.waveform.*` (a 500 001-sample buffer, one command per
      sample, `count`/`iterations`/`repeat-count`/`sample-period` per channel) and
      `function.waveform-generator.*` (segment-based — start/end position and
      velocity, duration — which is the one to use for a long smooth path).
      Two things were learned the hard way on 2026-08-27, both now enforced in
      hardware/piezo_stage.py:

      1. **The playback window defaults to the whole buffer.** Out of the box
         `waveform-start` = 0, `waveform-end` = **500000**, `count` = 1. Load 100
         samples and start, and it plays the other 499 901 — whatever is in the
         buffer — at 20 us a step. `upload_waveform()` now writes the window and
         `function_start()` refuses one that reaches past the count.
      2. **The generator does not read its samples in picometres.** A 100-sample
         +/-5 um sine about x = 300 um, uploaded in picometres (the unit
         `stage.position.command.set` takes), verified byte-identical by
         `function.waveform.data.get`, window 0..99, period 10 ms — played, it
         swung the axis over a measured **313.9 um**, ~31x the 10 um requested,
         with centre crossings 1-25 ms apart instead of 1 s. Not a readback
         artifact: 2000 static reads span 74 nm. Candidates, untested: the value
         is a DAC code rather than a distance (300 um of picometres wraps a
         24-bit code, which would scatter samples across the travel exactly like
         this), or it is an offset rather than an absolute position. The bounded
         way to tell is a **constant** waveform — every sample equal — which
         cannot oscillate whatever the unit, on a lateral axis. Until
         `piezo_stage.WAVEFORM_DATA_UNITS` is filled in, `function_start()`
         refuses.

      So: the *host-timed* path is confirmed and characterised, the
      *hardware-timed* path is one experiment away and must not be used before
      it. Either way this subsystem is readable, so unlike the tweezers a
      commanded trajectory here can be verified rather than assumed.
      **Open, and cheap to close: the security level has one more notch.** The
      command set is gated per level -- 188 commands at the base level, 414 at
      User -- and `piezo_stage.ACCESS_CODES` carries `super-user = 0xB01DFACE`
      from the vendor GUI's config file, never sent. So "414" is a floor. It also
      puts a claim in reference/npcd-command-set.md at risk: the `fpga.*`,
      `peek.*`, `system.*` and `stage.command.digital.scaling.*` families are
      recorded there as belonging to other models on the evidence that they answer
      "Invalid command name" -- which is also what a gated command answers. The
      run sheet is kb/systems/piezo-superuser-RUN-FIRST.md and the tool is
      config/piezo/dump_command_set.py; both are read-only and cannot move the
      stage.
      See kb/decisions/2026-08-26-piezo-waveform-generator.md.
  - name: "optical tweezers (Aresis Tweez 305/310, Tweez 300)"
    control: "separate Python (hardware/optical_tweezers.py, TCP 2070) — write-only; several essentials are GUI-only"
    mm_registered: false
    python_control: partial   # was `confirmed` (2026-08-10); qualified 2026-08-26 after reading the manual end to end
    confirmed_date: 2026-08-26
    note: >
      **2026-08-26 — the 2026-08-10 "python_control: confirmed" was too
      generous, and is now split by operation.** Full reasoning in
      kb/decisions/2026-08-26-tweezers-pattern-vs-direct.md and
      kb/decisions/2026-08-26-parallel-control-architecture.md.

      **Over TCP (port 2070, incrementing per GUI instance):** trap create/
      delete/on/off, TRAP_POSITION absolute and relative, TRAP_STRENGTH,
      pattern load/assign/rotate/scale/breakpoint-release, trap groups,
      LASER_ON/OFF, BEAM_SET_FOCUS, BEAM_SET_PARAMS, CLEAR_PROJECT and
      LOAD_PROJECT. hardware/optical_tweezers.py covers the whole documented
      command set — nothing was missing.

      **The interface is write-only.** No query command of any kind exists: no
      trap position, no force, no trap list, no laser power. A 0 means the GUI
      accepted the command, not that anything moved. Hence the
      active-microrheology channel reading force as F = kappa*(x_bead - x_trap)
      from the images rather than from the instrument, and hence the read-back
      verification hardware/microscope.py leans on having no analogue here.
      Liveness can only be probed indirectly — TRAP_DELETE against a sentinel
      name answers -25 from a working GUI (OpticalTweezers.wait_until_ready).

      **GUI-only, i.e. not reachable from Python at all:** per-trap wait states
      (the vendor mechanism for slow driven motion; only BEAM_SET_PARAMS is
      exposed and it is global); repeat enable/count; breakpoint Enable/Release
      bits; both calibrations (see the next entry); global laser power (System
      Manager > Laser Beam Control, relative 0-1 with 1 ~ 5 W on a Tweez 305,
      p.24 — per-trap relative strength IS over TCP, so the workable split is
      global power set once from the GUI or a project template and per-trap
      modulation from Python); and camera selection/release (GUI Tree View,
      p.48).

      **LOAD_PROJECT is the way round most of that.** A project is XML and
      carries the Tweez Elements tree, GUI settings *including camera settings
      and calibration*, ROIs, Views, and the laser + beam state (p.65) — so
      per-objective templates give per-objective calibration, selectable over
      TCP. Two cautions: it can restore a saved laser-ON state, and it returns
      0 even when the load report (visible only via Show Project Manager) says
      elements were dropped; the manual s own figure shows ROIs lost to a
      camera change.

      **Timing.** Pattern traversal is hardware-clocked by the AOD trap loop,
      one point per pass at up to 100 kHz, so .tpf patterns rather than TCP
      position streaming are the route for anything whose timing enters the
      result. Host round-trip latency over TCP is **still unmeasured**;
      config/session/measure_latency.py measures it read-only.

      **Two contradictions in the manual, unresolvable from the document:**
      LOAD_PATTERN argument order (Command List p.68 gives name-then-file, the
      p.69 example shows file-then-name) and the pattern-file extension (.tpf
      is claimed for both the ASCII pattern file, pp.55-56, and the XML project
      file, p.65; the single .tsf in the manual is that same example). Settle
      the second with: dir "%ProgramFiles%\Aresis\Tweez\Samples\Patterns".
  - name: "optical-tweezers calibrations (GUI + trapping field)"
    control: "GUI only — interactive, cannot be automated"
    mm_registered: false
    python_control: false
    confirmed_date: 2026-08-26
    note: >
      Two independent calibrations, both objective-dependent.

        - **GUI calibration** (pp.35-38, Tweez 300 GUI). *Magnification*
          (ICS<->WCS, px -> um) is set by dragging a scale line across a
          graticule and typing the distance. *Beam Position* (LCS<->ICS:
          rotation + translation + scale) needs an actually trapped ~2.5 um
          silica bead, the laser ON at 0.1-0.2, and at least 3 mouse-picked
          points (>=6 advised across the whole range). **The green trapezoid
          marking the trapping range is the output of this procedure** — which
          is why the range has to be read off the GUI and cannot be computed
          here. Per-camera: "each camera has its own calibration data
          attached" (p.37). Carried in a GUI project. Cannot be started while
          a project is active.
        - **Trapping field calibration** (pp.28-32, System Manager). AOD
          response; automatic, but needs a photodiode placed over the
          objective with the laser off and the objective retracted. **Not**
          carried by a project — saved and loaded from the System Manager s own
          File menu. The manual calls redoing it after an objective change
          "particularly important when performing e.g. force measurements,
          micro rheology", i.e. exactly this lab s experiment.

      Both are invalidated by an objective change, so moving the Nosepiece from
      hardware/microscope.py silently breaks the tweezers in um and in force,
      with nothing on either side reporting it. microscope.COLLISION_DEVICES
      records this as the second, independent reason that gate exists.

      A free cross-check available today: pixel_size_calibration above already
      carries a measured 0.1625 um/px for 40x at 1x intermediate magnification,
      so the GUI Magnification value should agree with it if the Tweez GUI is
      reading a Kinetix through the same tube optics.
  - name: "Kinetix cameras — shared with the optical-tweezers GUI"
    control: "pymmcore-plus, but not exclusively owned"
    mm_registered: true
    python_control: confirmed
    confirmed_date: 2026-08-26
    hazard: >
      **The Tweez 300 GUI loads a Kinetix, uses it, then releases it** (user,
      2026-08-26) — the same body Micro-Manager drives — and PVCAM hands a
      camera to exactly one process at a time. Whoever opens it first locks the
      other out, in both directions: with MM holding it the Tweez GUI gets no
      live image, which blocks its GUI calibration (Beam Position has to *see*
      trapped beads) and all visual trap placement; with the Tweez GUI holding
      it, initializing the camera under pymmcore-plus fails on an error that
      names nothing useful.

      **Required order: Tweez GUI takes the camera -> GUI calibration and trap
      setup -> release -> Micro-Manager loads its configuration -> acquire.**
      Enforced in code by hardware/orchestrator.py (Session.tweezers_setup,
      microscope_setup, CameraArbiter) rather than left to be remembered, and
      microscope.SHARED_DEVICES turns a contended load failure into a message
      that names the tweezers GUI. The drive survives the release — TCP trap
      and pattern commands need no image and the GUI runs cameraless (p.34) —
      so only the interactive parts are lost.

      This also reconciles the manual listing only DirectShow and IDS uEye
      camera categories: TweezGUICamPluginPM (archived — see manual/README.md)
      is the Photometrics plugin that adds the Kinetix. **Which body the GUI is
      bound to (Kinetix_red or _blue) is not yet recorded**, and it matters
      because the calibration is per-camera. Note too that multiple GUIs can
      attach to one System Manager with the TCP port incrementing per instance,
      so the port selects which camera and which calibration you are driving.
  - name: "LUN-F-XL laser combiner (405/488/561/640)"
    control: "split: blanking (on/off) via MM NIDAQ — working; per-line power via FT4222H SPI — transport only, blocked on the SPI word format"
    mm_registered: partial   # blanking lines yes (as NIDAQ devices); the laser itself is not one MM device
    python_control: partial
    confirmed_date: 2026-08-19
    note: >
      History: user dictation on 2026-08-10 said "Python control confirmed",
      with no record of which interface. On 2026-08-12 grep + an actual
      pymmcore-plus load settled that it is not registered in MM as its own
      device, and the **2026-08-12 user correction** was that the connection
      had simply not been made yet — no hidden path to find.

      **2026-08-19 — the control path is now traced and it is a two-way
      split** (read out of the NIS device DB `dev_PhysicalDevice[LUN-F].
      sConfiguration`, cross-checked against the NIS "LUN-F Configuration"
      dialog; see [[hardware/lunf_power.py]] for the full record):
        - **on/off (blanking)** → NI PCIe-6323 digital lines
          `Dev1/port0/line2/4/6/8` for 405/488/561/640, driven by MM's stock
          NIDAQ adapter. **This half works** — wired up in
          config/micromanager/DMD_dualcam_LUNF.cfg, 5.4 us measured.
        - **per-line power** → SPI DAC behind an FTDI FT4222H
          (`FT4222_00294-BOA/AO_A_0..3`). Transport is reachable (FT_OpenEx
          rc=0, chip rev D, 60 MHz) but **Nikon does not document the DAC word
          format**, so `lunf_power.PROTOCOL` is None and `set_power()`
          deliberately refuses rather than write guessed bytes at a laser
          AOTF driver.
      So power is the only half still missing, and it is blocked on a
      protocol unknown — not on wiring.

      **2026-08-19 user status**: connecting the LUN-F directly to the PC is
      proving difficult. **Plan: connect it straight over USB-B** and work the
      method out from there — i.e. try for a native/vendor link to the laser
      itself rather than continuing through the FT4222 bridge that NIS uses.
      If that USB-B route exposes a documented command set it supersedes the
      SPI-capture plan in lunf_power.py's docstring (USBPcap + Wireshark on
      the FT4222 endpoint) and removes the word-format unknown entirely — so
      **try USB-B first, capture second**. Not yet attempted.
      Consistent with [[project-pymmcore-only-no-nis]]: whatever path lands,
      the NIS control route is not used.
  - name: "CSUW1-Dichroic / EM1(CSUW1-Filter_Red) / EM2(CSUW1-Filter_Blue) filter elements (confocal path)"
    control: pymmcore-plus
    mm_registered: true
    python_control: confirmed
    confirmed_date: 2026-08-12
    note: >
      **Resolved 2026-08-12**: DMD_dualcam.cfg (a copy with only
      MightexPolygon1000 removed) was actually loaded via pymmcore-plus and
      all three devices read live —
      CSUW1-Dichroic state 0/"on", CSUW1-Filter_Red(EM1) state 0/"multi",
      CSUW1-Filter_Blue(EM2) state 0/"multi" — all matching this document's
      existing record. The earlier assumption that they were "NIS-Elements
      only" was wrong — they were properly registered all along by the MM
      `.cfg` lines `Device,CSUW1-Dichroic,...`/`Device,CSUW1-Filter_Red,...`/
      `Device,CSUW1-Filter_Blue,...` (see confocal_scanner and
      optical_path_nis > EM1/EM2 above) — NIS-Elements was merely the tool
      used to *observe* these devices, not the only control path.
  - name: "Splitter (dual-camera image splitter, DM A561LP)"
    control: "none — not yet connected to any programming interface"
    mm_registered: false
    python_control: not_connected
    confirmed_date: 2026-08-12
    note: >
      Split off while re-checking together with the CSUW1 group above:
      **the Splitter has no `Device,` line in any of the 9 .cfg files in this
      folder, and does not appear in the actual pymmcore-plus load
      (getLoadedDevices()) either** — unlike CSUW1-Dichroic/EM1/EM2, its
      absence from MM is settled. **2026-08-12 user correction**: as with
      LUN-F-XL, this is not a "hidden path to be found" but **a connection
      that has not been made yet** — the optical_path_nis > Splitter entry was
      observation only, via NIS-Elements Device Manager; programmatic control
      has never even been attempted. For now treat it as manual operation
      only, and re-check the pymmcore-plus path once the connection work is
      done.

# 2026-08-10 user dictation: beyond the two items above, the user says Python
# control has been confirmed for every piece of equipment appearing in this
# dossier, including the microscope stand (Ti2-E), the confocal (CSU-W1), and
# the DMD (Polygon1000). The stand/confocal/DMD are already MM .cfg-registered
# devices, so the pymmcore-plus path was judged likely to work for them.
#
# 2026-08-11 settled (actual access to the microscope PC): the DMD was
# confirmed directly by grep to be registered in the MM .cfg (see the dmd:
# section above). And a **project decision**: this project does not use the
# NIS-Elements control path — items that had remained NIS-Elements-only, such
# as LUN-F-XL/CSUW1-Dichroic above, are now to be judged by this decision
# rather than marked "to be re-checked". Devices not registered in MM (the
# laser combiner, internal confocal filter elements, etc.) are still
# unreachable via pymmcore-plus, so how to obtain that path remains a separate
# problem.
#
# 2026-08-12 re-check (microscope PC, verified by an actual pymmcore-plus
# load): the three devices_not_in_mm_config items above split into
# CSUW1-Dichroic/EM1/EM2 (resolved, confirmed via pymmcore-plus) vs
# LUN-F-XL/Splitter (unresolved, absence from MM settled) — see each item's
# note. One incidental environment issue was found and fixed along the way:
# the pymmcore-plus in-house MM build obtained via `mmcore install`
# (interface v75) is missing `Ti2_Mic_Driver.dll` (the Nikon vendor SDK), so
# the NikonTi2 adapter would not load at all — fixed by copying just that DLL
# from the lab's existing installation (`C:\Program Files\Micro-Manager-2.0`)
# (reproducible; the adapter DLL itself was not touched).
# Without that copy, every NikonTi2 child device — including the stand and the
# CSU-W1 — fails to load under pymmcore-plus. This step may be needed again
# before starting Phase 5a (state readout).
---

## How this was obtained

This dossier is extracted verbatim from two files the user provided:

1. `DMD_dualcam.cfg` — the Micro-Manager configuration file (created by
   Configurator 2026-07-03 15:32 PDT). This is the **current-system MM `.cfg`**
   that the README marked "top priority · not yet obtained".
2. `Confocal_microscope_conversion_factor(Apr 2025).xlsx` — a measured table of
   effective pixel size for the Kinetix camera, per magnification (4x-100x) ×
   intermediate magnification (1x/1.5x). This fills the "measured pixel-size
   calibration" item in roadmap Phase 0.
3. **NIS-Elements Device Manager measurement (2026-08-10)** — the user opened
   NIS-Elements and captured the Device Manager > Hardware Configurations view
   and the Filter Block Settings dialog of each filter element directly. This
   confirmed the actual passbands of `FilterTurret1` position 0 (MXR00724),
   which had only a label and no known contents in the MM .cfg, and newly
   discovered the confocal-path filter elements (DM/Splitter/EM1) and the laser
   combiner (LUN-F-XL), which are not registered in the MM .cfg at all. The
   `optical_path_nis`, `lasers`, and `light_sources` (LightEngine/Aura product
   names) entries came from this source.
4. **Nikon Objective Selector catalog cross-check (2026-08-10)** — the 6
   objective label strings in the `.cfg` were cross-checked against Nikon's
   official product comparison page (by part number) to settle NA, WD,
   coverslip, immersion medium, and part number. The entire `objectives` entry
   came from this source.

## Serial/model numbers — what was obtained and what was not

The `.cfg` file itself mostly records only device names and adapters, leaving
out serials. The only code-like string actually found in this extraction is
**`MXR00724`** (the `FilterTurret1` slot 0 label `"1-MXR00724 -Empty"`). It
looks like a Nikon filter cube catalog number, but the slot itself is recorded
as `Empty`, so even whether the physical part is present is uncertain.

For the cameras (Kinetix ×2), DMD (Polygon1000), confocal (CSU-W1), and light
sources (Lumencor ×2), **only model names are confirmed; the serials are not in
the `.cfg`** — they have to be read off the physical equipment labels or from
the "device info/About" screen of the respective software. In an earlier
session, commands that can obtain the piezo stage serial by live query
(`identity.hardware.serial.get`, etc.) were already identified
([hardware/piezo_stage.py](../../hardware/piezo_stage.py)) — these can be run
to fill it in if needed.

## Items needing confirmation (those marked verified: false)

- ~~Whether the last number in an objective label is NA or WD(mm)~~ →
  **resolved 2026-08-10.** All 6 confirmed against Nikon's official catalog
  (Objective Selector, part-number cross-check) — the trailing figure is
  **WD(mm)** in every case. Only 20x (`LmbdD0.8`) happens to have the same
  value for NA (0.80) and WD (0.8mm), which was the source of the confusion.
  **Fully resolved 2026-08-11**: the user also personally completed the
  physical barrel engraving cross-check (whether each lens really is the part
  its label claims, and whether anything was swapped or mislabeled) — this
  roadmap Phase 0 item is done.
- ~~The exact product names of the two Lumencor devices `LightEngine`/`Aura`~~ →
  **resolved 2026-08-10.** Confirmed in NIS-Elements Device Manager as
  `LightEngine`=SpectraIII, `Aura`=AuraIII. However, the per-line center
  wavelengths of both devices are approximate readings off diagram icons, so
  fwhm and a cross-check against the actual catalog specs are still not done.
- ~~Whether `MightexPolygon1000` (the DMD) is actually physically connected~~ →
  **resolved 2026-08-11.** The user confirmed it is physically connected — the
  "DMD: physical existence" cell of the three-way cross-check table in
  [02 §4](../../docs/02-knowledge-base.md) was updated at the same time.
  Whether it is registered in MM/NIS, and which software controls it, is still
  unconfirmed (see the `dmd:` section above).
- ~~The purpose of `LappMainBranch1`~~ → **behavior resolved 2026-08-10,
  purpose added 2026-08-11.** The physical behavior of mirror_in/out was
  confirmed on 2026-08-10, and on 2026-08-11 **why** mirror_in is used (DMD +
  widefield simultaneously; why the 50% Aura loss is worth accepting) was
  confirmed too — see the `lapp_branch` section above.
- ~~Serial numbers not obtained for either camera (Kinetix_blue/red), the
  CSU-W1, the DMD, or either light source~~
  → **2026-08-11: judged unnecessary by the user — no longer an item to
  confirm.**

## Related documents

- [02 Knowledge base §3 system dossier](../../docs/02-knowledge-base.md) — the schema this file follows
- [02 §4 three-way cross-check table](../../docs/02-knowledge-base.md) — why MM/NIS/physical cross-checking is needed
- [07 Roadmap Phase 0](../../docs/07-roadmap.md) — the items this dossier fills
