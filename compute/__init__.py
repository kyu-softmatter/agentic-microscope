"""The compute-resource lens: committee member #3 (docs/05-consensus-gate.md §5).

Owns data rate, circular buffer, storage capacity, real-time processing,
CPU/RAM. Gates G12 (data rate), G13 (buffer / capacity / real-time CPU) --
docs/04-decision-engine.md §8. The only lens that catches silent failure:
frame drops raise no error, only irregular ``ElapsedTime-ms`` intervals
after the fact (docs/06-pitfalls.md §C4-C5).
"""
