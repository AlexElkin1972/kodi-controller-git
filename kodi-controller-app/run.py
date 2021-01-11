#!/usr/bin/python
# coding: utf-8
from flask import Flask, request
import requests
import json

import config as cfg
import aliases
from waitress import serve

app = Flask(__name__)
channels = []
tv = {'mute': False, 'source': 'one'}


@app.route('/')
def entry_point():
    return 'Hello World!'


# Rule: {server IP:PORT}/{cfg.SECRET}/channel?request={value} -> Virtual device / TV / Control canals
@app.route('/{}/channel'.format(cfg.SECRET), methods=['GET'])
def chan_point():
    if request.args.get("request") in [None, "", "{value}"]:
        chan = get_chan()
        print("get channel: {}".format(chan))
        return '{{"value": {}}}'.format(chan), 200

    chan = request.args.get("request")
    print(u'command> channel {}'.format(chan))
    r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                      data='{{"id": 1, "jsonrpc": "2.0", "method": "Player.Open", '
                           '"params": {{"item": {{"channelid": {}}}}}}}'.format(chan))
    if r.status_code == 200:
        print("set channel {}".format(request.args.get("request")))
        return '{{"value": {}}}'.format(request.args.get("request")), 200
    else:
        return "Record not found", 400


# Rule: {server IP:PORT}/{cfg.SECRET}/label?request={in}
# NB: This rule NOT for use via virtual device
@app.route('/{}/label'.format(cfg.SECRET), methods=['GET'])
def label_point():
    if request.args.get("request") in [None, "", "{value}"]:
        label = get_label()
        print(u'get label: "{}"'.format(label))
        return u'{{"value": "{}"}}'.format(label), 200

    label = request.args.get("request").upper()
    label = label.replace(u'ПОСТАВЬ КАНАЛ', '').lstrip()
    print(u'command> label {}'.format(label))
    if label != "":
        # Collect aliases for label if any
        label_aliases = [label]
        for alias in aliases.ALIASES:
            if label in aliases.ALIASES[alias]:
                label_aliases.append(alias)
                print (u'\t{}'.format(alias))

        for _label in label_aliases:
            channel_id = [x['channelid'] for x in channels if x['label'].upper() == _label.upper()]
            if len(channel_id) > 0:
                r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                                  data='{{"id": 1, "jsonrpc": "2.0", "method": "Player.Open", '
                                       '"params": {{"item": {{"channelid": {}}}}}}}'.format(channel_id[0]))
                if r.status_code == 200:
                    print("set channel {}".format(channel_id[0]))
                    return '{{"value": {}}}'.format(channel_id[0]), 200

        print(u'NB: Consider register alias for "{}"'.format(label))
    return "Record not found", 400


# Rule: {server IP:PORT}/{cfg.SECRET}/volume?request={value} -> Virtual device / TV / Volume
@app.route('/{}/volume'.format(cfg.SECRET), methods=['GET'])
def volume_point():
    if request.args.get("request") in [None, "", "{value}"]:
        volume = get_volume()
        print(u'get volume: {}'.format(volume))
        return u'{{"value": {}}}'.format(volume), 200

    volume = request.args.get("request")
    print(u'command> volume {}'.format(volume))
    r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                      data='{{"jsonrpc": "2.0", "id": 1, "method": "Application.SetVolume", '
                           '"params": {{"volume": {}}}}}'.format(volume))
    if r.status_code == 200:
        print("set volume {}".format(volume))
        return '{{"value": {}}}'.format(volume), 200

    return "Record not found", 400


# Rule: {server IP:PORT}/{cfg.SECRET}/power?request={value} -> Virtual device / TV / Power
@app.route('/{}/power'.format(cfg.SECRET), methods=['GET'])
def power_point():
    result = {}
    if request.args.get("request") in [None, "", "{value}"]:
        result['value'] = True
        print(u'get power: true')
        return json.dumps(result), 200

    power = request.args.get("request")
    print(u'command> power {}'.format(power))
    if power == "0":
        r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                          data='{"jsonrpc": "2.0", "method": "System.Shutdown", "id": 1}')
        if r.status_code == 200:
            result['value'] = False
            print("set power {}".format(power))
            return json.dumps(result), 200
    if power == "1":
        result['value'] = True
        print("set power {}".format(power))
        return json.dumps(result), 200

    return "Record not found", 400


