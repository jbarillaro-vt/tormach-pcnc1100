#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
#
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------



import os
import sys
import re
import string
import json
import subprocess
import constants
import errors
import datetime
import locale

# Do not try to parse this yourself - use the version manager singleton
_LEGACY_VERSION_FILENAME = "version.txt"

# Singleton accessor
version_mgr_singleton = None
def GetVersionMgr():
    global version_mgr_singleton
    if version_mgr_singleton is None:
        version_mgr_singleton = VersionMgr(constants.LINUXCNC_HOME_DIR)
    return version_mgr_singleton

'''
This module is used by PathPilot, but is also invoked directly as part of the build process to
increment build numbers and figure out tarball names.
'''
class VersionMgr():

    def __init__(self, directory):
        self._expiration_warning = None
        self._expired = False
        self.error_handler = errors.error_handler_base()

        # These are ALL the settings that get written to the json file.
        self.version = { "version" : "v2.0.0",   # manually changed by marketing decision, not automated at all
                         "status"  : "???",      # usually empty, but could be "beta" or something else, displayed as a -suffix in UI
                         "build"   : 0,
                         "branch"  : "",
                         "tag"     : "",
                         "commit"  : "",
                         "expires" : "",
                         "kernels" : [""] }

        self.filepath = os.path.join(directory, "version.json")
        self.legacyfilepath = os.path.join(directory, _LEGACY_VERSION_FILENAME)

        try:
            with open(self.filepath, 'r') as jsonfile:
                self.version = json.load(jsonfile)
        except IOError:
            # file not present or unreadable
            self.error_handler.log("Using defaults for version information as %s did not exist." % self.filepath)


    def _run_cmd(self, cmd):
        result = ''
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True,)
            (result, error) = p.communicate()
            if p.returncode != 0:
                print 'Cmd failure: %s returned %d' % (cmd, p.returncode)
        except subprocess.CalledProcessError:
            print 'Failed to run %s' % cmd
        return result


    def _update_git_keys(self):
        result = self._run_cmd("git status --short --porcelain --branch")
        # Example output is:   ## feature/jessie...origin/feature/jessie
        firstline = string.split(result, "\n", 1)[0]
        self.version["branch"] = string.split(firstline)[1]

        result = self._run_cmd("git log --max-count=1 --pretty=oneline")
        # Example output is:   8dc968763a6c662d957e9a9ab59ba5229d798232 This is the commit message.
        self.version["commit"] = string.split(result, maxsplit=1)[0]

        result = self._run_cmd('git describe --always --match "v*"')
        # Example output is:  v2.0.0-beta8-5-g8dc96876
        self.version["tag"] = result.strip()


    def get_kernel_mismatch_warning_msg(self):
        '''
        Return None if the kernel is an expected and supported version
               String for warning message when it isn't.
        '''
        # check kernel release version match
        warning_msg = None
        supported_kernel = False
        kernel_version = (subprocess.check_output("uname -r", shell=True)).strip()
        for v in self.version["kernels"]:
            if v == kernel_version:
                supported_kernel = True
                break
        if not supported_kernel:
            warning_msg = "PathPilot {} does not support this Linux kernel version {}.  Contact Tormach for help.".format(self.get_display_version(), kernel_version)
            self.error_handler.log(warning_msg)

        return warning_msg


    def parse_legacy_version_string(self, versionstr):
        '''
        Returns a list of [major int, minor int, build int, suffix_string ]
        where suffix_string is usually a blank string
        If string cannot be parsed, it returns [0, 0, 0, '']
        '''

        # version lines to test with for complete coverage
        # we treat the prefix v as optional
        #
        #version = "v1.99.2323"
        #version = "v1.99.2323d"
        #version = "v2.10.20-beta3-81-g00ebd564"
        #version = "v112.0.20b-81-g00ebd564"

        version_list = [0, 0, 0, '']

        # look for a non-release version with the commit hash suffix (with or without the suffix letter messiness)
        # don't bother trying to pull out the suffix letter in this case - we just don't care and
        # aren't using it in the future anyway
        matchlist = re.findall(r'v?(\d+)\.(\d+)\.(\d+)[a-z]*(-.+)', versionstr)
        if len(matchlist) > 0:
            version_list = [ int(matchlist[0][0]), int(matchlist[0][1]), int(matchlist[0][2]), matchlist[0][3] ]

        else:
            # next try a match with the deprecated behavior with suffix letters
            matchlist = re.findall(r'v?(\d+)\.(\d+)\.(\d+)([a-z]+)', versionstr)
            if len(matchlist) > 0:
                # this is an old deprecated version that used suffix letters
                version_list = [ int(matchlist[0][0]), int(matchlist[0][1]), int(matchlist[0][2]), matchlist[0][3] ]

            else:
                # now look for a normal released version
                matchlist = re.findall(r'v?(\d+)\.(\d+)\.(\d+)', versionstr)
                if len(matchlist) > 0:
                    version_list = [ int(matchlist[0][0]), int(matchlist[0][1]), int(matchlist[0][2]), '']

        return version_list


    def parse_legacy_version_file(self, directory):
        filepath = os.path.join(directory, _LEGACY_VERSION_FILENAME)
        with open(filepath, "r") as legacyfile:
            legacyversionline = legacyfile.readline().strip()
            return self.parse_legacy_version_string(legacyversionline)


    def get_display_version(self):
        if self.version["status"] and len(self.version["status"]) > 0:
            return "%s-%s-%d" % (self.version["version"], self.version["status"], self.version["build"])
        else:
            return self.version["version"]


    def get_status(self):
        return self.version["status"]


    def get_internal_build_number(self):
        # Note this isn't the 'c' in 'a.b.c' - that's all marketing names.
        # This is the integer "build" number field of pathpilot.json
        return self.version["build"]


    def get_version_list(self):
        '''
        Returns a list of [major int, minor int, build int, suffix_string ]
        where suffix_string is usually a blank string
        If string cannot be parsed, it returns [0, 0, 0, '']
        '''
        return self.parse_legacy_version_string(self.get_display_version())


    def increment_build(self):
        self.version["build"] += 1
        self._update_git_keys()

        with open(self.filepath, 'w') as jsonfile:
            json.dump(self.version, jsonfile, indent=4, sort_keys=True)
            jsonfile.write("\n")   # make cat'ing the contexts of the file more legible in the shell

        self.write_legacy_version_file()

        print self.get_display_version()


    def write_legacy_version_file(self):
        with open(self.legacyfilepath, 'w') as legacyfile:
            legacyfile.write(self.get_display_version())
            legacyfile.write("\n\n")   # make cat'ing the contexts of the file more legible in the shell
            legacyfile.write("NOTE: this is a legacy file that exists solely for older versions to check\n")
            legacyfile.write("      tarball compatibility.  Do not try to parse verion files directly.\n")
            legacyfile.write("      Use versioning.VersionMgr singleton instead.\n\n")


    def get_debug_version(self):
        # this is just a string dump of the full version.json contents
        with open(self.filepath, 'r') as jsonfile:
            return jsonfile.read()


    def get_expiration_warning(self):
        # run this so it recalcs with the current date
        self.is_build_expired()
        return self._expiration_warning


    def is_build_expired(self):
        # we re-calculate this each call because PP may be left running for days or weeks at a time
        # during which it hits the expiration date.
        try:
            if self.version["expires"] != None and len(self.version["expires"]) > 0:
                # this build has an expiration date
                locale_dateformat_str = locale.nl_langinfo(locale.D_FMT)
                now = datetime.date.today()
                expires = datetime.datetime.strptime(self.version["expires"], "%Y-%m-%d").date()
                self._expired = (now >= expires)
                if self._expired:
                    # We're already expired!
                    self._expiration_warning = "This test version of PathPilot {} expired on {}.\n\nPlease update PathPilot immediately.".format(self.get_display_version(), expires.strftime(locale_dateformat_str))
                else:
                    delta = expires - now
                    if delta.days == 1:
                        self._expiration_warning = "You're using a test version of PathPilot {}, which expires on {} (in {} day).".format(self.get_display_version(), expires.strftime(locale_dateformat_str), delta.days)
                    else:
                        self._expiration_warning = "You're using a test version of PathPilot {}, which expires on {} (in {} days).".format(self.get_display_version(), expires.strftime(locale_dateformat_str), delta.days)
            else:
                self._expiration_warning = None
                self._expired = False
        except KeyError:
            pass

        return self._expired


if __name__ == "__main__":

    # This module is run directly by the build system to read and increment build numbers.
    mgr = VersionMgr(os.getcwd())

    if '--increment' in sys.argv:
        mgr.increment_build()
    else:
        # Even if we are just reading the current version, always re-create the legacy verison.txt file
        # BECAUSE version.json might be changed by git actions and since version.txt is not tracked
        # it could fall out of sync with version.json until the next time a tarball is created
        # and the build number is incremented.
        mgr.write_legacy_version_file()
        print mgr.get_display_version()

    sys.exit(0)
