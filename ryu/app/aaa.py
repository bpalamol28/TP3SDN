"""Simple layer-2 learning switch logic using OpenFlow Protocol v1.3."""

from ryu.base.app_manager import RyuApp
from ryu.controller.ofp_event import EventOFPSwitchFeatures
from ryu.controller.ofp_event import EventOFPPacketIn
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.ofproto.ofproto_v1_2 import OFPG_ANY
from ryu.ofproto.ofproto_v1_3 import OFP_VERSION
from ryu.ofproto import ether
from ryu.ofproto import inet
import time
import datetime
from ryu.lib.mac import haddr_to_bin
from ryu.lib.mac import haddr_to_str

import struct
from ryu import utils

# Topology
# LINC-Switch
#	Port 2:  PC
#	Port 3:  Media Server
#	Port 4:  EPB - classified traffic (eth3)
#	Port 5:  EPB - Data Traffic (eth1)
# 	Port 6:  EPB - Control Traffic (eth2)
#	Port 7:  PC2

class L2Switch(RyuApp):
    OFP_VERSIONS = [OFP_VERSION]
    table = {}

    def spawn(*args, **kwargs):
        def _launch(func, *args, **kwargs):
            # mimic gevent's default raise_error=False behaviour
            # by not propergating an exception to the joiner.
            try:
                func(*args, **kwargs)
            except greenlet.GreenletExit:
                pass
            except:
                # log uncaught exception.
                # note: this is an intentional divergence from gevent
                # behaviour. gevent silently ignores such exceptions.
                LOG.error('hub: uncaught exception: %s',
                          traceback.format_exc())

        return eventlet.spawn(_launch, *args, **kwargs)
    def __init__(self, *args, **kwargs):
        super(L2Switch, self).__init__(*args, **kwargs)

    @set_ev_cls(EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch features reply to install table miss flow entries."""
        datapath = ev.msg.datapath
        [self.install_table_miss(datapath, n) for n in [0, 1]]
	#'''Install ARP Request paths'''
	#self.handle_arp_request(datapath, '10.2.1.1', 6)
	#self.handle_arp_request(datapath, '10.3.1.1', 7)
	#self.handle_arp_request(datapath, '10.4.1.1', 6)
	#print "Installing Layer 2 Match"
	#self.install_l2_match(ofproto, datapath, in_port, eth_dst, eth_src)
	# This is the packet that just came in -- we want to
	# install the rule and also resend the packet.
	#self.install_l2_match(ofproto, datapath, dst_port, eth_src, eth_dst)

	# EPB related rules
	print "Installing Layer 7 RTSP Match"
	# Only activate one at a time
	self.install_experimental_flow(datapath, '10.3.1.1', 8554, 'channel7', 3, 3, 2, 2) #demo
	#self.install_test_flow_udp(datapath, '10.3.1.1', 3)
	self.media_server_flow(datapath, '10.3.1.1', 2, 8554)

	""" Install static flows for just the two host doing RTP/RTCP traffic"""
	self.install_experimental_flow_udp(datapath, '10.2.1.1', '10.3.1.1')
	self.install_experimental_flow_udp(datapath, '10.3.1.1', '10.2.1.1')
	# End of EPB related rules

	""" Also install DPI VLAN parser/popper to port address"""
	self.create_VLAN_to_port(datapath, 4)
	""" Install Media server flows to go through the EPB """
	#self.block_broadcast_flow(datapath, 9)
	#self.block_broadcast_flow(datapath, 10)
	""" Allow ARP Request/Replies"""
	self.allow_arp_request(datapath, 2, 3)
	self.allow_arp_reply(datapath, 3, 2)
	self.allow_arp_request(datapath, 3, 2)
	self.allow_arp_reply(datapath, 2, 3)
	# assuming traffic is from 10.2.1.1/10.4.1.1 are for 10.3.1.1 and vice versa
	self.allow_ip_traffic(datapath, '10.3.1.1', '10.2.1.1', 2)
	self.allow_ip_traffic(datapath, '10.2.1.1', '10.3.1.1', 3)
	self.allow_ip_traffic(datapath, '10.3.1.1', '10.4.1.1', 7)
	self.allow_ip_traffic(datapath, '10.4.1.1', '10.3.1.1', 3)

    def create_match(self, parser, fields):
        """Create OFP match struct from the list of fields."""
        match = parser.OFPMatch()
        for a in fields:
            match.append_field(*a)
        return match

    def create_flow_mod(self, datapath, idle_timeout, hard_timeout, priority,
                        table_id, match, instructions):
        """Create OFP flow mod message."""
        ofproto = datapath.ofproto
        flow_mod = datapath.ofproto_parser.OFPFlowMod(datapath, 0, 0, table_id,
                                                      ofproto.OFPFC_ADD, idle_timeout,
                                                      hard_timeout, priority,
                                                      ofproto.OFPCML_NO_BUFFER,
                                                      ofproto.OFPP_ANY,
                                                      OFPG_ANY, 0,
                                                      match, instructions)
        return flow_mod

    def install_table_miss(self, datapath, table_id):
        """Create and install table miss flow entries."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        empty_match = parser.OFPMatch()
        output = parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                        ofproto.OFPCML_NO_BUFFER)
        write = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                        [output])
        instructions = [write]
        flow_mod = self.create_flow_mod(datapath, 0, 0, 0, table_id,
                                        empty_match, instructions)
        datapath.send_msg(flow_mod)

    # Test to see UDP traffic flows
    def install_test_flow_udp(self, datapath, ip_addr, dst_port):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
	ip_addr = self.ipv4_to_int(ip_addr)
        match = self.create_match(parser,
                                [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_IP),
                                 (ofproto.OXM_OF_IPV4_DST, ip_addr),
                                 (ofproto.OXM_OF_IP_PROTO, 17)])
        output = parser.OFPActionOutput(dst_port, ofproto.OFPCML_NO_BUFFER)
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                              [output])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 120, 0, match, [action])
        datapath.send_msg(flow_mod)

    def install_experimental_flow_udp(self, datapath, src_addr, dst_addr):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        src_addr = self.ipv4_to_int(src_addr)
        dst_addr = self.ipv4_to_int(dst_addr)
