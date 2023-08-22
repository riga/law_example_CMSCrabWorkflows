#!/usr/bin/env bash

action() {
    local shell_is_zsh="$( [ -z "${ZSH_VERSION}" ] && echo "false" || echo "true" )"
    local this_file="$( ${shell_is_zsh} && echo "${(%):-%x}" || echo "${BASH_SOURCE[0]}" )"
    local this_dir="$( cd "$( dirname "${this_file}" )" && pwd )"


    #
    # setup variables
    #

    # paths
    export ANALYSIS_PATH="${this_dir}"
    export DATA_PATH="${DATA_PATH:-${ANALYSIS_PATH}/data}"
    export SOFTWARE_PATH="${SOFTWARE_PATH:-${DATA_PATH}/software}"
    export VENV_PATH="${SOFTWARE_PATH}/venv"
    export STORE_PATH="${DATA_PATH}/store"
    export JOB_PATH="${DATA_PATH}/jobs"

    # flags
    export IS_ON_CRAB="${IS_ON_CRAB:-0}"
    export IS_ON_HTCONDOR="${IS_ON_HTCONDOR:-0}"
    export IS_REMOTE_JOB="0"
    if [ "${IS_ON_CRAB}" != "0" ] || [ "${IS_ON_HTCONDOR}" != "0" ]; then
        IS_REMOTE_JOB="1"
    fi

    # other vars
    export VIRTUAL_ENV_DISABLE_PROMPT="1"


    #
    # software setup
    #

    # gfal2
    export LCG_DIR="${LCG_DIR:-/cvmfs/grid.cern.ch/centos7-ui-200122}"
    if [ ! -d "${LCG_DIR}" ]; then
        >&2 echo "lcg directory ${LCG_DIR} not existing"
        return "1"
    fi
    source "${LCG_DIR}/etc/profile.d/setup-c7-ui-python3-example.sh" "" || return "$?"

    # venv
    local software_flag="${VENV_PATH}/.installed"
    if [ ! -f "${software_flag}" ]; then
        # this should fail in remote jobs
        if [ "${IS_REMOTE_JOB}" == "1" ]; then
            >&2 echo "venv is missing, but cannot be installed in remote jobs"
            return "1"
        fi

        # install
        echo "setup venv at ${VENV_PATH}"
        rm -rf "${VENV_PATH}"
        mkdir -p "$( dirname "${VENV_PATH}" )"
        python3 -m venv --copies "${VENV_PATH}" || return "$?"
        source "${VENV_PATH}/bin/activate" "" || return "$?"
        pip install -I -U pip setuptools luigi six || return "$?"

        # make it relocatable
        make_venv_relocatable "${VENV_PATH}" || return "$?"

        touch "${software_flag}"
    else
        # source
        source "${VENV_PATH}/bin/activate" "" || return "$?"
    fi

    # additional exports
    export PATH="${ANALYSIS_PATH}/bin:${PATH}"
    export PYTHONPATH="${ANALYSIS_PATH}:${ANALYSIS_PATH}/modules/law:${PYTHONPATH}"


    #
    # law setup
    #

    export LAW_HOME="${this_dir}/.law"
    export LAW_CONFIG_FILE="${this_dir}/law.cfg"

    [ "${IS_REMOTE_JOB}" = "0" ] && source "$( law completion )" ""


    return "0"
}

make_venv_relocatable() {
    # check arguments
    local venv_path="$1"
    if [ ! -d "${venv_path}" ] || [ ! -f "${venv_path}/bin/activate" ]; then
        2>&1 echo "no venv existing at ${venv_path}"
        return "1"
    fi

    # remove csh and fish support
    rm -f "${venv_path}"/bin/activate{.csh,.fish}

    # replace absolute paths in the activation file
    sed -i -r \
        's/(VIRTUAL_ENV)=.+/\1="$( cd "$( dirname "$( [ ! -z "${ZSH_VERSION}" ] \&\& echo "${(%):-%x}" || echo "${BASH_SOURCE[0]}" )" )" \&\& dirname "$( \/bin\/pwd )" )"/' \
        "${venv_path}/bin/activate" || return "$?"

    # use /usr/bin/env in shebang's of bin scripts
    local f
    for f in $( find "${venv_path}" -type f ); do
        # must be readable and executable
        if [ -r "${f}" ] && [ -x "${f}" ]; then
            sed -i -r "s/#\!\/.+\/bin\/(python[\\\/]*)/#\!\/usr\/bin\/env \1/" "$f" || return "$?"
        fi
    done
}

action "$@"
