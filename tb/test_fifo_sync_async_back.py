# Collateral and installation requirement
# Understanding of Package
# Understanding Python Queue
# Understand how does the timer work ?
# Using raising edge only and not falling edge (Same can be done with Falling Edge)
# Why don't we use Falling Edge in our design (?)
# Where to find the documentation for this package
# Review the difference between PYUVM  and Cocotb and see how they  work together
     # import pyuvm and Cocotb  *
     # Course with Cocotb
     # Course with PYUVM
# What is the Python requirement to do this course?
    # Understand Class (Inheritance , Polymorphism , Decorator)
    # Use of Python __str__ and __eq__
    # async function Understanding (class) (Await)
    # Other use of Await (Thread)
    # Understand Queue (Different between a Queue and a Cocotb Queue)
    # difference between Logger and Print
    # Quizz
    # How to open compare the log file of the optimize module using python
        #Remove randomize seed and until the final realize
from email.headerregistry import Address
# Python course for  RTL and DV Engineers
# Limitation Cocotb ??
# Back Door Writing Work better with ECC for Demo
# Top level name of the verilog name change do not impact the python file as it is call as below
########### cocotb.top.clk
# Add the compactness of the code by refactoring some of code inside function Python Release 02
# What is the order of class in standard UVM function
# Testbench should not care what the signals name are: We should be able say write read reset
# It is the driver job to translate the sequence to what that mean to the DUT
# Generalize the Function to enable a reset while writing or reading. The code now can only read and write at same time
# The sequence in which you test your design can reduce the amount of time use for simulation there validation
#   Example Test full and Test extra after Full
# For the next release fill the Fifo then write again and find a way to see that the contain of the fifo as not been
    # Corrupted
    # Do a write and read at the same time when the fifo is full
# Put the clock frequency as variable and drive the data 20 % of clock after rising edge
   # to account for any logic before the Flip Flop. The remaining is the Hold time

# Use AI to find out which pattern of data could be used to increase your coverage
# Use AI to find which sequence of tests and in which order should run to optimize the testing time
# Use AI to find the pattern needed to test a sub-design based on the requirement of the top level
        # System too big meet the requirement of the top level
# Code Reusability do not remove the optimal approach in case the memory is not a power of two
#      wr_ptr <= (wr_ptr + 1) % DEPTH; keep this instead of wr_ptr <= (wr_ptr + 1) ;

# Is it possible way to exit at a certain time just stop the code for continuing for debugging purpose ?
# Can we reuse the same testbench for emulation
# Survey of Languages language for UVM HDL Validation (Python , System Verilog, SystemC ?)
# Is there anyway to exit a program after a certain test is run using python exit() routine ?
# We need to compute the delay of the Combinatorial pass through time whether (80-20) or (90-10)
# We should have a way of exiting the program at a certain stage just to run part of test of Interest
# Explain the log file and the output on the Xterm
# How to use Cocotb with inside Pycharm and Debug

from venv import logger

import pyuvm
import random

#from cocotb.binary import BinaryValue, BinaryRepresentation
from cocotb.types import LogicArray

from cocotb.clock import Clock
from cocotb.queue import Queue
from cocotb.triggers import RisingEdge, Timer, FallingEdge, ReadOnly
#from nacl.utils import random
from pyuvm import *
from tabulate import tabulate

from cocotb.utils import get_sim_time
from fifo_model_simple_version import FIFOModel



# Adding command to add debugger to Pycharm
# Remote debug server client pydevd
#import pydevd

#pydevd.settrace('localhost', port=9090, stdoutToServer=True, stderrToServer=True)
import sys
print("Python executable:", sys.executable)
print("Python path:", sys.path)


# Not sure to understand this command
logging.getLogger("pyuvm").setLevel(logging.DEBUG)


# Set the logging level (optional, default is WARNING)
logger.setLevel(logging.DEBUG)

# Create a file handler to write logs to a file
file_handler = logging.FileHandler('log_fifo_file.txt')

# Create a formatter for the log messages
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Attach the formatter to the file handler
file_handler.setFormatter(formatter)

# Add the file handler to PyUVM's logger
logger.addHandler(file_handler)

# class LogTest(uvm_test):
#     def build_phase(self):
#         self.info = InfoComp("info", self)
#         self.warning = WarningComp("warning", self)
#         self.debug = DebugComp("debug", self)


import queue

