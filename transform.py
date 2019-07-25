
from bs4 import BeautifulSoup, Tag
import json
import os
import re
import requests
import shutil
import tempfile
from urllib.parse import unquote_plus
from urllib.parse import urljoin
from html2text import html2text

from le_utils.constants import content_kinds, file_types, licenses
from ricecooker.utils.zip import create_predictable_zip


import slimit
from slimit.parser import Parser
from slimit.visitors import nodevisitor
from slimit import ast
# silence parse warning/errors
# via https://github.com/rspivak/slimit/issues/97#issuecomment-464370110
slimit.lexer.ply.lex.PlyLogger =  \
slimit.parser.ply.yacc.PlyLogger = \
  type('_NullLogger', (slimit.lexer.ply.lex.NullLogger,),
       dict(__init__=lambda s, *_, **__: (None, s.super().__init__())[0]))





# CONSTANTS
################################################################################




# TOP-LEVEL FUNCTION
################################################################################

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


# PARSE HTML CONTENT
################################################################################

COURSE_START_SPLIT_STRINGS = {
    'es': {
        'start_removables': ['Inicio:', 'INICIO:'],
        'cutpoint_starts': [
            '¿Por qué empezar hoy?',
            '¿Por qué comenzar hoy?',
            '¿Por qué comenzar hoy mismo?',
            '¿Por qué debo empezar hoy mismo?',
        ],
        'cutpoint_start_and_includes': [
            'En este curso',
        ],
        'cutpoint_ends': [
            'Pasos en el curso',
            'Pasos del curso',
            'Etapas del curso',
            'Pasos en el Curso',
            'Pasosen el curso',
            'Este curso fue desarrollado',
            'Este curso se desarrolló',
        ],
    },
    'fr': {
        'start_removables': ['Démarrer:', 'Démarrer :', 'DEMARRER :', 'DEMARRER:'],
        'cutpoint_starts': [
            'Pourquoi commencer aujourd\'hui ?',
            'Pourquoi commencer aujourd’hui ?',
            'Pourquoi démarrer aujourd\'hui ?',
            'Pourquoi démarrer le cours dès aujourd\'hui?',
        ],
        'cutpoint_start_and_includes': [
            'Durant ce cours, vous allez :',
        ],
        'cutpoint_ends': [
            'Étapes du cours',
            'Etapes du cours',
            'Étapes à suivre',
            'Ce cours a été élaboré',
        ],
    },
    'en': {
        'start_removables': ['Start:', 'START:'],
        'cutpoint_starts': [
            'Why start today?',
        ],
        'cutpoint_start_and_includes': [
            'In this course, you will:'
        ],
        'cutpoint_ends': [
            'Steps in the course',
            'This course was developed',
        ]
    }
}

def get_course_description_from_coursestart_html(content, lang):
    """
    Extracts the course description from the course start HTML content.
    """
    doc = BeautifulSoup(content, 'html5lib')
    body = doc.find('body')
    page_text = html2text(str(body), bodywidth=0)

    SPLIT_STRINGS = COURSE_START_SPLIT_STRINGS[lang]
    course_description_lines = []

    # Process markdown lines
    found_start = False
    found_end = False
    started = False
    for line in page_text.split('\n'):
        if found_start:
            started = True
        if found_end:
            break

        for pattern in SPLIT_STRINGS['cutpoint_starts']:
            if pattern in line:
                found_start = True
        for pattern in SPLIT_STRINGS['cutpoint_start_and_includes']:
            if not found_start and pattern in line:
                found_start = True
                course_description_lines.append(line)
        for pattern in SPLIT_STRINGS['cutpoint_ends']:
            if pattern in line and not line.startswith('●'):
                found_end = True

        if started and not found_end:
            course_description_lines.append(line)
        else:
            pass

    if not found_start or not found_end:
        print('ERROR: failed to parse markdown...')
        print(page_text)
        print('\n')

    non_blank_lines = [line for line in course_description_lines if line.strip()]

    # Clean and standardize line outputs
    clean_lines = []
    BOLD_RE = re.compile('\*\*')
    for line in non_blank_lines:
        line = line.replace('**', '').strip()
        line = line.replace('###', '').strip()
        line = line.replace('* · ', '•')
        line = line.replace('·', '•')
        line = line.replace('●', '•')
        line = line.replace('*', '•')
        if line.startswith('_'):
            line = line[1:]
        if line.endswith('_'):
            line = line[:-1]
        #
        if line:
            clean_lines.append(line)

    # prepare output
    couse_description = ''
    for line in clean_lines:
        if len(couse_description) < 400:
            couse_description += ' ' + line.strip()
        else:
            print('SKIPPING desription line', line)

    return couse_description.strip()




