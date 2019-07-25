#!/usr/bin/env python

from __future__ import print_function
import sys
import os
import os.path
import subprocess
import inspect
import re
import shutil
import argparse
import filecmp

## Important paths
thisFile = os.path.realpath(inspect.getfile(inspect.currentframe()))
currDir = os.path.dirname(thisFile)

## Boilerplate files
cam_copy_files = [".config_files.xml", ".gitignore", "TGIT.sh"]

## Regular expression for source files
cby_str="Committed by"
reRevis = re.compile(r"^r(\d+)\s+\|\s+([^|]+)\|\s+([^|]+)\|\s+(\d+)\s+lines?$")
reCommit = re.compile(r"^commit ([0-9a-f]+)$")
reImport = re.compile(r"^\s*Imported from .*@([\d]+)$")
reAuthor = re.compile(r"^\s*{} (.+)\s+at\s+([0-9][0-9\s:+-]+)$".format(cby_str))
reLastChange = re.compile(r"^Last Changed Rev:\s+(\d+)$")
reGitHash = re.compile("\A([a-fA-F0-9]+)\Z")
reRemoteBranch = re.compile("\s*origin/(\S+)")

##############################
###
### Helper Functions
###
##############################

def perr(errmsg, retcode=1):
    "Utility to print an error message and exit"
    print(errmsg, file=sys.stderr)
    exit(retcode)
# End perr

def quitOnFail(retcode, caller, command=None):
    "Utility to quit execution on a non-zero return code"
    if retcode != 0:
        errmsg = "{} failed with return code {}".format(caller, retcode)
        if command is not None:
            errmsg = errmsg + os.linesep + " ".join(command)
        # End if
        perr(errmsg, retcode)
    # End if
# End quitOnFail

def checkOutput(commands, verbose=False):
    "Try a command line and return the output on success (None on failure)"
    try:
        outstr = subprocess.check_output(commands, stderr=open("/dev/null", mode='w'))
    except OSError as e:
        print("Execution of '{}' failed:".format(' '.join(commands)),
              file=sys.stderr)
        print("{}".format(e), file=sys.stderr)
        exit(1)
    except ValueError as e:
        if (verbose):
            print("ValueError in '{}':".format(' '.join(commands)),
              file=sys.stderr)
            print("{}".format(e), file=sys.stderr)
            # End if
            outstr = None
    except subprocess.CalledProcessError as e:
        if (verbose):
            print("CalledProcessError in '{}':".format(' '.join(commands)),
              file=sys.stderr)
            print("{}".format(e), file=sys.stderr)
        # End if
        outstr = None
    # End of try
    return outstr
# End of checkOutput

def scall(commands):
    "Try a command line and return the return value (-1 on failure)"
    try:
        retcode = subprocess.check_call(commands)
    except OSError as e:
        print("Execution of '{}' failed".format(' '.join(commands)),
              file=sys.stderr)
        print("{}".format(e), file=sys.stderr)
        retcode = -1
    except ValueError as e:
        print("ValueError in '{}'".format(' '.join(commands)), file=sys.stderr)
        print("{}".format(e), file=sys.stderr)
        retcode = -1
    except subprocess.CalledProcessError as e:
        print("CalledProcessError in '{}'".format(' '.join(commands)),
              file=sys.stderr)
        print("{}".format(e), file=sys.stderr)
        retcode = -1
        # End of try
    return retcode
# End of scall

