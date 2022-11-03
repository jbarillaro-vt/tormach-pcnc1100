#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# T1 P1 Z+1.559766 ;

import sys
import os
import shutil
import stat
import fileinput
import constants
import errors

_eh = errors.error_handler_base()

TEMP_FILE = '/tmp/tool.tbl'

#template for creating a geo offset or wear offset lathe tool (we need both)
LATHE_WEAR_TOOL_TEMPLATE = 'T%d P%d D0.031500 Q9 ;\n'
LATHE_GEO_TOOL_TEMPLATE = 'T%d P%d ; none;\n'

EMPTY_MILL_ENTRY = ';'


# full path to tool table file in argv[1]

def generate_empty_mill_tool_table(fname):
    # if the file "tool.tbl" file is present in same directory
    # use tool info from it to populate entries 1-256 of new, larger tool table
    # this is only going to happen once as entries 1-256 get put in tool.tbl
    # after exit of LinuxCNC to stay compatible with older releases
    path2fname, basename = os.path.split(fname)

    with open(fname, mode="w") as f:

        tool_tbl_fname = os.path.join(path2fname, 'tool.tbl')
        if os.path.exists(tool_tbl_fname) and os.path.isfile(tool_tbl_fname):
            _eh.log('Found existing tool.tbl file %s, will migrate to %s' % (tool_tbl_fname, fname))
            from_file = open(tool_tbl_fname)
            for n in range(1, 256 + 1):
                f.write(from_file.read())
            start_line = 257
        else:
            start_line = 1

        # create empty tool table
        _eh.log('Creating %s entries for tools %d through %d in %s' % (constants.MAX_NUM_MILL_TOOL_NUM, start_line, constants.MAX_NUM_MILL_TOOL_NUM, fname))
        for n in range(start_line, constants.MAX_NUM_MILL_TOOL_NUM + 1):
            f.write('T%d P%d D0.0 Z0.0 ;\n' % (n, n))
        f.close()

def generate_empty_4axes_tool_table(fname):
    path2fname, basename = os.path.split(fname)

    with open(fname, mode="w") as f:

        tool_tbl_fname = os.path.join(path2fname, 'tool.tbl')
        start_line = 1
        # create empty tool table
        _eh.log('Creating %s entries for tools %d through %d in %s' % (constants.MAX_NUM_MILL_TOOL_NUM, start_line, constants.MAX_NUM_MILL_TOOL_NUM, fname))
        for n in range(start_line, constants.MAX_NUM_MILL_TOOL_NUM + 1):
            f.write('T%d P%d D0.0 Z0.0 ;\n' % (n, n))
        f.close()

def generate_empty_lathe_tool_table(fname):
    with open(fname, "w") as f:
        f.write('T1 P1 D0.0 I-85.000000 J-5.000000 Q2 ;\n')
        for n in range(2, constants.MAX_LATHE_TOOL_NUM + 1):
            f.write(LATHE_WEAR_TOOL_TEMPLATE % (n, n))
        f.write('T10001 P%d X-0.500000 Z-0.200000 I+3.000000 ; none\n' % (constants.MAX_LATHE_TOOL_NUM + 1))
        for n in range(2, constants.MAX_LATHE_TOOL_NUM + 1):
            f.write(LATHE_GEO_TOOL_TEMPLATE % (10000 + n, n + constants.MAX_LATHE_TOOL_NUM))
        f.close()


def backport_256_tools(fname):
    _eh.log('Back porting tools 1-256 to old mill tool.tbl file')

    path2fname, basename = os.path.split(fname)
    tool_tbl_fname = os.path.join(path2fname, 'tool.tbl')
    tmp = open(tool_tbl_fname, 'w')
    lineno = 1
    for line in fileinput.input(fname):
        try:
            (tool, pocket, remainder) = line.split(None, 2)
            # get rid of trailing newline
            remainder = remainder.rstrip()
            # _eh.log('tool: "%s" pocket: "%s" remainder: "%s"' % (tool, pocket, remainder))
            # peel number from Tnn string
            try:
                tool_num = int(tool[1:])

                #print 'tool_num: %d' % tool_num
                if tool_num > 256:
                    print('stopping at tool %d' % tool_num)
                    break
                else:
                    #print line
                    tmp.write(line)

            except:
                _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

        except:
            # split failed - empty line?
            _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

        lineno += 1

    fileinput.close()
    tmp.close()


