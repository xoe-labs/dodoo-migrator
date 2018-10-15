# Init the repository


init: chmod-scripts
	editor hack/variables.ini
	editor hack/boilerplate.readme.credits.txt
	hack/init-repo.sh

sync: chmod-scripts
	hack/sync-with-scaffold.sh


contribute:
	echo -e "pip install pre-commit & tox ..."
	sudo -k -H pip install pre-commit tox
	echo -e "apt install python2.7, python3.6 and *-dev ..."
	sudo -k -H apt install python2.7 python2.7-dev python3.6 python3.6-dev
	hack/install-hub.sh
	hub fork
	tox

pypi: chmod-scripts
	hack/add-pypi-deployment-to-travis-file.sh

chmod-scripts:
	chmod +x -R hack
