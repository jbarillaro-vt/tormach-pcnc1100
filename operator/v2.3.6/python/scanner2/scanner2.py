# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import time
import math
import gtk
import Queue
import threading
import logging
import cv2
import numpy as np
import tsifile
import linuxcnc
import pickle
from collections import deque
import timer

# Filename generation
import itertools
import os
import re

logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-10s) %(message)s')

class ScanCamera():
    """ This class is a wrapper around OpenCV's VideoCapture to add some useful
    calculations for the scanner.
    """

    def __init__(self, device_num, dest_buffer):
        #FIXME ugly way to use outside deque
        self.frame_buffer = dest_buffer
        self.device_num = device_num
        self.vidsrc = cv2.VideoCapture(device_num)
        self.vidsrc.set(cv2.cv.CV_CAP_PROP_FPS,15)

    #TODO define constructor to set default cropped window
    def set_frame_size(self,width,height):
        """ Set the current frame size for the camera.
        keyword arguments:
            width -- new frame width
            height -- new frame height

        returns True / False depending on success of operation
        """
        #NOTE: currently seems to be broken, maybe a limitation of USB cameras?
        #TODO validate frame widths
        res_w=self.vidsrc.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH,width)
        res_h=self.vidsrc.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT,height)
        return res_w and res_h

    def get_frame_size(self):
        """ Get the current frame size.
        returns a tuple (width, height)
        """
        full_width = self.vidsrc.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH)
        full_height = self.vidsrc.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT)
        return (int(full_width), int(full_height))

    def get_center_point(self):
        """ Compute the center point of the camera full frame.
        Returns a tuple of ints: (x, y)
        """
        center_point = np.array(self.get_frame_size())/2.0
        return tuple(center_point.astype('int'))

    def update_frame_buffer(self):
        """ Grab an image from the camera and append it to the local frame
        buffer. Note that this update function will block if a frame is not
        available, so avoid calling more frequently than the camera's refresh
        rate.
        """
        result,image = self.vidsrc.read()
        if result and self.frame_buffer is not None:
            self.frame_buffer.append(image)
            return True
        return False

    def set_brightness(self, value):
        if value > 1.0 or value < 0:
            #TODO throw error
            return
        self.vidsrc.set(cv2.cv.CV_CAP_PROP_BRIGHTNESS,value)

    def set_contrast(self, value):
        if value > 1.0 or value < 0:
            #TODO throw error
            return
        self.vidsrc.set(cv2.cv.CV_CAP_PROP_CONTRAST,value)

    #TODO similar set_xxx property functins here


