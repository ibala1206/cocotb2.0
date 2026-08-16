`timescale 1ns/1ps

module tb_fifo1;

    // Parameters
    parameter DEPTH = 8;

    // Testbench Signals
    reg clk;
    reg clk_rd;
    reg reset_n;
    reg wr_en;
    reg rd_en;
    reg [6:0] data_in;
    wire [6:0] data_out;
    wire full;
    wire empty;

    // Instantiate the Device Under Test (DUT)
    fifo1 #(.DEPTH(DEPTH)) uut (
        .clk(clk),
        .clk_rd(clk_rd),
        .reset_n(reset_n),
        .wr_en(wr_en),
        .rd_en(rd_en),
        .data_in(data_in),
        .data_out(data_out),
        .full(full),
        .empty(empty)
    );

    // Clock Generation (50MHz -> 20ns period)
    always #10 clk <= ~clk;
    always #10 clk_rd <= ~clk_rd; // Driving the read clock in sync for now

    // Stimulus Task: Write a byte of data
    task write_data(input [6:0] data);
        begin
            @(posedge clk);
            if (!full) begin
                wr_en   = 1'b1;
                data_in = data;
                $display("[WRITE] Time=%0t | Data In=0x%h", $time, data);
            end else begin
                $display("[WRITE SKIPPED] FIFO Full at Time=%0t", $time);
            end
            @(posedge clk);
            wr_en = 1'b0;
        end
    endtask

    // Stimulus Task: Read a byte of data
    task read_data();
        begin
            @(posedge clk);
            if (!empty) begin
                rd_en = 1'b1;
                @(posedge clk); // Wait for the clock edge where data is registered out
                $display("[READ]  Time=%0t | Data Out=0x%h", $time, data_out);
            end else begin
                $display("[READ SKIPPED] FIFO Empty at Time=%0t", $time);
            end
            rd_en = 0;
        end
    endtask

    // Initial Block - Main Test Sequence
    initial begin
        // Setup waveform dumping for Verilator / GTKWave
        $dumpfile("fifo1.fst");
        $dumpvars(0, tb_fifo1);
        
        // Initialize Signals
        clk     = 0;
        clk_rd  = 0;
        reset_n = 0;
        wr_en   = 0;
        rd_en   = 0;
        data_in = 0;

        // Apply Reset
        #40;
        reset_n = 1;
        $display("--- Reset Released ---");

        // --- Test Case 1: Write data until FIFO is full ---
        $display("\n--- Starting Write Sequence ---");
        write_data(7'h0A);
        write_data(7'h1B);
        write_data(7'h2C);
        write_data(7'h3D);
        write_data(7'h4E);
        write_data(7'h5F);
        write_data(7'h6A);
        write_data(7'h7B);
        
        // Attempt an extra write to check 'full' behavior
        write_data(7'h7F); 

        #20;
        $display("Status Check: Full=%b, Empty=%b", full, empty);

        // --- Test Case 2: Read data until FIFO is empty ---
        $display("\n--- Starting Read Sequence ---");
        repeat (8) begin
            read_data();
        end
        
        // Attempt an extra read to check 'empty' behavior
        read_data(); 

        #20;
        $display("Status Check: Full=%b, Empty=%b", full, empty);

        // Finish simulation
        $display("\n--- Simulation Complete ---");
        $finish;
    end

endmodule