# EPB Search Field
# Control port
# Data port
# Polling Interval
# Library ID
# Library Options
        result = self.external_processing('URL', '', 6, 5, 0, 0)
        dpiAction = parser.OFPActionExperimenter(3735929054,result)
	# trial using the ofp action experimenter
	#dpiAction = parser.OFPActionExperimenter(1)
        #UDP RTP/RTCP Test Traffic .... requires more testing
        match = self.create_match(parser,
                                [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_IP),
                                 (ofproto.OXM_OF_IPV4_DST, dst_addr),
                                 (ofproto.OXM_OF_IPV4_SRC, src_addr),
                                 (ofproto.OXM_OF_IP_PROTO, 17)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                              [dpiAction])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 126, 0, match, [action])
        datapath.send_msg(flow_mod)
	print "Installed Basic UDP Rule for External Processing ", self.ipv4_to_str(src_addr), " to ", self.ipv4_to_str(dst_addr)

    def media_server_flow(self, datapath, ip_addr, dst_port, port):
    #TCP SRC RTSP Test Traffic .... requires more testing
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        ip_addr = self.ipv4_to_int(ip_addr)
        output = parser.OFPActionOutput(dst_port, ofproto.OFPCML_NO_BUFFER)
        match = self.create_match(parser,
                                [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_IP),
                                 (ofproto.OXM_OF_IPV4_SRC, ip_addr),
                                 (ofproto.OXM_OF_IP_PROTO, 6),
                                 (ofproto.OXM_OF_TCP_SRC, port)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                                  [output])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 124, 0, match, [action])
        datapath.send_msg(flow_mod)
        print "Installed Media Server Rule returning traffic to go out port ", dst_port

    def allow_ip_traffic(self, datapath, src_ip_addr, dst_ip_addr, dst_port):
 #TCP SRC RTSP Test Traffic .... requires more testing
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        src_ip_addr = self.ipv4_to_int(src_ip_addr)
        dst_ip_addr = self.ipv4_to_int(dst_ip_addr)
        output = parser.OFPActionOutput(dst_port, ofproto.OFPCML_NO_BUFFER)
        match = self.create_match(parser,
                                [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_IP),
                                 (ofproto.OXM_OF_IPV4_SRC, src_ip_addr),
                                 (ofproto.OXM_OF_IPV4_DST, dst_ip_addr)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                                  [output])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 100, 0, match, [action])
        datapath.send_msg(flow_mod)
        print "Installed default traffic for ", src_ip_addr," -> ", dst_ip_addr, " goes out port ",dst_port

    # Drop broadcasting traffic from the cloud
    def block_incoming_traffic(self, datapath, in_port):
 #TCP SRC RTSP Test Traffic .... requires more testing
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        match = self.create_match(parser,
                                    [(ofproto.OXM_OF_IN_PORT, in_port)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                                  [])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 224, 0, match, [action])
        datapath.send_msg(flow_mod)
        print "Block incoming traffic from port ", in_port

    # Allow broadcasting traffic from the cloud
    def allow_arp_request(self, datapath, in_port, dst_port):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        # ARP Request
        output = parser.OFPActionOutput(dst_port, ofproto.OFPCML_NO_BUFFER)
        match = self.create_match(parser,
                                    [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_ARP),
                                     (ofproto.OXM_OF_ARP_OP, 1),
                                     (ofproto.OXM_OF_IN_PORT, in_port)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                                  [output])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 124, 0, match, [action])
        datapath.send_msg(flow_mod)
        print "Allow ARP Requests from port ", in_port, " to port ", dst_port

    def allow_arp_reply(self, datapath, in_port, dst_port):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        # ARP Reply
        output = parser.OFPActionOutput(dst_port, ofproto.OFPCML_NO_BUFFER)
        match = self.create_match(parser,
                                    [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_ARP),
                                     (ofproto.OXM_OF_ARP_OP, 2),
                                     (ofproto.OXM_OF_IN_PORT, in_port)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                                  [output])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 124, 0, match, [action])
        datapath.send_msg(flow_mod)
        print "Allow ARP Reply from port ", in_port, " to port ", dst_port

    # Drop broadcasting traffic from the cloud
    def block_broadcast_flow(self, datapath, in_port):
 #TCP SRC RTSP Test Traffic .... requires more testing
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        match = self.create_match(parser,
                                    [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_ARP),
                                     (ofproto.OXM_OF_ARP_OP, 1),
                                     (ofproto.OXM_OF_IN_PORT, in_port)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                                  [])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 124, 0, match, [action])
        datapath.send_msg(flow_mod)
        print "Block ARP Requests from port ", in_port

    def install_experimental_flow(self, datapath, ip_addr, rtsp_port, vidFile, to_server_reg_Port, to_server_expedite_port, from_server_reg_port, from_server_expedite_port):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        url = "rtsp://%s:%s/%s" % (ip_addr, rtsp_port, vidFile)
        #url = "rtsp://10.3.1.1:8554/channel7"
        # create external processing payload
        polling = 1
        vodType = 0
        port = rtsp_port
        vipPort = to_server_expedite_port
        regularPort = to_server_reg_Port
        returningPort = from_server_reg_port
        returningVIPPort = from_server_expedite_port
        lib_opt = self.library_options(polling, vodType, port, vipPort, regularPort, returningVIPPort,returningPort)
        print "Library Option ",lib_opt
        result = self.external_processing('URL', url, 6, 5, 1, lib_opt)
        dpiActionRTSP = parser.OFPActionExperimenter(3735929054,result)
        #TCP DST RTSP Test Traffic
        ip_addr = self.ipv4_to_int(ip_addr)
        match = self.create_match(parser,
                                [(ofproto.OXM_OF_ETH_TYPE, ether.ETH_TYPE_IP),
                                 (ofproto.OXM_OF_IPV4_DST, ip_addr),
                                 (ofproto.OXM_OF_IP_PROTO, 6),
                                 (ofproto.OXM_OF_TCP_DST, port)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                             [dpiActionRTSP])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 125, 0, match, [action])
        datapath.send_msg(flow_mod)
        #TCP SRC RTSP Test Traffic .... requires more testing
        # send to EPB but do not orchestrate any events ... dpiActionRTSP is already handling that
        result = self.external_processing('URL', '', 6, 5, 0, 0)
        noDPIAction = parser.OFPActionExperimenter(3735929054,result)
        match = self.create_match(parser,
                                [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_IP),
                                 (ofproto.OXM_OF_IPV4_SRC, ip_addr),
                                 (ofproto.OXM_OF_IP_PROTO, 6),
                                 (ofproto.OXM_OF_TCP_SRC, port)])
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                             [noDPIAction])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 124, 0, match, [action])
        #datapath.send_msg(flow_mod)
        print "Experimental Flow done for TCP port ", rtsp_port


    def create_VLAN_to_port(self, datapath, dpi_egress_port):
