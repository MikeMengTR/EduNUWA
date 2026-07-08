#!/usr/bin/env python3
"""M4 快速测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from M4_orchestrator.emitter.teaching_events import generate_teaching_events_v2_stream

events = [
    {'event_id':'evt_0001','type':'board','seq':1,'action':'write_title','content':'函数的基本概念'},
    {'event_id':'evt_0002','type':'speak','seq':2,'text':'今天我们来学习函数的基本概念。'},
    {'event_id':'evt_0003','type':'speak','seq':3,'text':'函数是数学中最重要的概念之一。'},
]

for chunk in generate_teaching_events_v2_stream(events):
    if chunk['chunk_type'] == 'event':
        item = chunk['data']
        print(f'  [{item["start_offset_sec"]:5.1f}s] {item["type"]:7s} {item["_latency_label"]:5s} ')

print('M4 test PASSED')
