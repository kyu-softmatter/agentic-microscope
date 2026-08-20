"""The compute-resource lens: committee member #3 (docs/05-consensus-gate.md §5).

Owns data rate, circular buffer, storage capacity, real-time processing,
CPU/RAM. Gates G12 (data rate: G12a disk budget, G12b frame-rate
provenance, G12c pixel container) and G13 (G13a buffer, G13b capacity,
G13c real-time CPU, G13d RAM-capture capacity) -- docs/04-decision-engine.md
§8.

The only lens that catches silent failure: frame drops raise no error, only
irregular ``ElapsedTime-ms`` intervals after the fact (docs/06-pitfalls.md
§C4-C5). ``compute.gate`` refuses a proposal that would cause them;
``compute.drops`` reads an acquisition that already happened and says
whether it did.
"""
