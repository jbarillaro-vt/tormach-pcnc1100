import os
from math import radians, degrees

import gobject

from d2g.canvas3d import Canvas3D
from d2g.dbusclient import DBusClient
from d2g.dbusclient import DBusException
from d2g.treeview import ShapeSelectionTreeView
from constants import GLADE_DIR
import gtk


try:
    import wingdbstub
except ImportError:
    pass


def raises_dbus_error(message):
    def wrap_args(func):
        def wrap_function(*args, **kwargs):
            panel = args[0]
            try:
                return func(*args, **kwargs)
            except DBusException as e:
                panel._report_error(message % str(e))

        return wrap_function

    return wrap_args


def slow_function():
    """ Decorator for slow functions. Shows a single plexiglass even with nested calls."""

    def wrap_args(func):
        def wrap_function(self, *args, **kwargs):
            if not self._plexiglass_in_use:
                try:
                    self._plexiglass_in_use = True
                    with self.get_plexiglass_cb():
                        result = func(self, *args, **kwargs)
                finally:
                    self._plexiglass_in_use = False
                return result
            else:
                return func(self, *args, **kwargs)

        return wrap_function

    return wrap_args


class DummyPlexiglass(object):
    # pylint doesn't like the __exit__ method here
    # pylint: disable=no-method-argument

    def write(self, data):
        pass  # ignore the data

    def __enter__(self):
        return self

    def __exit__(*x):
        pass


