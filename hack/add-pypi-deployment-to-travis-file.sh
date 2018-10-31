#!/bin/bash


source <(cat hack/variables.ini | hack/ini2env.py)

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

SNIPPET="""
jobs:
  include:
  - stage: deploy
    python: 3.6
    if: tag IS present
    deploy:
      provider: pypi
      user: \"{{ PYPI_USER }}\"
      passwrod:
        secure: "\$PYPI_TOKEN"
      distributions: \"sdist bdist_wheel\"
      skip_upload_docs: true
      on:
        repo: \"{{ GITHUBORG }}/click-odoo-{{ PROJECT }}\"
        tags: true
"""


if [ ! $(which travis) ]; then
  echo -e "${RED}We install latest 'travis' to mask your pypi credentials properly ...\n${NC}"

  sudo -k apt install ruby ruby-dev
  sudo gem install travis
fi

read -rp "PyPI username: " PYPI_USER

SNIPPET=${SNIPPET/\{\{ PYPI_USER \}\}/${PYPI_USER}}
SNIPPET=${SNIPPET/\{\{ GITHUBORG \}\}/${githuborg}}
SNIPPET=${SNIPPET/\{\{ PROJECT \}\}/${project}}

echo "${SNIPPET}" >> .travis.yml

read -rp "PyPI password (will be mask with travis): " PYPI_PASSWORD


travis encrypt "PYPI_TOKEN=${PYPI_PASSWORD}" --com --add
