# coding: utf-8

"""
Law example tasks to demonstrate HTCondor workflows at CERN.

In this file, some really basic tasks are defined that can be inherited by
other tasks to receive the same features. This is usually called "framework"
and only needs to be defined once per user / group / etc.
"""


import os
import re

import luigi
import law


# the crab workflow implementation is part of a law contrib package
# so we need to explicitly load it, plus others
law.contrib.load("cms", "git", "tasks", "wlcg")


###
# type of examples:
# - all within cmssw, use custom stageout (transfer logs via standard stageout?)
#   - requires gfal in cmssw
#   - still requires repository bundling
#   - software setup in venv (requires software bundling) or on CMSSW python directory?
#
# - all outside cmssw
#   - requires gfal in cmssw for file transfers on remote side
#   - requires repository bundling
#   - requires software bundling (use venv?), and this might be placed inside cmssw env, compatible?
###


class Task(law.Task):
    """
    Base task that we use to force a version parameter on all inheriting tasks, and that provides
    some convenience methods to create local file and directory targets at the default data path.
    """

    task_namespace = ""

    version = luigi.Parameter()

    def store_parts(self):
        parts = (self.__class__.__name__,)

        if self.version is not None:
            parts += (self.version,)

        return parts

    def local_path(self, *path):
        # STORE_PATH is defined in setup.sh
        parts = ("$STORE_PATH",) + self.store_parts() + path
        return os.path.join(*map(str, parts))

    def local_target(self, *path):
        return law.LocalFileTarget(self.local_path(*path))

    def remote_path(self, *path):
        parts = self.store_parts() + path
        return os.path.join(*map(str, parts))

    def remote_target(self, *path):
        return law.wlcg.WLCGFileTarget(self.remote_path(*path))


class CrabWorkflow(law.cms.CrabWorkflow):
    """
    Batch systems are typically very heterogeneous by design, and so is HTCondor. Law does not aim
    to "magically" adapt to all possible HTCondor setups which would certainly end in a mess.
    Therefore we have to configure the base HTCondor workflow in law.contrib.htcondor to work with
    the CERN HTCondor environment. In most cases, like in this example, only a minimal amount of
    configuration is required.
    """

    transfer_logs = luigi.BoolParameter(
        default=False,
        significant=False,
        description="transfer job logs to the output directory; default: False",
    )
    crab_memory = law.BytesParameter(
        default=law.NO_FLOAT,
        unit="MB",
        significant=False,
        description="requested memory in MB; empty value leads to crab's default setting; "
        "empty default",
    )

    def __init__(self, *args, **kwargs):
        super(CrabWorkflow, self).__init__(*args, **kwargs)

        # keep a reference to the BundleRepo requirement to avoid redundant checksum calculations
        self.bundle_repo_req = BundleRepo.req(self)

    def crab_storage_site(self):
        # TODO: maybe merge with lfn base
        return "T2_DE_DESY"

    def crab_output_lfn_base(self):
        return "/store/user/mrieger/law_crab_outputs3"

    def crab_output_directory(self):
        # the directory where submission meta data should be stored
        return law.LocalDirectoryTarget(self.local_path())

    def crab_bootstrap_file(self):
        # each job can define a bootstrap file that is executed prior to the actual job
        # configure it to be shared across jobs and rendered as part of the job itself
        bootstrap_file = law.util.rel_path(__file__, "bootstrap.sh")
        return law.JobInputFile(bootstrap_file, copy=False, render_job=True)

    def crab_workflow_requires(self):
        reqs = super(CrabWorkflow, self).crab_workflow_requires()

        # add repo and software bundling as requirements
        reqs["repo"] = self.bundle_repo_req
        reqs["software"] = BundleSoftware.req(self)

        return reqs

    def crab_job_config(self, config, submit_jobs):
        # include the wlcg specific tools script in the input sandbox
        config.input_files["wlcg_tools"] = law.JobInputFile(
            law.util.law_src_path("contrib/wlcg/scripts/law_wlcg_tools.sh"),
            share=True,
            render=False,
        )

        # customize memory
        if self.crab_memory > 0:
            config.crab.JobType.maxMemoryMB = int(round(self.crab_memory))

        # helper to return uris and a file pattern for replicated bundles
        reqs = self.crab_workflow_requires()
        def get_bundle_info(task):
            uris = task.output().dir.uri(base_name="filecopy", return_all=True)
            pattern = os.path.basename(task.get_file_pattern())
            return ",".join(uris), pattern

        # render_variables are rendered into all files sent with a job
        config.render_variables["lcg_dir"] = os.environ["LCG_DIR"]

        # repo bundle variables
        uris, pattern = get_bundle_info(reqs["repo"])
        config.render_variables["repo_uris"] = uris
        config.render_variables["repo_pattern"] = pattern

        # software bundle variables
        uris, pattern = get_bundle_info(reqs["software"])
        config.render_variables["software_uris"] = uris
        config.render_variables["software_pattern"] = pattern

        return config


class BundleRepo(Task, law.git.BundleGitRepository, law.tasks.TransferLocalFile):

    replicas = luigi.IntParameter(
        default=5,
        description="number of replicas to generate; default: 5",
    )
    version = None

    exclude_files = ["data", ".law"]

    def get_repo_path(self):
        # required by BundleGitRepository
        return os.environ["ANALYSIS_PATH"]

    def single_output(self):
        repo_base = os.path.basename(self.get_repo_path())
        return self.remote_target(f"{repo_base}.{self.checksum}.tgz")

    def get_file_pattern(self):
        path = os.path.expandvars(os.path.expanduser(self.single_output().path))
        return self.get_replicated_path(path, i=None if self.replicas <= 0 else r"[^\.]+")

    def output(self):
        return law.tasks.TransferLocalFile.output(self)

    @law.decorator.log
    @law.decorator.safe_output
    def run(self):
        # create the bundle
        bundle = law.LocalFileTarget(is_tmp="tgz")
        self.bundle(bundle)

        # log the size
        self.publish_message(f"size is {law.util.human_bytes(bundle.stat().st_size, fmt=True)}")

        # transfer the bundle
        self.transfer(bundle)


class BundleSoftware(Task, law.tasks.TransferLocalFile):

    replicas = luigi.IntParameter(
        default=5,
        description="number of replicas to generate; default: 5",
    )
    version = None

    def single_output(self):
        return self.remote_target("software.tgz")

    def get_file_pattern(self):
        path = os.path.expandvars(os.path.expanduser(self.single_output().path))
        return self.get_replicated_path(path, i=None if self.replicas <= 0 else r"[^\.]+")

    @law.decorator.log
    @law.decorator.safe_output
    def run(self):
        software_path = os.environ["SOFTWARE_PATH"]

        # create the local bundle
        bundle = law.LocalFileTarget(software_path + ".tgz", is_tmp=True)

        def _filter(tarinfo):
            if re.search(r"(\.pyc|\/\.git|\.tgz|__pycache__)$", tarinfo.name):
                return None
            return tarinfo

        # create the archive with a custom filter
        bundle.dump(software_path, add_kwargs={"filter": _filter})

        # log the size
        self.publish_message("bundled software archive, size is {}".format(
            law.util.human_bytes(bundle.stat().st_size, fmt=True),
        ))

        # transfer the bundle
        self.transfer(bundle)
