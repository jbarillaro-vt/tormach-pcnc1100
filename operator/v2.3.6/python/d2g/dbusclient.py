from dbus import SessionBus
from dbus import exceptions


class DBusException(exceptions.DBusException):
    """ Wraps dbus internal exception so we can replace it in the future without too much pain"""

    def __init__(self, value):
        exceptions.DBusException.__init__(self, value)


def dbusmethod(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except exceptions.DBusException as e:
            raise DBusException(e)

    return wrapper


class DBusClient(object):
    @dbusmethod
    def __init__(self):
        bus = SessionBus()
        self._service = bus.get_object(
            'com.tormach.Dxf2GCode', '/com/tormach/Dxf2GCode'
        )
        self._interface = 'com.tormach.Dxf2GCode'

    @dbusmethod
    def load(self, path):
        # loads from large files can take a long time on the little Brix controller.
        return self._service.load(path, dbus_interface=self._interface, timeout=60 * 5)

    @dbusmethod
    def make_shapes(self):
        """Generates shapes for the loaded DXF file.
        Note that this resets all attributes for the loaded layers (cut_cor, etc)
        because the layer and shape objects are recreated from scratch"""
        # loads from large files can take a long time on the little Brix controller.
        return self._service.make_shapes(dbus_interface=self._interface, timeout=60 * 5)

    @dbusmethod
    def get_filename(self):
        return self._service.get_filename(dbus_interface=self._interface)

    @dbusmethod
    def get_is_metric(self):
        return self._service.get_is_metric(dbus_interface=self._interface)

    @dbusmethod
    def export_shapes(self, path, metric, postpro_override_values):
        self._service.export_shapes(
            path,
            metric,
            postpro_override_values,
            dbus_interface=self._interface,
            timeout=60 * 5,
        )

    @dbusmethod
    def optimize_TSP(self):
        self._service.optimize_TSP(dbus_interface=self._interface)

    @dbusmethod
    def plot(self):
        return self._service.plot(dbus_interface=self._interface, timeout=60 * 5)

    @dbusmethod
    def plot_export_route(self):
        return self._service.plot_export_route(
            dbus_interface=self._interface, timeout=60 * 5
        )

    @dbusmethod
    def get_layers(self):
        return self._service.get_layers(dbus_interface=self._interface, timeout=60 * 5)

    @dbusmethod
    def set_layers(self, data):
        self._service.set_layers(data, dbus_interface=self._interface, timeout=60 * 5)

    @dbusmethod
    def set_configuration_values(self, values):
        return self._service.set_configuration_values(
            values, dbus_interface=self._interface
        )

    @dbusmethod
    def set_entity_root_values(self, values):
        return self._service.set_entity_root_values(
            values, dbus_interface=self._interface
        )