def retcall(commands):
    "Try a command line and return the return value. Suppress normal output"
    FNULL = open(os.devnull, 'w')
    try:
        retcode = subprocess.call(commands, stdout=FNULL, stderr=subprocess.STDOUT)
    except OSError as e:
        print("Execution of '{}' failed".format(' '.join(commands)),
              file=sys.stderr)
        print("{}".format(e), file=sys.stderr)
    except ValueError as e:
        print("ValueError in '{}'".format(' '.join(commands)),
              file=sys.stderr)
        print("{}".format(e), file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print("CalledProcessError in '{}'".format(' '.join(commands)),
              file=sys.stderr)
        print("{}".format(e), file=sys.stderr)
    # End of try
    return retcode
# End of retcall

def file_diff(file1, file2):
    """Return True if there is some difference between file1 and file2"""
    diff = not os.path.exists(file2)
    if not diff:
        # Check for permission or file size changes
        stat1 = os.stat(file1)
        stat2 = os.stat(file2)
        diff = stat1.st_mode != stat2.st_mode
        diff = diff or (stat1.st_size != stat2.st_size)
        diff = diff or (stat1.st_uid != stat2.st_uid)
        diff = diff or (stat1.st_gid != stat2.st_gid)
    # End if
    # Make sure the file is really the same
    diff = diff or (not filecmp.cmp(file1, file2, shallow=False))
    return diff
# End def file_diff

def file_sub_text(filename, patterns):
    """Search <filename> for a regular expression match in a key of dict,
    <patterns>, and substitute the key's value.
    """
    # First, make a backup copy of <filename>
    bkup_name = filename + '.fstbk'
    if os.path.exists(bkup_name):
        os.remove(bkup_name)
    # End if
    mode = os.stat(filename).st_mode
    os.rename(filename, bkup_name)
    # Try the substitution, restore backup on error
    try:
        with open(bkup_name, 'r') as infile:
            src_lines = infile.readlines()
        # End with
        search_res = patterns.keys()
        lines_to_skip = 0
        with open(filename, 'w') as outfile:
            for inline in src_lines:
                if lines_to_skip > 0:
                    lines_to_skip -= 1
                else:
                    for key in search_res:
                        add_lines = key[0] == '+'
                        if add_lines:
                            # Special case, add new line(s)
                            srch = key[1:]
                        else:
                            srch = key
                        # End if
                        match = re.search(srch, inline)
                        if match is not None:
                            repl = patterns[key]
                            if isinstance(repl, str):
                                # We have a match, do the substitution
                                if add_lines:
                                    outline = inline + repl
                                else:
                                    outline = re.sub(srch, repl, inline)
                                # End if
                            elif isinstance(repl, int):
                                # Just delete this line and n-1 more
                                lines_to_skip = repl - 1
                                outline = None
                            elif isinstance(repl, tuple):
                                # This should be a substitution plus a
                                # number of lines to ignore *after* this one
                                if add_lines:
                                    outline = inline + repl[0]
                                else:
                                    outline = re.sub(srch, repl[0], inline)
                                # End if
                                lines_to_skip = repl[1]
                            else:
                                outline = None # i.e., delete line
                            # End if
                            break
                        else:
                            outline = inline
                        # End if
                    # End for
                    if outline is not None:
                        outfile.write(outline)
                    # End if (else just omit line)
                # End if
            # End for
        # End with
        # Cleanup
        os.chmod(filename, mode)
        if os.path.exists(bkup_name):
            os.remove(bkup_name)
        # End if
    except Exception as e:
        print ('ERROR: {}\nAborting'.format(e))
        if os.path.exists(filename):
            os.remove(filename)
        # End if
        os.rename(bkup_name, filename)
        raise e
    # End try

def cam_svn_to_git_mods(repo_dir):
    num_changes = 0
    cconfig = os.path.join(repo_dir, 'cime_config')
    bld = os.path.join(repo_dir, 'bld')
    systest = os.path.join(repo_dir, 'test', 'system')
    # buildnml
    filename = os.path.join(cconfig, 'buildnml')
    patterns = {'"components", ?"cam",' : '',
                '+case.get_value\("RUN_REFTOD"\)' :
                '\n    testsrc = os.path.join(srcroot, "components", "cam")'
                '\n    if os.path.exists(testsrc):'
                '\n        srcroot = testsrc\n'}
    file_sub_text(filename, patterns)
    num_changes += 1
    # buildlib
    filename = os.path.join(cconfig, 'buildlib')
    patterns = {('cmd = os.path.join\(os.path.join\(srcroot, '
                 '"components", "cam",') :
                ('testpath = os.path.join(srcroot, "components", "cam")'
                 '\n        if os.path.exists(testpath):'
                 '\n            srcroot = testpath\n'
                 '\n        cmd = os.path.join(os.path.join(srcroot,')}
    file_sub_text(filename, patterns)
    # buildcpp
    filename = os.path.join(cconfig, 'buildcpp')
    patterns = {'cmd = os.path.join\(srcroot, "components", "cam", "bld", "configure"\) \+ \\\\' :
               ('testpath = os.path.join(srcroot, "components", "cam")'
                '\n    if os.path.exists(testpath):'
                '\n        srcroot = testpath\n'
                r'    cmd = os.path.join(srcroot, "bld", "configure") + \\')}
    file_sub_text(filename, patterns)
    num_changes += 1
    # config_files/definition.xml
    filename = os.path.join(bld, 'config_files', 'definition.xml')
    patterns = {'Root directory of CAM source distribution' :
                ('Root directory of CAM source distribution'
                '\n</entry>\n<entry id="cam_dir" value="">'
                 '\nRoot directory of CAM model source.')}
    file_sub_text(filename, patterns)
    num_changes += 1
    # configure
    filename = os.path.join(bld, 'configure')
    patterns = {'my \$cam_root = absolute_path\("\$cfgdir/../../.."\);' :
                (('# Check for standalone or CESM checkout\n'
                  'my $cam_root = absolute_path("$cfgdir/..");'
                  '\nmy $cam_dir = $cam_root;'
                  '\nif (! -d "$cam_root/cime") {'
                  '\n  $cam_root = absolute_path("$cfgdir/../../..");'
                  '\n}'
                  '\nif (-d "$cam_root/components/cam/src") {'
                  "\n    $cfg_ref->set('cam_root', $cam_root);"
                  '\n    $cam_dir = "$cam_root/components/cam";'
                  "\n    $cfg_ref->set('cam_dir', $cam_dir);"
                  '\n}\nelsif (-d "$cam_root/src") {'
                  "\n    $cfg_ref->set('cam_root', $cam_root);"
                  "\n    $cfg_ref->set('cam_dir', $cam_dir);"), 1),
                'contain the subdirectory components/cam/src/.' :
                ('contain the subdirectory components/cam/src/'
                 '\n** (CESM checkout) or the subdirectory src '
                 '(standalone checkout).'),
                ('\*\* It is derived from "config_dir/../../.." '
                 'where config_dir is the') :
                ('** For CESM checkouts, it is derived from '
                 '"config_dir/../../..".'
                 '\n** For CAM standalone checkouts, it is derived from'
                 '"config_dir/..",'),
                ('\*\* directory in the CAM distribution that contains '
                 'the configuration') :
                ('** where config_dir is the directory in the CAM '
                 'distribution that\n** contains the configuration scripts.'),
                'if \(-d "\$cam_root/components/cam/src"\) {' : 2,
                '\$cam_root/components/cam/src/' : '$cam_dir/src/',
                'my \$camsrcdir = "\$cam_root/components";' :
                "my $camsrcdir = $cfg_ref->get('cam_dir');",
                '\$camsrcdir/cam' : '$camsrcdir'}
    file_sub_text(filename, patterns)
    num_changes += 1

    #Regression test files:
    #---------------------
    #test_driver.sh
    filename = os.path.join(systest, 'test_driver.sh')
    patterns = {'root_dir=\"(\$\( dirname ){4}\$\{tdir\} (\)[ \"]){4}' :
               ('trial_dir="$( dirname $( dirname $( dirname $( dirname ${tdir} ) ) ) )"\n'
                '    if [ -d "${trial_dir}/cime/scripts" ]; then\n'
                '      root_dir=$trial_dir\n'
                '    else\n'
                '      root_dir="$( dirname $( dirname ${tdir} ) )"\n'
                '    fi\n'),

                'export CAM_ROOT=\\\`cd \\\\\$\{CAM_SCRIPTDIR}(/\.\.){4} ; pwd \\\`' :
               ('if [ -d "\${CAM_SCRIPTDIR}/../../components" ]; then\n'
                '        export CAM_ROOT=\`cd \${CAM_SCRIPTDIR}/../.. ; pwd \`\n'
                '    else\n'
                '        export CAM_ROOT=\`cd \${CAM_SCRIPTDIR}/../../../.. ; pwd \`\n'
                '    fi'),

                'echo \"ERROR: unable to determine script directory \"' :
               ('if [ -n "\${CAM_ROOT}"  -a  -f "\${CAM_ROOT}/test/system/test_driver.sh" ]; then\n'
                '            export CAM_SCRIPTDIR=\`cd \${CAM_ROOT}/test/system; pwd \`\n'
                '        else\n'
                '            echo \"ERROR: unable to determine script directory \"'),

                'echo \"       if initiating batch job from directory other than the one containing test_driver.sh, \"' :
                '    echo "       if initiating batch job from directory other than the one containing test_driver.sh, "',

                'echo \"       you must set the environment variable CAM_ROOT to the full path of directory containing \"' :
                '    echo "       you must set the environment variable CAM_ROOT to the full path of directory containing "',

                'echo \"       <components>. \"' :
                '    echo "       <components>. "',

                'exit 3' :
               ('    exit 3\n'
                '        fi')}
    file_sub_text(filename, patterns)
    num_changes += 1
    #TBL.sh
    filename = os.path.join(systest, 'TBL.sh') 
    patterns = {'env CAM_TESTDIR=\$\{BL_TESTDIR\} \\\\' :
               ('if [ -d "${BL_ROOT}/components/cam" ]; then\n'
                '\n'
                '            env CAM_TESTDIR=${BL_TESTDIR} \\\\'),

                '\$\{BL_ROOT\}/components/cam/test/system/TSM.sh \$1 \$2 \$3$' :
               ('${BL_ROOT}/components/cam/test/system/TSM.sh $1 $2 $3\n'
                '\n'
                '        else\n'
                '\n'
                '            env CAM_TESTDIR=${BL_TESTDIR} \\\n'
                '            CAM_SCRIPTDIR=${BL_ROOT}/test/system \\\n'
                '            ${BL_ROOT}/test/system/TSM.sh $1 $2 $3\n'
                '\n'
                '        fi'),

                '\$\{BL_ROOT\}/components/cam/test/system/TSM.sh \$1 \$2 \$3 \$4$' :
               ('${BL_ROOT}/components/cam/test/system/TSM.sh $1 $2 $3 $4\n'
                '\n'
                '        else\n'
                '\n'
                '            env CAM_TESTDIR=${BL_TESTDIR} \\\n'
                '            CAM_SCRIPTDIR=${BL_ROOT}/test/system \\\n'
                '            ${BL_ROOT}/test/system/TSM.sh $1 $2 $3 $4\n'
                '\n'
                '        fi')}
    file_sub_text(filename, patterns)
    num_changes += 1
    #TBL_ccsm.sh
    filename = os.path.join(systest, 'TBL_ccsm.sh')
    patterns = {'env CAM_TESTDIR=\$\{BL_TESTDIR\} \\\\' :
               ('if [ -d "${BL_ROOT}/components/cam" ]; then\n'
                '\n'
                '            env CAM_TESTDIR=${BL_TESTDIR} \\\\'),

                '\$\{BL_ROOT\}/components/cam/test/system/TSM_ccsm.sh \$1 \$2 \$3$' :
               ('${BL_ROOT}/components/cam/test/system/TSM_ccsm.sh $1 $2 $3\n'
                '\n'
                '        else\n'
                '\n'
                '            env CAM_TESTDIR=${BL_TESTDIR} \\\n'
                '            CAM_SCRIPTDIR=${BL_ROOT}/test/system \\\n'
                '            CAM_ROOT=${BL_ROOT} \\\n'
                '            ${BL_ROOT}/test/system/TSM_ccsm.sh $1 $2 $3\n'
                '\n'
                '        fi'),

                '\$\{BL_ROOT\}/components/cam/test/system/TSM_ccsm.sh \$1 \$2 \$3 \$4$' :
               ('${BL_ROOT}/components/cam/test/system/TSM_ccsm.sh $1 $2 $3 $4\n'
                '\n'
                '        else\n'
                '\n'
                '            env CAM_TESTDIR=${BL_TESTDIR} \\\n'
                '            CAM_SCRIPTDIR=${BL_ROOT}/test/system \\\n'
                '            CAM_ROOT=${BL_ROOT} \\\n'
                '            ${BL_ROOT}/test/system/TSM_ccsm.sh $1 $2 $3 $4\n'
                '\n'
                '        fi')}
    file_sub_text(filename, patterns)
    num_changes += 1
    #TPF.sh
    filename = os.path.join(systest, 'TPF.sh') 
    patterns = {'env CAM_TESTDIR=\$\{BL_TESTDIR\} \\\\' :
               ('if [ -d "${BL_ROOT}/components/cam" ]; then\n'
                '\n'
                '        env CAM_TESTDIR=${BL_TESTDIR} \\\\'),

                '\$\{BL_ROOT\}/components/cam/test/system/TSM.sh \$1 \$2 \$3 \$4$' :
               ('${BL_ROOT}/components/cam/test/system/TSM.sh $1 $2 $3 $4\n'
                '\n'
                '    else\n'
                '\n'
                '        env CAM_TESTDIR=${BL_TESTDIR} \\\n'
                '        CAM_SCRIPTDIR=${BL_ROOT}/test/system \\\n'
                '        ${BL_ROOT}/test/system/TSM.sh $1 $2 $3 $4\n'
                '\n'
                '    fi')}
    file_sub_text(filename, patterns)
    num_changes += 1
    #TR8.sh
    filename = os.path.join(systest, 'TR8.sh')
    patterns = {'# Check physics' :
               ('# Check physics\n'
                'if [ -d "${CAM_ROOT}/components/cam" ]; then\n'),

                '#Check Ionosphere' :
               ('else\n'
                '\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/physics/cam\n'
                'rc=$?\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/physics/camrt\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/physics/rrtmg -s aer_src\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/physics/simple\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/physics/waccm\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/physics/waccmx\n'
                'rc=`expr $? + $rc`\n'
                '\n'
                'fi\n'
                '\n'
                '#Check Ionosphere\n'
                'if [ -d "${CAM_ROOT}/components/cam" ]; then\n'),

                '#Check Chemistry' :
               ('else\n'
                '\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/ionosphere\n'
                'rc=`expr $? + $rc`\n'
                '\n'
                'fi\n'
                '\n'
                '#Check Chemistry\n'
                'if [ -d "${CAM_ROOT}/components/cam" ]; then\n'),
                                '#Check Dynamics' :
               ('else\n'
                '\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/chemistry\n'
                'rc=`expr $? + $rc`\n'
                '\n'
                'fi\n'
                '\n'
                '#Check Dynamics\n'
                'if [ -d "${CAM_ROOT}/components/cam" ]; then\n'),

                '#Check other' :
               ('else\n'
                '\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/dynamics/se\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/dynamics/fv\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/dynamics/eul\n'
                'rc=`expr $? + $rc`\n'
                '\n'
                'fi\n'
                '\n'
                '#Check other\n'
                'if [ -d "${CAM_ROOT}/components/cam" ]; then\n'),

                '#Check coupler' :
               ('else\n'
                '\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/advection\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/control\n'
                'rc=`expr $? + $rc`\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/utils\n'
                'rc=`expr $? + $rc`\n'
                '\n'
                'fi\n'
                '\n'
                '#Check coupler\n'
                'if [ -d "${CAM_ROOT}/components/cam" ]; then\n'),

                'echo \$rc' : '',
                                'if \[ \$rc = 255 \]; then' :
               ('else\n'
                '\n'
                'ruby $ADDREALKIND_EXE -r r8 -l 1 -d $CAM_ROOT/src/cpl\n'
                'rc=`expr $? + $rc`\n'
                '\n'
                'fi\n'
                '\n'
                'echo $rc\n'
                '\n'
                'if [ $rc = 255 ]; then'),

                'exit \$rc' :
               ('echo $rc\n'
                'exit $rc')}
    file_sub_text(filename, patterns)    
    num_changes += 1
    #input_tests_master
    filename = os.path.join(systest, 'input_tests_master')
    patterns = {'fm001 TFM.sh' :
               ('gt001 TGIT.sh\n'
                'fm001 TFM.sh')}
    file_sub_text(filename, patterns)
    num_changes += 1
    #tests_pretag_hobart_nag
    filename = os.path.join(systest, 'tests_pretag_hobart_nag')
    patterns = {'fm001' : 'gt001'}
    file_sub_text(filename, patterns)
    num_changes += 1
    #tests_pretag_izumi_nag
    filename = os.path.join(systest, 'tests_pretag_izumi_nag')
    #check that file actually exists (it doesn't always for older CAM versions):
    if os.path.exists(filename):  
        patterns = {'fm001' : 'gt001'}
        file_sub_text(filename, patterns)
        num_changes += 1
    #Makefile.in
    filename = os.path.join(bld, 'Makefile.in') 
    patterns = {'\$\(ROOTDIR\)/components/cam/bld/mkDepends Filepath Srcfiles > \$@' :
               ('if [ -d "${ROOTDIR}/components/cam" ]; then \\\n'
                '           $(ROOTDIR)/components/cam/bld/mkDepends Filepath Srcfiles > $@; \\\n'
                '        else \\\n'
                '           $(ROOTDIR)/bld/mkDepends Filepath Srcfiles > $@; \\\n' 
                '        fi' ),

                '\$\(ROOTDIR\)/components/cam/bld/mkSrcfiles -e \$\(EXCLUDE_SOURCES\) > \$@' :
               ('if [ -d "${ROOTDIR}/components/cam" ]; then \\\n'
                '           $(ROOTDIR)/components/cam/bld/mkSrcfiles -e $(EXCLUDE_SOURCES) > $@; \\\n'
                '        else \\\n'
                '           $(ROOTDIR)/bld/mkSrcfiles -e $(EXCLUDE_SOURCES) > $@; \\\n'
                '        fi')}
    file_sub_text(filename, patterns)
    num_changes += 1
    #---------------------

    return num_changes

##############################
###
### Classes
###
##############################

class SvnRevRange(object):
    """A class to represent a range of SVN revisions
    Instance variables:
    start = -1 # -1 means BASE, 0 means absent
    end   = -1 # -1 means most recent (HEAD), 0 means absent
    """
    def __init__(self, revstr):
        self.start = -1
        self.end = -1
        if (revstr is not None):
            revs = revstr.split(":")
            if (len(revs) > 2):
                quitOnFail(1, "Illegal revision string, '{}'".format(revstr))
            elif (len(revs) == 2):
                if (len(revs[0]) > 0):
                    self.start = int(revs[0])
                # No else, argument was left off, implied BASE
                # End if
                if (len(revs[1]) > 0):
                    self.end = int(revs[1])
                # No else, argument was left off, implied HEAD
                # End if
            elif (revstr == "HEAD"):
                self.start = 0
                self.end = -1
            elif (revstr == "BASE"):
                self.start = -1
                self.end = 0
            elif (len(revs) == 1):
                if (len(revs[0]) > 0):
                    if (not isinstance(revs[0], int)):
                        self.start = int(revs[0])
                    else:
                        self.start = revs[0]
                    # end if
                self.end = 0
            else:
                quitOnFail(1, "Badly formatted revision string, {}".format(revstr))
            # End if
        # no else, blank string uses defaults
        # End if
    # end def  __init__

    def revString(self):
        if (self.start < 0):
            sstr = "1" # svn log doesn't allow BASE
        elif (self.start == 0):
            sstr = ''
        else:
            sstr = str(self.start)
        # End if
        if (self.end < 0):
            estr = "HEAD"
        elif (self.end == 0):
            estr=""
        else:
            estr = str(self.end)
        # End if
        if ((len(sstr) > 0) and (len(estr) > 0)):
            revstr = "{}:{}".format(sstr, estr)
        else:
            revstr = sstr+estr
        # End if
        return revstr
    # end def revString

    def revStart(self):
        return self.start
    # end def revStart

    def revEnd(self):
        return self.end
    # end def revEnd
# End class SvnRevRange

class LogEntry(object):
    """A class to hold a single svn log entry
    Instance variables
    revstr = 0       # Revision number (as string)
    committer = ''   # Who made the commit
    commitDate = ''  # Date and time of commit
    URL = ''         # URL of the repo (including any subdirectory) for revision
    """
    def __init__(self, rev, who, when, url):
        self.revstr = rev
        self.committer = who
        self.commit_date = when
        self.URL = url
    # End def __init__

    def revision(self):
        return str(self.revstr)
    # End def revision

    def revNum(self):
        return int(self.revstr)
    # End def revNum

    def who(self):
        return self.committer
    # End def who

    def when(self):
        return self.commit_date
    # End def when

    def url(self):
        return self.URL
    # End def url

# End class LogEntry

class SvnLogEntry(LogEntry):
    """A class to hold a single svn log entry
    Instance variables
    message = None   # Commit message
    revTag = None    # Optional tag string if this entry is from a tag
    """
    def __init__(self, rev, who, when, url, lines, tag=None):
        super(self.__class__, self).__init__(rev, who, when, url)
        self.message = list(lines)
        self.revTag = tag
    # End def __init__

    def formatLogMessage(self):
        # First, create a short first line
        if (len(self.message[0]) > 72):
            logm = self.message[0][0:68] + ' ...'
        else:
            logm = self.message[0]
        # End if
        logm = logm + os.linesep + os.linesep
        # Include some import information
        logm = logm + 'Imported from ' + self.url() + "@{}".format(self.revNum())
        logm = logm + os.linesep + cby_str + ' ' + str(self.committer)
        logm = logm + ' at ' + str(self.commit_date) + os.linesep
        logm = logm + 'Original svn commit message:' + os.linesep
        # Now, include full original log message
        for line in self.message:
            logm = logm + os.linesep + line
        # End for
        return logm
    # End def formatLogMessage

    def tag(self):
        if (self.revTag is None):
            return None
        else:
            return str(self.revTag)
        # End if
    # End def revision

# End class SvnLogEntry

class Git2svnLogEntry(LogEntry):
    """A class to hold information from an svn2git log entry
    Instance variables
    commit = ''  # The git commit hash
    NB: The super class holds the original SVN information, not git info
      This allows sorting by SVN revision number
    """
    def __init__(self, gcommit, svnRev, svnWho, svnWhen, svnURL):
        super(self.__class__, self).__init__(svnRev, svnWho, svnWhen, svnURL)
        self.gitCommit = gcommit
    # End def __init__

    def commit(self):
        return str(self.gitCommit)
    # End revision

# End class Git2svnLogEntry

## Enumerate git ref types
class gitRef(object):
    unknown      = 0
    localBranch  = 1
    remoteBranch = 2
    tag          = 3
    sha1         = 4
# End class gitRef

##############################
###
### svn Functions
###
##############################

def svnExport(exportDir, repoURL, revstr=None):
    """Export a subversion commit, with optional revision
    NB: If the destination directory, exportDir, exists it is first removed
    """
    if (os.path.exists(exportDir)):
        shutil.rmtree(exportDir)
    # End if
    if (revstr is None):
        caller = "svnExport {} {}".format(exportDir, repoURL)
        retcode = scall(["svn", "export", "--ignore-externals", repoURL, exportDir])
    else:
        caller = "svnExport -r{} {} {}".format(revstr, repoURL, exportDir)
        retcode = retcall(["svn", "export", "--ignore-externals", "-r{}".format(revstr), repoURL, exportDir])
    # End if
    quitOnFail(retcode, caller)
# End def svnExport

def svn_list(url):
    """Call svn list on a  url"""
    caller = "svn_list {}".format(url)
    slist = checkOutput(["svn", "list", url])
    entries = []
    if slist is not None:
        for line in slist.splitlines():
            entries.append(line.rstrip("/"))
        # End for
    # End if

    return entries
# End def svn_list

def svnLastChangedRev(url):
    """Find the last commit to url"""
    caller = "svnLastChangedRev {}".format(url)
    lines = checkOutput(["svn", "info", url])
    rev = ''
    if (lines is not None):
        for line in lines.splitlines():
            match = reLastChange.match(line)
            if (match is not None):
                rev = match.group(1)
                break
            # End if
        # End for
    # End if
    return rev
# End def svnLastChangedRev

def svn_capture_log(repo_url, revstr, auth_table, svn_auth, keep_dates,
                    tag=None, default_author=None,
                    tag_rev_list=None, tag_str_list=None):
    logs = []
    caller = "svn_capture_log {} {}".format(repo_url, revstr)
    log = checkOutput(["svn", "log", "--stop-on-copy",
                       "-r{}".format(revstr), repo_url])
    nlines = 0
    lines = []
    skip = False
    if log is None:
        perr("ERROR: '{}', no log".format(caller))
    else:
        line_cnt = 0                 #initalize counter
        log_lines = log.splitlines() #create list of log lines
        for line in log_lines:
            line_cnt += 1
            match = reRevis.match(line)
            if (not skip) and (nlines > 0):
                lines.append(line)
                nlines -= 1
                if nlines == 0:
                    #Does tag list exist?
                    #---------------------
                    if tag_rev_list is not None:
                        #If so, then search for tag nearest to revision:
                        rev_idx = tag_rev_search(rev, rev_next, tag_rev_list)

                        #Does a tag revision match current revision?
                        if rev_idx != -1:
                            #If so, then set tag string:
                            tag_str = tag_str_list[rev_idx]
                        else:
                            #If not, set tag string to None:
                            tag_str = None
                    else:
                        #If no tag list is present, set tag labels to None:
                        tag_str = None
                    #---------------------

                    logs.append(SvnLogEntry(rev, who, when, repo_url,
                                            lines, tag=tag_str))
                    del(lines[:])
                    lines = []
                # End if
            elif match is not None:
                rev = match.group(1).strip()
                who = match.group(2).strip()
                #Look ahead for next revision:
                #----------------------------
                if line_cnt < len(log_lines)-1:
                    #If not at end of log, search ahead:
                    rev_next = next_revision_val(log_lines[line_cnt:])
                else:
                    #If at end of log, set next revision to gigantic number:
                    rev_next = sys.maxsize
                #----------------------------

                if auth_table is not None:
                    if who in auth_table:
                        who = auth_table[who]
                    elif default_author is not None:
                        wmsg = ("WARNING: Author, '{}', not found in author "
                                "table, substituting '{}'")
                        print(wmsg.format(who, default_author))
                        auth_table[who] = default_author
                        who = default_author
                    else:
                        wmsg = ("WARNING: Author, '{}', not found in author "
                                "table, guessing author info")
                        print(wmsg.format(who))

                        #Is svn author an email? Search for "@" to find out:
                        #--------------------------------------------------
                        at_idx = who.find("@")

                        if at_idx != -1:
                            #If an email, set start of email as "name":
                            who_name  = who[:at_idx]
                            who_new   = "{} : <{}>".format(who_name,who)

                            #re-name variable:
                            who = who_new
                        else:
                            #If not an email, add a fake one to keep git happy:
                            wmsg = "{} : <missing_email@missing.email>"
                            who_new = wmsg.format(who)

                            #re-name variable:
                            who = who_new
                        #--------------------------------------------------
                elif not svn_auth:
                    who = None
                # No else, just keep svn who
                # End if
                if keep_dates:
                    when = match.group(3).split('(')[0].strip()
                else:
                    when = None
                # End if
                nlines = int(match.group(4))
                skip = True # Skip the blank line after a match
            else:
                # just discard this line
                skip = False
            # End if
        # End for
    # End if
    return logs
# End def svn_capture_log

def parseAuthorTable(filename):
    if not os.path.exists(filename):
        perr("Author table, '{}', does not exist".format(filename))

    auth_table = {}
    try:
        with open(filename) as f:
            for line in f:
                entry = line.split(':')
                if len(entry) == 2:
                    auth_table[entry[0].strip()] = entry[1].strip()
                elif len(entry) != 1:
                    errmsg = "Bad author table entry, '{}'"
                    raise ValueError(errmsg.format(line))
                else:
                    wmsg = "Ignoring incorrectly formatted author entry, '{}'"
                    print(wmsg.format(line.strip()))
    except ValueError as e:
        perr(e)
    except Exception as e:
        perr(e)

    return auth_table
# End parseAuthorTable

def tag_rev_search(rev, rev_next, tag_rev_list):
    """This function is designed to search for the tag
      revision closest to, but after, the current trunk
      or branch revision, while also checking that no revisions
      are between the current revision and the tag revision"""

    #Convert tag revisions to integers:
    tag_rev_ints = map(int,tag_rev_list)

    #Convert current revision to integer
    curr_rev_int = int(rev)

    #Convert next revision to integer:
    rev_next_int = int(rev_next)

    #Ignore all tag revisions less than current revision:
    tag_abv_list = [rev for rev in tag_rev_ints if rev >= curr_rev_int]

    #Find revision closest to current revision:
    tag_rev_close = min(tag_abv_list, key=lambda x: x-curr_rev_int)

    #Determine if closest tag revision is in-between current revision and
    #next trunk/branch revision:
    if tag_rev_close < rev_next_int:
        #If so, then find list index of tag:
        rev_idx = tag_rev_ints.index(tag_rev_close)
    else:
        #If not, then set rev_idx to "-1", which indicates tag doesn't exist for this revision:
        rev_idx = -1

    #return tag revision index:
    return rev_idx

def next_revision_val(log_lines):
    """This function searches for the next revision
       in the subversion logs inside a loop of the
       logs themselves, which is needed to assign
       tags properly."""

    #Initalize next revision:
    rev_next = sys.maxsize

    #Loop over log lines:
    for line in log_lines:

        #Search for match:
        match = reRevis.match(line)

        if match is not None:
            #If match is present, pull out revision
            rev_next = match.group(1).strip()
            #break out of loop:
            break

    #Send next revision back:
    return rev_next

##############################
###
### git Functions
###
##############################

# Return the (current branch, sha1 hash) of working copy in wdir
def gitCurrentBranch(wdir):
    caller = "gitCurrentBranch {}".format(wdir)
    currdir = os.getcwd()
    os.chdir(wdir)
    branch = checkOutput(["git", "symbolic-ref", "--short", "HEAD"])
    if ((branch is None) or (len(branch) == 0)):
        hash = None
    else:
        branch = branch.rstrip()
        hash = checkOutput(["git", "rev-parse", "HEAD"])
    # End if
    if (hash is not None):
        hash = hash.rstrip()
    # End if
    os.chdir(currdir)
    return (branch, hash)
# End gitCurrentBranch

def gitRefType(chkdir, ref):
    """Determine if 'ref' is a local branch, a remote branch, a tag, or a commit
    Should probably use this command instead"""
    #  git show-ref --verify --quiet refs/heads/<branch-name>

    caller = "gitRefType {} {}".format(chkdir, ref)
    currdir = os.getcwd()
    os.chdir(chkdir)
    refType = gitRef.unknown
    # First check for local branch
    gitout = checkOutput(["git", "branch"])
    if gitout is not None:
        branches = [ x.lstrip('* ') for x in gitout.splitlines() ]
        for branch in branches:
            if branch == ref:
                refType = gitRef.localBranch
                break
            # End if
        # End for
    # End if
    # Next, check for remote branch
    if refType == gitRef.unknown:
        gitout = checkOutput(["git", "branch", "-r"])
        if gitout is not None:
            for branch in gitout.splitlines():
                match = reRemoteBranch.match(branch)
                if (match is not None) and (match.group(1) == ref):
                    refType = gitRef.remoteBranch
                    break
                # End if
            # End for
        # End if
    # End if
    # Next, check for a tag
    if refType == gitRef.unknown:
        gitout = checkOutput(["git", "tag"])
        if gitout is not None:
            for tag in gitout.splitlines():
                if tag == ref:
                    refType = gitRef.tag
                    break
                # End if
            # End for
        # End if
    # End if
    # Finally, see if it just looks like a commit hash
    if (refType == gitRef.unknown) and reGitHash.match(ref):
        refType = gitRef.sha1
    # End if

    os.chdir(currdir)
    # Return what we've come up with
    return refType
# End gitRefType

def gitCheckDir(chkdir, ref=None):
    """Check to see if directory (chkdir) exists and is the correct version (ref)
    returns True (correct), False (incorrect) or None (chkdir not found)"""

    caller = "gitCheckDir {} {}".format(chkdir, ref)
    currdir = os.getcwd()
    if (os.path.exists(chkdir)):
        if (os.path.exists(os.path.join(chkdir, ".git"))):
            os.chdir(chkdir)
            head = checkOutput(["git", "rev-parse", "HEAD"])
        else:
            head = None
        # End if
        if (ref is None):
            refchk = None
        else:
            os.chdir(chkdir)
            refchk = checkOutput(["git", "rev-parse", ref])
        # End if
        if (ref is None):
            retVal = head is not None
        elif (refchk is None):
            retVal = None
        else:
            retVal = (head == refchk)
        # End if
    else:
        retVal = None
    # End if
    os.chdir(currdir)
    return retVal
# End gitCheckDir

def gitWdirClean(wdir):
    caller = "getWdirClean {}".format(wdir)
    currdir = os.getcwd()
    os.chdir(wdir)
    retcode = retcall(["git", "diff", "--quiet", "--exit-code"])
    os.chdir(currdir)
    return (retcode == 0)
# End def gitWdirClean

def gitNewRepo(repo):
    caller = "gitNewRepo {}".format(repo)
    currdir = os.getcwd()
    os.chdir(repo)
    status = checkOutput(["git", "status"])
    newrepo = False
    for line in status.splitlines():
        if (line.rstrip(os.linesep) == "Initial commit"):
            newrepo = True
            break
        elif (line.rstrip(os.linesep) == "No commits yet"):
            newrepo = True
            break
        # End if
    # End for
    os.chdir(currdir)
    return newrepo
# End def gitNewRepo

def gitCheckout(checkoutDir, ref=None):
    caller = "gitCheckout {}".format(checkoutDir)
    currdir = os.getcwd()
    os.chdir(checkoutDir)
    retcode = 0
    if (gitCheckDir(checkoutDir) is None):
        perr("gitCheckout: Checkout dir ({}) not found".format(checkoutDir))
    # End if

    if ref is not None:
        (branch, chash) = gitCurrentBranch(checkoutDir)
        refType = gitRefType(checkoutDir, ref)
        if (refType == gitRef.remoteBranch):
            retcode = scall(["git", "checkout", "--track", "origin/"+ref])
        elif (refType == gitRef.localBranch):
            if ((branch != ref) and (not gitWdirClean(checkoutDir))):
                perr("Working directory ({}) not clean, aborting".format(checkoutDir))
            else:
                retcode = scall(["git", "checkout", ref])
            # End if
        else:
            # For now, do a hail mary and hope ref can be checked out
            retcode = scall(["git", "checkout", ref])
        # End if
        quitOnFail(retcode, caller)
    # End if
    os.chdir(currdir)
# End def gitCheckout

def gitRmFile(repo, filename):
    caller = "gitRmFile {} {}".format(repo, filename)
    currdir = os.getcwd()
    os.chdir(repo)
    retcode = retcall(["git", "rm", filename])
    os.chdir(currdir)
    quitOnFail(retcode, caller)
# End def gitRmFile

def gitAddFile(repo, filename):
    caller = "gitAddFile {} {}".format(repo, filename)
    currdir = os.getcwd()
    os.chdir(repo)
    # Since we may have declined to copy a new file (eg., bad symlink)
    # Make sure the file exists before trying to add it
    if os.path.exists(filename):
        retcode = retcall(["git", "add", filename])
        os.chdir(currdir)
        quitOnFail(retcode, caller)
    # End if
# End def gitAddFile

def gitCommitAll(repo, message, author=None, date=None):
    caller = "gitCommitAll {}".format(repo)
    currdir = os.getcwd()
    os.chdir(repo)
    gitcmd = ["git", "commit", "-a"]
    if author is not None:
        gitcmd.append("--author='{}'".format(author))

    if date is not None:
        gitcmd.append("--date='{}'".format(date))

    #Need to add quotes to message string, to
    #avoid git error when "/" is present in the message:
    full_message = "'"+message+"'"
    gitcmd.append("--message={}".format(full_message))

    retcode = retcall(gitcmd)
    os.chdir(currdir)
    quitOnFail(retcode, caller, gitcmd)
# End def gitCommitAll

def gitApplyTag(repo, tag, message):
    caller = "gitApplyTag {} {}".format(repo, tag)
    currdir = os.getcwd()
    os.chdir(repo)
    retcode = scall(["git", "tag", "-a", tag, "-m", message])
    os.chdir(currdir)
    quitOnFail(retcode, caller)
# End def gitApplyTag

def gitCaptureLog(repo):
    logs = []
    caller = "gitCaptureLog {}".format(repo)
    currdir = os.getcwd()
    os.chdir(repo)
    log = checkOutput(["git", "log"])
    status = 0
    if (log is not None):
        for line in log.splitlines():
            match = reCommit.match(line)
            if (match is not None):
                # A commit line should be the first in a new message
                if (status != 0):
                    # We are going to just ignore bad or non-svn commits for now
                    status = 0
                # End if
                commit = match.group(1)
                status = status + 8
            # End if
            match = reImport.match(line)
            if (match is not None):
                rev = match.group(1)
                status = status + 4
            # End if
            match = reAuthor.match(line)
            if (match is not None):
                who = match.group(1)
                when = match.group(2)
                status = status + 3
            # End if
            # See if we have a complete commit to flush
            if (status == 15):
                logs.append(Git2svnLogEntry(commit, rev, who, when, repo))
                status = 0
            # End if
        # End for
    # End if
    os.chdir(currdir)
    return logs
# End gitCaptureLog

def findParentCommit(gitLog, svnRev):
  "Find the commit with the closest (but not larger) svn revision"
  rnum = int(svnRev)
  commit = None
  # The log should be in inverse order so stop at first hit
  for log in gitLog:
    gnum = log.revNum()
    if (gnum < rnum):
      commit = log.commit()
      break
    # End if
  # End for
  return commit
# End def findParentCommit

def git_setup_dir(chkdir, repo, branch, rev, repo_url, auth_table,
                  svn_author, preserve_dates, default_author):
    """
    Check to see if directory (chkdir) exists and is okay to use
    Create chkdir (if necessary) and set current branch to master
    returns True unless directory exists but is not correct"""
    caller = "git_setup_dir {}".format(chkdir)
    dirOK = True
    currdir = os.getcwd()
    if (branch != "master"):
        if ((not os.path.exists(chkdir)) or
            (not os.path.exists(os.path.join(chkdir, ".git")))):
            perr("ERROR: git repo must exist to create branch {}".format(branch))
        else:
            os.chdir(chkdir)
            dirOK = (retcall(["git", "checkout", branch]) == 0)
            if (not dirOK):
                # We don't have a branch, better create it
                dirOK = (retcall(["git", "checkout", "master"]) == 0)
                if (dirOK):
                    # We have to figure out where to start this branch
                    gitLog = gitCaptureLog(chkdir)
                    logs = list()
                    revstart = rev.revStart()
                    while len(logs) < 1:
                        logs = svn_capture_log(repo_url, revstart, auth_table,
                                               svn_author, preserve_dates,
                                               default_author=default_author)
                        if len(logs) < 1:
                            revstart = revstart + 1
                            if revstart > rev.revEnd():
                                perr("No commits in range {} to {}".format(rev.revStart(), rev.revEnd()))
                            # End if
                        # End if
                    # End while
                    branchRev = logs[len(logs) - 1].revision()
                    commit = findParentCommit(gitLog, revstart)
                    if commit is None:
                        perr("No appropriate master commit to start branch {}".format(branch))
                    else:
                        dirOK = (retcall(["git", "branch", branch, str(commit)]) == 0)
                    # End if
                else:
                    perr("ERROR: master must exist to create branch {}".format(branch))
                # End if
            # End if
            os.chdir(currdir)
        # End if
    # End if (branch != master)
    if (os.path.exists(chkdir)):
        if (os.path.exists(os.path.join(chkdir, ".git"))):
            os.chdir(chkdir)
            dirOK = (retcall(["git", "checkout", branch]) == 0)
# XXgoldyXX: v debug only
# Should not have to do this
#            if (not dirOK):
#                dirOK = (retcall(["git", "checkout", "-b", branch]) == 0)
#            # End if
# XXgoldyXX: ^ debug only
        else:
            dirOK = False
        # End if
    else:
        # We need to make sure chkdir's parent exists
        parent = os.path.realpath(os.path.join(chkdir, ".."))
        if (not os.path.exists(parent)):
            os.mkdirs(parent)
        # End if
        os.chdir(parent)
        dirOK = (retcall(["git", "init",  "--quiet", chkdir]) == 0)
        if (dirOK):
            os.chdir(chkdir)
            dirOK = (retcall(["git", "checkout", "-b", "master"]) == 0)
        # End if
    # End if

    os.chdir(currdir)
    return dirOK
# End def git_setup_dir

##############################
###
### svn2git Functions
###
##############################

def FindTreeOrphans(dir1, dir2):
  "Provide lists of files which show up in one directory but not the other"
  groot = os.path.join(".", ".git")
  orphans = []
  currdir = os.getcwd()
  os.chdir(dir1)
  for root, dirs, files in os.walk("."):
    if (root[0:len(groot)] != groot):
      for file in files:
        fname = os.path.join(root, file).lstrip(".").lstrip("/")
        if (not os.path.exists(os.path.join(dir2, fname))):
          orphans.append(fname)
        # End if
      # End for
    # End if
  # End for
  os.chdir(currdir)
  return orphans
# End FindTreeOrphans

def copySvn2Git(svnDir, gitDir):
  "Copy the files in svnDir to gitDir"
  currdir = os.getcwd()
  os.chdir(svnDir)
  num_copies = 0
  for root, dirs, files in os.walk("."):
    parent = os.path.join(gitDir, root)
    if (not os.path.exists(parent)):
      os.makedirs(parent)
    # End if
    for file in files:
        file1 = os.path.join(root, file)
        file2 = os.path.join(parent, file)
        if file_diff(file1, file2):
            if os.path.islink(file1):
                pdir = os.path.dirname(file1)
                # SVN symlinks cannot (correctly) be absolute pathnames
                plink = os.path.join(pdir, os.readlink(file1))
                if not os.path.exists(plink):
                    # Do not try to copy a bad symlink
                    print("WARNING: Not copying bad symlink, {}".format(plink))
                    continue
                # End if
            # End if
            num_copies += 1
            shutil.copy2(file1, file2)
            # End if
        # End if
    # End for
  # End for
  os.chdir(currdir)
  return num_copies
# End def copySvn2Git

def processRevision(export_dir, git_dir, log, external, cam_move):
    rnum = log.revision()
    tag = log.tag()
    num_changes = 0
    print("Processing revision {}, tag = {}".format(int(rnum), tag))
    svnExport(export_dir, log.url(), rnum)

    #-----------------------------
    #Create Externals_CAM.cfg file
    #-----------------------------
    if external:
        #Determine CAM SVN Externals:
        cam_ext_path, cam_ext_url = read_svn_externals_cam(export_dir)

        #Create new 'manage_externals' cfg file for CAM:
        external_cam_cfg_create(cam_ext_path, cam_ext_url)
    # End if

    #-----------------------------------------
    #Move "components/cam" to head of svn repo
    #-----------------------------------------
    if cam_move:
        svn_cam_dir_top_move(export_dir)
    # End if
    #-----------------------------------------

    orphans1 = FindTreeOrphans(export_dir, git_dir)
    orphans2 = FindTreeOrphans(git_dir, export_dir)
    # Remove files no longer in repo
    for file in orphans2:
        if file not in cam_copy_files:
            gitRmFile(git_dir, file)
            num_changes += 1
        # End if
    # End for
    # Copy the svn export directory into the working git directory
    # Can't use copytree since the repo directory already exists
    num_changes += copySvn2Git(export_dir, git_dir)
    # Add files new to the repo
    for file in orphans1:
        gitAddFile(git_dir, file)
        num_changes += 1
    # End for

    #--------------------------------------
    #Add Externals_CAM.cfg file to git repo
    #--------------------------------------
    if external:
        #Modify top-level "Externals.cfg" to read-in CAM cfg file:
        external_cfg_add_cam(git_dir)

        #Add new cfg files to git repository:
        git_external_cfg_cam_add(git_dir, False, "")

        #Add "manage_externals" remote to git repository:
        git_manage_external_add(git_dir)
    # End if
    #---------------------------------------------

    #--------------------------------------
    # Add boilerplate files
    #--------------------------------------
    for file in cam_copy_files:
        if file == "TGIT.sh":
            src_path = os.path.join(currDir,file)
            dst_path = os.path.join(git_dir, "test", "system", file)
        else:
            src_path = os.path.join(currDir, "cam{}".format(file))
            dst_path = os.path.join(git_dir, file)

        needs_add = not os.path.exists(dst_path)
        if file_diff(src_path, dst_path):
            shutil.copy2(src_path, dst_path)
            num_changes += 1
        # End if
        if needs_add:
            gitAddFile(git_dir, dst_path)
        # End if
    # End for

    #--------------------------------------
    # Modify build scripts
    #--------------------------------------
    num_changes += cam_svn_to_git_mods(git_dir)

    # Commit everything
    if num_changes > 0:
        gitCommitAll(git_dir, log.formatLogMessage(),
                     author=log.who(), date=log.when())
    # End if
    if (tag is not None):
        # Apply the tag
        gitApplyTag(git_dir, tag, log.formatLogMessage())
    # End if
# End def processRevision

############################################
###
### SVN Externals -> Externals_CAM functions
###
############################################

#Create externals label dictionary:
ext_label_dict = {'chem_proc':'chem_proc',
                  'src/physics/carma/base':'carma',
                  'src/physics/clubb':'clubb',
                  'src/physics/cosp2/src':'cosp2',
                  'src/physics/silhs':'silhs'}

def read_svn_externals_cam(svndir):
    """Reads externals information from
       the SVN_EXTERNAL_DIRECTORIES file
       in the cam sub-directory."""

    #Set CAM's 'SVN_EXTERNAL_DIRECTORIES' file path:
    svn_ext_filepath = os.path.join(svndir,"components", "cam",
                                    "SVN_EXTERNAL_DIRECTORIES")

    #Check if CAM's SVN_EXTERNAL_DIRECTORIES file exists, and is
    #where we think it is:
    if not os.path.exists(svn_ext_filepath):
        perr("CAM's SVN_EXTERNAL_DIRECTORIES is not present, need to "
             "add CAM externals to git manually")

    #initalize externals list:
    svn_ext_list = []

    #Read in 'SVN_EXTERNAL_DIRECTORIES_CAM' file data:
    with open(svn_ext_filepath,'r') as svn_ext_fil:

        #Read data to list:
        svn_ext_list = svn_ext_fil.readlines()

    #Initalize lists:
    cam_ext_path = []
    cam_ext_url  = []

    #Loop over all CAM externals:
    for line in svn_ext_list:
        #Seperate local path and external URL:
        path_and_url = line.split()

        #Append external path list:
        cam_ext_path.append(path_and_url[0].strip())

        #Append external url list:
        cam_ext_url.append(path_and_url[1].strip())

    #Return cam external paths (for deletion):
    return cam_ext_path, cam_ext_url

#+++++++++++++++++++++++

def external_cam_cfg_create(cam_ext_path, cam_ext_url):
    """Generates a new Externals_CAM.cfg
       file based off the original
       'SVN_EXTERNAL_DIRECTORIES' file in
       the 'components/cam' subdirectory."""

    #Iinitalize lists:
    ext_cfg_labels = []
    ext_cfg_urls   = []
    ext_cfg_tags   = []

    #Determine external "labels":
    #---------------------------
    for line in cam_ext_path:
        #Look up label from dictionary
        label = ext_label_dict[line]

        #Add label to list:
        ext_cfg_labels.append(label)
    #--------------------------

    #Determine external URLs and tags:
    #--------------------------------
    for line in cam_ext_url:
        #Search for "tags" line:
        tags_exist = line.find("tags")

        #End script if "tags" string isn't found:
        if(tags_exist == -1):
            perr("The 'tags' string is missing in external URL {}".format(line))

        #Determine repository URLs:
        #Note:  Adding five to index to incorporate entire "tags/" string in URL
        ext_cfg_urls.append(line[:(tags_exist+5)])

        #Determine repository tag:
        ext_cfg_tags.append(line[(tags_exist+5):])
    #--------------------------------

    #Write new "Externals_CAM.cfg" file:
    #----------------------------------
    #Set cfg file name:
    cfg_fil_name = "Externals_CAM.cfg"

    #Determine local directory:
    currdir = os.getcwd()

    #Set full cfg file path:
    cfg_file_path = os.path.join(currdir,cfg_fil_name)

    #If file already exists, warn user and delete it:
    if(os.path.exists(cfg_file_path)):
        print("Local 'Externals_CAM.cfg' file already exists! Replacing it.")
        #Remove file:
        os.remove(cfg_file_path)

    #Create new cfg file:
    with open(cfg_file_path,'w') as cfg_file:

        #Loop over external label indices:
        for i in range(len(ext_cfg_labels)):
            #Add Externals label:
            cfg_file.write("["+ext_cfg_labels[i]+"]\n")
            #Add local path:
            cfg_file.write("local_path = "+cam_ext_path[i]+"\n")
            #Add protocol:
            cfg_file.write("protocol = svn\n")
            #Add URL:
            cfg_file.write("repo_url = "+ext_cfg_urls[i]+"\n")
            #Add tag:
            cfg_file.write("tag = "+ext_cfg_tags[i]+"\n")
            #Add "required" statement:
            cfg_file.write("required = True\n")
            #Add blank line:
            cfg_file.write("\n")

        #Add externals description to file:
        cfg_file.write("[externals_description]\n")
        cfg_file.write("schema_version = 1.0.0\n")
        #Add blank line:
        cfg_file.write("\n")
    #----------------------------------

#+++++++++++++++++++++

def external_cfg_add_cam(git_dir):
    """Adds a cam externals call to
       the top-level 'Externals.cfg'
       directory."""

    #Set cfg file name:
    cfg_fil_name = "Externals.cfg"

    #Set full cfg file path:
    cfg_file_path = os.path.join(git_dir,cfg_fil_name)

    #Check if file exists.  If not, then kill the script:
    if(not os.path.exists(cfg_file_path)):
        perr("Externals.cfg is missing from local git repo! Subversion branch may need updating.")

    #Open cfg file (to append):
    with open(cfg_file_path,'a') as cfg_file:

        #Add CAM externals to file:
        cfg_file.write("[cam]\n")
        cfg_file.write("local_path = .\n")
        cfg_file.write("protocol = externals_only\n")
        cfg_file.write("externals = Externals_CAM.cfg\n")
        cfg_file.write("required = True\n")
        #Add blank space:
        cfg_file.write("\n")

#+++++++++++++++++++++

def git_external_cfg_cam_add(git_dir, git_commit, git_com_msg):
    """Adds 'Externals_CAM.cfg' file to
       git directory, along with a modified
       'Externals.cfg' file needed to use the
       the new CAM cfg file."""

    #Set file names:
    cam_ext_file  = "Externals_CAM.cfg"
    head_ext_file = "Externals.cfg"

    #Determine current directory:
    currdir = os.getcwd()

    #Determine full CAM externals file path:
    cam_ext_full_path = os.path.join(currdir,cam_ext_file)

    #Go to new git (top-level) directory:
    os.chdir(git_dir)

    #Copy new Externals_CAM.cfg file to git repository:
    retcode = retcall(["mv", cam_ext_full_path, "."])

    #Add new Externals_CAM.cfg file to git:
    retcode = retcall(["git", "add", cam_ext_file])

    #Quit if git add fails:
    caller = "git add {} in {}".format(cam_ext_file, git_dir)
    quitOnFail(retcode, caller)

    #Add new Externals.cfg file to git:
    retcode = retcall(["git", "add", head_ext_file])

    #Quit if git add fails:
    caller = "git add {} in {}".format(head_ext_file, git_dir)
    quitOnFail(retcode, caller)

    #Commit changes to git respository:
    if git_commit:
        retcode = retcall(["git", "commit", "-m", git_com_msg])

        #quit if git commit fails:
        caller = "git commit -m {} in {}".format(git_com_msg, git_dir)
        quitOnFail(retcode, caller)

    #Return to original directory:
    os.chdir(currdir)

def git_manage_external_add(git_dir):
    """Adds the "manage_externals" routines
       from a remote git repo to the local
       cam git repo."""

    #Determine current directory:
    currdir = os.getcwd()

    #Go to new git (top-level) directory:
    os.chdir(git_dir)

    #Check if "manage_externals" directory does not exist:
    if not os.path.exists("manage_externals"):
        #Read in list of git remotes:
        remote_list = checkOutput(["git", "remote"])

        #Search for "manage_externals" in list:
        manage_exist = remote_list.find("manage_externals")

        if(manage_exist != -1):
            #If remote is present, simply add remote tree to repo:
            retcode = retcall(["git", "read-tree", "--prefix=manage_externals", \
                                "-u", "a48558d890d46c51c2508f97aed64b5dd1716b74"])

            #Quit if git  read-tree fails:
            caller = "git read-tree of manage_externals in {}".format(git_dir)
            quitOnFail(retcode, caller)
        else:
            #If not present, add "manage_externals" remote:
            retcode = retcall(["git", "remote", "add", "-f", "--tags", "manage_externals", \
                               "https://github.com/ESMCI/manage_externals"])

            #Quit if git remote add fails:
            caller = "git remote add of manage_externals in {}".format(git_dir)
            quitOnFail(retcode, caller)

            #Now add remote tree to repo:
            retcode = retcall(["git", "read-tree", "--prefix=manage_externals", \
                                "-u", "a48558d890d46c51c2508f97aed64b5dd1716b74"])

            #Quit if git  read-tree fails:
            caller = "git read-tree of manage_externals in {}".format(git_dir)
            quitOnFail(retcode, caller)

    #Return to original directory:
    os.chdir(currdir)

############################################
###
###SVN/Git repository re-arrangement scripts
###
############################################

def svn_cam_dir_top_move(svn_dir):
    """Moves the 'components/cam' directory
       to the top-level of the local subversion
       repository."""

    #Determine current directory:
    currdir = os.getcwd()

    #Go to new subversion (top-level) directory:
    os.chdir(svn_dir)

    #Move components/cam/bld to top-level svn repository:
    os.rename("components/cam/bld","./bld")

    #Move components/cam/cime_config to top-level svn repository:
    os.rename("components/cam/cime_config","./cime_config")

    #Move components/cam/doc to top-level svn repository:
    os.rename("components/cam/doc","./doc")

    #Move components/cam/src to top-level svn repository:
    os.rename("components/cam/src","./src")

    #Move components/cam/test to top-level svn repository:
    os.rename("components/cam/test","./test")

    #Move component/cam/tools to top-level svn repository:
    os.rename("components/cam/tools","./tools")

    #Remove "components/cam" directory, including "SVN_EXTERNAL_DIRECTORIES" file:
    shutil.rmtree("components")

    #Remove top-level "SVN_EXTERNAL_DIRECTORIES" file:
    os.remove("SVN_EXTERNAL_DIRECTORIES")

    #Return to original directory:
    os.chdir(currdir)

##############################
###
### Beginning of main program
###
##############################
def parse_arguments():
    parser = argparse.ArgumentParser(description='Move selected revisions from SVN to git.',
                                     epilog="""
                                     A <revisions> entry can be a comma-separated list of of the form
                                     start:end where start and end is the inclusive revision range to process.
                                     If end is blank, the more recent revision will be used
                                     If start is blank, the first available revision will be used
                                     Finally, a revision entry can simply be 'BASE' (earliest) or HEAD (latest).
                                     NB: If --branch is passed revisions apply to <branch_name>,
                                     otherwise, they are applied to master.
                                     """)

    parser.add_argument('export_dir', metavar='<SVN_dir>', type=str,
                        help="a temporary staging directory")
    parser.add_argument('git_dir', metavar='<git_dir>', type=str,
                        help="the destination git repository")
    parser.add_argument('repo_url', metavar='<svn URL>', type=str,
                        help="the subversion url to process")
    parser.add_argument('--subdir', dest='subdir', metavar='<subdir>',
                        type=str, nargs=1, default='',
                        help="A subdirectory from which to draw files")
    parser.add_argument('--tags', dest='tag_url', metavar='<tag_url>',
                        type=str, nargs=1, action='store', default='',
                        help="the svn URL for tags related to <tag_url>")
    parser.add_argument('--branch', dest='branch_name', metavar='<branch_name>',
                        type=str, nargs=1, action='store', default='',
                        help="a git branch name to checkout or create")
    parser.add_argument('--author-table', dest='author_table',
                        metavar='<author_translation_filename>',
                        type=str, nargs=1, default='',
                        help="""a filename for translating svn commit authors
                        to author string for use in git commits.
                        Each line has a svn author and a git author separated by a colon.
                        The git author should be in the format 'A U Thor <author@domain>'""")
    parser.add_argument('--ignore-svn-author', dest='git_author',
                        action='store_true', default=False,
                        help="""If False, use the original svn author string
                        for each git commit. If True, the default git author
                        string is used.
                        Note that if the --author-table option is used, this
                        argument is ignored and that table is used unless
                        the svn author is not found in the table.
                        Default is False
                        """)
    parser.add_argument('--default-author', dest='default_author',
                        metavar='[Name <email>]', type=str, nargs=1, default='',
                        help="""An author entry to use when the svn author
                        is not in the author table. This option is ignored if
                        the --author-table argument is not supplied.""")
    parser.add_argument('--use-current-date', dest='current_date',
                        action='store_true', default=False,
                        help="""If True, use current date and time for each git commit.
                        If False, use the original svn commit date and time.
                        Default is False""")
    parser.add_argument('--rev', dest='revisions', metavar="<revision>", type=str,
                        action='append',
                        help="revision, list of revisions or revision range")
    parser.add_argument('--no-external-cfg', dest='no_extern',
                        action='store_true', default=False,
                        help="""If True, the CAM SVN externals will not be modified
                                to work with the manage_externals routine.  If
                                False, the SVN externals will be removed in the
                                new git repository and replaced with Externals_CAM.cfg.
                                The default is False""")
    parser.add_argument('--no-cam-move', dest='no_cam_move',
                        action='store_true', default=False,
                        help="""If True, the components/cam directory will be left
                                in the same location.  If False, all of the cam files
                                will be moved to the top-level of the local git repository.
                                The default is False""")


    args = parser.parse_args()
    return args
# End def parse_arguemnts

###############################################################################
def _main_func():
    revlist = []
    revStart = None # revStart is the first revision in revlist

    args = parse_arguments()
    export_dir = args.export_dir
    git_dir = args.git_dir
    repo_url = args.repo_url
    subdir = args.subdir
    tag_url = args.tag_url
    branch_name = args.branch_name
    author_table = args.author_table
    svn_author  = not args.git_author
    if len(args.default_author) > 0:
        default_author = args.default_author[0]
    else:
        default_author = None
    preserve_dates = not args.current_date
    revisions = args.revisions

    #For externals:
    external = not args.no_extern

    #For CAM code location:
    cam_move = not args.no_cam_move

    export_dir = os.path.abspath(export_dir)
    git_dir = os.path.abspath(git_dir)

    #Script currently doesn't appear to work with Python version 3, so kill
    #script with warning if python 3 or greater is being used:
    if sys.version_info[0] >= 3:
        perr("Script only works with Python 2. Please switch python versions.")

    if len(author_table) > 0:
        auth_table = parseAuthorTable(author_table[0])
    else:
        auth_table = None

    # Create a master list of revision ranges to process
    if revisions is not None:
        for revarg in revisions:
            rlist = revarg.split(",")
            for rev in rlist:
                newrev = SvnRevRange(rev)
                revlist.append(newrev)
                nstart = newrev
                if (revStart is None) or (nstart < revStart.revStart()):
                    revStart = nstart
                # End if
            # End for
        # End for
    # End if

    if (len(branch_name) == 0):
        branch_name = 'master'
    else:
        branch_name = branch_name[0]
    # End if

    # Set the correct URL for the repo
    if (len(subdir) > 0):
        repo_url = os.path.join(repo_url, subdir[0])
    else:
        repo_url = repo_url
    # End if

    # Make sure the git directory is ready to go
    git_setup_dir(git_dir, repo_url, branch_name, revStart, repo_url,
                  auth_table, svn_author, preserve_dates, default_author)
    # Collect all the old svn revision numbers
    gitLog = gitCaptureLog(git_dir)
    gitRevs = [ x.revNum() for x in gitLog ]

    # Create new tag lists:
    tag_rev_list = list()
    tag_str_list = list()

    # Determine the subversion revisions associated with each tag (if any):
    if tag_url:
        print("Processing tags from {}".format(tag_url[0]))
        # Find all the tags:
        svnTags = svn_list(tag_url[0])
        if svnTags is not None:
            for tag in svnTags:
                # Set the correct URL for the repo
                tag_url_full = os.path.join(tag_url[0], tag)
                if subdir:
                    tag_url_full = os.path.join(tag_url_full, subdir[0])
                # End if
                #Dtermine revision associated with tag:
                tagRev = svnLastChangedRev(tag_url_full)
                #Add tag to lists:
                tag_str_list.append(tag)
                tag_rev_list.append(tagRev)
            # End for
        # End if

    # Capture all the revision log info
    svn_log = list()
    for rev in revlist:
        #check if tag lists are non-empty:
        if tag_rev_list:
            # Capture the log messages for range, 'rev' with tag included:
            logs = svn_capture_log(repo_url, rev.revString(), auth_table,
                                   svn_author, preserve_dates,
                                   default_author=default_author,
                                   tag_rev_list=tag_rev_list,
                                   tag_str_list=tag_str_list)
        else:
            # Capture the log messages for range, 'rev'
            logs = svn_capture_log(repo_url, rev.revString(), auth_table,
                                   svn_author, preserve_dates,
                                   default_author=default_author)
        # End if

        if logs:
            msg = "Adding {} revisions from {} to {}"
            print(msg.format(len(logs), rev.revString(), branch_name))
        else:
            print("No revisions found for {}".format(rev.revString()))
        # End if
        for log in logs:
            if log.revNum() not in gitRevs:
                svn_log.append(log)
            else:
                msg = "Skipping revision {}, already in git repo"
                print(msg.format(log.revNum()))
            # End if
        # End for
    # End for

    # Sort the requested svn revisions
    logs = sorted(svn_log, key = lambda x: x.revNum())

    # Process the sorted log revisions
    for log in logs:
        processRevision(export_dir, git_dir, log, external, cam_move)
    # End for
# End _main_func

###############################################################################

if __name__ == "__main__":
    _main_func()
