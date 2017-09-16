#coding: utf-8
""" git branch  [-r | -a] [--abbrev=n | --no-abbrev\n
    git branch [--set-upstream | --track | --no-track] [-l][-f] <branchname> <startpoint>
    git branch (-m | -M) [<oldbranch>] <newbranch>
    git branch (-d | -D) [-r] <branchname>…
    git branch --edit-description [<branchname>]"""

import sys,os
import dulwich
from dulwich import porcelain
from dulwich.walk import Walker
import argparse

from git.gitutils import _get_repo, find_revision_sha, is_ancestor, merge_base, can_ff, any_one, count_commits_between, get_remote_tracking_branch, GitError, remotes, branches
def _format_ref_branch(repo, branch):
    if branch.startswith(b'refs'):
       return branch
    else:
       return os.path.join(b'refs/heads',branch)
def active_branch(repo):
    try:
        active_branch=repo.refs.follow('HEAD')[0][1]
        active_branch=active_branch.split('refs/heads/')[-1]
    except:
        active_branch=None
    return active_branch
def branch(args):
    repo=_get_repo()
    
    parser = argparse.ArgumentParser(prog='git branch'
                                     , description="List, create, or delete branches")
    #list
    list_grp=parser.add_mutually_exclusive_group(required= False)
    list_grp.add_argument('-r','--remotes',action='store_true',help='list or delete remotep tracking branches')
    list_grp.add_argument('-a','--all',action='store_true',help='list both remote and local branches') 
    
    # move type commands
    move_type=parser.add_mutually_exclusive_group(required=False)
    move_type.add_argument('-m','--move', nargs='+', metavar=('[oldbranch]','newbranch'), help='move/rename oldbranch or HEAD')
    move_type.add_argument('-M',nargs='+',metavar=('[oldbranch]','newbranch'),help='move/rename even if branch already exists')

    # delete type commands
    delete_flags=parser.add_mutually_exclusive_group(required=False)
    delete_flags.add_argument('-d','--delete', nargs=1, metavar=('branchname'), help='delete branchname,TODO: branch must be fully merged with upstream ')
    delete_flags.add_argument('-D',nargs=1,metavar=('branchname'),help='Delete a branch irrespective of its merged status.')

    # misc flags
    parser.add_argument('-v','--verbose',action='count', help='When in list mode, show sha1 and commit subject line for each head, along with relationship to upstream branch (if any). If given twice, print the name of the upstream branch, as well (see also git remote show <remote>).')
    parser.add_argument('-f','--force',action='store_true', help='Reset <branchname> to <startpoint> if <branchname> exists already. Without -f git branch refuses to change an existing branch.')
    abbrevgrp=parser.add_mutually_exclusive_group()
    abbrevgrp.add_argument('--abbrev',action='store',nargs='?',help='set number of characters to display in sha',type=int,default=7)
    abbrevgrp.add_argument('--no-abbrev',action='store_const',help='do not abbreviate sha ',const=40,dest='abbrev')
    track_flags=parser.add_mutually_exclusive_group(required=False )

    track_flags.add_argument('--set-upstream',action='store', nargs=2, metavar=('branchname','upstream') ,help='set branchname to track upstream')
    track_flags.add_argument('--no-track', nargs='+',metavar=('branchname','startpoint'),help='set existing branch to not track, or create new branch that doesnt track')
    
    
    # add_branch 
    parser.add_argument('branchname',nargs='?')
    parser.add_argument('startpoint',nargs='?')

    
    parser.add_argument('--edit_description',action='store',nargs='?',metavar='branchname', const=active_branch(repo))
    
    
    result = parser.parse_args(args)

    # combine args
    edit_description=result.edit_description
    delete_branchname=result.delete or result.D
    move_branchname = result.move or result.M
    no_track=result.no_track
    add_branchname = (result.branchname, result.startpoint or active_branch(repo))
    set_upstream= result.set_upstream

    force = result.force or result.D or result.M
    mutual_exclusive_list=( delete_branchname, 
                           move_branchname, 
                           edit_description, 
                           result.branchname, 
                           set_upstream,
                           no_track)
    list_flag=not any_one(mutual_exclusive_list)
    
    if not any_one((list_flag,)+ mutual_exclusive_list):
        raise GitError('too many options specified.\n'+parser.print_help())
        
    if list_flag:
        branch_list(result) 
    elif delete_branchname:
        delete_branch(delete_branchname[0], force , result.remotes, result.verbose)
    elif move_branchname:
        move_branch(move_branchname, force, result.verbose)
    elif add_branchname[0]:
        create_branch(add_branchname[0],add_branchname[1],force,False )
    elif edit_description:
        edit_branch_description(edit_description)
    elif set_upstream:
        add_tracking(set_upstream[0], *( ['origin']+set_upstream[1].split('/'))[-2:])
        print set_upstream[0], format_tracking_branch_desc(repo,set_upstream[0])
    elif no_track:
        if len(no_track)==1:
            remove_tracking(no_track[0])
        else:
            create_branch(no_track[0],no_track[1],force,True)
            
