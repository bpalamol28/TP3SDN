# Copyright (C) 2016 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#--------->
import json
from ryu.controller import dpset
from ryu.exception import RyuException

from ryu.ofproto import ofproto_v1_0
from ryu.ofproto import ofproto_v1_2
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto import ofproto_v1_4
from ryu.ofproto import ofproto_v1_5

from ryu.lib import ofctl_v1_0
from ryu.lib import ofctl_v1_2
from ryu.lib import ofctl_v1_3
from ryu.lib import ofctl_v1_4
from ryu.lib import ofctl_v1_5

from ryu.app.wsgi import ControllerBase
from ryu.app.wsgi import Response
from ryu.app.wsgi import WSGIApplication

import requests

#<--------

from operator import attrgetter

from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub

supported_ofctl = {
    ofproto_v1_0.OFP_VERSION: ofctl_v1_0,
    ofproto_v1_2.OFP_VERSION: ofctl_v1_2,
    ofproto_v1_3.OFP_VERSION: ofctl_v1_3,
    ofproto_v1_4.OFP_VERSION: ofctl_v1_4,
    ofproto_v1_5.OFP_VERSION: ofctl_v1_5,
}

maxTrafficPort = {}

class TP3StatsController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(TP3StatsController, self).__init__(req, link, data, **config)
        self.dpset = data['dpset']
        self.waiters = data['waiters']

    def addRule(self, req, **_kwargs):
        rule = json.loads(req.body.decode('utf-8'))
        maxTrafficPort[rule['dpid']][rule['port']] = {}
        maxTrafficPort[rule['dpid']][rule['port']]['max'] = rule['max']
        maxTrafficPort[rule['dpid']][rule['port']]['applied'] = False
        return Response(status=200)

    def deleteRule(self, req, **_kwargs):
        rule = json.loads(req.body.decode('utf-8'))
        if (rule['port'] in maxTrafficPort):
            if (maxTrafficPort[rule['dpid']][rule['port']]['applied'] == True):
                datoP = {"dpid": rule["dpid"],"cookie": 0,"table_id": 0,"priority": 100,"flags": 1,"match":{"in_port": stat.port_no},"actions":[]}
                print(requests.post('http://localhost:8080/stats/flowentry/delete_strict', data = json.dumps(datoP)).request.body)
            del maxTrafficPort[rule['dpid']][rule['port']]
        return Response(status=200)

    def modifyRule(self, req, **_kwargs):
        rule = json.loads(req.body.decode('utf-8'))
        if (rule['port'] in maxTrafficPort):
            if (maxTrafficPort[rule['dpid']][rule['port']]['max'] < rule['max']):
                datoP = {"dpid": rule["dpid"],"cookie": 0,"table_id": 0,"priority": 100,"flags": 1,"match":{"in_port": stat.port_no},"actions":[]}
                print(requests.post('http://localhost:8080/stats/flowentry/delete_strict', data = json.dumps(datoP)).request.body)
                maxTrafficPort[rule['dpid']][rule['port']]['applied'] = False
            maxTrafficPort[rule['dpid']][rule['port']]['max'] = rule['max']
        return Response(status=200)

    def getRules(self, req, **_kwargs):
        return Response(content_type='application/json', body=json.dumps(maxTrafficPort))
        

class SimpleMonitor13(simple_switch_13.SimpleSwitch13):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION,
                    ofproto_v1_2.OFP_VERSION,
                    ofproto_v1_3.OFP_VERSION,
                    ofproto_v1_4.OFP_VERSION,
                    ofproto_v1_5.OFP_VERSION]
    _CONTEXTS = {
        'dpset': dpset.DPSet,
        'wsgi': WSGIApplication
    }

    def __init__(self, *args, **kwargs):
        super(SimpleMonitor13, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)

        self.dpset = kwargs['dpset']
        wsgi = kwargs['wsgi']
        self.waiters = {}
        self.data = {}
        self.data['dpset'] = self.dpset
        self.data['waiters'] = self.waiters
        mapper = wsgi.mapper

        wsgi.registory['TP3StatsController'] = self.data
        path = '/monitor'
        uri = path + '/getRules'
        mapper.connect('stats', uri,
                       controller=TP3StatsController, action='getRules',
                       conditions=dict(method=['GET']))

        uri = path + '/addRule'
        mapper.connect('stats', uri,
                       controller=TP3StatsController, action='addRule',
                       conditions=dict(method=['POST']))

        uri = path + '/modifyRule'
        mapper.connect('stats', uri,
                       controller=TP3StatsController, action='modifyRule',
                       conditions=dict(method=['POST']))

        uri = path + '/deleteRule'
        mapper.connect('stats', uri,
                       controller=TP3StatsController, action='deleteRule',
                       conditions=dict(method=['DELETE']))

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
                maxTrafficPort[datapath.id] = {}
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)


    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body

        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match['in_port'],
                                             flow.match['eth_dst'])):
            self.logger.info('%016x %8x %17s %8x %8d %8d',
                             ev.msg.datapath.id,
                             stat.match['in_port'], stat.match['eth_dst'],
                             stat.instructions[0].actions[0].port,
                             stat.packet_count, stat.byte_count)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body

        self.logger.info('datapath         port     ''rx-pkts  rx-bytes rx-error ''tx-pkts  tx-bytes tx-error')
        for stat in sorted(body, key=attrgetter('port_no')):
            if (stat.port_no in maxTrafficPort[ev.msg.datapath.id] and stat.tx_bytes > maxTrafficPort[ev.msg.datapath.id][stat.port_no]["max"] and maxTrafficPort[ev.msg.datapath.id][stat.port_no]["applied"] == False):
                maxTrafficPort[ev.msg.datapath.id][stat.port_no]["applied"] = True
                datoP = {"dpid": ev.msg.datapath.id,"cookie": 0,"table_id": 0,"priority": 100,"flags": 1,"match":{"in_port": stat.port_no},"actions":[]}
                print(requests.post('http://localhost:8080/stats/flowentry/add', data = json.dumps(datoP)).request.body)
            
            self.logger.info('%016x %8x %8d %8d %8d %8d %8d %8d',
                             ev.msg.datapath.id, stat.port_no,
                             stat.rx_packets, stat.rx_bytes, stat.rx_errors,
                             stat.tx_packets, stat.tx_bytes, stat.tx_errors)