#have a flow installed that takes VLAN, pop's it, and forward out of the port with that VLAN id
# for all the applicable ports on the switch create a matching parser for VLAN traffic coming out of the EPB switch
	parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
	for m_vid in range(2,12):
# in_port should not be the same as out_port .. Why would I want something to go into the EPB's classified traffic port
# port 6,7 is being used to send data to EPB ... OpenFlow will report an Error if check is not done
		if(m_vid != dpi_egress_port):
			popVlan = parser.OFPActionPopVlan()
			output = parser.OFPActionOutput(m_vid,0)
			match = self.create_match(parser,
                                                [#(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_IP),
                                                 (ofproto.OXM_OF_IN_PORT, dpi_egress_port),
                                                 (ofproto.OXM_OF_VLAN_VID, m_vid)])
			action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                                             [popVlan,output])
			flow_mod = self.create_flow_mod(datapath, 0, 0, 200, 0, match, [action])
			datapath.send_msg(flow_mod)
			print "Created DPI VLAN parser for port ", m_vid

    def create_flow_mod(self, datapath, idle_timeout, hard_timeout, priority,
                        table_id, match, instructions):
        """Create OFP flow mod message."""
        ofproto = datapath.ofproto
        flow_mod = datapath.ofproto_parser.OFPFlowMod(datapath, 0, 0, table_id,
                                                      ofproto.OFPFC_ADD, idle_timeout,
                                                      hard_timeout, priority,
                                                      ofproto.OFPCML_NO_BUFFER,
                                                      ofproto.OFPP_ANY,
                                                      OFPG_ANY, 0,
                                                      match, instructions)
        return flow_mod

    def install_table_miss(self, datapath, table_id):
        """Create and install table miss flow entries."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        empty_match = parser.OFPMatch()
        output = parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                        ofproto.OFPCML_NO_BUFFER)
        write = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                        [output])
        instructions = [write]
        flow_mod = self.create_flow_mod(datapath, 0, 0, 0, table_id,
                                        empty_match, instructions)
        datapath.send_msg(flow_mod)

    def install_regular_flow(self, datapath, in_port, ipv4_src, ipv4_dst):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        #install regular IP flow
        match = self.create_match(parser,
                                [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_IP),
                                 (ofproto.OXM_OF_IP_PROTO, 6),
                                 (ofproto.OXM_OF_IPV4_SRC, ipv4_src),
                                 (ofproto.OXM_OF_IPV4_DST, ipv4_dst)])
        output = parser.OFPActionOutput(in_port, ofproto.OFPCML_NO_BUFFER)
        action = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                              [output])
        flow_mod = self.create_flow_mod(datapath, 0, 0, 129, 0, match, [action])
        datapath.send_msg(flow_mod)
        print "Regular Flow done"

    @set_ev_cls(EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Handle packet_in events."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        table_id = msg.table_id
        fields = msg.match.fields
        ipv4_src_str = "EMPTY"
        ipv4_dst_str = "EMPTY"
        #Install Experimental
        #if table_id == 0:
            #self.install_experimental_flow(datapath)
        #return
        # Extract fields
        for f in fields:
            if f.header == ofproto.OXM_OF_IN_PORT:
                in_port = f.value
            elif f.header == ofproto.OXM_OF_ETH_SRC:
                eth_src = f.value
            elif f.header == ofproto.OXM_OF_ETH_DST:
                eth_dst = f.value
            elif f.header == ofproto.OXM_OF_ETH_TYPE:
                eth_type = f.value
            elif f.header == ofproto.OXM_OF_IPV4_SRC:
                ipv4_src = f.value
            elif f.header == ofproto.OXM_OF_IPV4_DST:
                ipv4_dst = f.value
                ipv4_dst_str = self.ipv4_to_str(ipv4_dst)
                ipv4_dst_str = ipv4_dst_str.strip()
                print "Found DST IP ADDRESS:", ipv4_dst_str
	# Learn the source and fill up routing table
	print "Packet In Retrieved ",(eth_src, in_port)

    def handle_arp_request(self, datapath, ip_addr, dst_port):
        ofproto = datapath.ofproto
        ip_addr = self.ipv4_to_int(ip_addr)
        parser = datapath.ofproto_parser
        match = self.create_match(parser,
                                  [(ofproto.OXM_OF_ETH_TYPE,ether.ETH_TYPE_ARP),
                                   (ofproto.OXM_OF_ARP_OP, 1),
                                   (ofproto.OXM_OF_ARP_TPA, ip_addr)])
        output = parser.OFPActionOutput(dst_port, ofproto.OFPCML_NO_BUFFER)
        test = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                            [output])
        idle_timeout = 0
        hard_timeout = 0
        flow_mod = self.create_flow_mod(datapath, idle_timeout, hard_timeout, 122, 0, match, [test])
        datapath.send_msg(flow_mod)

    def install_l2_match(self, ofproto, datapath, dst_port, frame_src, frame_dst):
        #Install flow entry matching on eth_src in table 0.
        print "Dst Port =", dst_port
        parser = datapath.ofproto_parser
        match = self.create_match(parser,
                                  [(ofproto.OXM_OF_ETH_SRC, frame_src),
                                   (ofproto.OXM_OF_ETH_DST, frame_dst)])
        output = parser.OFPActionOutput(dst_port, ofproto.OFPCML_NO_BUFFER)
        test = parser.OFPInstructionActions(ofproto.OFPIT_WRITE_ACTIONS,
                                            [output])
        idle_timeout = 0
        hard_timeout = 0
        flow_mod = self.create_flow_mod(datapath, idle_timeout, hard_timeout, 123, 0, match, [test])
        datapath.send_msg(flow_mod)

    def flood(self, datapath, in_port, data):
        """Send a packet_out with output to all ports."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        output_all = parser.OFPActionOutput(ofproto.OFPP_ALL,
                                            ofproto.OFPCML_NO_BUFFER)
        packet_out = parser.OFPPacketOut(datapath, 0xffffffff,
                                         in_port,
                                         [output_all], data)
        datapath.send_msg(packet_out)

    def ipv4_to_str(self, integre):
        ip_list = [str((integre >> (24 - (n * 8)) & 255)) for n in range(4)]
        return '.'.join(ip_list)

    def ipv4_to_int(self, string):
        ip = string.split('.')
        assert len(ip) == 4
        i = 0
        for b in ip:
            b = int(b)
            i = (i << 8) | b
        return i

    '''Creates a external processing payload to send to the data path'''
    def external_processing(self, field_type, url, control_port, data_port, lib_id, lib_options):
        if (field_type == 'URL'):
            epb_search_field_type = [0,0,1]
        if (field_type == 'Delay'):
            epb_search_field_type = [0,0,2]
        if (field_type == 'Jitter'):
            epb_search_field_type = [0,0,3]
        if (field_type == 'Loss'):
            epb_search_field_type = [0,0,4]
        epb_search_field_type = struct.pack("!3B", *epb_search_field_type)
        expected_size = 40
	epb_search_field_len = struct.pack("!B", expected_size)
        size = len(url)
        pad_len = expected_size - size
        epb_search_value = struct.pack("!"+("B"*size), *map(ord,url))
        # pad the remaining length with x00
        epb_search_value += struct.pack("!"+("B"*pad_len), *(pad_len*[0]))
        control_port = struct.pack("!B", control_port)
        data_port = struct.pack("!B", data_port)
        lib_id = struct.pack("!B", lib_id)
        lib_options = '{0:08b}'.format(lib_options)
        # Library Options is a 9 byte attribute
        len_ = utils.round_up(len(lib_options),72)
        pad_len = len_ - len(lib_options)
        lib_options_binary = str(lib_options)+("0"*pad_len)
        first_byte = int(lib_options_binary[:8], 2)
        next_four_bytes = int(lib_options_binary[8:40], 2)
        final_four_bytes = int(lib_options_binary[40:], 2)
        lib_options = struct.pack("!BII", first_byte, next_four_bytes, final_four_bytes)
        result = control_port+data_port+lib_id+lib_options+epb_search_field_type+epb_search_field_len+epb_search_value
        return result

    ''' Creates the Library Options value '''
    def library_options(self, polling, vodType, port, fromClientVipPort, fromClientRegularPort, toClientVIPPort, toClientRegularPort):
        if polling == 1:
            polling = 128
        port = hex(port)
        arr = [polling+vodType, int(port[2:4], 16), int(port[4:], 16), fromClientVipPort, fromClientRegularPort, toClientVIPPort,toClientRegularPort,0,0]
        result = ''.join(format(x,'02x') for x in arr)
        result = int(result,16)
        return result