# Rule: {server IP:PORT}/{cfg.SECRET}/mute?request={value} -> Virtual device / TV / Mute
@app.route('/{}/mute'.format(cfg.SECRET), methods=['GET'])
def mute_point():
    if request.args.get("request") in [None, "", "{value}"]:
        print(u'get mute: {}'.format("1" if tv['mute'] else "0"))
        return u'{{"value": {}}}'.format("1" if tv['mute'] else "0"), 200

    mute = request.args.get("request")
    print(u'command> mute {}'.format(mute))
    # Issue toggle only if need it
    if mute != ("1" if tv['mute'] else "0"):
        r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                          data='{"jsonrpc": "2.0", "method": "Application.SetMute", '
                               '"params": {"mute": "toggle"}, "id": 1}'
                          )
        if r.status_code == 200:
            js = json.loads(r.content)
            tv['mute'] = js['result']
            print("set mute {}".format(format("1" if tv['mute'] else "0")))
            return '{{"value": {}}}'.format(format("1" if tv['mute'] else "0")), 200
        else:
            return "Record not found", 400
    else:
        print("leave mute {}".format(format("1" if tv['mute'] else "0")))
        return '{{"value": {}}}'.format(format("1" if tv['mute'] else "0")), 200


# Rule: {server IP:PORT}/{cfg.SECRET}/source?request={value} -> Virtual device / TV / Source
@app.route('/{}/source'.format(cfg.SECRET), methods=['GET'])
def source_point():
    if request.args.get("request") in [None, "", "{value}"]:
        print(u'get source: {}'.format(tv['source']))
        return u'{{"value": "{}"}}'.format(tv['source']), 200

    source = request.args.get("request")
    print(u'command> source {}'.format(source))
    # Issue source only if it's a valid source (1..10)
    if source in ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']:
        tv['source'] = source
        return u'{{"value": "{}"}}'.format(tv['source']), 200
    else:
        return "Record not found", 400


# Return current playing channel id or -1
def get_chan():
    r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                      data='{"id": "OnPlayGetItem", "jsonrpc": "2.0", "method": "Player.GetItem", '
                           '"params": {"properties": [], "playerid": 1}}')
    if r.status_code == 200:
        js = json.loads(r.content)
        return js["result"]["item"]["id"]
    else:
        return -1


# Return current playing channel label or ""
def get_label():
    r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                      data='{"id": "OnPlayGetItem", "jsonrpc": "2.0", "method": "Player.GetItem", '
                           '"params": {"properties": [], "playerid": 1}}')
    if r.status_code == 200:
        js = json.loads(r.content)
        return js["result"]["item"]["label"]
    else:
        return ""


# Return current volume or "-1"
def get_volume():
    r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                      data='{"jsonrpc": "2.0", "method": "Application.GetProperties", '
                           '"params": {"properties": ["volume"]}, "id": 1}')
    if r.status_code == 200:
        js = json.loads(r.content)
        return js["result"]["volume"]
    else:
        return "-1"


# Catalog channels
def cat_chans():
    result = []
    try:
        # Get channel groups
        r = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                          data='{"jsonrpc": "2.0", "id": 1, "method": "PVR.GetChannelGroups", '
                               '"params": {"channeltype": "tv"}}', timeout=5)
        if r.status_code == 200:
            js = json.loads(r.content)
            for group in js['result']['channelgroups']:
                # Get channel group
                gr = requests.post('{}/jsonrpc'.format(cfg.KODIURL),
                                   data='{{"jsonrpc": "2.0", "id":1, "method": "PVR.GetChannels", '
                                        '"params": {{"channelgroupid": {}}}}}'.format(group['channelgroupid']),
                                   timeout=5)
                if gr.status_code == 200:
                    gjs = json.loads(gr.content)
                    result = result + gjs["result"]["channels"]

        # Check registered aliases for linking with reported channels
        invalid_aliases = []
        for al in aliases.ALIASES:
            if len([x for x in result if x['label'].upper() == al.upper()]) == 0:
                invalid_aliases.append(al)
        if len(invalid_aliases) > 0:
            print ('Followed aliases currently not linked with real channels')
            print(u"; ".join(invalid_aliases))

        print("Kodi reports {} channels".format(len(result)))
        return result

    except requests.exceptions.ConnectTimeout:
        print("Kodi is not responding, exiting...")
        exit(2)


if __name__ == '__main__':
    channels = cat_chans()
    serve(app, host='0.0.0.0', port=cfg.PORT)