class SceneSettings:

    #FIXME defaults manually set to initial values of GUI sliders here
    def __init__(self, bounds=None, scale=1.0, angle_rad=0.0, fov_ratio=0.7, camera = None, feed=0.0):
        """ Define a scene from calibration settings and user settings:
            bounds: numpy array of X and Y scan area [-X +X -Y +Y]
            scale: scale in in/pixel
            angle_rad: angle in radians of image wrt machine axes
            fov_ratio: amount of full camera window to use, where 1.0 is full width, 0.0 is nothing
            camera: opencv camera handle
            feed: machine speed to traverse between frames
        """
        self.feed = feed
        self.scale = scale
        self.angle = angle_rad * 180.0 / np.pi
        self.bounds = bounds if bounds else np.array([0.0,0.0,0.0,0.0])
        self.set_fov_ratio(fov_ratio)
        self.first_pos = None
        self.second_pos = None
        self.first_px = None
        self.second_px = None

        self.rows = 0
        self.columns = 0
        self.points = []
        self.points_count = 0

        #TODO better validation
        if camera is not None and bounds:
            w,h = camera.get_window_from_fov(fov_ratio)
            self.set_points_from_scene(bounds,
                                        w,
                                        h,
                                        scale)

    def get_settings_from_pickle(self,pickle_name):
        with open(pickle_name, 'r') as f:
            from_file=pickle.load(f)
        self.scale = from_file.scale

    @staticmethod
    def validate_scale(scale):
        if scale <= 0:
            return False
        else:
            return True

    def is_calibrated(self):
        """ Check if scanner has been calibrated to get a scale factor and
        rotation angle.
        """
        #TODO deal with method to save / restore calibration
        if self.first_px is None or self.second_px is None:
            return False

        if self.first_pos is None or self.second_pos is None:
            return False

        return True

    def is_valid(self):

        if not self.is_calibrated():
            return False

        #Need defined scanpoints
        if len(self.points) < 1:
            return False

        #Passed all tests
        return True

    def set_fov_ratio(self,fov_ratio):
        if fov_ratio < 0.0 or fov_ratio > 1.0:
            #TODO see if raising exceptions plays well with threads
            raise ValueError("fov_ratio is out of range!")

        self.fov_ratio = fov_ratio

    def set_calibration_points(self,pt1,pt2):
        """ Store points on the image used for scale and angle calibration.
        keyword arguments:
            pt1 -- first calibration point as (x,y) tuple
            pt2 -- second calibration point as (x,y) tuple
        """
        logging.info('Image calibration points: {0}, {1}'.format(pt1,pt2))
        self.first_px = np.array(pt1)
        self.second_px = np.array(pt2)
        return self.update_scale()

    def set_first_point(self,pos):
        """ Store current machine position corresponding to first calibration point"""
        self.first_pos = np.array(pos)
        return self.update_scale()

    def set_second_point(self,pos):
        """ Store current machine position corresponding to second calibration point"""
        self.second_pos = np.array(pos)
        return self.update_scale()

    def update_scale(self):
        """ Use stored state to compute the scale and angle of the image wrt the machine axes.
        """
        if self.second_pos is None or self.first_pos is None:
            #TODO check for image points
            return False

        if self.second_px is None or self.first_px is None:
            return False
        delta_pos = self.second_pos - self.first_pos
        delta_px = self.second_px - self.first_px

        logging.debug("delta machine pos: {0}".format(delta_pos))
        logging.debug("delta px pos: {0}".format(delta_px))

        self.scale = np.linalg.norm(delta_pos) / np.linalg.norm(delta_px)
        self.machine_angle = math.atan2(delta_pos[1],delta_pos[0])
        # Negative X coordinate to flip image coordinates to line up with
        # machine axes, accounting for 180 deg rotation
        self.image_angle = math.atan2(delta_px[1],-delta_px[0])

        # Store angle in degrees since opencv uses degrees for most
        # calculations
        self.angle = (self.machine_angle - self.image_angle)*180.0/np.pi

        logging.debug("machine angle: {0} ".format(self.machine_angle))
        logging.debug("image angle: {0}".format(self.image_angle))
        logging.debug("rotation correction: {0} deg".format(self.angle))

        #FIXME, handle X and Y scale differences
        logging.debug("scale: {0} in / pixel".format(self.scale))
        return True

    def update_scanpoints_from_camera(self,camera):
        if camera is None:
            return
        cropped_size = camera.get_window_from_fov(self.fov_ratio)
        logging.debug('Bounds: {0}'.format(self.bounds))
        self.set_points_from_scene(self.bounds, cropped_size, self.scale)

    def get_window_from_fov(self,frame_shape):
        """ Using a fraction of the total FOV (from 0.0 to 1.0), compute the
        size and location of the cropped image in the full frame.
        """

        #Assumes a valid FOV ratio
        window_size = np.array(frame_shape)

        #Ensure cropped size is evenly divisible by 2
        cropped_size = np.round(window_size * self.fov_ratio / 2.0) * 2.0
        return cropped_size.astype('int')

    def get_window_bounding_box(self, window_size, cropped_size):
        """ Based on the given window and cropped image size, return two tuples
        of ints with the lower and upper corner of the image.
        """
        lower_corner = np.round((window_size - cropped_size) / 2.0)
        upper_corner = np.round(cropped_size + lower_corner)

        #Return image points for cropped window
        return lower_corner.astype('int'), upper_corner.astype('int')

    def update_scanpoints(self, frame_shape):
        cropped_size = self.get_window_from_fov(frame_shape)

        logging.debug('Bounds: {0}'.format(self.bounds))
        self.set_points_from_scene(self.bounds, cropped_size, self.scale)

    def clear_point_data(self):
        self.points = []
        self.estimated_time = 0.0
        self.rows = 0
        self.columns = 0

    def set_points_from_scene(self, bounds, cropped_size, scale):
        """ Create a list of scan points for the scan based on scene settings:
            bounds (bounding box of the scan area, defined as [-x +x -y +y])
            cropped w/h (size of region of interest)
            scale (in / pixel)

        """

        # Start with an empty set of scan points
        # Initialize way up here so that we don't keep old points around from
        # previous settings
        self.clear_point_data()

        scaled_size = np.array(cropped_size) * scale
        logging.debug('single image size: {0}'.format(scaled_size))

        center_offset = scaled_size / 2.0

        scan_size = np.array([abs(bounds[1] - bounds[0]),(bounds[3] - bounds[2])])

        logging.debug('scan area size: {0}'.format(scan_size))
        if np.min(scan_size) <= 0:
            logging.error('Invalid scan bounds')
            return False

        scan_steps = np.ceil(scan_size / scaled_size).astype('int')
        logging.debug('scan points (x,y): {0}'.format(scan_steps))
        if np.min(scan_steps) < 1:
            logging.error('No scan points found')
            return False

        #Store rows and columns for TSI file
        self.rows = scan_steps[1]
        self.columns = scan_steps[0]

        # Grow the list of points to scan, so that we scan along rows
        self.points_count = 0
        for m in range(scan_steps[1]):
            # Add a dummy point to take up backlash
            start_point = scaled_size * [0, m]
            self.points.append((start_point, False))
            for n in range(scan_steps[0]):
                # Add actual scan points
                self.points.append((scaled_size * [n, m] + center_offset,True))
                self.points_count+=1


        logging.info('Computed {0} scan points'.format(self.points_count))

        #TODO better metric
        self.estimated_time = 2.0 * len(self.points) + 3.0 * max(self.rows,0)



