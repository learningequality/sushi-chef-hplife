#!/usr/bin/env python
import json
import os
import requests


from le_utils.constants import content_kinds, file_types, licenses
from ricecooker.chefs import JsonTreeChef
from ricecooker.classes.licenses import get_license
from ricecooker.utils.jsontrees import write_tree_to_json_tree


from libedx import extract_course_tree
from libedx import print_course

from transform import download_hpstoryline
from transform import extract_course_resouces
# from transform import transform_resource_folder
from transform import get_activity_descriptions_from_coursestart_html
from transform import get_course_description_from_coursestart_html
from transform import make_html5zip_from_resources
from transform import transform_html
from transform import transform_hpstoryline_folder
from transform import transform_articulate_storyline_folder


DEBUG_MODE = True

COURSES_DIR = 'chefdata/Courses'

HPLIFE_LICENSE = get_license(licenses.CC_BY, copyright_holder='HP LIFE').as_dict()

HPLIFE_LANGS = ['es', 'fr', 'en', 'ar', 'hi']


HPLIFE_COURSE_STRUCTURE_CHECK_STRINGS = {
    'en': {
        'coursestart': 'Start Course',
        'story': 'Story',
        'businessconcept': 'Business Concept',
        'technologyskill': 'Technology Skill',
        'coursefeedback': 'Course',
        'nextsteps': 'Steps',
        'downloadable_resources': 'Downloadable Resources',
    },
    'es': {
        'coursestart': 'Inicio',
        'story': 'Narración',
        'businessconcept': 'Concepto',
        'technologyskill': 'Habilidad',
        'coursefeedback': 'Encuesta',
        'nextsteps': 'asos', # 'Pasos siguientes'
        'downloadable_resources': 'Recursos descargable',
    },
    'fr': {
        'coursestart': 'Démarrer',
        'story': 'Histoire',
        'businessconcept': 'Concept commercial',
        'technologyskill': 'Compétence technologiqu',
        'coursefeedback': 'Sondage',
        'nextsteps': 'Étapes suivantes',
        'downloadable_resources': 'Ressources',
    }
}



HPLIFE_STRINGS = {
    'en': {
        'resources': 'Resources',
        'downloadable_resources': 'Downloadable resources',
    },
    'es': {
        'resources': 'Recursos',
        'downloadable_resources': 'Recursos descargables',
    },
    'fr': {
        'resources': 'Ressources',
        'downloadable_resources': 'Ressources téléchargeables',
    }
}





# PRE-VALIDATE
################################################################################

CONTENT_FOLDER_RENAMES = {
    '2355hpl-es06': {
        'technologyskill' : {
            'YTA_TS_ES_FIXED_reload': 'TU6_Tech_Skill_PRO_es - Storyline output',
        },
    },
    '2422hpl-fr06': {
        'technologyskill' : {
            'YTA_TS_FR_FIXED_reload': 'TU6_Tech_Skill_fr - Storyline output',
        },
    },
    '2287hpl-en06': {
        'technologyskill' : {
            'YTA_TS_EN_fixed_TEST_reload_3': 'TU6_Tech_Skill_PRO_en - Storyline output',
        },
    },
    '4788hpl-fr27': {
        'businessconcept': {
            '27-DT1-ST-FR-NR-MOB': '27-DT2-BC-FR-NR-MOB',  # fixes bug in course
        },
    },
}


