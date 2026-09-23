// Copyright 2026 Yaroslav Mariukha
// SPDX-License-Identifier: RPL-1.5

module stream_pipeline #(
    parameter integer BITS_PER_SYMBOL  = 8,
    parameter integer SYMBOLS_PER_BEAT = 2,
    parameter integer DATA_WIDTH       = BITS_PER_SYMBOL * SYMBOLS_PER_BEAT,
    parameter integer EMPTY_WIDTH      = SYMBOLS_PER_BEAT <= 1 ? 1 : $clog2(SYMBOLS_PER_BEAT)
) (
    input  wire                     clk,
    input  wire                     reset,

    input  wire [DATA_WIDTH-1:0]    din_data,
    input  wire                     din_valid,
    output wire                     din_ready,
    input  wire                     din_startofpacket,
    input  wire                     din_endofpacket,
    input  wire [EMPTY_WIDTH-1:0]   din_empty,

    output wire [DATA_WIDTH-1:0]    dout_data,
    output wire                     dout_valid,
    input  wire                     dout_ready,
    output wire                     dout_startofpacket,
    output wire                     dout_endofpacket,
    output wire [EMPTY_WIDTH-1:0]   dout_empty
);

    reg [DATA_WIDTH-1:0]  data_q;
    reg                   valid_q;
    reg                   startofpacket_q;
    reg                   endofpacket_q;
    reg [EMPTY_WIDTH-1:0] empty_q;

    assign din_ready          = ~valid_q | dout_ready;
    assign dout_data          = data_q;
    assign dout_valid         = valid_q;
    assign dout_startofpacket = startofpacket_q;
    assign dout_endofpacket   = endofpacket_q;
    assign dout_empty         = empty_q;

    always @(posedge clk) begin
        if (reset) begin
            valid_q <= 1'b0;
        end else if (din_ready) begin
            valid_q <= din_valid;
            if (din_valid) begin
                data_q          <= din_data;
                startofpacket_q <= din_startofpacket;
                endofpacket_q   <= din_endofpacket;
                empty_q         <= din_empty;
            end
        end
    end

endmodule