class ScannerThread(threading.Thread):
    """ Thread to move machine to scan points and capture images. This thread
    does minimal image processing to minimize scan time.
    """

    def __init__(self, stat, frame_buffer, scene, image_queue, status_queue, complete_event, abort_event, frame_ready_event, feedhold_event):
        """ Initialize a scanner to run a particular scan"""
        self.frame_buffer = frame_buffer
        self.scene = scene
        self.image_queue = image_queue
        self.complete_event = complete_event
        self.frame_ready_event = frame_ready_event
        self.feedhold_event = feedhold_event
        self.abort_event = abort_event
        self.command = linuxcnc.command()
        self.stat = stat
        self.status_queue = status_queue

        threading.Thread.__init__(self,name='ScannerThread')

    def soft_wait_complete(self,timeout=12, interval=0.16666667):
        """ Wait for MDI move to complete, allowing the thread to sleep for a few GUI updates in between.
        keyword arguments:
            timeout -- time to wait before declaring failure
            returns true if move is completed before the timeout, else false
        """
        start_time = time.time()
        #Force timeout to be >= 1 interval
        timeout = max(max(interval,timeout),0)
        while not self.is_mdi_move_done() and not self.complete_event.is_set() and not self.abort_event.is_set() and time.time() < start_time+timeout:
            logging.debug('waiting in scanner thread')
            time.sleep(interval)
        if self.stat.state == linuxcnc.RCS_ERROR:
            self.abort_event.set()
            raise RuntimeError('MDI command failed')

        if time.time() - start_time > timeout:
            return False
        return True

    def is_mdi_move_done(self):
        #TODO get rid of this polling by using main GUI stat object?
        self.stat.poll()
        return self.stat.state == linuxcnc.RCS_DONE or self.stat.state == linuxcnc.RCS_ERROR

    def move_to_point(self, point, feed):
        self.command.mode(linuxcnc.MODE_MDI)
        self.command.wait_complete(1.0)
        #FIXME deal with wrong mode gracefully
        if feed > 0.0000001:
            movecmd = 'G1 X{0} Y{1} F{2}'.format(point[0],point[1],feed)
        else:
            movecmd = 'G0 X{0} Y{1}'.format(point[0],point[1])
        logging.debug(movecmd)
        self.command.mdi(movecmd)
        return self.soft_wait_complete()

    def capture_frame(self):
        frame = self.frame_buffer[-1].copy()
        self.image_queue.put(frame)
        logging.debug('{0} Images now in queue'.format(self.image_queue.qsize()))
        #cv2.imwrite('/home/robert/gcode/camera/tempimage_{0}.bmp'.format(self.image_queue.qsize()),frame)

    def pause(self):
        pass

    def resume(self):
        pass

    def run(self):
        """
            Main function for thread, repeat this process until we're done:
        """

        # Start by clearing out the queue
        #NOTE this part has become dense. To prevent hangs, NOTHING
        #called within this loop can be blocking without a timeout.
        completed_points = 0
        try:
            logging.debug('Starting Scan')
            for point in self.scene.points:
                #Crude status output via a tuple
                #KLUDGE wait on pause, but allow abort
                while self.feedhold_event.is_set() and not self.complete_event.is_set() and not self.abort_event.is_set():
                    time.sleep(0)
                # Note: move has built in delay
                if not self.move_to_point(point[0], self.scene.feed):
                    logging.error('Failed to move to point {0}, aborting scan!'.format(point[0]))
                    break
                if point[1]:
                    self.status_queue.put_nowait((point[0],completed_points))
                    logging.info('Capturing frame at point {0}'.format(point[0]))
                    for t in range(6):
                        logging.debug("Got a new frame")
                        self.frame_ready_event.clear()

                        #KLUDGE Make sure not to block here
                        if not self.abort_event.is_set():
                            self.frame_ready_event.wait(1.0)
                        else:
                            break
                    self.capture_frame()
                    completed_points+=1
                else:
                    logging.info('Taking up backlash...')
                if self.abort_event.is_set() or self.complete_event.is_set():
                    break

            # All points scanned, tell the processor thread that we're done
            if not self.abort_event.is_set():
                self.complete_event.set()
            self.status_queue.put(([],0))

        # Catch all threading exceptions to prevent hangups
        # TODO specific exception handling
        except Exception as inst:
            logging.debug('Scanning thread interrupted')
            print inst
        finally:
            logging.debug('Scanning thread complete')


