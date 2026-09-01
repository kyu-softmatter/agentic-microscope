# NOTICE — what is not published here, and what is not mine to licence

This repository is public. Vendor manuals, proprietary DLLs, and commercial
correspondence were removed on 2026-08-28 because this repository has no licence
to redistribute them, and because the quotes carried third parties' names
alongside pricing.

**Scope of this notice.** The 19 files listed in §1–3 are in no commit of this
repository. They were removed from every commit with `git filter-repo`, not just
from the tip — see [Git history](#git-history) at the bottom for what that did
and did not accomplish.

**§4 is the converse**, added 2026-08-31 alongside the [MIT
licence](LICENSE): material that *is* here and that the licence does not reach.
A licence is a claim of ownership, so what it cannot cover has to be named as
precisely as what was removed.

---

## 1 · Commercial correspondence — removed, not replaced

| Removed | Carried |
|---|---|
| `reference/quotes/2024-09-29_nikon-quote-…md` | quote total, per-section line items, quote number, contract vehicle, payment terms, recipient's room address, vendor sales contact |
| `reference/quotes/2024-09-29_nikon-quote-…pdf` | the original quotation document |
| `reference/quotes/2026-08-20_teledyne-kinetix22-inquiry_…md` | indicative unit price, lead time, demo-loan terms, vendor sales contact |

The filenames are elided above because they carried the quote number, which is
itself a pointer to the document and is redacted throughout this history.

These are not re-published in redacted form. The repository's own convention,
stated in the second file's header before it was removed, is that **the source
document stays in the mailbox and only the figures it settles are copied in** —
so the correspondence was never the right thing to hold here in the first place.

**What the knowledge base actually drew from them is still here**, stated inline
wherever it is used:

- `data/detectors.yaml > Kinetix22` — every spec number, with the datasheet
  revision named as its source.
- `kb/systems/current.md` — the purchase-record cross-check: 6 objectives, 4 EM1
  filters, the FilterTurret1 pos-0 cube (MXR00724) and the CSU-W1 body all match
  the purchase record down to the part number. The camera configuration does not
  (purchased Kinetix22 + Prime95B, current Kinetix ×2), and that discrepancy and
  its resolution are recorded there.

No spec, gate, or verdict in this repository depends on a price.

## 2 · Vendor manuals — obtain from the vendor

14 PDFs under `manual/` were removed (~11 MB). They are reference documents,
cited by filename and revision wherever a number comes out of them, and each is
available from its manufacturer:

| Was under | Documents | Source |
|---|---|---|
| `manual/Camera/` | Kinetix 22 datasheet, rev 2024-10-21 (cited) and rev A3-05112021 (kept only as provenance for a known-wrong line-time row) | Teledyne Photometrics |
| `manual/Optical Tweezers/Manuals/` | Tweez 300 user manual, system installation guide, general hardware & safety, laser safety | Aresis — `support@aresis.com` |
| `manual/Piezo Stage/` | NPC-D controller interface library 2.7.9 + release note, NPC-D-6xx0 firmware release note, Nanobench 6000 user manual + release note, NanoFlash user manual + release note | Prior / Queensgate |
| `manual/DMD/` | Using Polygon1000 with Micro-Manager | Mightex |

`manual/README.md` stays, and records which revision is the one to cite and why.

## 3 · Proprietary DLLs — how to restore the hardware layer

```
hardware/piezo/vendor/controller_interface.dll     (32-bit)
hardware/piezo/vendor/controller_interface64.dll   (64-bit)
```

`hardware/piezo_stage.py` loads one of these by word size and cannot reach the
piezo controller without it. To restore:

1. Obtain the **NPC-D Digital Controller Interface DLL** production release from
   Prior/Queensgate. Version 2.7.9 is what the code in this repository was
   written and tested against.
2. Copy both DLLs out of the release — they sit under
   `controller_interface/bin/Windows/` (and are duplicated under
   `controller_interface/adapter/python/`) — into `hardware/piezo/vendor/`.
3. Nothing else changes. The filenames in
   [`hardware/piezo_stage.py`](hardware/piezo_stage.py) are the ones the release
   ships, and `hardware/piezo/vendor/dll_adapter.py` — which is kept, since it
   carries local modifications — already declares the entry points.

Everything the DLLs were *read* for is still here and needs no vendor file:
[`reference/npcd-command-set.md`](reference/npcd-command-set.md) is the command
set — and it no longer comes out of the binary at all. It was regenerated on
2026-08-27 by reading the live controller over COM4 (414 names at User level),
with the port, the firmware and the command that reproduces it recorded in its
header. The earlier 178 names pulled from the 64-bit DLL with `strings` were a
family-wide superset and are gone; what that swap corrected is in
[`kb/decisions/2026-08-29-device-discovery-scope.md`](kb/decisions/2026-08-29-device-discovery-scope.md).

`hardware/` is offline in this repository regardless — the working PC and the
microscope PC are separate, so these drivers produce recommendations, not
motion.

## 4 · Here, but not covered by the licence

[LICENSE](LICENSE) is MIT and covers this repository's own work — the lens
packages, the gates, the tests, `docs/`, `kb/`, `config/`. It does not cover the
three things below, which came from elsewhere and whose terms are somebody
else's to set. Their presence here grants no right over them.

| Path | Where it came from | What that means |
|---|---|---|
| `hardware/piezo/vendor/dll_adapter.py` | The Prior/Queensgate NPC-D Controller Interface release, `controller_interface/adapter/python/`, carrying local modifications | Vendor code. `.gitignore` ignores `hardware/*/vendor/*` and excepts exactly this one file, because `hardware/piezo_stage.py` imports it and the modifications are load-bearing (§3). For an unmodified original, obtain the release |
| `data/spectra/*.txt` | [FPbase](https://www.fpbase.org) CSV exports — FPbase's own data is CC-BY 4.0 — plus Semrock/IDEX and Chroma product-page ASCII downloads and Lumencor datasheets. Per-target provenance is tabulated in [`data/spectra/README.md`](data/spectra/README.md) | Third-party reference curves, used byte-exact and never renormalized (see `.gitattributes`). Re-obtain them from the source rather than taking them as MIT |
| `data/detectors.yaml`, `data/objectives.yaml`, `data/filters.yaml`, `data/light_sources.yaml`, `data/fluorophores.yaml` | Figures transcribed from manufacturer datasheets and catalogues, each with its source and revision named where it is used | The individual specifications are the manufacturers' published numbers. The selection, the schema and the commentary around them are this repository's |

**One file that belongs here and does not.**
[`reference/npcd-command-set.md`](reference/npcd-command-set.md) would have been
a fourth row until 2026-08-27, when it stopped being names pulled out of the
64-bit DLL with `strings` and became 414 names read off the live controller over
COM4 (§3). It is now this repository's own measurement of a device on the bench,
not vendor material passing through — which is a second thing that regeneration
bought, beyond correcting a family-wide superset down to what this controller
actually answers.

---

## Git history

The 19 paths were removed from every commit with `git filter-repo`, not just from
the tip. All 51 commits and their messages are intact; only these paths are gone,
so the commit SHAs differ from those of the repository this history was rewritten
out of.

Rewriting in place would not have been enough. GitHub keeps serving objects whose
refs are gone — a branch deleted from the original repository hours earlier was
still fetchable by SHA — and `refs/pull/1/head` survives both a branch deletion
and a force-push, which is exactly where one of the removed quotes remained
reachable. So the filtered history was pushed to a new repository and the
original was deleted, which is the only way those stop being served.

**What was exposed before that, measured rather than assumed.** The original
repository was public for seven days. At deletion it had 0 forks, 0 stars and 0
watchers; GitHub's traffic data recorded 2 clones and 1 unique visitor, all on
the day it was created, with no external referrer; and it was not in the Software
Heritage archive. That is consistent with nobody outside having fetched it, but
it is not proof of one — `raw.githubusercontent.com` requests do not appear in
clone counts, and the traffic window did not include the final day. Anyone with a
copy taken during those seven days still has it.
