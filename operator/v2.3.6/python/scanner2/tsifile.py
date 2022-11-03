# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

'''
@author: ibm
    DWORD    m_version;    //file version

    double    m_frameWidth;
    double    m_frameHeight;
    double    m_scale;

    DWORD    m_souWidth;    //frame width on pixel
    DWORD    m_souHeight;   //frame height on pixel

    DWORD    m_col;
    DWORD    m_row;

    double    m_FOVprecent;

    DWORD    m_cameraWidth;
    DWORD    m_cameraHeight;

    double    m_desireRes;
    double    m_resPix;
    double    m_angle;

    bool    m_bUnitInInch;        //if ture, the unit is on inch

    Geo::Matrix2d    m_matrix;
'''
import struct
import zlib
import cv2
import logging
import os
from PIL import Image
logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-10s) %(message)s')

_VERSION_OFFSET=20000

class TsiHeader:
    def __init__(self, camera, scene, use_inch=1):
        window_size = camera.get_frame_size()
        self.setup(scene.rows,
                   scene.columns,
                   scene.fov_ratio,
                   window_size[0],
                   window_size[1],
                   scene.scale,
                   scene.angle,
                   0,0,use_inch)

    def setup(self, rows=1, columns=1, fov_ratio=1.0, camera_width_px=640, camera_height_px=480, scale=0.001,
            angle=0, desireRes=0, resPix=0, use_inch=1, sub_version=2, matrix=None):
        """ Initialize a TSI file from a minimal set of inputs."""

        self.camera_width = camera_width_px
        self.camera_height = camera_height_px

        #Note that FOV ratio is assumed to be fraction of image AREA used
        self.cropped_width_px = int(round(fov_ratio * camera_width_px))
        self.cropped_height_px = int(round(fov_ratio * camera_height_px))

        self.rows = rows
        self.columns = columns

        self.fov_percent = fov_ratio * 100.0
        self.desired_resolution  = desireRes
        self.resolution_pixels = resPix
        self.angle = angle
        self.scale = scale

        self.frame_width = self.scale * self.cropped_width_px
        self.frame_height = self.scale * self.cropped_height_px

        self.use_inch = use_inch

        self.version = _VERSION_OFFSET + sub_version
        if matrix:
            self.matrix = matrix
        else:
            self.matrix = ((1, 0, 0),( 0, 1, 0))  # default value

    def write(self, file_handle):
        logging.warn('Writing TSI File header:\n'
                     '\trows: {0}\n'
                     '\tcolumns: {1}\n'
                     '\tframe_size: {2}\n'
                     '\tcropped_size: {3}\n'.format(self.rows,
                                                    self.columns,
                                                    [self.frame_width,self.frame_height],
                                                    [self.cropped_width_px,self.cropped_height_px]))
        buf = struct.pack(
            '<IIIIIddd?dIIddd',
            int(self.version),
            int(self.columns),
            int(self.rows),
            int(self.cropped_width_px),
            int(self.cropped_height_px),
            self.frame_width,
            self.frame_height,
            self.scale,
            self.use_inch,
            self.fov_percent,
            int(self.camera_width),
            int(self.camera_height),
            self.desired_resolution,
            self.resolution_pixels,
            self.angle )

        for i in range(0, 2):
            for j in range(0, 3):
                v = self.matrix[i][j]
                buf += struct.pack('<d', v)
        file_handle.write(buf)
        file_handle.flush()