def get_resources_from_articulate_storyline(contentdir, activity_ref):
    """
    Extracts the resource links from the articulate storyline 'frame.json'.
    resources = {
        'relpath': 'story_content/external_files/Additional_Excel_Tips.pdf',
        'title': 'Additional Excel Tips',
        'iconrelpath': 'story_content/6OiyTv2LR5V.png',
    }
    """
    #print('in get_resource_articulate_storyline for', contentdir, activity_ref)
    resources = []

    story_content_path = os.path.join(contentdir, activity_ref, 'story_content')
    if not os.path.exists(story_content_path):
        print( 'No story_content folder in', os.path.join(contentdir,activity_ref) )
    if os.path.exists(story_content_path):
        framepath = os.path.join(story_content_path, 'frame.json')
        if os.path.exists(framepath):
            frame_data = json.load(open(framepath))
            resource_data = frame_data["resource_data"]
            json_resources = resource_data['resources']
            if json_resources:
                for json_resource in json_resources:
                    resource = dict(
                        title=json_resource['title'],
                        relpath=json_resource['url'],
                        iconrelpath=json_resource.get('image', None),
                    )
                    resources.append(resource)
        else:
            # if 'frame.json' not found, try to parse 'frame.xml' as fallback
            xmlframepath = os.path.join(story_content_path, 'frame.xml')
            if os.path.exists(xmlframepath):
                # print(xmlframepath)
                frame_data = BeautifulSoup(open(xmlframepath).read(), 'xml')
                resource_data = frame_data.find("resource_data")
                if resource_data:
                    xml_resources = resource_data.find_all('resource')
                    if xml_resources:
                        for xml_resource in xml_resources:
                            resource = dict(
                                title=xml_resource['title'],
                                relpath=xml_resource['url'],
                                iconrelpath=xml_resource.get('image', None),
                            )
                            resources.append(resource)
    return resources




# TRANSFORM CONTENT FOLDERS
################################################################################


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







# DOWNLOADER FOR LEGACY hpstoryline STORIES
################################################################################

HPSTORYLINE_BASE_URL = 'https://hpstoryline.edcastcloud.com/hp_storyline/story?story='

PHOTO_CLASS = 'field-name-field-hplife-fotoscreen-photo'
BUBBLES_CLASS = 'field-name-field-hplife-fotoscreen-bubbles'
AUDIO_CLASS = 'field-name-field-hplife-fotoscreen-audio'

ASSETS_DIR_NAME = 'assets'
MEDIA_DIR_NAME='media'
SCRIPTS_DIR_NAME = 'scripts'

