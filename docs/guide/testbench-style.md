<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Testbench project style

This is the recommended project layout, not a required class hierarchy. Put one
testbench family in `simulation/<name>/`, where `<name>` identifies an interface
or integration level.

```text
simulation/<name>/
  __init__.py
  config.py
  layout.py
  functional_model.py
  behavior_model.py
  scoreboard.py
  env.py
  test_pyuvm.py
  run_test.py
```

Omit a layer that adds no useful boundary. Add focused files such as
`sequences.py`, `registers.py` or `memory.py` when one existing file would
otherwise gain a second responsibility.

## Dependency direction

```text
run_test.py  -> config.py
test_pyuvm.py -> env.py -> scoreboard.py -> behavior_model.py
                              |                  |
                              +-> layout.py      +-> functional_model.py
                                      ^
                                  config.py
```

Lower layers must not import higher layers. In particular, a functional model
must not import cocotb, pyuvm, agents, a scoreboard or a DUT handle.

## File ownership

| File | Responsibility |
| --- | --- |
| `config.py` | Immutable serialisable input values, HDL parameter metadata, named cases and intrinsic validation. |
| `layout.py` | Immutable derived formats, masks, dimensions and numeric ranges. |
| `functional_model.py` | Pure domain-value transformations. |
| `behavior_model.py` | Registers, modes, history and reset-visible state. Optional for a genuinely stateless component. |
| `scoreboard.py` | Packet/transaction adaptation and expectation creation. |
| `env.py` | Buses, BFMs, agents, models, connections and task lifecycle. |
| `test_pyuvm.py` | Contract-focused scenarios and common test lifecycle. |
| `run_test.py` | DUT, simulator, sources and resolved configuration. |

## Configuration rule

Resolve the configuration once before compiling or generating the DUT. Pass HDL
fields through `to_parameters()` and the complete resolved object through the
runtime environment. Restore it in cocotb with `load_runtime_config(TestConfig)`.

Never create a fallback `TestConfig()` in the running testbench. A fallback can
make Python interpret a different layout from the compiled HDL.

## Lifecycle rule

The base test should assert an objection, reset the environment, run the
scenario, drain all expectations and stop background tasks in `finally`:

```python
async def run_phase(self):
    self.raise_objection()
    try:
        await self.env.reset()
        await self.body()
        await self.env.drain()
    finally:
        self.env.stop_tasks()
        self.drop_objection()
```

## Review checklist

- Configuration inputs and derived layout are not mixed.
- Pure models can run in ordinary Python tests.
- Stateful models have an explicit reset contract.
- A scoreboard adapts protocols but does not implement the algorithm.
- One independent output stream has one expectation queue.
- Register writes reach the model in monitor acceptance order.
- Every started clock, BFM and monitor is stopped after success or failure.
- Test names describe contracts: reset, boundaries, concurrency and timing.
- The runner contains no stimulus or expected-result calculation.

The complete repository example is described in the
[stream-pipeline tutorial](../tutorial/stream-pipeline.md).
