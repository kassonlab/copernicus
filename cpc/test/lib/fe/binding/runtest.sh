#!/bin/sh

# check whether all input files will be available:
if [ ! -e cpc/test/lib/fe/conf.gro ]; then
    echo "This test script must be run from within the copernicus base directory"
    exit 1
fi

# start the project
./cpcc start test
# import the free energy module
./cpcc import fe
# add the function instance
./cpcc instance fe::binding fe
# activate the function instance
./cpcc activate


# start a transaction: all the 'set' and 'connect' commands following this
# will be executed as one atomic operation upon the cpcc commit command.
./cpcc transact

./cpcc set fe:in.ligand_name  ethanol
./cpcc set fe:in.receptor_name  ethanol2

# bound state
./cpcc set-file fe:in.grompp_bound.top cpc/test/lib/fe/binding/bound/topol.top
./cpcc set-file fe:in.grompp_bound.include[0]  cpc/test/lib/fe/binding/bound/ana.itp
./cpcc set-file fe:in.grompp_bound.include[1]  cpc/test/lib/fe/binding/bound/ana2.itp
./cpcc set-file fe:in.grompp_bound.mdp cpc/test/lib/fe/binding/bound/grompp.mdp
./cpcc set-file fe:in.grompp_bound.ndx  cpc/test/lib/fe/binding/bound/index.ndx

./cpcc set-file fe:in.conf_bound cpc/test/lib/fe/binding/bound/conf.gro

./cpcc set fe:in.restraints_bound[0].resname ethanol2
./cpcc set fe:in.restraints_bound[0].pos.x 0
./cpcc set fe:in.restraints_bound[0].pos.y 0
./cpcc set fe:in.restraints_bound[0].pos.z 0
./cpcc set fe:in.restraints_bound[0].strength 1000

# solvated state
./cpcc set-file fe:in.grompp_solv.top cpc/test/lib/fe/binding/solv/topol.top
./cpcc set-file fe:in.grompp_solv.include[0]  cpc/test/lib/fe/binding/solv/ana.itp
./cpcc set-file fe:in.grompp_solv.mdp cpc/test/lib/fe/binding/solv/grompp.mdp

./cpcc set-file fe:in.conf_solv cpc/test/lib/fe/binding/solv/conf.gro


./cpcc set fe:in.solvation_relaxation_time 1000
./cpcc set fe:in.binding_relaxation_time 2000
./cpcc set fe:in.precision 2


# and commit this set of updates
./cpcc commit