class ImageProcessThread(threading.Thread):

    def __init__(self, camera, scene, image_queue, complete_event, abort_event,filename, use_inch=True):
        """ To prevent thread-unsafe access, we copy all useful data out of the
        main structures, but don't store a copy of them in the thread. This
        way, the thread uses local data. Since the settings should never change
        during a scan, we don't need to be able to access or change the scene /
        camera.
        """

        # Data required for image processing
        self.img_rotation = scene.angle
        self.frame_size = np.array(camera.get_frame_size())
        self.cropped_size = scene.get_window_from_fov(self.frame_size)
        self.lower_corner, self.upper_corner = scene.get_window_bounding_box(self.frame_size, self.cropped_size)

        # Threading structures
        self.image_queue = image_queue
        self.complete_event = complete_event
        self.abort_event = abort_event

        # output filename
        self.filename = filename
        #FIXME handle metric
        self.tsi_header = tsifile.TsiHeader(camera, scene, use_inch)
        threading.Thread.__init__(self,name='ImgProcThread')

    def process_image(self,image):

        #Compute the rotation matrix to compensate for camera rotation, centered on image
        M = cv2.getRotationMatrix2D(tuple(self.frame_size.astype('int') / 2),
                                    self.img_rotation,
                                    1.0)

        img_rotated = cv2.warpAffine(image, M, tuple(self.frame_size.astype('int')))

        img_cropped = img_rotated[self.lower_corner[1]:self.upper_corner[1],
                                  self.lower_corner[0]:self.upper_corner[0]]
        logging.debug('img_cropped size: {0}'.format(img_cropped.shape))
        return img_cropped

    def run(self):
        """
        Main function for image processing thread. Wait for new images in
        the raw image queue, then process and write incoming images to the
        TSI file. Finally, close the TSI file when the scan is done.
        """
        logging.debug('Starting image processing')
        try:
            with tsifile.TsiFile(self.filename, self.tsi_header) as testfile:
                #TODO more direct setup here?
                testfile.header.write(testfile.file_handle)
                while not (self.complete_event.is_set() or self.abort_event.is_set()) or not self.image_queue.empty():
                    if not self.image_queue.empty():
                        image = self.image_queue.get()
                        # Do processing here
                        processed_image = self.process_image(image)
                        testfile.add_cropped_image(processed_image)
                        #cv2.imwrite('/home/robert/gcode/camera/processed_{0}.bmp'.format(self.image_queue.qsize()),processed_image)
                        self.image_queue.task_done()
                    time.sleep(.125)

        except Exception as e:
            logging.error('Interrupted with exception {0}'.format(e.args))

        logging.debug('Processing thread complete')


