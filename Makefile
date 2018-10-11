# Init the repository

ENV = $$(cat hack/variables.ini | grep -v "\#" | xargs)

init: chmod-scripts
	editor hack/variables.ini
	editor hack/boilerplate.readme.credits.txt
	env $(ENV) hack/init-repo.sh

sync:
	git pull scaffold master

chmod-scripts:
	chmod +x -R hack
