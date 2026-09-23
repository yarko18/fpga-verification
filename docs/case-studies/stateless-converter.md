<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Stateless stream converter

Consider a component that converts between two stream layouts. Depending on its
parameters it may group several narrow words into one wide word, split a wide
word, extend a word with zeroes, or retain only its low bits. The component has
no registers and retains no state between packets.

## Verification shape

`TestConfig` contains the input width, output width and conversion mode. An
immutable layout derives both `VideoFormat` objects, the conversion ratio and
whether the component uses a direct one-beat path or a packet-aware path.

The pure functional model owns three transformations:

- control geometry, when grouping or splitting changes the number of samples;
- user payload padding at a physical beat boundary;
- video payload word grouping, splitting or width adaptation.

The behavior model may be omitted for a small project. Keeping a thin stateless
behavior object is also reasonable when all testbenches follow one lifecycle;
its `reset()` then documents that no state survives or changes.

## Scoreboard contract

The custom scoreboard creates one expectation for each input packet:

```text
control -> transformed geometry
user    -> transformed payload and final-beat padding
video   -> transformed video payload
```

All expectations remain in one FIFO because these packet types share one output
stream. Test them independently first, then send a combined ordered sequence.

## Performance with different beat counts

A layout converter can accept and produce different physical beat counts for
the same logical packet. The generic `PacketObservation.beats` field represents
one count and therefore cannot describe both sides at once.

Measure the input and output sides separately, then combine their packet or
sequence metrics. Report the conversion ratio explicitly:

```text
beat conversion ratio = output beats / input beats
```

Throughput assertions should be stated in one chosen domain. For example,
convert output efficiency back to input-equivalent efficiency before computing
the required clock multiplier.

## Useful scenarios

- every supported conversion mode and ratio;
- a payload ending on a partial physical beat;
- control, user and video packets in one stream;
- randomized ready/valid timing;
- continuous packets on direct and packet-aware paths;
- reset between packet boundaries.
