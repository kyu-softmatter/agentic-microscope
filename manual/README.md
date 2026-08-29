# manual/

**No manuals are published here.** The 14 PDFs this folder held were removed on
2026-08-28 — this repository is public and has no licence to redistribute vendor
documentation. Each is available from its manufacturer;
[`NOTICE.md`](../NOTICE.md) lists which document came from whom. This file stays
because *which revision to cite, and why*, is the part that took work — see
[Camera/](#camera--re-created-2026-08-19) below.

Distilled on 2026-08-10. This folder used to be 1.3 GB (573 files): PDFs mixed
in with vendor installer executables, driver packages, and SDK/sample code
for the piezo stage, optical tweezers, DMD, and camera. The 2026-08-10 pass cut
it to ~12 PDF manuals/release notes (13 MB) -- the actual reference documents,
not the software. The 2026-08-28 pass removed those too.

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
- `hardware/piezo_stage.py`'s vendor DLL adapter (`dll_adapter.py`) survived
  this cleanup, having been copied into `hardware/piezo/vendor/` beforehand, and
  it is still here. The two DLLs it loads are **not** -- they were removed on
  2026-08-28 with everything else vendor-licensed. `dll_adapter.py` was kept
  because it carries local modifications; restoring the DLLs is step 3 of
  [`NOTICE.md`](../NOTICE.md).

---

## Camera/ — which Kinetix 22 revision to cite

Two revisions of the Kinetix 22 datasheet were held here from 2026-08-19 until
the 2026-08-28 removal. Which one a number came from decides whether the number
is right, so that distinction is recorded here rather than lost with the files.

- **`Rev 2024-10-21` — the one to cite.** Source of every number in
  `data/detectors.yaml > Kinetix22`. Provenance confirmed first-party
  2026-08-20 (below).
- **`Rev A3-05112021` — wrong, and worth knowing that it is.** Its "Line Time"
  row (5 / 0.836 / 4.71 / 80.12 µs/line) is too large by exactly 3200/2400,
  contradicts the frame-rate row in the same document, and would put every
  frame rate 25% low. The 2024 revision corrects it. It was filed *because* it
  is wrong — as provenance for the warning in that registry entry — and nothing
  cites it for a value.

Both were fetched from vendor/distributor mirrors because
`photometrics.com/wp-content/uploads/.../Kinetix22-Datasheet_2024_rev2.pdf`
301-redirects to a marketing page.

**That mirror caveat is retired for the 2024-10-21 revision, 2026-08-20.**
Teledyne Photometrics sent the same revision directly, attached to vendor
correspondence of that date (not published — see [`NOTICE.md`](../NOTICE.md)).
`pdftotext -layout` on the vendor attachment and on the mirrored copy filed here
gave 196 lines with zero diff, so the mirror was authentic and every number
`data/detectors.yaml > Kinetix22` draws from it is first-party.

The vendor attachment was **not** filed alongside it — a re-optimized web export
of the same revision, identical in text but not in bytes (597,606 B, md5
`2be65728…` against the 634,093 B, md5 `95a52c6c…` copy that was here), and a
second copy of one revision is how the "which one do I cite" question comes
back. Nothing cited the bytes, only the content.