def tranform_and_prevalidate(course_data, lang, coursedir, contentdir):
    """
    Performs necessary checks to know we have a valid course:
      - Exports the hpstyryline legacy files by running `download_hpstoryline`
      - Rename non-standard articulate storyline folder names
      - Ensure all activity files are present
    Returns validated, modified `course_data` dict or `None` if validation fails.
    """

    # Missing data for Marketing de medios sociales
    if course_data['display_name'] == 'Marketing de medios sociales':
        return None

    parsed_tree = parse_course_tree(course_data, lang)
    missing_activity_refs = []
    for key in ['story', 'businessconcept', 'technologyskill']:
        item = parsed_tree[key]
        kind = item['kind']
        assert kind == 'problem'

        # Old-style hpstoryline
        if kind == 'problem' and 'activity' in item and item['activity']['kind'] == 'hpstoryline':
            story_id = item['activity']['story_id']
            contentdir_story_id_path = os.path.join(contentdir, story_id)
            if not os.path.exists(contentdir_story_id_path):
                download_hpstoryline(contentdir, story_id)
            assert os.path.exists(contentdir_story_id_path)

        # New-style Articulate Storyline
        elif kind == 'problem' and 'activity' in item:
            course_id = course_data['course']
            activity_ref = item['activity']['activity_ref']

            if course_id in CONTENT_FOLDER_RENAMES \
                and key in CONTENT_FOLDER_RENAMES[course_id] \
                and activity_ref in CONTENT_FOLDER_RENAMES[course_id][key]:
                activity_ref = CONTENT_FOLDER_RENAMES[course_id][key][activity_ref]
                item['activity']['activity_ref'] = activity_ref

            activity_ref_sourcedir = os.path.join(contentdir, activity_ref)
            if not os.path.exists(activity_ref_sourcedir):
                missing_activity_refs.append(activity_ref)
        else:
            print('EEEEE Unrecognized problem item', item)

    if not missing_activity_refs:
        return course_data
    else:
        print('in course name', course_data['display_name'], 'with course id', course_data['course'])
        print('in coursedir', coursedir)
        print('we\'re missing activity folders', missing_activity_refs)
        folders = os.listdir(contentdir)
        candidate_folders = []
        for folder in folders:
            if not folder.endswith('_webroot') \
                and not folder.startswith('Downloadab') \
                and not folder.startswith('es_') \
                and not folder.startswith('fr_') \
                and not folder.startswith('en_') \
                and not folder == '.DS_Store':
                    candidate_folders.append(folder)
        print('available', candidate_folders)
        return None


# PARSE TREEE
################################################################################

def flatten_chapter(chapter):
    """
    Return a flat list of the content items chapter while checking assumptions.
    """
    content_items = []
    assert len(chapter['children']) <= 2, 'wrong number of sequentials'
    for sequential in chapter['children']:
        assert len(sequential['children']) == 1, 'wrong number of verticals'
        for vertical in sequential['children']:
            assert len(vertical['children']) <= 2, 'wrong number of items'
            for content_item in vertical['children']:
                content_item['sequential_title'] = sequential['display_name']
                content_items.append(content_item)
    return content_items


