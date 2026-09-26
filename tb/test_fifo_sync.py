# Synchronous FIFO verification environment (pyuvm)
#
# Implements the test plan in docs/sync_fifo_testplan.md.
#
# Architecture (reference model outside of the scoreboard):
#
#   Sequence -> Sequencer -> Driver -> DUT
#                              |        |
#                              |     Monitor --+--------------------------+
#                              |               |                          |
#                              |          Predictor (SyncFifoRefModel)    |
#                              |               | expected                 | actual
#                              |               v                          v
#                              +---------> Scoreboard (comparator only) <-+
#                                              ^
#                                  Coverage <--+ (from Predictor)

import bisect
import logging
import random

import pyuvm
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, FallingEdge, ReadOnly
from cocotb.utils import get_sim_time
from pyuvm import *
from tabulate import tabulate

from sync_fifo_ref_model import SyncFifoRefModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('log_sync_fifo.txt')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)


def to_int(value):
    """Convert a sampled DUT value to int, None if it contains X/Z."""
    return int(value) if value.is_resolvable else None


class SyncFifoItem(uvm_sequence_item):
    def __init__(self, name, data=0, wr_en=0, rd_en=0, reset_n=1):
        super().__init__(name)
        self.data = data
        self.wr_en = wr_en
        self.rd_en = rd_en
        self.reset_n = reset_n

    def __str__(self):
        return (f"{self.get_name()} reset_n={self.reset_n} wr_en={self.wr_en} "
                f"rd_en={self.rd_en} data={self.data}")


class SyncFifoDriver(uvm_driver):
    def build_phase(self):
        self.dut = cocotb.top
        self.ap = uvm_analysis_port("ap", self)

    async def run_phase(self):
        clock_setup_time = int(.5 + (ConfigDB().get(self, "", "CLOCK_PERIOD") *
                                     (1 - ConfigDB().get(self, "", "CLOCK_SETUP"))))
        while True:
            seq_item = await self.seq_item_port.get_next_item()
            logger.debug(f"SyncFifoDriver received {seq_item}")
            # Drive after the edge so the inputs are stable at the next edge
            await RisingEdge(self.dut.clk)
            await Timer(clock_setup_time, unit='ns')
            self.dut.data_in.value = seq_item.data
            self.dut.wr_en.value = seq_item.wr_en
            self.dut.rd_en.value = seq_item.rd_en
            self.dut.reset_n.value = seq_item.reset_n
            self.ap.write({"sim_time_ns": get_sim_time(unit="ns"),
                           "seq_name": seq_item.get_name()})
            self.seq_item_port.item_done()


class SyncFifoMonitor(uvm_monitor):
    """Samples the DUT once per rising edge.

    At ReadOnly after edge N the inputs are those sampled by edge N (the driver
    changes them later in the cycle) and the outputs are the result of edge N.
    """
    def build_phase(self):
        self.dut = cocotb.top
        self.ap = uvm_analysis_port("ap", self)

    async def run_phase(self):
        while True:
            await RisingEdge(self.dut.clk)
            await ReadOnly()
            self.ap.write({
                "sim_time_ns": get_sim_time(unit="ns"),
                "reset_n": to_int(self.dut.reset_n.value),
                "wr_en": to_int(self.dut.wr_en.value),
                "rd_en": to_int(self.dut.rd_en.value),
                "data_in": to_int(self.dut.data_in.value),
                "data_out": to_int(self.dut.data_out.value),
                "full": to_int(self.dut.full.value),
                "empty": to_int(self.dut.empty.value),
            })


class SyncFifoPredictor(uvm_subscriber):
    """Hosts the out-of-scoreboard reference model and publishes expected outputs."""
    def build_phase(self):
        self.ap = uvm_analysis_port("ap", self)
        self.model = SyncFifoRefModel(depth=ConfigDB().get(self, "", "FIFO_DEPTH"),
                                      width=ConfigDB().get(self, "", "FIFO_WIDTH"))

    def write(self, txn):
        expected = self.model.step(txn["reset_n"] == 1, txn["wr_en"] == 1, txn["rd_en"] == 1,
                                   txn["data_in"] or 0)
        expected.update({key: txn[key] for key in ("sim_time_ns", "reset_n", "wr_en", "rd_en", "data_in")})
        self.ap.write(expected)


