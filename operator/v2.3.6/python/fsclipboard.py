# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import os
import re
import gtk
import shutil
import constants as const
import singletons
import plexiglass
import fsutil
import tormach_file_util


class fsclipboard_mgr():

    def __init__(self, error_handler):
        self.error_handler = error_handler
        self.clipboard_selection_list = None
        self.clipboard_action = None
        self.paste_suffix_re = re.compile(r'-Copy( \((\d+)\))?$', re.I)
        self.file_chooser = None


    def on_clipboard_button_press_event(self, file_chooser, refresh_free_space_callback, widget, event, data=None):
        # one of the file choosers had a clipboard event
        # display the clipboard action popup menu
        self.file_chooser = file_chooser
        self.refresh_free_space_callback = refresh_free_space_callback
        menu = gtk.Menu()
        cut = gtk.MenuItem("Cut")
        copy = gtk.MenuItem("Copy")
        paste = gtk.MenuItem("Paste")
        cut.connect("activate", self.clipboard_cut)
        copy.connect("activate", self.clipboard_copy)
        paste.connect("activate", self.clipboard_paste)
        paste.set_sensitive(self.clipboard_action != None)
        menu.append(copy)
        menu.append(cut)
        menu.append(paste)
        menu.popup(None, None, None, event.button, event.time)
        cut.show()
        paste.show()
        copy.show()


    def clipboard_cut(self, widget, data=None):
        # save current selection off with 'cut' action for later paste
        self.clipboard_selection_list = self.file_chooser.get_filenames()
        self.clipboard_action = 'cut'


    def clipboard_copy(self, widget, data=None):
        # save current selection off with 'copy' action for later paste
        self.clipboard_selection_list = self.file_chooser.get_filenames()
        self.clipboard_action = 'copy'


    def clipboard_paste(self, widget, data=None):
        # paste always pastes into the cwd of the file chooser and it resets the selection
        # of the file chooser

        # perform cut or copy on saved selection
        target_folder = self.file_chooser.get_current_folder()

        cut_list = []
        new_select_list = []
        if self.clipboard_selection_list:
            with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as p:
                for path_source in self.clipboard_selection_list:

                    (source_folder, name_source) = os.path.split(path_source)

                    if os.path.isfile(path_source):
                        final_name = self.generate_non_conflicting_filename(target_folder, name_source)
                        path_dst = os.path.join(target_folder, final_name)
                        shutil.copy2(path_source, path_dst)
                        cut_list.append(path_source)
                        new_select_list.append(path_dst)

                    elif os.path.isdir(path_source):
                        final_name = self.generate_non_conflicting_dirname(target_folder, name_source)
                        path_dst = os.path.join(target_folder, final_name)

                        # detect situation where the destination folder is a subfolder of the source.
                        # e.g. you're trying to copy /home/operator/gcode/foo into /home/operator/gcode/foo/bar
                        # e.g. you're trying to copy /home/operator/gcode/foo into /home/operator/gcode
                        if path_dst.startswith(path_source) and source_folder != target_folder:
                            sanitized_source = fsutil.sanitize_path_for_user_display(path_source)
                            sanitized_dst = fsutil.sanitize_path_for_user_display(path_dst)
                            self.error_handler.write("Skipping paste of %s because it is a subfolder of %s" % (sanitized_dst, sanitized_source), const.ALARM_LEVEL_LOW)
                        else:
                            shutil.copytree(path_source, path_dst, symlinks=False)
                            cut_list.append(path_source)
                            new_select_list.append(path_dst)

                if self.clipboard_action == 'cut':
                    for path_source in cut_list:
                        self.error_handler.log("cut action deleting: {}".format(path_source))
                        if os.path.isdir(path_source):
                            shutil.rmtree(path_source)
                        else:
                            os.remove(path_source)

                    # cannot 'paste' a cut multiple times because the sources are gone now so clear the action
                    self.clipboard_action = None
                    self.clipboard_selection_list = None

                # change selection of file chooser to all the newly created items
                # but file chooser has no method to select more than one file even though it supports
                # multiple selection (cripes!)
                # so just pick the first one.
                self.file_chooser.unselect_all()
                if len(new_select_list) > 0:
                    # we need to 'kick' the file chooser to see all the new items we just created
                    # otherwise we can't 'select' them for the user.
                    self.file_chooser.set_current_folder(target_folder)
                    self.file_chooser.select_filename(new_select_list[0])

                # stuff above probably affected free space so refresh it
                self.refresh_free_space_callback()


    def generate_non_conflicting_dirname(self, target_folder, name_source):
        # this differs from the filename version as we don't care about inserting the unique suffix before any extension
        candidate_name = name_source
        candidate = os.path.join(target_folder, candidate_name)
        if os.path.exists(candidate):
            name_source_base = name_source
            suffix_template = "-Copy{:s}"
            ix_suffix = ''
            ix = 2

            # if the base source name already ends in -Copy or -Copy (n) then don't keep
            # adding to it or you end up with junk like -Copy-Copy.  Windows does this and its annoying.
            # instead just use the iteration number or find the (n) and jump ahead.
            match = self.paste_suffix_re.search(name_source_base)
            if match:
                if match.group(2) != None:
                    # the base source name already ends in -Copy (n) so jump the number to n+1 and start there.
                    ix = int(match.group(2)) + 1
                name_source_base = name_source_base[:-len(match.group(0))]
                ix_suffix = ' ({:d})'.format(ix)
                ix += 1

            while True:
                candidate_suffix = suffix_template.format(ix_suffix)
                candidate_name = name_source_base + candidate_suffix
                candidate = os.path.join(target_folder, candidate_name)
                if os.path.exists(candidate):
                    ix_suffix = ' ({:d})'.format(ix)
                    ix += 1
                else:
                    break  # no conflict so we're done

        return candidate_name


    def generate_non_conflicting_filename(self, target_folder, name_source):
        candidate_name = name_source
        candidate = os.path.join(target_folder, candidate_name)
        if os.path.exists(candidate):
            (name_source_base, ext) = os.path.splitext(name_source)

            suffix_template = "-Copy{:s}"
            ix_suffix = ''
            ix = 2

            # if the base source name already ends in -Copy or -Copy (n) then don't keep
            # adding to it or you end up with junk like -Copy-Copy.  Windows does this and its annoying.
            # instead just use the iteration number or find the (n) and jump ahead.
            match = self.paste_suffix_re.search(name_source_base)
            if match:
                if match.group(2) != None:
                    # the base source name already ends in -Copy (n) so jump the number to n+1 and start there.
                    ix = int(match.group(2)) + 1
                name_source_base = name_source_base[:-len(match.group(0))]
                ix_suffix = ' ({:d})'.format(ix)
                ix += 1

            while True:
                candidate_suffix = suffix_template.format(ix_suffix)
                candidate_name = name_source_base + candidate_suffix + ext
                candidate = os.path.join(target_folder, candidate_name)
                if os.path.exists(candidate):
                    ix_suffix = ' ({:d})'.format(ix)
                    ix += 1
                else:
                    break  # no conflict so we're done

        return candidate_name
