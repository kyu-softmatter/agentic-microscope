# manual/

Distilled on 2026-08-10. This folder used to be 1.3 GB (573 files): PDFs mixed
in with vendor installer executables, driver packages, and SDK/sample code
for the piezo stage, optical tweezers, DMD, and camera. It is now just the
~12 PDF manuals/release notes (13 MB) -- the actual reference documents,
not the software.

**Everything that was removed is backed up**, uncut, at:

    D:\backup\연구\experimentalist_installers\manual\

That backup keeps everything except pure installer/driver packages (setup
wizards, .msi/.exe installers, driver .inf/.cat/.sys bundles, prebuilt
redistributable DLLs like the OpenCV binaries bundled with the DMD support
package) -- those were deleted outright, not archived, since they're vendor
software reinstallable from the manufacturer if ever needed again. What the
backup *does* keep: the NPC-D piezo controller's C/C++/Python SDK (headers,
multi-platform prebuilt libraries, example projects under `Controller
Interface DLL & Drivers/.../controller_interface/` and `.../examples/`),
`TweezGUICamPluginPM`, and the small Mightex DMD config templates -- real
reference/sample-code value, not disposable install media.

Two exceptions worth knowing if something breaks:
- `Optical Tweezers/Tweez300Setup_V3.0.2.0.msi` (and a `.old` sibling
  version) and `Camera/PVCam_3.10.1.1-SDK60_Setup.exe` /
  `PVCam_3.10.2.7-PMQI_Release_Setup.exe` were deleted, not archived --
  these are the exact installer versions matched to the drivers currently
  running in the lab. If a fresh install ever needs *that specific* old
  version rather than whatever is current on the vendor site, it is gone
  for good.
- `hardware/piezo_stage.py`'s vendor DLL adapter (`dll_adapter.py`) and the
  DLLs it loads are unaffected -- those were already copied into
  `hardware/piezo/vendor/` before this cleanup and still work at runtime.

---

## Camera/ — re-created 2026-08-19

The old `Camera/` folder held only PVCAM installers and was deleted in the
2026-08-10 distillation. It is back, holding reference documents only:

- `Kinetix22-Datasheet_Rev-2024-10-21.pdf` — **the one to cite.** Source of
  every number in `data/detectors.yaml > Kinetix22`. Provenance confirmed
  first-party 2026-08-20 (below).
- `Kinetix22-Datasheet_Rev-A3-05112021_SUPERSEDED-line-times-wrong.pdf` — kept
  only as provenance for the warning in that registry entry. Its "Line Time"
  row (5 / 0.836 / 4.71 / 80.12 µs/line) is too large by exactly 3200/2400,
  contradicts the frame-rate row in the same document, and would put every
  frame rate 25% low. The 2024 revision corrects it.

Both were fetched from vendor/distributor mirrors because
`photometrics.com/wp-content/uploads/.../Kinetix22-Datasheet_2024_rev2.pdf` now
301-redirects to a marketing page.

**That mirror caveat is retired for the 2024-10-21 revision, 2026-08-20.**
Teledyne Photometrics sent the same revision directly, as an attachment to
[`reference/quotes/2026-08-20_teledyne-kinetix22-inquiry_price-and-demo-loan.md`](../reference/quotes/2026-08-20_teledyne-kinetix22-inquiry_price-and-demo-loan.md).
`pdftotext -layout` on the vendor copy and on the file here gives 196 lines with
zero diff, so the mirrored copy is authentic and every number
`data/detectors.yaml > Kinetix22` draws from it is first-party.

The vendor copy was **not** filed — it is a re-optimized web export of the same
revision, identical in text but not in bytes (597,606 B, md5 `2be65728…` vs the
634,093 B, md5 `95a52c6c…` here), and a second copy of one revision is how the
"which one do I cite" question comes back. If a byte-exact first-party original
is ever wanted over the mirror, that is the swap to make — nothing cites the
bytes, only the content.

The Rev A3-05112021 file above is still mirror-sourced. It does not matter:
it is kept *because* it is wrong, and nothing cites it.
