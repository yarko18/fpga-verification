# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

# read_mat_from_lpddr.tcl
#
# Usage:
# system-console --script read_mat_from_lpddr.tcl <output_file.bin> <base_addr> <total_size_bytes> ?chunk_size_bytes?

if {$argc < 3} {
    puts "TCL_ERROR Usage: read_mat_from_lpddr.tcl <output_file.bin> <base_addr> <total_size_bytes> ?chunk_size_bytes?"
    return -code error "not enough arguments"
}

set output_file   [lindex $argv 0]
set base_addr_str [lindex $argv 1]
set total_size    [expr {[lindex $argv 2]}]

if {$argc >= 4} {
    set chunk_size [expr {[lindex $argv 3]}]
} else {
    set chunk_size 4096
}

if {$chunk_size <= 0} {
    puts "TCL_ERROR chunk_size must be > 0"
    return -code error "bad chunk_size"
}

if {$total_size <= 0} {
    puts "TCL_ERROR total_size must be > 0"
    return -code error "bad total_size"
}

set base_addr [expr {$base_addr_str}]

puts "INFO output_file = $output_file"
puts "INFO base_addr   = [format 0x%08X $base_addr]"
puts "INFO total_size  = $total_size"
puts "INFO chunk_size  = $chunk_size"
flush stdout

if {[catch {
    set masters [get_service_paths master]
} err]} {
    puts "TCL_ERROR get_service_paths master failed"
    puts "TCL_ERROR $err"
    return -code error $err
}

if {[llength $masters] == 0} {
    puts "TCL_ERROR no master service found"
    return -code error "no master service found"
}

set master [lindex $masters 0]
puts "INFO master = $master"
flush stdout

if {[catch {
    open_service master $master
} err]} {
    puts "TCL_ERROR open_service master failed"
    puts "TCL_ERROR $err"
    return -code error $err
}

if {[catch {
    set f [open $output_file w]
    fconfigure $f -translation binary
} err]} {
    puts "TCL_ERROR failed to open output file"
    puts "TCL_ERROR $err"
    catch {close_service master $master}
    return -code error $err
}

for {set offset 0} {$offset < $total_size} {incr offset $chunk_size} {
    set remaining [expr {$total_size - $offset}]
    set this_size [expr {$remaining < $chunk_size ? $remaining : $chunk_size}]
    set addr [expr {$base_addr + $offset}]

    if {[catch {
        set data [master_read_memory $master $addr $this_size]
    } err]} {
        puts "TCL_ERROR master_read_memory failed"
        puts "TCL_ERROR offset=$offset size=$this_size addr=[format 0x%08X $addr]"
        puts "TCL_ERROR $err"
        flush stdout

        catch {close $f}
        catch {close_service master $master}
        return -code error $err
    }

    if {[catch {
        set chunk_bin [binary format cu* $data]
        puts -nonewline $f $chunk_bin
    } err]} {
        puts "TCL_ERROR failed to write output chunk"
        puts "TCL_ERROR offset=$offset size=$this_size addr=[format 0x%08X $addr]"
        puts "TCL_ERROR $err"
        flush stdout

        catch {close $f}
        catch {close_service master $master}
        return -code error $err
    }

    set done [expr {$offset + $this_size}]

    puts "PROGRESS_BYTES $done $total_size $offset $this_size [format 0x%08X $addr]"
    flush stdout
}

close $f
catch {close_service master $master}

puts "DONE"
flush stdout