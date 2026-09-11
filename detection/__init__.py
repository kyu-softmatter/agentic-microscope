"""The detection lens: committee member #2 (docs/05-consensus-gate.md §5).

Owns exposure, binning, ROI, readout mode, gain, bit depth, frame interval,
trigger. Gates L2.1 (sampling), L2.2 (saturation), L2.3 (SNR), L2.4 (motion blur),
L2.5 (frame-rate realizability) -- docs/04-decision-engine.md §2, §4, §5.

``gate`` grades settings you already chose; ``recommend`` runs it backwards,
turning one measured test frame into a mode and an exposure.
"""
