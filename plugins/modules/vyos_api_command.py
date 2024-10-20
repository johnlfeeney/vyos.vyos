#!/usr/bin/python
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = """
module: vyos_api_command
author: Nathaniel Case (@Qalthos)
short_description: Run one or more api commands on VyOS devices
description:
- The api command module allows running one or more commands on remote devices running
  VyOS.  This module can also be introspected to validate key parameters before returning
  successfully.  If the conditional statements are not met in the wait period, the
  task fails.
version_added: 2.7.0
extends_documentation_fragment:
- vyos.vyos.vyos
options:
  host:
    description:
    - The host to connect to.
    required: true
    type: str
  key:
    description:
    - The api secret key used for the connection.
    required: true
    type: str
  port:
    description:
    - The port the hosts listens on for the connection.
    type: int
    default: 443
  commands:
    description:
    - The ordered set of commands to execute on the remote device running VyOS.  The
      output from the command execution is returned to the playbook.  If the I(wait_for)
      argument is provided, the module is not returned until the condition is satisfied
      or the number of retries has been exceeded.
    required: true
    type: list
    elements: raw
  wait_for:
    description:
    - Specifies what to evaluate from the output of the command and what conditionals
      to apply.  This argument will cause the task to wait for a particular conditional
      to be true before moving forward.  If the conditional is not true by the configured
      I(retries), the task fails. See examples.
    type: list
    elements: str
    aliases:
    - waitfor
  match:
    description:
    - The I(match) argument is used in conjunction with the I(wait_for) argument to
      specify the match policy. Valid values are C(all) or C(any).  If the value is
      set to C(all) then all conditionals in the wait_for must be satisfied.  If the
      value is set to C(any) then only one of the values must be satisfied.
    default: all
    type: str
    choices:
    - any
    - all
  retries:
    description:
    - Specifies the number of retries a command should be tried before it is considered
      failed. The command is run on the target device every retry and evaluated against
      the I(wait_for) conditionals.
    default: 10
    type: int
  interval:
    description:
    - Configures the interval in seconds to wait between I(retries) of the command.
      If the command does not pass the specified conditions, the interval indicates
      how long to wait before trying the command again.
    default: 1
    type: int
  timeout:
    description:
      - The socket level timeout in seconds
    type: int
    default: 30
  validate_certs:
    description:
      - If C(no), SSL certificates will not be validated.
      - This should only set to C(no) used on personally controlled sites using self-signed certificates.
    type: bool
    default: yes
  client_cert:
    description:
      - PEM formatted certificate chain file to be used for SSL client authentication.
      - This file can also include the key as well, and if the key is included, I(client_key) is not required
    type: path
  client_key:
    description:
      - PEM formatted file that contains your private key to be used for SSL client authentication.
      - If I(client_cert) contains both the certificate and key, this option is not required.
    type: path
  ca_path:
    description:
      - PEM formatted file that contains a CA certificate to be used for validation
    type: path
  use_proxy:
    description:
      - If C(no), it will not use a proxy, even if one is defined in an environment variable on the target hosts.
    type: bool
    default: yes
notes:
- Tested against VyOS 1.3.0 (equuleus).
"""

EXAMPLES = """
- name: show configuration on ethernet devices eth0 and eth1
  vyos.vyos.vyos_api_command:
    host: vyos.lab.local
    key: 12345
    validate_certs: False
    commands:
    - show interfaces ethernet {{ item }}
  with_items:
  - eth0
  - eth1

- name: run multiple commands and check if version output contains specific version
    string
  vyos.vyos.vyos_api_command:
    host: vyos.lab.local
    key: 12345
    validate_certs: False
    commands:
    - show version
    - show hardware cpu
    wait_for:
    - result[0] contains 'VyOS 1.3.0'
"""

RETURN = """
stdout:
  description: The set of responses from the commands
  returned: always apart from low level errors (such as action plugin)
  type: list
  sample: ['...', '...']
stdout_lines:
  description: The value of stdout split into a list
  returned: always
  type: list
  sample: [['...', '...'], ['...'], ['...']]
failed_conditions:
  description: The list of conditionals that have failed
  returned: failed
  type: list
  sample: ['...', '...']
warnings:
  description: The list of warnings (if any) generated by module based on arguments
  returned: always
  type: list
  sample: ['...', '...']
"""
import time

from ansible.module_utils._text import to_text
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.parsing import (
    Conditional,
)
from ansible_collections.ansible.netcommon.plugins.module_utils.network.common.utils import (
    to_lines,
)
from ansible_collections.vyos.vyos.plugins.module_utils.network.vyos.vyos import (
    run_api_commands,
)
from ansible_collections.vyos.vyos.plugins.module_utils.network.vyos.vyos import (
    vyos_argument_spec,
)

API_COMMANDS = ['show', 'generate', 'set', 'delete', 'comment']


def parse_commands(module, warnings):
    commands = module.params["commands"]

    for item in list(commands):
        if not item.startswith(tuple(API_COMMANDS)):
            msg = "'%s' - is not an allowed command" % item
            module.fail_json(msg)

        if module.check_mode:
            if not item.startswith("show"):
                warnings.append(
                    "Only show commands are supported when using check mode, not "
                    "executing %s" % item
                )
                commands.remove(item)

    return commands


def main():
    spec = dict(
        host=dict(type='str', required=True),
        port=dict(type='int', default=443),
        key=dict(type='str', no_log=True, required=True),
        timeout=dict(type='int', default=30),
        validate_certs=dict(type='bool', default=True),
        client_cert=dict(type='path', default=None),
        client_key=dict(type='path', default=None),
        ca_path=dict(type='path', default=None),
        use_proxy=dict(type='bool', default=True),
        commands=dict(type="list", required=True, elements="raw"),
        wait_for=dict(type="list", aliases=["waitfor"], elements="str"),
        match=dict(default="all", choices=["all", "any"]),
        retries=dict(default=10, type="int"),
        interval=dict(default=1, type="int"),
    )

    spec.update(vyos_argument_spec)

    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)

    warnings = list()
    result = {"changed": False, "warnings": warnings}
    commands = parse_commands(module, warnings)
    wait_for = module.params["wait_for"] or list()
    direct_fail = False

    try:
        conditionals = [Conditional(c) for c in wait_for]
    except AttributeError as exc:
        module.fail_json(msg=to_text(exc))
    host = module.params['host']
    port = module.params['port']
    key = module.params['key']
    socket_timeout = module.params['timeout']
    ca_path = module.params['ca_path']
    retries = module.params["retries"]
    interval = module.params["interval"]
    match = module.params["match"]

    for item in range(retries):
        responses = run_api_commands(module, commands, direct_fail)

        for item in list(conditionals):
            if item(responses):
                if match == "any":
                    conditionals = list()
                    break
                conditionals.remove(item)

        if not conditionals:
            break

        time.sleep(interval)

    if conditionals:
        failed_conditions = [item.raw for item in conditionals]
        msg = "One or more conditional statements have not been satisfied"
        module.fail_json(msg=msg, failed_conditions=failed_conditions)

    result.update(
        {"stdout": responses, "stdout_lines": list(to_lines(responses))}
    )

    module.exit_json(**result)


if __name__ == "__main__":
    main()