def format_tracking_branch_desc(repo,branchname):
    try:
        remote=get_remote_tracking_branch(repo,branchname)
        mysha=porcelain.parse_commit(repo,branchname).id
        theirsha=porcelain.parse_commit(repo,remote).id
        ahead,behind=count_commits_between(repo,mysha, theirsha)
        return '+{}/-{} relative to {} ({})'.format(ahead,behind,remote,theirsha)
    except KeyError:
        return ''
def edit_branch_description(branchname, description=None):
    description = description or raw_input('enter description:')
    config = _get_repo().get_config()
    if not branchname in branches(_get_repo()):
        GitError('{} is not an existing branch'.format(branchname))
        config.set(('branch',branchname),'description',description)
        config.write_to_path()
        
def branch_list(result):
        # TODO: tracking branches
        N=result.abbrev
        repo = _get_repo()
        if not result.remotes:
            for key in branches(repo):
                sha=porcelain.parse_commit(repo,key).id
                dispval=sha[0:N]  #todo, --abbrev=n
                commitmsg=(repo[sha].message if result.verbose else '').strip()
                tracking=get_remote_tracking_branch(repo,key)
                trackmsg=''
                diffmsg=trackingsha=''
                if tracking:
                    trackingsha=porcelain.parse_commit(repo, tracking).id
                    ahead,behind= count_commits_between(repo,sha,trackingsha)
                    diffmsg='+{}/-{} compare to'.format(ahead,behind) if result.verbose else ''
                    trackmsg='[{} {} {}]'.format(diffmsg,tracking,trackingsha[0:N])
                print (' '.join([('* ' if active_branch(repo) == key else '') + key,  dispval, trackmsg, commitmsg]))
        if result.remotes or result.all:
            for key in branches(repo,remotes=True):
                sha=porcelain.parse_commit(repo,key).id
                dispval=sha[0:N]  #todo, --abbrev=n
                commitmsg=(repo[sha].message if result.verbose else '').strip()
                print (' '.join([('* ' if active_branch(repo) == key else '') + key,  dispval, commitmsg]))

def delete_branch(delete_branchname,force=False,remote=None, verbose=0):
    '''delete a branch.  
    if remote=True, then look in refs/remotes, otherwise check refs/heads
    for local, check if it has a remote tracking branch, and only allow delete if upstream has merged
    '''
    print 'delete',delete_branchname,force,remote
    repo=_get_repo()
    if remote:
        qualified_branch=_format_ref_remote(repo,delete_branchname)
    else:
        qualified_branch=_format_ref_branch(repo,delete_branchname)
        if delete_branchname == active_branch(repo):
            GitError('Cannot delete active branch.  ')


    remote_tracking_branch=get_remote_tracking_branch(repo,delete_branchname)

    if remote_tracking_branch and not force:
        #see if local is ahead of remote
        commits_ahead=count_commits_between(repo,
                                 repo.refs[qualified_branch],
                                 branches(repo,remote=True)[remote_tracking_branch] 
                                 )[0]
        if commits_ahead:
            raise GitError('{0} is ahead of {1} by {2} commits.\nuse git branch -D\n'.format(delete_branchname,
                                    remote_tracking_branch,
                                    commits_ahead))
    print 'removing {} (was {})\n'.format(delete_branchname,repo.refs[qualified_branch])
    del repo.refs[qualified_branch]

    if not remote:
        remove_tracking(delete_branchname)
    #todo reflog
        