class TsiFile:
    def __init__(self, tsi_filename, tsi_header, use_inch = True):
        """ Empty constructor to initialize with defaults for a simple VGA camera"""
        self.file_handle = None
        self.tsi_folder = os.path.expanduser('~/gcode/camera')
        self.tsi_filename = os.path.join(self.tsi_folder,tsi_filename)

        self.header = tsi_header
        self.setup()

    def setup(self):
        #Compute other helpful parameters
        self.image_row_start = round((self.header.camera_height
                - self.header.cropped_height_px ) / 2.0)

        self.image_column_start = round((self.header.camera_width
                - self.header.cropped_width_px ) / 2.0)

        self.images_required = self.header.rows * self.header.columns
        self.images_written = 0

    def add_bitmap_from_buf(self,str_buf):
        # Extract file size

        file_size, image_start, image_size = self.extract_size_from_buf(str_buf)

        # build image string from raw data
        image_str = str_buf[image_start:]

        print "*** cropping start ***"

        # number of bytes in a row = columns * 3 bytes per pixel for 24 bit
        # colordepth
        row_length_bytes = 3 * int(self.header.cropped_width_px)

        row_list=[]
        image_row_start = int( self.image_row_start )
        image_row_end = int( self.image_row_start + self.header.cropped_height_px)
        for y in range(image_row_start, image_row_end):
            """
            The image structure in raw format is as follows:
            24 bit color depth, 3 bytes (BGR), no alpha channel
            Pixels in 3 bytes, incrementing by column, then row.

            A 2 x 3 pixel image of the italian flag would look like this:

                00 FF 00  FF FF FF  00 00 FF   00 FF 00  FF FF FF  00 00 FF

            This corresponds to the pixels:
                0 1 2
             0  G W R
             1  G W R

            """
            start_pixel_index = y * self.header.camera_width + self.image_column_start
            start_byte = int(3 * start_pixel_index)

            #Get the appropriate substring from starting byte, rounding up to the nearest int32
            row_list.append(image_str[start_byte:start_byte+row_length_bytes])

        #Terminate read rows with empty string (used for join operation)
        # Note: Joining a list is more efficient than using the '+' operator on
        # strings
        row_list.append('')

        # Merge all read strings into a single chunk
        image_cropped_row_str = ''.join(row_list)
        return self.write_image_block(image_cropped_row_str)


    def add_bitmap_from_file(self,filename):
        """ Take an existing bitmap image, load it, and add it as a TSI image block"""

        with open(filename, 'rb') as image_file:
            str_buf = image_file.read()

        return self.add_bitmap_from_buf(str_buf)

    def row_padding(self, width, colordepth):
        '''
        David Hilton, http://pseentertainmentcorp.com/smf/index.php?topic=2034.0
        returns any necessary row padding
        '''
        byte_length = width*colordepth/8
        # how many bytes are needed to make byte_length evenly divisible by 4?
        padding = (4-byte_length)%4
        padbytes = [struct.pack('<B', 0) for i in range(int(padding))]
        return ''.join(padbytes)

    def extract_size_from_buf(self,str_buf):
        file_size_str = str_buf[2:2+4]
        file_size = struct.unpack('I', file_size_str)
        logging.info("--> file_size =%d" % file_size[0])

        # find image start
        image_start_str = str_buf[10:10+4]
        image_start = struct.unpack('I', image_start_str)
        logging.info("--> image_start = %d" % image_start[0])

        image_size = file_size[0] - image_start[0]
        logging.info("--> image_size = %d" % image_size)

        return file_size[0], image_start[0], image_size

    def add_cropped_bitmap_from_buf(self,str_buf):
        __,image_start,__ = self.extract_size_from_buf(str_buf)

        # build image string from raw data
        image_cropped_str = str_buf[image_start:]

        return self.write_image_block(image_cropped_str)

    def write_image_block(self, str_buf):
        if self.file_handle != None and str_buf != None:
            string_length = len(str_buf)
            logging.info("--> string_length = %d" % string_length)

            # Compress with ZLIB for TSI storage
            compressed_string = zlib.compress(str_buf)
            if compressed_string != None and compressed_string != "":
                compressed_length = len(compressed_string)
                logging.info("--> compressed_length = %d" % compressed_length)

                # write original and new buffer length
                self.file_handle.write(struct.pack( '<II', string_length ,
                                                    compressed_length))
                # write new buffer
                self.file_handle.write(compressed_string)

                #Update image count
                self.images_written +=1
                logging.debug("images_written = %d" % self.images_written)
                return True
        return False

    def add_image(self, image):
        str_buf = cv2.imencode('.bmp',image)[1].tostring()
        return self.add_bitmap_from_buf(str_buf)

    def add_cropped_image(self, image):
        # TODO - BMPs or PNGs might be faster/better format for intermediate files
        #jpeg = cv2.imencode('.jpg', image)
        new_filename = '/tmp/scanner-tmp-row%03d-col%03d.jpg' % (self.jpeg_cur_row, self.jpeg_cur_col)
        logging.debug('about to write: %s' % new_filename)
        cv2.imwrite(new_filename, image)
        logging.debug('file was created and exists: %d' % os.path.exists(new_filename))
        self.jpeg_cur_col += 1
        if self.jpeg_cur_col >= self.header.columns:
            self.jpeg_cur_col = 0
            self.jpeg_cur_row += 1

        str_buf = cv2.imencode('.bmp',image)[1].tostring()
        return self.add_cropped_bitmap_from_buf(str_buf)

    def end(self):
        #try:
        # paste all the accumulated jpeg files into one large jpeg file
        # arranged in the same row/column format in which they were acquired
        logging.debug('cols: %d, rows: %d' %(self.header.columns, self.header.rows))
        jpeg_num_files = self.header.rows * self.header.columns
        jpeg_height = self.header.rows * self.header.cropped_height_px
        jpeg_width = self.header.columns * self.header.cropped_width_px
        logging.debug('new composite jpeg is %d wide and %d high made up of %d files' % (jpeg_width, jpeg_height, jpeg_num_files))
        big_image = Image.new('RGB', (jpeg_width, jpeg_height))
        for row in range(0, self.header.rows):
            for col in range(0, self.header.columns):
                #try:
                # read file into image
                new_filename = '/tmp/scanner-tmp-row%03d-col%03d.jpg' % (row, col)
                logging.debug('pasting image file %s at (%d, %d)' % (new_filename, row, col))
                #logging.debug('file exists: %d' % os.path.exists(new_filename))
                new_image = Image.open(new_filename)
                # first image goes in bottom left of jpeg
                # next image if more than 1 column is to right
                # last image goes in top right of jpeg
                # pixel at (0, 0) is lower left of jpeg
                # paste individual image into large mosaic image
                # calculate the upper left pixel location in which to paste
                upper_left_x = col * self.header.cropped_width_px
                #upper_left_y = row * self.header.cropped_height_px
                upper_left_y = jpeg_height - (row * self.header.cropped_height_px) - self.header.cropped_height_px
                logging.debug('inserting into big jpeg at upper left coordinate (%d, %d)' % (upper_left_x, upper_left_y))
                big_image.paste(new_image, (upper_left_x, upper_left_y))
        #except Exception as e:
        #    logging.debug('exception creating composite image jpeg file')
        #    msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
        #    logging.debug(msg.format(type(e).__name__, e.args))
        # done - now write a jpeg file to disk from big image
        big_jpeg_name, tsi_ext = os.path.splitext(self.tsi_filename)
        big_jpeg_name += '.jpeg'
        dpi_xy = int(1/self.header.scale)
        logging.debug('scale: %f, dpi: %d' %(self.header.scale, dpi_xy))
        big_image.save(big_jpeg_name, dpi = (dpi_xy, dpi_xy))
        #except Exception as e:
        #    logging.debug('exception creating composite image jpeg file')
        #    msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
        #    logging.debug(msg.format(type(e).__name__, e.args))

        if self.file_handle != None:
            logging.warn("Closing TSI file")
            self.file_handle.close()
            return True
        else:
            return False

    def __enter__(self):
        self.file_handle = open(self.tsi_filename, 'wb')
        self.jpeg_cur_row = 0
        self.jpeg_cur_col = 0
        return self

    def __exit__(self, type, value, traceback):
        self.end()


