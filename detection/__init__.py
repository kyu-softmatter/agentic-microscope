"""The detection lens: committee member #2 (docs/05-consensus-gate.md §5).

Owns exposure, binning, ROI, readout mode, gain, bit depth, frame interval,
trigger. Gates G5 (sampling), G6 (saturation), G7 (SNR), G8 (motion blur),
G9 (frame-rate realizability) -- docs/04-decision-engine.md §2, §4, §5.

``gate`` grades settings you already chose; ``recommend`` runs it backwards,
turning one measured test frame into a mode and an exposure.
"""
