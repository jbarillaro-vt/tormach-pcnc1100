#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------



#
# Imports
#
import os
import multiprocessing
import Queue


class WorkerContext():
    '''
    WorkerContext is used by the child process to communicate with the AsyncWorkManager object in the parent process.
    While the work is being one, progress can be reported. If some situation occurs which requires user input, there
    is facility for pausing work and invoking code back on the GUI thread in the parent process.
    '''
    def __init__(self, cmd_to_worker_queue, feedback_to_mgr_queue):
        # object is initially constructed in the manager process so remember that for later active asserting
        self._mgr_pid = os.getpid()
        self._cmd_to_worker_queue = cmd_to_worker_queue
        self._feedback_to_mgr_queue = feedback_to_mgr_queue


    def run_on_gui(self, target, arglist=None):
        '''
        Run the target function on the GUI thread in the parent process. This may be needed to gain user feedback on an
        error condition or something that occurred while doing the asynchronous work.
        Returns whatever the target function returns (and therefore blocks until the target function returns)
        '''
        # async code is the only one that should be calling this.
        # check with active debugging
        assert self._mgr_pid != os.getpid()
        assert self._feedback_to_mgr_queue, "Invalid WorkerContext state as final_result() was already called."

        data = QueueData(QueueData.GUI, [target, arglist])
        self._feedback_to_mgr_queue.put(data)

        # block until the gui thread in the parent process returns
        data = self._cmd_to_worker_queue.get(True)
        assert data.command == QueueData.GUI

        if data.exception != None:
            raise data.exception

        return data.value


    def report_progress(self, progress_value):
        '''
        Send progress_value over to the parent process.
        '''
        # async code is the only one that should be calling this.
        # check with active debugging
        assert self._mgr_pid != os.getpid()
        assert self._feedback_to_mgr_queue, "Invalid WorkerContext state as final_result() was already called."

        # write this to the queue
        data = QueueData(QueueData.PROGRESS, progress_value)
        self._feedback_to_mgr_queue.put(data)


    def final_result(self, return_value):
        '''
        Send the final result of the async work to the parent process.
        '''
        # async code is the only one that should be calling this.
        # check with active debugging
        assert self._mgr_pid != os.getpid()
        assert self._feedback_to_mgr_queue, "Invalid WorkerContext state as final_result() was already called once before."

        data = QueueData(QueueData.FINALRESULT, return_value)
        self._feedback_to_mgr_queue.put(data)
        self._feedback_to_mgr_queue.close()
        self._feedback_to_mgr_queue = None


class ProgressTimeout(Exception):
    '''
    Raised when there is no progress to report
    '''
    def __init__(self):
        Exception.__init__(self)


class AsyncWorkerDiedUnexpectedlyError(Exception):
    '''
    Raised when the async worker process dies unexpectedly with no final result communicated back.
    '''
    def __init__(self):
        Exception.__init__(self)


