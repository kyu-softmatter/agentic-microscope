"""The compute-resource lens: committee member #3 (docs/05-consensus-gate.md §5).

Owns data rate, circular buffer, storage capacity, real-time processing,
CPU/RAM. Gates L3.1 (disk budget), L3.2 (frame-rate provenance), L3.3 (pixel
container), L3.4 (buffer), L3.5 (capacity), L3.6 (real-time CPU) and L3.7
(RAM-capture capacity) -- addressed 2026-09-11, previously G12a-c and G13a-d,
whose letter suffixes the address scheme absorbed. docs/04-decision-engine.md
§8.

The only lens that catches silent failure: frame drops raise no error, only
irregular ``ElapsedTime-ms`` intervals after the fact (docs/06-pitfalls.md
§C4-C5). ``compute.gate`` refuses a proposal that would cause them;
``compute.drops`` reads an acquisition that already happened and says
whether it did.
"""
