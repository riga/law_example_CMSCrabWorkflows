#!/usr/bin/env bash

# Bootstrap file for batch jobs that is sent with all jobs and
# automatically called by the law remote job wrapper script to find the
# setup.sh file of this example which sets up software and some environment
# variables. All render variables are defined in the workflow base task in analysis/framework.py.

action() {
    # set env variables
    export IS_ON_CRAB="1"
    export ANALYSIS_PATH="${LAW_JOB_HOME}/repo"
    export DATA_PATH="${LAW_JOB_HOME}/data"
    export SOFTWARE_PATH="${DATA_PATH}/software"

    # source the law wlcg tools, mainly for law_wlcg_get_file
    export LCG_DIR="{{lcg_dir}}"
    local lcg_setup="${LCG_DIR}/etc/profile.d/setup-c7-ui-python3-example.sh"
    if [ ! -f "${lcg_setup}" ]; then
        2>&1 echo "lcg setup file not existing: ${lcg_setup}"
        return "1"
    fi
    source "{{wlcg_tools}}" "" || return "$?"

    # load and unpack the software bundle, then source it
    (
        source "${lcg_setup}" "" &&
        mkdir -p "${SOFTWARE_PATH}" &&
        cd "${SOFTWARE_PATH}" &&
        GFAL_PYTHONBIN="$( which python3 )" law_wlcg_get_file '{{software_uris}}' '{{software_pattern}}' "software.tgz" &&
        tar -xzf "software.tgz" &&
        rm "software.tgz"
    ) || return "$?"

    # load the repo bundle
    (
        source "${lcg_setup}" "" &&
        mkdir -p "${ANALYSIS_PATH}" &&
        cd "${ANALYSIS_PATH}" &&
        GFAL_PYTHONBIN="$( which python3 )" law_wlcg_get_file '{{repo_uris}}' '{{repo_pattern}}' "repo.tgz" &&
        tar -xzf "repo.tgz" &&
        rm "repo.tgz"
    ) || return "$?"

    # source the analysis setup
    source "${ANALYSIS_PATH}/setup.sh" ""
}
action
