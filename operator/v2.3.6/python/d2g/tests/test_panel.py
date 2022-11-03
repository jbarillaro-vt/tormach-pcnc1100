import pytest

from d2g.panel import MillD2gPanel


@pytest.fixture
def panel_stub():
    class PanelStub(MillD2gPanel):
        def __init__(self):
            self._is_metric = True
            self.gui_is_metric_cb = lambda: False
            self.validate_and_format_dro_cb = lambda dro, _format: True
            self._dros = {}
            self._entity_dros = {}
            self._common_dros = {}

    return PanelStub()


class DroDummy(object):
    def __init__(self):
        self.grabbed = False

    def grab_focus(self):
        self.grabbed = True


@pytest.mark.parametrize(
    "gui_is_metric, dxf_is_metric, expected",
    [
        (False, False, 1.0),
        (True, True, 1.0),
        (True, False, 25.4),
        (False, True, 1 / 25.4),
    ],
)
def test_get_unit_scale_factor(gui_is_metric, dxf_is_metric, expected, panel_stub):
    panel_stub._is_metric = dxf_is_metric
    panel_stub.gui_is_metric_cb = lambda: gui_is_metric

    unit_scale_factor = MillD2gPanel._get_unit_scale_factor(panel_stub)

    assert unit_scale_factor == expected


def test_invalid_dro_results_in_current_dro_beeing_grabbed(panel_stub):
    dro1 = DroDummy()
    dro2 = DroDummy()
    dro3 = DroDummy()
    panel_stub._dros = {'dro1': dro1, 'dro2': dro2, 'dro3': dro3}
    panel_stub.validate_and_format_dro_cb = lambda dro, _format: dro is dro1

    MillD2gPanel._validate_all_dros(panel_stub, current_dro=dro3, next_dro=dro2)

    assert dro1.grabbed is False
    assert dro2.grabbed is False
    assert dro3.grabbed is True


def test_invalid_dro_results_in_next_dro_beeing_grabbed_when_current_dro_is_valid(
    panel_stub
):
    dro1 = DroDummy()
    dro2 = DroDummy()
    dro3 = DroDummy()
    panel_stub._dros = {'dro1': dro1, 'dro2': dro2, 'dro3': dro3}
    panel_stub.validate_and_format_dro_cb = lambda dro, _format: dro is dro1

    MillD2gPanel._validate_all_dros(panel_stub, current_dro=dro1, next_dro=dro3)

    assert dro1.grabbed is False
    assert dro2.grabbed is False
    assert dro3.grabbed is True
