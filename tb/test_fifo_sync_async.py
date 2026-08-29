#import random
#from nacl.utils import random


import bisect
import logging
logger = logging.getLogger(__name__)
import pyuvm
from cocotb.types import LogicArray
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, FallingEdge, ReadOnly
from pyuvm import *
from tabulate import tabulate
from cocotb.utils import get_sim_time
from fifo_model_simple_version import FIFOModel

import sys
print("Python executable:", sys.executable)
print("Python path:", sys.path)

# Not sure to understand this command
logging.getLogger("pyuvm").setLevel(logging.DEBUG)

# Set the logging level (optional, default is WARNING)
logger.setLevel(logging.INFO)

# Create a file handler to write logs to a file
file_handler = logging.FileHandler('log_fifo_file.txt')

# Create a formatter for the log messages
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Attach the formatter to the file handler
file_handler.setFormatter(formatter)

# Add the file handler to PyUVM's logger
logger.addHandler(file_handler)

# Let discuss this and the connect port not sure what they do
class FifoCoverage(uvm_subscriber):
    def __init__(self, name, parent):
        super().__init__(name, parent)
        self.coverage = {
            "write": 0,
            "read": 0,
            "full": 0,
            "empty_0": 0,
            "empty_1": 0

        }
    def write(self, coverage_signals):
        if coverage_signals["wr_en"]:
            self.coverage["write"] += 1
        if coverage_signals["rd_en"]:
            self.coverage["read"] += 1
        if coverage_signals["full"]:
            self.coverage["full"] += 1
        if str(coverage_signals["empty"]) == '0':
            self.coverage["empty_0"] += 1
        elif str(coverage_signals["empty"]) == "1":
            self.coverage["empty_1"] += 1
        else :
            print(f"The value of not empty is : {type(coverage_signals['empty'])} {coverage_signals['empty']}")

    def report_phase(self):
        print("Functional Coverage Report:")
        for key, value in self.coverage.items():
            print(f"{key}: {value}")

class FifoSequenceItem(uvm_sequence_item):
    def __init__(self, name, index, rd_en = 0, wr_en = 0, reset_n = 1) -> None:
        super().__init__(name)
        self.index = index
        self.write_data = index
        self.rd_en = rd_en
        self.wr_en = wr_en
        self.reset_n = reset_n

    def __str__(self):
        return f'{self.get_name()} {self.index}:{self.write_data}'


class FifoDriver(uvm_driver):
    def __init__(self, name = 'fifo', parent=None):
        super().__init__(name, parent)
        self.dut = None
        self.command = None
        self.stop_requested = False
        self.ap = None

    def build_phase(self):
        self.ap = uvm_analysis_port("ap", self)

    async def run_phase(self):
        # self.raise_objection()

        clock_setup_time = int(.5+(ConfigDB().get(self, "", "CLOCK_PERIOD") *
                            (1 - ConfigDB().get(self, "", "CLOCK_SETUP"))))
        while not self.stop_requested:
            seq_item = await self.seq_item_port.get_next_item()
            logger.debug(f"FifoDriver received Item {seq_item}")

            await RisingEdge(self.dut.clk) # Settings the signals to respect the set up and hold of the Flip Flop
            await Timer(clock_setup_time, unit='ns')
            self.dut.data_in.value = seq_item.write_data
            self.dut.wr_en.value = seq_item.wr_en
            self.dut.reset_n.value = seq_item.reset_n
            self.dut.rd_en.value = seq_item.rd_en
            signals_driven = dict()
            signals_driven["data_in"] = LogicArray.from_unsigned(seq_item.write_data,len(self.dut.data_in))
            signals_driven["sim_time_ns"] = get_sim_time(unit="ns")
            signals_driven["seq_name"] = seq_item.get_name()
            signals_driven["reset_n"] = seq_item.reset_n
            self.ap.write(signals_driven)  # Not used currently

            self.seq_item_port.item_done()
    def stop(self):

        self.stop_requested = True

