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


import sys
import os
import re
import os.path
import shutil
import shlex
import glob
import stat
import subprocess
import logging
import time


log=logging.getLogger('cpc.lib.grompp')


from cpc.dataflow import Value
from cpc.dataflow import FileValue
from cpc.dataflow import IntValue
from cpc.dataflow import FloatValue
from cpc.dataflow import StringValue
from cpc.dataflow import Resources
import cpc.server.command
import cpc.util

import tune
import iterate

class GromacsError(cpc.util.CpcError):
    pass


def procSettings(inp, outMdpDir):
    """Process settings into a new mdp file, or return the old mdp file if
       there are no additional settings."""
    mdpfile=inp.getInput('mdp')
    if ( inp.hasInput('settings') and len(inp.getInput('settings'))>0 ):
        repl=dict()
        if inp.hasInput('settings'):
            settings=inp.getInput('settings')
            for setting in settings:
                if ("name" in setting.value) and ("value" in setting.value):
                    val = setting.value["value"].value
                    name = setting.value["name"].value
                    name = name.strip().replace('-', '_').lower()
                    repl[name] = val
        # now set the gen_vel option
        outMdpName=os.path.join(outMdpDir, "grompp.mdp")
        outf=open(outMdpName, "w")
        inf=open(mdpfile, "r")
        for line in inf:
            sp=line.split('=')
            if len(sp) == 2:
                key=sp[0].strip().replace('-', '_').lower()
                if key in repl:
                    outf.write('%s = %s\n'%(key, str(repl[key])))
                    del repl[key]
                else:
                    outf.write(line)
        # and write our remaining options 
        for key, value in repl.iteritems():
            outf.write('%s = %s\n'%(key, str(value)))
        outf.close()
        return outMdpName
    else:
        return mdpfile



def grompp(inp):
    if inp.testing(): 
        # if there are no inputs, we're testing wheter the command can run
        cpc.util.plugin.testCommand("grompp -version")
        return 

    pers=cpc.dataflow.Persistence(os.path.join(inp.persistentDir,
                                               "persistent.dat"))
    fo=inp.getFunctionOutput()
    if not (inp.getInputValue('conf').isUpdated() or 
            inp.getInputValue('top').isUpdated() or 
            inp.getInputValue('include').isUpdated() or 
            inp.getInputValue('settings').isUpdated() or
            inp.getInputValue('ndx').isUpdated()):
        if pers.get('init') is not None:
            return fo
    if pers.get('init') is not None:
        log.debug("conf: %s"%(inp.getInputValue('conf').isUpdated()))
        log.debug("top: %s"%(inp.getInputValue('top').isUpdated()))
        log.debug("include: %s"%(inp.getInputValue('include').isUpdated()))
        log.debug("settings: %s"%(inp.getInputValue('settings').isUpdated()))
        log.debug("ndx: %s"%(inp.getInputValue('ndx').isUpdated()))

    pers.set('init', 1)
    mdpfile=procSettings(inp, inp.outputDir)
    # copy the topology and include files 
    topfile=os.path.join(inp.outputDir, 'topol.top')
    shutil.copy(inp.getInput('top'), topfile)
    incl=inp.getInput('include')
    if incl is not None and len(incl)>0:
        for i in range(len(incl)):
            filename=inp.getInput('include[%d]'%i)
            if filename is not None:
                # same name, but in one directory.
                nname=os.path.join(inp.outputDir, os.path.split(filename)[1])
                shutil.copy(filename, nname)
    # and execute grompp
    cmdlist=[ "grompp", "-f", mdpfile,
              "-quiet",
              "-c", inp.getInput('conf'),
              "-p", 'topol.top', # we made sure it's there
              "-o", "topol.tpr" ]
    if inp.hasInput('ndx'):
        cmdlist.append('-n')
        cmdlist.append(inp.getInput('ndx'))
    # TODO: symlink all the auxiliary files into the run dir
    stdoutfn=os.path.join(inp.outputDir, "stdout")
    stdoutf=open(stdoutfn,"w")
    stdoutf.write("%s\n"%time.strftime("%a, %d %b %Y %H:%M:%S"))
    stdoutf.write("%f\n"%time.time())
    #stdoutf=open(os.path.join(inp.outputDir, "stderr"),"w")
    proc=subprocess.Popen(cmdlist, 
                          stdin=None,
                          stdout=stdoutf,
                          stderr=subprocess.STDOUT,
                          cwd=inp.outputDir)
    proc.communicate(None)
    stdoutf.close()
    if proc.returncode != 0:
        raise GromacsError("Error running grompp: %s"%
                           (open(stdoutfn,'r').read()))
    fo.setOut('stdout', FileValue(stdoutfn))
    fo.setOut('tpr', FileValue(os.path.join(inp.outputDir, "topol.tpr")))
    pers.write()
    return fo