def download_hpstoryline(contentdir, story_id):
    """
    Downloads the HTML and all necessary assets to `{contentdir}/{story_id}/`.
    """
    destdir = os.path.join(contentdir, story_id)
    if not os.path.exists(destdir):
        os.makedirs(destdir)

    mediadir = os.path.join(destdir, MEDIA_DIR_NAME)
    if not os.path.exists(mediadir):
        os.makedirs(mediadir)

    assetsdir = os.path.join(destdir, ASSETS_DIR_NAME)
    if not os.path.exists(assetsdir):
        os.makedirs(assetsdir)


    source_url = HPSTORYLINE_BASE_URL + story_id
    html = requests.get(source_url).text
    doc = BeautifulSoup(html, 'html5lib')

    # A. Localize js libs
    scriptsdir = os.path.join(destdir, SCRIPTS_DIR_NAME)
    if not os.path.exists(scriptsdir):
        os.mkdir(scriptsdir)
    scripts = doc.find('head').find_all('script')
    for script in scripts:
        if script.has_attr('src'):
            script_url = urljoin(source_url, script['src'])
            script_basename = os.path.basename(script_url)
            destpath = os.path.join(scriptsdir, script_basename)
            if not os.path.exists(destpath):
                response = requests.get(script_url)
                script_src = response.text
                edited_script_src = script_src.replace('/assets', 'assets')
                with open(destpath, 'w') as scriptfile:
                    scriptfile.write(edited_script_src)
            scriptrelpath = os.path.join(SCRIPTS_DIR_NAME, script_basename)
            script['src'] = scriptrelpath
        else:
            print('skipping inline script')

    # B. Localize and rewrite css files
    header_links = doc.find('head').find_all('link')
    styles = [link for link in header_links if "stylesheet" in link["rel"]]
    for style in styles:
        style_url = urljoin(source_url, style['href'])
        style_basename = os.path.basename(style_url)
        destpath = os.path.join(assetsdir, style_basename)

        if not os.path.exists(destpath):
            response = requests.get(style_url)
            if response.status_code == 200:
                style_str = response.text
                new_style_str = css_rewriter(style_str, source_url, destdir)
                with open(destpath, 'w') as stylefile:
                    stylefile.write(new_style_str)
                    print('\tSaved rewritten css to', destpath)
                    style_rel_path = os.path.join(ASSETS_DIR_NAME, style_basename)
                    style['href'] = style_rel_path
            else:
                print('ERROR failed to GET', style_url)

    # C. Download slideshow assets
    body = doc.find('body')
    main = body.find('div', {'id':'main'})
    article = main.find('article')
    fotonovelas = article.find_all('div', class_="hplife-fotonovela-wrapper")
    for fotonovela in fotonovelas:
        photo_div = None
        bubbles_div = None
        audio_div = None

        fotonovela_divs = fotonovela.find_all('div', recursive=False)
        for div in fotonovela_divs:
            if PHOTO_CLASS in div['class']:
                photo_div = div
            elif BUBBLES_CLASS in div['class']:
                bubbles_div = div
            elif AUDIO_CLASS in div['class']:
                audio_div = div
            else:
                print('unrecognized div', div)

        # C1. download slide bg images 
        # print('photo_div=', photo_div)
        img_rewriter(photo_div, source_url, mediadir)

        # C2.
        # print('bubbles_div=', bubbles_div)
        img_rewriter(bubbles_div, source_url, mediadir)

        # C3. Edit JS code
        # print('audio_div=', audio_div)
        audio_div_script = audio_div.find('script')
        jscode_str = audio_div_script.text
        new_jscode_str = extract_and_download_mp3path(jscode_str, destdir)
        audio_div_script.string = new_jscode_str


    # D. Overlay img (appears in js source)
    overlay_basename = 'play-overlay-fddfa5b71982a2d91bc874f4981abb93.png'
    overlay_url = 'https://hpstoryline.edcastcloud.com/assets/' + overlay_basename
    destpath = os.path.join(assetsdir, overlay_basename)
    if not os.path.exists(destpath):
        response = requests.get(overlay_url)
        if response.status_code == 200:
            with open(destpath, 'wb') as overlayimgfile:
                overlayimgfile.write(response.content)
                print('\tSaved overlay_url', overlay_url)

    # E. TODO GET assets/favicon-80ee048bf3522feef23938f79caed29b.ico

    # make sure explicit charset utf-8
    meta = Tag(name='meta', attrs={'charset':'utf-8'})
    doc.head.append(meta)

    indexpath = os.path.join(destdir, 'index.html')
    with open(indexpath,'w') as indexfile:
        indexfile.write(str(doc))



# IMAGES

def img_rewriter(div, source_url, mediadir):
    imgs = div.find_all('img')
    assert len(imgs) <= 1, 'more than one img found'
    for img in imgs:
        img_url = urljoin(source_url, img['src'])
        img_basename = os.path.basename(img_url)
        if '%20' in img_basename:
            img_basename = img_basename.replace('%20','_')
        destpath = os.path.join(mediadir, img_basename)
        if not os.path.exists(destpath):
            response = requests.get(img_url)
            if response.status_code == 200:
                with open(destpath, 'wb') as imgfile:
                    imgfile.write(response.content)
                    print('\tdownloaded img', img_url, 'to', destpath)
            else:
                print('got HTTP', response.status_code, 'for image', img_url)
        img_rel_path = os.path.join(MEDIA_DIR_NAME, img_basename)
        img['src'] = img_rel_path



# CSS rewriter

CSS_URL_RE = re.compile(r"url\(['\"]?(.*?)['\"]?\)")

def css_rewriter(style_str, source_url, destdir):
    assetsdir = os.path.join(destdir, ASSETS_DIR_NAME)
    if not os.path.exists(assetsdir):
        os.makedirs(assetsdir)

    # Download linked fonts and images
    def handle_match(match):
        src = match.group(1)
        if '#' in src:
            src = src.split('#')[0]
        if src.startswith('//localhost'):
            print('\t\tfound localhost')
            return 'url()'
        # Don't download data: files
        if src.startswith('data:'):
            print('\t\tfound data')
            return match.group(0)

        resource_url = urljoin(source_url, src)
        resource_basename = os.path.basename(resource_url)
        destpath = os.path.join(assetsdir, resource_basename)
        if not os.path.exists(destpath):
            response = requests.get(resource_url)
            if response.status_code == 200:
                with open(destpath, 'wb') as resourcefile:
                    resourcefile.write(response.content)
                    print('\tdownloaded', resource_url, 'to', destpath)
            else:
                # print('got HTTP', response.status_code, 'for url', resource_url)
                return 'url()'

        # need path relative to .css file which is alrady in assets/
        resouce_rel_path = resource_basename
        return 'url("%s")' % resouce_rel_path

    return CSS_URL_RE.sub(handle_match, style_str)



