#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2019 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------


import pygtk
pygtk.require("2.0")
import gtk
import gobject
import sys
import os
import json
import subprocess
import signal
import tempfile
import string
import plexiglass
import popupdlg
import constants
import ui_misc
import pango
import stat
import ConfigParser
from iniparse import SafeConfigParser
from iniparse import NoOptionError
import fsutil
import ui_misc
import versioning

CONFIGCHOOSER_EXITCODE_SUCCESS          = 0
CONFIGCHOOSER_EXITCODE_NOCONFIGSELECTED = 1
CONFIGCHOOSER_EXITCODE_INSTALL_UPDATE   = 3


# look for the .glade file and the resources in a 'images' subdirectory below
# this source file.
GLADE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')


class Machine():
    def __init__(self):
        self.specific_filepath = None
        self.specific_sim_filepath = None
        self.specific_filepath_7i92 = None
        self.machine_class = None
        self.modelname = None
        self.sortweight = 0
        self.rapidturn_filepath = None
        self.rapidturn_filepath_7i92 = None
        self.rapidturn_sim_filepath = None
        self.image_filepath = None
        self.description = ''
        self.hostmot2_driver = None


class config_chooser():

    def __init__(self, sim_mode, comm_method):

        self.comm_method = comm_method
        self.exit_code = CONFIGCHOOSER_EXITCODE_NOCONFIGSELECTED

        # look for the .glade file and the images here:
        self.JSON_FILE = os.path.join(os.getenv("HOME"), 'pathpilot.json')
        self.CONFIGS_DIR = os.path.join(os.getenv("HOME"), 'tmc', 'configs')

        # glade, window, and gtk builder setup
        #
        # To make all of this much easier to keep straight, the window name and the glade file name are
        # exactly the same (minus the .glade extension).
        #
        # Use a separate Gtk Builder for each .glade file! This is critical to avoid stupid, hard to
        # find bugs where there is some mystery id in one glade file that ends up colliding with another glade
        # file. Wasted a lot of time trying to track a few things down because of this.
        #
        self.windows_builder_dict = { 'config_chooser_main':gtk.Builder(),
                                      'config_chooser_sn_help':gtk.Builder(),
                                      'config_chooser_old_machines':gtk.Builder(),
                                      'config_chooser_sdu_help':gtk.Builder(),
                                      's1_threedigitsn_upgrades_chart':gtk.Builder(),
                                      's1_upgrades_chart':gtk.Builder(),
                                      's2_upgrades_chart':gtk.Builder() }

        for (name, builder) in self.windows_builder_dict.iteritems():
            gladefilepath = os.path.join(GLADE_DIR, name) + ".glade"
            result = builder.add_from_file(gladefilepath)
            assert result > 0, "Builder failed on %s" % gladefilepath

            # be defensive if stuff exists in glade file that can't be found in the source anymore!
            missing_signals = builder.connect_signals(self)
            if missing_signals is not None:
                raise RuntimeError("Cannot connect signals: ", missing_signals)

        self.fixed = self.windows_builder_dict['config_chooser_main'].get_object('main_fixed_container')
        self.machine_description = self.windows_builder_dict['config_chooser_main'].get_object('machine_description')
        self.machine_image = self.windows_builder_dict['config_chooser_main'].get_object('machine_image')
        self.machine_image.set_no_show_all(True)
        self.machine_image.hide()
        self.sim_label = self.windows_builder_dict['config_chooser_main'].get_object('sim_label')
        self.sim_label.set_no_show_all(True)
        self.legacy_button = self.windows_builder_dict['config_chooser_main'].get_object('legacy_button')
        self.legacy_button.set_no_show_all(True)
        self.legacy_label = self.windows_builder_dict['config_chooser_main'].get_object('legacy_label')
        self.legacy_label.set_no_show_all(True)

        # Find all the Gtk window objects by name using the correct builder object
        self.window_dict = {}
        for (name, builder) in self.windows_builder_dict.iteritems():
            self.window_dict[name] = builder.get_object(name)

        # setup sim mode
        self.running_in_sim_mode = False     # default
        if sim_mode or os.getenv("PATHPILOT_SIM_MODE") == '1':
            self.set_sim_mode(True)

        self.save_button = self.windows_builder_dict['config_chooser_main'].get_object('save_button')

        # key to machine dictionary is status and value is sorted list of machine objects
        self.machines_dict = self.search_for_machines()

        self.machines_scrollwin = gtk.ScrolledWindow()
        self.machines_scrollwin.set_size_request(410, 320)
        self.machines_scrollwin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.machines_scrollwin.set_can_focus(False)

        # create list store
        self.machines_store = gtk.ListStore(str, str, gobject.TYPE_PYOBJECT)
        for machine in self.machines_dict['current']:
            # current machine model names use black for foreground text color
            self.machines_store.append([machine.modelname, constants.BLACK, machine])
        for machine in self.machines_dict['dev']:
            # dev machine model names use red for foreground text color
            self.machines_store.append(['DEV  ' + machine.modelname, constants.RED, machine])

        # get a 'tooltip' aware treeview...
        treeview = gtk.TreeView(self.machines_store)
        self.machines_scrollwin.add(treeview)

        self.tree_selection = treeview.get_selection()
        self.tree_selection.set_mode(gtk.SELECTION_SINGLE)
        self.tree_selection.connect('changed', self.on_machine_selection_changed)

        # define columns
        font = pango.FontDescription('Roboto Condensed 14')
        crt = gtk.CellRendererText()
        crt.set_property('font-desc', font)
        name_col = gtk.TreeViewColumn('', crt, text=0, foreground=1)  #, foreground=constants.BLACK, background=constants.WHITE)
        treeview.append_column(name_col)
        treeview.set_headers_visible(False)

        self.fixed.put(self.machines_scrollwin, 26, 104)

        # display version number to help tech support
        ver = versioning.GetVersionMgr().get_display_version()
        version_label = self.windows_builder_dict['config_chooser_main'].get_object('version_label')
        markup = '<span font_desc="Roboto Condensed 11" foreground="black">{:s}</span>'.format(ver)
        version_label.set_markup(markup)

        # Should we hide the entire legacy button side of things for this build?
        legacy_files = {
            'tormach_mill/tormach_1100-3_specific.ini',
            'tormach_lathe/tormach_lathe_5i25_specific.ini'
        }
        legacy_exists = False
        for ff in legacy_files:
            legacy_exists = legacy_exists or fsutil.file_exists(os.path.join(self.CONFIGS_DIR, ff))
        if not (len(self.machines_dict['legacy']) or legacy_exists):
            self.legacy_button.hide()
            self.legacy_label.hide()

        self.show_window('config_chooser_main')

        self.windows_builder_dict['config_chooser_main'].get_object('cancel_button').grab_focus()


    def search_for_machines(self):
        configs_top = self.CONFIGS_DIR
        items = os.listdir(configs_top)
        config_filepaths_list = []
        for ii in items:
            config_dir = os.path.join(configs_top, ii)
            if stat.S_ISDIR(os.stat(config_dir).st_mode):
                cmd = 'ls {}/*.ini | grep specific'.format(config_dir)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                (outdata, errdata) = p.communicate()
                if p.returncode == 0:
                    for line in outdata.splitlines():
                        if '_sim' in line:
                            continue
                        if '_rapidturn' in line:
                            continue
                        config_filepaths_list.append(os.path.join(config_dir, line))

        machines_dict = {
            'current' : [],
            'dev' : [],
            'legacy' : []
            }

        for candidate in config_filepaths_list:
            parser = SafeConfigParser()
            try:
                parser.read(candidate)
                if parser.has_section('CONFIG_CHOOSER'):
                    machine = Machine()
                    machine.specific_filepath = candidate

                    # look at the config dir name to determine machine class
                    parent_dirname = os.path.basename(os.path.dirname(machine.specific_filepath))
                    machine.machine_class = parent_dirname.replace('tormach_', '')

                    # Required
                    try:
                        machine.modelname = parser.get('CONFIG_CHOOSER', 'MODEL_NAME')
                    except ConfigParser.NoOptionError:
                        print "ERROR: config missing requird key [CONFIG_CHOOSER] MODEL_NAME - {:s}".format(candidate)
                        continue  # skip it

                    # Required
                    try:
                        status = parser.get('CONFIG_CHOOSER', 'STATUS')
                        if status:
                            machine.status = status.lower()
                        if machine.status not in ['current', 'legacy', 'dev']:
                            print "ERROR: config has invalid [CONFIG_CHOOSER] STATUS = {:s} - {:s}".format(status, candidate)
                            continue  # skip it
                    except ConfigParser.NoOptionError:
                        print "ERROR: config missing requird key [CONFIG_CHOOSER] STATUS - {:s}".format(candidate)
                        continue  # skip it

                    # Optional
                    try:
                        weight = parser.get('CONFIG_CHOOSER', 'SORT_WEIGHT')
                        # the below lets you leave the key in the file, but leave the value side blank if desired
                        if weight:
                            weight = weight.strip()
                            if len(weight) > 0:
                                try:
                                    machine.sortweight = int(weight)
                                except ValueError:
                                    print "ERROR: config has invalid value for [CONFIG_CHOOSER] SORT_WEIGHT = {:s} - {:s}".format(weight, candidate)
                                    continue  # skip it
                    except ConfigParser.NoOptionError:
                        machine.sortweight = 0

                    # Optional
                    # Mills that have parallel RapidTurn lathe configs explicity tell us what the
                    # config file name is over in the lathe dir rather than us guessing.
                    try:
                        rapidturn_filename = parser.get('CONFIG_CHOOSER', 'RAPIDTURN_CONFIGFILENAME')
                        # the below lets you leave the key in the file, but leave the value side blank if desired
                        if rapidturn_filename:
                            rapidturn_filename = rapidturn_filename.strip()
                            if len(rapidturn_filename) > 0:
                                # make sure file actually exists.
                                filepath = os.path.join(configs_top, 'tormach_lathe', rapidturn_filename)
                                if fsutil.file_exists(filepath):
                                    machine.rapidturn_filepath = filepath
                                    machine.rapidturn_sim_filepath = machine.rapidturn_filepath.replace('_specific', '_sim_specific')
                                else:
                                    print "ERROR: config has [CONFIG_CHOOSER] RAPIDTURN_CONFIGFILENAME = {:s}, but file doesn't exist! - {:s}".format(filepath, candidate)
                                    continue  # skip it
                    except ConfigParser.NoOptionError:
                        machine.rapidturn_filepath = None

                    # Optional - 7i92 flavor
                    # Mills that have parallel RapidTurn lathe configs explicity tell us what the
                    # config file name is over in the lathe dir rather than us guessing.
                    try:
                        rapidturn_filename = parser.get('CONFIG_CHOOSER', 'RAPIDTURN_CONFIGFILENAME_7I92')
                        # the below lets you leave the key in the file, but leave the value side blank if desired
                        if rapidturn_filename:
                            rapidturn_filename = rapidturn_filename.strip()
                            if len(rapidturn_filename) > 0:
                                # make sure file actually exists.
                                filepath = os.path.join(configs_top, 'tormach_lathe', rapidturn_filename)
                                if fsutil.file_exists(filepath):
                                    machine.rapidturn_filepath_7i92 = filepath
                                else:
                                    print "ERROR: config has [CONFIG_CHOOSER] RAPIDTURN_CONFIGFILENAME_7I92 = {:s}, but file doesn't exist! - {:s}".format(filepath, candidate)
                                    continue  # skip it
                    except ConfigParser.NoOptionError:
                        machine.rapidturn_filepath_7i92 = None

                    # Optional
                    try:
                        machine.description = parser.get('CONFIG_CHOOSER', 'DESCRIPTION_MSGID')
                    except ConfigParser.NoOptionError:
                        machine.description = ''

                    # Optional
                    try:
                        filename = parser.get('CONFIG_CHOOSER', 'IMAGE_FILENAME')
                        # the below lets you leave the key in the file, but leave the value side blank if desired
                        if filename:
                            filename = filename.strip()
                            if len(filename) > 0:
                                # make sure file actually exists
                                filepath = os.path.join(GLADE_DIR, filename)
                                if fsutil.file_exists(filepath):
                                    machine.image_filepath = filepath
                                else:
                                    print "ERROR: config has [CONFIG_CHOOSER] IMAGE_FILENAME = {:s}, but file doesn't exist! - {:s}".format(filepath, candidate)
                                    continue  # skip it
                    except ConfigParser.NoOptionError:
                        pass

                    # Optional
                    try:
                        filename = parser.get('CONFIG_CHOOSER', '7I92_FILENAME')
                        if filename:
                            filename = filename.strip()
                            if len(filename) > 0:
                                parent_path = os.path.dirname(machine.specific_filepath)
                                filepath = os.path.join(parent_path, filename)
                                if fsutil.file_exists(filepath):
                                    machine.specific_filepath_7i92 = filepath
                                else:
                                    print "ERROR: config has [CONFIG_CHOOSER] 7I92_FILENAME = {:s}, but file doesn't exist! - {:s}".format(filepath, candidate)
                                    continue  # skip it
                    except ConfigParser.NoOptionError:
                        pass

                    # Optional - sometimes this isn't in the specific .ini file, but an included section or a base file.
                    try:
                        if parser.has_section('HOSTMOT2'):
                            machine.hostmot2_driver = parser.get('HOSTMOT2', 'DRIVER')
                    except ConfigParser.NoOptionError:
                        pass

                    # now figure out how to simulate the machine config we found.
                    # in general unless the specific ini file has overridden the sim config filename using
                    # the [CONFIG_CHOOSER] SIM_FILENAME key, use the standard file naming substitution and
                    # see if the file exists.
                    try:
                        filename = parser.get('CONFIG_CHOOSER', 'SIM_FILENAME')
                        if filename:
                            filename = filename.strip()
                            if len(filename) > 0:
                                parent_path = os.path.dirname(machine.specific_filepath)
                                filepath = os.path.join(parent_path, filename)
                                if fsutil.file_exists(filepath):
                                    machine.specific_sim_filepath = filepath
                                else:
                                    print "ERROR: config has [CONFIG_CHOOSER] SIM_FILENAME = {:s} override, but file doesn't exist! - {:s}".format(filepath, candidate)
                                    continue  # skip it
                    except ConfigParser.NoOptionError:
                        pass

                    if not machine.specific_sim_filepath:
                        # try the generic naming convention since the override didn't pan out.
                        filepath = machine.specific_filepath.replace('_specific', '_sim_specific')
                        if fsutil.file_exists(filepath):
                            machine.specific_sim_filepath = filepath
                        else:
                            print "ERROR: config not valid for sim mode, filename or [CONFIG_CHOOSE] SIM_FILENAME override key needs to be used - {:s}".format(candidate)
                            continue   # skip it

                    machines_dict[machine.status].append(machine)

            except ConfigParser.ParsingError as e:
                print "ParsingError exception so skipping file {:s}\n{:s}".format(candidate, str(e))


        # in place sort for each list
        for key in machines_dict.keys():
            machines_dict[key].sort(key=lambda x: x.sortweight, reverse=True)

        return machines_dict


    def on_machine_selection_changed(self, treeselection):
        model,selected_iter = treeselection.get_selected()
        if selected_iter is not None:
            selected_path = model.get_path(selected_iter)
            modelname = model.get_value(selected_iter, 0)  # string
            machine = model.get_value(selected_iter, 2)  # machine object

            # update the description and image
            template = '<span font_desc="Roboto Condensed 12" foreground="black" >{:s}</span>'
            escaped_description = ui_misc.escape_markup(machine.description)
            self.machine_description.set_markup(template.format(escaped_description))

            # update the image if we have one, otherwise hide the image object
            if machine.image_filepath:
                self.machine_image.set_from_file(machine.image_filepath)
                self.machine_image.show()
            else:
                self.machine_image.hide()


    def destroy(self):
        for win in self.window_dict.itervalues():
            win.destroy()


    def on_legacy_button_clicked(self, widget, data=None):
        self.show_window('config_chooser_old_machines')


    def on_save_button_clicked(self, widget, data=None):
        # Does the treeview have a current selection?
        model,selected_iter = self.tree_selection.get_selected()
        if selected_iter is not None:
            selected_path = model.get_path(selected_iter)
            modelname = model.get_value(selected_iter, 0)  # string
            machine = model.get_value(selected_iter, 2)  # machine object

            self.write_json_file(machine)

            self.exit_code = CONFIGCHOOSER_EXITCODE_SUCCESS
            self.destroy()
            gtk.main_quit()
        else:
            with popupdlg.ok_cancel_popup(None, 'Select the machine connected to the controller.', cancel=False, checkbox=False) as dlg:
                pass


    def on_main_key_press_event(self, widget, event):
        # ctrl-alt-s force sim mode to be on
        # handy for development
        mask = gtk.accelerator_get_default_mod_mask()
        if (event.keyval in [gtk.keysyms.s, gtk.keysyms.S]) and ((event.state & mask) == (gtk.gdk.CONTROL_MASK | gtk.gdk.MOD1_MASK)):
            # toggle sim state
            self.running_in_sim_mode = not self.running_in_sim_mode
            self.set_sim_mode(self.running_in_sim_mode)

        #handle key combination ctrl-alt-u to open VMC console testing mode
        if (event.keyval in [gtk.keysyms.u, gtk.keysyms.U]) and ((event.state & mask) == (gtk.gdk.CONTROL_MASK | gtk.gdk.MOD1_MASK)):
            diagnostic_fullpath = os.path.join(os.getenv('HOME'), 'tmc', 'python', 'tormach_console', 'test.sh')
            if fsutil.file_exists(diagnostic_fullpath):
                exitcode = subprocess.call([diagnostic_fullpath], shell=True)
                print("Finished running tormach console diagnostic: ", str(exitcode))

    def set_sim_mode(self, sim_enabled):
        self.running_in_sim_mode = sim_enabled
        if self.running_in_sim_mode:
            print "config_chooser sim mode ENABLED"
            # in sim mode we use db25 parallel, that way the rest of the system releases the ethernet interface
            # for customer/developer use (and sim mode means we'll never verify it mesa parallel interface exists anyway)
            self.comm_method_save = self.comm_method
            self.comm_method = 'db25parallel'
            self.sim_label.show()
        else:
            print "config_chooser sim mode DISABLED"
            self.comm_method = self.comm_method_save
            self.sim_label.hide()


    def on_1100_series_2_button_release_event(self, widget, data=None):
        self.show_window('s2_upgrades_chart')


    def on_update_button_clicked(self, widget, data=None):
        # Just run swupdate.py
        print "Running swupdate.py"
        swupdate_fullpath = os.path.join(os.getenv('HOME'), 'tmc', 'python', 'swupdate.py')
        if fsutil.file_exists(swupdate_fullpath):
            exitcode = subprocess.call([swupdate_fullpath], shell=True)
            if exitcode == 1:
                # swupdate.py put a built in place and created an ~/update_file.txt containing the path to it.
                # now we just need to exit normally and pathpilotmanager.py will check for the update file.
                print "swupdate.py successful in placing build and creating update_file.txt, config_chooser exiting so pathpilotmanager can install it."
                self.exit_code = CONFIGCHOOSER_EXITCODE_INSTALL_UPDATE
                self.destroy()
                gtk.main_quit()


    def on_logdata_button_clicked(self, widget, data=None):
        print "Gathering log data"

        usbdrive_validated = False
        usbdrive_path = None
        prompt_msg = 'Insert USB drive for log data file.'
        while not usbdrive_validated:
            dlg = popupdlg.ok_cancel_popup(None, prompt_msg, cancel=True, checkbox=False)
            dlg.run()
            dlg.destroy()
            if dlg.response == gtk.RESPONSE_CANCEL:
                return

            # verify we can see one
            directory_entries = os.listdir(constants.USB_MEDIA_MOUNT_POINT)
            for candidate in directory_entries:
                usbdrive_path = os.path.join(constants.USB_MEDIA_MOUNT_POINT, candidate)
                if os.path.isdir(usbdrive_path):
                    usbdrive_validated = True
                    break # good enough

            if not usbdrive_validated:
                prompt_msg = 'USB drive not found.  Try again or use a different USB drive for the log data file.'

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()

        # automatically do a settings backup and include that zip into the log data zip.
        # makes reproducing issues a lot faster in support incidents.

        # create the temp directory where we gather all the log data into first.
        # then give that directory to the gatherdata script as an argument so it continues to
        # add to it.
        tmpdir = os.path.join(os.environ['HOME'], 'tmp')
        if not os.path.isdir(tmpdir):
            os.mkdir(tmpdir)
        logdata_tmpdir = tempfile.mkdtemp(prefix='logdata_', dir=tmpdir)

        with plexiglass.PlexiglassInstance(self.window_dict['config_chooser_main'], full_screen=False) as p:
            # perform a settings backup into that directory.
            settings_backup_fullpath = os.path.join(os.getenv('HOME'), 'tmc', 'python', 'settings_backup.py')

            print "Running", settings_backup_fullpath, logdata_tmpdir
            exitcode = subprocess.call([settings_backup_fullpath, logdata_tmpdir], shell=False)
            if exitcode == 0:
                # run lots of diagnostic gathering tools and produce a single file in
                # gcode which the customer can provide by email easily.
                # This can take 10-20 seconds so toss up the plexiglass.
                # The automatic settings backup above already uses its own plexiglass so don't nest them.

                proc = subprocess.Popen(['gatherdata', logdata_tmpdir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                (stdouttxt, stderrtxt) = proc.communicate()
                # The first line of stdout is the filename of the tarball that gatherdata writes.
                filenames = string.split(stdouttxt, '\n', 1)
                print "Log data written to file %s." % filenames[0]
                # dump the log info from the gatherdata script into our log file
                print "\ngatherdata stdout:\n", stdouttxt
                print "\ngatherdata stderr:\n", stderrtxt

                # we don't need to clean up the logdata_tmpdir as the gatherdata script does that for us.

                if fsutil.file_exists(os.path.join(usbdrive_path, filenames[0])):
                    with popupdlg.ok_cancel_popup(None, 'Log data file successfully copied to USB drive.\n\n{}'.format(filenames[0]), cancel=False, checkbox=False) as dialog:
                        pass
            else:
                # settings backup failed - clean up.
                try:
                    os.rmdir(logdata_tmpdir)
                except:
                    pass


    def on_cancel_button_clicked(self, widget, data=None):
        self.exit_code = CONFIGCHOOSER_EXITCODE_NOCONFIGSELECTED
        self.destroy()
        gtk.main_quit()


    # ------------------------------------------------------------
    # button release events - existing machinery screen
    # TODO - help screens for upgrade options
    # ------------------------------------------------------------

    def on_1100_original_button_release_event(self, widget, data=None):
        self.show_window('s1_upgrades_chart')

    def on_1100_3_digit_button_release_event(self, widget, data=None):
        self.show_window('s1_threedigitsn_upgrades_chart')


    # ------------------------------------------------------------
    # button release events - 'where is the serial number' screen
    # ------------------------------------------------------------

    def on_sdu_help_button_release_event(self, widget, data=None):
        self.show_window('config_chooser_sdu_help')


    def on_1100_series_3_button_release_event(self, widget, data=None):
        # legacy special case
        machine = Machine()
        machine.specific_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-3_specific.ini')
        machine.specific_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-3_7i92_specific.ini')
        machine.specific_sim_filepath = machine.specific_filepath.replace('_specific', '_sim_specific')
        machine.machine_class = 'mill'
        machine.modelname = '1100-3'
        machine.rapidturn_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_1100-3_rapidturn_specific.ini')
        machine.rapidturn_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_1100-3_7i92_rapidturn_specific.ini')
        machine.rapidturn_sim_filepath = machine.rapidturn_filepath.replace('_specific', '_sim_specific')

        self.write_json_file(machine)

        self.exit_code = CONFIGCHOOSER_EXITCODE_SUCCESS
        self.destroy()
        gtk.main_quit()


    def on_770_series_3_button_release_event(self, widget, data=None):
        # legacy special case
        machine = Machine()
        machine.specific_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_770_specific.ini')
        machine.specific_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_770_7i92_specific.ini')
        machine.specific_sim_filepath = machine.specific_filepath.replace('_specific', '_sim_specific')
        machine.machine_class = 'mill'
        machine.modelname = '770'
        machine.rapidturn_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_770_rapidturn_specific.ini')
        machine.rapidturn_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_770_7i92_rapidturn_specific.ini')
        machine.rapidturn_sim_filepath = machine.rapidturn_filepath.replace('_specific', '_sim_specific')

        self.write_json_file(machine)

        self.exit_code = CONFIGCHOOSER_EXITCODE_SUCCESS
        self.destroy()
        gtk.main_quit()


    # ------------------------------------------------------------
    # button release events - s1 upgrades screen
    # ------------------------------------------------------------

    def on_s1_no_upgrades_button_release_event(self, widget, data=None):
        # legacy special case
        machine = Machine()
        machine.specific_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-1_specific.ini')
        machine.specific_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-1_7i92_specific.ini')
        # for sim we just use an 1100-3
        machine.specific_sim_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-3_sim_specific.ini')

        machine.machine_class = 'mill'
        machine.modelname = '1100-1'
        # No RapidTurn support

        self.write_json_file(machine)

        self.exit_code = CONFIGCHOOSER_EXITCODE_SUCCESS
        self.destroy()
        gtk.main_quit()

    # ------------------------------------------------------------
    # button release events - s1 3 digit upgrades screen
    # ------------------------------------------------------------

    def on_s1_3_digit_button_release_event(self, widget, data=None):
        # legacy special case
        machine = Machine()
        machine.specific_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100_threedigitsn_specific.ini')
        machine.specific_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100_threedigitsn_7i92_specific.ini')
        # for sim we just use an 1100-3
        machine.specific_sim_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-3_sim_specific.ini')

        machine.machine_class = 'mill'
        machine.modelname = '1100'
        # No RapidTurn support

        self.write_json_file(machine)

        self.exit_code = CONFIGCHOOSER_EXITCODE_SUCCESS
        self.destroy()
        gtk.main_quit()


    def on_s1_3_digit_w_sdu_button_release_event(self, widget, data=None):
        # legacy special case
        machine = Machine()
        machine.specific_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100_threedigitsn_sdu_specific.ini')
        machine.specific_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100_threedigitsn_7i92_sdu_specific.ini')
        # for sim we just use an 1100-3
        machine.specific_sim_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-3_sim_specific.ini')

        machine.machine_class = 'mill'
        machine.modelname = '1100'
        machine.rapidturn_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_1100_threedigitsn_sdu_rapidturn_specific.ini')
        machine.rapidturn_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_1100_threedigitsn_sdu_7i92_rapidturn_specific.ini')
        machine.rapidturn_sim_filepath = machine.rapidturn_filepath.replace('_specific', '_sim_specific')

        self.write_json_file(machine)

        self.exit_code = CONFIGCHOOSER_EXITCODE_SUCCESS
        self.destroy()
        gtk.main_quit()

    # ------------------------------------------------------------
    # button release events - s2 upgrades screen
    # ------------------------------------------------------------

    def on_s2_no_upgrades_button_release_event(self, widget, data=None):
        # legacy special case
        machine = Machine()
        machine.specific_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-2_specific.ini')
        machine.specific_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-2_7i92_specific.ini')
        # for sim we just use an 1100-3
        machine.specific_sim_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_mill', 'tormach_1100-3_sim_specific.ini')

        machine.machine_class = 'mill'
        machine.modelname = '1100-2'
        machine.rapidturn_filepath = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_1100-2_rapidturn_specific.ini')
        machine.rapidturn_filepath_7i92 = os.path.join(self.CONFIGS_DIR, 'tormach_lathe', 'tormach_1100-2_7i92_rapidturn_specific.ini')
        machine.rapidturn_sim_filepath = machine.rapidturn_filepath.replace('_specific', '_sim_specific')

        self.write_json_file(machine)

        self.exit_code = CONFIGCHOOSER_EXITCODE_SUCCESS
        self.destroy()
        gtk.main_quit()


    # ------------------------------------------------------------
    # button release events - common to multiple screens
    # ------------------------------------------------------------

    def on_where_is_sn_button_release_event(self, widget, data=None):
        self.show_window('config_chooser_sn_help')

    def on_return_button_release_event(self, widget, data=None):
        self.show_window('config_chooser_main')


    # ------------------------------------------------------------
    # enter/leave notify events for text highlighting
    # ------------------------------------------------------------

    def on_enter_notify_event(self, widget, data=None):
        label = widget.get_child()
        text = label.get_text()
        markup = '<span font_desc="Roboto Condensed 12" foreground="blue" >' + text + '</span>'
        label.set_markup(markup)

    def on_leave_notify_event(self, widget, data=None):
        label = widget.get_child()
        text = label.get_text()
        markup = '<span font_desc="Roboto Condensed 12" foreground="black" >' + text + '</span>'
        label.set_markup(markup)

    def on_leave_notify_event_confidential(self, widget, data=None):
        label = widget.get_child()
        text = label.get_text()
        markup = '<span font_desc="Roboto Condensed 12" foreground="red" >' + text + '</span>'
        label.set_markup(markup)

    def on_help_enter_notify_event(self, widget, data=None):
        label = widget.get_child()
        text = label.get_text()
        markup = '<span font_desc="Roboto Condensed 12" foreground="blue" >' + text + '</span>'
        label.set_markup(markup)

    # ------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------

    def show_window(self, windowname):

        # show the specified window
        self.window_dict[windowname].show_all()

        # hide all the others (this prevents flashing)
        for name, win in self.window_dict.iteritems():
            if name != windowname:
                win.hide()


    def write_json_file(self, machine):

        # These are ALL the settings that get written to the json file.
        config = { "fileversion" : 2,
                   "machine" : {},
                   "pathpilot" : {} }

        # ignore the self.comm_method if we know that the config they choose requires ethernet.
        # not 100% reliable as some specific.ini files have them and some don't depending on structure.
        if machine.hostmot2_driver:
            if machine.hostmot2_driver == 'hm2_eth':
                self.comm_method = 'ethernet'
            elif machine.hostmot2_driver == 'hm2_pci' and machine.specific_filepath_7i92 is None:
                self.comm_method = 'db25parallel'

        # special case the 7i92 variants of all the older Mesa PCI card configs
        # everything else is the same, we just start with this file or not.
        if self.comm_method == "ethernet" and machine.specific_filepath_7i92:
            config["machine"]["generate_from"] = machine.specific_filepath_7i92
        else:
            config["machine"]["generate_from"] = machine.specific_filepath

        config["machine"]["linuxcnc_filepath"] = config["machine"]["generate_from"].replace('_specific', '')
        config["machine"]["class"] = machine.machine_class
        config["machine"]["model"] = machine.modelname
        config["machine"]["sim"] = self.running_in_sim_mode
        config["machine"]["rapidturn"] = False    # PathPilot when running will change this value to switch between Mill and Lathe personalities.
        config["machine"]["rapidturn_generate_from"] = None
        config["machine"]["rapidturn_linuxcnc_filepath"] = None

        # some mills support RapidTurn which is lathe mode
        if machine.rapidturn_filepath:

            if self.running_in_sim_mode:
                config["machine"]["rapidturn_generate_from"] = machine.rapidturn_sim_filepath
            elif self.comm_method == "ethernet" and machine.rapidturn_filepath_7i92:
                config["machine"]["rapidturn_generate_from"] = machine.rapidturn_filepath_7i92
            else:
                config["machine"]["rapidturn_generate_from"] = machine.rapidturn_filepath

            config["machine"]["rapidturn_linuxcnc_filepath"] = config["machine"]["rapidturn_generate_from"].replace('_specific', '')

        if self.running_in_sim_mode:
            # we always use the mesa card for sim so that pathpilotmanager releeases all ethernet interfaces
            # for other use.
            config["machine"]["communication_method"] = 'db25parallel'
            config["machine"]["generate_from"] = machine.specific_sim_filepath
            config["machine"]["linuxcnc_filepath"] = machine.specific_sim_filepath.replace('_specific', '')
        else:
            config["machine"]["communication_method"] = self.comm_method

        # since we expect to generate the file, make sure we do by deleting any existing file if it exists.
        abspath = os.path.expanduser(config["machine"]["linuxcnc_filepath"])
        if fsutil.file_exists(abspath):
            os.unlink(abspath)

        with open(self.JSON_FILE, 'w') as ppjsonfile:
            json.dump(config, ppjsonfile, indent=4, sort_keys=True)
            ppjsonfile.write("\n")   # make cat'ing the contexts of the file more legible in the shell

        print "Writing file %s" % self.JSON_FILE

        # dump the contents of the file for the log
        with open(self.JSON_FILE, 'r') as jsonfile:
            print jsonfile.read()

def _nop_callback():
    pass

if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    # There is no machine control going on during config chooser so just give the plexiglass something
    # to call that has no effect when it needs to make sure that all jogging has stopped.
    plexiglass.PlexiglassInitialize(_nop_callback)

    # kill the splash screen
    p = subprocess.Popen(['ps', 'x'], stdout=subprocess.PIPE)
    out, err = p.communicate()

    for line in out.splitlines():
        if 'tormach_splash.py' in line:
            pid = int(line.split(None, 6)[0])
            os.kill(pid, signal.SIGKILL)

    sim_mode = ('--sim' in sys.argv)

    # args related to communication cabling to the machine - is it ethernet or db25 parallel?
    comm_ethernet = ('--ethernet' in sys.argv)
    comm_db25 = ('--db25parallel' in sys.argv)

    if not (sim_mode or comm_db25 or comm_ethernet) and (len(sys.argv) > 1):
        print "\nInvalid argument for config_chooser.py."
        print "Valid arguments are\n\t--sim\n\t--ethernet\n\t--db25parallel\n"
        exit()

    # if we were told a mesa card is present, that is the default
    comm_method = "ethernet"
    if comm_db25:
        comm_method = "db25parallel"

    cp = config_chooser(sim_mode, comm_method)
    gtk.main()

    print "config_chooser.py exiting with code %d" % cp.exit_code
    sys.exit(cp.exit_code)
