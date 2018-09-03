#!/usr/bin/python

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
        retcode = scall(["svn", "export", repoURL, exportDir])
    else:
        caller = "svnExport -r{} {} {}".format(revstr, repoURL, exportDir)
        retcode = retcall(["svn", "export", "-r{}".format(revstr), repoURL, exportDir])
    # End if
    quitOnFail(retcode, caller)
# End def svnExport

def svnList(url):
    """Call svn list on a  url"""
    caller = "svnList {}".format(url)
    slist = checkOutput(["svn", "list", url])
    entries = []
    if (slist is not None):
        for line in slist.splitlines():
            entries.append(line.rstrip("/"))
        # End for
    # End if

    return entries
# End def svnList

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

def svnCaptureLog(repoURL, revstr, auth_table, svn_auth, keep_dates, tag=None, default_author=None):
    logs = []
    caller = "svnCaptureLog {} {}".format(repoURL, revstr)
    log = checkOutput(["svn", "log", "--stop-on-copy", "-r{}".format(revstr), repoURL])
    nlines = 0
    lines = []
    skip = False
    if (log is not None):
        for line in log.splitlines():
            match = reRevis.match(line)
            if ((not skip) and (nlines > 0)):
                lines.append(line)
                nlines = nlines - 1
                if (nlines == 0):
                    logs.append(SvnLogEntry(rev, who, when, repoURL, lines, tag=tag))
                    del(lines[:])
                    lines = []
                # End if
            elif (match is not None):
                rev = match.group(1).strip()
                who = match.group(2).strip()
                if auth_table is not None:
                    if who in auth_table:
                        who = auth_table[who]
                    elif default_author is not None:
                        print("WARNING: Author, '{}', not found in author table, substituting '{}'".format(who,default_author))
                        auth_table[who] = default_author
                        who = default_author
                    else:
                        print("WARNING: Author, '{}', not found in author table".format(who))
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
# End def svnCaptureLog

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
                    raise ValueError("Bad author table entry, '{}'".format(line))
                else:
                    print("Ignoring incorrectly formatted author entry, '{}'".format(line.strip()))
    except ValueError as e:
        perr(e)
    except Exception as e:
        perr(e)

    return auth_table
# End parseAuthorTable

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

    gitcmd.append("--message={}".format(message))
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

def gitSetupDir(chkdir, repo, branch, rev, repoURL, auth_table, svn_author, preserve_dates, default_author):
    """
    Check to see if directory (chkdir) exists and is okay to use
    Create chkdir (if necessary) and set current branch to master
    returns True unless directory exists but is not correct"""
    caller = "gitSetupDir {}".format(chkdir)
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
                        logs = svnCaptureLog(repoURL, revstart, auth_table, svn_author, preserve_dates, default_author=default_author)
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
# End def gitSetupDir

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
        fname1 = os.path.join(root, file).lstrip("./")
        fname2 = os.path.join(dir2, fname1)
        if (not os.path.exists(os.path.join(dir2, fname1))):
          orphans.append(fname1)
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
            num_copies = num_copies + 1
            shutil.copy2(file1, file2)
            # End if
        # End if
    # End for
  # End for
  os.chdir(currdir)
  return num_copies
# End def copySvn2Git

def processRevision(exportDir, gitDir, log):
  rnum = log.revision()
  tag = log.tag()
  num_changes = 0
  print("Processing revision {}, tag = {}".format(int(rnum), tag))
  svnExport(exportDir, log.url(), rnum)
  orphans1 = FindTreeOrphans(exportDir, gitDir)
  orphans2 = FindTreeOrphans(gitDir, exportDir)
  # Remove files no longer in repo
  for file in orphans2:
    gitRmFile(gitDir, file)
    num_changes = num_changes + 1
  # End for
  # Copy the svn export directory into the working git directory
  # Can't use copytree since the repo directory already exists
  num_changes = num_changes + copySvn2Git(exportDir, gitDir)
  # Add files new to the repo
  for file in orphans1:
    gitAddFile(gitDir, file)
    num_changes = num_changes + 1
  # End for
  # Commit everything
  if num_changes > 0:
    gitCommitAll(gitDir, log.formatLogMessage(), author=log.who(), date=log.when())
  # End if
  if (tag is not None):
    # Apply the tag
    gitApplyTag(gitDir, tag, log.formatLogMessage())
  # End if
# End def processRevision

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
                        type=str, nargs=1, action='append', default='',
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
    svn_author = not args.git_author
    if len(args.default_author) > 0:
        default_author = args.default_author[0]
    else:
        default_author = None
    preserve_dates = not args.current_date
    revisions = args.revisions

    export_dir = os.path.abspath(export_dir)
    git_dir = os.path.abspath(git_dir)

    if len(author_table) > 0:
        auth_table = parseAuthorTable(author_table[0])
    else:
        auth_table = None

    # Create a master list of revision ranges to process
    if (revisions is not None):
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
    gitSetupDir(git_dir, repo_url, branch_name, revStart, repo_url, auth_table, svn_author, preserve_dates, default_author)
    # Collect all the old svn revision numbers
    gitLog = gitCaptureLog(git_dir)
    gitRevs = [ x.revNum() for x in gitLog ]

    # Capture all the revision log info
    svnLog = list()
    for rev in revlist:
        # Capture the log messages for range, 'rev'
        logs = svnCaptureLog(repo_url, rev.revString(), auth_table, svn_author, preserve_dates, default_author=default_author)
        if (len(logs) > 0):
            print("Adding {} revisions from {} to {}".format(len(logs), rev.revString(), branch_name))
        else:
            print("No revisions found for {}".format(rev.revString()))
        # End if
        for log in logs:
            if (log.revNum() not in gitRevs):
                svnLog.append(log)
            else:
                print("Skipping revision {}, already in git repo".format(log.revNum()))
            # End if
        # End for
    # End for

    # Process the requested tags (if any)
    if (len(tag_url) > 0):
        print("Processing tags from {}".format(tag_url[0]))
        # Don't accept tags which predate repo
        minRev = sys.maxsize
        if (len(gitRevs) > 0):
            minRev = min(gitRevs)
        # End if
        svnRevs = [ x.revNum() for x in svnLog ]
        temp = min(svnRevs)
        if (temp < minRev):
            minRev = temp
        # End if
        # Find all the tags
        svnTags = svnList(tag_url[0])
        if (svnTags is not None):
            for tag in svnTags:
                # Set the correct URL for the repo
                tag_url = os.path.join(tag_url[0], tag)
                if (len(subdir) > 0):
                    tag_url = os.path.join(tag_url, subdir[0])
                # End if
                tagRev = svnLastChangedRev(tag_url)
                logs = svnCaptureLog(tag_url, tagRev, auth_table, svn_author, preserve_dates, tag=tag, default_author=default_author)
                log = logs[0]
                temp = log.revNum()
                if temp < minRev:
                    print("Skipping tag revision {}, before repo start".format(temp))
                elif temp in gitRevs:
                    print("Skipping tag revision {}, already in git repo".format(temp))
                elif (temp in svnRevs):
                    print("Skipping tag revision {}, already scheduled".format(temp))
                else:
                    svnLog.append(log)
                # End if
                # XXgoldyXX: Check file size (os.path.getsize())
            # End for
        # End if
    # End if

    # Sort the requested svn revisions
    logs = sorted(svnLog, key = lambda x: x.revNum())

    # Process the sorted log revisions
    for log in logs:
        processRevision(export_dir, git_dir, log)
    # End for
# End _main_func

###############################################################################

if __name__ == "__main__":
    _main_func()
