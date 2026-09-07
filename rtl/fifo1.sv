`timescale 1ns/1ps
module fifo1 #(  parameter DEPTH = 4'b1000 ) // Declare the parameter
(

    input wire clk,
    input wire clk_rd,
    input wire reset_n,
    input wire wr_en,
    input wire rd_en,
    input wire [6:0] data_in,
    output reg [6:0] data_out,
    output wire full,
    output wire empty
);
//    parameter DEPTH = 8;
    reg [6:0] mem [0:DEPTH-1];
    reg [2:0] wr_ptr, rd_ptr;
 //   reg [3:0] count;
 //   reg flag_full_empty = 1'b0 ;
    reg flag_full_empty ;



    assign full  = (wr_ptr == rd_ptr) & (flag_full_empty);
    assign empty = (wr_ptr == rd_ptr) & (~flag_full_empty);

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
            data_out <= 0 ;

        end else begin
            // Write operation
            if (wr_en && !full) begin
                mem[wr_ptr] <= data_in;
                //wr_ptr <= (wr_ptr + 4'b0001) % 4'(DEPTH);
                wr_ptr <= (wr_ptr + 3'b001) ;
            end

            // Read operation
            if (rd_en && !empty) begin
                data_out <= mem[rd_ptr];
                //rd_ptr <= (rd_ptr + 4'b0001) % 4'(DEPTH);
                rd_ptr <= (rd_ptr + 3'b001) ;
            end

        end
    end


   always @(posedge clk or negedge reset_n) begin
       if (!reset_n) begin
          flag_full_empty <= 1'b0 ;

       end else begin  // Reset end
       // Write enable flag
          if ((wr_ptr == 3'(DEPTH-1)) && (wr_en)) begin
            flag_full_empty <= 1'b1 ;
          end // if write end
          // Read enable Flag
          if ((rd_ptr == 3'(DEPTH-1)) && (rd_en)) begin
             flag_full_empty <= 1'b0 ;
          end // If read end
       end // Else end
   end // Module end



// Using custom vcd code to dump the memory otherwise just use wave = 1 in your Make file

   // the "macro" to dump signals
`ifdef COCOTB_SIM
initial begin
  integer idx ;
   //$dumpfile ("sim_build/fifo1.vcd"); // Generate VCD
   $dumpfile("logs/fifo1.vcd"); // Generate FST
   $dumpvars (0, fifo1);   // Dump all signals
  for (idx = 0; idx < DEPTH; idx = idx + 1) $dumpvars(0, mem[idx]);

  #1;
  $display(" XXXXXXXXXX THE COMMAND IS OVER XXXXXXXXXXXXXXXX") ;
end
`endif




endmodule
