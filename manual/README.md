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