class FifoMonitor(uvm_monitor):
    def __init__(self, name = 'fifo', parent=None, dut=None, cycles_to_monitor=100):
        super().__init__(name, parent)
        self.dut = dut
        self.cycles_to_monitor = cycles_to_monitor
        self.ap = uvm_analysis_port("ap", self)


    async def run_phase(self):
        self.raise_objection()
        for i in range(self.cycles_to_monitor):
            signals_monitored = dict()
            await RisingEdge(self.dut.clk)
            signals_monitored["rd_ptr"] = self.dut.rd_ptr.value

            await ReadOnly()   # After the simulated signals have settled for this time steps

            signals_monitored["sim_time_ns"] = get_sim_time(unit="ns")
            signals_monitored["reset_n"] = self.dut.reset_n.value
            signals_monitored["rd_en"] = self.dut.rd_en.value
            signals_monitored["wr_ptr"] = self.dut.wr_ptr.value
            signals_monitored["wr_en"] = self.dut.wr_en.value
            signals_monitored["data_out"] = self.dut.data_out.value
            signals_monitored["full"] = self.dut.full.value
            signals_monitored["empty"] = self.dut.empty.value
            signals_monitored["data_in"] = self.dut.data_in.value
    # Working on the internal signal
            signals_monitored["flag_full_empty"] = self.dut.flag_full_empty.value

            self.ap.write(signals_monitored)  # Send observed data to the connected scoreboard
        self.drop_objection()

#
class FifoScoreboard(uvm_scoreboard):
    def __init__(self, name = 'fifo', parent=None, dut=None):
        super().__init__(name, parent)
        self.dut = dut
        self.name = name
        self.result_table = []
        self.driver_info  = []
        self.result_fifo = uvm_tlm_analysis_fifo("result_fifo", self)
        self.result_get_port = uvm_get_port("result_get_port", self)
        self.result_export = self.result_fifo.analysis_export # connected to the Monitor

        self.driver_fifo = uvm_tlm_analysis_fifo("driver_fifo", self)
        self.driver_get_port = uvm_get_port("driver_get_port", self)
        self.driver_export = self.driver_fifo.analysis_export # connected to the Driver

        self.fifo_model = None

    def add_result(self, expected, observed, description="", mem_address_read=0, mem_addr_write=0 , sim_time_ns=0, seq_name=""):
        match = "PASS" if expected == observed else "FAIL"
        self.result_table.append({
            "Memory_Address": mem_address_read,
            "Memory_Address_Write": mem_addr_write,
            "Description": description,
            "Expected": f"{expected}",
            "Observed": f"{observed}",
            "Match": match ,
            "sim_time_ns": sim_time_ns,
            "seq_name": seq_name
        })

    def driver_entry_at(self, result_sim_time):
        # driver_info is appended in simulation-time order, so it is already
        # sorted by "sim_time_ns" and can be searched with a bisect.
        # Returns the entry with the largest sim_time_ns <= result_sim_time,
        # or None when the result predates every driven item.
        index = bisect.bisect_right(self.driver_info, result_sim_time,
                                    key=lambda entry: entry["sim_time_ns"])
        if index == 0:
            return None
        return self.driver_info[index - 1]

    def seq_name_at(self, result_sim_time):
        driver_entry = self.driver_entry_at(result_sim_time)
        return "" if driver_entry is None else driver_entry["seq_name"]

    def display_results(self):
        table_data = [
            [result["Description"], result["seq_name"], result["Memory_Address"], result["Memory_Address_Write"], result["Expected"], result["Observed"], result["Match"], result["sim_time_ns"]]
            for result in self.result_table
        ]
        # Define table headers
        headers = ["Description", "seq_name", "Memory_Address", "Memory_Address_write", "Expected", "Observed", "Match", "sim_time_ns"]
        # Generate table
        table = tabulate(table_data, headers=headers, tablefmt="grid")
        print(table)

    def build_phase(self):
        depth = ConfigDB().get(self, "", "FIFO_DEPTH")
        self.fifo_model = FIFOModel(depth=depth)
        logger.debug(f"Scoreboard reference model created with depth={depth}")

    def connect_phase(self):
        self.result_get_port.connect(self.result_fifo.get_export)
        self.driver_get_port.connect(self.driver_fifo.get_export)

    def check_phase(self):
        while self.driver_get_port.can_get():
            _, driver_data = self.driver_get_port.try_get()
            logger.info(f" FifoScoreboard Driver Data: {driver_data}")
            self.driver_info.append(driver_data)

        expected = None
        while self.result_get_port.can_get():
            _, monitor_data = self.result_get_port.try_get()
            logger.debug(f" FifoScoreboard Monitor Data: {monitor_data}")

            if monitor_data["reset_n"] == 0:
                self.fifo_model.reset()
                expected = 0
            elif monitor_data["wr_en"] == 1 and monitor_data["rd_en"] == 1:
                expected = self.fifo_model.read()
                self.fifo_model.write(monitor_data["data_in"])
            elif monitor_data["wr_en"] == 1 and monitor_data["rd_en"] == 0:
                self.fifo_model.write(monitor_data["data_in"])
            elif monitor_data["wr_en"] == 0 and monitor_data["rd_en"] == 1:
                expected = self.fifo_model.read()
            if expected is not None:
                observed = monitor_data["data_out"]
                sim_time_ns = monitor_data["sim_time_ns"]
                seq_name = self.seq_name_at(sim_time_ns)

                logger.debug(f"data_out: {monitor_data['data_out']}")
                match = observed == expected
                self.add_result(expected, observed, description= seq_name, mem_addr_write=monitor_data["wr_ptr"], mem_address_read=monitor_data["rd_ptr"], sim_time_ns=sim_time_ns, seq_name=seq_name)
                if not match:
                    self.display_results()
                    pyuvm.uvm_error(self.name, f"Mismatch at {sim_time_ns} ns (seq_name={seq_name}): Expected {expected}, Observed {observed}")
                else:
                    logger.debug(f" FifoScoreboard Actual_result {observed} =  Expected {expected}")
        self.display_results()

