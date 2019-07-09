#!/usr/bin/env python
import io
import json
import os
import pickle
# import tarfile
import shutil



from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request



# GOOGLE APIv3 UTILS
################################################################################

# Creds storage
CLIENT_SECRET_FILE = 'credentials/client_secret.json'  # server application -- this will request OAuth2 login
CLIENT_TOKEN_PICKLE = 'credentials/token.pickle'
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

class MemoryCache():
    # workaround for error "file_cache is unavailable when using oauth2client >= 4.0.0 or google-auth'"
    # via https://github.com/googleapis/google-api-python-client/issues/325#issuecomment-274349841
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content



def get_service(service_name=None, service_version=None):
    creds = None
    # The file credentials/token.pickle stores the user access and refresh tokens
    # it is created automatically after the first authorization flow completes
    if os.path.exists(CLIENT_TOKEN_PICKLE):
        with open(CLIENT_TOKEN_PICKLE, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open(CLIENT_TOKEN_PICKLE, 'wb') as token:
            pickle.dump(creds, token)
    service = build(service_name, service_version, credentials=creds, cache=MemoryCache())
    return service



# FILES
################################################################################

FOLDER_MIMETYPE = 'application/vnd.google-apps.folder'
DEFAULT_FILE_FIELDS = 'id,kind,name,mimeType,version,webViewLink,createdTime,modifiedTime'
FORBIDDEN_CHARS_IN_FOLDER_NAMES = ['/', ':']  # will be replaced with space ' '

def itercontents(drive, folder_id, order_by='folder,name', file_fields=DEFAULT_FILE_FIELDS):
    """
    Go through all the contents of the Googgle Drive folder `folder_id` and return
    the info requested in `file_fields` for each file (or folder) found.
    """
    fields = 'nextPageToken, files({})'.format(file_fields)
    params = {
        'q': "'"+folder_id+"' in parents",
        'pageToken': None,
        'orderBy': order_by,
        'fields': fields,
    }
    while True:
        response = drive.files().list(**params).execute()
        for file in response['files']:
            yield file
        if 'nextPageToken' in response:
            params['pageToken'] = response['nextPageToken']
        else:
            break


def list_folder(folder_id):
    """
    Non-recursive list of contents of `folder_id`.
    """
    drive = get_service(service_name='drive', service_version='v3')
    from pprint import pprint
    for item in itercontents(drive, folder_id):
        pprint(item)


def _clean_folder_name(name):
    """Remove forbidden chars from folder name and strip any whitespace."""
    for char in FORBIDDEN_CHARS_IN_FOLDER_NAMES:
        name = name.replace(char, ' ')
    name = name.strip()
    return name


def gdrive_walk(folder_id, file_fields=DEFAULT_FILE_FIELDS, drive=None):
    """
    Returns a `os.walk`-like (path, dirs, files) triples for all descendants of
    `folder_id`. Each dict in the list `files` has attributes in `file_fields`.
    """
    if drive is None:
        drive = get_service(service_name='drive', service_version='v3')

    # get the file root
    root_data = drive.files().get(fileId=folder_id, fields=file_fields).execute()
    assert root_data['mimeType'] == FOLDER_MIMETYPE, 'must start walk at folder'
    assert root_data['id'] == folder_id, 'wrong folder returned'

    # recursively walk tree, keeping track of current position using a stack that
    # stores (path_tuple, folder_id) of next folder to talk
    root_name = _clean_folder_name(root_data['name'])
    stack = [ ((root_name,), folder_id) ]
    while stack:
        path, folder_id = stack.pop()
        dirnames, files = [], []
        for item in itercontents(drive, folder_id, file_fields=file_fields):
            if item['mimeType'] == FOLDER_MIMETYPE:
                dirname = _clean_folder_name(item['name'])
                dirnames.append(dirname)
                item_path = path + (dirname,)
                stack.append( (item_path, item['id']) )
            else:
                files.append(item)
        yield '/'.join(path), dirnames, files


def gdrive_download_file(file_id, destpath, drive=None):
    """
    Download the file `file_id` to local path `destdir/destfilename`.
    """
    if drive is None:
        drive = get_service(service_name='drive', service_version='v3')

    request = drive.files().get_media(fileId=file_id)
    try:
        # print("\tDownloading file - {}".format(destpath))
        fh = io.FileIO(destpath, mode='wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
    except Exception as e:
        print("\tThere was an error while downloding {}".format(file_id))
        print(e)
        return None



# EXPORT
################################################################################

EXPORT_DIRNAME = 'Export'

def export_folder(folder_id, parentdir='', drive=None):
    if not os.path.exists(parentdir):
        os.makedirs(parentdir)
    
    for path, _dirs, files in gdrive_walk(folder_id):
        destdir = os.path.join(parentdir, path)
        print('exporting', len(files), 'files to', destdir)

        if not os.path.exists(destdir):
            os.makedirs(destdir)

        for file in files:
            file_id = file['id']
            filaname = file['name']
            destpath = os.path.join(destdir, filaname)
            if not os.path.exists(destpath):
                gdrive_download_file(file_id, destpath, drive=drive)
            else:
                pass
                # print('skipping download of', destpath, 'since it already exists.')


def export(lang='all'):
    from sushichef import HPLIFE_LANGS
    assert lang == 'all' or lang in HPLIFE_LANGS, 'unexpected lang'
    if lang == 'all':
        langs = HPLIFE_LANGS
    else:
        langs =[lang]

    drive = get_service(service_name='drive', service_version='v3')

    exportdir = os.path.join('chefdata', EXPORT_DIRNAME)
    data_sources = json.load(open('chefdata/data_sources.json'))

    for lang in langs:
        lang_data_sources = data_sources[lang]
        langdir = os.path.join(exportdir, lang)
        if not os.path.exists(langdir):
            print('Creating export dir parent', langdir)
            os.makedirs(langdir)

        # export courses (tar-gzipped XML files stored in a compressed .gz)
        courses = lang_data_sources['courses']
        export_folder(courses['folder_id'], parentdir=langdir, drive=drive)

        # export course activity files
        content = lang_data_sources['content']
        export_folder(content['folder_id'], parentdir=langdir, drive=drive)




# EXTRACT
################################################################################

EXTRACT_DIRNAME = 'Courses'
EXPORT_SUFFIX_TO_STRIP = ' - Storyline output'
FILES_TO_SKIP = ['.DS_Store', 'Thumbs.db', 'ehthumbs.db', 'ehthumbs_vista.db', '.gitkeep']


def extract_courses(lang):
    """
    Extract all the `.gz`s from `chedata/Export/{lang}/{Langname}/{course_name}.gz`
    to `chefdata/Courses/{lang}/{course_name}/course`.
    Returns course_names = list of course names encountered.
    """
    course_names = []

    # src
    exportdir = os.path.join('chefdata', EXPORT_DIRNAME, lang)
    data_sources = json.load(open('chefdata/data_sources.json'))
    lang_data_sources = data_sources[lang]
    dirname = lang_data_sources['courses']['name']
    srcdir = os.path.join(exportdir, dirname)

    # dest
    extractdir = os.path.join('chefdata', EXTRACT_DIRNAME, lang)

    for filename in os.listdir(srcdir):
        if filename.endswith('.gz') or filename.endswith('.tar.gz'):
            gzpath = os.path.join(srcdir, filename)
            if filename.endswith('.tar.gz'):
                course_name = filename.replace('.tar.gz', '')
            elif filename.endswith('.gz'):
                course_name = filename.replace('.gz', '')
            else:
                print('unexpected filename', filename)
            destdir = os.path.join(extractdir, course_name)
            if not os.path.exists(os.path.join(destdir, 'course')):
                print('Untargzipping course', course_name, 'from', gzpath, 'to', destdir)
                shutil.unpack_archive(gzpath, destdir, 'gztar')
            course_names.append(course_name)
        else:
            print('skipping non-gz file', filename)

    return course_names


def process_content_for_course(lang, course_name):
    """
    Copy over all resource folders `chedata/Export/{lang}/{Langname} - Activity Files/{course_name}/{srcfolder}`
    to `chefdata/Courses/{lang}/{course_name}/content/{srcfolder.replace(' - Storyline output','')}`
    Returns `activity_refs` (list) for resource folder names copied over.
    """
    activity_refs = []

    # src
    exportdir = os.path.join('chefdata', EXPORT_DIRNAME, lang)
    data_sources = json.load(open('chefdata/data_sources.json'))
    lang_data_sources = data_sources[lang]
    dirname = lang_data_sources['content']['name']
    srcdir = os.path.join(exportdir, dirname)
    coursedir = os.path.join(srcdir, course_name)
    if not os.path.exists(coursedir):
        print('Could not find Activity-Files for course_name', course_name)
        return []

    # dest
    extractdir = os.path.join('chefdata', EXTRACT_DIRNAME, lang)
    contentdir = os.path.join(extractdir, course_name, 'content')


    for srcfolder in os.listdir(coursedir):
        # src
        if srcfolder in FILES_TO_SKIP:
            continue
        srcpath = os.path.join(coursedir, srcfolder)

        # dest
        if srcfolder.endswith(EXPORT_SUFFIX_TO_STRIP):
            activity_ref = srcfolder.replace(EXPORT_SUFFIX_TO_STRIP, '')
        else:
            activity_ref = srcfolder
        # print('Processing activity_ref', activity_ref)
        resource_folder = os.path.join(contentdir, activity_ref)
        if not os.path.exists(resource_folder):
            shutil.copytree(srcpath, resource_folder)
        activity_refs.append(activity_ref)

    return activity_refs


def extract(lang):
    print('Extracting lang', lang)
    course_names = extract_courses(lang)
    print('\textracting course_names', course_names)

    for course_name in course_names:
        activity_refs = process_content_for_course(lang, course_name)
        print('\t\tprocessed activity_refs', activity_refs)




# CLI (for testing)
################################################################################

if __name__ == '__main__':
    export(lang='es')
    extract(lang='es')
