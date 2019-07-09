#!/usr/bin/env python
from bs4 import BeautifulSoup, Tag
import copy
import json
import os
import requests
import shutil
import tempfile
from urllib.parse import unquote_plus


from le_utils.constants import content_kinds, file_types, licenses
from ricecooker.chefs import JsonTreeChef
from ricecooker.classes.licenses import get_license
from ricecooker.utils.jsontrees import write_tree_to_json_tree
from ricecooker.utils.zip import create_predictable_zip

from libedx import extract_course_tree



containerdir = 'chefdata/Sample2'

HPLIFE_LICENSE = get_license(licenses.CC_BY, copyright_holder='HP LIFE').as_dict()

HPLIFE_LANGS = ['es', 'fr', 'en']

HPLIFE_COURSE_FOLDER_RENAMES = {
    'Energy efficiency  Do more for less': 'Energy efficiency - Do more for less',
    'Eficiencia de la energía hacer más con menos': 'Eficiencia de la energía - hacer más con menos',
    'Eficiencia de la energía  hacer más con menos': 'Eficiencia de la energía - hacer más con menos',
    'Efficacité énergétique Faire davantage avec moins': 'Efficacité énergétique - Faire davantage avec moins',
    'Efficacité énergétique : Faire davantage avec moins': 'Efficacité énergétique - Faire davantage avec moins',
}

