#!/bin/bash

project_name=$(basename "$(pwd)")

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color


echo -e "${GREEN}Replacing project variables and seeding files ...\n${NC}"

# Seed Placeholders
sed -i "s|{{ PROJECT }}|${PROJECT}|" hack/boilerplate.py.txt .travis.yml README.rst setup.py
sed -i "s|{{ GITHUBORG }}|${GITHUBORG}|" .travis.yml README.rst setup.py
sed -i "s|{{ COPYRIGHT }}|${COPYRIGHT}|" hack/boilerplate.py.txt
sed -i "s|{{ AUTHOR }}|${AUTHOR}/" hack/boilerplate.py.txt
sed -i "s|{{ PACKAGE_AUTHOR }}|${PACKAGE_AUTHOR}/" setup.py
sed -i "s|{{ PACKAGE_AUTHOR_EMAIL }}|${PACKAGE_AUTHOR_EMAIL}/" setup.py
sed -i "s|{{ PYPIUSER }}|${PYPIUSER}|" .travis.yml
sed -i "s|{{ PYPITOKEN }}|${PYPITOKEN}|" .travis.yml


cat boilerplate.readme.credits.txt >> README.rst
cat boilerplate.py.txt >> "src/${PROJECT}.py"
cat boilerplate.py.txt >> "test/test_${PROJECT}.py"
mkdir -p "test/data/test_${PROJECT}"
touch "test/data/test_${PROJECT}/.gitkeep"

echo -e "${RED}We install a bunch of pre-commit.com hooks"
echo -e  "to help you produce better code ...\n${NC}"
pip install pre-commit
pre-commit install

if [ ! $(which hub) ]; then
	get_latest_release() {
	  	curl --silent "https://api.github.com/repos/$1/releases/latest" | # Get latest release from GitHub api
	    grep '"tag_name":' |                                            # Get tag line
	    sed -E 's/.*"([^"]+)".*/\1/'                                    # Pluck JSON value
	}
	release=$(get_latest_release "github/hub")
	echo -e "${RED}We install latest 'hub' (${release}), a git shim, to make git lifecyle easier ...\n${NC}"

	case "$(uname -m)" in
                 x86_64) _arch__type="amd64" ;;
    i386/i486/i586/i686) _arch__type="386"   ;;
                   arm*) _arch__type="arm"   ;;
    esac

    case "$(uname)" in
        Linux*)   _platform__type="linux"   ;;
        Darwin*)  _platform__type="darwin"  ;;
        FreeBSD*) _platform__type="freebsd" ;;
        CYGWIN*|MINGW*|MSYS*) _platform__type="windows" ;;
    esac

	wget -q https://github.com/github/hub/releases/download/${release}/hub-${_platform__type}-${_arch__type}-${release#"v"}.tgz -O- | tar -xzO \*/bin/hub > /urs/local/bin/hub
	chmod +x ./urs/local/bin/hub
	hub version
	alias git=hub
fi

echo -e "${GREEN}We create https://github.com/${GITHUBORG}/click-odoo-${PROJECT}, commit and push ...\n${NC}"

git remote rename origin scaffold
git create "${GITHUBORG}/click-odoo-${PROJECT}"

# Git commit
git add .
git commit -m "Customize Project"
git push "${GITHUBORG}" origin

