# Init the repository


init: chmod-scripts
	editor hack/variables.ini
	editor hack/boilerplate.readme.credits.txt
	hack/init-repo.sh

sync: chmod-scripts
	hack/sync-with-scaffold.sh

pypi: chmod-scripts
	hack/add-pypi-deployment-to-travis-file.sh

chmod-scripts:
	chmod +x -R hack