def parse_course_tree(course_data, lang):
    """
    Parse the edX XML structure and pluck the neessary components form the tree
    to return a `parsed_tree` that looks like this:
        parsed_tree = {
            'coursestart': {},
            'story': {},
            'businessconcept': {},
            'technologyskill': {},          # first node under technologyskill
            'downloadable_resources': {},   # second node under technologyskill
            'nextsteps': {},
            'nextsteps_video': {},
        }
    """
    # print('in parse_course_tree', course_data['course'])

    parsed_tree = {
        'coursestart': {},
        'story': {},
        'businessconcept': {},
        'technologyskill': {},          # first node under technologyskill
        'downloadable_resources': {},   # second node under technologyskill
        'nextsteps': {},
        'nextsteps_video': {},
    }

    check_strings = HPLIFE_COURSE_STRUCTURE_CHECK_STRINGS[lang]

    # course chapters
    chapters = course_data['children']

    # course start
    chapter = chapters[0]
    chapter_title = chapter['display_name']
    assert check_strings['coursestart'] in chapter_title, 'bad ch. title ' + chapter_title
    content_items = flatten_chapter(chapter)
    assert len(content_items) == 1, 'unexpected # of items in course start'
    content_item = content_items[0]
    content_item['title'] = chapter_title
    assert content_item['kind'] == 'html', 'unexpected item kind in course start'
    parsed_tree['coursestart'] = content_item

    # story
    chapter = chapters[1]
    chapter_title = chapter['display_name']
    assert check_strings['story'] in chapter_title, 'bad ch. title ' + chapter_title
    content_items = flatten_chapter(chapter)
    assert len(content_items) <= 2, 'unexpected # of items in story'
    content_item = content_items[0]
    content_item['title'] = chapter_title
    assert content_item['kind'] == 'problem', 'unexpected item kind in story'
    parsed_tree['story'] = content_item
    if len(content_items) == 2:
        pass
        # print('skipping content_item', content_items[1])

    # businessconcept
    chapter = chapters[2]
    chapter_title = chapter['display_name'].strip()
    assert check_strings['businessconcept'] in chapter_title, 'bad ch. title ' + chapter_title
    content_items = flatten_chapter(chapter)
    assert len(content_items) == 1, 'unexpected # of items in businessconcept'
    content_item = content_items[0]
    content_item['title'] = chapter_title
    assert content_item['kind'] == 'problem', 'unexpected item kind in businessconcept'
    parsed_tree['businessconcept'] = content_item

    # technologyskill
    chapter = chapters[3]
    chapter_title = chapter['display_name']
    assert check_strings['technologyskill'] in chapter_title, 'bad ch. title ' + chapter_title
    content_items = flatten_chapter(chapter)
    assert len(content_items) == 2, 'unexpected # of items in technologyskill'
    # technologyskill activity
    content_item = content_items[0]
    content_item['title'] = chapter_title
    assert content_item['kind'] == 'problem', 'unexpected item kind in technologyskill'
    parsed_tree['technologyskill'] = content_item
    # downloadable_resources
    second_item = content_items[1]
    assert second_item['kind'] == 'html', 'unexpected item kind in technologyskill'
    second_item['title'] = second_item['sequential_title'] 
    parsed_tree['downloadable_resources'] = second_item

    # skip course feedback
    chapter = chapters[4]
    chapter_title = chapter['display_name']
    assert check_strings['coursefeedback'] in chapter_title, 'bad ch. title ' + chapter_title

    # next steps
    chapter = chapters[5]
    chapter_title = chapter['display_name']
    assert check_strings['nextsteps'] in chapter_title, 'bad ch. title ' + chapter_title
    content_items = flatten_chapter(chapter)
    assert len(content_items) <= 2, 'unexpected # of items in nextsteps'
    content_item = content_items[0]
    content_item['title'] = chapter_title
    assert content_item['kind'] == 'html', 'unexpected item kind in nextsteps'
    parsed_tree['nextsteps'] = content_item
    if len(content_items) == 2:
        second_item = content_items[1]
        second_item['title'] = second_item['display_name']
        assert second_item['kind'] == 'video', 'unexpected item kind in nextsteps'
        parsed_tree['nextsteps_video'] = second_item

    # skip wiki
    chapter = chapters[6]
    assert 'display_name' not in chapter, 'unexpected wiki has title'

    return parsed_tree




def process_course_tree(parsed_tree, lang, contentdir, course_id):
    """
    Tranform the parsed_tree for a course into channel subfolder for this course.
    Includes:
    1. extract info from coursestart
    2. download resources
    3. modify next steps
    Returns a parsed_tree with extra info:
        parsed_tree = {
            'description': "",
            'story': {},
            'businessconcept': {},
            'technologyskill': {},
            'nextsteps': {},
            'nextsteps_video': {},
            'resources': [
                {
                    'title': 'Hoja de trabajo',
                    'path': '{contentdir}/downloads/Hoja+de+trabajo.docx',
                    'ext': 'docx',
                    'filename': 'Hoja de trabajo.docx',
                    'convertedfilename': 'Hoja de trabajo.pdf',
                    'convertedpath': '{contentdir}/converted/Hoja de trabajo.pdf',
                },
            ]
        }    
    """
    # Extract descriptions from coursestart
    coursestart = parsed_tree['coursestart']
    course_description = get_course_description_from_coursestart_html(coursestart['content'], lang)
    parsed_tree['description'] = course_description
    #
    activity_descriptions = get_activity_descriptions_from_coursestart_html(coursestart['content'], lang)
    for key in ['story', 'businessconcept', 'technologyskill', 'nextsteps']:
        parsed_tree[key]['description'] = activity_descriptions[key]

    # Extract resouces
    parsed_tree = extract_course_resouces(parsed_tree, contentdir, course_id)

    # TODO: process next step

    return parsed_tree