class FilterQueue(queue.Queue):
    def __init__(self, driver_get_port, maxsize=0 ):

        super().__init__(maxsize)
        self.queue = []
        self.driver_get_port = driver_get_port


    def _put(self, item):
        self.queue.append(item)


    def _get(self):
        return self.queue.pop(0)  # Remove and return the highest priority item

    def try_get(self):
        data_available = True
        while data_available:
            data_available, driver_data = self.driver_get_port.try_get()
            if data_available:

                self._put(driver_data)
        if self.empty():

            return False, None
        else:
            driver_data = self._get()
            print(f"ZZZ : driver_data EEEE: {driver_data['reset_n']}, {driver_data['seq_name']}, {list(self.queue)}")
            return True, driver_data

    def __str__(self):
        return f"{self.queue}"

    def reset(self):
        while  len(self.queue) > 0 and self.queue[0]["reset_n"] == 1:
            deleted_data = self.queue.pop(0)
            print(
                f"ZZZ : DELETED DUE TO RESET: {deleted_data['reset_n']}, {deleted_data['seq_name']}, {list(self.queue)}")



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
        self.write_data_fifo = uvm_tlm_analysis_fifo("write_data_fifo", self)
        self.result_fifo = uvm_tlm_analysis_fifo("result_fifo", self)
        self.write_data_get_port = uvm_get_port("write_data_get_port", self)
        self.result_get_port = uvm_get_port("result_get_port", self)
        self.result_export = self.result_fifo.analysis_export  # connected to the Monitor
        self.write_data_export = self.write_data_fifo.analysis_export  # Connected to the Driver

    def connect_phase(self):
        self.write_data_get_port.connect(self.write_data_fifo.get_export)
        self.result_get_port.connect(self.result_fifo.get_export)
        pass

    def write(self, coverage_signals):
        if coverage_signals["wr_en"]:
            self.coverage["write"] += 1
        if coverage_signals["rd_en"]:
            self.coverage["read"] += 1
        if coverage_signals["full"]:
            self.coverage["full"] += 1
#        if coverage_signals["empty"].binstr == '0':
        if str(coverage_signals["empty"]) == '0':
            self.coverage["empty_0"] += 1
#        elif coverage_signals["empty"].binstr == "1":
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

# This method is used by the scoreboard to compare coming from driver and those observe
# by the monitor

    def __eq__(self, other):
        return self.write_data == other.write_data

    def __str__(self):
        return f'{self.get_name()} {self.index}:{self.write_data}'

    def randomize(self):
        self.write_data = random.randint(0,127)


# # FIFO Driver
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
            logger.info(f"Driver received Item {seq_item}")

        # Added to stop the code at anytime to progessivilely debug
        #     if seq_item.name == "stop":
        #         self.stop()

            # if self.dut.full.value == 1:
            #     print(f" I AM INSIDE THE DRIVER mem.value {cocotb.top.mem.value}")
            #     cocotb.top.mem[4].value = 127
            #     print(f" I AM INSIDE THE DRIVER mem.value after Force {cocotb.top.mem.value}")
            await RisingEdge(self.dut.clk) # Settings the signals to respect the set up and hold of the Flip Flop
            await Timer(clock_setup_time, unit='ns')
            self.dut.data_in.value = seq_item.write_data
            self.dut.wr_en.value = seq_item.wr_en

            self.dut.reset_n.value = seq_item.reset_n
            self.dut.rd_en.value = seq_item.rd_en
            if (seq_item.wr_en and not self.dut.full.value) or seq_item.reset_n == 0:
                # Added to enable the table results
                signals_driven = dict()
              #  signals_driven["data_in"] =  BinaryValue(seq_item.write_data, n_bits=len(self.dut.data_in), bigEndian=False,
              #                     binaryRepresentation=BinaryRepresentation.UNSIGNED )

                signals_driven["data_in"] = LogicArray.from_unsigned(seq_item.write_data,len(self.dut.data_in))

                signals_driven["seq_name"] = seq_item.get_name()
                signals_driven["reset_n"] = seq_item.reset_n
                print(f" XXXXXX sequence write_data and data_in +++++ : {seq_item.write_data} and data_in: {self.dut.data_in.value}")
                print(f" XXXXXX sequence signals_driven[data_in] +++++ : {seq_item.write_data} and data_in: {signals_driven['data_in']}")
                print(f" XXXXXX WRITE_DATA +++++ : {seq_item.write_data:0{len(self.dut.data_in)}b} ")
               # B = BinaryValue( n_bits=7)
              #  B = LogicArray(0, n_bits=7)
                B = LogicArray("111")
              #  B.integer = seq_item.write_data
                B[:] = seq_item.write_data & ((1 << len(B)) - 1)
 #               print(f'**************B: {B}, {B.binstr},{B.integer},{B.n_bits} ******************')
             #   B = BinaryValue(value=3, n_bits=3, bigEndian=False,
             #                      binaryRepresentation=BinaryRepresentation.UNSIGNED)
                B = LogicArray.from_unsigned(3, 3)

  #              print(f'**************B: {B}, {B.binstr},{B.integer},{B.n_bits} ******************')

                # Converting Integer data input to scoreboard into binary
    #            self.ap.write(f"{seq_item.write_data:0{len(self.dut.data_in)}b}")
 #               if not self.dut.full.value:
                print(f"VVVVV signals :{signals_driven}")
                self.ap.write(signals_driven)


 #           await Timer(2, unit='ns')