class SyncFifoCoverage(uvm_subscriber):
    """Functional coverage collected on the predictor output (pre-edge state + inputs)."""
    def build_phase(self):
        self.depth = ConfigDB().get(self, "", "FIFO_DEPTH")
        self.bins = {
            "TP01 reset asserted": 0,
            "TP02 write accepted": 0,
            "TP02 read accepted": 0,
            "TP02 full reached": 0,
            "TP02 empty after drain": 0,
            "TP03 write when full": 0,
            "TP04 read when empty": 0,
            "TP05 rw when empty": 0,
            "TP05 rw when partial": 0,
            "TP05 rw when full": 0,
            "TP06 write pointer wrap": 0,
            "TP06 read pointer wrap": 0,
            "TP07 reset when not empty": 0,
            "TP08 rw when empty at last slot": 0,
        }
        self.level_hist = [0] * (self.depth + 1)

    def write(self, exp):
        count = exp["pre_count"]
        if exp["reset_n"] != 1:
            self.bins["TP01 reset asserted"] += 1
            if count > 0:
                self.bins["TP07 reset when not empty"] += 1
            return
        self.level_hist[count] += 1
        wr, rd = exp["wr_en"] == 1, exp["rd_en"] == 1
        if exp["write_accepted"]:
            self.bins["TP02 write accepted"] += 1
            if exp["pre_wr_ptr"] == self.depth - 1:
                self.bins["TP06 write pointer wrap"] += 1
        if exp["read_accepted"]:
            self.bins["TP02 read accepted"] += 1
            if exp["pre_rd_ptr"] == self.depth - 1:
                self.bins["TP06 read pointer wrap"] += 1
        if exp["full"] and count < self.depth:
            self.bins["TP02 full reached"] += 1
        if exp["empty"] and count > 0:
            self.bins["TP02 empty after drain"] += 1
        if wr and count == self.depth:
            self.bins["TP03 write when full"] += 1
        if rd and count == 0:
            self.bins["TP04 read when empty"] += 1
        if wr and rd:
            if count == 0:
                self.bins["TP05 rw when empty"] += 1
                if exp["pre_wr_ptr"] == self.depth - 1:
                    self.bins["TP08 rw when empty at last slot"] += 1
            elif count == self.depth:
                self.bins["TP05 rw when full"] += 1
            else:
                self.bins["TP05 rw when partial"] += 1

    def holes(self):
        return [name for name, hits in self.bins.items() if hits == 0]

    def report_phase(self):
        print("Functional Coverage Report:")
        print(tabulate([[name, hits] for name, hits in self.bins.items()],
                       headers=["bin", "hits"], tablefmt="grid"))
        print(tabulate([[level, hits] for level, hits in enumerate(self.level_hist)],
                       headers=["fill level", "cycles"], tablefmt="grid"))
        hit = len(self.bins) - len(self.holes())
        print(f"Coverage: {hit}/{len(self.bins)} bins hit ({100.0 * hit / len(self.bins):.1f}%)")
        if self.holes():
            # Directed tests only target part of the plan; the random test is expected to close all bins
            self.logger.info(f"Coverage holes: {', '.join(self.holes())}")


class SyncFifoScoreboard(uvm_scoreboard):
    """Comparator only: pairs expected (predictor) with actual (monitor) per cycle."""
    def build_phase(self):
        self.expected_fifo = uvm_tlm_analysis_fifo("expected_fifo", self)
        self.actual_fifo = uvm_tlm_analysis_fifo("actual_fifo", self)
        self.driver_fifo = uvm_tlm_analysis_fifo("driver_fifo", self)
        self.expected_get_port = uvm_get_port("expected_get_port", self)
        self.actual_get_port = uvm_get_port("actual_get_port", self)
        self.driver_get_port = uvm_get_port("driver_get_port", self)
        self.expected_export = self.expected_fifo.analysis_export
        self.actual_export = self.actual_fifo.analysis_export
        self.driver_export = self.driver_fifo.analysis_export
        self.driver_info = []
        self.result_table = []
        self.checks = 0

    def connect_phase(self):
        self.expected_get_port.connect(self.expected_fifo.get_export)
        self.actual_get_port.connect(self.actual_fifo.get_export)
        self.driver_get_port.connect(self.driver_fifo.get_export)

    def seq_name_at(self, sim_time_ns):
        index = bisect.bisect_left(self.driver_info, sim_time_ns, key=lambda entry: entry["sim_time_ns"])
        return "" if index == 0 else self.driver_info[index - 1]["seq_name"]

    def check_phase(self):
        while self.driver_get_port.can_get():
            _, driver_data = self.driver_get_port.try_get()
            self.driver_info.append(driver_data)

        reset_seen = False
        while self.actual_get_port.can_get():
            _, actual = self.actual_get_port.try_get()
            _, expected = self.expected_get_port.try_get()
            # Nothing is predictable before the first reset
            reset_seen = reset_seen or actual["reset_n"] == 0
            if not reset_seen:
                continue
            seq_name = self.seq_name_at(actual["sim_time_ns"])
            for signal in ("data_out", "full", "empty"):
                self.checks += 1
                match = actual[signal] == expected[signal]
                if not match or expected["read_accepted"] and signal == "data_out":
                    self.result_table.append([seq_name, actual["sim_time_ns"], signal, expected["count"],
                                              expected[signal], actual[signal], "PASS" if match else "FAIL"])
                if not match:
                    self.logger.error(f"Mismatch at {actual['sim_time_ns']} ns (seq_name={seq_name}) "
                                      f"{signal}: expected {expected[signal]}, observed {actual[signal]}")
        assert not self.expected_get_port.can_get(), "Expected and actual streams are out of step"

    def report_phase(self):
        print(tabulate(self.result_table,
                       headers=["seq_name", "sim_time_ns", "signal", "model_count", "Expected", "Observed", "Match"],
                       tablefmt="grid"))
        failures = sum(1 for row in self.result_table if row[-1] == "FAIL")
        print(f"Scoreboard: {self.checks} checks, {failures} mismatches")
        assert failures == 0, f"Scoreboard found {failures} mismatches"