def scan_mill_tool_table(fname):
    _eh.log('Scanning mill tool table')

    # if the file 'tool.tbl' file is present in same directory as INI tool table file
    # and 'tool.tbl' is not the actual INI tool table file (like in a 256 tool version of PathPilot)
    # and 'tool.tbl' timestamp is newer than the INI tool table then:
    # use tool info from it to populate entries 1-256 of new, larger tool table
    # this will happen every time PathPilot starts because as PathPilot shuts down
    # it back ports entries 1-256 into tool.tbl to keep tool info consistent should
    # the user revert to an olders version that chokes on more than ~284 tool entries
    path2fname, basename = os.path.split(fname)
    tool_tbl_fname = os.path.join(path2fname, 'tool.tbl')
    if (fname != tool_tbl_fname) and os.path.exists(tool_tbl_fname) and os.path.isfile(tool_tbl_fname):
        tool_tbl_mtime = os.stat(tool_tbl_fname).st_mtime
        fname_mtime = os.stat(fname).st_mtime
        if fname_mtime > tool_tbl_mtime:
            # an orderly shutdown migrates tools 1-256 back to tool.tbl hence making it newer.
            # if tool.tbl isn't newer then don't migrate to the INI tool table file
            _eh.log('Existing 1-256 tool.tbl file %s is older than INI file %s. Not migrating 1-256 tool data.' % (tool_tbl_fname, fname))
        else:
             # tool.tbl exists and is newer than the INI tool table file
            _eh.log('Found existing 1-256 tool.tbl file %s, will migrate data to %s' % (tool_tbl_fname, fname))

            # keep track of the tools we've seen to detect duplicates if the file was hand edited or previously corrupted somehow
            tool_dict = {}
            lineno = 1
            expected_tool_num = 1

            # tool info contains the tool table line for each tool number
            tool_info = {}
            for line in fileinput.input(tool_tbl_fname):
                try:
                    (tool, pocket, remainder) = line.split(None, 2)
                    # get rid of trailing newline
                    remainder = remainder.rstrip()
                    # _eh.log('tool: "%s" pocket: "%s" remainder: "%s"' % (tool, pocket, remainder))
                    # peel number from Tnn string
                    try:
                        tool_num = int(tool[1:])
                        if tool_num != expected_tool_num:
                            _eh.log('Line {} has tool {} but expected tool {}'.format(lineno, tool_num, expected_tool_num))
                        expected_tool_num = tool_num + 1

                        if tool_num in tool_dict:
                            _eh.log('Line {} is a duplicate for tool {} that was previously seen on line {}'.format(lineno, tool_num, tool_dict[tool_num]))

                        tool_dict[tool_num] = lineno

                        # remember the line to later copy to new file
                        tool_info[tool_num] = line

                        if tool_num == 256:
                            # done, stop processing this file
                            break

                    except:
                        _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

                except:
                     # split failed - empty line?
                    _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

                lineno += 1
            fileinput.close()

            # now that tool.tbl has been read, replace the current tool table file's entries for 1-256 with these
            tmp = open(TEMP_FILE, 'w')
            lineno = 1
            for tool_num in range(1, 256 + 1):
                tmp.write(tool_info[tool_num])

            for line in fileinput.input(fname):
                try:
                    (tool, pocket, remainder) = line.split(None, 2)
                    # get rid of trailing newline
                    remainder = remainder.rstrip()
                    # _eh.log('tool: "%s" pocket: "%s" remainder: "%s"' % (tool, pocket, remainder))
                    # peel number from Tnn string
                    try:
                        tool_num = int(tool[1:])
                        if tool_num < 257:
                            # ignore info for 1-256
                            continue

                        if tool_num <= constants.MAX_NUM_MILL_TOOL_NUM:
                            tmp.write(line)

                    except:
                        _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

                except:
                    # split failed - empty line?
                   _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

            fileinput.close()
            tmp.close()

            # replace old table with new
            os.rename(fname, fname + '.old')
            shutil.copyfile(TEMP_FILE, fname)

    # process existing INI tool table file for inconsistencies

    # count the tools in the file
    lineno = 1
    expected_tool_num = 1
    highest_tool_num = 0
    must_move_t99 = False
    t99_data = ''

    # keep track of the tools we've seen to detect duplicates if the file was hand edited or previously corrupted somehow
    tool_dict = {}

    for line in fileinput.input(fname):
        try:
            (tool, pocket, remainder) = line.split(None, 2)
            # get rid of trailing newline
            remainder = remainder.rstrip()
            # _eh.log('tool: "%s" pocket: "%s" remainder: "%s"' % (tool, pocket, remainder))
            # peel number from Tnn string
            try:
                tool_num = int(tool[1:])
                if tool_num != expected_tool_num:
                    _eh.log('Line {} has tool {} but expected tool {}'.format(lineno, tool_num, expected_tool_num))
                expected_tool_num = tool_num + 1

                if tool_num in tool_dict:
                    _eh.log('Line {} is a duplicate for tool {} that was previously seen on line {}'.format(lineno, tool_num, tool_dict[tool_num]))

                tool_dict[tool_num] = lineno

                if tool_num > highest_tool_num:
                    highest_tool_num = tool_num

                if tool == 'T99' and pocket == 'P55':
                    # we have to fix this file - its ancient from Fall of 2014.
                    t99_data = remainder
                    must_move_t99 = True
            except:
                _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

        except:
            # split failed - empty line?
            _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

        lineno += 1

    _eh.log('highest tool number: %d' % (highest_tool_num))

    if highest_tool_num == constants.MAX_NUM_MILL_TOOL_NUM:
        # all is well - nothing to do
        _eh.log('tool table is already up to date')

    else:
        _eh.log('Modifying tool table for %d entries' % (constants.MAX_NUM_MILL_TOOL_NUM))
        tmp = open(TEMP_FILE, 'w')
        lineno = 1
        for line in fileinput.input(fname):
            try:
                (tool, pocket, remainder) = line.split(None, 2)
                # get rid of trailing newline
                remainder = remainder.rstrip()
                # _eh.log('tool: "%s" pocket: "%s" remainder: "%s"' % (tool, pocket, remainder))
                # peel number from Tnn string
                try:
                    tool_num = int(tool[1:])

                    if tool == "T99" and pocket == "P55":
                        _eh.log('replacing T99 offset')
                        tmp.write('T%d P%d %s\n' % (tool_num, tool_num, t99_data))
                        must_move_t99 = False   #  just did it
                    else:
                        # copy to new file
                        tmp.write('%s %s %s\n' % (tool, pocket, remainder))

                except:
                    _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))

            except:
                # split failed - empty line?
                _eh.log('Skipping corrupt tool number line {}: {}'.format(lineno, line))
            lineno += 1

        for num in range(highest_tool_num + 1, constants.MAX_NUM_MILL_TOOL_NUM + 1):
            # fill in as 0.0
            if must_move_t99 and num == 99:
                _eh.log('replacing T99 offset')
                tmp.write('T%d P%d %s\n' % (num, num, t99_data))
            else:
                tmp.write('T%d P%d %s\n' % (num, num, EMPTY_MILL_ENTRY))

        tmp.close()

        # replace old table with new
        os.rename(fname, fname + '.old')
        os.rename(TEMP_FILE, fname)