def test_from_file(outname,imagepath):
    """ Simple test function to turn a single VGA-size BMP into a TSI file.
    More tests forthcoming with additional test data.
    """
    with TsiFile(outname+'.tsi') as testfile:
        testfile.setup(1,1,.25,640,480,0.001,0,0,0,True,2)
        testfile.write_header()
        testfile.add_bitmap_from_file(imagepath)

def test_from_fileset(outname,imagestem,rows,cols):
    """ Simple test function to turn a single VGA-size BMP into a TSI file.
    More tests forthcoming with additional test data.
    """
    with TsiFile(outname+'.tsi') as testfile:
        testfile.setup(rows,cols,.25,640,480,0.001,0,0,0,True,2)
        testfile.write_header()
        for i in range(rows*cols):
            testfile.add_bitmap_from_file(imagestem+str(i)+'.bmp')

def test_single_from_camera(outname,vid_device = 0):
    vidcap = cv2.VideoCapture()
    vidcap.open(0)
    success, test_image = vidcap.read()
    #TODO auto match to camera size
    with TsiFile(outname+'.tsi') as testfile:
        testfile.setup(1,1,.25,640,480,0.001,0,0,0,True,2)
        testfile.write_header()
        testfile.add_image(test_image)
    vidcap.release()


if __name__ == '__main__':
    """ Test tsi file output """
    test_from_file('single','test_images/caliper0.bmp')
    test_from_fileset('setof4','test_images/caliper',2,2)
    test_single_from_camera('fromcam')


