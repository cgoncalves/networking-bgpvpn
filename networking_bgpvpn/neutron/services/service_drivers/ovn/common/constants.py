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

OVN_SUPPORTED_BGPVPN_TYPES = ['l3']

REQ_TYPE_EXIT = 'exit'
REQ_TYPE_CREATE_ROUTER_ASSOC = 'create_router_assoc'
REQ_TYPE_DELETE_ROUTER_ASSOC = 'delete_router_assoc'
REQ_TYPE_ADD_ROUTER_INTERFACE = 'add_router_interface'

OVN_GW_PORT_EXT_ID_KEY = 'neutron:gw_port_id'
OVN_EVPN_VNI_EXT_ID_KEY = 'neutron_bgpvpn:vni'
OVN_EVPN_AS_EXT_ID_KEY = 'neutron_bgpvpn:as'

LRP_PREFIX = "lrp-"
