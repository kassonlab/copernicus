#!/usr/bin/python
# Write the initial topology file for restrained simulations in swarm free energy calculations
# Grant Rotskoff, 11 July 2012
# Rewritten by Bjorn Wesen in June 2014

# This function can do two things - either get a start and end config and associated xvg's, and then interpolate 
# n states between them and write out to .itp files, or get a whole array of configs, extract dihedrals from them
# without interpolation and write to the same .itp files.

# Note: the start/end xvg's can be created from the conf's by g_rama -s topol.tpr -f a.gro -o a.xvg, but we don't
# do it for that mode here in the script, for the case where the user might want to modify the dihedrals for the
# start and end without updating the actual configs (I'm not sure this use-case is relevant at all, if it isn't, we can
# simply remove the start/end_xvg inputs)

# This file is part of Copernicus
# http://www.copernicus-computing.org/
# 
# Copyright (C) 2011-2015, Sander Pronk, Iman Pouya, Grant Rotskoff, Bjorn Wesen, Erik Lindahl and others.
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
import re
import random
import os
from subprocess import Popen
import argparse
import res_selection
import readxvg

from molecule import molecule
#import cpc.dataflow
#from cpc.dataflow import FileValue
from cpc.lib.gromacs import cmds

# If initial_confs is None or zero length, use start/end etc to interpolate, otherwise use the structures in initial_confs
#
# Note: if initial_confs are given, they should include the start and end configs as well (the complete string)

