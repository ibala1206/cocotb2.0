class FIFOModel:
    def __init__(self, depth=8):
        self.depth = depth
        self.buffer = []

    def is_full(self):
        return len(self.buffer) >= self.depth

    def is_empty(self):
        return len(self.buffer) == 0

    def write(self, data):
        if not self.is_full():
            self.buffer.append(data)
        else:
            print("FIFO full – write ignored")

    def read(self):
        if not self.is_empty():
            return self.buffer.pop(0)
        else:
            print("FIFO empty – read ignored")
            return None

    def reset(self):
        self.buffer.clear()
        print("FIFO reset")


if __name__ == "__main__":
    fifo = FIFOModel(depth=4)
    for i in range(4):
        fifo.write(i)
        print(f"Wrote {i}")
    for _ in range(3):
        data = fifo.read()
        print(f"Read {data}")
    fifo.reset()
    for i in range(5, 10):
        fifo.write(i)
        print(f"Wrote {i}")
    for _ in range(5):
        data = fifo.read()
        print(f"Read {data}")