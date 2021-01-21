#!/usr/bin/python
# coding: utf-8
import json
import os.path
from icecream import ic
from datetime import datetime
from dateutil.parser import parse as duparse

import requests
from flask_sqlalchemy import SQLAlchemy

from run import db
import config as cfg
import aliases

# https://www.freecodecamp.org/news/sqlalchemy-makes-etl-magically-easy-ab2bd0df928/
# db = SQLAlchemy(app)
# if not os.path.isfile(str(app.config['SQLALCHEMY_DATABASE_URI']).replace('sqlite:///', './')):
#     run.db.create_all()


def cat_chans():
    """
    Catalog TV channels via Kodi request and store it in the database. Invalid aliases reported to stdout.
    :return:
    None
    """
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

        # Drop content of Channel
        Channel.query.delete()
        db.session.commit()

        # Populate Channel with Kodi channels
        for r in result:
            channel = Channel(id=r['channelid'], label=r['label'])
            db.session.add(channel)
        db.session.commit()

        # Validate KODI channels with XML TV channels
        print("Following KODI channels are not linked to XMLTV programs:")
        channels = [x for x in Channel.query.all()]
        for chan in channels:
            xmlchannels = [x for x in XMLChannel.query.filter(XMLChannel.ulabel == chan.ulabel).all()]
            if len(xmlchannels) == 0:
                print (u'\t{}'.format(chan.label))

    except requests.exceptions.ConnectTimeout:
        print("Kodi is not responding, exiting...")
        exit(2)


class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(128), nullable=False)
    ulabel = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return '<Channel %r>' % self.label

    def __init__(self, **kwargs):
        super(Channel, self).__init__(**kwargs)
        # have to do custom stuff due lack of unicode upper in SQLite3
        self.ulabel = self.label.upper()


class XMLChannel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(128), nullable=False)
    ulabel = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return '<Channel %r>' % self.label

    def __init__(self, **kwargs):
        super(XMLChannel, self).__init__(**kwargs)
        # have to do custom stuff due lack of unicode upper in SQLite3
        self.ulabel = self.label.upper()


class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(128), nullable=False)
    start = db.Column(db.DateTime, nullable=False)
    stop = db.Column(db.DateTime, nullable=False)
    desc = db.Column(db.Text, nullable=True)

    category_id = db.Column(db.Integer, db.ForeignKey('category.id'),
        nullable=False)
    category = db.relationship('Category',
        backref=db.backref('programs', lazy=True))

    def __repr__(self):
        return '<Program %r>' % self.title


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    def __repr__(self):
        return '<Category %r>' % self.name


def get_xmltv():
    """
    Download XMLTV url and store channels and programs in the database.
    :return:
    None
    :return:
    """
    # http://wiki.xmltv.org/index.php/Main_Page/xmltvfileformat.html
    import urllib2
    import gzip
    import StringIO
    import xmltv
    url = cfg.TVGURL

    # Download XMLTV source
    out_file_path = url.split("/")[-1][:-3]
    print('Downloading TV program from: {}'.format(url))
    response = urllib2.urlopen(url)
    compressed_file = StringIO.StringIO(response.read())
    decompressed_file = gzip.GzipFile(fileobj=compressed_file)

    # Extract XMLTV
    with open(out_file_path, 'w') as outfile:
        outfile.write(decompressed_file.read())

    # Print XMLTV header
    xmltv_data = xmltv.read_data(open(out_file_path, 'r'))
    ic(xmltv_data)

    # Read xml channels
    xmlchannels = xmltv.read_channels(open(out_file_path, 'r'))
    print("Got {} channels from XMLTV source".format(len(xmlchannels)))

    # Drop content of XMLChannel
    XMLChannel.query.delete()
    db.session.commit()

    # Populate XMLChannel with channels from XMLTV source
    for xc in xmlchannels:
        xmlchannel = XMLChannel(id=int(xc['id']), label=xc['display-name'][0][0])
        db.session.add(xmlchannel)
    db.session.commit()

    programs = xmltv.read_programmes(open(out_file_path, 'r'))
    chunk = 512
    index = 0
    for pr in programs:
        desc = ""
        try:
            desc = pr['desc'][0][0]
        except KeyError:
            pass

        a_category = Category.query.filter(Category.name == pr['category'][0][0]).first()
        if a_category:
            p = Program(channel=int(pr['channel']),
                    title=pr['title'][0][0],
                    start=duparse(pr['start']),
                    stop=duparse(pr['stop']),
                    desc=desc,
                    category_id=a_category.id)
            db.session.add(p)
        else:
            py = Category(name=pr['category'][0][0])
            Program(channel=int(pr['channel']),
                    title=pr['title'][0][0],
                    start=duparse(pr['start']),
                    stop=duparse(pr['stop']),
                    desc=desc,
                    category=py)
            db.session.add(py)
        index += 1
        if index % chunk == 0:
            db.session.commit()
    db.session.commit()

    categories = [x for x in Category.query.all()]
    ic(categories)


def init_db():
    db.create_all()
    db.session.commit()


if __name__ == '__main__' and __package__ is None:
    __package__ = "helpers"
    init_db()
    get_xmltv()
