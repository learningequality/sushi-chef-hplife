#!/usr/bin/env python
from bs4 import BeautifulSoup, Tag
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
from libedx import print_course

from transform import extract_hpstoryline


DEBUG_MODE = True

COURSES_DIR = 'chefdata/Courses'

HPLIFE_LICENSE = get_license(licenses.CC_BY, copyright_holder='HP LIFE').as_dict()

HPLIFE_LANGS = ['es', 'fr', 'en']


HPLIFE_COURSE_STRUCTURE_STRINGS = {
    'en': {
        'intro': 'Start Course',
        'story': 'Story',
        'businessconcept': 'Business Concept',
        'technologyskill': 'Technology Skill',
        'coursefeedback': 'Course Feedback',
        'nextsteps': 'Next Steps',
    },
    'es': {
        'intro': 'Inicio del curso',
        'story': 'Narración',
        'businessconcept': 'Concepto de negocio',
        'technologyskill': 'Habilidad Tecnología',
        'coursefeedback': 'Encuesta',
        'nextsteps': 'Pasos siguientes',
    },
    'fr': {
        'intro': 'Démarrer',
        'story': 'Histoire',
        'businessconcept': 'Concept commercial',
        'technologyskill': 'Compétence technologiqu',
        'coursefeedback': 'Sondage',
        'nextsteps': 'Étapes suivantes',
    }
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
        print('WWW Could not find local resource folder for activity_ref=', activity_ref)
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
    
    # load index.html
    with open(indexhtmlpath, 'r') as indexfileread:
        indexhtml = indexfileread.read()
    doc = BeautifulSoup(indexhtml, 'html5lib')

    # A. Localize js libs
    scriptsdir = os.path.join(webroot, 'scripts')
    if not os.path.exists(scriptsdir):
        os.mkdir(scriptsdir)
    scripts = doc.find('head').find_all('script')
    for script in scripts:
        script_url = script['src']
        script_basename = os.path.basename(script_url)
        response = requests.get(script_url)
        with open(os.path.join(scriptsdir, script_basename), 'wb') as scriptfile:
            scriptfile.write(response.content)
        scriptrelpath = os.path.join('scripts', script_basename)
        script['src'] = scriptrelpath

    # B. Inline css files to avoid CORS issues
    styles = doc.find('body').find_all('link', rel="stylesheet")
    for style in styles:
        style_href = style['href']
        style_path = os.path.join(webroot, style_href)
        style_content = '\n' + open(style_path).read()
        inline_style_tag = doc.new_tag('style')
        inline_style_tag['data-noprefix'] = ''
        inline_style_tag['rel'] = 'stylesheet'
        inline_style_tag.string = style_content
        style.replace_with(inline_style_tag)

    # Save modified index.html
    with open(indexhtmlpath, 'w') as indexfilewrite:
        indexfilewrite.write(str(doc))

    # Zip it
    zippath = create_predictable_zip(webroot)
    metadata['zippath'] = zippath

    return metadata



def transform_hpstoryline_folder(contentdir, story_id, node):
    """
    Package the contents of the folder of kind `hpstoryline` called `story_id`
    located in the directory `contentdir` and return the neceesary metadata as a dict.
    """
    sourcedir = os.path.join(contentdir, story_id)
    webroot = os.path.join(contentdir, story_id+'_webroot')   # transformed dir

    if not os.path.exists(sourcedir):
        print('WWW Could not find local resource folder for story_id=', story_id)
        return None

    if os.path.exists(webroot):
        shutil.rmtree(webroot)

    # Copy source dir to webroot dir where we'll do the edits and transformations
    shutil.copytree(sourcedir, webroot)
    metadata = dict(
        kind = 'hpstoryline',
        title_en = node['title'],
        source_id = story_id,
        thumbnail = None, # TODO
        zippath = None,                     # will be set below
    )

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
            link['target'] = '_blank'

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



def parse_course_tree(course_data, coursedir, contentdir):
    """
    Parse the edX XML structure and pluck the neessary components form the tree
    to return a `parsed_tree` that looks like this:
    parsed_tree = {
        'intro': {},
        'story': {},
        'businessconcept': {},
        'technologyskill': {},
        'coursefeedback': {},
        'nextsteps': {},
    }
    """
    print('in parse_course_tree', course_data['course'], coursedir, contentdir)

def transform_course_tree(parsed_tree, coursedir, contentdir):
    """
    Tranform the parsed_tree for a course into channel subfolder for this course.
    Includes:
     - extract info from intro
     - modify next steps
     - generate _webroot with transformed outputs of resource folders
     - scrape hpstoryline stories (if applicable)
     - package resource folders as .zip
     - create ricecooker_json_tree
    Returns a ricecooker_json_tree (dict).
    """
    print('in transform_course_tree', parsed_tree, coursedir, contentdir)


def build_subtree_from_course(course, containerdir):
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

    course_dict['source_id'] = data['course']
    # Jul 17: handle duplicate course ID `2352hpl-es03` which is used for both
    # 'Ganancias y pérdidas' and 'Marketing de medios sociales'
    if data['course'] == '2352hpl-es03' and course['name'] == 'Marketing de medios sociales':
        course_dict['source_id'] = data['course'] + '-2'

    if DEBUG_MODE:
        print_course(data)
        course_tree_path = 'chefdata/trees/course_tree-{}.json'.format(course_dict['source_id'])
        with open(course_tree_path, 'w') as json_file:
            json.dump(data, json_file, indent=4, ensure_ascii=False)


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
                title=item['title'],
                source_id=chapter_dict['title'] + '___' + str(j),
                license=HPLIFE_LICENSE,
                language=course['lang'],
                files=[],
            )

            kind = item['kind']

            # Local resouce folder
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

            # Old-style hpstoryline
            elif kind == 'problem' and 'activity' in item and item['activity']['kind'] == 'hpstoryline':
                story_id = item['activity']['story_id']
                contentdir_story_id_path = os.path.join(contentdir, story_id)
                if not os.path.exists(contentdir_story_id_path):
                    extract_hpstoryline(contentdir, story_id)
                zip_info = transform_hpstoryline_folder(contentdir, story_id, item)
                if zip_info:
                    html5_dict['thumbnail'] = zip_info['thumbnail']
                    html5_dict['source_id'] = zip_info['source_id']
                    html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
                    zippath = zip_info['zippath']
                else:
                    print('EEEE2 transform_hpstoryline_folder', item['activity'])
                    continue

            # New-style Articulate Storyline
            elif kind == 'problem' and 'activity' in item:
                activity_ref = item['activity']['activity_ref']
                zip_info = transform_articulate_storyline_folder(contentdir, activity_ref)
                if zip_info:
                    html5_dict['thumbnail'] = zip_info['thumbnail']
                    html5_dict['source_id'] = zip_info['source_id']
                    html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
                    zippath = zip_info['zippath']
                else:
                    print('EEEE transform_articulate_storyline_folder', item['activity'])
                    continue
            else:
                print('EEEEE Unrecognized item', item)
                continue

            file_dict = dict(
                file_type=file_types.HTML5,
                path=zippath,
                language=course['lang'],
            )
            html5_dict['files'].append(file_dict)
            
            chapter_dict['children'].append(html5_dict)
        
    return course_dict