def scan_lathe_tool_table(fname):
    _eh.log("Scanning lathe tool table")
    #collect all wear offset tools (T1+) and geo offset tools (T10001+)
    wear_tools = {}
    geo_tools = {}
    for line in fileinput.input(fname):
        try:
            (tool, pocket, remainder) = line.split(None, 2)
            # _eh.log('tool: "%s" pocket: "%s" remainder: "%s"' % (tool, pocket, remainder))
            # peel number from Tnn string
            try:
                tool_num = int(tool[1:])
            except:
                tool_num = -1
            if tool_num < 10001:
                wear_tools[tool_num] = line
            else:
                #we'd have to replace the tnum and pocket, so just save the important part of the tool
                geo_tools[tool_num - 10000] = remainder
        except:
            pass
    #Do some checks for expected tools. This will catch missing tools
    #There are still some extra cases that aren't caught here, like someone adding tools
    #outside of the expected_tools set
    expected_tools = set(range(1, constants.MAX_LATHE_TOOL_NUM + 1))
    missing_wear_tools = expected_tools - set(wear_tools.keys())
    missing_geo_tools = expected_tools - set(geo_tools.keys())
    #if either set has tools missing from the other, we have a broken tool table.
    if len(missing_wear_tools ^ missing_geo_tools) != 0:
        _eh.log("Broken tool table: Has mismatched wear and geometric tools. Replacing it.")
        os.rename(fname, fname + '.broken')
        generate_empty_lathe_tool_table(fname)

    if(len(missing_geo_tools)):
        _eh.log("Lathe tool table is missing items. Adding them now and moving current file to *.old.")
        #since the missing sets are the same, we can use either one to populate the missing tools
        for t_num in missing_geo_tools:
            wear_tools[t_num] = LATHE_WEAR_TOOL_TEMPLATE % (t_num, t_num)
            geo_tools[t_num] = "; none;\n"
        with open(TEMP_FILE, 'w') as tmp:
            for tool_num, line in wear_tools.iteritems():
                tmp.write(line)
            #we need to replace the existing pocket numbers for the geo tools,
            #because they will be counting up from the wrong offset
            for tool_num, remainder in geo_tools.iteritems():
                tmp.write("T%d P%d %s" % (tool_num + 10000, constants.MAX_LATHE_TOOL_NUM + tool_num, remainder))
        os.rename(fname, fname + '.old')
        os.rename(TEMP_FILE, fname)

    else:
        _eh.log("Lathe tool table looks fine. Not making changes.")