def merge_mdp(inp):
    if inp.testing():
        # if there are no inputs, we're testing wheter the command can run
        return
    fo=inp.getFunctionOutput()
    mdpfile=procSettings(inp, inp.outputDir)
    fo.setOut('mdp', FileValue(mdpfile))
    return fo

def extract_mdp(inp):
    if inp.testing():
        # if there are no inputs, we're testing wheter the command can run
        return
    fo=inp.getFunctionOutput()
    keyFind=inp.getInput('name')
    keyFind=keyFind.strip().replace('-', '_').lower()
    setVal=None
    mdpfile=inp.getInput('mdp')
    #if ( inp.hasInput('settings') and len(inp.getInput('settings'))>0 ):
    repl=dict()
    if inp.hasInput('settings'):
        settings=inp.getInput('settings')
        for setting in settings:
            if ("name" in setting.value) and ("value" in setting.value):
                val = setting.value["value"].value
                name = setting.value["name"].value
                name = name.strip().replace('-', '_').lower()
                if name == keyFind:
                    setVal=val
    if setVal is None:
        #outMdpName=os.path.join(outMdpDir, "grompp.mdp")
        #outf=open(outMdpName, "w")
        inf=open(mdpfile, "r")
        for line in inf:
            sp=line.split('=')
            if len(sp) == 2:
                key=sp[0].strip().replace('-', '_').lower()
                if key==keyFind:
                    setVal=sp[1].strip()
    if setVal is not None:
        fo.setOut('value', StringValue(setVal))
    return fo

def tune_fn(inp):
    if inp.testing():
        # if there are no inputs, we're testing wheter the command can run
        #cpc.util.plugin.testCommand("grompp -version")
        #cpc.util.plugin.testCommand("mdrun -version")
        return
    fo=inp.getFunctionOutput()
    persDir=inp.getPersistentDir()
    mdpfile=procSettings(inp, inp.outputDir)
    # copy the topology and include files 
    topfile=os.path.join(inp.outputDir, 'topol.top')
    shutil.copy(inp.getInput('top'), topfile)
    incl=inp.getInput('include')
    if incl is not None and len(incl)>0:
        for i in range(len(incl)):
            filename=inp.getInput('include[%d]'%i)
            if filename is not None:
                # same name, but in one directory.
                nname=os.path.join(inp.outputDir, os.path.split(filename)[1])
                shutil.copy(filename, nname)
    # and execute grompp
    cmdlist=[ "grompp", "-f", mdpfile,
              "-quiet",
              "-c", inp.getInput('conf'),
              "-p", 'topol.top', # we made sure it's there
              "-o", "topol.tpr" ]
    if inp.hasInput('ndx'):
        cmdlist.append('-n')
        cmdlist.append(inp.getInput('ndx'))
    proc=subprocess.Popen(cmdlist, 
                          stdin=None,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          cwd=inp.outputDir)
    (stdo, stde) = proc.communicate(None)
    if proc.returncode != 0:
        raise GromacsError("Error running grompp: %s, %s"%
                           (stdo, stde))
    rsrc=Resources()
    tune.tune(rsrc, inp.getInput('conf'), 
              os.path.join(inp.outputDir, 'topol.tpr'), persDir)
    fo.setOut('mdp', FileValue(mdpfile))
    fo.setOut('resources', rsrc.setOutputValue())
    return fo