def move_branch(movebranch,force,verbose):
    '''move oldbranch (or active_branch) to newbranch. update config if needed'''
    repo=_get_repo()
    oldbranch,newbranch=([active_branch(repo)]+movebranch)[-2:]

    if oldbranch not in branches(repo):
        raise GitError('{} does not exist in branches'.format(oldbranch))
    if newbranch in branches(repo) and not force:
        raise GitError('{} already exists.  use -M to force overwriting'.format(newbranch))
    if newbranch != oldbranch:
        print 'Renaming {} ({}) to {}\n'.format(
        	oldbranch,
        	porcelain.parse_commit(repo,oldbranch).id,
        	newbranch)
        repo.refs.add_if_new(_format_ref_branch(repo,newbranch),porcelain.parse_commit(repo,_format_ref_branch(repo,oldbranch)).id)
        del repo.refs[_format_ref_branch(repo,oldbranch)]
        #todo: reflog
    if oldbranch == active_branch(repo):
        repo.refs.set_symbolic_ref(b'HEAD',newbranch)

        
def remove_tracking(branchname):
    '''remove branch entry from config'''
    # Get repo's config
    config = _get_repo().get_config()
    try:
        del config[('branch', branchname)]['remote']
        del config[('branch', branchname)]['merge']
        if not config[('branch', branchname)]:
            del config[('branch', branchname)]
    except KeyError:
        pass
    
    # Write to disk
    config.write_to_path()
    
        
def add_tracking(branchname, remote, remotebranch):
        # Get repo's config
        config = _get_repo().get_config()

        # Add new entries for remote
        config.set(('branch', branchname), 'remote', remote)
        config.set(('branch', branchname), 'merge', 'refs/heads/'+remotebranch)

        # Write to disk
        config.write_to_path()


def create_branch(new_branch, base_rev, force=False ,no_track=False  ):
        """Try creating a new branch which tracks the given remote
            if such a branch does not exist then branch off a local branch
        """
        repo=_get_repo()
        
        # Already exists
        if new_branch in branches(repo):
            if not force:
                raise GitError("branch %s already exists\n use --force to overwrite anyway" % new_branch)
       
         # fork with new sha
        new_ref = _format_ref_branch(repo,new_branch)
        base_sha=find_revision_sha(repo,base_rev)
        repo.refs[new_ref] = base_sha
        
        #handle tracking, only if this was a remote
        tracking,remote_branch =( ['origin']+base_rev.split('/'))[-2:]  #branch-> origin/branch.  remote/branch stays as is
        qualified_remote_branch=os.path.sep.join([tracking,remote_branch])
        if qualified_remote_branch in branches(repo,remotes=True) and not base_rev in branches(repo):
            if not no_track:
                add_tracking(new_branch,tracking,remote_branch)
            else:
                remove_tracking(new_branch)

        #todo reflog
        return new_ref
    
def test():
    import os
    os.chdir('../..')
    def run(cmd):
        print 'branch ', cmd
        branch(cmd.split())
        print ''
    #run('-d test')
    run('')
    run('-f test origin/master')
    run('')
    print 'delete test: should delete'
    run('-d test')

    print 'set to remote'
    run('test origin/master')
    run('-v')
    try:
        run('test dev')
    except GitError:
        pass
    else:
        print 'did not error!'

    run('-f test dev')
    run('-v')
    run('-m test test2')
if __name__=='__main__':
    branch(sys.argv[1:])
