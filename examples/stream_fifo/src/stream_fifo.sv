// Copyright 2026 Yaroslav Mariukha
// SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

module stream_fifo #(
    parameter integer FIFO_DEPTH = 16,
    parameter integer FIFO_WIDTH = 16
) (
    input  wire                  clk,
    input  wire                  reset,

    output wire                  din_ready,
    input  wire                  din_valid,
    input  wire [FIFO_WIDTH-1:0] din_data,

    input  wire                  dout_ready,
    output wire                  dout_valid,
    output wire [FIFO_WIDTH-1:0] dout_data
);

    wire fifo_empty;
    wire fifo_full;
    wire fifo_read;
    wire fifo_write;

    assign din_ready  = !fifo_full;
    assign fifo_write = din_valid && din_ready;

    assign dout_valid = !fifo_empty;
    assign fifo_read  = dout_valid && dout_ready;

    fifo #(
        .FIFO_DEPTH(FIFO_DEPTH),
        .FIFO_WIDTH(FIFO_WIDTH)
    ) fifo_inst (
        .clk(clk),
        .reset(reset),
        .data(din_data),
        .write(fifo_write),
        .full(fifo_full),
        .q(dout_data),
        .read(fifo_read),
        .empty(fifo_empty)
    );

endmodule
