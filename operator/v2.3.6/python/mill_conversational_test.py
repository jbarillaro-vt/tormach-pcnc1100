# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import pytest
import ast

@pytest.fixture
def conv():
    from mill_conversational import conversational

    class conv(conversational):
        def __init__(self):
            pass

    return conv()


@pytest.fixture
def raw_layers():
    return [['A-DETL-GENF', [[0, True], [5, True], [10, True], [15, True], [18, True], [47, True], [48, True], [64, True], [65, True], [67, True], [68, True], [78, True], [79, True]]], ['A-DETL-MEDM', [[31, True], [32, True], [33, True], [34, True], [35, True], [36, True], [46, True], [57, True], [58, True], [59, True], [63, True], [66, True], [77, True]]], ['A-DETL', [[1, True], [2, True], [3, True], [4, True], [6, True], [7, True], [8, True], [9, True], [11, True], [12, True], [13, True], [14, True], [16, True], [17, True], [19, True], [20, True], [21, True], [22, True], [23, True], [24, True], [25, True], [26, True], [27, True], [28, True], [29, True], [30, True], [37, True], [38, True], [39, True], [40, True], [41, True], [42, True], [43, True], [44, True], [45, True], [49, True], [50, True], [51, True], [52, True], [53, True], [54, True], [55, True], [56, True], [60, True], [61, True], [62, True], [69, True], [70, True], [71, True], [72, True], [73, True], [74, True], [75, True], [76, True], [80, True], [81, True], [82, True], [83, True], [84, True], [85, True], [86, True], [87, True], [88, True], [89, True], [90, True], [91, True], [92, True], [93, True], [94, True], [95, True], [96, True], [97, True], [98, True], [99, True], [100, True], [101, True]]]]


@pytest.fixture
def encoded_layers():
    return '''
(DXF File Path = /home/alexander/gcode/dxf_import/plates.dxf)
(Cutter Compensation = On)
(Layers = [['A-DETL-GENF', [[0, True], [5, True], [10, True], [15, True], [18, True], [47, True], [48, True], [64, True], [65, True], [67, True], [68, True], [78, True], [79, True]]], ['A-DETL-MEDM', [[31, True], [32, True], [33, True], [34, True], )
(Layers = [35, True], [36, True], [46, True], [57, True], [58, True], [59, True], [63, True], [66, True], [77, True]]], ['A-DETL', [[1, True], [2, True], [3, True], [4, True], [6, True], [7, True], [8, True], [9, True], [11, True], [12, True], )
(Layers = [13, True], [14, True], [16, True], [17, True], [19, True], [20, True], [21, True], [22, True], [23, True], [24, True], [25, True], [26, True], [27, True], [28, True], [29, True], [30, True], [37, True], [38, True], [39, True], [40, True], )
(Layers = [41, True], [42, True], [43, True], [44, True], [45, True], [49, True], [50, True], [51, True], [52, True], [53, True], [54, True], [55, True], [56, True], [60, True], [61, True], [62, True], [69, True], [70, True], [71, True], [72, True], )
(Layers = [73, True], [74, True], [75, True], [76, True], [80, True], [81, True], [82, True], [83, True], [84, True], [85, True], [86, True], [87, True], [88, True], [89, True], [90, True], [91, True], [92, True], [93, True], [94, True], [95, True], )
(Layers = [96, True], [97, True], [98, True], [99, True], [100, True], [101, True]]]])

(Scale = 1.000)
'''


def test_converting_dxf_layers_to_code_works(conv, raw_layers):
    code = conv.ja_dxf_convert_layers_to_code(raw_layers)

    assert(len(code) == 6)
    assert(code[0] == "(Layers = [['A-DETL-GENF', [[0, True], [5, True], [10, True], [15, True], [18, True], [47, True], [48, True], [64, True], [65, True], [67, True], [68, True], [78, True], [79, True]]], ['A-DETL-MEDM', [[31, True], [32, True], [33, True], [34, True], )")
    assert(code[1] == "(Layers = [35, True], [36, True], [46, True], [57, True], [58, True], [59, True], [63, True], [66, True], [77, True]]], ['A-DETL', [[1, True], [2, True], [3, True], [4, True], [6, True], [7, True], [8, True], [9, True], [11, True], [12, True], )")
    assert(code[5] == "(Layers = [96, True], [97, True], [98, True], [99, True], [100, True], [101, True]]]])")


def test_converting_code_to_dxf_layers_works(conv, encoded_layers):
    layer_string = conv.ja_dxf_convert_code_to_layers(encoded_layers)

    layers = ast.literal_eval(layer_string)
    assert(len(layers) == 3)
    assert(layers[0][0] == 'A-DETL-GENF')
    assert(layers[1][0] == 'A-DETL-MEDM')
    assert(layers[2][0] == 'A-DETL')
    assert(layers[1][1][2] == [33, True])
    assert(layers[2][1][4] == [6, True])
