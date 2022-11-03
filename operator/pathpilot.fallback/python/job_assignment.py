# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import gtk, pango, os, sys, gobject
import constants
import btn
import popupdlg
import tormach_file_util
import conversational
import constants
import time
import gtksourceview2
import ui_misc
import ui_support
import tooltipmgr

class JobAssignmentPopup():

    #implementation
    SAFE_REMOVE = False       # True: will tag non dulplicate files as 'Removed' but leave in tree
    EDITABLE_CELLS = True     # rows in tree have editable text...
    REMOVE_FILES = True       # DOn't mess with this one..
    FLATTEN_ON_SAVE = True    # After a save will flatten the tree...
    EXIT_TO_CURRENT_FILE = False # InSave this will exit JA to currently loaded file if replaced..
    OPTIMIZE_SAVED_FILES = True

    # Return status codes used internally
    STATUS_RUNNING = 0
    STATUS_CANCELED = 1
    STATUS_EDITING = 2
    STATUS_SAVING = 3
    STATUS_INSERTING = 4
    STATUS_INSERT_NEW = 5

    # TreeStore data tuple
    DATA_ICON = int(0)
    DATA_ICON_MOD = int(1)
    DATA_NAME = int(2)
    DATA_SEGMENT = int(3)

    ICON_COLUMN_WIDTH = 30
    ICON_MODIFER_COLUMN_WIDTH = 28

    # Sizes
    WINDOW_SIZE_X = int(900)
    WINDOW_SIZE_Y = int(520)
    TREE_SIZE_X =   int(WINDOW_SIZE_X * .33)
    TREE_SIZE_Y =   int(WINDOW_SIZE_Y - 40)
    BUTTON_START_X = int(TREE_SIZE_X + 35)
    BUTTON_START_Y = int(10)
    BUTTON_HEIGHT = float(45) # yes, this is a float!
    LABEL_HEIGHT = int(30)
    BUTTON_WIDTH = int(100)
    BASE_WIDGET_OFFSET = int(15)
    PREVIEW_START_X = int(BUTTON_START_X + BUTTON_WIDTH + 15)
    PAGE_WIDTH_REDUCTION = 6

    REMOVED_TEXT = ' (removed)'
    CELL_BACKCOLOR = '#FAFAFA'
    FILE_CELL_BACKCOLOR = '#fef8e7'
    DATA_CELL_BACKCOLOR ='#FAFAFA'
    PREVIEW_LABEL_FONT = 'Helvetica bold ultra-condensed 14'
    TVCOLUMN_LABEL_FONT = 'Helvetica ultra-condensed 14'
    PREVIEW_FONT = 'Monospace 10'

    _tree_view_tooltip_key = '_job_assignment_op_fba7_'


    modal_data = dict( original_file_path = None,
                       original_file_name = None,
                       original_file_ext = None,
                       save_state = False,
                       orig_list = []
                     )

    def __init__(self, parent_object, parentwindow, redis, gc_list=None, conversational=None, touchscreen_enabled=False, error_handler = None, segment_uuid=None, curr_notebook_page=None):
        """
        This class returns an object that includes the job assignment
        dialog that allows the user to edit, reorder, etc. routines in
        a job.
        """
        # Init image_store
