#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import os, re

PROGRAM_DIR = os.getcwd()
GLADE_DIR = os.path.join(PROGRAM_DIR, 'images')

def get_filenames_in_dir(directory):
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory,f)) ]

def sort_files_by_extention(extension, unsorted_list):
    sorted_list = []
    for f in unsorted_list:
        name, ext = os.path.splitext(f)
        if extension in ext:
            sorted_list.append(f)
    return sorted_list

def find_unused_files(file_list):
    unused_files = []
    for name in file_list:
        is_used = False
        for py_file in python_files:
            file_object = open(py_file)
            for line in file_object:
                if name in line:
                    is_used = True
            file_object.close()
        for glade_file in glade_files:
            file_object = open(os.path.join(GLADE_DIR, glade_file))
            for line in file_object:
                if name in line:
                    is_used = True
            file_object.close()


        if is_used == False:
            print "this file was not used! ", name
            unused_files.append(name)
    return unused_files

def move_unused_files(file_list, ext):
    # make a dir for the unused images
    dest = os.path.join(PROGRAM_DIR, 'unused_images', ext)
    os.makedirs(dest)
    for f in file_list:
        src = os.path.join(GLADE_DIR, f)
        dest = os.path.join(PROGRAM_DIR, 'unused_images', ext, f)
        os.rename(src, dest)



image_files = get_filenames_in_dir(GLADE_DIR)
python_files = get_filenames_in_dir(PROGRAM_DIR)

pngs = sort_files_by_extention('png', image_files)
jpgs = sort_files_by_extention('jpg', image_files)
svgs = sort_files_by_extention('svg', image_files)
glade_files = sort_files_by_extention('glade', image_files)
python_files = sort_files_by_extention('py', python_files)


pngs = find_unused_files(pngs)
jpgs = find_unused_files(jpgs)
svgs = find_unused_files(svgs)



print "\n\njpgs: ", jpgs
print "\n\npngs: ", pngs
print "\n\nsvgs: ", svgs


move_unused_files(jpgs, 'jpgs')
move_unused_files(pngs, 'pngs')
move_unused_files(svgs, 'svgs')