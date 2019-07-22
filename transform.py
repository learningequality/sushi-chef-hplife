
from bs4 import BeautifulSoup, Tag
import os
import re
import requests

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

from urllib.parse import urljoin



# CONSTANTS
################################################################################

HPSTORYLINE_BASE_URL = 'https://hpstoryline.edcastcloud.com/hp_storyline/story?story='

PHOTO_CLASS = 'field-name-field-hplife-fotoscreen-photo'
BUBBLES_CLASS = 'field-name-field-hplife-fotoscreen-bubbles'
AUDIO_CLASS = 'field-name-field-hplife-fotoscreen-audio'

ASSETS_DIR_NAME = 'assets'
MEDIA_DIR_NAME='media'
SCRIPTS_DIR_NAME = 'scripts'



# TOP-LEVEL FUNCTION
################################################################################

def extract_hpstoryline(contentdir, story_id):
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
################################################################################

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
################################################################################

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




# MP$ path form jscode_str
################################################################################

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


def download_resource(basedir, download_url):
    """
    Downloads the pdf/docx/pptx resource from download_url and returns localpath.
    """
    pass


def transform_downloadable_resource(title, download_url, description=''):
    """
    
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