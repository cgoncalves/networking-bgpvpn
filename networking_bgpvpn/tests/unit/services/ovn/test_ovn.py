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

import copy
from unittest import mock
import webob.exc

from neutron.db import agents_db
from neutron.db import db_base_plugin_v2
from neutron_lib import context as n_context

from networking_bgpvpn.tests.unit.services import test_plugin


class TestCorePluginWithAgents(db_base_plugin_v2.NeutronDbPluginV2,
                               agents_db.AgentDbMixin):
    pass


class TestOvnCommon(test_plugin.BgpvpnTestCaseMixin):
    def setUp(self, plugin=None,
              driver=('networking_bgpvpn.neutron.services.service_drivers.'
                      'ovn.ovn.OvnBGPVPNDriver')):

        self.mock_ovn_helper = mock.patch(
            'networking_bgpvpn.neutron.services.service_drivers.ovn.helper.'
            'OvnProviderHelper').start().return_value

        if not plugin:
            plugin = '%s.%s' % (__name__, TestCorePluginWithAgents.__name__)

        super(TestOvnCommon, self).setUp(service_provider=driver,
                                         core_plugin=plugin)

        # route_targets not supported
        self.bgpvpn_data['bgpvpn'].pop('route_targets')

        self.ctxt = n_context.Context('fake_user', self._tenant_id)

        n_dict = {"name": "netfoo",
                  "tenant_id": self._tenant_id,
                  "admin_state_up": True,
                  "router:external": True,
                  "shared": True}

        self.external_net = {'network':
                             self.plugin.create_network(self.ctxt,
                                                        {'network': n_dict})}


class TestOvnBGPVPNDriver(TestOvnCommon):

    def setUp(self):
        super(TestOvnBGPVPNDriver, self).setUp()

    def test_create_bgpvpn_l3(self):
        bgpvpn_data = copy.copy(self.bgpvpn_data)
        bgpvpn_data['bgpvpn'].update({"type": "l3"})

        # Assert that L3 type is accepted
        bgpvpn_req = self.new_create_request(
            'bgpvpn/bgpvpns', bgpvpn_data)
        res = bgpvpn_req.get_response(self.ext_api)
        self.assertEqual(webob.exc.HTTPCreated.code, res.status_int)

    def test_create_bgpvpn_l2_fails(self):
        bgpvpn_data = copy.copy(self.bgpvpn_data['bgpvpn'])
        bgpvpn_data.update({"type": "l2"})

        # Assert that an error is returned to the client
        bgpvpn_req = self.new_create_request(
            'bgpvpn/bgpvpns', bgpvpn_data)
        res = bgpvpn_req.get_response(self.ext_api)
        self.assertEqual(webob.exc.HTTPBadRequest.code, res.status_int)

    def test_create_bgpvpn_rds_fails(self):
        bgpvpn_data = copy.copy(self.bgpvpn_data)
        bgpvpn_data['bgpvpn'].update({"route_distinguishers": ["4444:55"]})

        # Assert that an error is returned to the client
        bgpvpn_req = self.new_create_request(
            'bgpvpn/bgpvpns', bgpvpn_data)
        res = bgpvpn_req.get_response(self.ext_api)
        self.assertEqual(webob.exc.HTTPBadRequest.code, res.status_int)

    def test_create_bgpvpn_rts_fails(self):
        bgpvpn_data = copy.copy(self.bgpvpn_data)
        bgpvpn_data['bgpvpn'].update({"route_targets": ["4444:55"]})

        # Assert that an error is returned to the client
        bgpvpn_req = self.new_create_request(
            'bgpvpn/bgpvpns', bgpvpn_data)
        res = bgpvpn_req.get_response(self.ext_api)
        self.assertEqual(webob.exc.HTTPBadRequest.code, res.status_int)

    def test_create_bgpvpn_its_fails(self):
        bgpvpn_data = copy.copy(self.bgpvpn_data)
        bgpvpn_data['bgpvpn'].update({"import_targets": ["4444:55"]})

        # Assert that an error is returned to the client
        bgpvpn_req = self.new_create_request(
            'bgpvpn/bgpvpns', bgpvpn_data)
        res = bgpvpn_req.get_response(self.ext_api)
        self.assertEqual(webob.exc.HTTPBadRequest.code, res.status_int)

    def test_create_bgpvpn_ets_fails(self):
        bgpvpn_data = copy.copy(self.bgpvpn_data)
        bgpvpn_data['bgpvpn'].update({"export_targets": ["4444:55"]})

        # Assert that an error is returned to the client
        bgpvpn_req = self.new_create_request(
            'bgpvpn/bgpvpns', bgpvpn_data)
        res = bgpvpn_req.get_response(self.ext_api)
        self.assertEqual(webob.exc.HTTPBadRequest.code,
                         res.status_int)

    def test_create_bgpvpn_local_pref_fails(self):
        bgpvpn_data = copy.copy(self.bgpvpn_data)
        bgpvpn_data['bgpvpn'].update({"local_pref": 100})

        # Assert that an error is returned to the client
        bgpvpn_req = self.new_create_request(
            'bgpvpn/bgpvpns', bgpvpn_data)
        res = bgpvpn_req.get_response(self.ext_api)
        self.assertEqual(webob.exc.HTTPBadRequest.code,
                         res.status_int)
