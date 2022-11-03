#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import sys
import os
import re
import datetime
from iniparse import SafeConfigParser
from iniparse.ini import LineContainer, OptionLine
import constants
import json

# This is passed the config dictionary generated from reading ~/pathpilot.json file which
# config_picker.py creates.
#
# Most of the linuxcnc configurations start with a specific ini file with just a few parameters and
# then point to a base ini file which holds the common parameters for an entire class of machines.
#
# The machine.generate_from key in the pathpilot.json file holds the specific ini file name.
# Inside the specific ini file is a key which points to the base ini file - example:
#
# [INI_CONFIG]
# BASE_INI_FILE = tormach_mill_base.ini
#
# [EMC]
# MACHINE = 1100-2
#
# [AXIS_0]
# MAX_VELOCITY = 1.500
# MAX_ACCELERATION = 9.0
#
# Where [INI_CONFIG]BASE_INI_FILE indicates we are to start with the contents of the file
# 'tormach_mill_base_ini' and replace item [EMC]MACHINE with the value "1100-2" and other
# differences between the base INI file which is actually for an 1100-3 such as faster axis
# speeds.
#
# RapidTurn adds complexity of course.
#
# For simplicity, there are 4 relevant keys in the pathpilot.json file and machine.rapidturn
# tells everyone which pair of keys to use like this:
#
#    if machine.rapidturn
#       machine.rapidturn_generate_from
#       machine.rapidturn_linuxcnc_filepath
#    else
#       machine.generate_from
#       machine.linuxcnc_filepath
#
# When the UI needs to switch from mill to rapidturn or vice versa, it ONLY flips the value
# of machine.rapidturn. It doesn't re-create filepaths.
#
# RapidTurn mode not only specifys a different UI to start, but also the linuxcnc INI file
# must swap the mill hardware X and Z axes such that they behave as expected in the
# lathe UI. There are other difference to account for such as limit switches,
# door/guard switch, spindle speeds, etc.
#


