# manual/

**No manuals are published here.** The 14 PDFs this folder held were removed on
2026-08-28 — this repository is public and has no licence to redistribute vendor
documentation. Each is available from its manufacturer;
[`NOTICE.md`](../NOTICE.md) lists which document came from whom. This file stays
because *which revision to cite, and why*, is the part that took work — see
[Camera/](#camera--which-kinetix-22-revision-to-cite) below.

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

## Restored onto this machine, 2026-09-04 — 13 of the 14, plus Ti2

`manual/` holds 15 PDFs again (21 MB). Twelve were copied from
`C:\Users\Takatori lab\Desktop\Maintanance\Setup\`; the thirteenth, the Kinetix
22 datasheet, arrived separately from the vendor later the same day (below).
**They are still not published.** `.gitignore` ignores `manual/*` and excepts only this file, and
`*.pdf` catches them a second time, so `git status` stays clean and
`git add manual/` adds nothing — verified file by file with `git check-ignore -v`
on the day of the copy. Nothing about the public repository changed; only this
working copy has the documents.

Against the §2 table in [`NOTICE.md`](../NOTICE.md):

| Folder | §2 expects | Restored | From |
|---|---|---|---|
| `Optical Tweezers/Manuals/` | 4 | 4 | `Setup/Optical Tweezers/` |
| `Piezo Stage/` | 7 | 7 | `Setup/Piezo Stage/{Controller Interface DLL & Drivers,User Manuals,Nanobench,Nanoflash}/` |
| `DMD/` | 1 | 1 | `Setup/DMD/Mightex Polygon1000 uManager … V1.0-202103/…/Polygon1000/Documentation/` |
| `Camera/` | 2 | **1** | vendor, direct — not the Desktop folder |
| `Ti2/` | — | 2 | `Setup/Ti2 Ver2.90/MEA54000_Ti2 Control Ver2.90_Windows/Docs/` |

**`Camera/` was the gap, and the cited revision is now closed.** Neither Kinetix
22 revision is in the Desktop folder — nothing there matches `*kinetix*` or
`*datasheet*` except DMD and OT calibration files. That folder is *install
media* (1049 files: the LabVIEW 2017 runtime, PVCam and DMD driver packages,
Tweez300 and Nanobench setups), and a camera datasheet is not install media, so
it was never there to begin with. It came from the vendor instead, and is filed
as:

    manual/Camera/Kinetix22-Datasheet_Rev-2024-10-21.pdf

`Revision Date: 2024 10 21` on its last page, so this is the revision every
number in `data/detectors.yaml > Kinetix22` cites — a document that, between
2026-08-28 and this date, was on no disk this repository could reach.

**Which bytes, since that mattered once.** This is the 597,606 B / md5
`2be65728…` vendor attachment described at the end of the next section, not the
634,093 B / md5 `95a52c6c…` mirrored copy. That note explains why the
attachment was *not* filed at the time: a second copy of one revision is how
the "which one do I cite" question comes back. The mirror went with the
2026-08-28 removal, so the attachment is now the only copy and the ambiguity it
guarded against no longer exists. The two were verified text-identical when both
were in hand, so nothing citing the mirror's content is disturbed by the swap.
`pdftotext -layout` here gives 197 lines against the 196 recorded next door;
the file ends `\r\n\f`, so that is a page-break/poppler-version artifact, and
the md5 matching the recorded attachment exactly is the check that settles
identity.

**Still missing: Rev A3-05112021**, the second of the two, which is why the
table above reads 1 of 2. It is wanted only as provenance for a known-wrong
line-time row and nothing cites it for a value, so this is the cheap half of
the gap — see the next section for why it was kept at all.

**One thing the recovered document settles.** Rev 2024-10-21 states the
Speed-mode full-frame rate twice and disagrees with itself: the page-1 bullet
and the CAMERA MODES table say **664 fps**, the KINETIX22 SPEED TABLE's
`2400 x 2400` row says **663**. `data/detectors.yaml` carries both — 664 at the
`Speed` mode entry, 663 in `frame_rate_by_roi_fps` — because each was
transcribed faithfully from its own table. That is the right behaviour and it
reads like a typo, so it is recorded here now that the source is back and can
be pointed at.

**`Ti2/` is not a restore.** `M706_E15_Ti2Control_Windows.pdf` (English) and
`M706_J15` (Japanese) are the Ti2 Control 2.90 software manual. Neither was
among the 14, and nothing here cites either one yet — they are filed because
the stand is a Ti2 and the document was sitting in the install media.

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

**Superseded 2026-09-04.** That attachment is now filed, as
`Camera/Kinetix22-Datasheet_Rev-2024-10-21.pdf`, and is the only copy in
existence here — the mirrored copy this paragraph weighs it against went with
the 2026-08-28 removal. Filing it no longer creates the second copy the decision
above was avoiding; it ends a stretch with none. See the restore section above.
