# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#
# Module for G-code generator support classes
#

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import sys
import gtk
import math
import re


####################################################################################################
# class MachTool - handles info about tooling
#
####################################################################################################
class MachTool(object):

    _tool_coating_re = None

    def __init__(self, info):
        assert('tv' in info)
        self.ui = info['ui']
        self.tv = info['tv']
        MachTool._tool_coating_re = self.ui.fs.__class__.tool_parse_data['tooling_keywords']['tool_coating']

    def update(self, row, data):
        pass # nothing to do here yet

####################################################################################################
# class MillTool - handles info about lathe tooling
#
####################################################################################################

class MillTool(MachTool):

    @staticmethod
    def __strip_zeros(num, fmt):
        assert (isinstance(num,float))
        num = fmt%num
        num = num.strip('0')
        while num.endswith('0'): num = num[:-1]
        return num

    @staticmethod
    def __make_radius_str(radius):
        if math.fabs(radius)<1e-8: return 'R0 '
        return 'R'+('%0.4f'%radius).strip('0')+' '

    @staticmethod
    def __add_type(typ):
        typ = typ.lower()
        if 'end mill' in typ: return 'End Mill'
        if 'tapered' in typ: return 'End Mill'
        if 'face' in typ: return 'Face Mill'
        if 'center drill' in typ: return 'Ctr Drill'
        if 'spot' in typ : return 'Spot'
        if 'chamfer' in typ: return 'Chamf'
        if 'tap' in typ: return 'Tap'
        if 'reamer' in typ: return 'Reamer'
        if 'counter' in typ: return 'Counter Sink'
        return ''

    @staticmethod
    def __add_coating(description):
        # see if there is any usefull coating info
        # in the description.
        words = description.split()
        for word in words:
            if any(MachTool._tool_coating_re.findall(word)): return word+' '
        return ''

    def __init__(self, info):
        super(MillTool, self).__init__(info)

    def validate_cam_info(self, tool_json_info):
        # is this a milling tool?
        if 'turning' in tool_json_info['type']: return False
        return True

    def json_to_description(self, tool_json_info):
        rt = ''
        loc = tool_json_info['geometry']['LCF']
        flutes = tool_json_info['geometry']['NOF']
        radius = tool_json_info['geometry']['RE']
        diameter = tool_json_info['geometry']['DC']
        cutter_material = tool_json_info['BMC']
        description = tool_json_info['description']
        typ = tool_json_info['type']
        units = tool_json_info['unit']
        part_number = tool_json_info['product-id']
        fmt = '%2.4f' if 'in' in units else '%3.2f'
        diam = MillTool.__strip_zeros(diameter,fmt)
        if not 'in' in units: diam += 'mm'
        if part_number.startswith('3') and len(part_number) is 5: rt += '['+part_number+'] '    #part number if tormach
        rt += diam+' '
        rt += MillTool.__add_type(typ)+' '
        rt += MillTool.__make_radius_str(radius)
        rt += ('%d'%flutes)+'FL '
        rt += ('loc:%.4f'%loc).strip('0')+' '
        rt += MillTool.__add_coating(description)
        rt += 'HSS' if cutter_material=='hss' else 'carbide'
        return rt

    def update(self, row, data):
        super(MillTool,self).update(row, data)
        self.ui.update_tool_store(row, data)

    def radius_diameter_value(self, tool_json_info):
        return float(tool_json_info['geometry']['DC'])

####################################################################################################
# class LatheTool - handles info about lathe tooling
#
####################################################################################################

class LatheTool(MachTool):
    def __init__(self, info):
        super(LatheTool, self).__init__(info)

    def validate_cam_info(self, tool_json_info):
        return True

    def json_to_description(self, tool_json_info):
        return tool_json_info['post-process']['comment']

    def update(self, row, data):
        super(LatheTool,self).update(row, data)
        self.ui.update_tool_store(row, data)

    def radius_diameter_value(self, tool_json_info):
        return float(tool_json_info['geometry']['RE'])