class IniFactory():
    def __init__(self):
        self.source_filelist = []

    def make_ini_file(self, configdict):

        assert configdict["fileversion"] == 2, "Unexpected pathpilot.json file version"

        # sanity check and deal with INI file path almost certainly starts with ~/
        if configdict["machine"]["rapidturn"] is True:
            assert configdict["machine"]["rapidturn_generate_from"] is not None, "Why is make_ini_file being called when pathpilot.json is not expecting generation?"
            generate_filepath = os.path.expanduser(configdict["machine"]["rapidturn_generate_from"])
            linuxcnc_filepath = os.path.expanduser(configdict["machine"]["rapidturn_linuxcnc_filepath"])
        else:
            assert configdict["machine"]["generate_from"] is not None, "Why is make_ini_file being called when pathpilot.json is not expecting generation?"
            generate_filepath = os.path.expanduser(configdict["machine"]["generate_from"])
            linuxcnc_filepath = os.path.expanduser(configdict["machine"]["linuxcnc_filepath"])

        # test if generation source file exists
        if not os.path.exists(generate_filepath):
            print 'file not found: %s' % generate_filepath
            return 1

        # parse up the specific INI file
        generate_filepath = os.path.abspath(generate_filepath)
        self.source_filelist.append(generate_filepath)
        cp_specific = self.process_includes_and_read(generate_filepath)

        cp_base_filename = ''

        # Make BASE_INI_FILE optional, in case #pp_include style composition is being used
        if cp_specific.has_section('INI_CONFIG') and cp_specific.has_option('INI_CONFIG', 'BASE_INI_FILE'):
            # pluck the base INI file out of the specific one
            cp_base_filename = cp_specific.get('INI_CONFIG', 'BASE_INI_FILE')
            cp_base_filepath = os.path.join(os.path.dirname(generate_filepath), cp_base_filename)

            # test if base file exists
            if not os.path.exists(cp_base_filepath):
                print 'file not found: %s' % cp_base_filepath
                return 1

            self.source_filelist.append(cp_base_filepath)
            cp_base = self.process_includes_and_read(cp_base_filepath)

            # replace or add sections/items
            for section in cp_specific.sections():
                if section != 'INI_CONFIG':
                    for item, value in cp_specific.items(section):
                        #print('makeini.py: replacing [%s]%s with: %s' % (section, item, value))
                        if not cp_base.has_section(section):
                            # add missing section before setting value
                            # item must be upper case
                            #print('makeini.py: adding missing section [%s]' % section)
                            cp_base.add_section(section)
                        # set new value
                        #print('makeini.py: setting [%s]%s to: %s' % (section, item, value))
                        cp_base.set(section, item.upper(), value)
        else:
            cp_base = cp_specific

        # Finally, convert remap sections into the REMAP= that linuxcnc expects
        self.convert_remap_sections(cp_base)

        # Now write out the INI file to a temp file because it will include all the comments from
        # the base file.  These can be really confusing since any individual key could be from some other file
        # right below the comment.  So we make a pass and brute force leave behind any comment lines.
        with open(linuxcnc_filepath + '.tmp', 'w') as fp:
            # write INI contents
            cp_base.write(fp)
        final_lines = []
        with open(linuxcnc_filepath + '.tmp', 'r') as fp:
            while True:
                line = fp.readline()
                if not line:
                    break
                testline = line.lstrip()
                if testline.startswith('#') or testline.startswith(';'):
                    continue
                final_lines.append(line)
        os.remove(linuxcnc_filepath + '.tmp')

        # Now write out the actual final generated file which only has the comment at the very top.
        with open(linuxcnc_filepath, 'w') as fp:
            fp.write('#\n')
            fp.write('# This file is machine generated. Do not edit.\n')
            fp.write('# Date generated: %s\n' % datetime.date.today())
            fp.write('# Created from files:\n')
            for name in self.source_filelist:
                fp.write('#     %s\n' % name)
            fp.write('#\n')
            fp.write('# Model: %s' % configdict["machine"]["model"])

            if configdict["machine"]["rapidturn"] is True:
                fp.write(' in RapidTurn lathe mode\n#\n\n')
            else:
                fp.write('\n')
                fp.write('#\n')
                fp.write('\n')

            for line in final_lines:
                fp.write(line)

        return 0

    # Process any "#pp_include filename" values in the given config file
    #
    # Filenames are relative to the directory config_fname is in
    #
    # A #pp_include= directive merges the sections in the included files into config_fname
    # ***but it does not replace values already present in the given config_file***
    # in that way, #include is different from the BASE_INI_FILE which merges
    # the specific_ini_file into base_ini_file and also overwrites values in the base
    #
    # The logic behind this is that #include directives can contain a set of sane defaults for
    # one or more sections, and you might only need to specifically define a few that might be different
    # than what's in the included file.
    #
    # Returns a config parser with the contents of config_fname and any included files
    def process_includes_and_read(self, config_fname):
        config_fname_abspath = os.path.abspath(config_fname)

        cp = SafeConfigParser()
        cp.read(config_fname_abspath)

        current_dir = os.path.dirname(config_fname_abspath)

        with open(config_fname_abspath) as config_file:
            file_contents = config_file.read()

        regex = r"^#pp_include\s*(.*\.inc)$"

        matches = re.finditer(regex, file_contents, re.MULTILINE)

        for matchNum, match in enumerate(matches):
            include_fname = match.groups()[0]
            include_fname_abspath = os.path.abspath(os.path.join(current_dir, include_fname))
            self.source_filelist.append(include_fname_abspath)
            cp_include = self.process_includes_and_read(include_fname_abspath)

            # update or add sections/items
            for section in cp_include.sections():
                if section != 'INI_CONFIG':
                    for item, value in cp_include.items(section):
                        if not cp.has_section(section):
                            cp.add_section(section)
                        #only set included item if value does not already exist in cp
                        if not cp.has_option(section, item):
                            cp.set(section, item.upper(), value)

        return cp

    # Linuxcnc has a rather nasty abuse of the .ini format where remaps are defined by creating
    # multiple values with the REMAP= key in the RS274NGC section
    #
    # This does not play nice with .ini composition using #pp_include, or really any other ini tools
    #
    # To avoid this, we look for sections named [REMAP_<code>] and use the keys and values in that section
    # to create the REMAP=M6 modalgroup=6 prolog=change_prolog ngc=change epilog=change_epilog style
    # key values in the RS274NGC section
    #
    # This is the very last step in the PP config processing, so that every other step can
    # rely on the rules of the .ini file being intact
    def convert_remap_sections(self, cp):
        regex = r"REMAP_([a-zA-Z]\d+)"

        if not cp.has_section("RS274NGC"):
            cp.add_section("RS274NGC")

        rs274_section = cp.data._getitem("RS274NGC")

        for section in cp.sections():
            re_match = re.match(regex, section)
            if re_match:
                remap_code = re_match.groups()[0]
                remap_string = remap_code + " "
                for item, value in cp.items(section):
                    remap_string += "{}={} ".format(item,value)
                rs274_section._lines[-1].add(LineContainer(OptionLine("REMAP", remap_string)))
                cp.remove_section(section)


    def print_cp(self, cp):
        for section in cp.sections():
            print 'Section: ', section
            for item, value in cp.items(section):
                print '  %s = %s' % (item, value)


if __name__ == "__main__":
    exitcode = 1

    # read in the pathpilot.json into a config dictionary
    if os.path.exists(constants.PATHPILOTJSON_FILEPATH):
        try:
            with open(constants.PATHPILOTJSON_FILEPATH, 'r') as jsonfile:
                config = json.load(jsonfile)
                exitcode = IniFactory().make_ini_file(config)
                if exitcode == 0:
                    print 'Generated linuxcnc ini file.'
                else:
                    print 'Failed to generate linuxcnc ini file.'
        except IOError:
            print "IOError exception trying to read", constants.PATHPILOTJSON_FILEPATH
    else:
        print "{:s} does not exist so nothing to do.".format(constants.PATHPILOTJSON_FILEPATH)

    sys.exit(exitcode)