#
# # FIFO Sequencer and Sequences
class FifoSequence(uvm_sequence):
    def __init__(self, name="uvm_sequence"):
        super().__init__(name)
        self.RESET_LENGTH = 0
        self.PAUSE_LENGTH = 0
        self.index  = 0
        self.DEPTH = 1

    async def body(self):
# Design Test Plan
# Reset the FIFO for 3 clock Cycle
####################################################################
        for i in range(self.RESET_LENGTH):
            seq_item = FifoSequenceItem("reset_nreset_n", 0, reset_n=0)
            await self.start_item(seq_item)
            await self.finish_item(seq_item)

# Wait 3 Clock Cycle before Read or Write do nothing
##########################################################################
        for i in range(self.PAUSE_LENGTH):
            await self.send_data_sequence("do_nothing", rd_en=0, wr_en=0)
#################################################


# Test 3 Filling the Fifo with data
# Write N items where N is the FIFO DEPTH. Fill the Fifo with Data
##############################################
        for i in range(self.DEPTH):
            await self.send_data_sequence(f"writing {i}", rd_en=0, wr_en=1)


# Wait 3 Clock Cycle before Reading the Entire Fifo Do nothing
###############################################
        for i in range(self.PAUSE_LENGTH):
            await self.send_data_sequence("do_nothing", rd_en=0, wr_en=0)

# # added to be able to stop the code at anytime to add multiple check
#         await self.send_data_sequence("stop")