#            self.dut.rd_en.value = seq_item.rd_en

            self.seq_item_port.item_done()

    def stop(self):

        self.stop_requested = True


# # FIFO Monitor
class FifoMonitor(uvm_monitor):
    def __init__(self, name = 'fifo', parent=None, dut=None, cycles_to_monitor=100):
        super().__init__(name, parent)
        self.dut = dut
        self.cycles_to_monitor = cycles_to_monitor
        self.ap = uvm_analysis_port("ap", self)

    def build_phase(self):
        pass

    async def run_phase(self):


        self.raise_objection()
        for i in range(self.cycles_to_monitor):
            signals_monitored = dict()
            await RisingEdge(self.dut.clk)
            signals_monitored["rd_ptr"] = self.dut.rd_ptr.value
            await ReadOnly()   # After the simulated signals have settled for this time steps
           # signals_monitored = dict()
            #Signal monitored sim time
            signals_monitored["sim_time_ns"] = get_sim_time(unit="ns")

            signals_monitored["reset_n"] = self.dut.reset_n.value
            signals_monitored["rd_en"] = self.dut.rd_en.value
            signals_monitored["wr_en"] = self.dut.wr_en.value
            signals_monitored["data_out"] = self.dut.data_out.value
            signals_monitored["full"] = self.dut.full.value
            signals_monitored["empty"] = self.dut.empty.value
            signals_monitored["data_in"] = self.dut.data_in.value
 #           signals_monitored["rd_ptr"] = self.dut.rd_ptr.value
    # Working on the internal signal
            signals_monitored["flag_full_empty"] = self.dut.flag_full_empty.value
          #  print(f"flag_full_empty: {signals_monitored['flag_full_empty']}")
            print(f" MEMORY mem: {len(self.dut.mem.value)} and  value {self.dut.mem.value}")
            print(f" MONITOR Signal data_out: {signals_monitored['data_out']}")


            self.ap.write(signals_monitored)  # Send observed data to the connected scoreboard

        self.drop_objection()

#
class FifoScoreboard(uvm_scoreboard):
    def __init__(self, name = 'fifo', parent=None, dut=None):
        super().__init__(name, parent)
        self.dut = dut
        self.name = name
        self.result_table = []
