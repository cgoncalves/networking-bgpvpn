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

from sqlalchemy import orm

from neutron.db.models import external_net

from neutron_lib.api.definitions import bgpvpn_vni as bgpvpn_vni_def
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.db import api as db_api
from neutron_lib import exceptions as n_exc

from oslo_log import helpers as log_helpers
from oslo_log import log as logging

from networking_bgpvpn._i18n import _
from networking_bgpvpn.neutron.extensions import bgpvpn as bgpvpn_ext
from networking_bgpvpn.neutron.services.common import utils
from networking_bgpvpn.neutron.services.service_drivers import driver_api
from networking_bgpvpn.neutron.services.service_drivers.ovn.common \
    import config
from networking_bgpvpn.neutron.services.service_drivers.ovn.common \
    import constants
from networking_bgpvpn.neutron.services.service_drivers.ovn import helper


config.register_opts()

LOG = logging.getLogger(__name__)
OVN_DRIVER_NAME = "ovn"


class BGPVPNExternalNetAssociation(n_exc.NeutronException):
    message = _("driver does not support associating an external"
                "network to a BGPVPN")


@db_api.CONTEXT_READER
def network_is_external(context, net_id):
    try:
        context.session.query(external_net.ExternalNetwork).filter_by(
            network_id=net_id).one()
        return True
    except orm.exc.NoResultFound:
        return False


def _log_callback_processing_exception(resource, event, trigger, metadata, e):
    LOG.exception("Error during notification processing "
                  "%(resource)s %(event)s, %(trigger)s, "
                  "%(metadata)s: %(exc)s",
                  {'trigger': trigger,
                   'resource': resource,
                   'event': event,
                   'metadata': metadata,
                   'exc': e})


