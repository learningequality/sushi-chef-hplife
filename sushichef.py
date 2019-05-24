#!/usr/bin/env python
from bs4 import BeautifulSoup
import copy
import json
import os
import requests
import shutil
from urllib.parse import unquote_plus

from ricecooker.chefs import SushiChef
from ricecooker.utils.zip import create_predictable_zip
from ricecooker.classes.nodes import ChannelNode, TopicNode, DocumentNode, HTML5AppNode
from ricecooker.classes.files import DocumentFile, HTMLZipFile
from ricecooker.classes.licenses import get_license



def transform_articulate_storyline_folder(contentdir, activity_ref):
    """
    Transform the contents of the folder of kind `articulate_storyline` called
    `activity_ref` located in the directory `contentdir` to adapt it to Kolibri
    plarform, package it as a zip, and return the neceesary metadata as a dict.
    """
    sourcedir = os.path.join(contentdir, activity_ref)            # source folder
    webroot = os.path.join(contentdir, activity_ref+'_webroot')   # transformed dir
    
    if os.path.exists(webroot):
        shutil.rmtree(webroot)

    # Copy source dir to webroot dir where we'll do the edits and transformations
    shutil.copytree(sourcedir, webroot)
    
    # Remove unnecessary files
    html_files_to_remove = ['story.html', 'story.swf', 'story_flash.html']
    for html_file in html_files_to_remove:
        filepath = os.path.join(webroot, html_file)
        if os.path.exists(filepath):
            os.remove(filepath)

    # Remove all .swf files from webroot/
    for root, dirs, files in os.walk(webroot):
        for file in files:
            filepath = os.path.join(root, file)
            _, ext = os.path.splitext(filepath)
            if ext == '.swf':
                os.remove(filepath)

    metapath = os.path.join(webroot, 'meta.xml')
    metaxml = open(metapath, 'r').read()
    metadoc = BeautifulSoup(metaxml, "html5lib")
    project = metadoc.find('project')
    metadata = dict(
        kind = 'articulate_storyline',
        title_en = project['title'],
        thumbnail = os.path.join(webroot, project.attrs['thumburl']),
        datepublished = project['datepublished'],
        duration = project['duration'],
        totalaudio = project['totalaudio'],
        zippath = None,  # to be set below
    )

    # Setup index.html
    indexhtmlpath = os.path.join(webroot,'index.html')
    shutil.move(os.path.join(webroot,'story_html5.html'), indexhtmlpath)
    
    # Localize js libs
    scriptsdir = os.path.join(webroot, 'scripts')
    if not os.path.exists(scriptsdir):
        os.mkdir(scriptsdir)
    with open(indexhtmlpath, 'r') as indexfileread:
        indexhtml = indexfileread.read()
    doc = BeautifulSoup(indexhtml, 'html5lib')
    scripts = doc.find('head').find_all('script')
    for script in scripts:
        script_url = script['src']
        script_basename = os.path.basename(script_url)
        response = requests.get(script_url)
        with open(os.path.join(scriptsdir, script_basename), 'wb') as scriptfile:
            scriptfile.write(response.content)
        scriptrelpath = os.path.join('scripts', script_basename)
        script['src'] = scriptrelpath
    with open(indexhtmlpath, 'w') as indexfilewrite:
        indexfilewrite.write(str(doc))
    
    # Zip it
    zippath = create_predictable_zip(webroot)
    metadata['zippath'] = zippath

    return metadata


def transform_resource_folder(contentdir, activity_ref, content):
    """
    Transform the contents of the folder of kind `resources_folder` called
    `activity_ref` located in the directory `contentdir`, turning it into a
    standalone zip file with an index.html taken from `content` (str).
    Return the neceesary metadata as a dict.
    """
    sourcedir = os.path.join(contentdir, activity_ref)            # source folder
    webroot = os.path.join(contentdir, activity_ref+'_webroot')   # transformed dir

    if os.path.exists(webroot):
        shutil.rmtree(webroot)
    
    # Copy source dir to webroot dir where we'll do the edits and transformations
    shutil.copytree(sourcedir, webroot)
    
    metadata = dict(
        kind = 'resources_folder',
        zippath = None,  # to be set below
    )

    doc = BeautifulSoup(content, 'html5lib')

    # Rewrite links
    links = doc.find_all('a')
    for link in links:
        if 'href' in link.attrs:
            url = link['href']
            print(url)
            url_parts = url.split('/')
            parentdir = unquote_plus(url_parts[-2])
            assert parentdir == activity_ref, 'Found link to another resouce folder'
            filename = unquote_plus(url_parts[-1])
            link['href'] = filename

    # TODO: add meta encoding utf-8
    # TODO: add meta language (in case of right-to-left languages)

    # Writeout new index.html
    indexhtmlpath = os.path.join(webroot, 'index.html')
    with open(indexhtmlpath, 'w') as indexfilewrite:
        indexfilewrite.write(str(doc))

    # Zip it
    zippath = create_predictable_zip(webroot)
    metadata['zippath'] = zippath

    return metadata




class HPLifeChef(SushiChef):
    channel_info = {
        'CHANNEL_TITLE': 'HP LIFE Sample Channel',
        'CHANNEL_SOURCE_DOMAIN': 'life-global.org',         # where you got the content (change me!!)
        'CHANNEL_SOURCE_ID': 'hp-life-sample-content',  # channel's unique id (change me!!)
        'CHANNEL_LANGUAGE': 'en',                        # le_utils language code
        'CHANNEL_THUMBNAIL': 'https://s10896.pcdn.co/wp-content/uploads/2015/08/HP-Life-Logo.jpg', # (optional)
        'CHANNEL_DESCRIPTION': 'This channel contains sample content exported from the Articulate Storyline format slideshows packaged as HTML5Zip',      # (optional)
    }

    def construct_channel(self, **kwargs):
        channel = self.get_channel(**kwargs)
        topic = TopicNode(title="Ariculate Storyline samples", source_id="sample_as")
        channel.add_child(topic)

        html_node1 = HTML5AppNode(
            title='Business Concept',
            description='The contents of Business Concept/ dir',
            source_id='business-concept',
            license=get_license('CC BY', copyright_holder='HP LIFE'),
            language='en',
            files=[HTMLZipFile(path='HP LIFE sample/Success Mindset - English/business-concept-webroot.zip',
                                language='en')],
        )
        topic.add_child(html_node1)

        # html_node2 = HTML5AppNode(
        #     title='Story',
        #     description='The contents of Story/ dir',
        #     source_id='story',
        #     license=get_license('CC BY', copyright_holder='HP LIFE'),
        #     language='en',
        #     files=[HTMLZipFile(path='HP LIFE sample/Success Mindset - English/story-webroot.zip',
        #                         language='en')],
        # )
        # topic.add_child(html_node2)

        return channel


if __name__ == '__main__':
    """
    Run this script on the command line using:
        python simple_chef.py -v --reset --token=YOURTOKENHERE9139139f3a23232
    """
    simple_chef = HPLifeChef()
    simple_chef.main()


