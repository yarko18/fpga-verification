// Copyright 2026 Yaroslav Mariukha
// SPDX-License-Identifier: RPL-1.5

module stream_pipeline #(
    parameter integer BITS_PER_SYMBOL  = 8,
    parameter integer SYMBOLS_PER_BEAT = 4,
    parameter integer DATA_WIDTH       = BITS_PER_SYMBOL * SYMBOLS_PER_BEAT,
    parameter integer EMPTY_WIDTH      = SYMBOLS_PER_BEAT <= 1 ? 1 : $clog2(SYMBOLS_PER_BEAT),
    parameter bit     USE_FIFO         = 1'b0,
    parameter integer FIFO_DEPTH       = 4,
    parameter integer FIFO_USED_WIDTH  = $clog2(FIFO_DEPTH)
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

    reg                   video_packet_q;
    wire                  input_is_video_identifier;
    wire                  input_is_video_payload;
    wire [DATA_WIDTH-1:0] converted_data;

    function automatic [DATA_WIDTH-1:0] reverse_valid_symbols(
        input [DATA_WIDTH-1:0]  value,
        input [EMPTY_WIDTH-1:0] empty,
        input                   endofpacket
    );
        integer destination;
        integer valid_symbols;
        begin
            valid_symbols = SYMBOLS_PER_BEAT;
            if (endofpacket) begin
                valid_symbols = SYMBOLS_PER_BEAT - int'(empty);
            end

            reverse_valid_symbols = value;
            for (
                destination = 0;
                destination < SYMBOLS_PER_BEAT;
                destination = destination + 1
            ) begin
                if (destination < valid_symbols) begin
                    reverse_valid_symbols[
                        destination * BITS_PER_SYMBOL +: BITS_PER_SYMBOL
                    ] = value[
                        (valid_symbols - 1 - destination) * BITS_PER_SYMBOL
                        +: BITS_PER_SYMBOL
                    ];
                end
            end
        end
    endfunction

    assign input_is_video_identifier =
        din_startofpacket && (din_data[3:0] == 4'h0);
    assign input_is_video_payload = video_packet_q && !din_startofpacket;
    assign converted_data = input_is_video_payload
        ? reverse_valid_symbols(din_data, din_empty, din_endofpacket)
        : din_data;

    always @(posedge clk) begin
        if (reset) begin
            video_packet_q <= 1'b0;
        end else if (din_valid && din_ready) begin
            if (din_startofpacket) begin
                video_packet_q <=
                    input_is_video_identifier && !din_endofpacket;
            end else if (din_endofpacket) begin
                video_packet_q <= 1'b0;
            end
        end
    end

    generate
        if (USE_FIFO) begin : g_fifo
            localparam integer FIFO_WIDTH = DATA_WIDTH + EMPTY_WIDTH + 2;

            wire [FIFO_WIDTH-1:0] fifo_data;
            wire [FIFO_WIDTH-1:0] fifo_q;
            wire                  fifo_empty;
            wire                  fifo_full;
            wire                  fifo_read;
            wire                  fifo_write;

            assign din_ready = !fifo_full;
            assign fifo_write = din_valid && din_ready && !reset;
            assign fifo_read = dout_ready && dout_valid;
            assign fifo_data = {
                din_startofpacket,
                din_endofpacket,
                din_empty,
                converted_data
            };

            assign dout_valid = !fifo_empty;
            assign {
                dout_startofpacket,
                dout_endofpacket,
                dout_empty,
                dout_data
            } = fifo_q;

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
            ) stream_fifo (
                .clock(clk),
                .data(fifo_data),
                .rdreq(fifo_read),
                .sclr(reset),
                .wrreq(fifo_write),
                .empty(fifo_empty),
                .full(fifo_full),
                .q(fifo_q),
                .aclr(),
                .almost_empty(),
                .almost_full(),
                .eccstatus(),
                .usedw()
            );
        end else begin : g_register
            reg [DATA_WIDTH-1:0]  data_q;
            reg                   valid_q;
            reg                   startofpacket_q;
            reg                   endofpacket_q;
            reg [EMPTY_WIDTH-1:0] empty_q;

            assign din_ready          = !valid_q || dout_ready;
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
                        data_q          <= converted_data;
                        startofpacket_q <= din_startofpacket;
                        endofpacket_q   <= din_endofpacket;
                        empty_q         <= din_empty;
                    end
                end
            end
        end
    endgenerate

endmodule
