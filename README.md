HP LIFE
=======
Content import for the HP LIFE courses available in multiple languages.

All HP-LIFE courses have the following structure (3 interactive activities):
- Story slides: into about what the course is about
- Business concept: Actual course
- Technology Skills: The user gets the option to work on the simulator and practice
  what is learnt in the above activity



Source data
-----------
HP LIFE content is made available as a combination of edX course (XML metadata)
and folders containing the HTML content of each activity.

    chefdata/subdir/Course Name/
        course/
            ├── about
            ├── assets
            ├── chapter
            ├── course 
            ├── course.xml
            ├── html
            ├── info
            ├── policies
            ├── problem
            ├── sequential
            ├── tabs
            └── vertical
        content/
            activity_ref1/
            activity_ref2/
            activity_ref3/


Extract workflow
----------------

### POC (sample channel)
Use a manual process for pre-processing and putting the data into the desired form
that includes the following steps:
  - unzip the course archive (unzip to directory `course/`)
  - unip the content archive and rename the containing folder to `content/` and
    make sure all the activity refs match what appears in `course/`
  - Manually document paths in the `course_list.json`

### Production (final HP LIFE channels)
  - download all edX courses via API?
  - obtain all content directly from s3 buckets
  - process the above to place them in standard `course/` and `content/` folder format



Design
------
We break down the cheffing process into three independent tasks:

### A. Parse edX XML
In: edX `course/` directory that contains XML metadata files (and some HTML)  
Out: `edX_course_tree.json` with `activity` content pointers  of the form:  

    activity_ref = {
        kind = 'articulate_storyline',
        bucket_url = 'https://s3.amazonaws.com/hp-life-content',
        bucket_path = 'Antonio+TechClass+Academy/Cash+Flow/Chinese',
        activity_ref = 'CF_BC_CH1',
        entrypoint = 'story_html5.html'
    }

The assumption is that `activity_ref` is a subfolder in the `content/` folder of
that course.


### B. Prepare content folders

#### B1. Articulate Storyline
In: folder containing activity content of kind=`articulate_storyline` (HTML+assets)
Out: HTML5Zip file + activity_metadata ?  
Steps:
  - remove .swf / .flv files
  - remove story.html
  - rename `story_html5.html` to `index.html` (Kolibri expects the "main" file to be called index.html)
  - Downloaded and localized javascript libraries:
    - jschannel.js
    - edcast.js
    - zepto.min.js
  - Rewrite links
  - Created a file `{activity_ref}_webroot.zip` from the activity folder
  - Save necessary metadata as `{activity_ref}_metadata.json`

#### B2. Resources Folder
In: folder containing file resources of kind=`resources_folder` (files in a static webserver)
Out: HTML5Zip file + activity_metadata
- Created a file `{activity_ref}_webroot.zip` from the folder
- Save necessary metadata as `{activity_ref}_metadata.json`



### C. Generate channel json
In: `course_list.json` + `edX_course_tree.json` + content metadata for each activity  
Out: `ricecooker_json_tree.json` for the channel  


### D. Upload
In: `ricecooker_json_tree.json` + content zips  
Out: Channel on Studio  
Run the `linecook.py` chef to upload to Kolibri Studio