class AsyncWorkManager():
    '''
    The AsyncWorkManager provides a way to run a function in an asynchronous child process while having
    an easy way to communicate feedback and results of the work.
    Typically used by the GUI thread of a GTK python app so that work can be done without blocking the
    dispatching of the event loop (which freezes the UI).
    While the async work is being done, some situation may develop where it needs user input (think error handling).
    In this case, there is a facility for the worker to run a function back on the main GUI thread to
    perform a message box or some other GTK UI.

    The asyncwork module relies on the multiprocessing module to move code and data between the calling process and the child process.
    The standard multiprocessing module does this with pickle, but that's pretty restrictive. The function
    you want to run has to be a top level function (can't be an object method or lambda).
    There is an alternative package called pathos which eliminates these restrictions seamlessly. It uses a
    replacement marshaler called dill.
    But I didn't want to pull in a huge pile of further dependencies at this point. Let's go there only
    if its really needed.

    Pathos framework:
    http://trac.mystic.cacr.caltech.edu/project/pathos/wiki.html
    '''
    def __init__(self):
        self._mgr_pid = os.getpid()
        self._cmd_to_worker_queue = multiprocessing.Queue()
        self._feedback_to_mgr_queue = multiprocessing.Queue()
        self._context = WorkerContext(self._cmd_to_worker_queue, self._feedback_to_mgr_queue)
        self._asyncprocess = None
        self._finalresult = None


    def run_async(self, targetfunction, kwargs={}):
        '''
        Run the targetfunction(argstuple) in a child process and provide a way to monitor status
        and collect a final result of the work.
        '''
        # this entire object should never be accessed from the worker process
        # check with active debugging
        assert self._mgr_pid == os.getpid()

        # TODO dynamically add wrapper to target functor then we can put return object on the feedback queue
        # automatically and catch and forward exceptions
        # But for now, let's just count on cooperation
        # Could define some decorator which would make it handy and visually clear, e.g. @asyncwork

        kwargs["workercontext"] = self._context
        self._asyncprocess = multiprocessing.Process(target=targetfunction, kwargs=kwargs)
        self._asyncprocess.start()
        assert self._asyncprocess.pid, "Something died trying to fork async work"


    def get_progress(self, block):
        '''
        Try to get progress data from the async worker if they have communicated it.
        Requests to run a function on the GUI thread from the async worker may occur during
        the call.
        Returns None if no progress is available and caller does not want to block waiting for it.
        Otherwise returns progress value received from worker.
        '''
        # this entire object should never be accessed from the worker process
        # check with active debugging
        assert self._mgr_pid == os.getpid()

        value = None

        noticed_child_is_dead = 0
        while self._feedback_to_mgr_queue:
            try:
                # pull from the feedback queue
                # we use a timeout so we occasionally fall out to
                # check child process liveness
                # (otherwise we could block forever if child unexpectedly dies)
                qd = self._feedback_to_mgr_queue.get(block, 0.25)

                if qd.command == QueueData.PROGRESS:
                    value = qd.value
                    break

                elif qd.command == QueueData.GUI:
                    # worker needs to run a function on this GUI thread so dispatch it
                    self.__runGuiFunctor(qd.value)

                elif qd.command == QueueData.FINALRESULT:
                    # save the final result for a later call to get_final_result()
                    self._finalresult = qd.value
                    self._feedback_to_mgr_queue.close()
                    self._feedback_to_mgr_queue = None

                else:
                    raise NotImplementedError("Unexpected feedback queue key value %s" % qd.command)

            except Queue.Empty:
                if not block:
                    # no feedback from the async process yet and the caller doesn't want to block
                    # so bail.
                    break

                if not self._asyncprocess.is_alive():
                    # loop around and check the queue for one final result if we haven't been here before.
                    noticed_child_is_dead += 1
                    if noticed_child_is_dead > 1:
                        # child is no longer running AND we've checked the queue for a final result
                        # after we noticed the child was dead. This avoids the race
                        # condition where we time out on the queue get() and then right after that
                        # the child writes a final result and dies before the is_alive() check is done above.

                        # if child process dies due to exception, the exit code should not be 0
                        assert self._asyncprocess.exitcode != 0

                        raise AsyncWorkerDiedUnexpectedlyError()

        return value



    def get_final_result(self, block):
        '''
        Try to get the final result from the async worker if it is done.
        Requests to run a function on the GUI thread from the async worker may occur during
        the call.
        Returns None if no final result is available and caller does not want to block waiting for it.
        Otherwise returns final result received from worker.
        '''

        # this entire object should never be accessed from the worker process
        # check with active debugging
        assert self._mgr_pid == os.getpid()

        noticed_child_is_dead = 0
        while self._feedback_to_mgr_queue:
            try:
                # pull from the feedback queue until we get a final result
                # we use a timeout so we occasionally fall out to
                # check child process liveness
                # (otherwise we could block forever if child unexpectedly dies)
                qd = self._feedback_to_mgr_queue.get(block, 0.25)

                if qd.command == QueueData.PROGRESS:
                    pass    # throw it on the floor as the caller isn't interested

                elif qd.command == QueueData.GUI:
                    # worker needs to run a function on this GUI thread so dispatch it
                    self.__runGuiFunctor(qd.value)

                elif qd.command == QueueData.FINALRESULT:
                    # bingo
                    self._finalresult = qd.value
                    self._feedback_to_mgr_queue.close()
                    self._feedback_to_mgr_queue = None

                else:
                    raise NotImplementedError("Unexpected feedback queue key value %s" % qd.command)

            except Queue.Empty:
                if not block:
                    # no feedback from the async process yet and the caller doesn't want to block
                    # so bail.
                    break

                if not self._asyncprocess.is_alive():
                    # loop around and check the queue for one final result if we haven't been here before.
                    noticed_child_is_dead += 1
                    if noticed_child_is_dead > 1:
                        # child is no longer running AND we've checked the queue for a final result
                        # after we noticed the child was dead. This avoids the race
                        # condition where we time out on the queue get() and then right after that
                        # the child writes a final result and dies before the is_alive() check is done above.

                        # if child process dies due to exception, the exit code should not be 0
                        assert self._asyncprocess.exitcode != 0

                        raise AsyncWorkerDiedUnexpectedlyError()

        return self._finalresult


    def shutdown(self):
        # this entire object should never be accessed from the worker process
        # check with active debugging
        assert self._mgr_pid == os.getpid()

        self._asyncprocess.join()

        # if child process dies due to exception, the exit code will not be 0
        #assert self.asyncprocess.exitcode is 0

        self._asyncprocess = None


    def __runGuiFunctor(self, targetlist):
        # the targetlist is a list of 2 items - the function to call and the argument list to pass to the function
        assert len(targetlist) == 2

        qd = QueueData(QueueData.GUI, None)
        try:
            qd.value = targetlist[0](targetlist[1])
        except Exception as e:
            # snag the exception and pass that back to the worker process
            qd.exception = e

        self._cmd_to_worker_queue.put(qd)



class QueueData():
    '''
    Private constants for queue communication
    '''
    GUI = 1
    PROGRESS = 2
    FINALRESULT = 3

    def __init__(self, cmd, value):
        self.command = cmd
        self.value = value
        self.exception = None
