# Simulator
SIM ?= verilator

# HDL language
TOPLEVEL_LANG = verilog

# RTL sources
VERILOG_SOURCES = $(PWD)/rtl/fifo1.sv

# Top-level DUT
TOPLEVEL = fifo1

# Python test module (without .py)
COCOTB_TEST_MODULES = test_fifo_sync_async

PYTHONPATH := $(PWD)/tb
export PYTHONPATH

# Verilator options
EXTRA_ARGS += --timing
EXTRA_ARGS += -Wall
EXTRA_ARGS += --Wno-fatal
#EXTRA_ARGS += --trace-fst
EXTRA_ARGS += --trace

# Generate FST waveform
WAVES = 1

# Cocotb makefiles
include $(shell cocotb-config --makefiles)/Makefile.sim