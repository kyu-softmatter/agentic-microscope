"""One-shot snap: light on, grab a frame, save it as a viewable PNG, light off.

    python config/session/snap_preview.py

Meant to be re-run on demand (a manual "refresh"), not left looping -- keeps
light-on time bounded to just the snap itself.
"""
from hardware.microscope import Microscope
from pathlib import Path
import numpy as np
from PIL import Image
import time

CFG = Path(r"C:\agentic_microscope\config\micromanager\single_cam_red_noDMD.cfg")
OUT = Path(r"D:\data\preview\live_view.png")


def main():
    scope = Microscope.connect(CFG, allow_write=True, allow_motion=False)
    core = scope.core
    try:
        core.setProperty("Aura", "GREEN_Intensity", "80")
        core.setProperty("Aura", "GREEN", "1")
        core.setProperty("Aura", "State", "1")
        core.waitForDevice("Aura")
        time.sleep(0.2)

        core.setExposure(33.33)
        core.snapImage()
        frame = core.getImage().astype(np.float32)

        core.setProperty("Aura", "State", "0")

        lo, hi = np.percentile(frame, [1, 99.5])
        stretched = np.clip((frame - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix(".tmp.png")
        Image.fromarray(stretched).save(tmp)
        tmp.replace(OUT)
        print(f"saved -> {OUT}  (max={frame.max():.0f}, median={np.median(frame):.0f})")
    finally:
        scope.close()


if __name__ == "__main__":
    main()