class SyncFifoSequencer(uvm_sequencer):
    pass


class SyncFifoEnv(uvm_env):
    def build_phase(self):
        dut = cocotb.top
        ConfigDB().set(None, "*", "FIFO_DEPTH", int(dut.DEPTH.value))
        ConfigDB().set(None, "*", "FIFO_WIDTH", len(dut.data_in))
        self.seqr = SyncFifoSequencer("seqr", self)
        self.driver = SyncFifoDriver("driver", self)
        self.monitor = SyncFifoMonitor("monitor", self)
        self.predictor = SyncFifoPredictor("predictor", self)
        self.scoreboard = SyncFifoScoreboard("scoreboard", self)
        self.coverage = SyncFifoCoverage("coverage", self)

    def connect_phase(self):
        self.driver.seq_item_port.connect(self.seqr.seq_item_export)
        self.driver.ap.connect(self.scoreboard.driver_export)
        self.monitor.ap.connect(self.predictor.analysis_export)
        self.monitor.ap.connect(self.scoreboard.actual_export)
        self.predictor.ap.connect(self.scoreboard.expected_export)
        self.predictor.ap.connect(self.coverage.analysis_export)


# Sequences

class SyncFifoBaseSequence(uvm_sequence):
    def __init__(self, name="sync_fifo_seq"):
        super().__init__(name)
        self.depth = ConfigDB().get(None, "", "FIFO_DEPTH")
        self.max_data = (1 << ConfigDB().get(None, "", "FIFO_WIDTH")) - 1
        self.reset_length = 3
        self.pause_length = 3
        self.index = 0

    async def send(self, name, wr_en=0, rd_en=0, reset_n=1, data=None):
        if data is None:
            data = self.index & self.max_data
        item = SyncFifoItem(name, data=data, wr_en=wr_en, rd_en=rd_en, reset_n=reset_n)
        await self.start_item(item)
        await self.finish_item(item)
        self.index += 1

    async def reset(self, name="reset"):
        for _ in range(self.reset_length):
            await self.send(name, reset_n=0)

    async def idle(self, name="idle", cycles=None):
        for _ in range(self.pause_length if cycles is None else cycles):
            await self.send(name)

    async def write(self, name, count):
        for _ in range(count):
            await self.send(name, wr_en=1)

    async def read(self, name, count):
        for _ in range(count):
            await self.send(name, rd_en=1)

    async def read_write(self, name, count):
        for _ in range(count):
            await self.send(name, wr_en=1, rd_en=1)


class ResetSequence(SyncFifoBaseSequence):
    """TP01: reset values and reset released into an idle FIFO."""
    async def body(self):
        await self.reset()
        await self.idle("idle_after_reset")


class FillDrainSequence(SyncFifoBaseSequence):
    """TP02: fill to full, drain to empty, data comes out in order."""
    async def body(self):
        await self.reset()
        await self.write("fill", self.depth)
        await self.idle("hold_full")
        await self.read("drain", self.depth)
        await self.idle("hold_empty")


