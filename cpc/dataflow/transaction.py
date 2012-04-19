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
import os
import sys
import os.path
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import traceback
import subprocess
import stat
import threading

import apperror
import connection
import value


log=logging.getLogger('cpc.dataflow.transaction')


class TransactionList(object):
    """A list of transaction items (TransactionItem objects)"""
    def __init__(self, networkLock, autoCommit):
        """Initialize, with autocommit flag.
           networkLock = the projecct's network lock
           autoCommit = whether to autocommit every added item immediately"""
        self.lst=[]
        self.lock=threading.Lock()
        self.autoCommit=autoCommit
        self.networkLock=networkLock

    def addItem(self, transactionItem, project, outf):
        """Add a single transaction item to the list."""
        with self.lock:
            self.lst.append(transactionItem)
        if self.autoCommit:
            self.commit(project, outf)
        else:
            outf.write("Scheduled ")
            transactionItem.describe(outf)
            outf.write(" at commit")

    def commit(self, project, outf):
        """Commit all items of the transaction in one step."""
        affectedInputAIs=set()
        affectedOutputAIs=set()
        outputsLocked=False
        outf.write("Committing scheduled changes:\n")
        with self.lock:
            with self.networkLock:
                try:
                    # first get all affected active instances.
                    for item in self.lst:
                        item.getAffected(project, affectedInputAIs, 
                                         affectedOutputAIs)
                    # lock all affected I/O active instances
                    for ai in affectedOutputAIs:
                        ai.outputLock.acquire()
                    outputsLocked=True
                    # now run the transaction
                    for item in self.lst:
                        outf.write("- ")
                        item.run(project, project, outf)
                    for ai in affectedInputAIs:
                        ai.handleNewInput(project, 0)
                finally:
                    # make sure everything is released.
                    if outputsLocked:
                        for ai in affectedOutputAIs:
                            ai.outputLock.release()
                    self.lst=[]

class TransactionItem(object):
    """Common base class for transaction item types. 
      
       The actual functions are getAffected() and run(). getAffected should
       return the affected input and output active instance. These are then
       locked, and run() is called to perform the changes. 

       Between getAffected() and run(), the global project.networkLock is 
       locked.
       """
    def getAffected(self, project, affectedDestACPs, affectedOutputAIs):
        """Get the affected items of this transaction

           This is the first item to run. The affected ais are locked
           after this.

           project = the project this item belongs to
           affectedInputAIs = a set of active instances that will be 
                              updated with affected inputs generated by 
                              this change.
           affectedOutputAIs = a set of active instances that will be 
                               updated with active instances with affected 
                               inputs generated by this change.  """
        pass
    def run(self, project, sourceTag, outf=None):
        """Run the transaction item. After this run is finished, 
           handleNewInput() will be called on all affectedInputAIs.
           
           project = the project this item belongs to
           sourceTag = the source tag.
           outf = an output file to write a description of the commited change
                  to (or None)"""
        pass

    def describe(self, outf):
        """Describe the item to be committed later.
           outf =  a file object to write the description to"""
        pass

class SetError(apperror.ApplicationError):
    def __init__(self, name):
        self.str="Assignment: %s not found"%(name)

class Set(TransactionItem):
    """Transaction item for setting a value."""
    def __init__(self, project, itemname, activeInstance, direction, 
                 ioItemList, literal, sourceType):
        """initialize based on the active instance, old value associated
           with the instance, and a new value."""
        #instanceName,direction,ioItemList=connection.splitIOName(itemname, None)
        #self.activeInstance=self.active.getNamedActiveInstance(instanceName)
        self.itemname=itemname
        self.activeInstance=activeInstance
        self.direction=direction
        self.ioItemList=ioItemList
        self.literal=literal
        self.sourceType=sourceType
        with self.activeInstance.lock:
            closestVal=self.activeInstance.findNamedInput(self.direction, 
                                                          self.ioItemList, 
                                                          project,
                                                          True)
        if closestVal is None:
            raise SetError(itemname)


    def getAffected(self, project, affectedInputAIs, affectedOutputAIs):
        """Get the affected items of this transaction"""
        ## there are no affected output AIs: only input AIs change.
        with self.activeInstance.lock:
            closestVal=self.activeInstance.findNamedInput(self.direction, 
                                                          self.ioItemList, 
                                                          project,
                                                          True)
        self.activeInstance.getNamedInputAffectedAIs(closestVal, 
                                                     affectedInputAIs)

    def run(self, project, sourceTag, outf=None):
        """Run the transaction item."""
        ## there are no affected output AIs: only input AIs change.
        with self.activeInstance.lock:
            oldVal=self.activeInstance.findNamedInput(self.direction, 
                                                      self.ioItemList, 
                                                      project,
                                                      False)
            # now we can extract the type.
            tp=oldVal.getType()
            if not isinstance(self.literal, value.Value):
                newVal=value.interpretLiteral(self.literal, tp, self.sourceType,
                                              project.fileList)
            else:
                newVal=self.literal
                if not (tp.isSubtype(rval.getType()) or
                        rval.getType().isSubtype(tp) ):
                    raise ActiveError(
                              "Incompatible types in assignment: %s to %s"%
                              (rval.getType().getName(), tp.getName()))
        self.activeInstance.stageNamedInput(oldVal, newVal, sourceTag)
        if outf is not None:
            outf.write("Set %s:%s to %s\n"%
                       (self.activeInstance.getCanonicalName(),
                        oldVal.getFullName(),
                        newVal.getDesc()))

    def describe(self, outf):
        """Describe the item."""
        outf.write("set %s: %s to %s"%
                   (self.activeInstance.getCanonicalName(),
                    self.itemname, self.literal))

class Connect(TransactionItem):
    """Transaction item for connecting a value"""
    #def __init__(self, connection):
    #    self.connection=connection
    def __init__(self, project, src, dst):
        self.src=src
        self.dst=dst

    def getAffected(self, project, affectedInputAIs, affectedOutputAIs):
        """Get the affected items of this transaction"""
        # we can do this because the global lock prevents other updates
        # at the same time.
        srcInstName,srcDir,srcItemName=connection.splitIOName(self.src, None)
        dstInstName,dstDir,dstItemName=connection.splitIOName(self.dst, None)
        cn=connection.makeConnection(project.active,
                                     srcInstName, srcDir, srcItemName,
                                     dstInstName, dstDir, dstItemName)
        self.connection=cn
        project.active.findConnectionSrcDest(cn,
                                             affectedInputAIs,
                                             affectedOutputAIs)

    def run(self, project, sourceTag, outf=None):
        """Run the transaction item."""
        project.active.addConnection(self.connection, sourceTag)
        if outf is not None:
            outf.write("Connected %s to %s\n"%(self.connection.srcString(),
                                               self.connection.dstString()))

    def describe(self, outf):
        """Describe the item."""
        outf.write("connect %s to %s"%(self.src, self.dst) )

