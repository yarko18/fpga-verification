// Copyright 2026 Yaroslav Mariukha
// SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

module fifo #(
    parameter integer FIFO_DEPTH = 16,
    parameter integer FIFO_WIDTH = 16,
    parameter integer FIFO_USED_WIDTH =
        FIFO_DEPTH <= 2 ? 1 : $clog2(FIFO_DEPTH)
) (
    input  wire                  clk,
    input  wire                  reset,

    input  wire [FIFO_WIDTH-1:0] data,
    input  wire                  write,
    output wire                  full,

    output wire [FIFO_WIDTH-1:0] q,
    input  wire                  read,
    output wire                  empty
);

    wire [FIFO_USED_WIDTH-1:0] used;

    scfifo #(
        .add_ram_output_register("OFF"),
        .intended_device_family("Cyclone V"),
        .lpm_numwords(FIFO_DEPTH),
        .lpm_showahead("ON"),
        .lpm_type("scfifo"),
        .lpm_width(FIFO_WIDTH),
        .lpm_widthu(FIFO_USED_WIDTH),
        .overflow_checking("ON"),
        .underflow_checking("ON"),
        .use_eab("ON")
    ) scfifo_lib (
        .clock(clk),
        .data(data),
        .rdreq(read),
        .sclr(reset),
        .wrreq(write),
        .empty(empty),
        .full(full),
        .q(q),
        .usedw(used),
        .aclr(),
        .almost_empty(),
        .almost_full(),
        .eccstatus()
    );

endmodule