#       self.init_image_store()

        # noticed a dependency on this below
        assert conversational != None

        self.icon_modifiers = dict (
            normal                = dict( icon_file = 'ce_state_icon_empty.png',               icon = None ),
            _add                  = dict( icon_file = 'ce_state_icon_add.png',                 icon = None ),
            _add_update           = dict( icon_file = 'ce_state_icon_add_update.png',          icon = None ),
            _add_update_edit      = dict( icon_file = 'ce_state_icon_add_update_edit.png',     icon = None ),
            _add_update_copy      = dict( icon_file = 'ce_state_icon_add_update_dup.png',      icon = None ),
            _add_update_edit_copy = dict( icon_file = 'ce_state_icon_add_update_edit_dup.png', icon = None ),
            _add_edit             = dict( icon_file = 'ce_state_icon_add_edit.png',            icon = None ),
            _add_edit_copy        = dict( icon_file = 'ce_state_icon_add_edit_dup.png',        icon = None ),
            _add_copy             = dict( icon_file = 'ce_state_icon_add_dup.png',             icon = None ),
            _update               = dict( icon_file = 'ce_state_icon_update.png',              icon = None ),
            _update_edit          = dict( icon_file = 'ce_state_icon_update_edit.png',         icon = None ),
            _update_copy          = dict( icon_file = 'ce_state_icon_update_dup.png',          icon = None ),
            _update_edit_copy     = dict( icon_file = 'ce_state_icon_update_edit_dup.png',     icon = None ),
            _edit                 = dict( icon_file = 'ce_state_icon_edit.png',                icon = None ),
            _edit_copy            = dict( icon_file = 'ce_state_icon_edit_dup.png',            icon = None ),
            _copy                 = dict( icon_file = 'ce_state_icon_dup.png',                 icon = None ),
            )
        self.icon_data = dict(
            file_icon = dict(icon_file = 'conv_edit_file_icon_32.png', icon = None),
            op_icon = dict(icon_file = 'op_icon.png', icon = None),
            ext_icon = dict(icon_file = 'external_gcode_icon.png', icon = None)
            )

        # use of floats for position allows for some
        # layout differences
        self.button_list = [dict(name = 'job_move_up',       aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_move_down',     aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_duplicate',     aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_remove',        aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_unremove',      aux = 'job_remove', pos = 0.0,  y= 0 ),
                       dict(name = 'job_ins_from_new',  aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_ins_from_file', aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_conv_edit',     aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_revert',        aux = None,         pos = 0.0,  y= 0 ),
                       dict(name = 'job_post',          aux = 'exclude',    pos = 0.0,  y= 0 ),
                       dict(name = 'job_post_n_go',     aux = 'exclude',    pos = 0.6,  y= 0 ),
                       dict(name = 'job_save',          aux = None,         pos = 0.3,  y= 0 ),
                       dict(name = 'job_saveas',        aux = None,         pos = 0.3,  y= 0 ),
                       dict(name = 'job_cancel',        aux = None,         pos = 0.3,  y= 0 )]

        self.button_data = dict(
            job_move_up = dict(
                button = None,
                handler = 'on_job_move_up_button_release_event',
                image_mapping = ('job_move_up', 'button_job_move_up.png')
                ),
            job_move_down = dict(
                button = None,
                handler = 'on_job_move_down_button_release_event',
                image_mapping = ('job_move_down', 'button_job_move_down.png')
                ),
            job_duplicate = dict(
                button = None,
                handler = 'on_job_duplicate_button_release_event',
                image_mapping = ('job_duplicate', 'button_job_duplicate.png')
                ),
            job_remove = dict(
                button = None,
                handler = 'on_job_remove_button_release_event',
                image_mapping = ('job_remove', 'button_job_remove.png')
                ),
            job_unremove = dict(
                button = None,
                handler = 'on_job_un_remove_button_release_event',
                image_mapping = ('job_un_remove', 'button_job_un_remove.png')
                ),
            job_ins_from_new = dict(
                button = None,
                handler = 'on_job_ins_from_new_button_release_event',
                image_mapping = ('job_ins_from_new', 'button_job_insert_step.png')
                ),
            job_ins_from_file = dict(
                button = None,
                handler = 'on_job_ins_from_file_button_release_event',
                image_mapping = ('job_ins_from_file', 'button_job_insert_file.png')
                ),
            job_conv_edit = dict(
                button = None,
                handler = 'on_job_conv_edit_button_release_event',
                image_mapping = ('job_conv_edit', 'button_job_conv_edit.png')
                ),
            job_revert = dict(
                button = None,
                handler = 'on_job_revert_button_release_event',
                image_mapping = ('job_revert', 'button_job_revert.png')
                ),
            job_post = dict(
                button = None,
                handler = 'on_job_post_button_release_event',
                image_mapping = ('job_post', 'button_job_post.png')
                ),
            job_save = dict(
                button = None,
                handler = 'on_job_save_button_release_event',
                image_mapping = ('job_save', 'save-button.png'),
                annimate = dict(esig='enter-notify-event',ehandler='on_job_save_button_mouse_enter',
                                lsig='leave-notify-event',lhandler='on_job_save_button_mouse_exit')
                ),
            job_saveas = dict(
                button = None,
                handler = 'on_job_save_as_button_release_event',
                image_mapping = ('job_saveas', 'button_save_as.png'),
                annimate = dict(esig='enter-notify-event',ehandler='on_job_saveas_button_mouse_enter',
                                lsig='leave-notify-event',lhandler='on_job_saveas_button_mouse_exit')
                ),
            job_post_n_go = dict(
                button = None,
                handler = 'on_job_post_n_go_button_release_event',
                image_mapping = ('job_post_n_go', 'button_job_post-n-go.png'),
                annimate = dict(esig='enter-notify-event',ehandler='on_job_postgo_button_mouse_enter',
                                lsig='leave-notify-event',lhandler='on_job_postgo_button_mouse_exit')
                ),
            job_cancel = dict(
                button = None,
                handler = 'on_job_close_button_release_event',
                image_mapping = ('job_cancel', 'button_job_close.png')
                ),
            )


        self.ja = parent_object
        # don't use WINDOW_POPUP, that's for GTK menus and tool tips,
        # not dialogs
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        # setting the hint type to dialog keeps this window in front
        # of the main UI screen
        self.parentwindow = parentwindow
        self.window.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.window.set_transient_for(parentwindow)
        self.window.set_modal(True)
        self.window.set_destroy_with_parent(True)
        self.error_handler = error_handler

        main_fixed = gtk.Fixed()
        main_fixed.set_size_request(JobAssignmentPopup.WINDOW_SIZE_X, JobAssignmentPopup.WINDOW_SIZE_Y)

        background = gtk.Image()
        background.set_from_file(os.path.join(constants.GLADE_DIR, 'ja_brushed_dark_background.png'))
        main_fixed.put(background, 0, 0)

        self.buttons = dict()
        self.gc_list = gc_list
        self.file_count = 0
        self.implied_selected_file = (-1,)
        self.conversational = conversational
        self.double_click_row = False
        self.double_click_path = None
        self.post_n_go_path = None
        self.selected_uuid = None
        self.hilight_save = False
        self.main_gremlin_view = self.conversational.ui.gremlin.get_view()

        # -----------------------------------------
        # Buttons
        # get buttons inited
        self._init_buttons_data()
        for conv_button in self.button_list:
            if conv_button['aux'] == 'exclude': continue
            init_data = self.button_data[conv_button['name']]
            button = btn.ImageButton(init_data['image_mapping'][1],
                                     init_data['image_mapping'][0],
                                     JobAssignmentPopup.BUTTON_START_X,
                                     conv_button['y'])

            gtk.Buildable.set_name(button,'conv_edit_'+conv_button['name']+'_button')
            button.connect("enter-notify-event",conversational.ui.on_mouse_enter)
            button.connect("leave-notify-event",conversational.ui.on_mouse_leave)
            init_data['button'] = button
            main_fixed.put(button, JobAssignmentPopup.BUTTON_START_X, conv_button['y'])
            handler = getattr(self, init_data['handler'])
            button.connect("button_release_event", handler)
            #add to a dictionary
            self.buttons[init_data['image_mapping'][0]] = button

            if init_data.has_key('annimate'):
                button.connect(init_data['annimate']['esig'],getattr(self,init_data['annimate']['ehandler']))
                button.connect(init_data['annimate']['lsig'],getattr(self,init_data['annimate']['lhandler']))


        # -----------------------------------------
        # job table init (gtk.treeview)
        if self.icon_data['file_icon']['icon'] is None:
            # common icons
            for icon_name, icon_dict in self.icon_data.iteritems():
                img_path = os.path.join(constants.GLADE_DIR,icon_dict['icon_file'])
                icon_dict['icon'] = gtk.image_new_from_file(img_path)

            # tool specific icons
            for icon_name, icon_dict in self.conversational.icon_data.iteritems():
                img_path = os.path.join(constants.GLADE_DIR,icon_dict['icon_file'])
                icon_dict['icon'] = gtk.image_new_from_file(img_path)
                self.icon_data.update({icon_name:icon_dict})

            # modifier icons
            for icon_name, icon_dict in self.icon_modifiers.iteritems():
                img_path = os.path.join(constants.GLADE_DIR,icon_dict['icon_file'])
                icon_dict['icon'] = gtk.image_new_from_file(img_path)

        JobAssignmentPopup.ICON_MODIFER_COLUMN_WIDTH = self.icon_modifiers['normal']['icon'].get_pixbuf().get_width()
        job_font = pango.FontDescription('helvetica ultra-condensed 12')
        job_i_font = pango.FontDescription('helvetica ultra-condensed 14')

        # liststore for job assignment page
        # columns are ID, filename, routine type, filepath, routine object
        # filepath and routine object are not displayed
        self.job_treestore = gtk.TreeStore(gtk.gdk.Pixbuf, gtk.gdk.Pixbuf, str, object)
        self.clear_job_treestore()
        #setup the current gc data

        # create a scrolled window to hold the treeview
        scrolled_window_job_table = gtk.ScrolledWindow()
        scrolled_window_job_table.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolled_window_job_table.set_can_focus(False)
        # the treeview knows about scrolling so do NOT add it using add_with_viewport or you
        # break all inherent keyboard navigation.
        scrolled_window_job_table.set_size_request(JobAssignmentPopup.TREE_SIZE_X, JobAssignmentPopup.TREE_SIZE_Y)

        self.job_treeview = tooltipmgr.TT_TreeView(self.job_treestore, scrolled_window_job_table, self.conversational.ui, 2, JobAssignmentPopup._tree_view_tooltip_key)
#       self.job_treeview = gtk.TreeView(self.job_treestore)
        self.tvcolumn = gtk.TreeViewColumn('   Job: %s' % JobAssignmentPopup.modal_data['original_file_name'])
        self.job_treeview.append_column(self.tvcolumn)
        self.job_treeview.set_enable_tree_lines(True)
        self.tree_selection = self.job_treeview.get_selection()
        self.tree_selection.set_mode(gtk.SELECTION_SINGLE)
        self.tree_selection.connect('changed', self.on_selection_changed)
        self.tree_model = self.job_treeview.get_model()
        self.tree_model.connect('rows-reordered', self.on_rows_reorderred)
        self.job_treeview.connect('test-expand-row', self.on_test_expand_row)
#       self.job_treeview.connect('row-activated', self.on_row_activated)
        self.job_treeview.connect('button-press-event', self.on_button_press)
        self.job_treeview.connect('button-release-event', self.on_button_release)
#       self.job_treeview.modify_base(gtk.STATE_SELECTED, gtk.gdk.Color('#2b389a'))
        label = gtk.Label('')
        label.set_size_request(JobAssignmentPopup.TREE_SIZE_X,22)
        label.show_all()
        label.set_justify(gtk.JUSTIFY_CENTER)
        label.modify_font(pango.FontDescription(JobAssignmentPopup.TVCOLUMN_LABEL_FONT))
        self.tvcolumn.set_widget(label)

        # cell renderers
        renderer = gtk.CellRendererPixbuf()
        renderer.set_fixed_size(JobAssignmentPopup.ICON_COLUMN_WIDTH, -1)
        renderer.set_padding(0,0)
        renderer.set_alignment(0,.5)
        renderer.set_property('cell-background', JobAssignmentPopup.CELL_BACKCOLOR)
        self.tvcolumn.pack_start(renderer,False)
        self.tvcolumn.add_attribute(renderer, 'pixbuf', JobAssignmentPopup.DATA_ICON)
        self.tvcolumn.set_cell_data_func(renderer, self._get_icon_render_data)

        renderer = gtk.CellRendererPixbuf()
        renderer.set_fixed_size(JobAssignmentPopup.ICON_MODIFER_COLUMN_WIDTH, -1)
        renderer.set_padding(0,0)
        renderer.set_alignment(0,.5)
        renderer.set_property('cell-background', JobAssignmentPopup.CELL_BACKCOLOR)
        self.tvcolumn.pack_start(renderer,False)
        self.tvcolumn.add_attribute(renderer, 'pixbuf', JobAssignmentPopup.DATA_ICON_MOD)
        self.tvcolumn.set_cell_data_func(renderer, self._get_icon_modifier_render_data)

        renderer = gtk.CellRendererText()
        renderer.set_property('editable', JobAssignmentPopup.EDITABLE_CELLS)
        renderer.connect('edited', self.on_cell_name_edit)
        renderer.set_property('cell-background', JobAssignmentPopup.CELL_BACKCOLOR)
        renderer.set_property('font-desc', job_i_font)
        renderer.connect('edited',self.on_cell_edit)
        renderer.connect('editing-started',self.on_cell_edit_start)
        self.tvcolumn.pack_start(renderer)
        self.tvcolumn.add_attribute(renderer, 'text', JobAssignmentPopup.DATA_NAME)
        self.tvcolumn.set_cell_data_func(renderer, self._get_text_render_data)
        self.text_cell = renderer
        self.cell_editable = None

#       scrolled_window_job_table.add(self.job_treeview)
        main_fixed.put(scrolled_window_job_table, JobAssignmentPopup.BASE_WIDGET_OFFSET, JobAssignmentPopup.BASE_WIDGET_OFFSET)

        # show in notebook
        preview_x_start = JobAssignmentPopup.PREVIEW_START_X
        preview_y_start = JobAssignmentPopup.BASE_WIDGET_OFFSET
        preview_width = JobAssignmentPopup.WINDOW_SIZE_X - (JobAssignmentPopup.PREVIEW_START_X + JobAssignmentPopup.BASE_WIDGET_OFFSET)
        preview_height = JobAssignmentPopup.TREE_SIZE_Y
        preview_page_width = preview_width - JobAssignmentPopup.PAGE_WIDTH_REDUCTION
        preview_page_height = JobAssignmentPopup.TREE_SIZE_Y - JobAssignmentPopup.LABEL_HEIGHT - JobAssignmentPopup.PAGE_WIDTH_REDUCTION
        preview_text_height = JobAssignmentPopup.TREE_SIZE_Y - (2 * JobAssignmentPopup.LABEL_HEIGHT)

        self.preview_notebook = gtk.Notebook()
        self.preview_notebook.set_size_request(preview_width, preview_height)
        preview_text_fixed = gtk.Fixed()
        preview_grem_fixed = gtk.Fixed()
        preview_text_fixed.set_size_request(preview_page_width,preview_height - JobAssignmentPopup.LABEL_HEIGHT)
        preview_grem_fixed.set_size_request(preview_page_width,preview_height - JobAssignmentPopup.LABEL_HEIGHT)
        self.preview_notebook.append_page(preview_grem_fixed, gtk.Label('Tool Path'))
        self.preview_notebook.append_page(preview_text_fixed, gtk.Label('Preview'))
        main_fixed.put(self.preview_notebook, preview_x_start, preview_y_start)


        # Preview
        scrolled_window_job_preview = gtk.ScrolledWindow()
        scrolled_window_job_preview.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        self.preview_text_view = gtksourceview2.View()
        self.preview_text_view_buffer = gtksourceview2.Buffer()
        self.preview_text_view.set_buffer(self.preview_text_view_buffer)

        self.preview_text_view.set_editable(False)
        self.preview_normal_font = self.preview_text_view.get_style().font_desc.to_string()
        scrolled_window_job_preview.set_size_request(preview_page_width, preview_text_height - 5)
        scrolled_window_job_preview.add(self.preview_text_view)
        preview_text_fixed.put(scrolled_window_job_preview, 0, JobAssignmentPopup.LABEL_HEIGHT)

        # show line numbers in the preview if the user has them enabled
        showlinenum = (redis.hget('uistate', 'main_tab_gcodewindow_linenumbers') == 'True')
        self.preview_text_view.set_show_line_numbers(showlinenum)

        # show gcode syntax highlighting in the preview if the user has them enabled
        usesyntaxcolor = (redis.hget('uistate', 'main_tab_gcodewindow_syntaxcoloring') == 'True')
        ui_misc.set_sourceview_gcode_syntaxcoloring(self.preview_text_view_buffer, usesyntaxcolor)

        #create a preview window
        self.preview_label = gtk.Label()
        self.preview_label.set_size_request(preview_page_width,JobAssignmentPopup.LABEL_HEIGHT)
        self.preview_label.modify_font(pango.FontDescription(JobAssignmentPopup.PREVIEW_LABEL_FONT))
        self.preview_label.modify_fg(gtk.STATE_NORMAL,gtk.gdk.Color('#222222'))
        self.preview_label.set_justify(gtk.JUSTIFY_CENTER)
        self.preview_label.set_text('PREVIEW')
        preview_text_fixed.put(self.preview_label, 0, 0)

        self.gremlin = self.conversational.ui.create_jobassignment_gremlin(preview_page_width, preview_page_height + 1)
        preview_grem_fixed.put(self.gremlin,0,0)


        self._populate_tree_store(gc_list)
        # end job table init (gtk.treeview)
        # -----------------------------------------
        # window

        self.job_treeview.expand_all()
        self.window.add(main_fixed)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_position(gtk.WIN_POS_CENTER_ON_PARENT)


        self.window.show_all()
        self.buttons['job_un_remove'].hide_all()

        # self.file_chooser.connect("file-activated", self.on_file_activated)

        # -----------------------------------------
        # Set up data
        self.last_used_save_as_path = gc_list[0].path
        self.touchscreen_enabled = touchscreen_enabled
        self.last_sel_path = None


        #------------------------------------------
        # set the selection if it's there
        self.set_selected(segment_uuid)
        if segment_uuid is None:
            self.buttons['job_save'].set_sensitive(self._check_gc_update())
        # Set status
        self.exit_status = self.STATUS_RUNNING
        if curr_notebook_page is not None:
            self.preview_notebook.set_current_page(curr_notebook_page)


    @classmethod
    def clear_modal_data(cls):
        cls.modal_data['original_file_path'] = None
        cls.modal_data['original_file_ext'] = None
        cls.modal_data['save_state']= False
        cls.modal_data['orig_list'] = []

    @staticmethod
    def _gcode_list_to_text(gcode):
        gcode_text = ''
        for line in gcode:
            if 'M30' not in line:
                gcode_text += (line + '\n')
        return gcode_text

    def _init_buttons_data(self):
        button_moving_y = 0.0
        for n,conv_button in enumerate(self.button_list):
            if conv_button['aux'] == 'exclude': continue
            # check to see if current buton is superimposed
            # on the last another...
            button_y_incr = 1.0
            if conv_button['aux'] is not None:
                for i in range(n):
                    if self.button_list[i]['name'] == conv_button['aux']:
                        conv_button['pos'] = self.button_list[i]['pos']
                        button_y_incr = 0.0
                        break
            # setup rest of 'class' level data, which just gets inited once..
            conv_button['pos'] += button_moving_y
            button_moving_y += button_y_incr
            button_y_float = float(JobAssignmentPopup.BUTTON_HEIGHT * conv_button['pos'])
            conv_button['y'] = JobAssignmentPopup.BUTTON_START_Y + int(round(button_y_float,0))

    def _get_icon_modifier(self, segment_data):
        # icon 'ce_state_icon...' files are organized such that the
        # name is additive starting with '_add' (then _update .. etc).
        # if certain states are active in the 'segment_data' the name
        # simply gets added to the string resulting in the correct icon...
        icon_type_name = ''
        if segment_data['new_step']: icon_type_name += '_add'
        if segment_data['can update']: icon_type_name += '_update'
        if segment_data['changed']: icon_type_name += '_edit'
        if segment_data['copy']: icon_type_name += '_copy'
        icon_type = self.icon_modifiers['normal'] if not icon_type_name else self.icon_modifiers[icon_type_name]
        return icon_type['icon']

    def _get_icon(self, segment_data ):
        title = segment_data['segment name']
        icon_name = 'op'
        try:
            if 'Drill' in title:
                icon_name = 'drill'
            elif 'Face' in title:
                icon_name = 'face'
            elif 'Facing' in title:
                icon_name = 'face'
            elif 'Threading' in title:
                icon_name = 'int_thread' if 'Internal' in title else 'ext_thread'
            elif 'Thread' in title:
                icon_name = 'thread'
            elif 'Tapping' in title:
                icon_name = 'tapping'
            elif 'Tap' in title:
                icon_name = 'tap'
            elif 'Profile' in title:
                icon_name = 'mill'
            elif 'Profiling' in title:
                icon_name = 'odturn' if 'External' in title else 'boring'
            elif 'Pocket' in title:
                icon_name = 'mill'
            elif 'OD Turn' in title:
                icon_name = 'odturn'
            elif 'Parting' in title:
                icon_name = 'parting'
            elif 'Groove' in title:
                icon_name = 'parting'
            elif 'ID' in title:
                icon_name = 'boring'
            elif 'Engrave' in title:
                icon_name = 'engrave'
            elif 'DXF' in title:
                icon_name = 'dxf'
            elif 'Threading' in title:
                icon_name = 'int_thread' if 'Internal' in title else 'ext_thread'
            elif 'Radius' in title:
                icon_name = 'boring' if 'Internal' in title else 'odturn'
            elif 'Chamfer' in title:
                icon_name = 'boring' if 'Internal' in title else 'odturn'
            elif 'ExternalCode' in title:
                icon_name = 'ext'
            icon_name += '_icon'
            ret_val = self.icon_data[icon_name]['icon']
            # attempt to get a pix_buf...
            pix_buf = ret_val.get_pixbuf()
            return ret_val
        except KeyError:
            self.error_handler.log('JAPopup._get_icon: KeyError occured in retrieving icon for {}'.format(title))
        except ValueError:
            self.error_handler.log('JAPopup._get_icon: exeption occured in retrieving icon pix_buf for {}'.format(title))
        return self.icon_data['op_icon']['icon']

    def _can_edit(self, routine_data):
        return routine_data['editable']

    def _set_tree_title(self, title=None):
        job = 'Job:  '
        if title is None:
            title = JobAssignmentPopup.modal_data['original_file_name']
        label = self.tvcolumn.get_widget()
        if label:
            label.set_text(job + title)

    def _populate_tree_store(self, gc_list):
        if self.tree_model.get_iter_first() is None:
            JobAssignmentPopup.modal_data['original_file_path'] = gc_list[0].path
            JobAssignmentPopup.modal_data['original_file_name'] = gc_list[0].ncfile.filename()
            JobAssignmentPopup.modal_data['original_file_ext']  = gc_list[0].ncfile.extension()
            self._set_tree_title()
        build_original_uuid_list = not any(JobAssignmentPopup.modal_data['orig_list'])
        for gc in gc_list:
            self._insert_new_file_routines(gc,'force append')
            if build_original_uuid_list:
                for segment in gc.segments:
                    JobAssignmentPopup.modal_data['orig_list'].append(segment['segment uuid'])


    def _update_external_code_description(self,routine_data,action='new'):
        source_str = 'orig' if action == 'revert' else 'mod'
        new_text = routine_data['segment data']['Description'][source_str]
        text = routine_data['segment text']
        descript_str = 'Description = '
        len_ds = len(descript_str)
        pos = text.find(descript_str)
        if pos > 0:
            pos += len_ds
            pos_end = text.find(')',pos)
            routine_data['segment text'] = text[:pos] + new_text + text[pos_end:]
        if action != 'new':
            routine_data['segment data']['Description']['mod'] = routine_data['segment data']['Description']['orig']

    def _get_segment_gcode_cooked(self, segment):
        gcode_text = segment['segment text']
        if type(gcode_text) is str:
            tmp = gcode_text.translate(None,'\r')
        elif type(gcode_text) is unicode:
            tmp = gcode_text.replace('\r', '')  # translate works differently for unicode, which might come alon
        else:
            sys.stderr.write('Warning: passed something other than str or unicode to: %s' % self._get_segment_gcode_cooked.__name__)
            tmp = gcode_text
        ret_val = tmp.split('\n')
        return ret_val

    def _get_segment_gcode(self, model, segment_iter):
        try:
            segment = model.get_value(segment_iter, JobAssignmentPopup.DATA_SEGMENT)
            if segment.has_key('removed'):
                if segment['removed']:
                    return []
            return self._get_segment_gcode_cooked(segment)
        except ValueError:
            self.error_handler.log('JAPopup._get_segment_gcode: Exception ocurred in retrieving segment code.')
        return []

    def _format_file_preview_text(self, sel_iter, gc):
        path_text = gc.preview_data['path']
        gcode_pos = gc.preview_data['path'].find('gcode') + 6
        gcode_pos = 0 if gcode_pos < 6 else gcode_pos
        text = ' Path: %s\n  Tools:.....Description.........................................\n' % path_text[gcode_pos:]
        max_description = 0
        segments = []

        file_path = self.tree_model.get_path(sel_iter)
        n_segments = self.tree_model.iter_n_children(sel_iter)
        for n in range(n_segments):
            child_iter = self.tree_model.get_iter((file_path[0],n))
            segment_data = self.tree_model.get_value(child_iter, JobAssignmentPopup.DATA_SEGMENT)
            segments.append(segment_data)
            tool_data = segment_data['tool data']
            for tool in tool_data:
                max_description = max(max_description, len(tool['tool_description']))


        max_description += 1
        spaces = '                                                                                               '
        for segment in segments:
            tool_data = segment['tool data']
            for tool in tool_data:
                tl = tool['tool_number']
                tmp = '   tool: '
                tmp += spaces[:3-len(tl)]
                tmp += tl
                tmp += ' '
                td = tool['tool_description']
                tmp += td
                tmp += spaces[:max_description-len(td)]
                min_z = tool['min_z']
                tmp += '(min)Z: '
                if min_z >= 0.0: tmp += ' '
                tmp += conversational.conversational_base._NA_ if segment['external code'] else '%.4f' % min_z
                tmp += '\n'
                text += tmp
        return text

    def _get_selected_ordinal(self):
        model, selected_iter = self.job_treeview.get_selection().get_selected()
        if selected_iter is None: return None
        sel_path = model.get_path(selected_iter)
        if len(sel_path) == 1: return None
        ret_val = 0
        for n in range(sel_path[0]):
            ret_val += model.iter_n_children(model.get_iter((n,)))
        ret_val += sel_path[1]
        return ret_val


    def _update_tree_on_save(self, path):
        if JobAssignmentPopup.FLATTEN_ON_SAVE:
            JobAssignmentPopup.modal_data['orig_list'] = []
            reselect = self._get_selected_ordinal()
            self.file_count = 0
            gc = conversational.ConvDecompiler(self.conversational, path, self.conversational.ui.error_handler)
            self.job_treestore.clear()
            self.gc_list = [gc]
            self._populate_tree_store(self.gc_list)
            tree_selection = self.job_treeview.get_selection()
            sel_path = (0,) if reselect is None else (0,reselect)
            tree_selection.select_iter(self.tree_model.get_iter(sel_path))
        else:
            path_part = os.path.dirname(path)
            title = os.path.split(path)[1]
            ext_pos = title.rfind('.')
            title = title[:ext_pos]
            gc_fix_list = self._fix_gc_list()
            gc_fix_list[0].path = path_part
            gc_fix_list[0].title = title
            JobAssignmentPopup.modal_data['orig_list'] = []
            for gc in gc_fix_list:
                for segment in gc.segments:
                    self.conversational.ja_gen_make_orig_gcode(segment)
                    JobAssignmentPopup.modal_data['orig_list'].append(segment['segment uuid'])
            JobAssignmentPopup.modal_data['original_file_path'] = path_part
            JobAssignmentPopup.modal_data['original_file_name'] = title
        self._set_tree_title()
        self.buttons['job_save'].set_sensitive(False)
        self.job_treeview.queue_draw()

    def _check_gc_update(self):
        # test for the 'gc's 'can update' state - this is True if
        # an update to the conversational file is requested because
        # of some future change in conversational file format...
        gc_fix_list = self._fix_gc_list()
        for gc in gc_fix_list:
            if gc.can_update(): return True
        return False

    def _update_save_state(self):
        n = 0
        n_max = len(JobAssignmentPopup.modal_data['orig_list'])
        if self._check_gc_update(): return True
        # otherwise - proceed as before...
        gc_fix_list = self._fix_gc_list()
        save_state = False
        for gc in gc_fix_list:
            # latch 'save_state' if gc.can_update() is True
            save_state = save_state or gc.can_update()
            if save_state: break
            for segment in gc.segments:
                save_state = n == n_max or \
                             segment['changed'] or \
                             segment['segment uuid'] != JobAssignmentPopup.modal_data['orig_list'][n]
                if save_state: break
                n += 1
        save_state = save_state or ( n < n_max and n > 0 )
        JobAssignmentPopup.modal_data['save_state'] = save_state
        return save_state

    def _fix_gc_list(self):
        gc_list = []
        #before bringing down this window the gc list needs to be
        #recreated in the order of the tree
        try:
            for file_part in range(self.file_count):
                file_path = (file_part,)
                file_iter = self.tree_model.get_iter(file_path)
                gc = self.tree_model.get_value(file_iter, JobAssignmentPopup.DATA_SEGMENT)
                gc.segments = []
                gc.line_count = 0

                n_segments = self.tree_model.iter_n_children(file_iter)
                for seg_part in range(n_segments):
                    seg_iter = self.tree_model.get_iter((file_part,seg_part))
                    seg_data = self.tree_model.get_value(seg_iter, JobAssignmentPopup.DATA_SEGMENT)
                    gc.segments.append(seg_data)
                    gc.line_count += seg_data['end line'] - seg_data['start line']
                gc_list.append(gc)
        except:
            self.error_handler.log('JAPopup._fix_gc_list : enouterred error')
        return gc_list

    def _regenerate_segment_on_update(self, segment_data):
        # if the 'can update' flag is set this will call
        # 1) JobAssignment.ja_conversational to load all the conversational
        #    data into the conversational set of DROs ect.
        # 2) regenerate the gcode (because a tool diameter may have changed)
        # 3) JobAssignment.ja_conversational to restore the conversational set
        #    of DROs ect to roginal state.
        if segment_data['external code']: return
        if not segment_data['can update']: return
        restore_data = self.ja.ja_conversational(segment_data, 'edit')
        page_id = segment_data['segment conv'][0]
        valid, new_gcode = self.conversational.ui.generate_gcode(page_id)
        self.ja.ja_conversational(segment_data, 'restore')
        if restore_data and restore_data.has_key('restore_proc'): restore_data['restore_proc'](restore_data)
        if not valid:
            self.error_handler.log('JAPopup._regenerate_segment: gcode validation failed.')
            return
        self.conversational.reparse_parse_tool_updates_gcode(new_gcode, segment_data)
        segment_data['segment text'] = JobAssignmentPopup._gcode_list_to_text(new_gcode)
        segment_data['can update'] = False

    def _optimize_same_tool(self, segment, gcode_segment_list, opt_vars):
        if not JobAssignmentPopup.OPTIMIZE_SAVED_FILES: return

        opt_vars['segment'] = segment
        gcode_list = opt_vars['gcode_list']
        _end = len(gcode_list)
        tool_count = len(segment['tool data'])
        last_tool = opt_vars['last_tool']
        curr_tool =  segment['tool data'][0]['tool_number']
        opt_vars['last_tool'] = segment['tool data'][tool_count-1]['tool_number']
        if curr_tool != last_tool or segment['external code']:
            opt_vars['last_segment'] = opt_vars['segment']
            if any(gcode_list): gcode_list.append(conversational.conversational_base.m1)
            opt_vars['last_segment_index'] = _end+1
            return

        # last segment's gcode: turn off M5, M9, and all G30s after
        _start = _end - (_end - opt_vars['last_segment_index'])
        M5M9_count = 0
        for n in reversed(range(_start,_end)):
            line = gcode_list[n]
            if 'M5' in line and M5M9_count<2:
                gcode_list[n] = ';' + line
                M5M9_count += 1
            elif 'M9' in line and M5M9_count<2:
                gcode_list[n] = ';' + line
                M5M9_count += 1
            elif M5M9_count == 0 and 'G30' in line:
                gcode_list[n] = ';' + line
        # curr segment's gcode: turn off M3, M8, and all G30s before tool call
        tool_found = False
        for n,line in enumerate(gcode_segment_list):
            if 'M8' in line or 'M3' in line:
                pass #gcode_segment_list[n] = ';' + line
            elif conversational.ConvDecompiler._is_tool_line(line):
                gcode_segment_list[n] = ';' + line
                tool_found = True
            elif not tool_found and 'G30' in line:
                gcode_segment_list[n] = ';' + line

        opt_vars['last_segment'] = opt_vars['segment']
        opt_vars['last_segment_index'] = _end

    def _make_code_all(self):
        r_dict = dict( ncfile = '', gcode = [], error = None )
        opt_vars = dict( gcode_list = [],
                         last_segment_index = 0,
                         last_tool = '',
                         last_segment = None,
                         segment = None)
        try:
            self.gc_list = self._fix_gc_list()
            for gc in self.gc_list:
                for segment in gc.segments:
                    self._regenerate_segment_on_update(segment)
                    gcode_segment_list = self._get_segment_gcode_cooked(segment)
                    gc.check_update_fixup(segment, gcode_segment_list)
                    self._optimize_same_tool(segment, gcode_segment_list, opt_vars)
                    opt_vars['gcode_list'] += gcode_segment_list
            r_dict['gcode'] = opt_vars['gcode_list']
            if any(r_dict['gcode']):
                r_dict['gcode'].append('M30 (end program)')
        except Exception as e:
            self.error_handler.log('JAPopup._make_code_all: raised Exception {}'.format(str(e)))
        return r_dict

    def _make_backplot_code(self):
        selection = self.job_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        gcode_list = []
        if selected_iter is None:
            return None

        r_dict = dict( file_name = '', gcode = [], error = None )
        selected_path = model.get_path(selected_iter)
        sel_file = selected_path[0]
        sel_segment = selected_path[1] if len(selected_path) > 1 else None
        if sel_segment is None:
            num_children = model.iter_n_children(selected_iter)
            if num_children == 0:
                r_dict['error'] = 'Nothing to Save'
                return r_dict
            r_dict['file_name'] = model.get_value(selected_iter, JobAssignmentPopup.DATA_NAME)
            for n in range(num_children):
                child_iter = model.get_iter((sel_file,n))
                gcode_list += self._get_segment_gcode(model, child_iter)
            r_dict['gcode'] = gcode_list
        else:
            file_iter = model.get_iter((sel_file,))
            r_dict['file_name'] = model.get_value(file_iter, JobAssignmentPopup.DATA_NAME)
            r_dict['file_name'] += '-'
            r_dict['file_name'] += model.get_value(selected_iter, JobAssignmentPopup.DATA_NAME)
            r_dict['gcode'] = self._get_segment_gcode(model, selected_iter)
        if any(r_dict['gcode']):
            r_dict['gcode'].append('M30 (end program)')
        return r_dict

    def _update_tool_path(self):
        gcode = self._make_backplot_code()
        self.gremlin.load_gcode_list(gcode['gcode'])

    def _pack_file_row_data(self, segment_data):
        if not isinstance(segment_data,conversational.ConvDecompiler):
            return None
        icon = self.icon_data['file_icon']['icon']
        icon_modifier = self.icon_modifiers['normal']['icon']
        return (icon.get_pixbuf(), icon_modifier.get_pixbuf(), segment_data.ncfile.filename(), segment_data)

    def _pack_segment_row_data(self, segment):
        routine_data = segment['segment data']
        routine_name = routine_data['Description']['mod']
        icon = self._get_icon(segment)
        icon_modifier = self._get_icon_modifier(segment)
        return (icon.get_pixbuf(), icon_modifier.get_pixbuf(), routine_name, segment)

    def _get_icon_modifier_render_data(self, column, cell, model, iter_item):
        segment_data = self.tree_model.get_value(iter_item, JobAssignmentPopup.DATA_SEGMENT)
        if segment_data is None:
            return
        removed = False
        if isinstance(segment_data,conversational.ConvDecompiler):
            cell.set_property('cell-background', JobAssignmentPopup.FILE_CELL_BACKCOLOR)
        else:
            if segment_data.has_key('removed'):
                cell.set_property('cell-background', JobAssignmentPopup.DATA_CELL_BACKCOLOR)
            icon = self._get_icon_modifier(segment_data)
            cell.set_property('pixbuf', icon.get_pixbuf())

    def _get_icon_render_data(self, column, cell, model, iter_item):
        segment_data = self.tree_model.get_value(iter_item, JobAssignmentPopup.DATA_SEGMENT)
        if segment_data is None:
            return
        removed = False
        if isinstance(segment_data,conversational.ConvDecompiler):
            cell.set_property('cell-background', JobAssignmentPopup.FILE_CELL_BACKCOLOR)
        else:
            if segment_data.has_key('removed'):
                cell.set_property('cell-background', JobAssignmentPopup.DATA_CELL_BACKCOLOR)
            icon = self._get_icon(segment_data)
            cell.set_property('pixbuf', icon.get_pixbuf())

    def _get_text_render_data(self, column, cell, model, iter_item):
        segment_data = self.tree_model.get_value(iter_item, JobAssignmentPopup.DATA_SEGMENT)
        if segment_data is None:
            return
        removed = False
        if isinstance(segment_data,conversational.ConvDecompiler):
            removed = segment_data.removed
            empty = not self.tree_model.iter_has_child(iter_item)
            color_spec = '#7f7d7a' if removed or empty else '#091872'
            cell.set_property('background', JobAssignmentPopup.FILE_CELL_BACKCOLOR)
            cell.set_property('foreground', color_spec )
            cell.set_property('font-desc', pango.FontDescription('helvetica bold ultra-condensed 14'))
        else:
            if self.hilight_save:
                pass
            else:
                pass
            #older removed logic...
            if segment_data.has_key('removed'):
                removed = segment_data['removed']
                can_edit = not segment_data.has_key('editable') or segment_data['editable']
                color_spec = '#7f7d7a' if removed else '#091872' if can_edit else '#4e5898'
                cell.set_property('background', JobAssignmentPopup.DATA_CELL_BACKCOLOR)
                cell.set_property('foreground', color_spec)
                cell.set_property('font-desc', pango.FontDescription('helvetica ultra-condensed 14'))

        text = cell.get_property('text')
        rem_pos = text.find(JobAssignmentPopup.REMOVED_TEXT)
        if removed:
            if rem_pos < 0:
                text += JobAssignmentPopup.REMOVED_TEXT
                cell.set_property('text', text)
        elif rem_pos > 0:
            text = text[rem_pos:]
            cell.set_property('text', text)

    def _toggle_save_button(self):
        self.buttons['job_save'].set_sensitive(self._update_save_state())


    def _toggle_buttons(self, model, selected_iter):
        if selected_iter is None:
            self.buttons['job_conv_edit'].set_sensitive(False)
            self.buttons['job_remove'].set_sensitive(False)
            self.buttons['job_move_up'].set_sensitive(False)
            self.buttons['job_move_down'].set_sensitive(False)
            self.buttons['job_revert'].set_sensitive(False)
#           self.buttons['job_post'].set_sensitive(False)
            self.buttons['job_ins_from_new'].set_sensitive(False)
#           self.buttons['job_post_n_go'].set_sensitive(False)
#           self.buttons['job_save'].set_sensitive(False)
            self.buttons['job_saveas'].set_sensitive(False)
            self.buttons['job_duplicate'].set_sensitive(False)
            self._toggle_save_button()
        else:
            selected_path = model.get_path(selected_iter)
            sel_file = selected_path[0]
            sel_file_iter = model.get_iter((sel_file,))
            sel_segment = selected_path[1] if len(selected_path) > 1 else None
            sel_num_children = model.iter_n_children(sel_file_iter)

            avail_conv_edit = sel_segment is not None
            if avail_conv_edit:
                segment_data = model.get_value(selected_iter, JobAssignmentPopup.DATA_SEGMENT)
                avail_conv_edit = not segment_data['external code']
                avail_conv_edit = self._can_edit(segment_data)
            self.buttons['job_conv_edit'].set_sensitive(avail_conv_edit)

            avail_move_up = True
            if sel_file == 0 and (sel_segment is None or sel_segment == 0):
                avail_move_up = False
            self.buttons['job_move_up'].set_sensitive(avail_move_up)

            avail_move_down = True
            last_sel_file = sel_file == (self.file_count - 1)
            if last_sel_file and sel_segment is None:
                avail_move_down = False
            elif last_sel_file and sel_segment is not None and sel_segment == (sel_num_children - 1):
                avail_move_down = False
            self.buttons['job_move_down'].set_sensitive(avail_move_down)

            avail_revert = False
            if sel_segment is not None:
                segment_data = model.get_value(selected_iter, JobAssignmentPopup.DATA_SEGMENT)
                avail_revert = segment_data['changed']
            self.buttons['job_revert'].set_sensitive(avail_revert)

            avail_from_new = True
            if sel_segment is None and sel_num_children is 0:
                avail_from_new = False
            self.buttons['job_ins_from_new'].set_sensitive(avail_from_new)

            avail_post = True
            if sel_segment is None and sel_num_children is 0:
                avail_post = False
#           self.buttons['job_post'].set_sensitive(avail_post)
#           self.buttons['job_post_n_go'].set_sensitive(avail_post)
            self.buttons['job_saveas'].set_sensitive(avail_post)
            self._toggle_save_button()

            avail_remove = True
            if sel_segment is None and self.file_count == 0:
                avail_remove = False
            self.buttons['job_remove'].set_sensitive(avail_remove)

            avail_duplicate = True
            if sel_segment is None and self.file_count == 0:
                avail_duplicate = False
            self.buttons['job_duplicate'].set_sensitive(avail_duplicate)

    def _toggle_remove_un_remove(self, data):
        try:
            removed = data.removed if isinstance(data,conversational.ConvDecompiler) else data['removed']
            if removed:
                self.buttons['job_remove'].hide_all()
                self.buttons['job_un_remove'].show_all()
            else:
                self.buttons['job_remove'].show_all()
                self.buttons['job_un_remove'].hide_all()
        except:
            pass
        return

    # not used yet...
    def _remove_file(self, sel_iter, sel_path, sel_segment):
        if not JobAssignmentPopup.REMOVE_FILES:
            return False
        try:
            sel_file = sel_path[0]

            if sel_file + 1 == self.file_count: # it's the last file...
                sel_file = 0 if sel_file == 0 else sel_file - 1
            self.job_treestore.remove(sel_iter)
            for i,gc in enumerate(self.gc_list):
                if sel_segment is gc:
                    self.file_count -= 1
                    self.gc_list.pop(i)
                    break
            # setup a new selected file
            if self.file_count == 0:
                self._set_tree_title('<None>')
                self.implied_selected_file = None
                self._toggle_save_button()
            else:
                tree_selection = self.job_treeview.get_selection()
                new_sel_path = (sel_file,)
                new_sel_iter = self.tree_model.get_iter(new_sel_path)
                tree_selection.select_iter(new_sel_iter)
        except:
            self.implied_selected_file = None
            #the iter can fail if sel_file is less than 0
            # that's OK, it means the last file can't be
            # removed .. just return False
            pass
        return True


    def _remove_segment(self, sel_iter, segment_data):
        is_original_segment = segment_data['copy'] is False
        if is_original_segment and JobAssignmentPopup.SAFE_REMOVE:
            return False
        for gc in self.gc_list:
            if segment_data in gc.segments:
                sel_path = self.tree_model.get_path(sel_iter)
                if len(sel_path) == 2:
                    sel_file, sel_seg = sel_path
                    num_children = self.tree_model.iter_n_children(self.tree_model.get_iter((sel_file,)))
                    sel_seg_next = sel_seg + 1
                    sel_seg = sel_seg_next if sel_seg_next < num_children else (sel_seg - 1)
                    new_sel_path = (sel_file,) if num_children == 1 else (sel_file,sel_seg)
                    tree_selection = self.job_treeview.get_selection()
                    new_sel_iter = self.tree_model.get_iter(new_sel_path)
                    tree_selection.select_iter(new_sel_iter)
                    self.job_treestore.remove(sel_iter)
                    gc.segments.remove(segment_data)
                    return True
        return False


    def _set_data_removed(self, removed=True):
        model, sel_iter, sel_path, sel_segment = self._get_sel_model_iter_path_segment()
        do_toggle = True
        if sel_iter is None or sel_segment is None:
            return
        if isinstance(sel_segment,conversational.ConvDecompiler):
            sel_segment.removed = removed
            if removed:
                sel_segment.state = 'expanded' if self.job_treeview.row_expanded(sel_path) else ''
                self.job_treeview.collapse_row(sel_path)
                if self._remove_file(sel_iter, sel_path, sel_segment):
                    do_toggle = False
            else:
                if sel_segment.state == 'expanded':
                    self.job_treeview.expand_row(sel_path, True)
                sel_segment.state = ''
        elif sel_segment.has_key('removed'):
            sel_segment['removed'] = removed
            if self._remove_segment(sel_iter, sel_segment):
                do_toggle = False
        if do_toggle:
            self._toggle_remove_un_remove(sel_segment)
        self._toggle_save_button()
        self.job_treeview.queue_draw()

    def _insert_new_file_routines(self, gc, action = 'normal'):

        next_file = self.implied_selected_file[0] + 1 if self.implied_selected_file is not None else 0
        if self.file_count == next_file or action == 'force append':
            files = self.job_treestore.append(None, self._pack_file_row_data(gc))
        else:
            files = self.job_treestore.insert(None, next_file, self._pack_file_row_data(gc))
        for segment in gc.segments:
            row_data = self._pack_segment_row_data(segment)
            self.job_treestore.append(files, row_data)
        files_path = self.tree_model.get_path(files)
        self.job_treeview.expand_row(files_path, True)
        self.file_count += 1
        try:
            if self.file_count == 1:
                tree_selection = self.job_treeview.get_selection()
                tree_selection.select_iter(files)
            else:
                # if another file is brought in through 'Insert File'
                # gc.can_update won't be called because the tree selection
                # does not change .. call it here explicitly...
                gc.can_update()
            selection = self.job_treeview.get_selection()
            model, selected_iter = selection.get_selected()
            self._toggle_buttons(model, selected_iter)
        except:
            pass



    def _get_sel_model_iter_path_segment(self):
        selection = self.job_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter is None:
            return (model,selected_iter,(),None)
        path = model.get_path(selected_iter)
        segment = model.get_value(selected_iter, JobAssignmentPopup.DATA_SEGMENT)
        return (model,selected_iter,path,segment)


    def on_cell_name_edit(self,cell,path,text,data=None):
        if any(text):
            self.job_treestore[path][JobAssignmentPopup.DATA_NAME] = text

    def set_selected(self, segment_uuid=None):
        # drill down the tree to make a match on uuid of the
        # segment - this is not recursive because children are
        # only one level deep.
        tree_selection = self.job_treeview.get_selection()
        parent_iter = self.tree_model.get_iter_first()
        if segment_uuid is None:
            tree_selection.select_iter(parent_iter)
            return
        while parent_iter != None:
            num_children = self.tree_model.iter_n_children(parent_iter)
            for n in range(num_children):
                child_iter = self.tree_model.iter_nth_child(parent_iter,n)
                segment = self.tree_model.get_value(child_iter, JobAssignmentPopup.DATA_SEGMENT)
                if segment_uuid == segment['segment uuid']:
                    tree_selection.select_iter(child_iter)
                    break
            parent_iter = self.tree_model.iter_next(parent_iter)



    def get_selected(self, default=None):
        model, selected_iter = self.tree_selection.get_selected()
        if selected_iter is None:
            last_sel_iter = model.get_iter(self.last_sel_path)
            return last_sel_iter
        return selected_iter

    def _get_selected_routine_data(self,qualifier='any'):
        selection = self.job_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter is None:
            if self.last_sel_path is None:
                return None
            selected_iter = model.get_iter(self.last_sel_path)
        if selected_iter is None:
            return None
        if qualifier is 'parent':
            path = model.get_path(selected_iter)
            selected_iter = model.get_iter((path[0],))
        return model.get_value(selected_iter, JobAssignmentPopup.DATA_SEGMENT)

    # these capture a 'double' click action. 'on_row_activate' is called
    # through this not directly, because the second on-button-release event
    # will get the window behind if not comsumed.
    def on_button_press(self, widget, event, data=None):
        self.double_click_row = False
        text_area_start = self.tvcolumn.cell_get_position(self.text_cell)[0]-10
        in_icon_area = event.x > text_area_start and (event.x - text_area_start) <= JobAssignmentPopup.ICON_COLUMN_WIDTH
        model, selected_iter = self.tree_selection.get_selected()
        if event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
            if selected_iter is None:
                self.double_click_path = None
                return
            path = model.get_path(selected_iter)
            if self.double_click_path is not None and path == self.double_click_path:
                self.double_click_path = path
                self.double_click_row = in_icon_area
        elif event.button == 1 and event.type == gtk.gdk.BUTTON_PRESS:
            try:
                click_path,tc,x,y = self.job_treeview.get_path_at_pos(int(event.x), int(event.y))
            except:
                return False
            sel_path = model.get_path(selected_iter) if selected_iter is not None else None
            if len(click_path) == 1 and click_path == sel_path:
                return True
            self.double_click_path = None
            model, selected_iter = self.tree_selection.get_selected()
            if selected_iter is not None:
                sel_path = self.tree_model.get_path(selected_iter)
                if click_path != sel_path:
                    return
                self.double_click_path = model.get_path(selected_iter)
                if in_icon_area:
                    if self.cell_editable:
                        self.text_cell.stop_editing(True)
                        self.cell_editable.remove_widget()
                        self.cell_editable = None
                return in_icon_area


    def on_button_release(self, widget, signal_id, data=None):
        if self.double_click_row and self.double_click_path is not None:
            self.on_row_activated(self.job_treeview, self.double_click_path, None)
            self.double_click_row = False
            self.double_click_path = None

    def on_job_move_up_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        selection = self.job_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter: #result could be None
            selected_path = model.get_path(selected_iter)
            sel_file = selected_path[0]
            sel_segment = selected_path[1] if len(selected_path) > 1 else None
            if sel_segment is None:
                sel_file -= 1
                try:
                    target_iter = model.get_iter((sel_file,))
                    self.job_treestore.move_before(selected_iter, target_iter)
                except ValueError:
                    return
                except:
                    self.error_handler.log('JAPopup.on_job_move_up_button_release_event: exception: on_job_move_up_button_release_event')
                    return
            else:
                if sel_segment == 0: # move to the bottom of the next file up...
                    if sel_file == 0:
                        return
                    sel_file -= 1
                    file_iter = model.get_iter((sel_file,))
                    row = (model.get_value(selected_iter, JobAssignmentPopup.DATA_ICON),
                           model.get_value(selected_iter, JobAssignmentPopup.DATA_ICON_MOD),
                           model.get_value(selected_iter, JobAssignmentPopup.DATA_NAME),
                           model.get_value(selected_iter, JobAssignmentPopup.DATA_SEGMENT))
                    self.job_treestore.append(file_iter,row)
                    self.job_treestore.remove(selected_iter)
                    num_children = model.iter_n_children(file_iter)
                    selected_iter = model.get_iter((sel_file,num_children - 1))
                    if num_children is 1:
                        file_path = model.get_path(file_iter)
                        self.job_treeview.expand_row(file_path, False)
                else:
                    target_iter = model.get_iter((sel_file, sel_segment - 1))
                    self.job_treestore.move_before(selected_iter, target_iter)
                selection.select_iter(selected_iter)

    def on_job_move_down_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        selection = self.job_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter: #result could be None
            selected_path = model.get_path(selected_iter)
            sel_file = selected_path[0]
            sel_segment = selected_path[1] if len(selected_path) > 1 else None
            if sel_segment is None:
                sel_file += 1
                try:
                    target_iter = model.get_iter((sel_file,))
                    self.job_treestore.move_after(selected_iter, target_iter)
                except ValueError:
                    return
                except:
                    self.error_handler.log('JAPopup.on_job_move_down_button_release_event: exception: on_job_move_up_button_release_event')
                    return
            else:
                file_iter = model.get_iter((sel_file,))
                num_children = model.iter_n_children(file_iter)
                if sel_segment + 1 == num_children:
                    if sel_file + 1 == self.file_count:
                        return
                    sel_file += 1
                    file_iter = model.get_iter((sel_file,))
                    row = (model.get_value(selected_iter, JobAssignmentPopup.DATA_ICON),
                           model.get_value(selected_iter, JobAssignmentPopup.DATA_ICON_MOD),
                           model.get_value(selected_iter, JobAssignmentPopup.DATA_NAME),
                           model.get_value(selected_iter, JobAssignmentPopup.DATA_SEGMENT))
                    self.job_treestore.append(file_iter,row)
                    self.job_treestore.remove(selected_iter)
                    num_children = model.iter_n_children(file_iter)
                    selected_iter = model.get_iter((sel_file,num_children - 1))
                    if num_children is 1:
                        file_path = model.get_path(file_iter)
                        self.job_treeview.expand_row(file_path, False)
                    elif num_children > 1:
                        target_iter = model.get_iter((sel_file,0))
                        self.job_treestore.move_before(selected_iter, target_iter)
                        selected_iter = model.get_iter((sel_file,0))
                else:
                    target_iter = model.get_iter((sel_file, sel_segment + 1))
                    self.job_treestore.move_after(selected_iter, target_iter)
                    self._toggle_buttons(model, selected_iter)
                selection.select_iter(selected_iter)

    def on_job_duplicate_button_release_event(self, widget, data=None):
        model,sel_iter,sel_path,sel_segment = self._get_sel_model_iter_path_segment()
        segment_data = model.get_value(sel_iter, JobAssignmentPopup.DATA_SEGMENT)
        copy = conversational.ConvDecompiler.copy(segment_data)
        if isinstance(copy, conversational.ConvDecompiler):
            self._insert_new_file_routines(copy)
            self.gc_list.append(copy)
        else:
            try:
                sel_file, sel_position = sel_path
                file_iter = model.get_iter((sel_file,))
                file_data = model.get_value(file_iter, JobAssignmentPopup.DATA_SEGMENT)
                file_data.segments.insert(sel_position + 1, copy)
                row_data = self._pack_segment_row_data(copy)
                new_iter = self.job_treestore.insert_after(None, sel_iter, row_data)
                selection = self.job_treeview.get_selection()
                selection.select_iter(new_iter)
            except:
                self.error_handler.log('JAPopup.on_job_duplicate_button_release_event: Exception in on_job_duplicate_button_release_event - copy segment')


    def on_job_remove_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        self._set_data_removed()

    def on_job_un_remove_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        self._set_data_removed(False)

    def on_job_ins_from_new_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        self.gc_list = self._fix_gc_list()
        self.quit(self.STATUS_INSERT_NEW)

    def on_job_ins_from_file_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        init_path = self.last_used_save_as_path
        if self.implied_selected_file is not None:
            implied_file_path = self.implied_selected_file
            if implied_file_path[0] < 0:
                model, selected_iter = self.tree_selection.get_selected()
                if selected_iter is None:
                    implied_file_path = self.tree_model.get_path(selected_iter)
                    implied_file_path = (implied_file_path[0],)
            file_iter = self.tree_model.get_iter(implied_file_path)
            segment_data = self.tree_model.get_value(file_iter, JobAssignmentPopup.DATA_SEGMENT)
            init_path = segment_data.path if isinstance(segment_data,conversational.ConvDecompiler) else self.last_used_save_as_path

        with tormach_file_util.file_open_popup(self.window, init_path, "*") as dialog:
            if dialog.response != gtk.RESPONSE_OK:
                return
            # Extract dialog information for later use
            self.last_used_save_as_path = dialog.current_directory
            path = dialog.get_path()
        gc = conversational.ConvDecompiler(self.conversational, path, self.conversational.ui.error_handler)
        if self.tree_model.get_iter_first() is None:
            self._populate_tree_store([gc])
        elif not gc.empty:
            self._insert_new_file_routines(gc)
            self.gc_list.append(gc)

    def on_job_revert_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        routine_data = self._get_selected_routine_data()
        if isinstance(routine_data,conversational.ConvDecompiler):
            self.error_handler.log('JAPopup.on_job_revert_button_release_event: File object selected for revert.')
            return
        if not routine_data['external code']:
            valid, new_gcode = self.conversational.ja_gen_revert_gcode(routine_data)
            if not valid:
                self.error_handler.log('JAPopup.on_job_revert_button_release_event: gcode validation failed.')
                return
            self.conversational.reparse_parse_tool_updates_gcode(new_gcode, routine_data)
            routine_data['segment text'] = JobAssignmentPopup._gcode_list_to_text(new_gcode)
            self._update_tool_path()
        else:
            self._update_external_code_description(routine_data, 'revert')
            routine_data['changed'] = False
        model, sel_iter, sel_path, sel_segment = self._get_sel_model_iter_path_segment()
        self.job_treestore.set_value(sel_iter,JobAssignmentPopup.DATA_NAME,routine_data['segment data']['Description']['mod'])
        self.preview_text_view_buffer.set_text(routine_data['segment text'])
        self.buttons['job_revert'].set_sensitive(False)
        self._toggle_save_button()
        self.job_treeview.queue_draw()

    def _job_save_full_path(self):
        save_path = self.conversational.ui.last_used_save_as_path
        use_path = JobAssignmentPopup.modal_data['original_file_path']
        self.conversational.ui.last_used_save_as_path = use_path
        return (use_path, save_path)

    def _job_save_make_save_dict(self):
        path = JobAssignmentPopup.modal_data['original_file_path']
        save_dict = None
        if path is not None and any(path):
            save_dict = self._make_code_all()
            save_dict['ncfile'] = conversational.nc_file(JobAssignmentPopup.modal_data['original_file_name']+JobAssignmentPopup.modal_data['original_file_ext'])
        return save_dict


    def _job_post(self, save_dict, path=None, query=True, modifier=None):
        assert modifier in (None, 'overwrite', 'close_without_save'), "Unexpected modifier value {}".format(modifier)

        if save_dict is None:
            return (gtk.RESPONSE_CANCEL, None)

        if save_dict['error'] is None:
            use_path, save_path = self._job_save_full_path()

            closewithoutsavebutton = (modifier == 'close_without_save')
            overwrite_ok = (modifier == 'overwrite')

            ret_val, new_path, new_file_name = self.conversational.ui.post_to_file(self.window, str(save_dict['ncfile']), save_dict['gcode'],
                                                                                   query, load_file=False,
                                                                                   closewithoutsavebutton=closewithoutsavebutton,
                                                                                   overwrite_ok=overwrite_ok)
            if ret_val != gtk.RESPONSE_CANCEL and ret_val != gtk.RESPONSE_CLOSE:
                fn = new_file_name if query else str(save_dict['ncfile'])
                use_path = new_path if query else use_path
                save_dict['ncfile'] = conversational.nc_file(fn)
                self.post_n_go_path = os.path.join(use_path, str(save_dict['ncfile']))
            self.conversational.ui.last_used_save_as_path = save_path
        return (ret_val, use_path)

    def on_job_save_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        save_dict = self._job_save_make_save_dict()
        response, use_path = self._job_post(save_dict, path=None, query=False, modifier='overwrite')
        if response != gtk.RESPONSE_CANCEL:
            full_path = os.path.join(use_path, str(save_dict['ncfile']))
            if self.conversational.ui.current_gcode_file_path == full_path and JobAssignmentPopup.EXIT_TO_CURRENT_FILE:
                with popupdlg.ok_cancel_popup(self.window, 'File changed on disk.  Reload?') as dialog:
                    dialog.run()
                    ok_cancel_response = dialog.response
                if ok_cancel_response == gtk.RESPONSE_OK:
                    self.post_n_go_path = full_path
                    self.quit(self.STATUS_SAVING)
            self._update_tree_on_save(full_path)

    def on_job_save_as_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        save_dict = self._job_save_make_save_dict()
        response, use_path = self._job_post(save_dict, path=None, query=True, modifier=None)
        if response != gtk.RESPONSE_CANCEL:
            full_path = os.path.join(use_path, str(save_dict['ncfile']))
            self._update_tree_on_save(full_path)

    def on_job_post_button_release_event(self, widget, data=None):
        return self.on_job_save_as_button_release_event(widget)

    def on_job_post_n_go_button_release_event(self, widget, data=None):
        if self.on_job_post_button_release_event(widget) != gtk.RESPONSE_CANCEL:
            self.quit(self.STATUS_SAVING)

    def on_job_save_button_mouse_enter(self, widget, event, data=None):
        self.hilight_save = True

    def on_job_save_button_mouse_exit(self, widget, event, data=None):
        self.hilight_save = False

    def on_job_saveas_button_mouse_enter(self, widget, event, data=None):
        pass

    def on_job_saveas_button_mouse_exit(self, widget, event, data=None):
        pass

    def on_job_postgo_button_mouse_enter(self, widget, event, data=None):
        pass

    def on_job_postgo_button_mouse_exit(self, widget, event, data=None):
        pass

    def on_cell_edit_start(self, cellrenderer, editable, path):
        self.cell_editable = editable

    def on_cell_edit(self, cellrenderer, path, new_text, data=None):
        try:
            self.cell_editable = None
            sel_iter = self.tree_model.get_iter(path)
            routine_data = self.tree_model.get_value(sel_iter, JobAssignmentPopup.DATA_SEGMENT)
            if isinstance(routine_data,conversational.ConvDecompiler):
                if routine_data.title != new_text:
                    routine_data.title = new_text
            else:
                if routine_data['segment data']['Description']['mod'] == new_text:
                    return

                routine_data['segment data']['Description']['mod'] = new_text
                if not routine_data['external code']:
                    valid, new_gcode = self.conversational.ja_gen_update_gcode(routine_data)
                    if not valid:
                        self.error_handler.log('JAPopup.on_cell_edit: gcode validation failed in update - on_cell_edit.')
                        return
                    routine_data['segment text'] = JobAssignmentPopup._gcode_list_to_text(new_gcode)
                else: # external gcode ...
                    self._update_external_code_description(routine_data)
                routine_data['changed'] = routine_data['segment data']['Description']['mod'] != routine_data['segment data']['Description']['orig']
                self.preview_label.set_text(new_text)
                self.preview_text_view_buffer.set_text(routine_data['segment text'])
                self.buttons['job_revert'].set_sensitive(True)
                self._toggle_save_button()
                self.job_treeview.queue_draw()
        except:
            pass

    def _do_conv_edit_action(self):
        routine_data = self._get_selected_routine_data()
        if not self._can_edit(routine_data): return
        self.routine_under_edit = routine_data
        if self.routine_under_edit is not None:
            self.gc_list = self._fix_gc_list()
            self.quit(self.STATUS_EDITING)

    def on_job_conv_edit_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        self._do_conv_edit_action()

    @property
    def status_is_editing(self):
        return self.exit_status == self.STATUS_EDITING

    @property
    def status_is_inserting_new(self):
        return self.exit_status == self.STATUS_INSERT_NEW



    @property
    def status_is_saving(self):
        return self.exit_status == self.STATUS_SAVING

    @property
    def status_is_canceled(self):
        return self.exit_status == self.STATUS_CANCELED

    def on_job_close_button_release_event(self, widget, data=None):
        self.buttons[widget.get_name()].unshift()
        if self._update_save_state():
            save_dict = self._job_save_make_save_dict()
            response, use_path = self._job_post(save_dict, path=None, query=True, modifier='close_without_save')
            if response == gtk.RESPONSE_OK:
                response = gtk.RESPONSE_CLOSE

            if response == gtk.RESPONSE_CLOSE:
                self.quit(self.STATUS_CANCELED)
        else:
            self.quit(self.STATUS_CANCELED)

    def on_selection_changed(self, treeselection):
        model,selected_iter = treeselection.get_selected()
        self.last_sel_path = None
        if selected_iter is not None:
            self.last_sel_path = model.get_path(selected_iter)
            segment_data = model.get_value(selected_iter, JobAssignmentPopup.DATA_SEGMENT)
            try:
                if isinstance(segment_data,conversational.ConvDecompiler):
                    self.preview_label.set_text(str(segment_data.ncfile))
                    self.preview_text_view.modify_font(pango.FontDescription(JobAssignmentPopup.PREVIEW_FONT))
                    self.preview_text_view_buffer.set_text(self._format_file_preview_text(selected_iter, segment_data))
                    self.selected_uuid = segment_data.path
                    self.implied_selected_file = model.get_path(selected_iter)

                elif segment_data.has_key('segment text'):
                    title = model.get_value(selected_iter, JobAssignmentPopup.DATA_NAME)
#                   self.preview_text_view.modify_font(self.preview_normal_font)
                    self.preview_text_view_buffer.set_text(segment_data['segment text'])
                    self.preview_label.set_text(title)
                    self.sel_file = segment_data['title']
                    self.selected_uuid = segment_data['segment uuid']
                    parent_iter = model.iter_parent(selected_iter)
                    self.implied_selected_file = model.get_path(parent_iter)
            except:
                self.error_handler.log('JAPopup.on_selection_changed: Exception ocurred in JobAssignment.on_selection_changed.')
            self._update_tool_path()
            self._toggle_remove_un_remove(segment_data)
        self._toggle_buttons(model, selected_iter)
        return

    def on_rows_reorderred(self, model, path, iter_item, new_order):
        if not any(path):
            self.on_selection_changed(self.tree_selection)
        return

    def on_row_activated(self, treeview, path, view_column, data = None):
        if path is None or len(path) is 1:
            return
        try:
            iter_item = treeview.get_model().get_iter(path)
            segment_data = treeview.get_model().get_value(iter_item, JobAssignmentPopup.DATA_SEGMENT)
            if segment_data.has_key('external code') and segment_data['external code']:
                return
            if segment_data.has_key('removed') and segment_data['removed']:
                return
            self._do_conv_edit_action()
        except:
            pass

    def on_test_expand_row(self, treeview, iter_item, path):
        if iter_item is not None:
            try:
                segment_data = treeview.get_model().get_value(iter_item, JobAssignmentPopup.DATA_SEGMENT)
                if isinstance(segment_data,conversational.ConvDecompiler):
                    if segment_data.removed:
                        return True
            except:
                pass
        return False


    def quit(self, status):
        self.exit_status = status
        # Only run main_quit() if the current main_level is higher
        # than when we began.  In case an exception breaks the 'with
        # JobAssignmentPopup' block, the main_level can be reduced,
        # and a second call to main_quit() will quit the whole
        # application.
        if gtk.main_level() > self.main_level:
            gtk.main_quit()


    def clear_job_treestore(self):
        self.job_treestore.clear()

    def run(self):
        self.window.show()
        self.main_level = gtk.main_level()  # Record for main_quit() safety
        gtk.main()

    def destroy(self):
        self.window.destroy()
        self.window = None

        # Smack Gtk 2 in order to clue it in which window should be at the top of the z-order.
        # This is not needed by default if you create your top level modal window decorated (with a title bar).
        # But the title bar leaks access out to the window manager menu.
        self.parentwindow.present()
        self.parentwindow = None
        self.conversational = None
        self.main_gremlin_view = None

        # Must clean up the gremlin or resources like threads will leak!
        self.gremlin.destroy()
        self.gremlin = None

        # break circular references which are trouble for garbage collection
        self.preview_text_view = None
        self.preview_text_view_buffer = None
        self.job_treeview = None
        self.tree_model = None
        self.tree_selection = None
        self.job_treestore = None
        self.text_cell = None
        self.gc_list = None
        self.tvcolumn = None
        self.preview_notebook = None


    def __enter__(self):
        self.run()
        return self

    def __exit__(self, type, value, traceback):
        # Automatically called at the end of a with statement.
        self.destroy()

    def stash_gremlin_view(self):
        self.main_gremlin_view = self.conversational.ui.gremlin.ui_view

    @property
    def stashed_main_view(self):
        return self.main_gremlin_view

    @property
    def state(self):
        if self.exit_status in (self.STATUS_SAVING, self.STATUS_CANCELED):
            return dict()
        else:
            return dict(
                        segment_uuid = self.selected_uuid,
                        curr_notebook_page = self.preview_notebook.get_current_page()
                        )

####################################################################################################
# JA - singleton accessor
####################################################################################################
_job_asignment_singleton = None

def JAObj(**kwargs):
    global _job_asignment_singleton
    if _job_asignment_singleton is None: _job_asignment_singleton = JobAssignment(**kwargs)
    return _job_asignment_singleton

####################################################################################################
# JobAssignment - class for job assignment
#
####################################################################################################

class JobAssignment(object):
    is_active = False
    _tt_strings = None

    def __init__(self, **kwargs):
        assert 'ui' in kwargs
        self.ui = kwargs['ui']
        self.conversational = self.ui.conversational
        self.error_handler = self.ui.error_handler
        self.gc_list = []
        self.current_edit_routine_data = None
        self.restore_data = None
        self.job_assignment_popup = None
        # set the default pages for the
        self.main_notebook_pages_edit_mode = ("notebook_main_fixed", "notebook_file_util_fixed")

        # copy the 'Post To File' and 'Append To File' Buttons...
        name = 'job_assignment_finish_editing'
        self.finish_edit_button = btn.ImageButton.copy(self.ui.button_list['post_to_file'], 'finish-editing-button.png', name)
        self.finish_edit_button.connect("button-press-event", self.finish_edit_button.on_button_press_event)
        self.finish_edit_button.connect("button-release-event", self.on_finish_edit_button_release_event)
        gtk.Buildable.set_name(self.finish_edit_button,name+'_button')
        self.finish_edit_button.connect("enter-notify-event",self.ui.on_mouse_enter)
        self.finish_edit_button.connect("leave-notify-event",self.ui.on_mouse_leave)

        name = 'job_assignment_cancel_editing'
        self.cancel_edit_button = btn.ImageButton.copy(self.ui.button_list['append_to_file'], 'cancel-button.png', name)
        self.cancel_edit_button.connect("button-press-event", self.cancel_edit_button.on_button_press_event)
        self.cancel_edit_button.connect("button-release-event", self.on_exit_edit_button_release_event)
        gtk.Buildable.set_name(self.cancel_edit_button,name+'_button')
        self.cancel_edit_button.connect("enter-notify-event",self.ui.on_mouse_enter)
        self.cancel_edit_button.connect("leave-notify-event",self.ui.on_mouse_leave)

        name = 'job_assignment_finish_new'
        self.accept_new_button = btn.ImageButton.copy(self.ui.button_list['post_to_file'], 'button_job_new.png', name)
        self.accept_new_button.connect("button-press-event", self.accept_new_button.on_button_press_event)
        self.accept_new_button.connect("button-release-event", self.on_finish_new_button_release_event)
        gtk.Buildable.set_name(self.accept_new_button,name+'_button')
        self.accept_new_button.connect("enter-notify-event",self.ui.on_mouse_enter)
        self.accept_new_button.connect("leave-notify-event",self.ui.on_mouse_leave)

        name = 'job_assignment_cancel_new'
        self.cancel_new_button = btn.ImageButton.copy(self.ui.button_list['append_to_file'], 'cancel-button.png', name)
        self.cancel_new_button.connect("button-press-event", self.cancel_new_button.on_button_press_event)
        self.cancel_new_button.connect("button-release-event", self.on_exit_new_button_release_event)
        gtk.Buildable.set_name(self.cancel_new_button,name+'_button')
        self.cancel_new_button.connect("enter-notify-event",self.ui.on_mouse_enter)
        self.cancel_new_button.connect("leave-notify-event",self.ui.on_mouse_leave)


    def ja_conversational(self, routine, name):
        return_item = None
        try:
            routine_name = routine['segment name']
            rountines = self.conversational.routine_names['routines']
            data_factory_name = rountines[routine_name][name]
            data_factory_method = getattr(self.conversational, data_factory_name)
            return_item = data_factory_method(routine)
        except:
            self.error_handler.log('JobAssignment.ja_conversational could not find or execute {}.'.format(name))
        return return_item

    def set_gc(self,gc=None):
        if gc is None:
            self.gc_list = []
        else:
            self.gc_list.append(gc)


    def job_assignment_conv_edit(self, **kwargs):
        if not any(self.gc_list):
            return
        JobAssignment.is_active = True

        self.job_assignment_popup = JobAssignmentPopup(self,
                                                       self.ui.window,
                                                       self.ui.redis,
                                                       gc_list=self.gc_list,
                                                       conversational=self.conversational,
                                                       touchscreen_enabled=self.ui.settings.touchscreen_enabled,
                                                       error_handler = self.error_handler,
                                                       **kwargs)
        self.job_assignment_popup.run()

        self.job_assignment_state = self.job_assignment_popup.state
        if self.job_assignment_popup.status_is_editing:
            self.gc_list = self.job_assignment_popup.gc_list
            self.enter_edit_mode(self.job_assignment_popup.routine_under_edit)
        elif self.job_assignment_popup.status_is_saving:
            self.set_gc()
            self.ui.load_gcode_file(self.job_assignment_popup.post_n_go_path)
            JobAssignmentPopup.clear_modal_data()
        elif self.job_assignment_popup.status_is_canceled:
            self.set_gc()
            JobAssignmentPopup.clear_modal_data()
            JobAssignment.is_active = False
        elif self.job_assignment_popup.status_is_inserting_new:
            self.gc_list = self.job_assignment_popup.gc_list
            self.enter_insert_new_mode()

        self.job_assignment_popup.destroy()
        self.job_assignment_popup = None

    def enter_insert_new_mode(self):
        self.ui.conv_edit_prep_new_mode()

        # show the JA buttons in converational
        self.accept_new_button.show_all()
        self.cancel_new_button.show_all()

    def leave_new_mode(self):
        self.accept_new_button.hide_all()
        self.cancel_new_button.hide_all()
        self.ui.conv_edit_exit_new_mode()
        if self.job_assignment_state:
            self.job_assignment_conv_edit(**self.job_assignment_state)

    def enter_edit_mode(self, routine):
        self.in_edit_mode = True
        self.current_edit_routine_data = routine

        # go to the ui and prep the edit op by rearranging
        # the UI
        self.ui.conv_edit_prep_edit_mode(routine)

        # show the JA buttons in converational
        self.finish_edit_button.show_all()
        self.cancel_edit_button.show_all()

        # unpack the routines 'edit' method,
        # which will pack the DROs on the conversational
        # page
        # at this point the conversational page
        # should be visible with the DROs showing
        # correct values...
        self.restore_data = self.ja_conversational(routine, 'edit')


    def leave_edit_mode(self):
        self.finish_edit_button.hide_all()
        self.cancel_edit_button.hide_all()
        self.ui.conv_edit_exit_edit_mode()

        # if there is a restore packet from when this
        # went into edit mode, unpack it and call the
        # routine in the map...
        if self.restore_data is not None:
            if self.restore_data.has_key('restore_proc'):
                restore = self.restore_data['restore_proc']
                restore(self.restore_data)
            self.restore_data = None

        # If any job assignment state was saved, restart the popup
        if self.job_assignment_state:
            self.job_assignment_conv_edit(**self.job_assignment_state)

    def on_finish_edit_button_release_event(self, widget, data=None):
        self.finish_edit_button.unshift()
        page_id = self.current_edit_routine_data['segment conv'][0]
        valid, new_gcode = self.ui.generate_gcode(page_id)
        if not valid:
            return
        if self.conversational.ja_difference(self.current_edit_routine_data) or self.current_edit_routine_data['can update']:
                self.conversational.reparse_parse_tool_updates_gcode(new_gcode, self.current_edit_routine_data)
                self.current_edit_routine_data['segment text'] = JobAssignmentPopup._gcode_list_to_text(new_gcode)
        self.ja_conversational(self.current_edit_routine_data, 'restore')
        self.leave_edit_mode()

    def on_exit_edit_button_release_event(self, widget, data=None):
        self.cancel_edit_button.unshift()
        self.ja_conversational(self.current_edit_routine_data, 'restore')
        self.leave_edit_mode()

    def on_finish_new_button_release_event(self, widget, data=None):
        self.accept_new_button.unshift()
        valid, new_gcode = self.ui.generate_gcode()
        if valid:
            for n,line in enumerate(new_gcode): new_gcode[n] = line+'\n' # need to normalize this for parsing...
            gc = conversational.ConvDecompiler(self.conversational, new_gcode, self.ui.error_handler, action='parse list')
            new_segment = gc.segments[0]
            new_segment['new_step'] = True
            insert_uuid = self.job_assignment_state
            is_path = '/' in insert_uuid['segment_uuid'] or '.' in insert_uuid['segment_uuid']
            #insert...
            for list_gc in self.gc_list:
                new_segment['parent'] = list_gc
                if is_path:
                    if insert_uuid['segment_uuid'] == list_gc.path:
                        list_gc.segments.insert(0, new_segment)
                        insert_uuid['segment_uuid'] = new_segment['segment uuid']
                        break
                else:
                    for n,segment in enumerate(list_gc.segments):
                        if insert_uuid['segment_uuid'] == segment['segment uuid']:
                            list_gc.segments.insert(n+1, new_segment)
                            insert_uuid['segment_uuid'] = new_segment['segment uuid']
                            break
            self.leave_new_mode()
        else:
            pass


    def on_exit_new_button_release_event(self, widget, data=None):
        self.cancel_new_button.unshift()
        self.leave_new_mode()

    def tool_change_listener(self, tool_number):
        # The recipient of calls from ui_common.tool_table_update_observer
        # this loops through current segment data chunks in the gc_list.
        # Each 'gc' corrensponds to a conv-edit gcode file; each 'segment'
        # corresponds to a 'step' or 'operation'. At the end, the gc's
        # can_update method is called to tag the segments.
        if not JobAssignment.is_active: return
        tool_number = str(tool_number)
        description = self.conversational.ui.get_tool_description(tool_number)
        for gc in self.gc_list:
            for segment_data in gc.segments:
                for td in segment_data['tool data']:
                    if tool_number != td['tool_number']: continue
                    td['tool_description'] = description if description is not None else '<none>'
                    self.conversational.tool_radius_adjustment(tool_number, td, segment_data['metric'])
            gc.can_update()

    def main_notebook_policy(self, action='enable'):
        """Summary

        Args:
            action (str, optional): 'enable' to show pages, 'disable' to hide
        """
        enabled = lambda a : a == 'enable'
        effected_pages = self.main_notebook_pages_edit_mode
        for page_id in effected_pages:
            page = self.ui.get_main_notebook_page_by_id(page_id)
            page.show() if enabled(action) else page.hide()

    # ----------------------------------------------------------------------------------------------
    # dynamic tooltip methods
    # ----------------------------------------------------------------------------------------------

    def job_assignment_save_button(self, param):
        if not self.job_assignment_popup: return ''
        show_update_message = self.job_assignment_popup._check_gc_update()
        if not show_update_message: return ''
        return tooltipmgr.TTMgr().get_local_string('conv_edit_job_save_update_text')

    def get_treeview_data(self, param):
        if not self.job_assignment_popup: return ''
        tree_view = self.job_assignment_popup.job_treeview
        if not hasattr(tree_view, '_tool_tip_path'): return ''
        path = tree_view._tool_tip_path
        model = tree_view.get_model()
        gc_object = model[path[0]][3]
        if path is None: return ''
        if not isinstance(gc_object, conversational.ConvDecompiler): return ''
        if not isinstance(path, tuple): return ''
        if len(path)<2:
            file_str = tooltipmgr.TTMgr().get_local_string('job_assignment_op_1faa_file')
            return file_str.format(gc_object.preview_data['path'])
        if len(path)>=2:
            if not self.__class__._tt_strings:
                self.__class__._tt_strings = dict()
                self.__class__._tt_strings['copy']           = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_copy')
                self.__class__._tt_strings['edited']         = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_edited')
                self.__class__._tt_strings['new']            = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_new')
                self.__class__._tt_strings['update']         = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_update')
                self.__class__._tt_strings['optype']         = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_optype')
                self.__class__._tt_strings['opname']         = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_opname')
                self.__class__._tt_strings['external']       = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_external')
                self.__class__._tt_strings['tool_type']      = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_tooltype')
                self.__class__._tt_strings['tool_data']      = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_tooldata')
                self.__class__._tt_strings['tool_radius']    = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_toolradius')
                self.__class__._tt_strings['tool_diameter']  = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_tooldiameter')
                self.__class__._tt_strings['warn_tool_diff'] = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_warn_tool_diff')
                self.__class__._tt_strings['needs_update']   = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_needupdate')
                self.__class__._tt_strings['undefined']        = tooltipmgr.TTMgr().get_local_string('job_assignment_1faa_undefined')
            _tt_s = self.__class__._tt_strings
            segment_data = gc_object.segments[path[1]]
            tdr = ui_support.ToolDescript.parse_text(segment_data['tool data recorded'][0]['tool_description'])
            text = _tt_s['optype']+segment_data['segment name']+'\n'
            text += _tt_s['opname'].format(segment_data['segment data']['Description']['mod'])+'\n'
            _text_len = len(text)
            if segment_data['copy']: text += _tt_s['copy']
            if segment_data['changed']: text += _tt_s['edited']
            if segment_data['new_step']: text += _tt_s['new']
            if segment_data['can update']: text += _tt_s['update']
            if segment_data['external code']: text += _tt_s['external']
            if len(text)>_text_len: text += '\n'
            typ_string = _tt_s['tool_type']
            tool_type_str = tdr.data['type'][0]['ref'].lower()
            if not tool_type_str: tool_type_str = _tt_s['undefined']
            axial = tool_type_str in ('endmill','drill','centerdrill','tap','ball','chamfer','spot','flat','taper','bullnose','reamer','indexable')
            dia_string = _tt_s['tool_diameter']
            if self.ui.machine_type == constants.MACHINE_TYPE_LATHE and not axial: dia_string = _tt_s['tool_radius']
            tool_description_str = segment_data['tool data recorded'][0]['tool_description']
            if not tool_description_str: tool_description_str = _tt_s['undefined']
            text += _tt_s['tool_data'].format(segment_data['tool data recorded'][0]['tool_number'], \
                                              typ_string.format(tool_type_str),\
                                              dia_string.format(segment_data['tool data recorded'][0]['tool_rd']), \
                                              tool_description_str)
            if segment_data['can update']:
                update_color = '#ff0000'
                if ui_support.ToolDescript.differences(segment_data['tool data recorded'][0]['tool_description'],segment_data['tool data'][0]['tool_description']) > 0:
                    text += '\n'+_tt_s['warn_tool_diff']
                    update_color = '#6500b3'
                text += '\n'+_tt_s['needs_update'].format(update_color)
            return text


