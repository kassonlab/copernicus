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
import collections
import os
import os.path
import xml.sax


log=logging.getLogger('cpc.dataflow.active_value')


import cpc.util
import apperror
import vtype
import value

class ActiveValError(cpc.util.CpcError):
    pass

class ValueUpdateListener(object):
    """Base class of any class that wants to listen to updates of specific
       values."""
    def update(self, val):
        """The method that will be called when the value is updated. 
           Can either return None, or a list of items that are 
           returned with the value's update() method."""
        return None

class ActiveValue(value.Value):
    """The class describing an active data value, as held by an active 
       instance.
       
       Values are trees with dicts/lists of members; the top level is usually
       a <instance>:in or <instance>:out. ActiveValue trees have listeners:
       active connection points that connect values together."""
    def __init__(self, val, tp, parent=None, selfName=None, seqNr=0,
                 createObject=None, fileList=None):
        """Initializes an new value, with no references
    
           val = an original value
           tp = the actual type
           parent = the parent in which this value is a sub-item
           selfName = the name in the parent's collection
        """
        if createObject is None:
            createObject=ActiveValue
        value.Value.__init__(self, val, tp, parent, selfName,
                             createObject=createObject, fileList=fileList)
        self.seqNr=seqNr # sequence number.
        self.listener=None
        self.sourceTag=None

    def setListener(self, listener):
        """Set a pointer to an associated listener (usually an active 
           connection point)."""
        self.listener=listener
    def getListener(self):
        """Get the associated listener."""
        return self.listener

    def update(self, srcVal, newSeqNr, sourceTag=None):
        """Set a new value from a Value, and call update() on all subitems. 
           This keeps all the metadata intact.
           
           srcVal = the input value.
           newSeqNr = the new sequence number (or None to keep the old one)
           sourceTag = any source tag to apply."""
        if newSeqNr is None:
            newSeqNr=self.seqNr
        if self.seqNr > newSeqNr:
            log.debug("Rejecting update because of sequence number: %d>%d."%
                      (self.seqNr, newSeqNr))
            return
        if self.basetype!=srcVal.basetype:
            raise ActiveValError("Type mismatch in %s: expected %s, got %s"%
                                 (self.getFullName(),
                                  self.basetype.getName(), 
                                  srcVal.basetype.getName()))
        self.sourceTag=sourceTag
        self.seqNr=newSeqNr
        # keep the file value for later.
        fileValue=self.fileValue
        self.fileValue=None
        # check updated
        if srcVal.updated:
            self.markUpdated(True)
        # now set the value.
        if not srcVal.basetype.isCompound():
            # and set value
            if ( (self.fileList is not None) and 
                 (srcVal.basetype.isSubtype(vtype.fileType)) and 
                 (srcVal.value is not None)):
                if os.path.isabs(srcVal.value):
                    self.fileValue=self.fileList.getAbsoluteFile(srcVal.value)
                    self.value=self.fileValue.getName()
                else:
                    self.fileValue=self.fileList.getFile(srcVal.value)
                    self.value=srcVal.value
            else:
                self.value=srcVal.value
        else:
            self.updated=srcVal.updated
            if self.basetype == vtype.listType:
                for name, item in srcVal.value.iteritems():
                    if not self.type.hasMember(name):
                        raise ActiveValError("Unknown member item '%s'"%name)
                    # make the value if it doesn't exist
                    if not self.value.has_key(name):
                        self.value[name]=self._create(None, 
                                                      self.type.getMember(name),
                                                      members[name], name)
                    self.value[name].update(item, newSeqNr)
            elif self.basetype == vtype.dictType:
                for name, item in srcVal.value:
                    if not self.value.has_key(name):
                        self.value[name]=self._create(None,
                                                      self.type.getMembers(),
                                                      name)
                    self.value[name].update(item, newSeqNr)
            elif self.basetype == vtype.arrayType:
                i=0
                if not isinstance(self.value, list):
                    self.value=[]
                for item in srcVal.value:
                    if len(self.value) < i+1:
                        self.value.append(self._create(None, 
                                                       self.type.getMembers(), 
                                                       i))
                    self.value[i].update(item, newSeqNr)
                    i+=1
            else:
                raise ActiveValError("Unknown compound type")
        # remove previous reference, only after we know the new value
        # has added a ref (it might be the same file).
        if fileValue is not None:
            fileValue.rmRef()

    def addMember(self, name, tp, opt, const):
        """Add a member item to a list if this value is a list.
           name = the name
           tp = the member type
           opt = whether it is optional
           const = whether it should be constant."""
        if self.type.isSubtype(vtype.listType):
            self.type.addMember(name, tp, opt, const)
            self.value[name]=self._create(None, tp, name)
        else:
            raise ActiveValError("Tried to add member to non-list value")

    def acceptNewValue(self, sourceValue, sourceTag):
        """Find all newly set value of this value and any of its children that
           originate from source.
           
           sourceValue = the input value
           sourceTag = a source tag to check for (or None to accept anything)"""
        ret=False
        if ( (sourceValue.sourceTag == sourceTag) or (sourceTag is None) ):
            if sourceValue.seqNr is None:
                sourceValue.seqNr=self.seqNr
            if sourceValue.seqNr >= self.seqNr:
                self.update(sourceValue, sourceValue.seqNr, sourceTag)
                ret=True
        if isinstance(sourceValue.value, dict):
            for name, val in sourceValue.value.iteritems():
                if name in self.value:
                    rt=self.value[name].acceptNewValue(val,sourceTag)
                    ret=ret or rt
                else:
                    # only check the direct descendants
                    if ( (val.sourceTag == sourceTag) or (sourceTag is None) ):
                        self.value[name]=self._create(None, 
                                                      self.type.getMember(name),
                                                      members[name], name)
                        ret=ret or self.value[name].acceptNewValue(val,
                                                                   sourceTag)
        elif isinstance(self.value, list):
            i=0
            for val in sourceValue.value:
                if i+1 < len(self.value):
                    ret=ret or self.value[i].acceptNewValue(val, sourceTag)
                else:
                    # only check the direct descendants
                    if ( (val.sourceTag == sourceTag) or (sourceTag is None) ):
                        self.value.append(self._create(None, 
                                                      self.type.getMember(name),
                                                      members[name], name))
                        rt=self.value[i].acceptNewValue(val, sourceTag)
                        ret=ret or rt
                i+=1
        return ret

    def findListeners(self, listeners, omitSelf=None):
        """Find all listeners on this value and all its subvalues. 
           listeners = a (usually empty) list to add listeners to
           omitSelf = an optional listener to omit."""
        self._findChildListeners(listeners, omitSelf)
        if self.parent is not None:
            self.parent._findParentListeners(listeners, omitSelf)
    def _findChildListeners(self, listlist, omitSelf):
        """Helper function for findListeners()."""
        if (self.listener is not None) and (self.listener!=omitSelf):
            listlist.append(self.listener)
        if isinstance(self.value, dict):
            for val in self.value.itervalues():
                val._findChildListeners(listlist, omitSelf)
        elif isinstance(self.value, list):
            for val in self.value:
                val._findChildListeners(listlist, omitSelf)
    def _findParentListeners(self, listlist, omitSelf):
        """Helper function for findListeners()."""
        if (self.listener is not None) and (self.listener!=omitSelf):
            listlist.append(self.listener)
        if self.parent is not None:
            self.parent._findParentListeners(listlist, omitSelf)

    def propagate(self, sourceTag, seqNr):
        """Find all listeners associated with this value and update their 
           values, calling propagate() on their associated listeners.
           
           sourceTag = a source tag that handleInput matches to check
                       for input from a single source
           seqNr = a sequence number to check for updated inputs."""
        if self.parent is not None:
            self.parent._propagateParent(sourceTag, seqNr)
        self._propagateChild(sourceTag, seqNr)
    def _propagateParent(self, sourceTag, seqNr):
        """Helper function for propagateListenerOutput()"""
        if self.listener is not None:
            self.listener.propagate(sourceTag, seqNr)
        if self.parent is not None:
            self.parent._propagateParent(sourceTag, seqNr)
    def _propagateChild(self, sourceTag, seqNr):
        """Helper function for propagateListenerOutput()"""
        if self.listener is not None:
            self.listener.propagate(sourceTag, seqNr)
        if isinstance(self.value, dict):
            for val in self.value.itervalues():
                val._propagateChild(sourceTag, seqNr)
        elif isinstance(self.value, list):
            for val in self.value:
                val._propagateChild(sourceTag, seqNr)

    def notifyListeners(self, sourceTag, seqNr):
        """Find all listeners' destinations associated with this value and call 
           notify() on them. This in turn calls handleNewInput() on the 
           activeInstances that the acps belong to."""
        if self.parent is not None:
            self.parent._notifyParentListeners(sourceTag, seqNr)
        self._notifyChildListeners(sourceTag, seqNr)
    def _notifyParentListeners(self, sourceTag, seqNr):
        """Helper function for notifyListeners()"""
        if self.listener is not None:
            self.listener.notifyDestinations(sourceTag, seqNr)
        if self.parent is not None:
            self.parent._notifyParentListeners(sourceTag, seqNr)
    def _notifyChildListeners(self, sourceTag, seqNr):
        """Helper function for notifyListeners()"""
        if self.listener is not None:
            self.listener.notifyDestinations(sourceTag, seqNr)
        if isinstance(self.value, dict):
            for val in self.value.itervalues():
                val._notifyChildListeners(sourceTag, seqNr)
        elif isinstance(self.value, list):
            for val in self.value:
                val._notifyChildListeners(sourceTag, seqNr)