def write_restraints(inp, initial_confs, start, end, start_xvg, end_xvg, tpr, top, includes, n, ndx_file, Nchains):
    cmdnames = cmds.GromacsCommands()
    # Get the atoms involved with the residues to use for dihedrals (might be more than one atom in the index
    # per residue, since it's probably generated by make_ndx)
    ndx_atoms = res_selection.read_ndx(ndx_file)
    # Map them to each affected residue so we just get the residue numbers back
    selection = res_selection.res_select(start, ndx_atoms)

    n = int(n)  # number of points in the string, including start and end point

    use_interpolation = False

    if initial_confs is None or len(initial_confs) == 0:
        use_interpolation = True
        # Read the starting and ending dihedrals for later interpolation
        startpts = readxvg.readxvg(start_xvg, selection)
        endpts = readxvg.readxvg(end_xvg, selection)
    else:
        # Have to generate the dihedrals ourselves from the given initial structures
        # Note: when we get an initial_confs[] array, we use it for all points and 
        # the start/end input parameters are completely ignored
        # TODO: assert that len(initial_confs) == n otherwise?

        ramaprocs = {}

        # Run g_rama (in parallel) on each structure and output to a temporary .xvg
        FNULL = open(os.devnull, 'w') # dont generate spam from g_rama 
        for i in range(n):
            # TODO: check for and use g_rama_mpi.. like everywhere else
            cmd = cmdnames.rama.split() + ['-f', initial_confs[i], '-s', tpr,
                                           '-o', '0%3d.xvg' % i]
            ramaprocs[i] = Popen(cmd, stdout=FNULL, stderr=FNULL)

        # Go through the output from the rama sub-processes and read the xvg outputs

        stringpts = {}  # Will have 4 levels: stringpoint, residue, chain, phi/psi value

        for i in range(n):
            # Start array indexed by residue
            xvg_i = os.path.join(inp.getOutputDir(), '0%3d.xvg' % i)
            # Make sure the corresponding g_rama task has ended
            ramaprocs[i].communicate()
            # Read back and parse like for the start/end_xvg above
            stringpts[i] = readxvg.readxvg(xvg_i, selection)

    # Rewrite the topology to include the res itp files instead of the original per-chain itps (if any)
    # There will be one topol_x.top per string point

    sys.stderr.write('%s' % includes)
    for k in range(n):
        with open(top) as in_topf:
            in_top = in_topf.read()       
            for mol in range(Nchains):
                if len(includes) > 0:
                    includename = includes[mol].split('/')[-1]
                    in_top = re.sub(includename, 'res_%d_chain_%d.itp' % (k, mol), in_top)
            with open('topol_%d.top' % k,'w') as out_top:
                # sys.stderr.write('%s'%in_top)
                out_top.write(in_top)   

    # Generate/copy and write-out the dihedrals for each point
    for k in range(n):
        for mol in range(Nchains):
            # TODO: use with statement for restraint_itp as well
            restraint_itp = open('res_%d_chain_%d.itp' % (k, mol), 'w')
            if Nchains > 1:
                with open(includes[mol]) as moltop_f:
                    moltop = moltop_f.read()
                    restraint_itp.write(moltop)
            # write the initial part of the topology file
            # Note: gromacs 4.6+ required
            restraint_itp.write("[ dihedral_restraints ]\n")
            restraint_itp.write("; ai   aj   ak   al  type phi  dphi  kfac\n")
            if len(includes) > 0:
                protein = molecule(includes[mol])
                # replace the chain names with the chain names
            else:
                with open('topol_%d.top' % k, 'w') as out_top:
                    protein = molecule(top)
                    with open(top,'r') as in_itp_f:
                        in_itp = in_itp_f.read().split('; Include Position restraint file')
                        out_top.write(in_itp[0])
                        out_top.write('#include "res_%d_chain_%d.itp"\n' % (k, mol))
                        out_top.write(in_itp[1])

            # Create a lookup-table for the protein topology that maps residue to dihedrally relevant
            # backbone atom indices for N, CA and C.

            dih_atoms = {}

            for a in protein:
                if (a.atomname == 'CA' or a.atomname == 'N' or a.atomname == 'C'):
                    try:
                        dih_atoms[a.resnr][a.atomname] = a.atomnr;
                    except KeyError:
                        dih_atoms[a.resnr] = { a.atomname: a.atomnr }

            # Use the lookup-table built above and get the dihedral specification atoms needed for each
            # residue in the selection. This is O(n) in residues, thanks to the dih_atoms table.

            for r in selection:
                # Get the atom numbers to use for the phi and psi dihedrals (4 atoms each)

                # phi is C on the previous residue, and N, CA, C on this
                phi = [ dih_atoms[r - 1]['C'], dih_atoms[r]['N'], dih_atoms[r]['CA'], dih_atoms[r]['C'] ]
                
                # psi is N, CA and C on this residue and N on the next
                psi = [ dih_atoms[r]['N'], dih_atoms[r]['CA'], dih_atoms[r]['C'], dih_atoms[r + 1]['N'] ]

                # Write phi, psi angles and the associated k factor into a row in the restraint file
                # Note: in the Gromacs 4.6+ format, the k-factor is here. Before, it was in the .mdp as
                # dihre_fc.
                # Also see reparametrize.py

                if use_interpolation:
                    # k is from 0 to n-1, so map it so we get a factor from 0 to 1
                    phi_val = startpts[r][mol][0] + k * (endpts[r][mol][0] - startpts[r][mol][0]) / (n - 1)
                    psi_val = startpts[r][mol][1] + k * (endpts[r][mol][1] - startpts[r][mol][1]) / (n - 1)
                else:
                    # Use the values extracted from the initial_confs[] structures above
                    phi_val = stringpts[k][r][mol][0]
                    psi_val = stringpts[k][r][mol][1]

                # Since we need different force constants in different stages, we need to put
                # a searchable placeholder in the file here and replace it later. KFAC is normally 
                # a %8.4f number.
                restraint_itp.write("%5d%5d%5d%5d%5d %8.4f%5d  KFAC\n"
                                    %(phi[0], phi[1], phi[2], phi[3], 1, phi_val, 0))
                restraint_itp.write("%5d%5d%5d%5d%5d %8.4f%5d  KFAC\n"
                                    %(psi[0], psi[1], psi[2], psi[3], 1, psi_val, 0))

            restraint_itp.close()