class BaseD2gPanel(gobject.GObject):
    __gsignals__ = {
        'open-file-requested': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'errored': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            (gobject.TYPE_STRING,),
        ),  # message
    }

    def __init__(self, parentUI, common_dros):
        gobject.GObject.__init__(self)

        self.parentUI = parentUI
        self._builder = gtk.Builder()
        gladefile = os.path.join(GLADE_DIR, 'mill_dxf.glade')
        self._builder.add_from_file(gladefile)
        self._common_dros = common_dros

        # DXF DROs
        self._dxf_dro_list = (
            'dxf_z_start_mill_depth_dro',
            'dxf_z_slice_depth_dro',
            'dxf_z_mill_depth_dro',
            'dxf_x_offset_dro',
            'dxf_y_offset_dro',
            'dxf_scale_dro',
            'dxf_rotation_angle_dro',
        )

        self._dxf_dro_list = dict(
            (i, self._builder.get_object(i)) for i in self._dxf_dro_list
        )
        for name, dro in self._dxf_dro_list.items():
            dro.modify_font(self.parentUI.conv_dro_font_description)

        self.checkbuttonlist = 'dxf_g40_button', 'dxf_g41_button', 'dxf_g42_button'

        self._conv_dxf_fixed = self._builder.get_object('conv_dxf_fixed')
        self._dro_fixed = self._builder.get_object('dxf_dro_fixed')
        self._set_all_dro_sensitivity(False)  # disable until file is loaded
        self._dros = {}
        self._entity_dros = {}

        self._dros['z_start_mill_depth'] = self._builder.get_object(
            'dxf_z_start_mill_depth_dro'
        )
        self._dros['z_slice_depth'] = self._builder.get_object('dxf_z_slice_depth_dro')
        self._dros['z_mill_depth'] = self._builder.get_object('dxf_z_mill_depth_dro')

        for dro in self._dros.values():
            dro.connect('activate', self._on_dro_changed)

        for dro in self._common_dros.values():
            dro.connect('activate', self._on_dro_changed)

        self._entity_dros['rotate'] = self._builder.get_object('dxf_rotation_angle_dro')
        self._entity_dros['scale'] = self._builder.get_object('dxf_scale_dro')
        self._entity_dros['x_offset'] = self._builder.get_object('dxf_x_offset_dro')
        self._entity_dros['y_offset'] = self._builder.get_object('dxf_y_offset_dro')

        for dro in self._entity_dros.values():
            dro.connect('activate', self._on_dro_changed)

        self._dro_activation_order = {
            self._dros['z_start_mill_depth']: self._dros['z_slice_depth'],
            self._dros['z_slice_depth']: self._dros['z_mill_depth'],
            self._dros['z_mill_depth']: self._entity_dros['x_offset'],
            self._entity_dros['x_offset']: self._entity_dros['y_offset'],
            self._entity_dros['y_offset']: self._entity_dros['scale'],
            self._entity_dros['scale']: self._entity_dros['rotate'],
            self._entity_dros['rotate']: self._dros['z_start_mill_depth'],
        }

        self._filename_dro = self._builder.get_object('dxf_filename_dro')
        self._filename_dro.connect(
            'button-release-event', self._on_filename_dro_focused
        )

        self._move_down_button = self._builder.get_object('dxf_move_down_button')
        self._move_down_button.connect('released', self._on_move_down_button_released)
        self._move_bottom_button = self._builder.get_object('dxf_move_bottom_button')
        self._move_bottom_button.connect(
            'released', self._on_move_bottom_button_released
        )
        self._move_up_button = self._builder.get_object('dxf_move_up_button')
        self._move_up_button.connect('released', self._on_move_up_button_released)
        self._move_down_button.set_sensitive(False)
        self._move_up_button.set_sensitive(False)
        self._move_bottom_button.set_sensitive(False)
        self._fold_button = self._builder.get_object('dxf_fold_button')
        self._fold_button.connect('released', self._on_fold_button_released)
        self._unfold_button = self._builder.get_object('dxf_unfold_button')
        self._unfold_button.connect('released', self._on_unfold_button_released)
        self._g40_button = self._builder.get_object('dxf_g40_button')
        self._g40_button.modify_bg(
            gtk.STATE_PRELIGHT, self.parentUI._check_button_hilight_color
        )
        self._g40_button.connect('released', self._on_g40_button_released)
        self._g41_button = self._builder.get_object('dxf_g41_button')
        self._g41_button.connect('released', self._on_g41_button_released)
        self._g42_button = self._builder.get_object('dxf_g42_button')
        self._g42_button.connect('released', self._on_g42_button_released)

        drawing_area = self._builder.get_object('dxf_drawing_area')
        self._canvas3d = Canvas3D(*drawing_area.get_size_request())
        self._canvas3d.connect('layers-changed', self._on_layers_changed)
        self._canvas3d.connect('expose_event', self._on_expose)
        drawing_area.pack_start(self._canvas3d, expand=True, fill=True)

        # preview eventbox is used to "overlay" the preview canvas
        self._preview_eventbox = self._builder.get_object('dxf_preview_eventbox')
        self._preview_eventbox.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color('#000'))
        self._preview_eventbox.connect('button-release-event', self._on_preview_clicked)

        treeview = self._builder.get_object('dxf_treeview')
        self._treeview = ShapeSelectionTreeView()
        self._treeview.connect('layers-changed', self._on_layers_changed)
        treeview.pack_start(self._treeview.sw, expand=True, fill=True)

        self._treeview.treeview.get_selection().connect(
            'changed', self.on_selection_changed
        )

        self.get_tool_diameter_cb = lambda index: 0.0
        self.validate_and_format_dro_cb = lambda widget, _format: True
        self.gui_is_metric_cb = lambda: True
        self.get_plexiglass_cb = (
            lambda: DummyPlexiglass()
        )  # we use plexiglass for time intensive operations
        self._plexiglass_in_use = False

        self._scale = 1.0
        self._rotation = 0.0
        self._dx = 0.0
        self._dy = 0.0
        self._file_loaded = False
        self._is_metric = True
        self._ready = False
        self._dros_invalidated = False

        self.enable_remote_update = (
            False
        )  # in theory we could use the remote D2G instance with multiple clients
        self.enable_preview_update = (
            False
        )  # set this to true to enable automatic updates of the preview

    @property
    def panel_fixed(self):
        return self._conv_dxf_fixed

    @property
    def dro_list(self):
        return self._dxf_dro_list

    def restore_dros(self, saved_values):
        for dro_name, val in saved_values.items():
            if dro_name in self.dro_list:
                self.dro_list[dro_name].set_text(val)

    def _set_all_dro_sensitivity(self, sensitivity):
        # labels look really broken and fuzzy when they are disabled
        # appears buggy, not disabled to most users
        # so just disable the dros entry and radio buttons.
        for child in self._dro_fixed.get_children():
            if type(child) is not gtk.Label:
                child.set_sensitive(sensitivity)

    @property
    def cutter_compensation(self):
        return self._get_g4x_buttons()

    @cutter_compensation.setter
    def cutter_compensation(self, value):
        self._set_g4x_buttons(value)

    @property
    def enabled_layers(self):
        """
        Returns the enabled state and order of all layers and shapes.
        """
        enabled = []
        for layer, shapes in self._treeview.layers:
            shape_list = []
            for shape in shapes:
                shape_list.append(
                    [int(shape['nr']), bool(not shape['disabled'])]
                )  # we use lists instead of tuples
            enabled.append(
                [str(layer['name']), shape_list]
            )  # because they are easy to represent in GCode comments
        return enabled

    @enabled_layers.setter
    def enabled_layers(self, data):
        """
        Sets the order and enabled state of all layers and shapes.
        The preview screen needs to be updated afterwards.
        """
        new_order = []

        def update_layer(shapes, real_shapes):
            new_order = []
            for shape in shapes:
                for real_shape in real_shapes:
                    if shape[0] == real_shape['nr']:
                        real_shape['disabled'] = not shape[1]
                        new_order.append(real_shape)
                        break
            return new_order

        for layer, shapes in data:
            for real_layer, real_shapes in self._treeview.layers:
                if layer == real_layer['name']:
                    new_shapes = update_layer(shapes, real_shapes)
                    new_order.append((real_layer, new_shapes))
                    break
        self._treeview.layers = new_order
        self._update_layers()

    preserved_layer_attrs = []
    preserved_shape_attrs = ["cut_cor", "disabled"]

    @property
    def layer_attrs(self):
        """
        Create an ordered list of layers and the current attribute settings on them.
        Can be used to restore the attributes after a DXF reload.

        This is a more generalized version of the enabled_layers getter and setter above.
        """
        layer_list = []
        for layer, shapes in self._treeview.layers:
            layer_attrs = {}
            for attrname in BaseD2gPanel.preserved_layer_attrs:
                layer_attrs[attrname] = layer[attrname]
            shape_list = []
            for shape in shapes:
                shape_attrs = {}
                for attrname in BaseD2gPanel.preserved_shape_attrs:
                    shape_attrs[attrname] = shape[attrname]
                shape_list.append([shape['nr'], shape_attrs])
            layer_list.append([str(layer['name']), layer_attrs, shape_list])
        return layer_list

    @layer_attrs.setter
    def layer_attrs(self, data):
        """
        Sets the order and preserved attributes of all layers and shapes.
        The preview screen needs to be updated afterwards.
        """
        new_order = []

        def update_layer_shapes(shapes, real_shapes):
            new_order = []
            for shape in shapes:
                for real_shape in real_shapes:
                    if shape[0] == real_shape['nr']:
                        for key in shape[1]:
                            real_shape[key] = shape[1][key]
                        new_order.append(real_shape)
                        break
            return new_order

        for layer, layer_attrs, shapes in data:
            for real_layer, real_shapes in self._treeview.layers:
                if layer == real_layer['name']:
                    for key in layer_attrs:
                        real_layer[key] = layer_attrs[key]
                    new_shapes = update_layer_shapes(shapes, real_shapes)
                    new_order.append((real_layer, new_shapes))
                    break
        self._treeview.layers = new_order
        self._update_layers()

    @property
    def dxf_file_path(self):
        return self._get_dxf_file_path()

    @property
    def file_loaded(self):
        return self._file_loaded

    @property
    def ready(self):
        return self._ready

    @ready.setter
    def ready(self, value):
        if value:
            self.enable_preview_update = True
            if not self._file_loaded:
                self._show_preview()
            else:
                self._unload_preview()  # for some reason unloading again helps to prevent render errors
        else:
            self._treeview.unselect_all()
            self._unload_preview()
            self.enable_preview_update = False
            self._hide_preview()
        self._ready = value

    def unload(self):
        """ must be called when preview is hidden to prevent render problems on next drawing """
        if not self._file_loaded:
            return
        self._file_loaded = False
        self._treeview.layers = []
        self._canvas3d.clear()
        self._set_all_dro_sensitivity(False)
        self._filename_dro.set_text('filename.dxf')

    def _unload_preview(self):
        """ unloads the preview canvas, frees memory and prevents render problems when changing tabs """
        self._canvas3d.clear()
        self._canvas3d.update()

    def _show_preview(self):
        self._preview_eventbox.set_visible(False)

    def _hide_preview(self):
        self._preview_eventbox.set_visible(True)

    @slow_function()
    @raises_dbus_error('Error loading DXF file: %s')
    def load_dxf_file(self, filename, plot=True):
        self._show_preview()
        dbusclient = DBusClient()
        self._canvas3d.reset_viewport()
        # load the dxf file
        dbusclient.load(os.path.expanduser(filename))

        # we need to know whether the DXF file is metric or not to scale the input values
        self._is_metric = dbusclient.get_is_metric()

        # reset entity values to default
        if self.enable_remote_update:
            self._reset_entity_values()
        else:
            try:
                self._update_entity_values_from_dros()
            except ValueError:
                pass
        self._set_entity_values(auto_reload=False)

        dbusclient.make_shapes()
        self._load_layers(dbusclient)

        # update GUI elements
        if self.enable_remote_update:
            self._update_dros_from_layer_values()
        else:
            try:
                self._update_layer_values_from_dros(auto_reload=False)
                self._update_tool_info_from_tool_table()
            except ValueError:
                pass
        if plot:
            self._plot()
        self._file_loaded = True
        self._filename_dro.set_text(os.path.basename(filename))
        self._set_all_dro_sensitivity(True)
        self._dros_invalidated = False
        self._validate_all_dros()  # clear errors

    @slow_function()
    @raises_dbus_error('Error converting DXF file: %s')
    def convert_dxf_file(self, output_filename=None, postpro_override_values=None):
        if postpro_override_values is None:
            postpro_override_values = {}
        dbusclient = DBusClient()
        if not output_filename:
            filename, ext = os.path.splitext(dbusclient.get_filename())
            output_filename = filename + '.nc'
        dbusclient.export_shapes(
            output_filename, self.gui_is_metric_cb(), postpro_override_values
        )
        return output_filename

    def redraw(self):
        self._canvas3d.redraw()

    def _get_unit_scale_factor(self):
        dxf_is_metric = self._is_metric
        gui_is_metric = self.gui_is_metric_cb()

        factor = int(dxf_is_metric) or 25.4
        factor /= int(gui_is_metric) or 25.4

        return factor

    @raises_dbus_error('Error aquiring DXF file path: %s')
    def _get_dxf_file_path(self):
        dbusclient = DBusClient()
        return dbusclient.get_filename()

    @slow_function()
    @raises_dbus_error('Error plotting DXF file: %s')
    def _plot(self):
        self._show_preview()
        dbusclient = DBusClient()
        if self.gui_is_metric_cb():
            self._canvas3d.number_format = '%.3f'
        else:
            self._canvas3d.number_format = '%.4f'
        self._canvas3d.shapes = dbusclient.plot()
        self._canvas3d.export_route = dbusclient.plot_export_route()
        self._canvas3d.update()

    @raises_dbus_error('Error exporting optimization route: %s')
    def _plot_export_route(self):
        dbusclient = DBusClient()
        self._canvas3d.export_route = dbusclient.plot_export_route()

    def _reset_entity_values(self):
        self._scale = 1.0
        self._rotation = 0.0
        self._dx = 0.0
        self._dy = 0.0
        self._update_entity_value_dros()

    @raises_dbus_error('Error setting DXF entity values: %s')
    def _set_entity_values(self, auto_reload=True):
        scale_factor = self._get_unit_scale_factor()
        dbusclient = DBusClient()
        values = {
            'rotation': self._rotation,
            'scale': self._scale * scale_factor,
            'dx': self._dx,
            'dy': self._dy,
        }
        dbusclient.set_entity_root_values(values)
        if auto_reload:
            self._reload()

    @slow_function()
    @raises_dbus_error('Error loading DXF file: %s')
    def _reload(self):
        """Rebuild the DXF layers and shapes, taking into account any changed rotation and scale values
        This will destroy any custom attributes set on a per-layer basis (cut-cor, etc)
        """
        # layer_state = self.enabled_layers  # save layer state
        layer_attrs = self.layer_attrs
        dbusclient = DBusClient()
        dbusclient.make_shapes()
        self._load_layers(dbusclient)
        self.layer_attrs = layer_attrs
        # self.enabled_layers = layer_state  # restore layer state
        self._update_layer_values_from_dros(auto_reload=False)
        self._plot()

    def on_selection_changed(self, selection):
        count = selection.count_selected_rows()

        if count == 0:
            self._toggle_g4x_buttons(False)
        else:
            self._toggle_g4x_buttons(True)
            g4xval = self._treeview.get_attr_for_selection('cut_cor')
            if g4xval == None:
                self._set_g4x_buttons(0)
            else:
                self._set_g4x_buttons(g4xval)

    def _get_selected_layer_and_shape(self):
        selected_shape = None
        selected_layer = None
        for layer, shapes in self._treeview.layers:
            for shape in shapes:
                if shape['selected']:
                    selected_shape = shape
                    break
            if selected_shape:
                selected_layer = layer
                break
        return selected_layer, selected_shape

    def _update_tool_info_from_tool_table(self):
        for layer, _ in self._treeview.layers:
            tool_id = layer['tool_nr']
            tool_diameter = self.get_tool_diameter_cb(tool_id)
            layer['tool_diameter'] = tool_diameter

    def _toggle_g4x_buttons(self, enabled):
        self._g40_button.set_sensitive(enabled)
        self._g41_button.set_sensitive(enabled)
        self._g42_button.set_sensitive(enabled)

    def _set_g4x_buttons(self, cut_cor):
        if cut_cor not in [40, 41, 42]:
            self._g40_button.set_inconsistent(True)
            self._g41_button.set_inconsistent(True)
            self._g42_button.set_inconsistent(True)
        else:
            self._g40_button.set_inconsistent(False)
            self._g41_button.set_inconsistent(False)
            self._g42_button.set_inconsistent(False)
            self._g40_button.set_active(cut_cor == 40)
            self._g41_button.set_active(cut_cor == 41)
            self._g42_button.set_active(cut_cor == 42)

    def _get_g4x_buttons(self):
        if self._g40_button.get_active():
            return 40
        elif self._g41_button.get_active():
            return 41
        elif self._g42_button.get_active():
            return 42

    def _update_dros_from_layer_values(self):
        layers = self._treeview.layers
        if not any(layers):
            self._set_all_dro_sensitivity(False)
            return
        else:
            self._set_all_dro_sensitivity(True)

        layer, shapes = layers[0]
        if any(shapes):
            shape = shapes[0]
        else:
            shape = None

        if shape:
            self._set_g4x_buttons(shape['cut_cor'])
            self._dros['z_start_mill_depth'].set_text(
                str(shape['axis3_start_mill_depth'])
            )
            self._dros['z_slice_depth'].set_text(str(-shape['axis3_slice_depth']))
            self._dros['z_mill_depth'].set_text(str(shape['axis3_mill_depth']))
            if 'conv_feed_dro' in self._common_dros:
                self._common_dros['conv_feed_dro'].set_text(str(shape['f_g1_plane']))
            if 'conv_z_feed_dro' in self._common_dros:
                self._common_dros['conv_z_feed_dro'].set_text(str(shape['f_g1_depth']))

        if layer:
            self._common_dros['conv_tool_number_dro'].set_text(str(layer['tool_nr']))
            if 'conv_rpm_dro' in self._common_dros:
                self._common_dros['conv_rpm_dro'].set_text(str(layer['speed']))
            if 'conv_z_clear_dro' in self._common_dros:
                self._common_dros['conv_z_clear_dro'].set_text(
                    str(layer['axis3_retract'])
                )

    def _update_move_up_down_button_sensitivity(self):
        selected_layer, selected_shape = self._get_selected_layer_and_shape()

        if not selected_layer and not selected_shape:
            self._move_down_button.set_sensitive(False)
            self._move_up_button.set_sensitive(False)
            self._move_bottom_button.set_sensitive(False)
        else:
            self._move_down_button.set_sensitive(True)
            self._move_up_button.set_sensitive(True)
            self._move_bottom_button.set_sensitive(True)

    def _update_layer_values_from_dros(self, auto_reload=True):
        def update_if_necessary(target, key, value):
            if target[key] != value:
                target[key] = value
                return True
            else:
                return False

        # g4x = self._get_g4x_buttons()
        z_start_mill_depth = float(self._dros['z_start_mill_depth'].get_text())
        z_slice_depth = -float(self._dros['z_slice_depth'].get_text())
        z_mill_depth = float(self._dros['z_mill_depth'].get_text())
        xy_feed = (
            float(self._common_dros['conv_feed_dro'].get_text())
            if 'conv_feed_dro' in self._common_dros
            else 0
        )
        z_feed = (
            float(self._common_dros['conv_z_feed_dro'].get_text())
            if 'conv_z_feed_dro' in self._common_dros
            else 0
        )
        tool_id = int(self._common_dros['conv_tool_number_dro'].get_text())
        tool_diameter = self.get_tool_diameter_cb(tool_id)
        speed = (
            float(self._common_dros['conv_rpm_dro'].get_text())
            if 'conv_rpm_dro' in self._common_dros
            else 0
        )
        z_retract = (
            float(self._common_dros['conv_z_clear_dro'].get_text())
            if 'conv_z_clear_dro' in self._common_dros
            else 0
        )
        z_safe_margin = z_retract - z_start_mill_depth

        modified = False
        for layer, shapes in self._treeview.layers:
            for shape in shapes:

                def update_shape(key, value):
                    return update_if_necessary(shape, key, value)

                # modified |= update_shape('cut_cor', g4x)
                modified |= update_shape('axis3_start_mill_depth', z_start_mill_depth)
                modified |= update_shape('axis3_slice_depth', z_slice_depth)
                modified |= update_shape('axis3_mill_depth', z_mill_depth)
                modified |= update_shape('f_g1_plane', xy_feed)
                modified |= update_shape('f_g1_depth', z_feed)

            def update_layer(key, value):
                return update_if_necessary(layer, key, value)

            modified |= update_layer('tool_nr', tool_id)
            modified |= update_layer('tool_diameter', tool_diameter)
            modified |= update_layer('speed', speed)
            modified |= update_layer('axis3_retract', z_retract)
            modified |= update_layer('axis3_safe_margin', z_safe_margin)

        if modified:
            self._update_layers()
            if auto_reload:
                self._plot()

    def _update_entity_value_dros(self):
        self._entity_dros['x_offset'].set_text(str(self._dx))
        self._entity_dros['y_offset'].set_text(str(self._dy))
        self._entity_dros['scale'].set_text(str(self._scale))
        self._entity_dros['rotate'].set_text(str(-degrees(self._rotation)))
        for dro in self._entity_dros.values():
            self.validate_and_format_dro_cb(dro, True)

    def _update_entity_values_from_dros(self):
        self._dx = float(self._entity_dros['x_offset'].get_text())
        self._dy = float(self._entity_dros['y_offset'].get_text())
        self._scale = float(self._entity_dros['scale'].get_text())
        self._rotation = -radians(float(self._entity_dros['rotate'].get_text()))

    @raises_dbus_error('Error updating DXF layers: %s')
    def _update_layers(self):
        dbusclient = DBusClient()
        dbusclient.set_layers(self._treeview.layers)
        if any(self._treeview.layers):
            layer, _ = self._treeview.layers[0]
            #  make sure to override axis retract config value
            config = {'Depth_Coordinates/axis3_retract': layer['axis3_retract']}
            dbusclient.set_configuration_values(config)
        self._canvas3d.layers = self._treeview.layers

    def _load_layers(self, dbusclient):
        self._treeview.layers = dbusclient.get_layers()
        self._canvas3d.layers = self._treeview.layers

    def _report_error(self, message):
        self.emit('errored', message)

    def _validate_all_dros(self, current_dro=None, next_dro=None):
        """
        Validates all dros in the panel.
        @current_dro Pass in currently active DRO.
        """

        def dro_is_more_suitable(dro_, invalid_dro_, next_dro_, current_dro_):
            return (dro_ is current_dro_) or (
                invalid_dro_ is not current_dro_ and dro_ is next_dro_
            )

        invalid_dro = None
        common_dros = self._common_dros.values()
        all_dros = self._entity_dros.values() + self._dros.values() + common_dros
        for dro in all_dros:
            format_dro = (
                dro not in common_dros and dro is current_dro
            )  # Note: don't format common dros
            valid = self.validate_and_format_dro_cb(dro, format_dro)
            if (
                not valid and not dro is current_dro and not dro in common_dros
            ):  # only format DRO if it is not current dro and not a common DRO
                self.validate_and_format_dro_cb(dro, True)
            if not valid and (
                not invalid_dro
                or dro_is_more_suitable(dro, invalid_dro, next_dro, current_dro)
            ):
                invalid_dro = dro

        if invalid_dro:
            invalid_dro.grab_focus()
            return False
        else:
            return True

    def _on_dro_changed(self, widget, _data=None):
        if not self.enable_preview_update or not self._file_loaded:
            return
        next_widget = self._dro_activation_order.get(widget)
        if not self._validate_all_dros(current_dro=widget, next_dro=next_widget):
            self._dros_invalidated = True
            return
        try:
            if widget in self._entity_dros.values() or self._dros_invalidated:
                self._update_entity_values_from_dros()
                self._set_entity_values()
            if widget in self._dros.values() or self._dros_invalidated:
                self._update_layer_values_from_dros()
            self._dros_invalidated = False
        except ValueError:
            pass
        if next_widget:
            next_widget.grab_focus()

    def _on_layers_changed(self, widget, full_update_required):
        self._update_layers()
        self._treeview._sync_selection()
        if not self.enable_preview_update:
            pass
        elif not full_update_required:
            self._plot_export_route()
            self._canvas3d.update()
        else:
            self._canvas3d.redraw()
        if self.enable_remote_update:
            self._update_dros_from_layer_values()
        self._update_move_up_down_button_sensitivity()

    def _on_move_up_button_released(self, *_):
        self._treeview.move_selected_shape_up()

    def _on_move_down_button_released(self, *_):
        self._treeview.move_selected_shape_down()

    def _on_move_bottom_button_released(self, widget, data=None):
        self._treeview.move_selected_shape_bottom()

    def _on_fold_button_released(self, *_):
        self._treeview.collapse_all()

    def _on_unfold_button_released(self, *_):
        self._treeview.expand_all()

    def _on_g40_button_released(self, widget, data=None):
        self._set_g4x_buttons(40)
        self._treeview.set_attr_for_selection('cut_cor', 40)
        self._update_layers()
        self._plot()

    def _on_g41_button_released(self, widget, data=None):
        self._set_g4x_buttons(41)
        self._treeview.set_attr_for_selection('cut_cor', 41)
        self._update_layers()
        self._plot()

    def _on_g42_button_released(self, widget, data=None):
        self._set_g4x_buttons(42)
        self._treeview.set_attr_for_selection('cut_cor', 42)
        self._update_layers()
        self._plot()

    def _on_filename_dro_focused(self, widget, data=None):
        self.emit('open-file-requested')

    def _on_expose(self, widget=None, event=None):
        """ this functions is called when the panel becomes visible """
        pass

    def _on_preview_clicked(self, *_):
        if self._file_loaded and not any(self._canvas3d.layers):
            if self._validate_all_dros():
                self._reload()
            else:
                self._dros_invalidated = True


class MillD2gPanel(BaseD2gPanel):
    pass