def transform_articulate_storyline_folder(contentdir, activity_ref):
    """
    Transform the contents of the folder of kind `articulate_storyline` called
    `activity_ref` located in the directory `contentdir` to adapt it to Kolibri
    plarform, package it as a zip, and return the neceesary metadata as a dict.
    """
    sourcedir = os.path.join(contentdir, activity_ref)            # source folder
    webroot = os.path.join(contentdir, activity_ref+'_webroot')   # transformed dir

    if not os.path.exists(sourcedir):
        print('wrong guess about content type--- this is not an articulate_storyline_... ')
        return None
    
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
    # TODO: get author from     project > <author name="Victoria" email="" website="" />
    metadata = dict(
        kind = 'articulate_storyline',
        title_en = project['title'],
        source_id = activity_ref,
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

    if not os.path.exists(sourcedir):
        print('missing sourcedir', sourcedir)
        return None

    if os.path.exists(webroot):
        shutil.rmtree(webroot)
    
    # Copy source dir to webroot dir where we'll do the edits and transformations
    shutil.copytree(sourcedir, webroot)
    
    metadata = dict(
        kind = 'resources_folder',
        source_id = activity_ref,
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

    meta = Tag(name='meta', attrs={'charset':'utf-8'})
    doc.head.append(meta)
    # TODO: add meta language (in case of right-to-left languages)

    # Writeout new index.html
    indexhtmlpath = os.path.join(webroot, 'index.html')
    with open(indexhtmlpath, 'w') as indexfilewrite:
        indexfilewrite.write(str(doc))

    # Zip it
    zippath = create_predictable_zip(webroot)
    metadata['zippath'] = zippath

    return metadata


def transform_html(content):
    """
    Transform the HTML markup taken from `content` (str) to file index.html in
    a standalone zip file. Return the neceesary metadata as a dict.
    """
    chef_tmp_dir = 'chefdata/tmp'
    webroot = tempfile.mkdtemp(dir=chef_tmp_dir)

    metadata = dict(
        kind = 'html_content',
        source_id = content[0:30],
        zippath = None,  # to be set below
    )

    doc = BeautifulSoup(content, 'html5lib')
    meta = Tag(name='meta', attrs={'charset':'utf-8'})
    doc.head.append(meta)
    # TODO: add meta language (in case of right-to-left languages)

    # Writeout new index.html
    indexhtmlpath = os.path.join(webroot, 'index.html')
    with open(indexhtmlpath, 'w') as indexfilewrite:
        indexfilewrite.write(str(doc))

    # Zip it
    zippath = create_predictable_zip(webroot)
    metadata['zippath'] = zippath

    return metadata






def flatten_subtree(chapter):
    """
    Returns a flat list of the content nodes
    """
    content_items = []
    for sequential in chapter['children']:
        for vertical in sequential['children']:
            for content_item in vertical['children']:
                content_item['title'] = sequential['display_name']
                content_items.append(content_item)
    return content_items



def build_subtree_from_course(course):
    print('Building a tree from course', course)
    course_dict = dict(
        kind=content_kinds.TOPIC,
        title=course['name'],
        language=course['lang'],
        children = [],
    )
    basedir = os.path.join(containerdir, course['path'])
    contentdir = os.path.join(basedir, 'content')
    coursedir = os.path.join(basedir, 'course')
    data = extract_course_tree(coursedir)

    # TODO: title = data['display_name'] + (first_native_name)

    course_dict['source_id'] = data['course']


    for i, chapter in enumerate(data['children']):

        if 'display_name' not in chapter:
            print('skipping title-less wiki')
            continue
        if i == 4:
            print('skipping course feedback', chapter['display_name'])
            continue

        chapter_dict = dict(
            kind=content_kinds.TOPIC,
            title=chapter['display_name'],
            source_id=chapter['display_name'],
            children = [],
        )
        course_dict['children'].append(chapter_dict)

        content_items = flatten_subtree(chapter)
        for j, item in enumerate(content_items):
            html5_dict = dict(
                kind=content_kinds.HTML5,
                title=chapter_dict['title'],
                source_id=chapter_dict['title'] + '___' + str(j),
                license=HPLIFE_LICENSE,
                language=course['lang'],
                files=[],
            )

            kind = item['kind']

            # Resouce folder
            if kind == 'html' and 'activity' in item:
                activity_ref = item['activity']['activity_ref']
                zip_info = transform_resource_folder(contentdir, activity_ref, item['content'])
                if zip_info:
                    zippath = zip_info['zippath']
                    html5_dict['source_id'] = zip_info['source_id']
                    html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
                else:
                    continue

            # Generic HTML
            elif kind == 'html':
                zip_info = transform_html(item['content'])
                if zip_info:
                    zippath = zip_info['zippath']
                    html5_dict['source_id'] = zip_info['source_id']
                    html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
                else:
                    continue

            # Articulate Storyline
            elif kind == 'problem' and 'activity' in item:
                activity_ref = item['activity']['activity_ref']
                zip_info = transform_articulate_storyline_folder(contentdir, activity_ref)
                if zip_info:
                    html5_dict['thumbnail'] = zip_info['thumbnail']
                    html5_dict['source_id'] = zip_info['source_id']
                    html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
                    zippath = zip_info['zippath']
                else:
                    print('transform_articulate_storyline_folder returned None')
                    continue
            else:
                print('Unrecognized item', item)
                continue

            file_dict = dict(
                file_type=file_types.HTML5,
                path=zippath,
                language=course['lang'],
            )
            html5_dict['files'].append(file_dict)
            
            chapter_dict['children'].append(html5_dict)
        
    return course_dict









class HPLifeChef(JsonTreeChef):
    """
    Sushi chef script for uploading HP LIFE courses to the Kolibri platform.
    """

    RICECOOKER_JSON_TREE = 'hplife_ricecooker_tree.json'

    def pre_run(self, args, options):

        ricecooker_json_tree = dict(
            title='HP LIFE Channel',
            source_domain='life-global.org',         # where you got the content (change me!!)
            source_id='hp-life-sample-content',  # channel's unique id (change me!!)
            description='This is Sample2 channel with Articulate Storyline and HTML content packaged as HTML5Zip for use on Kolibri',
            thumbnail='https://pbs.twimg.com/profile_images/458985190191136768/4yaxe2B3.png',
            language='en',
            children=[],
        )

        course_list = json.load(open(os.path.join(containerdir,'course_list.json')))
        for course in course_list['courses']:
            course_dict = build_subtree_from_course(course)
            ricecooker_json_tree['children'].append(course_dict)

        json_tree_path = self.get_json_tree_path()
        write_tree_to_json_tree(json_tree_path, ricecooker_json_tree)



if __name__ == '__main__':
    """
    Run this script on the command line using:
        python simple_chef.py -v --reset --token=YOURTOKENHERE9139139f3a23232
    """
    simple_chef = HPLifeChef()
    simple_chef.main()


