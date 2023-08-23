# coding: utf-8

"""
Law example tasks to demonstrate workflows using Crab as well as HTCondor at CERN.

In this file, some really basic tasks are defined that can be inherited by
other tasks to receive the same features. This is usually called "framework"
and only needs to be defined once per user / group / etc.
"""


import os
import re
import math

import luigi
import law


# the crab and htcondor workflow implementations are part of law "contrib" packages
# so we need to explicitly load them, plus some others
law.contrib.load("cms", "git", "htcondor", "tasks", "wlcg")


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
    Crab has lots of settings to configure almost every aspects of jobs and law does not aim to
    to "magically" guess all possible settings for you, which would certainly end in a mess.
    Therefore we have to adjust the base Crab workflow in law.contrib.cms to our needs in this
    example, which we do by create a subclass. However, in most cases, as in this example, only a
    minimal amount of configuration is required.
    """

    # example for a parameter whose value is propagated to the crab job configuration
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

    def crab_stageout_location(self):
        # the storage site and base directory on it for crab specific outputs
        return (
            law.config.get_expanded("crab", "storage_element"),
            law.config.get_expanded("crab", "base_directory"),
        )

    def crab_output_directory(self):
        # the directory where submission meta data should be stored
        return law.LocalDirectoryTarget(self.local_path())

    def crab_bootstrap_file(self):
        # each job can define a bootstrap file that is executed prior to the actual job
        # configure it to be shared across jobs and rendered as part of the job itself
        bootstrap_file = law.util.rel_path(__file__, "bootstrap.sh")
        return law.JobInputFile(bootstrap_file, copy=False, render_job=True)

    def crab_workflow_requires(self):
        # definition of requirements for the crab workflow to start
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
        config.render_variables["bootstrap_name"] = "crab"
        config.render_variables["grid_user"] = os.environ["GRID_USER"]
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


class HTCondorWorkflow(law.htcondor.HTCondorWorkflow):
    """
    Batch systems are typically very heterogeneous by design, and so is HTCondor. Law does not aim
    to "magically" adapt to all possible HTCondor setups which would certainly end in a mess.
    Therefore we have to configure the base HTCondor workflow in law.contrib.htcondor to work with
    the CERN HTCondor environment. In most cases, like in this example, only a minimal amount of
    configuration is required.
    """

    # example for a parameter whose value is propagated to the htcondor job configuration
    max_runtime = law.DurationParameter(
        default=1.0,
        unit="h",
        significant=False,
        description="maximum runtime; default unit is hours; default: 1",
    )
    transfer_logs = luigi.BoolParameter(
        default=True,
        significant=False,
        description="transfer job logs to the output directory; default: True",
    )

    def htcondor_output_directory(self):
        # the directory where submission meta data should be stored
        return law.LocalDirectoryTarget(self.local_path())

    def htcondor_bootstrap_file(self):
        # each job can define a bootstrap file that is executed prior to the actual job
        # configure it to be shared across jobs and rendered as part of the job itself
        bootstrap_file = law.util.rel_path(__file__, "bootstrap.sh")
        return law.JobInputFile(bootstrap_file, share=True, render_job=True)

    def htcondor_job_config(self, config, job_num, branches):
        # render_variables are rendered into all files sent with a job
        config.render_variables["bootstrap_name"] = "htcondor_getenv"
        config.render_variables["analysis_path"] = os.getenv("ANALYSIS_PATH")

        # force to run on CC7, http://batchdocs.web.cern.ch/batchdocs/local/submit.html#os-choice
        config.custom_content.append(("requirements", "(OpSysAndVer =?= \"CentOS7\")"))

        # maximum runtime
        config.custom_content.append(("+MaxRuntime", int(math.floor(self.max_runtime * 3600)) - 1))

        # copy the entire environment
        config.custom_content.append(("getenv", "true"))

        # the CERN htcondor setup requires a "log" config, but we can safely set it to /dev/null
        # if you are interested in the logs of the batch system itself, set a meaningful value here
        config.custom_content.append(("log", "/dev/null"))

        return config


class BundleRepo(Task, law.git.BundleGitRepository, law.tasks.TransferLocalFile):
    """
    This task is needed by the CrabWorkflow above as it bundles the example repository and uploads
    it to a remote storage where crab jobs can access it. Each job then fetches and unpacks a bundle
    to be able to access your code before the actual payload commences.
    """

    replicas = luigi.IntParameter(
        default=5,
        description="number of replicas to generate; default: 5",
    )
    version = None

    exclude_files = ["data", ".law"]

    def get_repo_path(self):
        # location of the repository to bundle, required by BundleGitRepository
        return os.environ["ANALYSIS_PATH"]

    def single_output(self):
        # single output target definition, might be used to infer names and locations of replicas
        repo_base = os.path.basename(self.get_repo_path())
        return self.remote_target(f"{repo_base}.{self.checksum}.tgz")

    def get_file_pattern(self):
        # returns a pattern (format "{}") into which the replica number can be injected
        path = os.path.expandvars(os.path.expanduser(self.single_output().path))
        return self.get_replicated_path(path, i=None if self.replicas <= 0 else r"[^\.]+")

    def output(self):
        # the actual output definition, simply using what TransferLocalFile outputs
        return law.tasks.TransferLocalFile.output(self)

    @law.decorator.log
    @law.decorator.safe_output
    def run(self):
        # create the bundle
        bundle = law.LocalFileTarget(is_tmp="tgz")
        self.bundle(bundle)  # method of BundleGitRepository

        # log the size
        self.publish_message(f"size is {law.util.human_bytes(bundle.stat().st_size, fmt=True)}")

        # transfer the bundle
        self.transfer(bundle)  # method of TransferLocalFile


class BundleSoftware(Task, law.tasks.TransferLocalFile):
    """
    This task is needed by the CrabWorkflow above as it bundles the software environment (i.e. the
    venv created by setup.sh) and uploads it to a remote storage where crab jobs can access it.
    Each job then fetches and unpacks a bundle to be able to access your software before the actual
    payload commences.
    """

    replicas = luigi.IntParameter(
        default=5,
        description="number of replicas to generate; default: 5",
    )
    version = None

    def single_output(self):
        # single output target definition, might be used to infer names and locations of replicas
        return self.remote_target("software.tgz")

    def get_file_pattern(self):
        # returns a pattern (format "{}") into which the replica number can be injected
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
        self.transfer(bundle)  # method of TransferLocalFile
