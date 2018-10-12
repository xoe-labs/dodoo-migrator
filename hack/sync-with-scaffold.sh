#!/bin/bash
set +x
# Record conflitct resolution
git config rerere.enabled true

# Fetch Scaffold
git fetch scaffold master

# Marge, you might need to do a conflict resolution the first time
if ! eval "git merge --no-commit --no-ff scaffold/master" ; then
	true
fi

# Protect files from beeing merged from scaffold
git reset -- README.md
git checkout -- README.rst
git checkout -- setup.cfg
git clean -f -d
git commit
