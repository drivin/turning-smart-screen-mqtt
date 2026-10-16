# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate a generic three-node theme and example sensor configurations."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / 'examples/themes/MqttClusterRetro92'
NAVY = '4, 8, 28'
WHITE = '235, 245, 255'
MUTED = '140, 165, 195'
FREE = '35, 65, 95'
CYAN = '30, 225, 255'
PINK = '255, 65, 195'
YELLOW = '255, 225, 50'
FONT = 'roboto-mono/RobotoMono-Regular.ttf'


def build():
    sensors = {}
    theme = {'author': 'MQTT extension · Telegraf cluster retro',
             'display': {'DISPLAY_SIZE': '9.2"', 'DISPLAY_ORIENTATION': 'landscape',
                         'DISPLAY_RGB_LED': '0, 0, 0'},
             'static_images': {'RETRO': {'PATH': 'retro-arcade-v1.png', 'X': 0, 'Y': 0,
                                        'WIDTH': 1920, 'HEIGHT': 480}},
             'static_text': {}, 'STATS': {'CUSTOM': {'INTERVAL': 3}}}
    theme['STATS']['CUSTOM']['INTERVAL'] = 10
    custom = theme['STATS']['CUSTOM']
    labels = theme['static_text']

    def text(x, y, width=400, height=32, size=23, color=WHITE):
        return {'SHOW': True, 'X': x, 'Y': y, 'WIDTH': width, 'HEIGHT': height,
                'FONT': FONT, 'FONT_SIZE': size, 'FONT_COLOR': color,
                'BACKGROUND_COLOR': NAVY}

    def label(key, content, x, y, width=400, size=23, color=WHITE):
        labels[key] = dict(text(x, y, width, size+8, size, color), TEXT=content)

    def sensor(key, node, tail, unit='', decimals=1, scale=1):
        sensors[key] = {'label': f'{node} · {tail}', 'topic': f'example/cluster/{node}/{tail}',
                        'kind': 'number', 'unit': unit, 'decimals': decimals,
                        'stale_after': 60, 'history': 60}
        if scale != 1:
            sensors[key]['scale'] = scale

    def pie(key, node, disk_path, cx, cy, radius, color):
        sensor(key, node, f'disk/{disk_path}/used_percent', unit='%')
        custom[key] = {'RADIAL': {'SHOW': True, 'X': cx, 'Y': cy, 'RADIUS': radius,
                                 'WIDTH': radius, 'MIN_VALUE': 0, 'MAX_VALUE': 100,
                                 'ANGLE_START': 0, 'ANGLE_END': 360, 'ANGLE_SEP': 0,
                                 'ANGLE_STEPS': 1, 'CLOCKWISE': True, 'SHOW_TEXT': False,
                                 'BAR_COLOR': color, 'BACKGROUND_COLOR': NAVY,
                                 'DRAW_BAR_BACKGROUND': True, 'BAR_BACKGROUND_COLOR': FREE},
                       'TEXT': text(cx-radius-10, cy+radius+3, 2*radius+36, 26, 19, color)}

    for index, node in enumerate(['node1', 'node2', 'node3']):
        base = [96, 680, 1264][index]
        color = [CYAN, YELLOW, PINK][index]
        prefix = 'Mqtt' + node.capitalize()
        label(node+'_title', node.upper(), base+28, 69, 490, 32, color)
        label(node+'_cpu', 'CPU // TOTAL', base+28, 126, 320, 22)
        key = prefix+'Cpu'
        sensor(key,node,'cpu/cpu-total/usage_active',unit='%')
        custom[key] = {'TEXT': text(base+382, 120, 145, 36, 28, color),
                       'GRAPH': {'SHOW': True, 'X': base+28, 'Y': 165, 'WIDTH': 490,
                                 'HEIGHT': 25, 'MIN_VALUE': 0, 'MAX_VALUE': 100,
                                 'BAR_COLOR': color, 'BACKGROUND_COLOR': FREE}}
        label(node+'_ram', 'RAM // USED / FREE', base+28, 210, 355, 21)
        key=prefix+'RamPercent'
        sensor(key,node,'mem/used_percent',unit='%')
        custom[key]={'TEXT':text(base+382,205,145,36,28,PINK),
                     'GRAPH':{'SHOW':True,'X':base+28,'Y':249,'WIDTH':490,'HEIGHT':25,
                              'MIN_VALUE':0,'MAX_VALUE':100,'BAR_COLOR':PINK,
                              'BACKGROUND_COLOR':'15, 115, 125'}}
        for suffix, tail, x, unit, tint in [('RamUsed','used',base+28,' GiB used',PINK),
                                           ('RamFree','available',base+280,' GiB free',CYAN)]:
            key=prefix+suffix
            sensor(key,node,'mem/'+tail,unit=unit,scale=1/1024**3)
            custom[key]={'TEXT':text(x,281,250,28,18,tint)}
        if node!='node3':
            pie(prefix+'Root',node,'_',base+125,374,44,color)
            label(node+'_root','ROOTFS /',base+205,337,280,25)
            label(node+'_disklegend','USED / FREE',base+205,374,280,18,MUTED)
        else:
            for suffix,path,cx,caption,tint in [('Root','_',base+105,'ROOT /',YELLOW),
                                               ('Usb1','_mnt_usb1',base+280,'USB HDD 1',CYAN),
                                               ('Usb2','_mnt_usb2',base+455,'USB HDD 2',PINK)]:
                label(node+'_'+suffix,caption,cx-62,322,145,18)
                pie(prefix+suffix,node,path,cx,375,39,tint)
    # Second page shares the immutable background; only foreground content changes.
    hardware = {'static_text': labels, 'CUSTOM': custom}
    labels = {}
    custom = {'INTERVAL': 10}
    for index, (node, nic) in enumerate([('node1','eth0'),('node2','eth0'),('node3','eth0')]):
        base = [96,680,1264][index]
        color = [CYAN,YELLOW,PINK][index]
        prefix = 'Mqtt'+node.capitalize()
        label(node+'_title',node.upper(),base+28,69,490,32,color)
        label(node+'_nic','PARENT NIC // '+nic,base+28,126,490,22)
        label(node+'_rx','RX // RECEIVE',base+28,178,490,21,CYAN)
        label(node+'_tx','TX // TRANSMIT',base+28,268,490,21,PINK)
        for suffix,field,y,tint in [('Rx','bytes_recv',211,CYAN),('Tx','bytes_sent',301,PINK)]:
            key=prefix+suffix
            sensor(key,node,f'net/{nic}/{field}',unit=' MiB/s',decimals=2,scale=1/1024**2)
            sensors[key]['rate']=True
            custom[key]={'TEXT':text(base+28,y,490,44,32,tint)}
        key=prefix+'LinkSpeed'
        sensor(key,node,f'net/{nic}/speed',unit=' Mbit/s',decimals=0)
        label(node+'_link','LINK',base+28,383,110,22,MUTED)
        custom[key]={'TEXT':text(base+150,377,365,40,28,color)}
    network = {'static_text': labels, 'CUSTOM': custom}
    def lower(value):
        if isinstance(value,dict):
            if 'Y' in value:
                value['Y'] += 6
            for item in value.values():
                lower(item)
    lower(hardware)
    lower(network)
    theme['MQTT_PAGES']={'INTERVAL':20,'VIEWS':[hardware,network]}
    THEME.mkdir(parents=True,exist_ok=True)
    header='# Generated from tools/build_cluster_theme.py. Native content fits y < 462.\n'
    (THEME/'theme.yaml').write_text(header+yaml.safe_dump(theme,sort_keys=False,allow_unicode=True),encoding='utf-8')
    broker={'host':'mqtt.example.com','port':1883,'tls':False,
            'username_env':'TURZX_MQTT_USER','password_env':'TURZX_MQTT_PASSWORD'}
    for name,host in [('cluster-mqtt.yaml','mqtt.example.com'),('cluster-mqtt-runtime.yaml','mqtt.example.com')]:
        broker['host']=host
        config={'broker':dict(broker),'render':{'batch_frames':True},'sensors':sensors}
        comment='# Example Telegraf scalar topics. Free RAM = Linux MemAvailable. Customize broker, nodes, NICs and mounts.\n'
        (ROOT/'examples'/name).write_text(comment+yaml.safe_dump(config,sort_keys=False,allow_unicode=True),encoding='utf-8')
    print('Generated cluster theme and',len(sensors),'Telegraf sensors.')


if __name__=='__main__':
    build()
