#!/bin/bash

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
