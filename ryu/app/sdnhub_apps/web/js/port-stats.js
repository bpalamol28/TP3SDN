/*
 * Copyright (C) 2014 SDN Hub
 *
 * Licensed under the GNU GENERAL PUBLIC LICENSE, Version 3.
 * You may not use this file except in compliance with this License.
 * You may obtain a copy of the License at
 *
 *    http://www.gnu.org/licenses/gpl-3.0.txt
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied.
 */

var url = "http://" + location.hostname + ":8080";
var rulesR = {};

function updatePortStats() {
    var statsTableBody = document.getElementById('port-stats-data');
    while (statsTableBody.firstChild) {
            statsTableBody.removeChild(statsTableBody.firstChild);
    }

    $.getJSON(url.concat("/monitor/getRules"), function(rules){
        rulesR = rules;
    });

    $.getJSON(url.concat("/stats/switches"), function(switches){
        $.each(switches, function(index, dpid){
            var hex_dpid = parseInt(dpid).toString(16);

            $.getJSON(url.concat("/stats/port/").concat(dpid), function(ports) {
                var portStats = ports[dpid];

                var tr = document.createElement('TR');
                var physicalPorts = 0;
                var switchColTd = document.createElement('TD');
                switchColTd.appendChild(document.createTextNode(hex_dpid));
                tr.appendChild(switchColTd);

                $.each(portStats, function(index, obj) {
                    if (obj.port_no < 65280) {
                        physicalPorts += 1;
                        var statsArray = new Array(obj.port_no, obj.rx_packets, obj.rx_bytes, obj.rx_dropped, obj.rx_errors, obj.tx_packets, obj.tx_bytes, obj.tx_dropped, obj.tx_errors);

                        $.each(statsArray, function(index, value) {
                            var td = document.createElement('TD');
                            td.appendChild(document.createTextNode(value));
                            tr.appendChild(td);
                        });
                        input = document.createElement('INPUT');
                        input.setAttribute("id", "entrada"+index);
                        input.setAttribute("type", "number");
                        btn = document.createElement('BUTTON');
                        btn.innerHTML = 'click me';
                        btn.onclick = function(){
                            if (document.getElementById('entrada'+index).value == 0) {
                                $.ajax({type: "DELETE",url: url.concat("/monitor/deleteRule"),data: '{"dpid":'+ dpid +',"port":'+index+', "max": '+document.getElementById('entrada'+index).value+'}',success: function(){},dataType:"json"});
                            } else {
                                $.post(url.concat("/monitor/addRule"), '{"dpid":'+ dpid +',"port":'+index+', "max": '+document.getElementById('entrada'+index).value+'}', function() {}, "json");
                            }
                            //document.getElementById('entrada'+index).value = 0;
                        };
                        if(dpid in rulesR && index in rulesR[dpid]){
                            input.value = rulesR[dpid][index]["max"];
                        }
                        tr.appendChild(input);
                        tr.appendChild(btn);
                        statsTableBody.appendChild(tr);
                        tr = document.createElement('TR');
                    }
                });

                switchColTd.rowSpan = physicalPorts;
            });
        });
    });
}

updatePortStats();

var portStatsIntervalID = setInterval(function(){updatePortStats()}, 5000);

function stopPortStatsTableRefresh() {
    clearInterval(portStatsIntervalID);
}
