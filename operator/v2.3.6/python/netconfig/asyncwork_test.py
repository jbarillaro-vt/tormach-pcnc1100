# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------


import os
import time
import unittest
import asyncwork

# gui callback has to be pickle compatible which means top level module scope function
# can't be a class static method or a class method
# can't be a lambda
# can't be a private function

g_gui_pid = None
g_gui_function_ran = False


def gui_function(arglist):
    global g_gui_pid, g_gui_function_ran
    g_gui_function_ran = True
    g_gui_pid = os.getpid()
    return arglist[0] + arglist[1]


def gui_function_exception(arglist):
    raise ValueError("Just a test")


def basic_async_function(workercontext, one, two):
    # use our process ID as the very first progress value
    workercontext.report_progress(os.getpid())

    for i in range(5):
        workercontext.report_progress(i)
        time.sleep(0.1)

    # darn, hit some situation where we need a user decision
    result_from_gui_function = workercontext.run_on_gui(gui_function, [2, 3])

    # if everything pickled correctly, we should get the sum of the arguments back
    # use the value as our final result so test case can verify

    # darn, hit some situation where we need a user decision
    try:
        workercontext.run_on_gui(gui_function_exception, [2, 3])
        assert False, "expected exception to get returned and raised"
    except ValueError:
        pass

    # ok, now do more work than even expected. this will test
    # that get_final_result() ignores extra progress reports
    # in the feedback queue while it searches for the final result.

    for i in range(5,20):
        workercontext.report_progress(i)
        time.sleep(0.1)

    workercontext.final_result(result_from_gui_function)


def exception_function(workercontext):
    raise RuntimeError("Just a test - Kaboom!")


def slow_function(workercontext):
    time.sleep(2)
    workercontext.report_progress(2)
    time.sleep(2)
    workercontext.final_result(4)


class TestAsyncWork(unittest.TestCase):

    def test_basic(self):
        mgr = asyncwork.AsyncWorkManager()

        mgr.run_async(basic_async_function, {"one":"arg1", "two":"arg2"})

        time.sleep(2)   # force worker to make some progress

        # first progress value is the PID of the worker process
        # can only verify that it is NOT our PID
        workerpid = mgr.get_progress(True)

        self.assertEqual(workerpid, mgr._asyncprocess.pid)

        # should get 10 progress events
        for ii in range(10):
            self.assertEqual(mgr.get_progress(True), ii)

        # make sure that in the middle of getting progress, the worker was able
        # to run the GUI function on this thread
        self.assertTrue(g_gui_function_ran)
        self.assertEqual(g_gui_pid, os.getpid())

        value = mgr.get_final_result(True)
        mgr.shutdown()

        self.assertEqual(value, 5)


    def test_exception(self):
        mgr = asyncwork.AsyncWorkManager()

        mgr.run_async(exception_function)

        time.sleep(1)  # wait for child to fully die

        with self.assertRaises(asyncwork.AsyncWorkerDiedUnexpectedlyError):
            value = mgr.get_final_result(True)

        mgr.shutdown()


    def test_nonblocking_feedback(self):
        mgr = asyncwork.AsyncWorkManager()

        mgr.run_async(slow_function)

        t0 = time.time()
        value = mgr.get_progress(False)
        t1 = time.time()
        self.assertLess(t1 - t0, 0.015)   # 15 milliseconds or less of wall clock time

        t0 = time.time()
        value = mgr.get_final_result(False)
        t1 = time.time()
        self.assertLess(t1 - t0, 0.015)   # 15 milliseconds or less of wall clock time

        # Now block until the first progress is reported
        value = mgr.get_progress(True)
        self.assertEqual(value, 2)

        t0 = time.time()
        value = mgr.get_progress(False)
        t1 = time.time()
        self.assertLess(t1 - t0, 0.015)   # 15 milliseconds or less of wall clock time

        t0 = time.time()
        value = mgr.get_final_result(False)
        t1 = time.time()
        self.assertLess(t1 - t0, 0.015)   # 15 milliseconds or less of wall clock time

        # Now block until the final result is reported
        value = mgr.get_final_result(True)
        self.assertEqual(value, 4)

        mgr.shutdown()


if __name__=='__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAsyncWork)
    unittest.TextTestRunner(verbosity=2).run(suite)