class OverflowSequence(SyncFifoBaseSequence):
    """TP03: writes on a full FIFO are dropped and do not corrupt stored data."""
    async def body(self):
        await self.reset()
        await self.write("fill", self.depth)
        await self.write("overflow_write", self.depth // 2)
        await self.read("drain", self.depth)
        await self.idle()


class UnderflowSequence(SyncFifoBaseSequence):
    """TP04: reads on an empty FIFO are ignored and data_out holds its value."""
    async def body(self):
        await self.reset()
        await self.read("read_after_reset", 2)
        await self.write("write", 2)
        await self.read("drain", 2)
        await self.read("underflow_read", self.depth // 2)
        await self.idle()


class SimultaneousRWSequence(SyncFifoBaseSequence):
    """TP05: simultaneous read and write when empty, partially full and full."""
    async def body(self):
        await self.reset()
        await self.read_write("rw_empty", 2)
        await self.idle()
        await self.write("fill_half", self.depth // 2)
        await self.read_write("rw_partial", self.depth)
        await self.write("fill_rest", self.depth)
        await self.read_write("rw_full", 2)
        await self.read("drain", self.depth)
        await self.idle()


class WrapAroundSequence(SyncFifoBaseSequence):
    """TP06: pointers wrap several times while the FIFO keeps a steady level."""
    async def body(self):
        await self.reset()
        for lap in range(3):
            await self.write(f"lap{lap}_write", self.depth - 1)
            await self.read(f"lap{lap}_read", self.depth - 1)
        await self.write("fill", self.depth)
        await self.read("drain", self.depth)
        await self.idle()


class ResetMidOperationSequence(SyncFifoBaseSequence):
    """TP07: reset while partially full and while full clears contents."""
    async def body(self):
        await self.reset()
        await self.write("fill_half", self.depth // 2)
        await self.reset("reset_half_full")
        await self.read("read_after_reset", 2)
        await self.write("fill", self.depth)
        await self.reset("reset_full")
        await self.write("write_after_reset", 1)
        await self.read("read_after_reset", 2)
        await self.idle()


class SimultaneousRWLastSlotSequence(SyncFifoBaseSequence):
    """TP08: simultaneous read/write on an empty FIFO with pointers at DEPTH-1."""
    async def body(self):
        await self.reset()
        await self.write("advance_ptrs", self.depth - 1)
        await self.read("advance_ptrs", self.depth - 1)
        await self.read_write("rw_empty_last_slot", 1)
        await self.write("fill", self.depth - 1)
        await self.idle("check_full")
        await self.read("drain", self.depth)
        await self.idle()


class RandomSequence(SyncFifoBaseSequence):
    """TP09: constrained random traffic with occasional reset."""
    def __init__(self, name="random_seq"):
        super().__init__(name)
        self.cycles = 1000

    async def body(self):
        await self.reset()
        # Bias the traffic in phases so the FIFO spends time near full and empty
        for cycle in range(self.cycles):
            phase = (cycle // (4 * self.depth)) % 3
            wr_weight = (0.8, 0.2, 0.5)[phase]
            if random.random() < 0.005:
                await self.reset("random_reset")
                continue
            await self.send(f"random_p{phase}",
                            wr_en=int(random.random() < wr_weight),
                            rd_en=int(random.random() < 1 - wr_weight),
                            data=random.randint(0, self.max_data))
        await self.read("final_drain", self.depth + 1)
        await self.idle()


# Tests

class SyncFifoBaseTest(uvm_test):
    sequence_class = ResetSequence

    def build_phase(self):
        ConfigDB().set(None, "*", "CLOCK_PERIOD", 10)  # Period in nanosecond
        ConfigDB().set(None, "*", "CLOCK_SETUP", 0.8)  # Set up % before rising edge
        self.env = SyncFifoEnv("env", self)

    async def run_phase(self):
        self.raise_objection()
        clock = Clock(cocotb.top.clk, ConfigDB().get(self, "", "CLOCK_PERIOD"), unit="ns")
        cocotb.start_soon(clock.start())
        await FallingEdge(cocotb.top.clk)
        sequence = self.sequence_class.create(self.sequence_class.__name__)
        await sequence.start(self.env.seqr)
        # Let the monitor sample the effect of the last driven item
        for _ in range(2):
            await RisingEdge(cocotb.top.clk)
        self.drop_objection()


@pyuvm.test()
class SyncFifoResetTest(SyncFifoBaseTest):
    sequence_class = ResetSequence


@pyuvm.test()
class SyncFifoFillDrainTest(SyncFifoBaseTest):
    sequence_class = FillDrainSequence


@pyuvm.test()
class SyncFifoOverflowTest(SyncFifoBaseTest):
    sequence_class = OverflowSequence


@pyuvm.test()
class SyncFifoUnderflowTest(SyncFifoBaseTest):
    sequence_class = UnderflowSequence


@pyuvm.test()
class SyncFifoSimultaneousRWTest(SyncFifoBaseTest):
    sequence_class = SimultaneousRWSequence


@pyuvm.test()
class SyncFifoWrapAroundTest(SyncFifoBaseTest):
    sequence_class = WrapAroundSequence


@pyuvm.test()
class SyncFifoResetMidOperationTest(SyncFifoBaseTest):
    sequence_class = ResetMidOperationSequence


@pyuvm.test()
class SyncFifoSimultaneousRWLastSlotTest(SyncFifoBaseTest):
    sequence_class = SimultaneousRWLastSlotSequence


@pyuvm.test()
class SyncFifoRandomTest(SyncFifoBaseTest):
    sequence_class = RandomSequence
