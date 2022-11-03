# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

try:
    import wingdbstub
except ImportError:
    pass


from constants import *
import errors
import gremlin
from ui_common import set_current_notebook_page_by_id


class Tormach_Gremlin_Base(gremlin.Gremlin):

    def __init__(self, ui, width, height):
        gremlin.Gremlin.__init__(self, ui.inifile)
        self.ui = ui
        self.status = ui.status
        self.set_size_request(width, height)

    def destroy(self):
        gremlin.Gremlin.destroy(self)
        self.ui = None
        self.status = None

    def report_gcode_warnings(self, warnings, filename, suppress_after = 3):
        """ Show the warnings from a loaded G code file.
        Accepts a list of warnings produced by the load_preview function, the
        current filename, and an optional threshold to suppress warnings after.
        """
        num_warnings = len(warnings)
        if num_warnings > 0:
            # Find the maximum number of warnings to print
            max_ind = min(max(suppress_after, 0), num_warnings)

            # Find out how many we're suppressing if any
            num_suppressed = max(num_warnings-max_ind,0)

            # warn, but still switch to main page if loading the file
            set_current_notebook_page_by_id(self.ui.notebook, 'notebook_main_fixed')

            #Iterate in reverse to print a coherent list to the status window, which shows most recent first
            if num_suppressed:
                self.ui.error_handler.write("Suppressed %d more warnings" % num_suppressed, ALARM_LEVEL_LOW)
            else:
                if num_warnings > 1:
                    self.ui.error_handler.write("*** End of warning list ***", ALARM_LEVEL_LOW)

            for w in warnings[max_ind::-1]:
                # Add a space to show that the warning is part of the list
                self.ui.error_handler.write("     "+w, ALARM_LEVEL_LOW)

            # Was the preview clipped on load?
            for w in warnings:
                if "ADMIN SET_PREVIEW_LIMIT" in w:
                    self.ui.gcode_file_clipped_load = True
                    self.ui.preview_clipped_label.show()
                    if num_suppressed > 0:
                        # If the preview is clipped because the number of g-code lines is larger than the preview line limit,
                        # that's really important to let the operator know, but it might be hidden with the suppression thing.
                        self.ui.error_handler.write("     "+w, ALARM_LEVEL_LOW)
                    break

            warning_header = "G-Code warnings in %s " % os.path.basename(filename) + ":"
            self.ui.error_handler.write(warning_header, ALARM_LEVEL_LOW)

            self.ui.interp_alarm = True

