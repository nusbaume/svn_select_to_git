#! /bin/bash

curr_dir="$( dirname ${0} )"
prog_dir="$( dirname $( cd ${curr_dir}; pwd -P ) )"
svn2git="${prog_dir}/svn_select_to_git.py"
name_table="${prog_dir}/CAM_name_table.txt"
svnroot="https://svn-ccsm-models.cgd.ucar.edu/cam1"
trunk="${svnroot}/trunk"
ttags="${svnroot}/trunk_tags"
trunk_commits="89219:91395"
isotopes="${svnroot}/branches/geotrace3_cac_atmonly"
geobranch="geotrace3_cac_atmonly"
geotags="${svnroot}/branch_tags/geotrace3_cac_atmonly_tags"
geo_commits="90462:91092"
release="${svnroot}/branches/cam_cesm2_1_rel"
relbranch="cam_cesm2_1_rel"
reltags="${svnroot}/release_tags"
rel_commits="90462:91092"
if [ ! -x "${svn2git}" ]; then
  echo "Cannot find executable, '${svn2git}'"
  exit 1
else
  echo "Running ${svn2git}"
fi

if [ -z "${USER}" ]; then
  echo "Environment variable, USER, needs to be set"
  exit 1
fi
if [ -d "/scratch/cluster/${USER}" ]; then
  scratch="/scratch/cluster/${USER}"
elif [ -d "/scratch/${USER}" ]; then
  scratch="/scratch/${USER}"
elif [ -d "/glade/scratch/${USER}" ]; then
  scratch="/glade/scratch/${USER}"
elif [ -n "${HOME}" -a -d "${HOME}/scratch/${USER}" ]; then
  scratch="${HOME}/scratch/${USER}"
else
  echo "Cannot find scratch dir"
  exit 1
fi

doerr() {
  if [ $1 -ne 0 ]; then
    echo "Error ${1}, aborting"
    exit $1
  fi
}

cd ${scratch}
svndir="${scratch}/cam_svn"
gitdir="${scratch}/cam_git"
#rm -rf ${svndir} ${gitdir}
fixargs="--author-table ${name_table}"
# First, setup the trunk
args="${fixargs} --tags ${ttags} --rev ${trunk_commits}"
args="${args} ${svndir} ${gitdir} ${trunk}"
echo "Executing: ${svn2git} ${args}"
${svn2git} ${args}
doerr $?
# Next, the isotope branch
args="${fixargs} --branch ${geobranch} --rev ${geo_commits} --tags ${geotags}"
args="${args} ${svndir} ${gitdir} ${isotopes}"
echo "Executing: ${svn2git} ${args}"
${svn2git} ${args}
doerr $?
# The release tags
args="${fixargs} --branch ${relbranch} --tags ${reltags} --rev ${rel_commits}"
args="${args} ${svndir} ${gitdir} ${release}"
echo "Executing: ${svn2git} ${args}"
${svn2git} ${args}
doerr $?
cd ${gitdir}
doerr $?
git status
doerr $?
git branch
doerr $?
