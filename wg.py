import os
import io
import argparse
import wgconfig
import wgconfig.wgexec as wgexec
import json

import qrcode

from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage
from tinydb.middlewares import CachingMiddleware

from pathlib import Path

with open('config.json', 'r') as f:
    config = json.load(f)

interface = config['Interface']
prefix = config['ClientConfigPrefix']
if prefix is None: prefis = ""

def create_client_config(data:dict):
    name = data['name']
    client = wgconfig.WGConfig(os.path.join(config['ClientConfigsPath'], f'{prefix}{name}.conf'))
    client.add_attr(None, 'PrivateKey', data['key'])
    client.add_attr(None, 'Address', data['IP'])
    dns = config.get('DNS')
    if dns is not None:
        client.add_attr(None, 'DNS', dns)

    peer = config['PublicKey']
    client.add_peer(peer)
    client.add_attr(peer, 'AllowedIPs ', config['allowedIPs'])
    client.add_attr(peer, 'Endpoint', config['Endpoint'])
    client.add_attr(peer, 'PersistentKeepalive ', '25')
    return client

def get_allowed_ip(p:dict):
    return f'{p["IP"]}/32'

def wg_set(p:dict):
    os.system(f"wg set {interface} peer {p['pub']} allowed-ips {get_allowed_ip(p)}")

def chmod(filename:str):
    os.chmod(filename, 0o3400)

def add_peer(args):
    peer = Query()
    t = db.table('peers')
    p = t.get(peer.name == args.name)
    if p is None:
        key_pair = wgexec.generate_keypair()
        new_id = t.all()[-1].doc_id + 2 if len(t.all())>0 else config['ClientStartIP'] if config.get('ClientStartIP') is not None else 2
        p = {
            'name': args.name,
            'key': key_pair[0],
            'pub': key_pair[1],
            'IP': config["clientIP"].format(str(new_id))
        }

        server.add_peer(p['pub'], f'# {args.name}')
        server.add_attr(p['pub'], 'AllowedIPs', get_allowed_ip(p))
        server.write_file()

        client = create_client_config(p)
        client.write_file()
        chmod(client.filename)

        wg_set(p)

        del p['key']
        t.insert(p)

        qr = qrcode.QRCode()
        qr.add_data('\n'.join(client.lines))
        filename = os.path.join(config['ClientConfigsPath'], f'{prefix}{args.name}.qrcode')
        with open(filename, 'w') as f:
            qr.print_ascii(out=f)
        chmod(filename)

    else:
        print('Already exists')

def update_peer(args):
    peer = Query()
    t = db.table('peers')
    p = t.get(peer.name == args.name)
    if p is None:
        raise Exception(f'Peer is not found "{args.name}"')
    wg_set(p)
    print(p)

def del_peer(args):
    peer = Query()
    t = db.table('peers')
    p = t.get(peer.name == args.name)
    if p is None:
        raise Exception(f'Peer is not found "{args.name}"')
    os.system(f"wg set {interface} peer {p['pub']} remove")
    server.del_peer(p['pub'])
    server.write_file()
    t.remove(peer.name == args.name)

def list_peers(args):
    peer = Query()
    t = db.table('peers')
    for p in t.all():
        print(p['name'])

def parse_args():
    parser = argparse.ArgumentParser(description='Wireguard management CLI')
    subparsers = parser.add_subparsers(title='subcommands')

    add_parser = subparsers.add_parser('add', help='Add peer by name if not exists')
    upd_parser = subparsers.add_parser('update', help='Update peer by name')
    del_parser = subparsers.add_parser('delete', help='Delete peer by name')
    list_parser = subparsers.add_parser('list', help='List peers names')

    add_parser.add_argument("name", type=str)
    add_parser.set_defaults(func=add_peer)

    upd_parser.add_argument("name", type=str)
    upd_parser.set_defaults(func=update_peer)

    del_parser.add_argument("name", type=str)
    del_parser.set_defaults(func=del_peer)

    list_parser
    list_parser.set_defaults(func=list_peers)

    return parser.parse_args()

server = wgconfig.WGConfig(interface)
server.read_file()

with TinyDB(config['DB'], storage=CachingMiddleware(JSONStorage)) as db:
    args = parse_args()
    args.func(args)

