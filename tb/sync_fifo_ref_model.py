class SyncFifoRefModel:
    """Cycle-based reference model of a synchronous FIFO.

    The model lives outside of the DUT and outside of the scoreboard. It is
    stepped once per rising clock edge with the inputs sampled at that edge
    and returns the outputs the DUT is expected to show after that edge.

    Specification modeled:
      * Asynchronous active-low reset empties the FIFO and clears data_out.
      * A write is accepted only if the FIFO is not full before the edge.
      * A read is accepted only if the FIFO is not empty before the edge.
      * A simultaneous read and write are both evaluated against the state
        before the edge (a write on a full FIFO is dropped even if a read
        happens in the same cycle).
      * data_out is registered: it updates on an accepted read, otherwise it
        holds its previous value.
    """

    def __init__(self, depth=8, width=7):
        self.depth = depth
        self.mask = (1 << width) - 1
        self.buffer = []
        self.data_out = 0
        self.wr_ptr = 0
        self.rd_ptr = 0

    @property
    def count(self):
        return len(self.buffer)

    def is_full(self):
        return len(self.buffer) >= self.depth

    def is_empty(self):
        return len(self.buffer) == 0

    def reset(self):
        self.buffer.clear()
        self.data_out = 0
        self.wr_ptr = 0
        self.rd_ptr = 0

    def step(self, reset_n, wr_en, rd_en, data_in):
        """Advance one clock edge and return the expected outputs.

        The pre-edge state (count and pointers) is returned as well so that
        coverage can be collected on the state the operation was applied to.
        """
        pre_count, pre_wr_ptr, pre_rd_ptr = self.count, self.wr_ptr, self.rd_ptr
        write_accepted = False
        read_accepted = False
        if not reset_n:
            self.reset()
        else:
            write_accepted = bool(wr_en) and not self.is_full()
            read_accepted = bool(rd_en) and not self.is_empty()
            if read_accepted:
                self.data_out = self.buffer.pop(0)
                self.rd_ptr = (self.rd_ptr + 1) % self.depth
            if write_accepted:
                self.buffer.append(int(data_in) & self.mask)
                self.wr_ptr = (self.wr_ptr + 1) % self.depth
        return {
            "pre_count": pre_count,
            "pre_wr_ptr": pre_wr_ptr,
            "pre_rd_ptr": pre_rd_ptr,
            "data_out": self.data_out,
            "full": int(self.is_full()),
            "empty": int(self.is_empty()),
            "count": self.count,
            "write_accepted": write_accepted,
            "read_accepted": read_accepted,
        }


if __name__ == "__main__":
    model = SyncFifoRefModel(depth=4)
    for i in range(5):
        print(f"write {i}: {model.step(1, 1, 0, i)}")
    for _ in range(5):
        print(f"read: {model.step(1, 0, 1, 0)}")
