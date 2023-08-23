#!/usr/bin/env bash

# Bootstrap file for batch jobs that is sent with all jobs and
# automatically called by the law remote job wrapper script to find the
# setup.sh file of this example which sets up software and some environment
# variables. All render variables are defined in the workflow base task in analysis/framework.py.
# Depending on the type of workflow used (crab or htcondor), one of the two bootstrap methods is
# called, which is - again - controlled through a render variable (bootstrap_name).

bootstrap_crab() {
    # for crab jobs, predefine some variables, fetch the software and repository bundles, then setup

    # set env variables
    export IS_ON_CRAB="1"
    export ANALYSIS_PATH="${LAW_JOB_HOME}/repo"
    export DATA_PATH="${LAW_JOB_HOME}/data"
    export SOFTWARE_PATH="${DATA_PATH}/software"
    export GRID_USER="{{grid_user}}"

    # source the law wlcg tools, mainly for law_wlcg_get_file
    source "{{wlcg_tools}}" "" || return "$?"

    # prepare the lcg setup (but do not source yet) that provides gfal cli commands
    # which are likely needed by law_wlcg_get_file
    export LCG_DIR="{{lcg_dir}}"
    local lcg_setup="${LCG_DIR}/etc/profile.d/setup-c7-ui-python3-example.sh"
    if [ ! -f "${lcg_setup}" ]; then
        2>&1 echo "lcg setup file not existing: ${lcg_setup}"
        return "1"
    fi

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

bootstrap_htcondor_getenv() {
    # on htcondor with the "getenv" feature enabled (job env is the same as the submission env),
    # simply call the analysis setup script again for htcondor specific adjustments

    source "{{analysis_path}}/setup.sh" ""
}

# invoke the bootstrap method
bootstrap_{{bootstrap_name}} "$@"