# BUILD RICECOOKER TREE
################################################################################

def build_subtree_from_course(course, containerdir):
    print('Building a tree from course', course)
    lang = course['lang']
    course_dict = dict(
        kind=content_kinds.TOPIC,
        title=course['name'],
        language=lang,
        thumbnail='chefdata/thumbnails/new_channel_thumbnail.png',
        children = [],
    )
    basedir = os.path.join(containerdir, course['path'])
    contentdir = os.path.join(basedir, 'content')
    coursedir = os.path.join(basedir, 'course')
    course_data = extract_course_tree(coursedir)
    course_dict['source_id'] = course_data['course']

    course_data = tranform_and_prevalidate(course_data, lang, coursedir, contentdir)
    if course_data is None:
        return None

    parsed_tree = parse_course_tree(course_data, lang)
    parsed_tree = process_course_tree(parsed_tree, lang, contentdir, course_data['course'])
    course_dict['description'] = parsed_tree['description']

    for key in ['story', 'businessconcept', 'technologyskill', 'resources', 'nextsteps', 'nextsteps_video']:

        if key == 'resources':
            resources = parsed_tree['resources']
            if resources:
                # First add the Resources folder
                topic_dict = dict(
                    kind=content_kinds.TOPIC,
                    title=HPLIFE_STRINGS[lang]['resources'],
                    source_id=course_dict['title'] + '___' + key,
                    license=HPLIFE_LICENSE,
                    language=lang,
                    thumbnail='chefdata/thumbnails/resources_folder_thumbnail.png',
                    children=[],
                )
                course_dict['children'].append(topic_dict)

                # Second add all the converted resources as PDFs
                resource_urls_seen = []
                for resource in resources:
                    if resource['url'] not in resource_urls_seen:
                        ext = resource['ext']
                        if ext == 'pdf' or 'convertedpath' in resource:
                            pdf_node = dict(
                                kind=content_kinds.DOCUMENT,
                                title=resource['title'],
                                description=resource.get('description', ''),
                                source_id=resource['url'],
                                license=HPLIFE_LICENSE,
                                language=lang,
                                files=[],
                            )
                            if ext == 'pdf':
                                path = resource['path']
                            elif 'convertedpath' in resource:
                                path = resource['convertedpath']
                            else:
                                raise ValueError('unexpected situation yo!')
                            file_dict = dict(
                                file_type=file_types.DOCUMENT,
                                path=path,
                                language=lang,
                            )
                            pdf_node['files'].append(file_dict)
                            topic_dict['children'].append(pdf_node)
                            resource_urls_seen.append(resource['url'])
                    else:
                        print('skipping duplicate resource', resource)

                # Third add the zip file containing all non-pdf downloadable resources
                nonpdfresources = [r for r in resources if r['ext'] != 'pdf']
                if nonpdfresources:
                    html5_node = dict(
                        kind=content_kinds.HTML5,
                        title=HPLIFE_STRINGS[lang]['downloadable_resources'],
                        description=resource.get('description', ''),
                        source_id=course_dict['title'] + '__' + key + '__downloadable_resources',
                        license=HPLIFE_LICENSE,
                        language=lang,
                        thumbnail='chefdata/thumbnails/downloadable_resources_thumbnail.png',
                        files=[],
                    )
                    zip_path = make_html5zip_from_resources(nonpdfresources, contentdir, lang)
                    zip_file = dict(
                        file_type=file_types.HTML5,
                        path=zip_path,
                        language=lang,
                    )
                    html5_node['files'].append(zip_file)
                    topic_dict['children'].append(html5_node)


        elif key == 'nextsteps_video':
            nextsteps_video = parsed_tree[key]
            if nextsteps_video:
                youtube_id = nextsteps_video['youtube_id_1_0']
                video_node = dict(
                    kind=content_kinds.VIDEO,
                    source_id=youtube_id,
                    language=lang,
                    title=nextsteps_video['title'],
                    description=nextsteps_video.get('description', ''),
                    license=HPLIFE_LICENSE,
                    files=[],
                )
                video_file = dict(
                    file_type=file_types.VIDEO,
                    youtube_id=youtube_id,
                    language=lang,
                    high_resolution=False,
                )
                video_node['files'].append(video_file)
                course_dict['children'].append(video_node)


        else:
            item = parsed_tree[key]
            html5_dict = dict(
                kind=content_kinds.HTML5,
                title=item['title'],
                description=item.get('description', ''),
                source_id=course_dict['title'] + '___' + key,
                license=HPLIFE_LICENSE,
                language=lang,
                files=[],
            )

            kind = item['kind']

            # # Local resouce folder
            # if kind == 'html' and 'activity' in item:
            #     activity_ref = item['activity']['activity_ref']
            #     zip_info = transform_resource_folder(contentdir, activity_ref, item['content'])
            #     if zip_info:
            #         zippath = zip_info['zippath']
            #         html5_dict['source_id'] = zip_info['source_id']
            #         html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
            #     else:
            #         continue

            # Generic HTML
            if kind == 'html':
                zip_info = transform_html(item['content'])
                if zip_info:
                    zippath = zip_info['zippath']
                    html5_dict['source_id'] = zip_info['source_id']
                    # html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
                else:
                    continue

            # Old-style hpstoryline
            elif kind == 'problem' and 'activity' in item and item['activity']['kind'] == 'hpstoryline':
                story_id = item['activity']['story_id']
                contentdir_story_id_path = os.path.join(contentdir, story_id)
                if not os.path.exists(contentdir_story_id_path):
                    download_hpstoryline(contentdir, story_id)
                zip_info = transform_hpstoryline_folder(contentdir, story_id, item)
                if zip_info:
                    html5_dict['thumbnail'] = zip_info['thumbnail']
                    html5_dict['source_id'] = zip_info['source_id']
                    # html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
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
                    # html5_dict['description'] = 'Content taken from ' + zip_info['source_id']
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
                language=lang,
            )
            html5_dict['files'].append(file_dict)
            course_dict['children'].append(html5_dict)

    return course_dict






