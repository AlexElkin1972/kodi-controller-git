#!/usr/bin/python
# coding: utf-8
import json
import os.path
from icecream import ic
from datetime import datetime
from dateutil.parser import parse as duparse
from dateutil.tz import tzoffset

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

        xmlchannels = XMLChannel.query.all()
        # ic(xmlchannels[0].label, xmlchannels[0].id)
        # ic(xmlchannels[1].label, xmlchannels[1].id)
        # ic(xmlchannels[2].label, xmlchannels[2].id)
        print("Kodi reports {} channels vs {} channels in XMLTV program".format(len(result), len(xmlchannels)))

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
    utitle = db.Column(db.String(128), nullable=False)
    start = db.Column(db.DateTime, nullable=False)
    stop = db.Column(db.DateTime, nullable=False)
    desc = db.Column(db.Text, nullable=True)

    category_id = db.Column(db.Integer, db.ForeignKey('category.id'),
        nullable=False)
    category = db.relationship('Category',
        backref=db.backref('programs', lazy=True))

    def __repr__(self):
        return '<Program %r>' % self.title

    def __init__(self, **kwargs):
        super(Program, self).__init__(**kwargs)
        # have to do custom stuff due lack of unicode upper in SQLite3
        self.utitle = self.title.upper()


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

    categories = [x.name for x in Category.query.all()]
    ic(u', '.join(categories))



def get_programs(category=None, filter_program=None, now=False):
    ic(["get_programs", category, filter_program, now])
    if category == None:
        return [x.name for x in Category.query.all()]
    filter_program_ = '' if filter_program is None else filter_program
    category_id = Category.query.filter(Category.name == category).first().id
    search_pattern = u"%{}%".format(filter_program_.upper())
    if not now:
        # Filtered future programs of selected category
        # offset = tzoffset(None, 10 * 3600)
        ts_now = datetime.now()
        # ic(ts_now)
        programs = Program.query.filter(Program.category_id == category_id,
                                        Program.utitle.like(search_pattern),
                                        Program.start > ts_now).all()

        # ic(programs[0].start)
        program_titles = [{'channel': resolve_kodi_channel(x.channel),
                           'title': x.title,
                           'start': str(x.start),
                           'stop': str(x.stop),
                           'time_before_start':
                               (x.start - ts_now).total_seconds()}
                          for x in programs if resolve_kodi_channel(x.channel)]

        for program_title in sorted(program_titles, key=lambda y: y['time_before_start']):
            # print(program_title)
            print (program_title['channel'] +
                   " " + program_title['title'] + u" через " +
                   str(int(program_title['time_before_start'] / 60)) + u' мин., в ' +
                   str(program_title['start']))

        return sorted(program_titles, key=lambda y: y['time_before_start'])

    # Filtered current programs of selected category
    ts_now = datetime.now()
    # ic(ts_now)
    programs = Program.query.filter(Program.category_id == category_id,
                                    Program.utitle.like(search_pattern),
                                    Program.start < ts_now,
                                    Program.stop > ts_now).all()

    program_titles = [{'channel': resolve_kodi_channel(x.channel),
                       'title': x.title,
                       'start': str(x.start),
                       'stop': str(x.stop),
                       'time_before_stop': (x.stop - ts_now).total_seconds()}
                      for x in programs if resolve_kodi_channel(x.channel)]
    for program_title in sorted(program_titles, key=lambda y: y['time_before_stop'], reverse=True):
        # print(program_title)
        print (program_title['channel'] +
               " " + program_title['title'] + u" ещё " +
               str(int(program_title['time_before_stop'] / 60)) + u' мин., до ' +
               str(program_title['stop']))

    return sorted(program_titles, key=lambda y: y['time_before_stop'], reverse=True)


def resolve_kodi_channel(xmlChannelId):
    # ic(xmlChannelId)
    channelUlabel = XMLChannel.query.filter(XMLChannel.id == xmlChannelId).first().ulabel
    # ic(channelUlabel)
    channel = Channel.query.filter(Channel.ulabel == channelUlabel).first()
    # ic(channel)
    if channel is None:
        return None
    return u'{}/{}:'.format(channel.id, channel.label)


def init_db():
    db.create_all()
    db.session.commit()


if __name__ == '__main__' and __package__ is None:
    __package__ = "helpers"
    init_db()
    get_xmltv()
