#!/bin/sh

# check whether all input files will be available:
if [ ! -e test/lib/gromacs/trjconv/traj.xtc ]; then
    echo "This test script must be run from within the copernicus base directory"
    exit 1
fi

# start the project
./cpcc start test
# import the gromacs module with grompp and mdrun functions
./cpcc import gromacs
# add the grompp and mdrun function instances
./cpcc instance gromacs::trjconv_split trjconv_split
# activate the function instance
./cpcc activate


# start a transaction: all the 'set' and 'connect' commands following this
# will be executed as one atomic operation upon the cpcc commit command.
./cpcc transact


./cpcc set-file trjconv_split:in.tpr test/lib/gromacs/trjconv/topol.tpr
./cpcc set-file trjconv_split:in.traj test/lib/gromacs/trjconv/traj.xtc
./cpcc set trjconv_split:in.center 'RNA'
./cpcc set trjconv_split:in.pbc 'mol'
./cpcc set trjconv_split:in.ur 'compact'
#./cpcc set trjconv:in.fit_type 'rot+trans'


# and commit this set of updates
./cpcc commit


#./cpcc get tune:out.resources
