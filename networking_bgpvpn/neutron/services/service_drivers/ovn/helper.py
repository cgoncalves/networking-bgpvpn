#    Copyright 2021 Red Hat, Inc. All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import queue
import threading

from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.db import api as db_api
from neutron_lib import constants as n_lib_consts
from neutron_lib.plugins import directory
from oslo_config import cfg
from oslo_log import log as logging
from ovs.stream import Stream

from networking_bgpvpn.neutron.services.service_drivers.ovn.common \
    import config
from networking_bgpvpn.neutron.services.service_drivers.ovn.common \
    import constants
from networking_bgpvpn.neutron.services.service_drivers.ovn.ovsdb \
    import impl_idl_ovn

LOG = logging.getLogger(__name__)


class OvnProviderHelper():

    def __init__(self):
        self._requests = queue.Queue()
        self._helper_thread = threading.Thread(target=self._request_handler)
        self._helper_thread.daemon = True
        self._check_and_set_ssl_files()
        self._init_bgpvpn_actions()
        self._subscribe()
        self._helper_thread.start()

    def _subscribe(self):
        registry.subscribe(self._post_fork_initialize,
                           resources.PROCESS,
                           events.AFTER_INIT)

    def _post_fork_initialize(self, resource, event, trigger, payload=None):
        # We need to open a connection to OVN Northbound database for
        # each worker so that we can process the BGPVPN requests.
        self.ovn_nbdb = impl_idl_ovn.OvnNbIdlForBgpVpn()
        self.ovn_nbdb_api = self.ovn_nbdb.start()

    def _init_bgpvpn_actions(self):
        self._bgpvpn_request_func_maps = {
            constants.REQ_TYPE_CREATE_ROUTER_ASSOC: self.create_router_assoc,
            constants.REQ_TYPE_DELETE_ROUTER_ASSOC: self.delete_router_assoc,
            constants.REQ_TYPE_ADD_ROUTER_INTERFACE: self.add_router_interface,
        }

    def _check_and_set_ssl_files(self):
        priv_key_file = config.get_ovn_nb_private_key()
        cert_file = config.get_ovn_nb_certificate()
        ca_cert_file = config.get_ovn_nb_ca_cert()

        if priv_key_file:
            Stream.ssl_set_private_key_file(priv_key_file)

        if cert_file:
            Stream.ssl_set_certificate_file(cert_file)

        if ca_cert_file:
            Stream.ssl_set_ca_cert_file(ca_cert_file)

    def _request_handler(self):
        while True:
            request = self._requests.get()
            request_type = request['type']
            if request_type == constants.REQ_TYPE_EXIT:
                break

            request_handler = self._bgpvpn_request_func_maps.get(request_type)
            try:
                if request_handler:
                    request_handler(request['info'])
                self._requests.task_done()
            except Exception:
                # If any unexpected exception happens we don't want the
                # notify_loop to exit.
                # TODO(cgoncalves): The resource(s) we were updating status for
                # should be cleaned-up
                LOG.exception('Unexpected exception in request_handler')

    def _execute_commands(self, commands):
        with self.ovn_nbdb_api.transaction(check_error=True) as txn:
            for command in commands:
                txn.add(command)

    def shutdown(self):
        self._requests.put({'type': constants.REQ_TYPE_EXIT})
        self._helper_thread.join()
        self.ovn_nbdb.stop()
        del self.ovn_nbdb_api

    def add_request(self, req):
        self._requests.put(req)

    def create_router_assoc(self, info):
        LOG.debug('Creating router association in OVN Northbound database...')

        context = info['context']
        router_assoc = info['router_association']
        bgpvpn = info['bgpvpn']
        router_id = router_assoc['router_id']
        external_ids = {
            constants.OVN_EVPN_VNI_EXT_ID_KEY: str(bgpvpn.get('vni')),
            constants.OVN_EVPN_AS_EXT_ID_KEY: str(cfg.CONF.ovn.bgp_as)}

        filters = {'device_id': [router_id],
                   'device_owner': n_lib_consts.ROUTER_PORT_OWNERS}

        with db_api.CONTEXT_READER.using(context):
            router_ports = directory.get_plugin().get_ports(context, filters)

        # Add VNI to router ports
        port_ids = []
        for iface in router_ports:
            lsp = self.ovn_nbdb_api.lsp_get(
                iface['id']).execute(check_error=True)
            port_ids.append(lsp.uuid)

        commands = []
        for port_id in port_ids:
            commands.append(
                self.ovn_nbdb_api.db_set(
                    'Logical_Switch_Port', port_id,
                    ('external_ids', external_ids)))
        self._execute_commands(commands)

        LOG.debug('Created router association in OVN Northbound database!')

    def delete_router_assoc(self, info):
        LOG.debug('Deleting router association in OVN Northbound database...')

        context = info['context']
        router_assoc = info['router_association']
        router_id = router_assoc['router_id']

        filters = {'device_id': [router_id],
                   'device_owner': n_lib_consts.ROUTER_PORT_OWNERS}
        with db_api.CONTEXT_READER.using(context):
            router_ports = directory.get_plugin().get_ports(context, filters)

        # Remove VNI from router ports
        port_ids = []
        for iface in router_ports:
            lsp = self.ovn_nbdb_api.lsp_get(
                iface['id']).execute(check_error=True)
            port_ids.append(lsp.uuid)

        commands = []
        for port_id in port_ids:
            commands.append(
                self.ovn_nbdb_api.db_remove(
                    'Logical_Switch_Port', port_id,
                    'external_ids', (constants.OVN_EVPN_VNI_EXT_ID_KEY)))
        self._execute_commands(commands)

        LOG.debug('Deleted router association in OVN Northbound database!')

    def add_router_interface(self, info):
        LOG.debug('Adding router interface in OVN Northbound database...')

        port_id = info['port_id']
        bgpvpn = info['bgpvpn']
        external_ids = {
            constants.OVN_EVPN_VNI_EXT_ID_KEY: str(bgpvpn.get('vni')),
            constants.OVN_EVPN_AS_EXT_ID_KEY: str(cfg.CONF.ovn.bgp_as)}

        lsp = self.ovn_nbdb_api.lsp_get(port_id).execute(check_error=True)
        self.ovn_nbdb_api.db_set(
            'Logical_Switch_Port', lsp.uuid,
            ('external_ids', external_ids)).execute(check_error=True)

        LOG.debug('Added router interface in OVN Northbound database!')

    def remove_router_interface(self, info):
        LOG.debug('Removing router interface in OVN Northbound database...')

        port_id = info['port_id']

        lsp = self.ovn_nbdb_api.lsp_get(port_id).execute(check_error=True)
        self.ovn_nbdb_api.db_remove(
            'Logical_Switch_Port', lsp.uuid, 'external_ids',
            (constants.OVN_EVPN_VNI_EXT_ID_KEY)).execute(check_error=True)

        LOG.debug('Deleted router interface in OVN Northbound database!')