#        self.expected_data = Queue()
 #       self.write_data_fifo = uvm_tlm_analysis_fifo("write_data_fifo", self)
        self.result_fifo = uvm_tlm_analysis_fifo("result_fifo", self)
 #       self.write_data_get_port = uvm_get_port("write_data_get_port", self)
        self.result_get_port = uvm_get_port("result_get_port", self)
        self.result_export = self.result_fifo.analysis_export # connected to the Monitor
 #       self.write_data_export = self.write_data_fifo.analysis_export # Connected to the Driver
       # self.driver_get_port = FilterQueue(self.write_data_get_port)
        self.fifo_model = FIFOModel(depth=4)


    def add_result(self, expected, observed, description="", mem_address_read=0, sim_time_ns=0):
        match = "PASS" if expected == observed else "FAIL"
        self.result_table.append({
            "Memory_Address": mem_address_read,
            "Description": description,
            "Expected": f"{expected}",
            "Observed": f"{observed}",
            "Match": match ,
            "sim_time_ns": sim_time_ns
        })


    def display_results(self):
        # Convert results into a list of lists for tabulate



        table_data = [
            [result["Description"], result["Memory_Address"], result["Expected"], result["Observed"], result["Match"], result["sim_time_ns"]]
            for result in self.result_table
        ]
        # Define table headers
        headers = ["Description", "Memory_Address", "Expected", "Observed", "Match", "sim_time_ns"]
        # Generate table
        table = tabulate(table_data, headers=headers, tablefmt="grid")
        print(table)



    def connect_phase(self):

      #  self.write_data_get_port.connect(self.write_data_fifo.get_export)
        self.result_get_port.connect(self.result_fifo.get_export)
        pass

    def check_phase(self):
        previous_cycle_empty = 0
        while self.result_get_port.can_get():
            _, monitor_data = self.result_get_port.try_get()
    #        if monitor_data["rd_en"] == 1 and not monitor_data["empty"] and 'x' not in monitor_data['data_out']:
            print(f" XXXX In the ScoreBoard Checking monitor_data: {monitor_data}")


            if (monitor_data["rd_en"] == 1 and (not monitor_data["empty"] or not previous_cycle_empty)) or monitor_data["reset_n"] == 0:

                observed = monitor_data["data_out"]
                sim_time_ns = monitor_data["sim_time_ns"]
                logger.info(f"data_out: {monitor_data['data_out']}")

                if monitor_data["reset_n"] == 0:
                    self.driver_get_port.reset()


 #               data_available, driver_data = self.write_data_get_port.try_get() Change the previous value
                data_available, driver_data = self.driver_get_port.try_get()
                expected = driver_data["data_in"]
                if data_available:
                    print(f"+++++++++ Monitor_data +++++++++: {monitor_data}")
                    print(f" expected: {type(expected)}, actual_result = {type(observed)}")
                    logger.info(f"expected: {expected}, actual_result = {observed}")

                    match = observed == expected
                    self.add_result(expected, observed, description=driver_data["seq_name"], mem_address_read=monitor_data["rd_ptr"], sim_time_ns=sim_time_ns)
                    if not match:
                        self.display_results()
                        pyuvm.uvm_error(self.name, f"Mismatch: Expected {expected}, Observed {observed}")


                        #      logger.error(self.name + f"Mismatch: Expected {expected}, Observed {observed}")
                #    assert actual_result == expected, f"Data mismatch: expected {expected}, got {actual_result}"
                else:
                    print(f" actual_result =  {observed} ")
            previous_cycle_empty = monitor_data["empty"]



        while self.write_data_get_port.can_get():
            _, driver_data = self.write_data_get_port.try_get()
            print(f" XXXXXXXX Scoreboard extra datadriver_data: {driver_data['data_in']}")

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

        print(f" I AM INSIDE THE FIFO SEQUENCE flag_full_empty.value {cocotb.top.flag_full_empty.value}")
        print(f" I AM INSIDE THE FIFO SEQUENCE FIFO_DEPTH.value {cocotb.top.DEPTH.value}")
#        print(f" I AM INSIDE THE FIFO SEQUENCE mem.value {cocotb.top.mem.value}")
 #       for i in cocotb.top:
 #           print(str(i.name))


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
        #
        # for i in range(int(self.DEPTH/2)):
        #     await self.send_data_sequence("reading_after_reset", rd_en=1, wr_en=0)


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

#
class FifoSequencer(uvm_sequencer):
     pass

class FifoEnv(uvm_env):

    def build_phase(self):

        self.dut = cocotb.top
        self.monitor = FifoMonitor.create("cmd_mon", self)
        self.monitor.dut = self.dut
        self.seqr = FifoSequencer("seqr", self)
        ConfigDB().set(None, "*", "SEQR", self.seqr)

        self.driver = FifoDriver.create("driver", self)
        self.driver.dut = self.dut
        self.coverage = FifoCoverage("coverage", self)
        self.scoreboard = FifoScoreboard("scoreboard", self, self.dut)
#
    def connect_phase(self):
        self.driver.seq_item_port.connect(self.seqr.seq_item_export)
        self.monitor.ap.connect(self.scoreboard.result_export)
        self.monitor.ap.connect(self.coverage.analysis_export)
        self.driver.ap.connect(self.scoreboard.write_data_export)
#        self.driver.ap.connect(self.coverage.cmd_export)

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

#
    def end_of_elaboration_phase(self):
        self.sequence = FifoSequence.create("random_sequence")
#
    async def run_phase(self):
    #    cocotb.top.DEPTH = 7   # Just added

        self.raise_objection()
        clock_period = ConfigDB().get(self, "", "CLOCK_PERIOD")
        clock = Clock(cocotb.top.clk, clock_period, unit="ns")
        cocotb.start_soon(clock.start())
        await FallingEdge(cocotb.top.clk)
 #       await Timer(5, unit="ns")    #For future reference
        if hasattr(cocotb.top, "clk_rd"):   # System Verilog cannot create a clock Conditionally based on the DUT interface
            clock = Clock(cocotb.top.clk_rd, clock_period, unit="ns")
            cocotb.start_soon(clock.start())

# TEST PARAMETERS
        self.sequence.RESET_LENGTH = 3
        self.sequence.PAUSE_LENGTH = 4
#ARCHITECTURE PARAMETER
    #    self.sequence.DEPTH = 8
        self.sequence.DEPTH = cocotb.top.DEPTH.value
        print(f" ++++ The Value of the DEPTH is DEPTH ++++ : {self.sequence.DEPTH}")

        await self.sequence.start(self.env.seqr)

        self.drop_objection()

