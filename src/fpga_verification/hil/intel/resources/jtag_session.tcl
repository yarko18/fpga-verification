# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5
#
# Unless explicitly acquired and licensed from Licensor under another license,
# the contents of this file are subject to the Reciprocal Public License ("RPL")
# Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
# or use this file in either source code or executable form, except in compliance
# with the terms and conditions of the RPL.
#
# All software distributed under the RPL is provided strictly on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
# HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
# ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
# rights and limitations under the RPL.

# Persistent System Console worker for HIL tests.
#
# Protocol on stdin/stdout uses tab-separated records:
#   WRITE <file> <base_addr> <chunk_size>
#   READ  <file> <base_addr> <total_size_bytes> <chunk_size>
#   UART  <payload_hex> <timeout_ms>
#   QUIT

proc protocol_puts {line} {
    puts $line
    flush stdout
}

proc report_progress {done total offset chunk addr} {
    protocol_puts "PROGRESS_BYTES\t$done\t$total\t$offset\t$chunk\t[format 0x%08X $addr]"
}

proc write_memory {master input_file base_addr_str chunk_size} {
    if {$chunk_size <= 0} {
        error "chunk_size must be > 0"
    }
    if {![file exists $input_file]} {
        error "input file does not exist: $input_file"
    }

    set base_addr [expr {$base_addr_str}]
    set f ""
    set raw ""
    if {[catch {
        set f [open $input_file r]
        fconfigure $f -translation binary
        set raw [read $f]
        close $f
        set f ""
    } err]} {
        if {$f ne ""} {
            catch {close $f}
        }
        error "failed to read input file: $err"
    }

    set total_size [string length $raw]
    if {$total_size == 0} {
        error "input file is empty"
    }

    for {set offset 0} {$offset < $total_size} {incr offset $chunk_size} {
        set remaining [expr {$total_size - $offset}]
        set this_size [expr {$remaining < $chunk_size ? $remaining : $chunk_size}]
        set addr [expr {$base_addr + $offset}]
        set chunk [string range $raw $offset [expr {$offset + $this_size - 1}]]
        binary scan $chunk cu* data
        master_write_memory $master $addr $data
        report_progress [expr {$offset + $this_size}] $total_size $offset $this_size $addr
    }
}

proc read_memory {master output_file base_addr_str total_size chunk_size} {
    if {$chunk_size <= 0} {
        error "chunk_size must be > 0"
    }
    if {$total_size <= 0} {
        error "total_size must be > 0"
    }

    set base_addr [expr {$base_addr_str}]
    set f ""
    if {[catch {
        set f [open $output_file w]
        fconfigure $f -translation binary

        for {set offset 0} {$offset < $total_size} {incr offset $chunk_size} {
            set remaining [expr {$total_size - $offset}]
            set this_size [expr {$remaining < $chunk_size ? $remaining : $chunk_size}]
            set addr [expr {$base_addr + $offset}]
            set data [master_read_memory $master $addr $this_size]
            puts -nonewline $f [binary format cu* $data]
            report_progress [expr {$offset + $this_size}] $total_size $offset $this_size $addr
        }

        close $f
        set f ""
    } err]} {
        if {$f ne ""} {
            catch {close $f}
        }
        error "failed to read memory: $err"
    }
}

proc drain_uart {uart} {
    while {1} {
        set discarded [bytestream_receive $uart 4096]
        if {[llength $discarded] == 0} {
            return
        }
    }
}

proc uart_request {uart payload_hex timeout_ms} {
    if {$timeout_ms <= 0} {
        error "timeout_ms must be > 0"
    }

    drain_uart $uart
    set payload [binary format H* $payload_hex]
    binary scan $payload cu* payload_bytes
    bytestream_send $uart $payload_bytes

    set response ""
    set deadline [expr {[clock milliseconds] + $timeout_ms}]
    while {[clock milliseconds] < $deadline} {
        set incoming [bytestream_receive $uart 4096]
        if {[llength $incoming] > 0} {
            append response [binary format cu* $incoming]
            if {[string first "\n" $response] >= 0} {
                binary scan $response H* response_hex
                protocol_puts "UART_RESULT\t$response_hex"
                return
            }
        }
        after 10
    }

    error "timeout waiting for UART response"
}

set master_index 0
set uart_index 0
if {$argc >= 1} {
    set master_index [expr {[lindex $argv 0]}]
}
if {$argc >= 2} {
    set uart_index [expr {[lindex $argv 1]}]
}

set master ""
set uart ""
if {[catch {
    set masters [get_service_paths master]
    if {$master_index < 0 || $master_index >= [llength $masters]} {
        error "master service index $master_index not found"
    }
    set master [lindex $masters $master_index]
    open_service master $master

    set uart_paths [get_service_paths bytestream]
    if {$uart_index < 0 || $uart_index >= [llength $uart_paths]} {
        error "bytestream service index $uart_index not found"
    }
    set uart_path [lindex $uart_paths $uart_index]
    set uart [claim_service bytestream $uart_path nuc_test]
} err]} {
    if {$master ne ""} {
        catch {close_service master $master}
    }
    protocol_puts "JTAG_FATAL\t$err"
    exit 1
}

protocol_puts "JTAG_READY"

set running 1
while {$running && [gets stdin line] >= 0} {
    set fields [split $line "\t"]
    set operation [lindex $fields 0]

    if {[catch {
        switch -- $operation {
            WRITE {
                if {[llength $fields] != 4} {
                    error "WRITE requires file, address and chunk_size"
                }
                write_memory $master [lindex $fields 1] [lindex $fields 2] [lindex $fields 3]
                protocol_puts "JTAG_DONE\tWRITE"
            }
            READ {
                if {[llength $fields] != 5} {
                    error "READ requires file, address, total_size and chunk_size"
                }
                read_memory $master [lindex $fields 1] [lindex $fields 2] [lindex $fields 3] [lindex $fields 4]
                protocol_puts "JTAG_DONE\tREAD"
            }
            UART {
                if {[llength $fields] != 3} {
                    error "UART requires payload_hex and timeout_ms"
                }
                uart_request $uart [lindex $fields 1] [lindex $fields 2]
            }
            QUIT {
                set running 0
            }
            default {
                error "unknown operation: $operation"
            }
        }
    } err]} {
        protocol_puts "JTAG_ERROR\t$operation\t$err"
    }
}

if {$uart ne ""} {
    catch {close_service bytestream $uart}
}
if {$master ne ""} {
    catch {close_service master $master}
}

protocol_puts "JTAG_CLOSED"
exit 0
