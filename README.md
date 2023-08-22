TODO

# Example: HTCondor workflows at CERN

This example demonstrates how to create law task workflows that run on the HTCondor batch system at CERN.

The actual payload of the tasks is rather trivial. The workflow consists of 26 tasks which convert an integer between 97 and 122 (ascii) into a character. A single task collects the results in the end and writes all characters into a text file.

Resources: [luigi](http://luigi.readthedocs.io/en/stable), [law](http://law.readthedocs.io/en/latest)


#### 0. At CERN: copy this example to your user space

```shell
mkdir -p /examplepath
cd /examplepath
cp -r /afs/cern.ch/user/m/mrieger/public/law_sw/law/examples/htcondor_at_cern/* .
```


#### 1. Source the setup script (just software and some variables)

```shell
source setup.sh
```


#### 2. Let law index your tasks and their parameters (for autocompletion)

```shell
law index --verbose
```

You should see:

```shell
loading tasks from 1 module(s)
loading module 'analysis.tasks', done

module 'analysis.tasks', 2 task(s):
    - CreateChars
    - CreateAlphabet

written 2 task(s) to index file '/examplepath/.law/index'
```


#### 3. Check the status of the `CreateAlphabet` task

```shell
law run CreateAlphabet --version v1 --print-status -1
```

No tasks ran so far, so no output target should exist yet. You will see this output:

```shell
print task status with max_depth -1 and target_depth 0

0 > CreateAlphabet(version=v1)
│     LocalFileTarget(fs=local_fs, path=$DATA_PATH/CreateAlphabet/v1/alphabet.txt)
│       absent
│
└──1 > CreateChars(workflow=htcondor, branch=-1, branches=, version=v1)
         submission: LocalFileTarget(fs=local_fs, path=$DATA_PATH/CreateChars/v1/htcondor_submission_0To26.json, optional)
           absent
         status: LocalFileTarget(fs=local_fs, path=$DATA_PATH/CreateChars/v1/htcondor_status_0To26.json, optional)
           absent
         collection: TargetCollection(len=26, threshold=26.0)
           absent (0/26)
```


#### 4. Run the `CreateAlphabet` task


```shell
law run CreateAlphabet --version v1 --CreateChars-transfer-logs --CreateChars-poll-interval 30sec
```

The ``CreateChars`` task is a ``HTCondorWorkflow`` by default, but it is also able to run tasks locally. To do so, just add ``--CreateChars-workflow local`` to the command above.

This should take only a few minutes to process, depending on the job queue.

By default, this example uses a local scheduler, which - by definition - offers no visualization tools in the browser. If you want to see how the task tree is built and subsequently run, run ``luigid`` in a second terminal. This will start a central scheduler at *localhost:8082* (the default address). To inform tasks (or rather *workers*) about the scheduler, either add ``--local-scheduler False`` to the ``law run`` command, or set the ``local-scheduler`` value in the ``[luigi_core]`` config section in the ``law.cfg`` file to ``False``.


#### 5. Check the status again

```shell
law run CreateAlphabet --version v1 --print-status -1
```

When step 4 succeeded, all output targets should exist:

```shell
print task status with max_depth -1 and target_depth 0

0 > CreateAlphabet(version=v1)
│     LocalFileTarget(fs=local_fs, path=$DATA_PATH/CreateAlphabet/v1/alphabet.txt)
│       existent
│
└──1 > CreateChars(workflow=htcondor, branch=-1, branches=, version=v1)
         submission: LocalFileTarget(fs=local_fs, path=$DATA_PATH/CreateChars/v1/htcondor_submission_0To26.json, optional)
           existent
         status: LocalFileTarget(fs=local_fs, path=$DATA_PATH/CreateChars/v1/htcondor_status_0To26.json, optional)
           existent
         collection: TargetCollection(len=26, threshold=26.0)
           existent (26/26)
```


#### 6. Look at the results

```shell
cd data
ls */v1/
```


#### 7. Cleanup the results

```shell
law run CreateAlphabet --version v1 --remove-output -1
```