# MP3 path form jscode_str

def extract_and_download_mp3path(jscode_str, destdir, mediadirname=MEDIA_DIR_NAME):
    """
    Extract and rewrite the mp3path path from JavaScript code block jscode_str.
    Returns jscode_str with mp3 path rewritten to `{destdir}/media/{mp3filename}`
    """

    parser = Parser()
    tree = parser.parse(jscode_str)

    found = False
    mp3path = None
    mp3filename = None

    for node in nodevisitor.visit(tree):
        if isinstance(node, ast.Object):
            # Object literal { key: val ...}
            for prop in node:
                left, right = prop.left, prop.right
                if isinstance(left, ast.Identifier) and isinstance(right, ast.String):
                    if left.value == 'mp3':
                        found = True
                        mp3path = right.value.lstrip('"').rstrip('"')
                        mp3filename = os.path.basename(mp3path)
                        assets_path = os.path.join(mediadirname, mp3filename)
                        quoted_assets_path = '"' + assets_path + '"'
                        right.value = quoted_assets_path
    if found:
        destpath = os.path.join(destdir, assets_path)
        if not os.path.exists(destpath):
            response = requests.get(mp3path)
            with open(destpath, 'wb') as destfile:
                destfile.write(response.content)
                print('Saved file to', destpath)
        else:
            print('File', destpath, 'already exists')

        return tree.to_ecma()
    else:
        raise ValueError('Could not extract mp3path')






# DOCUMENT CONVERSION HELPER
################################################################################

def is_downloadable_resource(download_url):
    if download_url.strip().startswith('https://s3.amazonaws.com/hp-life-content'):
        return True
    else:
        return False


def transform_downloadable_resource(title, download_url, description=''):
    """
    
    """
    pass



def download_resource(basedir, download_url):
    """
    Downloads the pdf/docx/pptx resource from download_url and returns localpath.
    """
    pass


CONVERTIBLE_DOC_FORMATS = ['.doc', '.docx', '.pptx']

def convert_resource(basedir, download_url):
    """
    Convert a Kolibri-imcopatible document format like pptx or docx to pdf
    using the microwave document conversion service.
    """
    #
    downloadsdirname = 'downloads'
    downloadsdir = os.path.join(basedir, downloadsdirname)
    if not os.path.exists(downloadsdir):
        os.makedirs(downloadsdir)
    #
    resourcesdirname = 'resources'
    destdir = os.path.join(basedir, resourcesdirname)
    if not os.path.exists(destdir):
        os.makedirs(destdir)
    #
    src_filename = os.path.basename(download_url)
    name, ext = os.path.splitext(src_filename)
    if ext in CONVERTIBLE_DOC_FORMATS:
        # destination path for converted file
        dest_filename = name + '.pdf'
        destpath = os.path.join(destdir, dest_filename)
        if not os.path.exists(destpath):
            print('Downloading convertible resource from', download_url)
            # go GET a sample.docx
            response = requests.get(download_url)
            downloadpath = os.path.join(downloadsdir, src_filename)
            with open(downloadpath, 'wb') as localfile:
                localfile.write(response.content)
            # convert it
            microwave_url = 'http://35.185.105.222:8989/unoconv/pdf'
            files = {'file': open(downloadpath, 'rb')}
            response2 = requests.post(microwave_url, files=files)
            # save converted output to destination path
            with open(destpath, 'wb') as localfile:
                localfile.write(response2.content)
    else:
        print('ERROR non-convertible file extension', ext, 'at', download_url)





# DEBUG UTILS
################################################################################

def print_parsed_course_dict(parsed_course):
    """
    Display course tree hierarchy for debugging purposes.
    """
    PARSED_KEYS = ['coursestart', 'story', 'businessconcept', 'technologyskill',
                   'downloadable_resources', 'nextsteps', 'nextsteps_video']
    TRANSFORMED_EXTRA_KEYS = ['title', 'description', 'resources']
    
    for key in PARSED_KEYS:
        if key in parsed_course and parsed_course[key]:
            item = parsed_course[key]
            extra = ''
            if 'url_name' in item:
                extra += ' url_name=' + item['url_name']
            if 'slug' in item:
                extra += ' slug=' + item['slug']
            if 'activity' in item:
                if item['activity']['kind'] == 'hpstoryline':
                    extra += 'story_id=' + str(item['activity']['story_id'])
                else:
                    extra += 'activity_ref=' + str(item['activity']['activity_ref'])
            # print(item)
            print('   -', key,  'kind='+item['kind'], ' \t', extra)
    print('\n')