if __name__ == "__main__":

    if len(sys.argv) < 3:
        _eh.log('missing argument: <tool table file> <machine type (mill|lathe)>')
        sys.exit(1)

    # typically /home/operator/mill_data/tool.tbl
    tool_tbl = sys.argv[1]
    machine_type = sys.argv[2]

    _eh.log('tool file is %s' % tool_tbl)
    _eh.log('machine type is %s' % machine_type)

    # pathpilotmanager.py calls this after LinuxCNC and the UI exits
    # this will back migrate tool info 1-256 back to ~/mill_data/tool.tbl
    # this lets older versions of PP continue to run correctly with the most accurate
    # tool table.  we can eventually kill this behavior once it is impossible to back
    # up to a version of PP that only supported 256 tools.
    if machine_type == 'mill' and len(sys.argv) == 4 and sys.argv[3] == 'update-256':
        backport_256_tools(tool_tbl)
        sys.exit(0)

    file_exists = os.path.isfile(tool_tbl)
    if not file_exists:
        _eh.log('generating empty '+machine_type+' tool table')
        if machine_type == 'mill':
            generate_empty_mill_tool_table(tool_tbl)
        elif machine_type == 'lathe':
            generate_empty_lathe_tool_table(tool_tbl)
        else:
            generate_empty_4axes_tool_table(tool_tbl)
    else:
        if machine_type == 'mill':
            scan_mill_tool_table(tool_tbl)
        elif machine_type == 'lathe':
            scan_lathe_tool_table(tool_tbl)

    sys.exit(0)
