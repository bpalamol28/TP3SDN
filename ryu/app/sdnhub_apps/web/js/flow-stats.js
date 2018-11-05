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
var types = {53:"dns", 80:"web", 8080:"web", 443:"web"};
var myChart;

function updateFlowStats() {
    var statsTableBody = document.getElementById('flow-stats-data');
    while (statsTableBody.firstChild) {
            statsTableBody.removeChild(statsTableBody.firstChild);
    }
    var graphData = [0, 0, 0];

    $.getJSON(url.concat("/stats/switches"), function(switches){
        $.each(switches, function(index, dpid){
            var hex_dpid = parseInt(dpid).toString(16);

            $.getJSON(url.concat("/stats/flow/").concat(dpid), function(flows) {
                var flowStats = flows[dpid];

                var tr = document.createElement('TR');
                var numFlows = 0;
                var switchColTd = document.createElement('TD');
                switchColTd.appendChild(document.createTextNode(hex_dpid));
                tr.appendChild(switchColTd);

                var td;

                $.each(flowStats, function(index, obj) {
                    var outPorts = [];
                    if ("actions" in obj) {
                        $.each(obj.actions, function(index, action) {
                            var command = action.split(':')[0];
                            var param = action.split(':')[1];

                            if (command == "OUTPUT") {
                                if (param < 65280) 
                                    outPorts.push(param);
                            }
                        });
                    }
                    if (outPorts.length > 0) {
                        numFlows += 1;
                        var matchFields = new Array("in_port", "dl_src", "dl_dst", "dl_type",
                            "nw_src", "nw_dst", "nw_proto", "tp_src", "tp_dst");

                        if (!("match" in obj)) {
                            obj.match = {};
                        }
                        tipo = "otro";

                        $.each(matchFields, function(index, field) {
                            td = document.createElement('TD');
                            if (field in obj.match)  {
                                value = obj.match[field];
                                if (field == "dl_type") {
                                    value = ethertypeToString(obj.match[field]);
                                } else if (field == "nw_proto"){
                                    value = nwprotoToString(obj.match[field]);
                                } else if (field == "tp_dst"){
                                    if (obj.match[field] in types)
                                        tipo = types[obj.match[field]];
                                } else if (field == "tp_src"){
                                    if (obj.match[field] in types)
                                        tipo = types[obj.match[field]];
                                }

                                td.appendChild(document.createTextNode(value));
                            }
                            else
                                td.appendChild(document.createTextNode("*"));
                            tr.appendChild(td);
                        });

                        td = document.createElement('TD');
                        td.appendChild(document.createTextNode(outPorts));
                        tr.appendChild(td);

                        td = document.createElement('TD');
                        var duration = obj.duration_sec + obj.duration_nsec/1000000000;
                        td.appendChild(document.createTextNode(duration));
                        tr.appendChild(td);

                        td = document.createElement('TD');
                        td.appendChild(document.createTextNode(obj.packet_count));
                        tr.appendChild(td);

                        td = document.createElement('TD');
                        td.appendChild(document.createTextNode(obj.byte_count));
                        tr.appendChild(td);

                        td = document.createElement('TD');
                        td.appendChild(document.createTextNode(tipo));
                        tr.appendChild(td);

                        statsTableBody.appendChild(tr);
                        tr = document.createElement('TR');

                        graphData[(tipo=="web"? 0 : (tipo=="dns"? 1:2))] += obj.byte_count;
                    }
                });

                switchColTd.rowSpan = numFlows;
                fillGraph(graphData);
            });
        });
    });
}

function fillGraph(graphData) {
    var ctx = document.getElementById("typeChart").getContext('2d');
    if (myChart != null){
        myChart.destroy();
    }
    myChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ["web", "dns", "otro"],
            datasets: [{
                label: '#Bytes',
                data: graphData,
                backgroundColor: [
                    'rgba(255, 99, 132, 0.2)',
                    'rgba(54, 162, 235, 0.2)',
                    'rgba(75, 192, 192, 0.2)',
                ],
                borderColor: [
                    'rgba(255,99,132,1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(75, 192, 192, 1)',
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                yAxes: [{
                    ticks: {
                        beginAtZero:true
                    }
                }]
            }
        }
    });
    myChart.resize();
}

updateFlowStats();

var flowStatsIntervalID = setInterval(function(){updateFlowStats()}, 5000);

function stopFlowStatsTableRefresh() {
    clearInterval(flowStatsIntervalID);
}
