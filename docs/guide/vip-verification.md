<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# VIP verification

An agent moves packets; a behavior model predicts the IP; a scoreboard checks
the ordered result. Keeping these jobs separate is the central verification
pattern used by the library.

`VIPSequence` sends `VIPItem` objects through an active `VIPAgent`. Source and
sink monitors publish decoded packets through pyuvm analysis ports. A custom
scoreboard consumes those packets and queues `PacketExpectation` objects for
`BaseVIPScoreboard`.

```python
class MyIPScoreboard(BaseVIPScoreboard):
    def __init__(self, name, parent, source_fmt, sink_fmt, model, **kwargs):
        super().__init__(
            name, parent, source_fmt, sink_fmt, **kwargs
        )
        self.model = model

    def process_input_packet(self, packet):
        result = self.model.transform(packet)
        self.add_expectation(PacketExpectation(result))

    def process_control_transaction(self, transaction):
        self.model.apply_control(transaction)

    def on_reset(self):
        self.model.reset()
```

The example method names are intentionally project-specific. A stateful model
usually benefits from narrower typed operations instead of a universal packet
method.

`CheckMode.EXACT` compares complete decoded content. `CheckMode.SHAPE` checks
packet type and observable geometry when content is intentionally undefined.
It is an explicit expectation, not a skipped check. User-packet handling is
also explicit through `UserPacketPolicy`.

At the end of a test, `drain()` waits for pending expectations, reports sticky
failures, and optionally observes a quiet output window. One independent VIP
path should have one `BaseVIPScoreboard` instance so its control context,
expectation queue, and frame counters stay isolated.

See the
[VIP verification notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/09_vip_verification_components.ipynb)
for connection and lifecycle examples.

Next: [measure stream performance](performance.md).
