// Copyright 2026 Yaroslav Mariukha
// SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

module adder #(
    parameter integer DATA_WIDTH = 8
) (
    input  wire                  clk,
    input  wire                  reset_n,

    input  wire [DATA_WIDTH-1:0] a,
    input  wire [DATA_WIDTH-1:0] b,
    output reg  [DATA_WIDTH-1:0] sum,
    output reg                   overflow
);

    wire [DATA_WIDTH-1:0] next_sum;
    wire                  next_overflow;

    assign next_sum = a + b;
    assign next_overflow =
        (a[DATA_WIDTH-1] == b[DATA_WIDTH-1])
        && (a[DATA_WIDTH-1] != next_sum[DATA_WIDTH-1]);

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            sum      <= '0;
            overflow <= 1'b0;
        end else begin
            sum      <= next_sum;
            overflow <= next_overflow;
        end
    end

endmodule
