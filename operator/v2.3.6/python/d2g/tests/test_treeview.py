import pytest

from d2g.treeview import ShapeSelectionTreeView


@pytest.fixture
def FakeTreeView():
    treeview = ShapeSelectionTreeView
    treeview._save_row_expansion_state = lambda x: None
    treeview._expanded_rows = []
    treeview.treeview = None
    return treeview


@pytest.fixture
def layers():
    shape = {'disabled': False, 'nr': 2, 'selected': False}
    layers = []
    layers.append(
        ({'name': 'foo'}, [shape.copy(), shape.copy(), shape.copy(), shape.copy()])
    )
    return layers


def test_move_selected_layer_up_moves_layer_when_possible(FakeTreeView, layers):
    treeview = FakeTreeView()
    treeview.layers = layers
    treeview._get_selected_paths = lambda x: [(0, 1)]

    shape = layers[0][1][1]
    treeview.move_selected_shape_up()

    assert shape is layers[0][1][0]
