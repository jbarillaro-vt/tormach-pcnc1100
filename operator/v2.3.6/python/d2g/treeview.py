import gtk
import gobject
import traceback


class ShapeSelectionTreeView(gobject.GObject):
    __gsignals__ = {
        'layers-changed': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            (gobject.TYPE_BOOLEAN,),
        )  # needs full update
    }

    def __init__(self):
        gobject.GObject.__init__(self)

        # create tree store
        self.store = gtk.TreeStore(bool, bool, str, object)

        self.treeview = gtk.TreeView(self.store)
        self.treeview.connect('cursor-changed', self._on_cursor_changed)
        self.treeview.set_headers_visible(True)
        self.treeview.set_reorderable(True)
        self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        # define columns
        enable_col = gtk.TreeViewColumn('Enable')
        cellrenderertoggle = gtk.CellRendererToggle()
        cellrenderertoggle.set_activatable(True)
        enable_col.pack_start(cellrenderertoggle, True)
        enable_col.set_min_width(60)
        enable_col.add_attribute(cellrenderertoggle, 'active', 0)
        enable_col.add_attribute(cellrenderertoggle, 'inconsistent', 1)
        cellrenderertoggle.connect("toggled", self._on_cell_toggled)
        self.treeview.append_column(enable_col)

        id_col = gtk.TreeViewColumn('ID', gtk.CellRendererText(), text=2)
        self.treeview.append_column(id_col)

        offset_text_renderer = gtk.CellRendererText()
        offset_col = gtk.TreeViewColumn('Path', offset_text_renderer)
        offset_lookup = {0: "", 40: "On", 41: "Out", 42: "In"}

        def celldatafunction(column, cell, model, iter_):
            data = model.get(iter_, 3)[0]
            if "cut_cor" in data:
                text = offset_lookup[data['cut_cor']]
            else:
                text = ""
            cell.set_property("text", text)

        offset_col.set_cell_data_func(offset_text_renderer, celldatafunction)
        self.treeview.append_column(offset_col)

        self.sw = gtk.ScrolledWindow()
        self.sw.set_size_request(200, 400)

        self.sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)
        self.sw.set_can_focus(False)
        self.sw.add(self.treeview)

        self._layers = []
        self._exanded_rows = []

    @property
    def layers(self):
        """
        Structure of the layers object:

        [
            (
                {layer attrs: 'axis3_retract', 'axis3_safe_margin', 'tool_nr', 'tool_diameter',
                                'speed', 'start_radius', 'name'},
                [
                    {shape attrs: 'nr', 'cut_cor', 'selected', 'disabled', 'cw', 'allowed_to_change',
                          'axis3_start_mill_depth', 'axis3_slice_depth', 'axis3_mill_depth', 'f_g1_plane', 'f_g1_depth'},
                    {shape 2 attrs}
                ]
            ),
            (
                {layer 2 attrs},
                [
                    {shape attrs},
                    {shape 2 attrs}
                ]
            )
        ]

        returns: A list of layers currently held by the treeview
        """
        return self._layers

    @layers.setter
    def layers(self, layers):
        self._save_row_expansion_state()
        self._layers = layers
        self.store.clear()
        for layer, shapes in layers:
            root = self.store.append(None, [True, True, layer['name'], layer])
            has_enabled = False
            has_disabled = False
            for shape in shapes:
                has_enabled |= not shape['disabled']
                has_disabled |= shape['disabled']
                self.store.append(
                    root, [not shape['disabled'], False, str(int(shape['nr'])), shape]
                )
            self.store.set_value(root, 0, has_enabled)  # active
            self.store.set_value(root, 1, has_enabled and has_disabled)  # inconsistent
        self._sync_selection()
        self._restore_row_expansion_state()

    def _select_layer_and_shape(self, path):
        i_l = path[0]
        i_s = None
        if len(path) > 1:
            i_s = path[1]

        layer, shapes = self._layers[i_l]
        if i_s is not None:
            shapes[i_s]['selected'] = True
        else:
            for shape in shapes:
                shape['selected'] = True

    def _clear_layer_and_shape_selection(self):
        for layer, shapes in self._layers:
            for shape in shapes:
                shape['selected'] = False

    def move_selected_shape_up(self):
        paths = self._get_selected_paths(self.treeview)
        if len(paths) == 0:
            return

        path = paths[0]
        i_l = path[0]
        layers = self._layers
        if len(path) == 1:  # layer
            if i_l < 1:
                return
            layers.insert(i_l - 1, layers.pop(i_l))
            self.layers = layers
            self._select_path(str(i_l - 1))
        else:  # shape
            i_s = path[1]
            if i_s < 1:
                return
            layer, shapes = layers.pop(i_l)
            shapes.insert(i_s - 1, shapes.pop(i_s))
            layers.insert(i_l, (layer, shapes))
            self.layers = layers
            self._select_path('%i:%i' % (i_l, i_s - 1))
        self.emit('layers-changed', False)

    def move_selected_shape_down(self):
        paths = self._get_selected_paths(self.treeview)
        if len(paths) == 0:
            return

        path = paths[0]
        i_l = path[0]
        layers = self._layers
        if len(path) == 1:  # layer
            if i_l > len(self._layers) - 2:
                return
            layers.insert(i_l + 1, layers.pop(i_l))
            self.layers = layers
            self._select_path(str(i_l + 1))
        else:  # shape
            i_s = path[1]
            if i_s > len(self._layers[i_l][1]) - 2:
                return
            layer, shapes = layers.pop(i_l)
            shapes.insert(i_s + 1, shapes.pop(i_s))
            layers.insert(i_l, (layer, shapes))
            self.layers = layers
            self._select_path('%i:%i' % (i_l, i_s + 1))

        self.emit('layers-changed', False)

    def move_selected_shape_bottom(self):
        paths = self._get_selected_paths(self.treeview)
        if len(paths) == 0:
            return

        path = paths[0]
        i_l = path[0]
        layers = self._layers
        if len(path) == 1:  # layer
            layers.append(layers.pop(i_l))
            self.layers = layers
            self._select_path(str(len(layers) - 1))
        else:  # shape
            i_s = path[1]
            layer, shapes = layers.pop(i_l)
            shapes.append(shapes.pop(i_s))
            layers.insert(i_l, (layer, shapes))
            self.layers = layers
            self._select_path('%i:%i' % (i_l, len(shapes) - 1))

        self.emit('layers-changed', False)

    def expand_all(self):
        self.treeview.expand_all()

    def collapse_all(self):
        self.treeview.collapse_all()

    def unselect_all(self):
        selection = self.treeview.get_selection()
        selection.unselect_all()
        self._clear_layer_and_shape_selection()
        self.emit('layers-changed', False)

    def set_attr_for_selection(self, attr, value):
        paths = self._get_selected_paths(self.treeview)
        if len(paths) == 0:
            return
        for path in paths:
            i_l = path[0]
            i_s = None
            if len(path) > 1:
                i_s = path[1]

            layer, shapes = self._layers[i_l]
            if i_s is not None:
                shapes[i_s][attr] = value
        self.emit('layers-changed', False)

    def get_attr_for_selection(self, attr):
        """
        Get the value of the attribute with name attr, returning None if there are no items selected,
        or items in the selection have different values for attr
        """
        paths = self._get_selected_paths(self.treeview)
        if len(paths) == 0:
            return None
        value = None
        for path in paths:
            i_l = path[0]
            i_s = None
            if len(path) > 1:
                i_s = path[1]

            layer, shapes = self._layers[i_l]
            if i_s is not None:
                if value is None or shapes[i_s][attr] == value:
                    value = shapes[i_s][attr]
                else:
                    return None
        return value

    def _get_selected_paths(self, treeview):
        selection = treeview.get_selection()
        try:
            rows = selection.get_selected_rows()[1]
        except IndexError:
            rows = []
        return rows

    def _select_path(self, path):
        selection = self.treeview.get_selection()
        selection.select_path(path)
        self.treeview.scroll_to_cell(path)

    def _sync_selection(self):
        self.treeview.get_selection().unselect_all()
        for i_l, (layer, shapes) in enumerate(self._layers):
            has_unselected = False
            has_selected = False
            for i_s, shape in enumerate(shapes):
                if shape['selected']:
                    self.treeview.expand_row(str(i_l), True)
                    self._select_path('%i:%i' % (i_l, i_s))
                    has_selected = True
                else:
                    has_unselected = True
            if has_selected and not has_unselected:  # all shapes selected
                self._select_path(str(i_l))

    def _save_row_expansion_state(self):
        self._expanded_rows = []
        for i in range(len(self._layers)):
            if self.treeview.row_expanded(i):
                self._expanded_rows.append(i)

    def _restore_row_expansion_state(self):
        for i in self._expanded_rows:
            self.treeview.expand_row(i, True)

    def _on_cell_toggled(self, cellrenderertoggle, treepath):
        path = treepath.split(':')
        enabled = self.store[treepath][0]
        i_l = int(path[0])
        if len(path) > 1:
            i_s = int(path[1])
            self.store[treepath][0] = not enabled
            self._layers[i_l][1][i_s]['disabled'] = enabled
        else:
            self.store[treepath][0] = not enabled
            for i_s, shape in enumerate(self._layers[i_l][1]):
                treepath = '%i:%i' % (i_l, i_s)
                self.store[treepath][0] = not enabled
                self._layers[i_l][1][i_s]['disabled'] = enabled
        self.emit('layers-changed', False)

    def _on_cursor_changed(self, treeview):
        paths = self._get_selected_paths(treeview)
        if len(paths) == 0:
            return
        self._clear_layer_and_shape_selection()
        for path in paths:
            self._select_layer_and_shape(path)
        self.emit('layers-changed', False)


gobject.type_register(ShapeSelectionTreeView)