# Test extra write in the Fifo when Fifo is full to make sure that we cannot write anymore
###########################################################
        for i in range(int(self.DEPTH)//2):
            await self.send_data_sequence(f"writing_{i} x", rd_en=0, wr_en=1)

###############################################################
#        cocotb.stop()
 #       uvm_stop()
 #       uvm_test_done()
# Wait 3 Clock Cycle before Reading the Entire Fifo
###############################################
        for i in range(self.PAUSE_LENGTH):
            await self.send_data_sequence("do_nothing", rd_en=0, wr_en=0)

# Read N items where N is the FIFO DEPTH. Read the Entire Fifo
###############################################
        for i in range(self.DEPTH):
            await self.send_data_sequence("read_1", rd_en=1, wr_en=0)

# Wait 3 Clock Cycle After Read
###############################################
        for i in range(self.PAUSE_LENGTH):
            await self.send_data_sequence("do_nothing", rd_en=0, wr_en=0)

# Read the Fifo when the Fifo is empty after reading the Full Fifo to check that the Flag stay high
##################################################################
        for i in range(int(self.DEPTH)//2):
            await self.send_data_sequence("read_when_empty", rd_en=1, wr_en=0)

####################################################################

# Then Write into Half of the FIFo then Reset the Fifo and Perform a read we should not be able to read
##########################################################################################
        for i in range(int(self.DEPTH)//2):
            await self.send_data_sequence(f"writing 2 {i}", rd_en=0, wr_en=1)
        #
        for i in range(self.RESET_LENGTH):
            seq_item = FifoSequenceItem("reset_after_write", 0, reset_n=0)
            await self.start_item(seq_item)
            await self.finish_item(seq_item)

        await self.send_data_sequence("Extra_write", rd_en=0, wr_en=1)
        await self.send_data_sequence("Extra_read", rd_en=1, wr_en=0)
###############################################################################################

    async def send_data_sequence(self, name, rd_en = 0, wr_en = 0):
        seq_item = FifoSequenceItem(name, self.index , wr_en=wr_en, rd_en=rd_en)
        await self.start_item(seq_item)
        # if wr_en == 1:
        #     seq_item.randomize()  # Just added by Dr Eric
        await self.finish_item(seq_item)
        self.index += 1
################

class FifoSequencer(uvm_sequencer):
     pass

class FifoEnv(uvm_env):

    def build_phase(self):
        self.dut = cocotb.top
        self.monitor = FifoMonitor.create("cmd_mon", self)
        self.monitor.dut = self.dut
        self.seqr = FifoSequencer("seqr", self)
        ConfigDB().set(None, "*", "SEQR", self.seqr)
        # Added by Christian
        ConfigDB().set(None, "*", "FIFO_DEPTH", int(self.dut.DEPTH.value))
        self.driver = FifoDriver.create("driver", self)
        self.driver.dut = self.dut
        self.coverage = FifoCoverage("coverage", self)
        self.scoreboard = FifoScoreboard("scoreboard", self, self.dut)
#
    def connect_phase(self):
        self.driver.seq_item_port.connect(self.seqr.seq_item_export)  # Connect the driver to the sequence Item
        self.driver.ap.connect(self.scoreboard.driver_export)
        self.monitor.ap.connect(self.scoreboard.result_export)
        self.monitor.ap.connect(self.coverage.analysis_export)

    async def run_phase(self):
        for i in range(100):
            await RisingEdge(self.dut.clk)
        self.driver.stop()


# # FIFO Test
@pyuvm.test()
class FifoTest(uvm_test):

    def build_phase(self):
        self.env = FifoEnv("env", self)
        ConfigDB().set(None, "*", "CLOCK_PERIOD", 10) # Period in nanosecond
        ConfigDB().set(None, "*", "CLOCK_SETUP", 0.8) # Set up % before rising edge

    async def run_phase(self):
        self.raise_objection()
        self.sequence = FifoSequence.create("random_sequence")
        self.sequence.DEPTH = int(ConfigDB().get(None, "", "FIFO_DEPTH"))
        self.sequence.RESET_LENGTH = 3
        self.sequence.PAUSE_LENGTH = 4

        clock_period = ConfigDB().get(self, "", "CLOCK_PERIOD")
        clock = Clock(cocotb.top.clk, clock_period, unit="ns")
        cocotb.start_soon(clock.start())
        await FallingEdge(cocotb.top.clk)
 #       await Timer(5, unit="ns")    #For future reference
        if hasattr(cocotb.top, "clk_rd"):   # System Verilog cannot create a clock Conditionally based on the DUT interface
            clock = Clock(cocotb.top.clk_rd, clock_period, unit="ns")
            cocotb.start_soon(clock.start())

        await self.sequence.start(self.env.seqr)
        self.drop_objection()

