#!/usr/bin/env python
#
# First create a config file in either /etc or ~/
# Contents should be as follows
#
# -------------------------------------------------
# [global]
# default = https://gitlab.com
# ssl_verify = true
# timeout = 5
# 
# [gitlab]
# url = https://gitlab.com
# private_token = <your private gitlab token here>
# api_version = 4
# -------------------------------------------------
#
# Then you must set an environment variable..
# 
#   PYTHON_GITLAB_CFG=~/.python-gitlab.cfg
# 
# ..or..
#
#   PYTHON_GITLAB_CFG=/etc/python-gitlab.cfg
#
# .. depending on where you created the config file.
#
# USAGE:
#
# mrpatcount.py 24118165 859
#
# Where:
#
#   24118165 is the project ID for ..
#       https://gitlab.com/redhat/rhel/src/kernel/rhel-8
#
#   859 is an MR ID number.
#

import sys
import gitlab

project_id = str(sys.argv[1])
mr_id   = str(sys.argv[2])

gl = gitlab.Gitlab.from_config('gitlab')
gl_project = gl.projects.get(project_id)
mr = gl_project.mergerequests.get(mr_id)
ncommits = len(mr.commits())
print(ncommits)