class Scanner():


    #########################################################################
    # Setup / init functions for scanner

    def __init__(self,stat, scanfile=None,scene=None,camera=None,render_target=None):
        # The camera is the active VideoCapture object
        self.camera = camera
        # a "scene" is other settings, like scaling, start / end points, etc
        self.scene = SceneSettings() if scene is None else scene
        self.raw_queue = Queue.Queue()
        self.status_queue = Queue.Queue()
        self.stat = stat

        if scanfile is None:
            self.filename = self.get_default_filename()
            logging.warn('Using default scan file : {0}'.format(self.filename))
        else:
            self.filename = scanfile

        #Old names that will be refactored
        self.zoom_state = 'off'
        self.scope_circle_dia = 10.0
        self.calibration_shrinkage = 0.3

        # Placeholders for threads
        self.scan_thread = None
        self.processing_thread = None

        # Events for threading control
        self.complete_event = threading.Event()
        self.abort_event = threading.Event()

        self.frame_ready_event = threading.Event()

        # Safe storage of frames in a circular buffer, since we only ever want
        # the most recent one
        self.raw_frame_buffer = deque(maxlen=6)

        self.overlay_transparency = 0.7
        self.preview_size = (528,396)

        self.set_render_target(render_target)

        self.stopwatch = None


    # Filename handling functions

    def get_default_filename(self,stem='scan',extension='tsi'):
        """ Create a new numbered filename, checking against existing files in
        the default directory
        """

        # Search specifically for our number suffix, and strip it out of the
        # stem. By only searching for our specific format, this lessens the
        # chances of stripped user data.
        file_fmt = "%s_%03i.%s"

        filename_gen = (file_fmt % (stem, i, extension) for i in itertools.count(0))

        #FIXME defeats purpose of generator syntax
        filename = next(filename_gen)
        #TODO get this path from global or GUI state?
        while os.path.exists(os.path.join(os.path.expanduser('~/gcode/camera'), filename)):
            filename = next(filename_gen)
            continue
        return filename

    def set_filename(self,filename):
        """ Using a candidate filename, find and store an unused,
        number-suffixed filename based on the given name.
        returns the actual filename stored
        """
        #TODO default arguments are confusing here
        if not filename:
            self.filename = self.get_default_filename()
        else:
            #Remove extension from input filename
            file_stem = os.path.splitext(filename)[0]

            #Remove our number suffix (prevents endless name growth)
            stem_stripped = re.sub('_\d\d\d$','',file_stem)
            self.filename = self.get_default_filename(stem=stem_stripped)

        return self.filename

    def create_snapshot_filename(self):
        """ Create a unique filename for captured snapshots so that they don't overwrite."""
        return self.get_default_filename('snapshot','jpg')

    def remove_camera(self):
        if self.camera is None:
            return
        self.camera.vidsrc.release()
        self.camera = None

    def create_camera(self):
        """ Initialize a new camera instance and store in scanner"""
        self.remove_camera()
        #TODO device #
        self.camera = ScanCamera(0,self.raw_frame_buffer)
        if not self.camera.vidsrc.grab():
            self.remove_camera()
            return False
        else:
            self.on_camera_enable()
            return True

    def on_camera_enable(self):
        """ Copy state from GUI to scanner internals after camera is enabled.
        This is a sloppy way to do it, but it's a start
        """
        #FIXME make the camera a property so that any change does this automatically?
        # Store the calibration points based on the camera
        self.scene.set_calibration_points(*self.get_calibration_points())

    def stop_threads(self):
        """ Safely abort scanning threads. """
        #TODO deal with junk exceptions
        logging.debug('Stopping scanner threads')
        self.abort_event.set()
        self.complete_event.clear()
        # Block and wait for threads to end
        try:
            self.scan_thread.join()
        except AttributeError:
            # Handle case where threads are not created yet
            pass

        try:
            self.processing_thread.join()
        except AttributeError:
            # Handle case where threads are not created yet
            pass
        # Push empty status
        self.status_queue.put(([],0))

    def init_threads(self,feedhold_event):
        #First, stop existing threads
        #TODO deal with missing items / errors
        self.stop_threads()

        # Create new events and threads
        self.complete_event.clear()
        self.abort_event.clear()

        self.scan_thread = ScannerThread(self.stat, self.raw_frame_buffer, self.scene, self.raw_queue, self.status_queue, self.complete_event, self.abort_event, self.frame_ready_event, feedhold_event)
        #TODO better encapsulation of machine state (units)
        self.processing_thread = ImageProcessThread(self.camera, self.scene, self.raw_queue, self.complete_event, self.abort_event, self.filename, self.use_inch)

    def set_calibration_ratio(self,r):
        self.calibration_shrinkage = r

    def get_calibration_points(self):
        """ Get image points for calibration of scale and angle.

        returns two points as (x,y) tuples
        """
        corner = np.array(self.camera.get_frame_size())

        p1 = self.calibration_shrinkage * corner
        p2 = (1.0-self.calibration_shrinkage) * corner

        #Switch Y coordinates around to align with Kirk's GUI graphic
        temp = p1[1]
        p1[1]=p2[1]
        p2[1]=temp

        p1_out = tuple(p1.astype('int'))
        p2_out = tuple(p2.astype('int'))
        return p1_out, p2_out

    def save_snapshot(self):
        frame = self.raw_frame_buffer[-1].copy()
        print frame.shape
        if frame is not None:
            imgpath = os.path.join(os.path.expanduser('~/gcode/camera'),self.create_snapshot_filename())
            print imgpath
            print cv2.imwrite(imgpath,frame)

    def set_render_target(self,gtk_image = None):
        self.gtk_preview_image = gtk_image

    def ready_to_scan(self):
        """ Validation to make sure that all the scan settings are present """
        #TODO throw tormach-style errors when anything is wrong
        #TODO highlight bad DRO's
        if self.scene is None:
            return False
        if self.camera is None:
            return False
        if not self.scene.is_valid():
            return False
        if self.running():
            return False
        return True


    def start(self,feedhold_event):
        if not self.ready_to_scan():
            return
        self.init_threads(feedhold_event)
        #TODO need to kill these threads and remake them for a second scan
        self.scan_thread.start()
        self.processing_thread.start()

    def pause(self):
        pass

    def abort(self):
        """Redundant function to abort the scanner"""
        self.stop_threads()

    def moving(self):
        """ Test if scanner needs to control movement """
        if self.scan_thread and self.scan_thread.is_alive():
            return True
        # Default to not running unless we see activity on threads
        return False

    def running(self):
        if self.moving():
            return True
        if self.processing_thread and self.processing_thread.is_alive():
            return True


    # Utility functions for scanner

    def periodic_update(self, page=None):
        """ All functions for the periodic GUI update should happen at once here, to prevent UI / video lag"""
        if not self.stopwatch:
            self.stopwatch = timer.Stopwatch()
            time_interval = 0
        else:
            time_interval = self.stopwatch.get_elapsed_seconds()
            self.stopwatch.restart()

        self.frame_update()
        self.render_overlay(page)

        work_time = self.stopwatch.get_elapsed_seconds()
        # print "Periodic update: time between calls %f sec   work time %f sec" % (time_interval, work_time)
        self.stopwatch.restart()


    def frame_update(self):
        #TODO obviously need better checks here
        if self.camera is not None:
            #Pull out camera frame
            #FIXME deal with damage, bad frame etc.
            self.camera.update_frame_buffer()
            self.frame_ready_event.set()


    def render_overlay(self, page):
        """ Kludgy way to add an overlay to a the current frame depending on the current page"""

        # Early abort conditions
        if self.camera is None:
            return False

        if len(self.raw_frame_buffer) == 0:
            return

        # Get the latest frame from the buffer
        frame = self.raw_frame_buffer[-1].copy()

        # Choose which overlay to produce
        if page is None:
            return
        elif 'Calibration' in page:
            overlay_frame = self.render_calibration_frame(frame)
        elif 'Scope' in page:
            frame = self.render_rotated_frame(frame)
            overlay_frame = self.render_scope_frame(frame)
        else:
            frame = self.render_rotated_frame(frame)
            overlay_frame = self.render_fov_frame(frame)

        # Create transparent overlay by blending original frame
        # and the modified overlay
        # http://bistr-o-mathik.org/2012/06/13/simple-transparency-in-opencv/
        #summed_frame = cv2.addWeighted(frame,
                                       #1.0-self.overlay_transparency,
                                       #overlay_frame,
                                       #self.overlay_transparency,
                                       #0)

        # Handle zoomed state if need be by resizing the final frame
        if self.zoom_state == 'p1' and 'Calibration' in page:
            zoomed_frame = self.zoom_to_point(overlay_frame,self.scene.first_px,3)
        elif self.zoom_state == 'p2' and 'Calibration' in page:
            zoomed_frame = self.zoom_to_point(overlay_frame,self.scene.second_px,3)
        else:
            zoomed_frame = overlay_frame

        #Resize after all drawing is done
        shrunk_frame = cv2.resize(zoomed_frame,self.preview_size)

        # Convert from opencv standard BGR to RGB for GTK
        rgb_frame = cv2.cvtColor(shrunk_frame,cv2.COLOR_BGR2RGB)

        # Finally, load processed frame into preview image
        preview_pixbuf = gtk.gdk.pixbuf_new_from_array(rgb_frame, gtk.gdk.COLORSPACE_RGB, 8)
        self.gtk_preview_image.set_from_pixbuf(preview_pixbuf)

    def render_rotated_frame(self,frame):
        M = cv2.getRotationMatrix2D(self.camera.get_center_point(),
                                    self.scene.angle,
                                    1.0)

        return cv2.warpAffine(frame, M, self.camera.get_frame_size())

    def render_scope_frame(self,frame):
        scope_overlay=frame.copy()
        center_point = get_frame_center(frame)
        #TODO make color adjustable for color-blind users
        circle_radius = int(max(self.scope_circle_dia / 2.0, 1))
        mark_radius = circle_radius+10
        scope_color = (100, 255, 0)
        center_mark(scope_overlay,center_point,
                    circle_radius,
                    mark_radius,
                    scope_color,2)
        return scope_overlay

    def render_fov_frame(self,frame):
        return dim_border(frame,self.scene.fov_ratio)

    def render_calibration_frame(self,frame):
        calibration_overlay = frame.copy()
        p1,p2 = self.get_calibration_points()

        #Draw rectangle to represent calibration points
        cv2.rectangle(calibration_overlay,p1, p2,(0,255,0),1)

        #Highlight points
        #TODO allow this color to be changed somewhere due to color blindness?
        p1_color = (0,255,0)
        center_mark(calibration_overlay,p1,10,20,p1_color,1)

        p2_color = (0,255,100)
        center_mark(calibration_overlay,p2,10,20,p2_color,1)

        return calibration_overlay

    def zoom_to_point(self,frame,center,factor):
        """ Zoom the current image to the desired point, preserving the image size
        """
        if center is None:
            return frame

        # Get width and height from frame shape
        cur_size = np.array(frame.shape[0:2])
        # Switch from row,column to width,height
        rc_center = np.array(center[1::-1])
        # find the bounding points for the zoomed subimage
        lower_corner = rc_center - cur_size / 2 / factor
        upper_corner = rc_center + cur_size / 2 / factor
        # Resize the sub-image to full size
        output_frame = cv2.resize(frame[lower_corner[0]:upper_corner[0],lower_corner[1]:upper_corner[1]],self.preview_size)
        return output_frame


