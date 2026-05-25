# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

# load_mat_to_lpddr.tcl
#
# Usage:
# system-console --script load_mat_to_lpddr.tcl <input_file.bin> <base_addr> ?chunk_size_bytes?
#
# Example:
# system-console --script load_mat_to_lpddr.tcl data_in.bin 0x01e84800 4096

if {$argc < 2} {
    puts "TCL_ERROR Usage: load_mat_to_lpddr.tcl <input_file.bin> <base_addr> ?chunk_size_bytes?"
    exit 1
}

set input_file    [lindex $argv 0]
set base_addr_str [lindex $argv 1]

if {$argc >= 3} {
    set chunk_size [expr {[lindex $argv 2]}]
} else {
    set chunk_size 4096
}

if {$chunk_size <= 0} {
    puts "TCL_ERROR chunk_size must be > 0"
    exit 1
}

if {![file exists $input_file]} {
    puts "TCL_ERROR input file does not exist: $input_file"
    exit 1
}

set base_addr [expr {$base_addr_str}]

puts "INFO input_file = $input_file"
puts "INFO base_addr  = [format 0x%08X $base_addr]"
puts "INFO chunk_size = $chunk_size"
flush stdout

# Read binary file
if {[catch {
    set f [open $input_file r]
    fconfigure $f -translation binary
    set raw [read $f]
    close $f
} err]} {
    puts "TCL_ERROR failed to read input file"
    puts "TCL_ERROR $err"
    exit 1
}

set total_size [string length $raw]
puts "INFO total_size = $total_size"
flush stdout

if {$total_size == 0} {
    puts "TCL_ERROR input file is empty"
    exit 1
}

# Get and open JTAG-to-Avalon-MM master
if {[catch {
    set masters [get_service_paths master]
} err]} {
    puts "TCL_ERROR get_service_paths master failed"
    puts "TCL_ERROR $err"
    exit 1
}

if {[llength $masters] == 0} {
    puts "TCL_ERROR no master service found"
    exit 1
}

set master [lindex $masters 0]
puts "INFO master = $master"
flush stdout

if {[catch {
    open_service master $master
} err]} {
    puts "TCL_ERROR open_service master failed"
    puts "TCL_ERROR $err"
    exit 1
}

# Write chunks
for {set offset 0} {$offset < $total_size} {incr offset $chunk_size} {
    set remaining [expr {$total_size - $offset}]
    set this_size [expr {$remaining < $chunk_size ? $remaining : $chunk_size}]
    set addr [expr {$base_addr + $offset}]

    set chunk [string range $raw $offset [expr {$offset + $this_size - 1}]]

    # Convert binary string to unsigned byte list for master_write_memory
    binary scan $chunk cu* data

    if {[catch {
        master_write_memory $master $addr $data
    } err]} {
        puts "TCL_ERROR master_write_memory failed"
        puts "TCL_ERROR offset=$offset size=$this_size addr=[format 0x%08X $addr]"
        puts "TCL_ERROR $err"
        flush stdout

        catch {close_service master $master}
        exit 1
    }

    set done [expr {$offset + $this_size}]

    # Machine-readable progress only.
    # Python parses this. Do not print CHUNK every time.
    puts "PROGRESS_BYTES $done $total_size $offset $this_size [format 0x%08X $addr]"
    flush stdout
}

catch {close_service master $master}

puts "DONE"
flush stdout
