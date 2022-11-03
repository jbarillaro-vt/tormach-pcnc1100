# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import os
import sys
import subprocess


def change_grub_to_vga_terminal():
    #
    # found that on the Gigabyte Brix controllers that some touchscreens when
    # connected by VGA would hang the Brix on boot.
    # for some reason grub trying to use the default PP 2.x VESA graphics mode of
    # grub exposed some bug between the VGA hardware on the motherboard and the
    # VGA implementation in the monitor.  Sigh.
    # so dig into the grub file and change things this way.
    #     comment out GRUB_GFXMODE line
    #     set GRUB_TERMINAL_OUTPUT="vga_text"
    #
    # we run this on every boot so it only rewrites the file and runs update-grub
    # if it has to.

    filename = '/etc/default/grub'

    grub_needs_updating = False

    with open(filename, "r") as ff:
        lines = ff.readlines()
        ff.close()

    gto_line_ok = False

    for ix in xrange(len(lines)):
        line = lines[ix].strip()
        # ignore blank lines
        if len(line) == 0:
            continue

        if line.find('GRUB_TERMINAL_OUTPUT') != -1:
            if gto_line_ok:
                # we already did this once before so there must be multiple
                # lines for GRUB_TERMINAL_OUTPUT, nuke this one and replace with a blank line so iteration isn't thrown off
                lines[ix] = '\n'
                grub_needs_updating = True
            else:
                ii = line.find('=')
                value = ''
                if ii != -1:
                    value = line[ii+1:].strip()
                if line[0] == '#' or value != '"vga_text"':
                    # replace this line with the value we want
                    lines[ix] = 'GRUB_TERMINAL_OUTPUT="vga_text"\n'
                    grub_needs_updating = True
                gto_line_ok = True
                continue

        # ignore comments
        if line[0] == '#':
            continue

        if line.find('GRUB_GFXMODE') != -1 or line.find('GRUB_TERMINAL') != -1:
            # found these uncommented, must comment them out
            lines[ix] = '#' + line + '\n'
            grub_needs_updating = True
            continue

    if not gto_line_ok:
        lines.append('\nGRUB_TERMINAL_OUTPUT="vga_text"\n')
        grub_needs_updating = True

    if grub_needs_updating:
        tmpfilename = '/tmp/grub.tmp'
        with open(tmpfilename, "w") as ff:
            ff.writelines(lines)
            ff.close()

        cmd = "sudo mv {} {}".format(tmpfilename, filename)
        print cmd
        rc = subprocess.call(cmd, shell=True)
        cmd = "sudo update-grub"
        print cmd
        rc = subprocess.call(cmd, shell=True)

        print '{} patched to change terminal output = vga_text on boot and ran update-grub which returned {:d}'.format(filename, rc)

    else:
        print '{} already configured for terminal output = vga_text on boot, no patch needed'.format(filename)


if __name__ == "__main__":
    change_grub_to_vga_terminal()
    sys.exit(0)