def get_frame_center(frame):
    """ Find the center of an opencv image"""
    width = frame.shape[1]
    height = frame.shape[0]
    return (int(width/2),int(height/2))

# Helper functions for frame overlay rendering
def center_mark(image,center_raw,radius,mark_radius,color,thickness=1):
        center=np.array(center_raw)
        cv2.circle(image,tuple(center),radius,color,thickness)
        x_disp = [mark_radius,0]
        y_disp = [0,mark_radius]
        #Always make the lines thin to avoid occluding features
        cv2.line(image, tuple(center-x_disp), tuple(center+x_disp),color,1)
        cv2.line(image, tuple(center-y_disp), tuple(center+y_disp),color,1)

def dim_border(img,fov):

    full_width = img.shape[1]
    full_height = img.shape[0]

    cropped_width_px = int(fov * full_width)
    cropped_height_px = int(fov * full_height)

    #Compute other helpful parameters
    cropped_row_start = int((full_height
            - cropped_height_px ) / 2.0)

    cropped_column_start = int((full_width
            - cropped_width_px ) / 2.0)

    #logging.info('cropped w x h = {0} x {1}'.format(cropped_width_px, cropped_height_px))

    cropped_row_end = cropped_row_start + cropped_height_px
    cropped_column_end = cropped_column_start + cropped_width_px

    # cut intensity in half for everything but the cropped region
    mask = np.zeros((img.shape),np.uint8)
    mask[cropped_row_start:cropped_row_end,cropped_column_start:cropped_column_end]=img[cropped_row_start:cropped_row_end,cropped_column_start:cropped_column_end]
    return mask

