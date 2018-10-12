#!/bin/bash


RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

rm README.md

echo -e "${GREEN}Replacing project variables and seeding files ...\n${NC}"

echo -e "${GREEN}Install configparser, cause this script needs it ...\n${NC}"
sudo -H -k pip install configparser

source <(cat hack/variables.ini | hack/ini2env.py)

# Seed Placeholders
sed -i "s|{{ PROJECT }}|${project}|g" hack/boilerplate.py.txt hack/boilerplate.py.test.txt .travis.yml README.rst setup.py
sed -i "s|{{ GITHUBORG }}|${githuborg}|g" .travis.yml README.rst setup.py
sed -i "s|{{ COPYRIGHT }}|${copyright}|g" hack/boilerplate.py.txt hack/boilerplate.py.test.txt
sed -i "s|{{ AUTHOR }}|${author}|g" hack/boilerplate.py.txt hack/boilerplate.py.test.txt
sed -i "s|{{ PACKAGE_AUTHOR }}|${package_author}|g" setup.py
sed -i "s|{{ PACKAGE_AUTHOR_EMAIL }}|${package_author_email}|g" setup.py


cat hack/boilerplate.readme.credits.txt >> README.rst
cat hack/boilerplate.py.txt >> "src/${project}.py"
cat hack/boilerplate.py.test.txt >> "tests/test_${project}.py"
mkdir -p "tests/data/test_${project}"
touch "tests/data/test_${project}/.gitkeep"
if [ ! $(which pre-commit) ]; then
	echo -e "${RED}We install a bunch of pre-commit.com hooks"
	echo -e  "to help you produce better code ...\n${NC}"
	sudo -k -H pip install pre-commit
	pre-commit install
else
	pre-commit install
fi

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

	wget -p https://github.com/github/hub/releases/download/${release}/hub-${_platform__type}-${_arch__type}-${release#"v"}.tgz -O /tmp/hub.tgz
	sudo -k tar -vxf /tmp/hub.tgz --directory /usr/local/bin/ --strip-components=2 --wildcards \*/bin/hub
	sudo chmod +x /usr/local/bin/hub
	/usr/local/bin/hub version
	echo 'eval "$(hub alias -s)"' >> ~/.bash_profile
	PATH=$PATH:/usr/local/bin/hub
fi

echo -e "${GREEN}We create https://github.com/${githuborg}/click-odoo-${project}, commit and push ...\n${NC}"

git remote rename origin scaffold || true
hub create "${githuborg}/click-odoo-${project}"

# Git commit
git add .
git commit -m "Customize Project"
git push --set-upstream origin master


echo -e "${GREEN}We let tox manage all virtual environemnts ...\n${NC}"
if [ ! $(which tox) ]; then
	echo -e "${RED}Seems we need to install \`tox\` first\n${NC}"
	sudo -H -k pip install tox
fi


echo -e "${GREEN}We need to make sure you have 2.7 & 3.6 python ...\n${NC}"
sudo -k apt-get install python2.7 python2.7-dev python3.6 python3.6-dev


echo -e "${GREEN}Now we finally tox your environment ...\n${NC}"
echo -e "${RED}That might take a little while.\n${NC}"
tox

echo -e "${RED}If you want to execute tests locally with \`tox\`,\n"
echo -e "you need to make sure the current user can execute \`createdb\`\n"
echo -e "against a local postgres cluster.${NC}"