# CHEF
################################################################################


CHANNEL_TITLE_LOOKUP = {
    'ar': 'HP LIFE - Cours (العَرَبِيَّة‎)',
    'en': 'HP LIFE - Courses (English)',
    'es': 'HP LIFE - Cursos (Español)',
    'fr': 'HP LIFE - Cours (Français)',
    'hi': 'HP LIFE - Cours (हिन्दी)',
}


CHANNEL_DESCRIPTION_LOOKUP = {
    'ar': "HP LIFE in Arabic",
    'en': "A program of the HP Foundation, this collection of short introductory courses helps adults learn independently various digital and entrepreneurship skills, including information technology, starting a business, online sales, and marketing. Appropriate for adults who are curious to develop their professional skills or simply learn about new opportunities.",
    'es': "Una iniciativa de HP Foundation, esta colección de cursos introductorios y breves ayuda a los adultos a adquirir habilidades en tecnología y emprendimiento de forma independiente, incluye tecnologías de la información, empezar  un negocio, venta en línea y marketing. Son apropiados para adultos con curiosidad por desarrollarse profesionalmente o por aprender nuevas oportunidades.",
    'fr': "Un programme de HP Foundation, les cours HP LIFE sont conçus pour aider les adultes à apprendre de manière autonome diverses compétences numériques, y compris les technologies de l'information, la création d'entreprise, les ventes en ligne et le marketing. Ces cours conviennent aux adultes qui sont curieux de développer leurs compétences professionnelles ou poursuivre de nouvelles opportunités.",
    'hi': "HP LIFE in Hindi",
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
            thumbnail='chefdata/thumbnails/new_channel_thumbnail.png',
            language=lang,
            children=[],
        )
        print('in pre_run; channel info = ', ricecooker_json_tree)

        containerdir = os.path.join(COURSES_DIR, lang)
        course_list = json.load(open(os.path.join(containerdir, 'course_list.json')))
        for course in course_list['courses']:
            course_dict = build_subtree_from_course(course, containerdir)
            if course_dict:
                ricecooker_json_tree['children'].append(course_dict)
            else:
                print('WARNING: Skipping course', course['name'], 'because it failed to pre-validate')
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