CHANNEL_TITLE_LOOKUP = {
    'en': 'HP LIFE Courses (English)',
    'es': 'Cursos HP LIFE (Español)',
    'fr': 'Cours HP LIFE (Français)',
}


CHANNEL_DESCRIPTION_LOOKUP = {
    'en': "A program of the HP Foundation, this collection of short introductory courses helps adults learn independently various digital and entrepreneurship skills, including information technology, starting a business, online sales, and marketing. Appropriate for adults who are curious to develop their professional skills or simply learn about new opportunities.",
    'es': "Una iniciativa de HP Foundation, esta colección de cursos introductorios y breves ayuda a los adultos a adquirir habilidades en tecnología y emprendimiento de forma independiente, incluye tecnologías de la información, empezar  un negocio, venta en línea y marketing. Son apropiados para adultos con curiosidad por desarrollarse profesionalmente o por aprender nuevas oportunidades.",
    'fr': "Un programme de HP Foundation, les cours HP LIFE sont conçus pour aider les adultes à apprendre de manière autonome diverses compétences numériques, y compris les technologies de l'information, la création d'entreprise, les ventes en ligne et le marketing. Ces cours conviennent aux adultes qui sont curieux de développer leurs compétences professionnelles ou poursuivre de nouvelles opportunités.",
}


class HPLifeChef(JsonTreeChef):
    """
    Sushi chef script for uploading HP LIFE courses to the Kolibri platform.
    """

    def get_json_tree_path(self, *args, **kwargs):
        """
        Return path to ricecooker json tree file. Override this method to use
        a custom filename, e.g., for channel with multiple languages.
        """
        lang = kwargs['lang']
        RICECOOKER_JSON_TREE = 'hplife_ricecooker_tree_{}.json'.format(lang)
        json_tree_path = os.path.join(self.TREES_DATA_DIR, RICECOOKER_JSON_TREE)
        return json_tree_path

    def pre_run(self, args, options):
        if 'lang' not in options:
            raise ValueError('Must specify lang option in ' + str(HPLIFE_LANGS))
        lang = options['lang']
        assert lang in HPLIFE_LANGS

        if not os.path.exists(self.TREES_DATA_DIR):
            os.makedirs(self.TREES_DATA_DIR)

        ricecooker_json_tree = dict(
            title=CHANNEL_TITLE_LOOKUP[lang],
            source_domain='life-global.org',
            source_id='hp-life-courses-{}'.format(lang),
            description=CHANNEL_DESCRIPTION_LOOKUP[lang],
            thumbnail='chefdata/channel_thumbnail.png',
            language=lang,
            children=[],
        )
        print('in pre_run; channel info = ', ricecooker_json_tree)

        containerdir = os.path.join(COURSES_DIR, lang)
        course_list = json.load(open(os.path.join(containerdir, 'course_list.json')))
        for course in course_list['courses']:
            course_dict = build_subtree_from_course(course, containerdir)
            ricecooker_json_tree['children'].append(course_dict)

        json_tree_path = self.get_json_tree_path(lang=lang)
        write_tree_to_json_tree(json_tree_path, ricecooker_json_tree)


    # def run(self, args, options):
    #     self.pre_run(args, options)
    #     print('exiting FOR DEBUGGING')  ###################################################################################################################



if __name__ == '__main__':
    """
    Run this script on the command line using:
    ./suschichef.py -v --reset --thumbnails --token=<YOURTOKENHERE>  lang=es
    """
    chef = HPLifeChef()
    chef.main()

