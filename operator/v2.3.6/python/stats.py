#!/usr/bin/env python

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import os
import subprocess
import time
import json
import fsutil
import re
from datetime import datetime
from constants import *


class StatsMgr():
    def __init__(self, inifile, machine):
        self.machine = machine    # a subclass of TormachUIBase
        self._include_ethernet = False
        self._last_ethernet_stats_sec = None
        self._ethernet_interval_min = 15        # default is every 15 minutes for now

        # get ethernet stats only for configurations using hm2_eth
        hm2drivername = inifile.find("HOSTMOT2", "DRIVER")
        if hm2drivername != None and hm2drivername.startswith('hm2_eth'):
            self._include_ethernet = True
            try:
                interval_min_str = inifile.find("HOSTMOT2", "STATS_INTERVAL_MIN")
                if interval_min_str != None:
                    min = int(interval_min_str)
                    if min > 0:
                        self._ethernet_interval_min = min
            except:
                pass
            self.machine.error_handler.log("Gathering eth0 stats every %d minutes." % self._ethernet_interval_min)

        # this is the data structure for the gcode stat cache
        self.gcodestats = { "version" : 1,      # data structure version
                            "filepaths" : { "template.nc" : { "cycle_sec" : 0, "run_sec" : 0, "size_bytes" : 0, "mtime" : 0, "last_loaded_time" : 0 } }
                          }
        try:
            with open(STATSFILE_BASE_PATH, 'r') as jsonfile:
                possiblestats = json.load(jsonfile)
                if possiblestats['version'] == 1:
                    self.gcodestats = possiblestats
                else:
                    self.machine.error_handler.log("gcode stats reset due to mismatched file version.")
        except IOError:
            # file not present or unreadable
            self.machine.error_handler.log("Using defaults for gcode stats as %s did not exist." % STATSFILE_BASE_PATH)

        # run brute force cache eviction if needed. keep enough around for a few thousand to limit memory consumption.
        filepaths = self.gcodestats['filepaths']
        timenow = time.time()
        evictcount = 0
        while len(filepaths) > 2000:
            # find oldest last loaded time and evict it.
            greatest_delta = 0
            oldest_key = None
            for key, value in filepaths.iteritems():
                delta = timenow - value['last_loaded_time']
                if delta > greatest_delta:
                    greatest_delta = delta
                    oldest_key = key
            del filepaths[oldest_key]
            evictcount += 1

        if evictcount > 0:
            # save the updated stats to disk now that we've evicted some
            self.machine.error_handler.log("Evicted {:d} entries from the gcode timing stats cache.".format(evictcount))
            with open(STATSFILE_BASE_PATH, 'w') as jsonfile:
                json.dump(self.gcodestats, jsonfile, indent=4, sort_keys=True)
                jsonfile.write("\n")   # make cat'ing the contexts of the file more legible in the shell


    def _log_ethernet_stats(self, force):
        if self._include_ethernet:
            now_sec = time.time()

            # has it been at least 15 minutes since the last stats?
            # (or have we never gathered stats yet?)
            if force or self._last_ethernet_stats_sec == None or ((now_sec - self._last_ethernet_stats_sec) > (self._ethernet_interval_min * 60)):
                self._last_ethernet_stats_sec = now_sec
                self.machine.error_handler.log("Gathering eth0 driver stats:")
                retcode = subprocess.call(['/sbin/ethtool -S eth0'], shell=True)


    def maybe_log_stats(self, force=False):
        # force = True will ignore any intervals and log all relevant stats

        # keep this very fast if there isn't anything to do as it gets called frequently
        # from the 0.5 second periodic function whenever the machine isn't busy running
        #  a program or moving around.
        self._log_ethernet_stats(force)


    def get_last_runtime_sec(self):
        display_filename = fsutil.sanitize_path_for_user_display(self.machine.current_gcode_file_path)
        if display_filename in self.gcodestats['filepaths']:
            filedict = self.gcodestats['filepaths'][display_filename]

            # see if the stats we have are relevant or if the file has changed since then.
            try:
                filestat = os.stat(self.machine.current_gcode_file_path)

                if filestat.st_size == filedict['size_bytes'] and filestat.st_mtime == filedict['mtime']:
                    # gcode file is unchanged so any runtime we have cached is still valid.
                    return filedict['run_sec']

            except OSError:
                # the user could delete the file that is currently loaded in the gcode display
                # we've seen that happen in rare situations in the log
                pass

        return 0


    def log_cycle_start(self, line):
        self._log('cycle start, line {:d}'.format(line))


    def _log(self, event_name):
        display_filename = fsutil.sanitize_path_for_user_display(self.machine.current_gcode_file_path)
        dt = datetime.now()
        long_timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        # use CR LF line endings in the log file so that its easy for customers with Windows to use notepad or other editors to
        # browse the file.
        logline = "{:s} | {:s} | {:s} | {:s}\r\n".format(long_timestamp, self.machine.settings.netbios_name, display_filename, event_name)
        with open(GCODELOGFILE_BASE_PATH, 'a') as logfile:
            logfile.write(logline)


    def update_gcode_cycletimes(self):
        # log some stats - this is usually called whenever we stop running a program for any reason from the 500ms periodic.
        display_filename = fsutil.sanitize_path_for_user_display(self.machine.current_gcode_file_path)
        cycle_time = '%02d:%02d:%02d' % (self.machine.hal['cycle-time-hours'], self.machine.hal['cycle-time-minutes'], self.machine.hal['cycle-time-seconds'])
        run_time = '%02d:%02d:%02d' % (self.machine.hal['run-time-hours'], self.machine.hal['run-time-minutes'], self.machine.hal['run-time-seconds'])

        # update our gcode stats cache file which we use to estimate the 'time remaining' for a program.
        #
        # Determine if we stopped due to an M30 or not.
        # Otherwise if the rest of the remaining lines in the gcode file are comments,
        # 'tape end' percent markers, blank numbered lines, or block deletes
        # we call that good enough also.
        lineno = self.machine.status.current_line
        line = self.machine.gcode_pattern_search.get_line_text(lineno).strip()

        # graceful program ends via M02 or M30 are treated the same for timing purposes
        program_end = False
        if self.machine.status.program_ended or self.machine.status.program_ended_and_reset:
            program_end = True
        else:
            # pretend to 'execute' the remaining lines after the current one and see if they are all
            # comments basically.
            comment_re = re.compile(r'(N\d+)?\s*(%|\(.*\)|/.*)', re.I)
            while lineno < self.machine.gcode_last_line:
                lineno += 1
                line = self.machine.gcode_pattern_search.get_line_text(lineno).strip()
                if len(line) > 0 and not comment_re.search(line):
                    # not a comment so back up one and leave lineno representing the 'last executed line'
                    lineno -= 1
                    break

        if program_end or lineno >= self.machine.gcode_last_line:
            # appears that we ran through the whole program so save this run time for later use as an estimate.
            cycle_sec = self.machine.hal['cycle-time-hours']*60*60 + self.machine.hal['cycle-time-minutes']*60 + self.machine.hal['cycle-time-seconds']
            run_sec = self.machine.hal['run-time-hours']*60*60 + self.machine.hal['run-time-minutes']*60 + self.machine.hal['run-time-seconds']

            try:
                filestat = os.stat(self.machine.current_gcode_file_path)
                filedict = {}
                if display_filename in self.gcodestats['filepaths']:
                    filedict = self.gcodestats['filepaths'][display_filename]

                filedict['cycle_sec'] = cycle_sec
                filedict['run_sec'] = run_sec
                filedict['size_bytes'] = filestat.st_size
                filedict['mtime'] = filestat.st_mtime
                filedict['last_loaded_time'] = time.time()   # used for cache eviction

                self.gcodestats['filepaths'][display_filename] = filedict

                # save the updated stats to disk
                with open(STATSFILE_BASE_PATH, 'w') as jsonfile:
                    json.dump(self.gcodestats, jsonfile, indent=4, sort_keys=True)
                    jsonfile.write("\n")   # make cat'ing the contexts of the file more legible in the shell

            except OSError:
                # the user could delete the file that is currently loaded in the gcode display
                # we've seen that happen in rare situations in the log
                pass

            full_or_partial = 'complete run'

        else:
            full_or_partial = 'partial run'
            self.machine.error_handler.log("Current line was %d out of %d so not saving that run time as a future estimate." %
                                           (self.machine.status.current_line, self.machine.gcode_last_line))

        # update the gcode log file
        # m30 now resets the current line to 0 so it looks wrong in the log.  Just omit it in this case so it isn't confusing.
        if self.machine.status.current_line == 0:
            event_details = "program stopped, cycle time {:s}, run time {:s}, {:s}".format(cycle_time,
                run_time, full_or_partial)
            self.machine.error_handler.write("{:s} = cycle time {:s}   run time {:s}".format(display_filename,
                cycle_time, run_time), ALARM_LEVEL_QUIET)
        else:
            event_details = "program stopped, cycle time {:s}, run time {:s}, last line {:d}, {:s}".format(cycle_time,
                run_time, self.machine.status.current_line, full_or_partial)
            self.machine.error_handler.write("{:s} = cycle time {:s}   run time {:s}   last line {:d}".format(display_filename,
                cycle_time, run_time, self.machine.status.current_line), ALARM_LEVEL_QUIET)

        self._log(event_details)
