#!/bin/env python
#
# LUNARC HPC Desktop On-Demand graphical launch tool
# Copyright (C) 2017-2020 LUNARC, Lund University
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Jobs module

This module provides classes for supported job types.
"""


import os
import sys
import subprocess
import time
from subprocess import Popen, PIPE, STDOUT


class Job(object):
    """Class describing a SLURM jobs"""

    def __init__(self, account="", partition="", time="00:60:00"):
        """Initialise default class variables"""

        self.script = ""
        self.id = -1
        self.status = ""

        self.magic = "#!/bin/bash"
        self.name = "gui_interactive"
        self.nodes = ""
        self.tasksPerNode = 1
        self.cpusPerNode = -1
        self.exclusive = False
        self.time = time
        self.nodeCount = 1
        self.memory = -1
        self.account = account
        self.partition = partition
        self.node = ""
        self.submitNode = False
        self.constraints = []
        self.gres = ""
        self.oversubscribe = False
        self.module_list = []

        self.scriptLines = []
        self.customLines = []

        self._process_output = False
        self.update_processing = False

        self._create_script()

    def add_constraint(self, constraint):
        """Add constraint (feature)"""
        self.constraints.append(constraint)

    def clear_constraints(self):
        self.constraints = []

    def add_script(self, line):
        self.scriptLines.append(line)

    def add_option(self, option):
        self.add_script("#SBATCH " + option)

    def add_module(self, name, version=""):
        self.module_list.append([name, version])

    def clear_script(self):
        self.scriptLines = []
        self.customLines = []
        self.constraints = []
        self.module_list = []

    def _create_script(self):

        self.scriptLines = []

        self.add_script(self.magic)
        self.add_script("")

        if self.account != "":
            self.add_option("-A %s" % self.account)

        if self.submitNode:
            self.add_option("-w %s" % self.node)
        else:
            if self.partition != "":
                self.add_option("-p %s" % self.partition)

        if self.nodeCount >= 0:
            self.add_option("-N %d" % self.nodeCount)

        if self.tasksPerNode >= 0:
            self.add_option("--ntasks-per-node=%d" % self.tasksPerNode)

        self.add_option("--time=%s" % self.time)

        if self.gres != "":
            self.add_option("--gres=%s" % self.gres)

        if self.memory > 0:
            self.add_option("--mem=%d" % self.memory)

        if self.exclusive:
            self.add_option("--exclusive")

        if self.oversubscribe:
            self.add_option("--oversubscribe")

        if len(self.constraints) > 0:
            if len(self.constraints) == 1:
                self.add_option("--constraint=%s" % self.constraints[0])
            else:
                constraint_string = "&".join(self.constraints)
                self.add_option("--constraint=%s" % constraint_string)

        self.add_option("-J %s" % self.name)
        self.add_script("")
        self.add_script('echo "Starting at `date`"')
        self.add_script('echo "Running on hosts: $SLURM_NODELIST"')
        self.add_script('echo "Running on $SLURM_NNODES nodes."')
        self.add_script('echo "Running on $SLURM_NPROCS processors."')
        self.add_script('echo "SLURM JobID $SLURM_JOB_ID processors."')
        self.add_script('echo "Node has $SLURM_CPUS_ON_NODE processors."')
        self.add_script('echo "Node has $SLURM_MEM_PER_NODE total memory."')
        self.add_script('echo "Node has $SLURM_MEM_PER_CPU memory per cpu."')
        self.add_script('echo "Current working directory is `pwd`"')
        self.add_script('echo "Current path is $PATH"')
        self.add_script('')

        for module in self.module_list:
            module_name = module[0]
            module_version = module[1]

            if module_version == "":
                self.add_script('module load %s' % (module_name))
            else:
                self.add_script('module load %s/%s' % (module_name, module_version))

        self.script = "\n".join(self.scriptLines + self.customLines)

    def add_custom_script(self, line):
        self.customLines.append(line)

    def update(self):
        self._create_script()

    def set_process_output(self, flag):
        self._process_output = flag

    def get_process_output(self):
        return self._process_output

    def do_process_output(self, output_lines):
        pass

    def do_update_processing(self):
        pass

    def __str__(self):
        return self.script

    process_output = property(get_process_output, set_process_output)


class PlaceHolderJob(Job):
    """Placeholder job running acting as master process"""

    def __init__(self, account="", partition="", time="00:30:00"):
        Job.__init__(self, account, partition, time)
        self.add_custom_script('while true; do date; sleep 5; done')
        self.update()


class JupyterNotebookJob(Job):
    """Jupyter notebook job"""

    def __init__(self, account="", partition="", time="00:30:00", notebook_module="Anaconda3"):
        Job.__init__(self, account, partition, time)
        self.notebook_url = ""
        self.process_output = True
        self.notebook_module = notebook_module

        self.add_module(self.notebook_module)

        self.add_custom_script("unset XDG_RUNTIME_DIR")
        self.add_custom_script('jupyter-notebook --no-browser --ip=$HOSTNAME')
        self.add_custom_script("module list")
        self.add_custom_script("which python")

    def on_notebook_url_found(self, url):
        """Event method called when notebook has been found"""
        print("Notebook found: "+url)

    def do_process_output(self, output_lines):
        """Process job output"""

        Job.do_process_output(self, output_lines)

        if self.process_output:
            for line in output_lines:
                if line.find("?token=") != -1:
                    parts = line.split()
                    if len(parts) == 4:
                        self.notebook_url = parts[3]
                        self.process_output = False

                        self.on_notebook_url_found(self.notebook_url)


class JupyterLabJob(Job):
    """Jupyter lab job"""

    def __init__(self, account="", partition="", time="00:30:00", jupyterlab_module="Anaconda3"):
        Job.__init__(self, account, partition, time)
        self.notebook_url = ""
        self.process_output = True
        self.jupyterlab_module = jupyterlab_module

        self.add_module(self.jupyterlab_module)

        self.add_custom_script("unset XDG_RUNTIME_DIR")
        self.add_custom_script('jupyter-lab --no-browser --ip=$HOSTNAME')
        self.add_custom_script("module list")
        self.add_custom_script("which python")

    def on_notebook_url_found(self, url):
        """Event method called when notebook has been found"""
        print("Lab found: "+url)

    def do_process_output(self, output_lines):
        """Process job output"""

        Job.do_process_output(self, output_lines)

        if self.process_output:
            for line in output_lines:
                if line.find("?token=") != -1:
                    parts = line.split()
                    if len(parts) == 4:
                        self.notebook_url = parts[3]
                        self.process_output = False

                        self.on_notebook_url_found(self.notebook_url)


class VMJob(Job):
    """Special Job for starting VM:s"""

    def __init__(self, account="", partition="", time="00:30:00"):
        """Class constructor"""
        super().__init__(account, partition, time)
        self.notebook_url = ""
        self.process_output = False
        self.update_processing = True
        #self.add_custom_script("sleep infinity")
        self.add_custom_script("while true; do date; sleep 5; done")
        self.hostname = ""
        self.oversubscribe = True
        self.memory = 100
        self.gres = "win10m"
        self.nodeCount = -1
        self.tasksPerNode = -1

    def do_update_processing(self):
        """Check for vm job ip file"""

        home_dir = os.getenv("HOME")

        store_dir = os.path.join(home_dir, ".lhpc")
        job_host_filename = os.path.join(
            store_dir, "vm_host_%s.ip" % str(self.id))

        if os.path.exists(job_host_filename):
            with open(job_host_filename) as f:
                hostname = f.readlines()[0].strip()

            self.update_processing = False
            self.hostname = hostname
            self.on_vm_available(hostname)

    def on_vm_available(self, hostname):
        """Callback when job ib file found."""
        print("VM vailable: "+hostname)
