# This file is part of Copernicus
# http://www.copernicus-computing.org/
# 
# Copyright (C) 2011, Sander Pronk, Iman Pouya, Erik Lindahl, and others.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as published 
# by the Free Software Foundation
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.



import logging
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import Queue
import traceback
import sys
import threading


import cpc.util
import apperror
import function
import instance
import cpc.server.command
import cpc.util
import run
import connection
import value


log=logging.getLogger('cpc.dataflow.task')

class TaskError(apperror.ApplicationError):
    pass

class TaskNoNetError(TaskError):
    def __init__(self, name):
        self.str=("Trying to add new instance in instance %s without subnet"%
                  name)

class TaskQueue(object):
    """A task queue holds the a list of tasks to execute in order."""
    def __init__(self, cmdQueue):
        log.debug("Creating new task queue.")
        self.queue=Queue.Queue()
        self.cmdQueue=cmdQueue
    
    def put(self, task):
        """Put a task in the queue."""
        self.queue.put(task)

    def putNone(self):
        """Put a none into the queue to make sure threads are reading it."""
        self.queue.put(None)
    
    def get(self):
        return self.queue.get()

    def empty(self):
        return self.queue.empty()


class Task(object):
    """A task is a queueable and runnable function with inputs."""
    def __init__(self, project, activeInstance, function, fnInput, 
                 priority, seqNr):
        """Create a task based on a function 
       
           project = the project of this task 
           activeInstance = the activeInstance this task belongs to
           function = the function object
           fnInput = the FunctionRunInput object
           priority = the task's priority.
           seqNr = the task's sequence number
           """
           
        log.debug("creating task")    
        log.debug("Making task of instance %s of function %s"%
                  (activeInstance.instance.getName(),
                   activeInstance.instance.function.getName()))
        self.activeInstance=activeInstance
        self.function=function
        self.priority=priority
        self.id=id(self)
        self.project = project
        # we want only one copy of a task running at a time
        self.lock=threading.Lock() 
        self.seqNr=seqNr
        self.fnInput=fnInput
        self.cmds=[]

    def setFnInput(self, fnInput):
        """Replace the fnInput object. Only for readxml"""
        self.fnInput=fnInput
    def addCommands(self, cmds):
        """Add commands. Only for readxml"""
        for cmd in cmds:
            cmd.setTask(self)
        self.cmds.extend(cmds)

    def getFnInput(self):
        """Get the fnInput object."""
        return self.fnInput

    def getCommands(self):
        return self.cmds

    def _handleFnOutput(self, out):
        # handle addInstances
        addedInstances=[]
        if out.newInstances is not None:
            activeNet=self.activeInstance.getNet()
            if activeNet is None:
                raise TaskNetError(self.activeInstance.instance.getName())
            imports=self.project.getImportList()
            for newInstance in out.newInstances:
                log.debug("Making new instance %s (%s)"%
                          (newInstance.name, 
                           newInstance.functionName))
                fn=imports.getFunctionByFullName(newInstance.functionName,
                                                 self.function.getLib())
                inst=instance.Instance(newInstance.name, fn, 
                                       fn.getFullName())
                addedInstances.append(activeNet.addInstance(inst))
        # new subnet inputs
        if out.newSubnetInputs is not None:
            imports=self.project.getImportList()
            for newSubnetInput in out.newSubnetInputs:
                log.debug("Making new subnet input %s (%s)"%
                          (newSubnetInput.name, newSubnetInput.type))
                tp=imports.getTypeByFullName(newSubnetInput.type,
                                             self.function.getLib())
                #tp=self.project.getType(newSubnetInput.type)
                #self.activeInstance.addNewSubnetInput(newSubnetInput.name, tp)
                si=self.activeInstance.getSubnetInputs()
                si.addMember(newSubnetInput.name, tp, True, False)
        # and new subnet outputs
        log.debug("new subnet outputs: %s"%str(out.newSubnetOutputs))
        if out.newSubnetOutputs is not None:
            imports=self.project.getImportList()
            for newSubnetOutput in out.newSubnetOutputs:
                log.debug("Making new subnet output %s (%s)"%
                          (newSubnetOutput.name, newSubnetOutput.type))
                tp=imports.getTypeByFullName(newSubnetOutput.type,
                                             self.function.getLib())
                #tp=self.project.getType(newSubnetOutput.type)
                #self.activeInstance.addNewSubnetOutput(newSubnetOutput.name,tp)
                so=self.activeInstance.getSubnetOutputs()
                so.addMember(newSubnetOutput.name, tp, True, False)
        # we handle new network connnections and new output atomically: 
        # if the new network connection references newly outputted data,
        # that is all the instance sees.
        try:
            affectedInputAIs=None
            affectedOutputAIs=None
            outputsLocked=False
            # whether the task's ai is already locked
            selfLocked=False
            if out.newConnections is not None:
                # we have new connections so we need to lock the global lock
                self.project.networkLock.acquire()
                imports=self.project.getImportList()
                activeNet=self.activeInstance.getNet()
                if activeNet is None:
                    raise TaskNetError(self.activeInstance.instance.getName())
                # and allocate emtpy sets
                affectedInputAIs=set()
                affectedOutputAIs=set()
                # Make the connections
                conns=[]
                for newConnection in out.newConnections:
                    if newConnection.srcStr is not None:
                        log.debug("Making new connection %s -> %s)"%
                                  (newConnection.srcStr, newConnection.dstStr))
                        conn=connection.makeConnectionFromDesc(activeNet,
                                                           newConnection.srcStr,
                                                           newConnection.dstStr)
                    else:
                        log.debug("Making assignment %s -> %s)"%
                                  (newConnection.val.value, 
                                   newConnection.dstStr))
                        conn=connection.makeInitialValueFromDesc(activeNet,
                                                           newConnection.dstStr,
                                                           newConnection.val)
                    conns.append(conn)
                    activeNet.findConnectionSrcDest(conn, affectedInputAIs,
                                                    affectedOutputAIs)
                # Now lock all affected outputs
                # An exception during this loop should be impossible:
                for ai in affectedOutputAIs:
                    ai.outputLock.acquire()
                    if ai == self.activeInstance: 
                        selfLocked=True
                outputsLocked=True
                # now handle the connection updates
                for conn in conns:
                    activeNet.addConnection(conn, self)
            if not selfLocked:
                self.activeInstance.outputLock.acquire()
                selfLocked=True
            # we can do this safely because activeInstance.inputLock is an rlock
            self.activeInstance.handleTaskOutput(self, out.outputs, 
                                                 out.subnetOutputs)
            # now handle the input generated by making new connections
            if affectedInputAIs is not None:
                for ai in affectedInputAIs:
                    ai.handleNewInput(self, None)
        finally:
            # unlock everything in the right order
            # we still need to unlock self
            if selfLocked:
                self.activeInstance.outputLock.release()
            if (affectedOutputAIs is not None) and outputsLocked:
                for ai in affectedOutputAIs:
                    if ai != self.activeInstance:
                        ai.outputLock.release()
            if out.newConnections is not None:
                # we release the global lock
                self.project.networkLock.release()
        # now activate any new added instances.
        for inst in addedInstances:
            inst.activate()


            ## now do the parts that require locks. 
            #if out.newConnections is not None:
            #    # we set the global lock
            #    self.project.networkLock.acquire()
            #    imports=self.project.getImportList()
            #    activeNet=self.activeInstance.getNet()
            #    if activeNet is None:
            #        raise TaskNetError(self.activeInstance.instance.getName())
            #    affectedInputAIs=set()
            #    affectedOutputAIs=set()
            #    for newConnection in out.newConnections:
            #        if newConnection.srcStr is not None:
            #            log.debug("Making new connection %s -> %s)"%
            #                      (newConnection.srcStr, newConnection.dstStr))
            #            conn=connection.makeConnectionFromDesc(activeNet,
            #                                               newConnection.srcStr,
            #                                               newConnection.dstStr)
            #        else:
            #            log.debug("Making assignment %s -> %s)"%
            #                      (newConnection.val.value, 
            #                       newConnection.dstStr))
            #            conn=connection.makeInitialValueFromDesc(activeNet,
            #                                               newConnection.dstStr,
            #                                               newConnection.val)
            #        activeNet.addConnection(conn, affectedInputAIs,
            #                                affectedOutputAIs)
            #    # so that outputs know where they go
            #    for ai in affectedOutputAIs:
            #        ai.outputLock.acquire()
            #        if ai == self.activeInstance: 
            #            selfLocked=True
            #    outputsLocked=True
            #    if not selfLocked:
            #        self.activeInstance.outputLock.acquire()
            #        selfLocked=True
            #    # and inputs are connected to the right output
            #    for ai in affectedInputAIs:
            #        ai.inputLock.acquire()
            #    # An exception during the above loop should be impossible.
            #    inputsLocked=True
            #    # now make the new connections
            #    for ai in affectedOutputAIs:
            #        ai.handleNewOutputConnections()
            #    for ai in affectedInputAIs:
            #        ai.handleNewInputConnections()
            #else:
            #    self.activeInstance.outputLock.acquire()
            #    selfLocked=True
            ## we can do this safely because activeInstance.inputLock is an rlock
            #self.activeInstance.handleTaskOutput(self, out.outputs, 
            #                                     out.subnetOutputs)
            #if affectedInputAIs is not None:
            #    for ai in affectedInputAIs:
            #        ai.handleNewInput(None, 0)
        #finally:
        #    # unlock everything in the right order
        #    if (affectedInputAIs is not None) and inputsLocked:
        #        for ai in affectedInputAIs:
        #            ai.inputLock.release()
        #    if (affectedOutputAIs is not None) and outputsLocked:
        #        if (affectedOutputAIs is not None): 
        #            for ai in affectedOutputAIs:
        #                ai.outputLock.release()
        #                if ai == self.activeInstance:
        #                    selfLocked=False
        #    if selfLocked:
        #        self.activeInstance.outputLock.release()
        #    if out.newConnections is not None:
        #        # we releae the global lock
        #        self.project.networkLock.release()

    def run(self, cmd=None):
        """Run the task's underlying function with the required inputs,
           possibly in response to a finished command (given as parameter cmd) 
           and return a list of commands to queue. If a command is queued,
           the task should continue existining until its corresponding 
           run() call is called. """
        with self.lock:
            try:
                log.debug("Running function %s"%
                          self.activeInstance.instance.getName())
                self.fnInput.cmd=cmd
                self.fnInput.reset()

                if self.activeInstance.runLock is not None:
                    self.activeInstance.runLock.acquire()
                # now actually run
                ret=self.function.run(self.fnInput)
                # and we're done.
                if self.activeInstance.runLock is not None:
                    self.activeInstance.runLock.release()

                self.fnInput.cmd=None
                if cmd is not None:
                    self.cmds.remove(cmd)

                # handle things that can throw exceptions:
                haveRetcmds=(ret.cmds is not None) and len(ret.cmds)>0
                   
                if ( (ret.hasOutputs() or ret.hasSubnetOutputs()) and
                     ( haveRetcmds or len(self.cmds)>0 ) ):
                    raise TaskError("Task returned both outputs: %s, %s and commands %s,%s"%
                                    (str(ret.outputs), str(ret.subnetOutputs), 
                                     str(self.cmds),str(ret.cmds)))

                self._handleFnOutput(ret)

                if ret.cmds is not None: 
                    for cmd in ret.cmds:
                        cmd.setTask(self)
                        self.cmds.append(cmd)
                else:
                    # the task is done.
                    self.activeInstance.removeTask(self)

                # everything went OK; we got results
                log.debug("Ran fn %s, got %s"%(self.function.getName(), 
                                                   str(ret.outputs)) )
                # there is nothing more to execute
                if len(self.cmds) == 0:
                    self.fnInput.destroy()
            except cpc.util.CpcError as e:
                self.activeInstance.markError(e.__str__())
                return None
            except:
                fo=StringIO()
                traceback.print_exception(sys.exc_info()[0], sys.exc_info()[1],
                                          sys.exc_info()[2], file=fo)
                errmsg="Run error: %s"%(fo.getvalue())
                self.activeInstance.markError(errmsg)
                return None

            return ret.cmds

    def getID(self):
        return "%s.%s"%(self.activeInstance.getCanonicalName(), self.seqNr)

    def getFunctionName(self):
        return self.function.getName()
    
    def getProject(self):
        return self.project

    def writeXML(self, outf, indent=0):
        indstr=cpc.util.indStr*indent
        iindstr=cpc.util.indStr*(indent+1)
        outf.write('%s<task project="%s" priority="%d" active_instance="%s" seqnr="%d">\n'%
                   (indstr,
                    self.project.getName(),
                    self.priority, 
                    self.activeInstance.getCanonicalName(),
                    self.seqNr))
        self.fnInput.writeXML(outf, indent+1)
        if len(self.cmds)>0:
            outf.write('%s<command-list>\n'%iindstr)
            for cmd in self.cmds:
                cmd.writeXML(outf, indent+2)
            outf.write('%s</command-list>\n'%iindstr)
        outf.write('%s</task>\n'%indstr)