@registry.has_registry_receivers
class OvnBGPVPNDriver(driver_api.BGPVPNDriver):

    """BGPVPN Service Driver class for OVN"""

    more_supported_extension_aliases = [bgpvpn_vni_def.ALIAS]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ovn_helper = helper.OvnProviderHelper()

    def __del__(self):
        self._ovn_helper.shutdown()

    def _common_precommit_checks(self, bgpvpn):
        # No support yet for specifying route distinguishers
        if bgpvpn.get('route_distinguishers', None):
            raise bgpvpn_ext.BGPVPNRDNotSupported(driver=OVN_DRIVER_NAME)
        # No support yet for specifying route targets
        if bgpvpn.get('route_targets', None):
            raise bgpvpn_ext.BGPVPNRTNotSupported(driver=OVN_DRIVER_NAME)
        # No support yet for specifying import targets
        if bgpvpn.get('import_targets', None):
            raise bgpvpn_ext.BGPVPNITNotSupported(driver=OVN_DRIVER_NAME)
        # No support yet for specifying export targets
        if bgpvpn.get('export_targets', None):
            raise bgpvpn_ext.BGPVPNETNotSupported(driver=OVN_DRIVER_NAME)
        # No support yet for specifying local pref
        if bgpvpn.get('local_pref', None):
            raise bgpvpn_ext.BGPVPNLocalPrefNotSupported(
                driver=OVN_DRIVER_NAME)
        # Only l3 type is supported
        bgp_type = bgpvpn.get('type', None)
        if bgp_type not in constants.OVN_SUPPORTED_BGPVPN_TYPES:
            raise bgpvpn_ext.BGPVPNTypeNotSupported(
                driver=OVN_DRIVER_NAME, type=bgp_type)

    def create_bgpvpn_precommit(self, context, bgpvpn):
        self._common_precommit_checks(bgpvpn)

    def create_bgpvpn_postcommit(self, context, bgpvpn):
        pass

    def delete_bgpvpn_precommit(self, context, bgpvpn):
        bgpvpn_id = bgpvpn.get('id')

        # Delete router associations
        router_assocs = self.get_router_assocs(context, bgpvpn_id)
        for router_assoc in router_assocs:
            self.delete_router_assoc(context, router_assoc.get('id'),
                                     bgpvpn_id)

        net_assocs = self.get_net_assocs(context, bgpvpn_id)
        for net_assoc in net_assocs:
            self.delete_net_assoc(context, net_assoc.get('id'), bgpvpn_id)

    def delete_bgpvpn_postcommit(self, context, bgpvpn):
        pass

    def update_bgpvpn_precommit(self, context, old_bgpvpn, bgpvpn):
        self._common_precommit_checks(bgpvpn)

    def update_bgpvpn_postcommit(self, context, old_bgpvpn, bgpvpn):
        (added_keys, removed_keys, changed_keys) = (
            utils.get_bgpvpn_differences(bgpvpn, old_bgpvpn))
        ATTRIBUTES_TO_IGNORE = set(['name'])
        moving_keys = added_keys | removed_keys | changed_keys
        if len(moving_keys ^ ATTRIBUTES_TO_IGNORE):
            # TODO(cgoncalves)
            pass

    def create_net_assoc_precommit(self, context, net_assoc):
        if network_is_external(context, net_assoc['network_id']):
            raise BGPVPNExternalNetAssociation()

    def create_net_assoc_postcommit(self, context, net_assoc):
        # TODO(cgoncalves)
        pass

    def delete_net_assoc_precommit(self, context, net_assoc):
        pass

    def delete_net_assoc_postcommit(self, context, net_assoc):
        # TODO(cgoncalves)
        pass

    def create_router_assoc_precommit(self, context, router_assoc):
        bgpvpn = self.get_bgpvpn(context, router_assoc['bgpvpn_id'])
        request = {'type': constants.REQ_TYPE_CREATE_ROUTER_ASSOC,
                   'info': {'context': context,
                            'router_association': router_assoc,
                            'bgpvpn': bgpvpn}}
        self._ovn_helper.add_request(request)

    def create_router_assoc_postcommit(self, context, router_assoc):
        pass

    def delete_router_assoc_precommit(self, context, router_assoc):
        request = {'type': constants.REQ_TYPE_DELETE_ROUTER_ASSOC,
                   'info': {'context': context,
                            'router_association': router_assoc}}
        self._ovn_helper.add_request(request)

    def delete_router_assoc_postcommit(self, context, router_assoc):
        pass

    @registry.receives(resources.ROUTER_INTERFACE, [events.AFTER_CREATE])
    @log_helpers.log_method_call
    def registry_router_interface_created(self, resource, event, trigger,
                                          payload=None):
        try:
            context = payload.context
            router_id = payload.resource_id
            port_id = payload.metadata.get('port').get('id')

            filters = {'routers': [router_id]}
            bgpvpns = self.get_bgpvpns(context, filters=filters)

            # Ignore if the router in which a router interface was plugged is
            # not associated to a BGPVPN
            if not bgpvpns:
                return

            request = {'type': constants.REQ_TYPE_ADD_ROUTER_INTERFACE,
                       'info': {'port_id': port_id,
                                'bgpvpn': bgpvpns[0]}}
            self._ovn_helper.add_request(request)
        except Exception as e:
            _log_callback_processing_exception(resource, event, trigger,
                                               payload.metadata, e)


    @registry.receives(resources.ROUTER_GATEWAY, [events.AFTER_CREATE])
    @log_helpers.log_method_call
    def registry_router_gateway_crated(self, resource, event, trigger,
                                       payload=None):
        try:
            context = payload.context
            router_id = payload.resource_id

            filters = {'routers': [router_id]}
            bgpvpns = self.get_bgpvpns(context, filters=filters)

            # Ignore if the router in which a router gateway was plugged is
            # not associated to a BGPVPN
            if not bgpvpns:
                return

            router_assocs = self.get_router_assocs(context, bgpvpns[0]['id'],
                                                   filters=filters)

            request = {'type': constants.REQ_TYPE_CREATE_ROUTER_ASSOC,
                       'info': {'context': context,
                                'router_association': router_assocs[0],
                                'bgpvpn': bgpvpns[0]}}
            self._ovn_helper.add_request(request)
        except Exception as e:
            _log_callback_processing_exception(resource, event, trigger,
                                               payload.metadata, e)