def grompp_multi(inp):
    if inp.testing():
    # if there are no inputs, we're testing wheter the command can run
        cpc.util.plugin.testCommand("grompp -version")
        return

    pers=cpc.dataflow.Persistence(os.path.join(inp.persistentDir,
                                               "persistent.dat"))

    inputs = ['mdp','top','conf', 'ndx', 'settings', 'include']
    outputs = [ 'tpr' ]
    running=0
    if(pers.get("running")):
        running=pers.get("running")
    it=iterate.iterations(inp, inputs, outputs, pers)
    out=inp.getFunctionOutput()
    for i in range(running, it.getN()):
        instName="grompp_%d"%i
        out.addInstance(instName, "grompp")
        it.connect(out, i, instName)
        out.addConnection("%s:out.tpr"%instName, "self:ext_out.tpr[%d]"%i)
        running+=1
    pers.set("running", running)
    pers.write()
    return out




def mdrun_multi(inp):
    if inp.testing():
        # if there are no inputs, we're testing wheter the command can run
        cpc.util.plugin.testCommand("trjcat -version")
        cpc.util.plugin.testCommand("eneconv -version")
        cpc.util.plugin.testCommand("gmxdump -version")
        return

    pers=cpc.dataflow.Persistence(os.path.join(inp.persistentDir,
                                               "persistent.dat"))

    inputs = ['tpr','priority','cmdline_options','resources']
    outputs = [ 'conf', 'xtc', 'trr', 'edr' ]
    running=0
    if(pers.get("running")):
        running=pers.get("running")
    it=iterate.iterations(inp, inputs, outputs, pers)
    out=inp.getFunctionOutput()
    for i in range(running, it.getN()):
        instName="mdrun_%d"%i
        out.addInstance(instName, "mdrun")
        it.connect(out, i, instName)
        running+=1
    pers.set("running", running)
    pers.write()
    return out


def grompp_mdrun_multi(inp):
    if inp.testing():
    # if there are no inputs, we're testing wheter the command can run
        cpc.util.plugin.testCommand("grompp -version")
        return

    pers=cpc.dataflow.Persistence(os.path.join(inp.persistentDir,
                                               "persistent.dat"))

    grompp_inputs = ['mdp','top','conf', 'ndx', 'settings', 'include' ]
    mdrun_inputs = [ 'priority', 'cmdline_options', 'resources']
    inputs = grompp_inputs + mdrun_inputs
    grompp_outputs = [ 'tpr' ]
    mdrun_outputs = [ 'conf', 'xtc', 'trr', 'edr' ]
    outputs = grompp_outputs + mdrun_outputs
    running=0
    if(pers.get("running")):
        running=pers.get("running")
    it=iterate.iterations(inp, inputs, outputs, pers)
    out=inp.getFunctionOutput()
    for i in range(running, it.getN()):
        gromppInstName="grompp_%d"%i
        mdrunInstName="mdrun_%d"%i
        out.addInstance(gromppInstName, "grompp")
        out.addInstance(mdrunInstName, "mdrun")
        out.addConnection('%s:out.tpr'%gromppInstName, 
                          '%s:in.tpr'%mdrunInstName)
        it.connectOnly(grompp_inputs, grompp_outputs, out, i, gromppInstName)
        it.connectOnly(mdrun_inputs, mdrun_outputs, out, i, mdrunInstName)
        running+=1
    pers.set("running", running)
    pers.write()
    return out
