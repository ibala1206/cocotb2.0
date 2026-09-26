# Synchronous FIFO Test Plan

DUT: `rtl/fifo1.sv` (single clock `clk`, `clk_rd` unused), `DEPTH = 8`, 7-bit data,
asynchronous active-low reset `reset_n`, registered `data_out`, combinational `full` / `empty`.

Testbench: `tb/test_fifo_sync.py` (pyuvm) + `tb/sync_fifo_ref_model.py` (reference model).

Run all tests:

```
make COCOTB_TEST_MODULES=test_fifo_sync
```

Run one test:

```
make COCOTB_TEST_MODULES=test_fifo_sync COCOTB_TEST_FILTER=SyncFifoOverflowTest
```

## 1. Features under verification

| ID  | Feature                         | Specification                                                                   |
|-----|---------------------------------|---------------------------------------------------------------------------------|
| F1  | Reset                           | `reset_n = 0` empties the FIFO: `empty=1`, `full=0`, `data_out=0`               |
| F2  | Write                           | `wr_en=1` and not full stores `data_in` at the tail                             |
| F3  | Read                            | `rd_en=1` and not empty moves the head to `data_out` on the next edge           |
| F4  | Ordering                        | Data leaves in the same order it was written (first in, first out)              |
| F5  | Full flag                       | `full=1` exactly when DEPTH entries are stored                                  |
| F6  | Empty flag                      | `empty=1` exactly when no entries are stored                                    |
| F7  | Overflow protection             | A write on a full FIFO is dropped; stored data is unchanged                     |
| F8  | Underflow protection            | A read on an empty FIFO is ignored; `data_out` holds its previous value         |
| F9  | Simultaneous read/write         | Both are judged on the state before the edge; count is unchanged when both pass |
| F10 | Pointer wrap-around             | Correct behavior across repeated wrap of the read and write pointers            |

## 2. Verification architecture

```
 Sequence -> Sequencer -> Driver ----------------------------> DUT
                            | (seq_name, time)                  |
                            v                                Monitor (1 txn per rising edge)
                        Scoreboard  <-- actual ----------------+|
                        (comparator)                            |
                            ^                                   v
                            +------ expected ------------ Predictor --> Coverage
                                                        (SyncFifoRefModel)
```

* **Reference model outside the scoreboard.** `SyncFifoRefModel` is a plain-Python,
  cycle-based model with no pyuvm or cocotb dependency. It is hosted by `SyncFifoPredictor`,
  which turns every monitored cycle into an expected transaction. The scoreboard only
  compares; it has no knowledge of FIFO behavior. The model can be unit-tested on its own
  (`python tb/sync_fifo_ref_model.py`) or swapped out without touching the scoreboard.
* **Driver** applies inputs `CLOCK_PERIOD * (1 - CLOCK_SETUP)` = 2 ns after the rising edge,
  so they are stable at the next edge (same scheme as `test_fifo_sync_async.py`).
* **Monitor** samples at `ReadOnly` after every rising edge: the inputs sampled by that
  edge plus the resulting outputs.
* **Scoreboard** checks `data_out`, `full` and `empty` on every cycle after the first reset,
  prints a table of all reads and mismatches, and fails the test on any mismatch.
* **Coverage** is collected on the predictor output (inputs + model state before the edge).

## 3. Test cases

| TP   | Test class                            | Features   | Stimulus                                                                                 | Checks / expected result                                                        |
|------|---------------------------------------|------------|------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| TP01 | `SyncFifoResetTest`                   | F1         | 3 reset cycles, then idle                                                                | `empty=1`, `full=0`, `data_out=0` during and after reset                        |
| TP02 | `SyncFifoFillDrainTest`               | F2–F6      | Reset, write DEPTH, idle, read DEPTH, idle                                               | `full` after the DEPTHth write, data read in order, `empty` after the last read |
| TP03 | `SyncFifoOverflowTest`                | F5, F7     | Fill, write DEPTH/2 more, drain                                                          | Extra writes dropped, drained data is the first DEPTH values                    |
| TP04 | `SyncFifoUnderflowTest`               | F6, F8     | Read after reset, write 2, read 2, read DEPTH/2 more                                     | `empty` stays 1, `data_out` holds the last valid value                          |
| TP05 | `SyncFifoSimultaneousRWTest`          | F9         | Read+write together when empty, half full and full                                       | Empty: write only. Partial: both, level unchanged. Full: read only              |
| TP06 | `SyncFifoWrapAroundTest`              | F4, F10    | 3 laps of write DEPTH-1 / read DEPTH-1, then fill and drain                              | Order and flags correct across several pointer wraps                            |
| TP07 | `SyncFifoResetMidOperationTest`       | F1         | Reset while half full and while full, then read and write                                | Contents lost, reads after reset ignored, new writes work                       |
| TP08 | `SyncFifoSimultaneousRWLastSlotTest`  | F5, F6, F9 | Move both pointers to DEPTH-1 while empty, read+write together, then write DEPTH-1 more | FIFO reports `full=1` with DEPTH entries and drains them in order               |
| TP09 | `SyncFifoRandomTest`                  | All        | 1000 random cycles, write-heavy / read-heavy / balanced phases, random data, ~0.5 % resets | No mismatches; all coverage bins hit                                            |

## 4. Functional coverage

| Bin                              | Plan item |
|----------------------------------|-----------|
| reset asserted                   | TP01      |
| write accepted / read accepted   | TP02      |
| full reached / empty after drain | TP02      |
| write when full                  | TP03      |
| read when empty                  | TP04      |
| rw when empty / partial / full   | TP05      |
| write / read pointer wrap        | TP06      |
| reset when not empty             | TP07      |
| rw when empty at last slot       | TP08      |
| fill-level histogram 0..DEPTH    | all       |

Pass criterion: every test passes with zero mismatches, and `SyncFifoRandomTest` reaches
100 % bin coverage.

## 5. Assumptions and known issues

* `DEPTH` must be 8: `wr_ptr` / `rd_ptr` are 3 bits and wrap without a modulo.
* **Known RTL bug, found by TP08.** In `fifo1.sv` the `flag_full_empty` clear condition
  `(rd_ptr == DEPTH-1) && rd_en` does not check `!empty`. When the FIFO is empty with both
  pointers at DEPTH-1 and `wr_en` and `rd_en` are high together, the write is accepted and
  should set the flag, but the blocked read clears it (the later non-blocking assignment wins).
  After DEPTH-1 more writes the FIFO holds DEPTH entries but reports `empty=1, full=0`, and
  the stored data can no longer be read. A possible fix is to qualify both flag updates with
  the real accept conditions: `wr_en && !full` for set, `rd_en && !empty` for clear.
  TP09 hits this corner (coverage bin) but does not always follow it with enough writes to
  expose the bug, which is why TP08 is a directed test.
