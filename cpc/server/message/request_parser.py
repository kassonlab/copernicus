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


try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


import sys
import traceback
import logging


import server_command 
import trackingcmd 
import workercmd
import projectcmd
import cpc.network.server_response
import cpc.util


log=logging.getLogger('cpc.server.request_parser')


class ServerCommandError(cpc.util.CpcError):
    pass

class ServerCommandList(object):
    """An object list that takes a request and runs the right server command 
       object's request handler."""
    def __init__(self):
        self.cmds=dict()

    def add(self, cmd):
        name=cmd.getRequestString()
        self.cmds[name]=cmd

    def run(self, request, response, serverState):
        """Run a request by instantiating the right object and calling
           run() on it."""
        cmd=request.getCmd()
        if cmd in self.cmds:
            self.cmds[cmd].run(serverState, request, response)
        else:
            raise ServerCommandError("Unknown command %s"%cmd)

# these are the server commands that the secure server may run:
scSecureList=ServerCommandList()
scSecureList.add(server_command.SCStop())
scSecureList.add(server_command.SCSaveState())
scSecureList.add(server_command.SCTestServer())
scSecureList.add(server_command.SCNetworkTopology())
scSecureList.add(server_command.SCNetworkTopologyUpdate())
scSecureList.add(workercmd.SCWorkerReady())  
scSecureList.add(workercmd.SCCommandFinished())
scSecureList.add(workercmd.SCCommandFinishedForward())  
scSecureList.add(workercmd.SCCommandFailed())  
scSecureList.add(workercmd.SCWorkerHeartbeat())
scSecureList.add(workercmd.SCWorkerFailed())  
scSecureList.add(server_command.SCListServerItems())
scSecureList.add(server_command.SCReadConf())
scSecureList.add(server_command.ScAddNode())
scSecureList.add(server_command.ScAddNodeRequest())
scSecureList.add(server_command.ScListNodes())   
scSecureList.add(server_command.ScListNodeConnectionRequests())
scSecureList.add(server_command.ScListSentNodeConnectionRequests())
scSecureList.add(server_command.ScGrantNodeConnection()) 
scSecureList.add(server_command.ScGrantAllNodeConnections())    
scSecureList.add(server_command.ScChangeNodePriority()) 
scSecureList.add(trackingcmd.SCPullAsset())
scSecureList.add(trackingcmd.SCClearAsset())
# requests for dataflow
scSecureList.add(projectcmd.SCProjects())
scSecureList.add(projectcmd.SCProjectStart())
scSecureList.add(projectcmd.SCProjectDelete())
scSecureList.add(projectcmd.SCProjectSetDefault())
scSecureList.add(projectcmd.SCProjectActivate())
scSecureList.add(projectcmd.SCProjectUpload())
scSecureList.add(projectcmd.SCProjectList())
scSecureList.add(projectcmd.SCProjectInfo())
scSecureList.add(projectcmd.SCProjectImport())
scSecureList.add(projectcmd.SCProjectAddInstance())
scSecureList.add(projectcmd.SCProjectConnect())
scSecureList.add(projectcmd.SCProjectGraph())
scSecureList.add(projectcmd.SCProjectSet())
scSecureList.add(projectcmd.SCProjectGet())
scSecureList.add(projectcmd.SCProjectCommit())
scSecureList.add(projectcmd.SCProjectLog())


# these are the server commands that may be run by the unencrypted HTTP server
scInsecureList=ServerCommandList()
scInsecureList.add(server_command.ScAddNodeRequest())
scInsecureList.add(server_command.ScAddNodeAccepted())
scInsecureList.add(server_command.ScAddClientRequest())

class RequestParser(object):
    '''
        input : cpc.util.Request
    '''
    def __init__(self, serverState, request, response):
        self.cmd=None
        self.cmdList=[]
        self.request = request
        self.serverState=serverState
        self.response=response

    
    def getCmdList(self):
        return self.cmdList

'''
    input : cpc.util.Request
'''
def parse(scList, request, serverState, response=None):
    """Parse a request and the server state and return a result string. 
       May not cause an exception; may alter the server state."""
            
    if response is None:
        response = cpc.network.server_response.ServerResponse()
    try:                        
        scList.run(request, response, serverState)
    except cpc.util.CpcError as e:
        response.add(("%s"%e.__str__()), status="ERROR")
        log.error(e.__str__())
    except: 
        fo=StringIO()
        traceback.print_exception(sys.exc_info()[0], sys.exc_info()[1],
                                  sys.exc_info()[2], file=fo)
        errmsg="Server exception: %s"%(fo.getvalue())
        response.add(errmsg, status="ERROR")
        log.error(errmsg)
    return response

       
